from __future__ import annotations

import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from threading import Barrier

import pytest

from invest_system import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ArtifactPayload,
    ArtifactReceiptItem,
    AuditReplayRequest,
    CacheIntegrityError,
    CacheIssueKind,
    DeliveryTransport,
    FixedClock,
    HashDigest,
    ImmutableMappingError,
    ProviderReleaseStatus,
    ReleaseAccessError,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    ReleaseCacheStore,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
    ReleaseRetentionNode,
    ReleaseStatusObservation,
    RetentionArtifact,
    RuleStatus,
    RunMode,
    RunPurpose,
    SchemaValidationResult,
    StorageSchemaError,
    StrategyInputRef,
    StrategyRunManifest,
    canonical_json_bytes,
)

BASE = datetime(2026, 7, 31, 8, tzinfo=UTC)


def digest(content: bytes) -> str:
    return sha256(content).hexdigest()


def hash_value(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def ref(release_id: str, character: str, *, cutoff_hours: int) -> StrategyInputRef:
    return StrategyInputRef(
        schema_version="0.1.0",
        dataset_release_id=release_id,
        knowledge_cutoff=BASE + timedelta(hours=cutoff_hours),
        release_manifest_schema_version="1.0.0",
        # Provider semantic Manifest identity deliberately differs from the
        # physical Manifest document digest used by storage.
        manifest_hash=hash_value(character * 64),
    )


def retention_artifact(artifact_id: str, content: bytes) -> RetentionArtifact:
    return RetentionArtifact(
        artifact_id=artifact_id,
        item_type="context_pack_jsonl",
        artifact_hash=hash_value(digest(content)),
        size_bytes=len(content),
        record_count=1,
    )


def receipt_artifact(artifact_id: str, content: bytes) -> ArtifactReceiptItem:
    return ArtifactReceiptItem(
        artifact_id=artifact_id,
        item_type="context_pack_jsonl",
        artifact_hash=hash_value(digest(content)),
        size_bytes=len(content),
        record_count=1,
    )


class Scenario:
    def __init__(self, store: ReleaseCacheStore) -> None:
        self.store = store
        self.root_ref = ref("root-release", "a", cutoff_hours=0)
        self.source_ref = ref("source-release", "b", cutoff_hours=-1)
        self.root_bytes = b'{"root":true}\n'
        self.source_bytes = b'{"source":true}\n'
        self.root_manifest_bytes = b'{"provider_float":1.25}'
        self.source_manifest_bytes = b"opaque-provider-manifest-bytes"
        root_descriptor = retention_artifact("shared-artifact", self.root_bytes)
        source_descriptor = retention_artifact("shared-artifact", self.source_bytes)
        self.receipt = ArtifactConsumptionReceipt.create(
            consumer_contract_version="0.1.0",
            strategy_input_ref=self.root_ref,
            artifacts=(receipt_artifact("shared-artifact", self.root_bytes),),
        )
        self.closure = ReleaseRetentionClosure.create(
            root_strategy_input_ref=self.root_ref,
            releases=(
                ReleaseRetentionNode(
                    strategy_input_ref=self.root_ref,
                    manifest_document_hash=hash_value(digest(self.root_manifest_bytes)),
                    manifest_size_bytes=len(self.root_manifest_bytes),
                    artifacts=(root_descriptor,),
                    dependency_release_ids=(self.source_ref.dataset_release_id,),
                ),
                ReleaseRetentionNode(
                    strategy_input_ref=self.source_ref,
                    manifest_document_hash=hash_value(digest(self.source_manifest_bytes)),
                    manifest_size_bytes=len(self.source_manifest_bytes),
                    artifacts=(source_descriptor,),
                ),
            ),
        )

    def persist(self) -> bool:
        return self.store.record_verified_consumption(
            self.receipt,
            self.closure,
            (
                ArtifactPayload("root-release", "shared-artifact", self.root_bytes),
                ArtifactPayload("source-release", "shared-artifact", self.source_bytes),
            ),
            (
                ReleaseManifestPayload("root-release", self.root_manifest_bytes),
                ReleaseManifestPayload("source-release", self.source_manifest_bytes),
            ),
        )

    def status(
        self,
        input_ref: StrategyInputRef,
        observation_id: str,
        *,
        sequence: int,
        status: ProviderReleaseStatus = ProviderReleaseStatus.PUBLISHED,
        supersedes: str | None = None,
        result: SchemaValidationResult = SchemaValidationResult.PASSED,
        observed_hours: int = 2,
        event_id: str | None = None,
        event_hash_character: str = "e",
        previous_event_hash_character: str | None = None,
        recorded_hours: int | None = None,
    ) -> ReleaseStatusObservation:
        passed = result is SchemaValidationResult.PASSED
        return ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id=observation_id,
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=BASE + timedelta(hours=observed_hours),
            schema_validation_result=result,
            status=status if passed else None,
            status_event_id=(event_id or f"event-{observation_id}") if passed else None,
            status_event_hash=hash_value(event_hash_character * 64) if passed else None,
            previous_status_event_hash=(
                hash_value(previous_event_hash_character * 64)
                if passed and previous_event_hash_character is not None
                else None
            ),
            status_sequence=sequence if passed else None,
            status_recorded_at=(
                BASE
                + timedelta(hours=observed_hours - 1 if recorded_hours is None else recorded_hours)
                if passed
                else None
            ),
            failure_reasons=() if passed else ("provider_unconfirmable",),
            supersedes=supersedes,
        )

    def ready(self) -> StrategyRunManifest:
        self.persist()
        fetch = ArtifactFetchObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="root-fetch-1",
            release_id="root-release",
            strategy_input_ref=self.root_ref,
            observed_at=BASE + timedelta(hours=1),
            transport=DeliveryTransport.IMMUTABLE_EXPORT,
            source_endpoint="export:test",
            schema_validation_result=SchemaValidationResult.PASSED,
            receipt_hash=self.receipt.receipt_hash,
            artifact_ids=("shared-artifact",),
            local_cache_keys=("sha256/root",),
        )
        self.store.append_observation(fetch)
        for input_ref, prefix, final_hash in (
            (self.root_ref, "root", "c"),
            (self.source_ref, "source", "d"),
        ):
            building_id = f"{prefix}-status-building"
            validated_id = f"{prefix}-status-validated"
            final_id = f"{prefix}-status-1"
            self.store.append_observation(
                self.status(
                    input_ref,
                    building_id,
                    sequence=1,
                    status=ProviderReleaseStatus.BUILDING,
                    observed_hours=1,
                    event_hash_character="a" if prefix == "root" else "1",
                )
            )
            self.store.append_observation(
                self.status(
                    input_ref,
                    validated_id,
                    sequence=2,
                    status=ProviderReleaseStatus.VALIDATED,
                    supersedes=building_id,
                    observed_hours=2,
                    event_hash_character="b" if prefix == "root" else "2",
                    previous_event_hash_character="a" if prefix == "root" else "1",
                )
            )
            self.store.append_observation(
                self.status(
                    input_ref,
                    final_id,
                    sequence=3,
                    supersedes=validated_id,
                    observed_hours=3,
                    event_hash_character=final_hash,
                    previous_event_hash_character="b" if prefix == "root" else "2",
                )
            )
        admission = ReleaseAdmissionObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="root-admission-1",
            release_id="root-release",
            strategy_input_ref=self.root_ref,
            observed_at=BASE + timedelta(hours=4),
            status_observation_id="root-status-1",
            admission_status=ReleaseAdmissionStatus.AUTHORIZED,
        )
        self.store.append_observation(admission)
        return StrategyRunManifest(
            strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
            run_id="run-1",
            created_at=BASE + timedelta(hours=8),
            strategy_id="industrial-event",
            strategy_version="0.1.0-draft",
            code_commit="0123456789abcdef0123456789abcdef01234567",
            rule_bundle_version="0.1.0-draft",
            rule_status=RuleStatus.DRAFT,
            config_hash=hash_value("1" * 64),
            strategy_input_ref=self.root_ref,
            artifact_consumption_receipt_hash=self.receipt.receipt_hash,
            artifact_fetch_observation_id="root-fetch-1",
            release_status_observation_id="root-status-1",
            release_admission_observation_id="root-admission-1",
            random_seed=0,
            run_mode=RunMode.RESEARCH,
            runtime_environment_lock_hash=hash_value("2" * 64),
        )


