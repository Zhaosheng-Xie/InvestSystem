from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest

from invest_system import (
    STORAGE_SCHEMA_VERSION,
    STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
    AdmissionStatus,
    ArtifactRead,
    AuditReplayRequest,
    CacheIntegrityError,
    CacheIssueKind,
    FixedClock,
    ImmutableMappingError,
    ReleaseAccessError,
    ReleaseCacheStore,
    ReleaseStatus,
    RunPurpose,
    StorageSchemaError,
    StrategyRunManifest,
    canonical_json_bytes,
)

FIXED_TIME = datetime(2026, 7, 31, 8, tzinfo=UTC)
ADMISSION_ID = "synthetic_admission_observation_stage1_001"


def digest(content: bytes) -> str:
    return sha256(content).hexdigest()


@pytest.fixture
def store(tmp_path: Path) -> ReleaseCacheStore:
    return ReleaseCacheStore(
        database_path=tmp_path / "state" / "invest_system.sqlite3",
        cache_root=tmp_path / "cache",
        soft_limit_bytes=64,
        clock=FixedClock(FIXED_TIME),
    )


def table_count(database: Path, table: str) -> int:
    allowed = {
        "cache_objects",
        "pin_artifacts",
        "release_admission_observations",
        "release_artifacts",
        "release_pins",
        "release_status_observations",
        "releases",
    }
    if table not in allowed:
        raise ValueError("unexpected test table")
    with sqlite3.connect(database) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def authorize_for_manifest(
    store: ReleaseCacheStore,
    manifest: StrategyRunManifest,
    *,
    admission_id: str | None = None,
) -> str:
    admission_id = admission_id or manifest.release_admission_observation_id
    release_id = manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id=manifest.release_status_observation_id,
        strategy_input_ref=manifest.strategy_input_ref,
    )
    store.record_release_admission(
        release_id,
        status_observation_id=manifest.release_status_observation_id,
        admission_observation_id=admission_id,
        admission_status=AdmissionStatus.AUTHORIZED,
    )
    return release_id


def put(
    store: ReleaseCacheStore,
    release_id: str,
    artifact_id: str,
    content: bytes,
) -> Path:
    return store.put_artifact(
        release_id=release_id,
        artifact_id=artifact_id,
        content=content,
        expected_sha256=digest(content),
    ).path


def pin(
    store: ReleaseCacheStore,
    manifest: StrategyRunManifest,
    *artifact_ids: str,
) -> bool:
    return store.pin_run(manifest, artifact_ids=artifact_ids)