@pytest.fixture
def store(tmp_path: Path) -> ReleaseCacheStore:
    return ReleaseCacheStore(
        database_path=tmp_path / "state" / "invest_system.sqlite3",
        cache_root=tmp_path / "cache",
        soft_limit_bytes=1,
        clock=FixedClock(BASE + timedelta(hours=8)),
    )


def count(database: Path, table: str) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def test_formal_path_pins_full_closure_and_separates_normal_from_audit(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()

    assert store.pin_run(manifest) is True
    assert store.pin_run(manifest) is False
    assert count(store.database_path, "pin_releases") == 2
    assert count(store.database_path, "pin_artifacts") == 2

    root = store.read_artifact(
        artifact_id="shared-artifact",
        purpose=RunPurpose.NEW_RUN,
        source_manifest=manifest,
    )
    assert root.content == scenario.root_bytes
    with pytest.raises(ReleaseAccessError, match="ordinary strategy"):
        store.read_artifact(
            release_id="source-release",
            artifact_id="shared-artifact",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=manifest,
        )
    audit = store.read_artifact(
        release_id="source-release",
        artifact_id="shared-artifact",
        purpose=RunPurpose.AUDIT_REPLAY,
        source_manifest=manifest,
        audit_request=AuditReplayRequest(
            source_run_id=manifest.run_id,
            source_manifest_hash=digest(manifest.to_canonical_bytes()),
        ),
    )
    assert audit.content == scenario.source_bytes


def test_record_verified_consumption_is_exact_idempotent_and_opaque_manifest_safe(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    assert scenario.persist() is True
    assert scenario.persist() is False
    with sqlite3.connect(store.database_path) as connection:
        physical_hash = connection.execute(
            "SELECT sha256 FROM release_manifests WHERE release_id='root-release'"
        ).fetchone()[0]
    assert physical_hash == digest(scenario.root_manifest_bytes)
    assert physical_hash != scenario.root_ref.manifest_hash.value

    with pytest.raises(CacheIntegrityError, match="committed hash/size"):
        store.record_verified_consumption(
            scenario.receipt,
            scenario.closure,
            (
                ArtifactPayload("root-release", "shared-artifact", scenario.root_bytes),
                ArtifactPayload("source-release", "shared-artifact", scenario.source_bytes),
            ),
            (
                ReleaseManifestPayload("root-release", b"different-physical-manifest"),
                ReleaseManifestPayload("source-release", scenario.source_manifest_bytes),
            ),
        )

    with pytest.raises(ValueError, match="exactly cover"):
        store.record_verified_consumption(
            scenario.receipt,
            scenario.closure,
            (ArtifactPayload("root-release", "shared-artifact", scenario.root_bytes),),
            (
                ReleaseManifestPayload("root-release", scenario.root_manifest_bytes),
                ReleaseManifestPayload("source-release", scenario.source_manifest_bytes),
            ),
        )


def test_pin_is_atomic_until_every_source_is_current_published(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    failed_source = scenario.status(
        scenario.source_ref,
        "source-status-failed",
        sequence=0,
        supersedes="source-status-1",
        result=SchemaValidationResult.FAILED,
        observed_hours=3,
    )
    store.append_observation(failed_source)

    with pytest.raises(ReleaseAccessError, match="not currently confirmed"):
        store.pin_run(manifest)
    assert count(store.database_path, "strategy_run_pins") == 0
    assert count(store.database_path, "pin_artifacts") == 0


def test_withdrawal_blocks_normal_access_but_preserves_audit(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    store.pin_run(manifest)
    withdrawn = scenario.status(
        scenario.root_ref,
        "root-status-withdrawn",
        sequence=4,
        status=ProviderReleaseStatus.WITHDRAWN,
        supersedes="root-status-1",
        observed_hours=5,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    store.append_observation(withdrawn)

    with pytest.raises(ReleaseAccessError, match="lost current"):
        store.read_artifact(
            artifact_id="shared-artifact",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=manifest,
        )
    audit = store.read_artifact(
        artifact_id="shared-artifact",
        purpose=RunPurpose.AUDIT_REPLAY,
        source_manifest=manifest,
        audit_request=AuditReplayRequest(manifest.run_id, digest(manifest.to_canonical_bytes())),
    )
    assert audit.content == scenario.root_bytes

    stale = scenario.status(
        scenario.root_ref,
        "root-status-stale",
        sequence=5,
        supersedes="root-status-withdrawn",
        observed_hours=6,
        event_hash_character="9",
        previous_event_hash_character="f",
    )
    with pytest.raises(ReleaseAccessError, match="terminal"):
        store.append_observation(stale)


def test_source_withdrawal_is_visible_in_source_audit_context(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    store.pin_run(manifest)
    withdrawn = scenario.status(
        scenario.source_ref,
        "source-status-withdrawn",
        sequence=4,
        status=ProviderReleaseStatus.WITHDRAWN,
        supersedes="source-status-1",
        observed_hours=5,
        event_hash_character="e",
        previous_event_hash_character="d",
    )
    store.append_observation(withdrawn)
    audit = store.read_artifact(
        release_id="source-release",
        artifact_id="shared-artifact",
        purpose=RunPurpose.AUDIT_REPLAY,
        source_manifest=manifest,
        audit_request=AuditReplayRequest(manifest.run_id, digest(manifest.to_canonical_bytes())),
    )
    assert audit.artifact.release_id == "source-release"
    assert audit.pinned_release_status_observation_id == "source-status-1"
    assert audit.current_release_access.provider_status is ProviderReleaseStatus.WITHDRAWN
    assert not audit.current_release_access.authorized


def test_status_replay_and_stale_sequence_leave_head_unchanged(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    scenario.ready()
    replay = scenario.status(
        scenario.root_ref,
        "root-status-replay",
        sequence=4,
        supersedes="root-status-1",
        observed_hours=4,
        event_id="event-root-status-1",
        event_hash_character="8",
        previous_event_hash_character="c",
    )
    with pytest.raises(ReleaseAccessError, match="remapped"):
        store.append_observation(replay)
    stale = scenario.status(
        scenario.root_ref,
        "root-status-stale",
        sequence=3,
        supersedes="root-status-1",
        observed_hours=4,
        event_hash_character="7",
        previous_event_hash_character="b",
    )
    with pytest.raises(ReleaseAccessError, match="repeat only"):
        store.append_observation(stale)
    with sqlite3.connect(store.database_path) as connection:
        head = connection.execute(
            "SELECT current_status_observation_id FROM release_heads WHERE release_id='root-release'"
        ).fetchone()[0]
    assert head == "root-status-1"


def test_exact_latest_status_reobservation_recovers_after_unconfirmable(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    failed = scenario.status(
        scenario.root_ref,
        "root-status-unconfirmable",
        sequence=0,
        supersedes="root-status-1",
        result=SchemaValidationResult.FAILED,
        observed_hours=5,
    )
    store.append_observation(failed)
    reconfirmed = scenario.status(
        scenario.root_ref,
        "root-status-reconfirmed",
        sequence=3,
        supersedes=failed.observation_id,
        observed_hours=6,
        recorded_hours=2,
        event_id="event-root-status-1",
        event_hash_character="c",
        previous_event_hash_character="b",
    )
    assert store.append_observation(reconfirmed)
    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="root-admission-2",
        release_id="root-release",
        strategy_input_ref=scenario.root_ref,
        observed_at=BASE + timedelta(hours=7),
        status_observation_id=reconfirmed.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
        supersedes="root-admission-1",
    )
    assert store.append_observation(admission)
    recovered_manifest = replace(
        manifest,
        run_id="run-reconfirmed",
        release_status_observation_id=reconfirmed.observation_id,
        release_admission_observation_id=admission.observation_id,
    )
    assert store.pin_run(recovered_manifest)
    read = store.read_artifact(
        artifact_id="shared-artifact",
        purpose=RunPurpose.NEW_RUN,
        source_manifest=recovered_manifest,
    )
    assert read.current_release_access.authorized


def test_provider_status_chain_rejects_gaps_and_wrong_previous_hash(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    scenario.persist()
    checkpoint_without_chain = scenario.status(
        scenario.root_ref,
        "chain-unverified-checkpoint",
        sequence=3,
        observed_hours=1,
        event_hash_character="c",
        previous_event_hash_character="b",
    )
    with pytest.raises(ReleaseAccessError, match="must have sequence 1"):
        store.append_observation(checkpoint_without_chain)
    building = scenario.status(
        scenario.root_ref,
        "chain-building",
        sequence=1,
        status=ProviderReleaseStatus.BUILDING,
        observed_hours=1,
        event_hash_character="a",
    )
    store.append_observation(building)
    gap = scenario.status(
        scenario.root_ref,
        "chain-gap",
        sequence=3,
        supersedes=building.observation_id,
        observed_hours=3,
        event_hash_character="c",
        previous_event_hash_character="a",
    )
    with pytest.raises(ReleaseAccessError, match="contiguous"):
        store.append_observation(gap)
    wrong_link = scenario.status(
        scenario.root_ref,
        "chain-wrong-link",
        sequence=2,
        status=ProviderReleaseStatus.VALIDATED,
        supersedes=building.observation_id,
        observed_hours=2,
        event_hash_character="b",
        previous_event_hash_character="f",
    )
    with pytest.raises(ReleaseAccessError, match="breaks the chain"):
        store.append_observation(wrong_link)


def test_observation_and_manifest_persistence_times_enforce_real_causality(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    with pytest.raises(ReleaseAccessError, match="predate persisted"):
        store.pin_run(
            replace(manifest, run_id="run-backdated", created_at=BASE + timedelta(hours=7))
        )
    with pytest.raises(ReleaseAccessError, match="in the future"):
        store.pin_run(replace(manifest, run_id="run-future", created_at=BASE + timedelta(hours=9)))
    future_observation = scenario.status(
        scenario.root_ref,
        "future-observation",
        sequence=4,
        status=ProviderReleaseStatus.WITHDRAWN,
        supersedes="root-status-1",
        observed_hours=9,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    with pytest.raises(ReleaseAccessError, match="later than its persistence"):
        store.append_observation(future_observation)


def test_observation_idempotency_collision_and_linear_supersedes(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    scenario.persist()
    status = scenario.status(
        scenario.root_ref,
        "status-1",
        sequence=1,
        status=ProviderReleaseStatus.BUILDING,
    )
    assert store.append_observation(status) is True
    assert store.append_observation(status) is False
    collision = replace(status, observed_at=status.observed_at + timedelta(minutes=1))
    with pytest.raises(ImmutableMappingError, match="remapped"):
        store.append_observation(collision)
    fork = scenario.status(
        scenario.root_ref,
        "status-fork",
        sequence=2,
        status=ProviderReleaseStatus.VALIDATED,
        supersedes=None,
        observed_hours=3,
        event_hash_character="6",
        previous_event_hash_character="e",
    )
    with pytest.raises(ImmutableMappingError, match="exact current head"):
        store.append_observation(fork)


def test_admission_cannot_predate_status(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    scenario.persist()
    building = scenario.status(
        scenario.root_ref,
        "status-building",
        sequence=1,
        status=ProviderReleaseStatus.BUILDING,
        observed_hours=2,
        event_hash_character="a",
    )
    validated = scenario.status(
        scenario.root_ref,
        "status-validated",
        sequence=2,
        status=ProviderReleaseStatus.VALIDATED,
        supersedes=building.observation_id,
        observed_hours=3,
        event_hash_character="b",
        previous_event_hash_character="a",
    )
    status = scenario.status(
        scenario.root_ref,
        "status-late",
        sequence=3,
        supersedes=validated.observation_id,
        observed_hours=4,
        event_hash_character="c",
        previous_event_hash_character="b",
    )
    store.append_observation(building)
    store.append_observation(validated)
    store.append_observation(status)
    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="admission-early",
        release_id="root-release",
        strategy_input_ref=scenario.root_ref,
        observed_at=BASE + timedelta(hours=3),
        status_observation_id="status-late",
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
    )
    with pytest.raises(ReleaseAccessError, match="cannot predate"):
        store.append_observation(admission)


def test_manifest_cannot_predate_required_observation(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    too_early = replace(manifest, created_at=BASE + timedelta(hours=2, minutes=30))
    with pytest.raises(ReleaseAccessError, match="cannot predate"):
        store.pin_run(too_early)
    assert count(store.database_path, "strategy_run_pins") == 0


def test_append_only_triggers_cover_observations_and_head_delete(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    scenario.ready()
    with sqlite3.connect(store.database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE observations SET observed_at='2000-01-01T00:00:00.000000Z'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM release_heads WHERE release_id='root-release'")


def test_database_guards_reject_replace_and_head_rollback_bypasses(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    scenario.ready()
    withdrawn = scenario.status(
        scenario.root_ref,
        "root-status-withdrawn-guard",
        sequence=4,
        status=ProviderReleaseStatus.WITHDRAWN,
        supersedes="root-status-1",
        observed_hours=5,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    store.append_observation(withdrawn)
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("PRAGMA recursive_triggers").fetchone()[0] == 0
        with pytest.raises(
            sqlite3.DatabaseError,
            match="investsystem_head_write_allowed|transition is invalid",
        ):
            connection.execute(
                """UPDATE release_heads
                   SET current_status_observation_id='root-status-1'
                   WHERE release_id='root-release'"""
            )
        with pytest.raises(
            sqlite3.DatabaseError,
            match="investsystem_head_write_allowed|transition is invalid",
        ):
            connection.execute(
                """UPDATE OR REPLACE release_heads
                   SET current_status_observation_id='source-status-1'
                   WHERE release_id='root-release'"""
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable identity conflict"):
            connection.execute(
                """INSERT OR REPLACE INTO release_identities
                   VALUES ('root-release', '0.1.0',
                           '2000-01-01T00:00:00.000000Z', '1.0.0', ?, 'now')""",
                ("9" * 64,),
            )
        assert connection.execute("SELECT COUNT(*) FROM release_heads").fetchone()[0] == 2


def test_forged_status_after_withdrawal_cannot_restore_release_access(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    withdrawn = scenario.status(
        scenario.root_ref,
        "root-status-withdrawn-forgery",
        sequence=4,
        status=ProviderReleaseStatus.WITHDRAWN,
        supersedes="root-status-1",
        observed_hours=5,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    store.append_observation(withdrawn)
    forged = scenario.status(
        scenario.root_ref,
        "root-status-forged-after-withdrawal",
        sequence=5,
        status=ProviderReleaseStatus.PUBLISHED,
        supersedes=withdrawn.observation_id,
        observed_hours=6,
        event_hash_character="0",
        previous_event_hash_character="f",
    )
    canonical = forged.to_canonical_bytes()
    document = forged.to_json_value()

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.observation_type.value,
                forged.release_id,
                document["observed_at"],
                forged.supersedes,
                canonical,
                digest(canonical),
                document["observed_at"],
            ),
        )
        connection.execute(
            "INSERT INTO release_status_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.schema_validation_result.value,
                forged.status.value if forged.status is not None else None,
                forged.status_event_id,
                forged.status_event_hash.value if forged.status_event_hash is not None else None,
                (
                    forged.previous_status_event_hash.value
                    if forged.previous_status_event_hash is not None
                    else None
                ),
                forged.status_sequence,
                document["status_recorded_at"],
            ),
        )
        with pytest.raises(
            sqlite3.DatabaseError,
            match="investsystem_head_write_allowed|transition is invalid",
        ):
            connection.execute(
                """UPDATE release_heads
                   SET current_status_observation_id=?
                   WHERE release_id=?""",
                (forged.observation_id, forged.release_id),
            )

        # The connection-local gate is only an accidental-write guard, not the
        # trust boundary. Even if a writer deliberately impersonates the store,
        # full-chain validation must still detect the terminal withdrawal.
        connection.create_function("investsystem_head_write_allowed", 0, lambda: 1)
        connection.execute(
            """UPDATE release_heads
               SET current_status_observation_id=?
               WHERE release_id=?""",
            (forged.observation_id, forged.release_id),
        )

    with pytest.raises(CacheIntegrityError, match="withdrawn provider status is terminal"):
        store.pin_run(manifest)
    with pytest.raises(CacheIntegrityError, match="withdrawn provider status is terminal"):
        store.append_observation(forged)


def test_canonical_observation_remains_authoritative_over_sqlite_projection(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    forged = scenario.status(
        scenario.root_ref,
        "root-status-projection-forgery",
        sequence=4,
        status=ProviderReleaseStatus.PUBLISHED,
        supersedes="root-status-1",
        observed_hours=5,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    canonical = forged.to_canonical_bytes()
    document = forged.to_json_value()

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.observation_type.value,
                forged.release_id,
                document["observed_at"],
                forged.supersedes,
                canonical,
                digest(canonical),
                document["observed_at"],
            ),
        )
        connection.execute(
            "INSERT INTO release_status_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.schema_validation_result.value,
                ProviderReleaseStatus.WITHDRAWN.value,
                forged.status_event_id,
                forged.status_event_hash.value if forged.status_event_hash is not None else None,
                (
                    forged.previous_status_event_hash.value
                    if forged.previous_status_event_hash is not None
                    else None
                ),
                forged.status_sequence,
                document["status_recorded_at"],
            ),
        )
        connection.create_function("investsystem_head_write_allowed", 0, lambda: 1)
        connection.execute(
            """UPDATE release_heads
               SET current_status_observation_id=?
               WHERE release_id=?""",
            (forged.observation_id, forged.release_id),
        )

    with pytest.raises(
        CacheIntegrityError,
        match="observation subtype differs from canonical parent",
    ):
        store.pin_run(manifest)
    with pytest.raises(
        CacheIntegrityError,
        match="observation subtype differs from canonical parent",
    ):
        store.append_observation(forged)


def test_non_contract_canonical_status_cannot_be_authorized_or_pinned(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    forged = scenario.status(
        scenario.root_ref,
        "root-status-invalid-canonical",
        sequence=4,
        status=ProviderReleaseStatus.PUBLISHED,
        supersedes="root-status-1",
        observed_hours=5,
        event_hash_character="f",
        previous_event_hash_character="c",
    )
    document = forged.to_json_value()
    document["unexpected_contract_field"] = "must-be-rejected"
    canonical = canonical_json_bytes(document)

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.observation_type.value,
                forged.release_id,
                document["observed_at"],
                forged.supersedes,
                canonical,
                digest(canonical),
                document["observed_at"],
            ),
        )
        connection.execute(
            "INSERT INTO release_status_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                forged.observation_id,
                forged.schema_validation_result.value,
                forged.status.value if forged.status is not None else None,
                forged.status_event_id,
                forged.status_event_hash.value if forged.status_event_hash is not None else None,
                (
                    forged.previous_status_event_hash.value
                    if forged.previous_status_event_hash is not None
                    else None
                ),
                forged.status_sequence,
                document["status_recorded_at"],
            ),
        )
        connection.create_function("investsystem_head_write_allowed", 0, lambda: 1)
        connection.execute(
            """UPDATE release_heads
               SET current_status_observation_id=?
               WHERE release_id=?""",
            (forged.observation_id, forged.release_id),
        )

    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="root-admission-invalid-canonical",
        release_id=scenario.root_ref.dataset_release_id,
        strategy_input_ref=scenario.root_ref,
        observed_at=BASE + timedelta(hours=6),
        status_observation_id=forged.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
        supersedes="root-admission-1",
    )
    with pytest.raises(CacheIntegrityError, match="canonical parent is inconsistent"):
        store.append_observation(admission)
    with pytest.raises(CacheIntegrityError, match="canonical parent is inconsistent"):
        store.pin_run(manifest)


def test_canonical_receipt_rejects_appended_child_rows(store: ReleaseCacheStore) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """INSERT INTO receipt_artifacts
               VALUES (?, 'injected/artifact', 'context_pack_jsonl', ?, ?, 1)""",
            (
                scenario.receipt.receipt_hash.value,
                digest(scenario.root_bytes),
                len(scenario.root_bytes),
            ),
        )
    with pytest.raises(CacheIntegrityError, match="Receipt artifact index"):
        store.pin_run(manifest)


def test_canonical_closure_rejects_self_consistent_appended_pin_rows(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    store.pin_run(manifest)
    root_digest = digest(scenario.root_bytes)
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """INSERT INTO release_artifacts
               VALUES ('root-release', 'injected/artifact', 'context_pack_jsonl', ?, ?, 1, 'now')""",
            (root_digest, len(scenario.root_bytes)),
        )
        connection.execute(
            """INSERT INTO closure_artifacts
               VALUES (?, 'root-release', 'injected/artifact',
                       'context_pack_jsonl', ?, ?, 1)""",
            (scenario.closure.closure_hash.value, root_digest, len(scenario.root_bytes)),
        )
        connection.execute(
            """INSERT INTO pin_artifacts
               VALUES ('run-1', 'root-release', 'injected/artifact', ?, ?)""",
            (root_digest, len(scenario.root_bytes)),
        )
    with pytest.raises(CacheIntegrityError, match="closure artifact index"):
        store.read_artifact(
            artifact_id="injected/artifact",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=manifest,
        )


def test_reused_closure_is_verified_before_linking_a_new_receipt(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    scenario.persist()
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """INSERT INTO closure_artifacts
               VALUES (?, 'root-release', 'injected/artifact',
                       'context_pack_jsonl', ?, ?, 1)""",
            (
                scenario.closure.closure_hash.value,
                digest(scenario.root_bytes),
                len(scenario.root_bytes),
            ),
        )
    new_receipt = ArtifactConsumptionReceipt.create(
        consumer_contract_version="0.1.1",
        strategy_input_ref=scenario.root_ref,
        artifacts=scenario.receipt.artifacts,
    )
    with pytest.raises(CacheIntegrityError, match="closure artifact index"):
        store.record_verified_consumption(
            new_receipt,
            scenario.closure,
            (
                ArtifactPayload("root-release", "shared-artifact", scenario.root_bytes),
                ArtifactPayload("source-release", "shared-artifact", scenario.source_bytes),
            ),
            (
                ReleaseManifestPayload("root-release", scenario.root_manifest_bytes),
                ReleaseManifestPayload("source-release", scenario.source_manifest_bytes),
            ),
        )
    assert count(store.database_path, "receipts") == 1


def test_quota_reports_pinned_manifests_artifacts_orphans_and_corruption(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    store.pin_run(manifest)
    orphan = store.cache_root / "orphan.bin"
    orphan.write_bytes(b"orphan")
    report = store.quota_report()
    assert report.over_limit
    assert report.pinned_bytes > len(scenario.root_bytes) + len(scenario.source_bytes)
    assert report.orphan_bytes == len(b"orphan")

    root_digest = digest(scenario.root_bytes)
    path = store.cache_root / "sha256" / root_digest[:2] / root_digest
    path.write_bytes(b"corrupt")
    corrupt = store.quota_report()
    assert corrupt.issues_of_kind(CacheIssueKind.CORRUPT)
    assert any(issue.pinned for issue in corrupt.issues_of_kind(CacheIssueKind.CORRUPT))


def test_cache_symlink_or_junction_is_rejected_fail_closed(
    store: ReleaseCacheStore,
    tmp_path: Path,
) -> None:
    scenario = Scenario(store)
    root_digest = digest(scenario.root_bytes)
    outside = tmp_path / "outside"
    outside.mkdir()
    prefix = store.cache_root / "sha256" / root_digest[:2]
    prefix.parent.mkdir()
    try:
        prefix.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"platform cannot create test symlink: {exc}")
    with pytest.raises(CacheIntegrityError, match="symlink or junction"):
        scenario.persist()
    assert list(outside.iterdir()) == []
    report = store.quota_report()
    assert report.issues_of_kind(CacheIssueKind.SCAN_FAILURE)
    assert not report.scan_complete


def test_cache_hardlink_is_not_adopted_as_independently_owned(
    store: ReleaseCacheStore,
    tmp_path: Path,
) -> None:
    scenario = Scenario(store)
    root_digest = digest(scenario.root_bytes)
    outside = tmp_path / "outside.bin"
    outside.write_bytes(scenario.root_bytes)
    target = store.cache_root / "sha256" / root_digest[:2] / root_digest
    target.parent.mkdir(parents=True)
    try:
        os.link(outside, target)
    except OSError as exc:
        pytest.skip(f"filesystem cannot create test hardlink: {exc}")
    with pytest.raises(CacheIntegrityError, match="multiple hard links"):
        scenario.persist()
    assert count(store.database_path, "cache_objects") == 0
    report = store.quota_report()
    assert any(
        "hard links" in issue.detail for issue in report.issues_of_kind(CacheIssueKind.METADATA)
    )


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
        clock=FixedClock(BASE),
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


def test_every_read_revalidates_source_artifacts_and_manifests(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    store.pin_run(manifest)

    source_manifest_digest = digest(scenario.source_manifest_bytes)
    source_manifest_path = (
        store.cache_root / "sha256" / source_manifest_digest[:2] / source_manifest_digest
    )
    source_manifest_path.write_bytes(b"corrupt-manifest")
    with pytest.raises(CacheIntegrityError, match="failed size/hash"):
        store.read_artifact(
            artifact_id="shared-artifact",
            purpose=RunPurpose.NEW_RUN,
            source_manifest=manifest,
        )
    source_manifest_path.write_bytes(scenario.source_manifest_bytes)

    source_digest = digest(scenario.source_bytes)
    source_path = store.cache_root / "sha256" / source_digest[:2] / source_digest
    source_path.write_bytes(b"corrupt-source")
    with pytest.raises(CacheIntegrityError, match="failed size/hash"):
        store.read_artifact(
            artifact_id="shared-artifact",
            purpose=RunPurpose.AUDIT_REPLAY,
            source_manifest=manifest,
            audit_request=AuditReplayRequest(
                manifest.run_id, digest(manifest.to_canonical_bytes())
            ),
        )


def test_pin_failure_rolls_back_every_derived_pin_and_removes_subset_bypass(
    store: ReleaseCacheStore,
) -> None:
    scenario = Scenario(store)
    manifest = scenario.ready()
    with pytest.raises(TypeError):
        store.pin_run(manifest, artifact_ids=("shared-artifact",))  # type: ignore[call-arg]
    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            """CREATE TRIGGER injected_pin_failure BEFORE INSERT ON pin_artifacts
               BEGIN SELECT RAISE(ABORT, 'injected pin failure'); END"""
        )
    with pytest.raises(sqlite3.IntegrityError, match="injected pin failure"):
        store.pin_run(manifest)
    assert count(store.database_path, "strategy_run_pins") == 0
    assert count(store.database_path, "pin_releases") == 0
    assert count(store.database_path, "pin_artifacts") == 0
    assert count(store.database_path, "receipts") == 1
    assert count(store.database_path, "observations") == 8


def test_concurrent_first_initialization_converges_on_one_verified_v2(
    tmp_path: Path,
) -> None:
    worker_count = 24
    for round_index in range(10):
        database = tmp_path / f"concurrent-{round_index}.sqlite3"
        cache = tmp_path / f"concurrent-cache-{round_index}"
        barrier = Barrier(worker_count)

        def initialize(
            _index: int,
            *,
            round_barrier: Barrier = barrier,
            round_database: Path = database,
            round_cache: Path = cache,
        ) -> int:
            round_barrier.wait()
            return ReleaseCacheStore(
                database_path=round_database,
                cache_root=round_cache,
            ).schema_version

        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            versions = tuple(executor.map(initialize, range(worker_count)))
        assert versions == (2,) * worker_count
        assert ReleaseCacheStore(database_path=database, cache_root=cache).schema_version == 2


_V1_DDL = (
    "CREATE TABLE releases (release_id TEXT NOT NULL PRIMARY KEY, current_status_observation_id TEXT, current_admission_observation_id TEXT, created_at TEXT NOT NULL)",
    "CREATE TABLE release_status_observations (status_observation_id TEXT NOT NULL PRIMARY KEY, release_id TEXT NOT NULL, status TEXT NOT NULL, input_ref_schema_version TEXT NOT NULL, dataset_release_id TEXT NOT NULL, knowledge_cutoff TEXT NOT NULL, release_manifest_schema_version TEXT NOT NULL, manifest_hash_algorithm TEXT NOT NULL, manifest_hash_value TEXT NOT NULL, observed_at TEXT NOT NULL, reason TEXT)",
    "CREATE TABLE release_admission_observations (admission_observation_id TEXT NOT NULL PRIMARY KEY, release_id TEXT NOT NULL, status_observation_id TEXT NOT NULL, admission_status TEXT NOT NULL, observed_at TEXT NOT NULL, reason TEXT)",
    "CREATE TABLE cache_objects (sha256 TEXT NOT NULL PRIMARY KEY, size_bytes INTEGER NOT NULL, relative_path TEXT NOT NULL, stored_at TEXT NOT NULL)",
    "CREATE TABLE release_artifacts (release_id TEXT NOT NULL, artifact_id TEXT NOT NULL, sha256 TEXT NOT NULL, PRIMARY KEY(release_id, artifact_id))",
    "CREATE TABLE release_pins (run_id TEXT NOT NULL PRIMARY KEY, release_id TEXT NOT NULL, run_manifest_canonical BLOB NOT NULL, run_manifest_hash_algorithm TEXT NOT NULL, run_manifest_hash_value TEXT NOT NULL, canonical_profile_version TEXT NOT NULL, source_run_mode TEXT NOT NULL, input_ref_schema_version TEXT NOT NULL, dataset_release_id TEXT NOT NULL, knowledge_cutoff TEXT NOT NULL, release_manifest_schema_version TEXT NOT NULL, input_manifest_hash_algorithm TEXT NOT NULL, input_manifest_hash_value TEXT NOT NULL, receipt_hash_algorithm TEXT NOT NULL, receipt_hash_value TEXT NOT NULL, status_observation_id TEXT NOT NULL, admission_observation_id TEXT NOT NULL, pinned_at TEXT NOT NULL)",
    "CREATE TABLE pin_artifacts (run_id TEXT NOT NULL, release_id TEXT NOT NULL, artifact_id TEXT NOT NULL, sha256 TEXT NOT NULL, size_bytes INTEGER NOT NULL, PRIMARY KEY(run_id, artifact_id))",
    "CREATE INDEX status_observations_release_idx ON release_status_observations(release_id)",
    "CREATE INDEX admission_observations_release_idx ON release_admission_observations(release_id)",
    "CREATE INDEX release_artifacts_sha_idx ON release_artifacts(sha256)",
    "CREATE INDEX release_pins_release_idx ON release_pins(release_id)",
    "CREATE INDEX pin_artifacts_sha_idx ON pin_artifacts(sha256)",
)


def make_v1(database: Path, *, nonempty: bool = False) -> None:
    with sqlite3.connect(database) as connection:
        for sql in _V1_DDL:
            connection.execute(sql)
        if nonempty:
            connection.execute(
                "INSERT INTO cache_objects VALUES (?, 1, 'sha256/00/x', 'now')",
                ("0" * 64,),
            )
        connection.execute("PRAGMA user_version=1")


def test_empty_known_v1_upgrades_but_nonempty_v1_is_preserved(tmp_path: Path) -> None:
    empty = tmp_path / "empty.sqlite3"
    make_v1(empty)
    upgraded = ReleaseCacheStore(database_path=empty, cache_root=tmp_path / "empty-cache")
    assert upgraded.schema_version == 2

    nonempty = tmp_path / "nonempty.sqlite3"
    make_v1(nonempty, nonempty=True)
    with pytest.raises(StorageSchemaError, match="cannot be migrated"):
        ReleaseCacheStore(database_path=nonempty, cache_root=tmp_path / "nonempty-cache")
    with sqlite3.connect(nonempty) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert connection.execute("SELECT COUNT(*) FROM cache_objects").fetchone()[0] == 1


def test_unknown_empty_v1_and_tampered_v2_fail_closed(tmp_path: Path) -> None:
    unknown = tmp_path / "unknown.sqlite3"
    with sqlite3.connect(unknown) as connection:
        connection.execute("CREATE TABLE unexpected (value TEXT)")
        connection.execute("PRAGMA user_version=1")
    with pytest.raises(StorageSchemaError, match="inventory"):
        ReleaseCacheStore(database_path=unknown, cache_root=tmp_path / "unknown-cache")

    view_only = tmp_path / "view-only.sqlite3"
    with sqlite3.connect(view_only) as connection:
        connection.execute("CREATE VIEW unexpected_view AS SELECT 1 AS value")
    with pytest.raises(StorageSchemaError, match="unversioned"):
        ReleaseCacheStore(database_path=view_only, cache_root=tmp_path / "view-only-cache")
    with sqlite3.connect(view_only) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='view' AND name='unexpected_view'"
            ).fetchone()[0]
            == 1
        )

    view_v2 = tmp_path / "view-v2.sqlite3"
    view_cache = tmp_path / "view-v2-cache"
    ReleaseCacheStore(database_path=view_v2, cache_root=view_cache)
    with sqlite3.connect(view_v2) as connection:
        connection.execute("CREATE VIEW unexpected_view AS SELECT 1 AS value")
    with pytest.raises(StorageSchemaError, match="view inventory"):
        ReleaseCacheStore(database_path=view_v2, cache_root=view_cache)

    database = tmp_path / "v2.sqlite3"
    cache = tmp_path / "v2-cache"
    ReleaseCacheStore(database_path=database, cache_root=cache)
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER prevent_delete_release_heads")
    with pytest.raises(StorageSchemaError, match="trigger inventory"):
        ReleaseCacheStore(database_path=database, cache_root=cache)