def test_migrates_empty_database_and_reopens_at_known_version(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    cache = tmp_path / "cache"

    first = ReleaseCacheStore(database_path=database, cache_root=cache)
    second = ReleaseCacheStore(database_path=database, cache_root=cache)

    assert first.schema_version == STORAGE_SCHEMA_VERSION
    assert second.schema_version == STORAGE_SCHEMA_VERSION
    assert table_count(database, "releases") == 0


def test_concurrent_first_initialization_is_serialized(tmp_path: Path) -> None:
    database = tmp_path / "state.sqlite3"
    cache = tmp_path / "cache"
    workers = 6
    barrier = Barrier(workers)

    def initialize() -> int:
        barrier.wait(timeout=5)
        return ReleaseCacheStore(database_path=database, cache_root=cache).schema_version

    with ThreadPoolExecutor(max_workers=workers) as executor:
        versions = list(executor.map(lambda _index: initialize(), range(workers)))

    assert versions == [STORAGE_SCHEMA_VERSION] * workers


def test_unknown_or_unversioned_nonempty_schema_fails_closed(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.sqlite3"
    with sqlite3.connect(unknown) as connection:
        connection.execute("PRAGMA user_version = 99")
    with pytest.raises(StorageSchemaError, match="unsupported storage schema"):
        ReleaseCacheStore(database_path=unknown, cache_root=tmp_path / "unknown-cache")

    unversioned = tmp_path / "unversioned.sqlite3"
    with sqlite3.connect(unversioned) as connection:
        connection.execute("CREATE TABLE foreign_state(value TEXT)")
    with pytest.raises(StorageSchemaError, match="unversioned non-empty"):
        ReleaseCacheStore(database_path=unversioned, cache_root=tmp_path / "foreign-cache")


@pytest.mark.parametrize(
    "damage",
    [
        "unknown-table",
        "wrong-index",
        "trigger",
        "view",
        "missing-check",
        "missing-foreign-key",
    ],
)
def test_bogus_v1_metadata_or_mutating_object_is_rejected(tmp_path: Path, damage: str) -> None:
    database = tmp_path / f"{damage}.sqlite3"
    cache = tmp_path / f"{damage}-cache"
    ReleaseCacheStore(database_path=database, cache_root=cache)
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        if damage == "unknown-table":
            connection.execute("CREATE TABLE rogue(value TEXT)")
        elif damage == "wrong-index":
            connection.execute("DROP INDEX release_artifacts_sha_idx")
            connection.execute(
                "CREATE INDEX release_artifacts_sha_idx ON release_artifacts(artifact_id)"
            )
        elif damage == "trigger":
            connection.execute(
                """CREATE TRIGGER rogue AFTER INSERT ON releases
                   BEGIN DELETE FROM releases WHERE release_id = NEW.release_id; END"""
            )
        elif damage == "view":
            connection.execute("CREATE VIEW rogue AS SELECT * FROM releases")
        elif damage == "missing-check":
            connection.execute("DROP TABLE cache_objects")
            connection.execute(
                """CREATE TABLE cache_objects (
                    sha256 TEXT NOT NULL PRIMARY KEY,
                    size_bytes INTEGER NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    stored_at TEXT NOT NULL
                )"""
            )
        else:
            connection.execute("DROP INDEX release_artifacts_sha_idx")
            connection.execute("DROP TABLE release_artifacts")
            connection.execute(
                """CREATE TABLE release_artifacts (
                    release_id TEXT NOT NULL,
                    artifact_id TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    PRIMARY KEY (release_id, artifact_id),
                    UNIQUE (release_id, artifact_id, sha256)
                )"""
            )
            connection.execute(
                "CREATE INDEX release_artifacts_sha_idx ON release_artifacts(sha256)"
            )

    with pytest.raises(StorageSchemaError, match="unknown|mismatch|constraint"):
        ReleaseCacheStore(database_path=database, cache_root=cache)


def test_hash_mismatch_writes_no_file_or_metadata(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = strategy_run_manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id="status_001",
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    with pytest.raises(CacheIntegrityError, match="artifact hash mismatch"):
        store.put_artifact(
            release_id=release_id,
            artifact_id="manifest",
            content=b"actual",
            expected_sha256=digest(b"different"),
        )
    assert store.quota_report().registered_bytes == 0
    assert list(store.cache_root.rglob("*")) == []


def test_artifact_mapping_is_atomic_immutable_and_soft_quota_never_blocks(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = strategy_run_manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id="status_001",
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    content = b"x" * 65
    first = put(store, release_id, "manifest", content)
    second = put(store, release_id, "manifest", content)
    assert first == second
    assert store.quota_report().over_limit
    with pytest.raises(ImmutableMappingError, match="different bytes"):
        put(store, release_id, "manifest", b"different")


def test_provider_status_and_local_admission_are_separate_latest_axes(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = strategy_run_manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id=strategy_run_manifest.release_status_observation_id,
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    put(store, release_id, "manifest", b"bytes")
    with pytest.raises(ReleaseAccessError, match="admission"):
        pin(store, strategy_run_manifest, "manifest")

    store.record_release_admission(
        release_id,
        status_observation_id=strategy_run_manifest.release_status_observation_id,
        admission_observation_id="unconfirmed_001",
        admission_status=AdmissionStatus.UNCONFIRMED,
    )
    with pytest.raises(ReleaseAccessError, match="not authorized"):
        pin(
            store,
            replace(
                strategy_run_manifest,
                release_admission_observation_id="unconfirmed_001",
            ),
            "manifest",
        )

    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id="newer_provider_observation_001",
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    store.record_release_admission(
        release_id,
        status_observation_id="newer_provider_observation_001",
        admission_observation_id=ADMISSION_ID,
        admission_status=AdmissionStatus.AUTHORIZED,
    )
    with pytest.raises(ReleaseAccessError, match="latest provider observation"):
        pin(store, strategy_run_manifest, "manifest")


def test_release_identity_cannot_drift_across_provider_observations(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    reference = strategy_run_manifest.strategy_input_ref
    changed_reference = replace(
        reference,
        manifest_hash=replace(reference.manifest_hash, value="f" * 64),
    )
    with pytest.raises(ImmutableMappingError, match="identity is immutable"):
        store.record_release_status(
            release_id,
            status=ReleaseStatus.PUBLISHED,
            status_observation_id="identity_drift_001",
            strategy_input_ref=changed_reference,
        )


def test_pin_rechecks_full_provider_observation_identity(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    put(store, release_id, "manifest", b"manifest")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """UPDATE release_status_observations SET manifest_hash_value = ?
               WHERE status_observation_id = ?""",
            ("f" * 64, strategy_run_manifest.release_status_observation_id),
        )
    with pytest.raises(ReleaseAccessError, match="does not bind"):
        pin(store, strategy_run_manifest, "manifest")


def test_withdrawal_is_terminal_and_invalidates_current_admission(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    store.record_release_status(
        release_id,
        status=ReleaseStatus.WITHDRAWN,
        status_observation_id="withdrawn_001",
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
        reason="provider withdrawal",
    )
    with pytest.raises(ReleaseAccessError, match="irreversible"):
        store.record_release_status(
            release_id,
            status=ReleaseStatus.PUBLISHED,
            status_observation_id="illegal_reactivation_001",
            strategy_input_ref=strategy_run_manifest.strategy_input_ref,
        )
    with pytest.raises(ReleaseAccessError, match="cannot be admitted"):
        store.record_release_admission(
            release_id,
            status_observation_id="withdrawn_001",
            admission_observation_id="illegal_admission_001",
            admission_status=AdmissionStatus.AUTHORIZED,
        )


def test_pin_is_exact_run_subset_and_does_not_freeze_release_globally(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    put(store, release_id, "manifest", b"manifest")
    put(store, release_id, "facts_a", b"facts a")
    assert pin(store, strategy_run_manifest, "manifest")
    assert not pin(store, strategy_run_manifest, "manifest")

    put(store, release_id, "facts_b", b"facts b")
    second = replace(strategy_run_manifest, run_id="synthetic_run_stage1_002")
    assert pin(store, second, "facts_a", "facts_b")
    with sqlite3.connect(store.database_path) as connection:
        snapshots = connection.execute(
            "SELECT run_id, artifact_id FROM pin_artifacts ORDER BY run_id, artifact_id"
        ).fetchall()
    assert snapshots == [
        (strategy_run_manifest.run_id, "manifest"),
        (second.run_id, "facts_a"),
        (second.run_id, "facts_b"),
    ]
    with pytest.raises(ImmutableMappingError, match="different inputs"):
        pin(store, strategy_run_manifest, "manifest", "facts_a")


def test_pin_preserves_original_canonical_bytes_hash_mode_and_profile(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    put(store, release_id, "manifest", b"manifest")
    pin(store, strategy_run_manifest, "manifest")
    expected = canonical_json_bytes(strategy_run_manifest)
    with sqlite3.connect(store.database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM release_pins").fetchone()
    assert bytes(row["run_manifest_canonical"]) == expected
    assert row["run_manifest_hash_value"] == digest(expected)
    assert row["canonical_profile_version"] == (STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION)
    assert row["source_run_mode"] == strategy_run_manifest.run_mode.value


def test_normal_read_requires_prior_atomic_pin_and_returns_context(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    content = b"manifest"
    put(store, release_id, "manifest", content)
    with pytest.raises(ReleaseAccessError, match="not admitted and pinned"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=strategy_run_manifest,
        )
    pin(store, strategy_run_manifest, "manifest")
    result = store.read_artifact(
        artifact_id="manifest",
        purpose=RunPurpose.NEW_RUN,
        source_manifest=strategy_run_manifest,
    )
    assert isinstance(result, ArtifactRead)
    assert result.content == content
    assert result.purpose is RunPurpose.NEW_RUN
    assert result.current_access.authorized


def test_audit_request_is_separate_read_only_capability_and_reports_withdrawal(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    content = b"historical"
    put(store, release_id, "manifest", content)
    pin(store, strategy_run_manifest, "manifest")
    manifest_hash = digest(canonical_json_bytes(strategy_run_manifest))
    request = AuditReplayRequest(strategy_run_manifest.run_id, manifest_hash)
    store.record_release_status(
        release_id,
        status=ReleaseStatus.WITHDRAWN,
        status_observation_id="withdrawn_001",
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
        reason="provider withdrawal",
    )

    with pytest.raises(ReleaseAccessError, match="lost current"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=strategy_run_manifest,
        )

    result = store.read_artifact(
        artifact_id="manifest",
        purpose=RunPurpose.AUDIT_REPLAY,
        source_manifest=strategy_run_manifest,
        audit_request=request,
    )
    assert result.content == content
    assert result.purpose is RunPurpose.AUDIT_REPLAY
    assert result.source_run_id == strategy_run_manifest.run_id
    assert result.source_manifest_hash == manifest_hash
    assert result.current_access.provider_status is ReleaseStatus.WITHDRAWN
    assert result.current_access.authorized is False
    assert result.current_access.admission_status is None

    with pytest.raises(ReleaseAccessError, match="ordinary run"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=strategy_run_manifest,
            audit_request=request,
        )
    with pytest.raises(TypeError, match="StrategyRunManifest"):
        store.pin_run(
            request,  # type: ignore[arg-type]
            artifact_ids=("manifest",),
        )


def test_audit_replay_rejects_changed_manifest_or_request_hash(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    put(store, release_id, "manifest", b"historical")
    pin(store, strategy_run_manifest, "manifest")
    manifest_hash = digest(canonical_json_bytes(strategy_run_manifest))
    changed = replace(strategy_run_manifest, random_seed=1)

    with pytest.raises(ReleaseAccessError, match="does not identify"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.AUDIT_REPLAY,
            source_manifest=changed,
            audit_request=AuditReplayRequest(strategy_run_manifest.run_id, manifest_hash),
        )
    with pytest.raises(ReleaseAccessError, match="AuditReplayRequest"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.AUDIT_REPLAY,
            source_manifest=strategy_run_manifest,
        )


def test_audit_detects_tampered_pin_artifact_mapping(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    put(store, release_id, "manifest", b"historical")
    replacement = b"other cached object"
    put(store, release_id, "other", replacement)
    pin(store, strategy_run_manifest, "manifest")
    with sqlite3.connect(store.database_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "UPDATE pin_artifacts SET sha256 = ?, size_bytes = ? WHERE run_id = ?",
            (digest(replacement), len(replacement), strategy_run_manifest.run_id),
        )
    request = AuditReplayRequest(
        strategy_run_manifest.run_id,
        digest(canonical_json_bytes(strategy_run_manifest)),
    )
    with pytest.raises(CacheIntegrityError, match="mapping changed"):
        store.read_artifact(
            artifact_id="manifest",
            purpose=RunPurpose.AUDIT_REPLAY,
            source_manifest=strategy_run_manifest,
            audit_request=request,
        )


def test_quota_reports_orphan_missing_corrupt_and_pinned_objects(
    store: ReleaseCacheStore,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    release_id = authorize_for_manifest(store, strategy_run_manifest)
    corrupt_path = put(store, release_id, "corrupt", b"abc")
    missing_path = put(store, release_id, "missing", b"defg")
    pin(store, strategy_run_manifest, "corrupt", "missing")
    corrupt_path.write_bytes(b"bad!")
    missing_path.unlink()
    orphan = store.cache_root / "orphan.bin"
    orphan.write_bytes(b"orphan")

    report = store.quota_report()
    assert report.registered_bytes == 7
    assert report.pinned_bytes == 7
    assert report.physical_bytes == 10
    assert report.orphan_bytes == 6
    assert report.integrity_checked
    assert len(report.issues_of_kind(CacheIssueKind.MISSING)) == 1
    assert len(report.issues_of_kind(CacheIssueKind.CORRUPT)) == 1
    assert report.issues_of_kind(CacheIssueKind.MISSING)[0].pinned
    assert report.issues_of_kind(CacheIssueKind.CORRUPT)[0].pinned
    assert report.has_anomalies
    assert report.scan_complete

    capacity_only = store.quota_report(verify_integrity=False)
    assert not capacity_only.integrity_checked
    assert not capacity_only.issues_of_kind(CacheIssueKind.CORRUPT)
    assert capacity_only.issues_of_kind(CacheIssueKind.MISSING)


def test_cache_symlink_or_junction_is_rejected_fail_closed(
    tmp_path: Path,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    store = ReleaseCacheStore(
        database_path=tmp_path / "state.sqlite3",
        cache_root=tmp_path / "cache",
        clock=FixedClock(FIXED_TIME),
    )
    release_id = strategy_run_manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id=strategy_run_manifest.release_status_observation_id,
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    content = b"must stay inside cache"
    digest_value = digest(content)
    outside = tmp_path / "outside"
    outside.mkdir()
    prefix = store.cache_root / "sha256" / digest_value[:2]
    prefix.parent.mkdir()
    try:
        prefix.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"platform cannot create test symlink: {exc}")

    with pytest.raises(CacheIntegrityError, match="symlink or junction"):
        store.put_artifact(
            release_id=release_id,
            artifact_id="manifest",
            content=content,
            expected_sha256=digest_value,
        )
    assert list(outside.iterdir()) == []
    report = store.quota_report()
    assert report.issues_of_kind(CacheIssueKind.SCAN_FAILURE)
    assert not report.scan_complete


def test_cache_hardlink_is_not_adopted_as_independently_owned(
    tmp_path: Path,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    store = ReleaseCacheStore(
        database_path=tmp_path / "state.sqlite3",
        cache_root=tmp_path / "cache",
        clock=FixedClock(FIXED_TIME),
    )
    release_id = strategy_run_manifest.strategy_input_ref.dataset_release_id
    store.record_release_status(
        release_id,
        status=ReleaseStatus.PUBLISHED,
        status_observation_id=strategy_run_manifest.release_status_observation_id,
        strategy_input_ref=strategy_run_manifest.strategy_input_ref,
    )
    content = b"externally shared inode"
    digest_value = digest(content)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(content)
    target = store.cache_root / "sha256" / digest_value[:2] / digest_value
    target.parent.mkdir(parents=True)
    try:
        os.link(outside, target)
    except OSError as exc:
        pytest.skip(f"filesystem cannot create test hardlink: {exc}")

    with pytest.raises(CacheIntegrityError, match="multiple hard links"):
        store.put_artifact(
            release_id=release_id,
            artifact_id="manifest",
            content=content,
            expected_sha256=digest_value,
        )
    assert table_count(store.database_path, "cache_objects") == 0
    report = store.quota_report()
    hardlink_issues = report.issues_of_kind(CacheIssueKind.METADATA)
    assert any("hard links" in issue.detail for issue in hardlink_issues)


@pytest.mark.parametrize("replacement", ["root", "ancestor"])
def test_quota_rejects_cache_path_replaced_by_directory_symlink(
    tmp_path: Path,
    replacement: str,
) -> None:
    cache_parent = tmp_path / "owned-cache-parent"
    cache_root = cache_parent / "cache"
    store = ReleaseCacheStore(
        database_path=tmp_path / "state.sqlite3",
        cache_root=cache_root,
        clock=FixedClock(FIXED_TIME),
    )
    outside_parent = tmp_path / "outside-parent"
    outside_cache = outside_parent / "cache"
    outside_cache.mkdir(parents=True)
    (outside_cache / "must-not-be-scanned.bin").write_bytes(b"external")

    if replacement == "root":
        cache_root.rmdir()
        link_path = cache_root
        link_target = outside_cache
    else:
        original_parent = tmp_path / "original-cache-parent"
        cache_parent.rename(original_parent)
        link_path = cache_parent
        link_target = outside_parent
    try:
        link_path.symlink_to(link_target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"platform cannot create test directory symlink: {exc}")

    with pytest.raises(CacheIntegrityError, match="symlink or junction|escapes cache_root"):
        store.quota_report()


def test_quota_checks_cache_root_before_starting_walk(
    store: ReleaseCacheStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked_paths: list[Path] = []

    def reject_replaced_root(cache_store: ReleaseCacheStore, path: Path) -> None:
        checked_paths.append(path)
        raise CacheIntegrityError("cache_root became a symlink or junction")

    def forbidden_walk(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("os.walk must not start before root validation")

    monkeypatch.setattr(ReleaseCacheStore, "_assert_safe_cache_path", reject_replaced_root)
    monkeypatch.setattr(os, "walk", forbidden_walk)

    with pytest.raises(CacheIntegrityError, match="cache_root became"):
        store.quota_report()
    assert checked_paths == [store.cache_root]
