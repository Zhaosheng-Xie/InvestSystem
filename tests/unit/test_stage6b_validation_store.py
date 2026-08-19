from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system.integrations.investment_research_kb.http_client import (
    VerifiedHTTPDocument,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes as provider_canonical_json_bytes,
)
from invest_system.integrations.investment_research_kb.stage6b_status import (
    project_stage6b_status_evidence,
)
from invest_system.models import HashDigest, StrategyInputRef
from invest_system.retention import (
    ArtifactPayload,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
    ReleaseRetentionNode,
    RetentionArtifact,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    Stage6BHistoricalAdmissionEnvelope,
    issue_stage6b_validation_confirmation,
)
from invest_system.strategies.industrial_event.stage6b_validation_store import (
    Stage6BAdmissionStatus,
    Stage6BValidationStore,
    Stage6BValidationStoreError,
)

from .test_stage6b_admission import (
    _complete_admission,
    _fixture_response,
    _rehash_status_response,
)


def _commit(
    store: Stage6BValidationStore,
    values: dict[str, Any],
    *,
    committed_at: datetime = datetime(2026, 8, 1, 0, 4, 40, tzinfo=UTC),
) -> Any:
    return store.commit_validation_admission(
        values["envelope"],
        manifest_payloads=values["manifest_payloads"],
        artifact_payloads=values["artifact_payloads"],
        status_payloads=values["status_payloads"],
        committed_at=committed_at,
    )


def test_validation_store_seals_last_and_exact_retry_is_idempotent(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    store = Stage6BValidationStore(tmp_path / "isolated-stage6b")

    first = _commit(store, values)
    second = _commit(
        store,
        values,
        committed_at=datetime(2026, 8, 1, 0, 4, 50, tzinfo=UTC),
    )

    assert first == second == store.read_validation_seal(first.run_id)
    assert first.status is Stage6BAdmissionStatus.SEALED_VALIDATION_ONLY
    assert first.validation_only is True
    assert first.authority_eligible is False
    assert first.strategy_evaluator_calls == 0
    counts = store.authoritative_row_counts()
    assert counts["stage6b_validation_seals"] == 1
    assert counts["stage6b_validation_generations"] == 1
    assert counts["stage6b_validation_release_heads"] == 1
    assert counts["stage6b_validation_pin_releases"] == 1
    assert counts["stage6b_validation_pin_artifacts"] == 1
    with sqlite3.connect(store.database_path) as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE stage6b_validation_seals SET seal_id='changed' WHERE run_id=?",
                (first.run_id,),
            )

    with pytest.raises(Stage6BValidationStoreError, match="PRECHECK_BLOCKED"):
        Stage6BValidationStore(repository_root / "var" / "state" / "stage6b")


def test_same_run_different_envelope_is_an_immutable_identity_conflict(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    first = _complete_admission(repository_root)
    changed = _complete_admission(repository_root, request_id="stage6b_changed_request")
    store = Stage6BValidationStore(tmp_path / "isolated-stage6b")
    _commit(store, first)

    with pytest.raises(Stage6BValidationStoreError, match="IMMUTABLE_IDENTITY_CONFLICT"):
        _commit(store, changed)
    assert store.authoritative_row_counts()["stage6b_validation_seals"] == 1


@pytest.mark.parametrize(
    "failure_step",
    (
        "cas_prepared",
        "release_identities",
        "receipt_closure",
        "observations",
        "preregistration",
        "manifest",
        "confirmation",
        "pins",
        "envelope",
        "before_seal",
    ),
)
def test_failure_before_seal_rolls_back_every_authoritative_row_but_may_leave_cas(
    repository_root: Path,
    tmp_path: Path,
    failure_step: str,
) -> None:
    class InjectedFailure(RuntimeError):
        pass

    def inject_failure(step: str) -> None:
        if step == failure_step:
            raise InjectedFailure("injected transaction failure")

    values = _complete_admission(repository_root)
    store = Stage6BValidationStore(
        tmp_path / "isolated-stage6b",
        _failure_hook=inject_failure,
    )
    with pytest.raises(InjectedFailure, match="injected transaction failure"):
        _commit(store, values)

    assert all(count == 0 for count in store.authoritative_row_counts().values())
    assert tuple((store.cache_root / "objects").rglob("[0-9a-f]*"))
    with pytest.raises(KeyError):
        store.read_validation_seal(values["request"].run_id)


def test_commit_rechecks_freshness_payload_sets_and_sealed_cas(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    store = Stage6BValidationStore(tmp_path / "isolated-stage6b")

    at_boundary = datetime(2026, 8, 1, 0, 9, tzinfo=UTC)
    seal = _commit(store, values, committed_at=at_boundary)
    assert seal.committed_at == at_boundary

    late_store = Stage6BValidationStore(tmp_path / "late-stage6b")
    with pytest.raises(Stage6BValidationStoreError, match="STATUS_UNCONFIRMED"):
        _commit(
            late_store,
            values,
            committed_at=at_boundary + timedelta(microseconds=1),
        )

    missing_store = Stage6BValidationStore(tmp_path / "missing-stage6b")
    with pytest.raises(Stage6BValidationStoreError, match="RECONCILIATION_BLOCKED"):
        missing_store.commit_validation_admission(
            values["envelope"],
            manifest_payloads=(),
            artifact_payloads=values["artifact_payloads"],
            status_payloads=values["status_payloads"],
            committed_at=datetime(2026, 8, 1, 0, 4, 40, tzinfo=UTC),
        )

    cas_file = next(path for path in (store.cache_root / "objects").rglob("*") if path.is_file())
    cas_file.write_bytes(b"tampered")
    with pytest.raises(Stage6BValidationStoreError, match="RECONCILIATION_BLOCKED"):
        store.read_validation_seal(seal.run_id)


def test_read_rejects_child_index_injection_and_concurrent_retry_has_one_generation(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    store = Stage6BValidationStore(tmp_path / "concurrent-stage6b")
    with ThreadPoolExecutor(max_workers=2) as executor:
        seals = tuple(executor.map(lambda _: _commit(store, values), range(2)))
    assert seals[0] == seals[1]
    assert store.authoritative_row_counts()["stage6b_validation_generations"] == 1

    with sqlite3.connect(store.database_path) as connection:
        connection.execute(
            "INSERT INTO stage6b_validation_links VALUES (?, ?, ?, ?, ?, ?)",
            (
                "admission_envelope",
                seals[0].envelope_hash.value,
                "injected",
                0,
                "injected",
                "0" * 64,
            ),
        )
    with pytest.raises(Stage6BValidationStoreError, match="RECONCILIATION_BLOCKED"):
        store.read_validation_seal(seals[0].run_id)


def test_complete_transitive_source_release_is_confirmed_pinned_and_cached(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    source_release_id = "rel_stage6b_source_fixture"
    source_response = _fixture_response(repository_root)
    source_response["meta"]["request_id"] = "req-stage6b-source-fixture"
    source_response["meta"]["release_id"] = source_release_id
    source_response["data"]["release_id"] = source_release_id
    for event in source_response["data"]["events"]:
        event["release_id"] = source_release_id
        event["event_id"] = event["event_id"].replace("transport", "source")
    _rehash_status_response(source_response)
    source_body = provider_canonical_json_bytes(source_response)
    source_ref = StrategyInputRef(
        schema_version="1.0.0",
        dataset_release_id=source_release_id,
        knowledge_cutoff=datetime(2026, 8, 1, tzinfo=UTC),
        release_manifest_schema_version="1.0.0",
        manifest_hash=HashDigest(algorithm="sha256", value="8" * 64),
    )
    source_projection = project_stage6b_status_evidence(
        VerifiedHTTPDocument(
            operation="get_dataset_release_status_history",
            request_path=f"/api/v1/dataset-releases/{source_release_id}/status",
            release_id=source_release_id,
            request_id="req-stage6b-source-fixture",
            knowledge_cutoff="2026-08-01T00:00:00.000000Z",
            response_sha256=sha256(source_body).hexdigest(),
            response_bytes=source_body,
            data=source_response["data"],
            authority_eligible=False,
        ),
        strategy_input_ref=source_ref,
        checked_at=datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),
        status_observation_id="status_observation_stage6b_source",
    )
    source_manifest_content = b"stage6b source validation manifest bytes\n"
    source_artifact_content = b"stage6b source validation artifact bytes\n"
    source_artifact_hash = HashDigest(
        algorithm="sha256", value=sha256(source_artifact_content).hexdigest()
    )
    root_node = replace(
        values["closure"].release(values["request"].strategy_input_ref.dataset_release_id),
        dependency_release_ids=(source_release_id,),
    )
    source_node = ReleaseRetentionNode(
        strategy_input_ref=source_ref,
        manifest_document_hash=HashDigest(
            algorithm="sha256", value=sha256(source_manifest_content).hexdigest()
        ),
        manifest_size_bytes=len(source_manifest_content),
        artifacts=(
            RetentionArtifact(
                artifact_id="source-evidence-v1",
                item_type="evidence_bundle",
                artifact_hash=source_artifact_hash,
                size_bytes=len(source_artifact_content),
                record_count=1,
            ),
        ),
    )
    closure = ReleaseRetentionClosure.create(
        root_strategy_input_ref=values["request"].strategy_input_ref,
        releases=(root_node, source_node),
    )
    confirmation = issue_stage6b_validation_confirmation(
        confirmation_id="stage6b_validation_confirmation",
        request=values["request"],
        receipt=values["receipt"],
        closure=closure,
        evidences=(values["projection"].evidence, source_projection.evidence),
        confirmed_at=datetime(2026, 8, 1, 0, 4, 31, tzinfo=UTC),
    )
    envelope = Stage6BHistoricalAdmissionEnvelope.create(
        request=values["request"],
        preregistration=values["preregistration"],
        receipt=values["receipt"],
        closure=closure,
        fetch_observation=values["fetch_observation"],
        status_evidences=(values["projection"].evidence, source_projection.evidence),
        status_observations=(
            values["projection"].observation,
            source_projection.observation,
        ),
        admission_observation=values["admission_observation"],
        manifest=values["manifest"],
        confirmation=confirmation,
    )
    store = Stage6BValidationStore(tmp_path / "multi-source-stage6b")
    seal = store.commit_validation_admission(
        envelope,
        manifest_payloads=(
            *values["manifest_payloads"],
            ReleaseManifestPayload(
                release_id=source_release_id,
                content=source_manifest_content,
            ),
        ),
        artifact_payloads=(
            *values["artifact_payloads"],
            ArtifactPayload(
                release_id=source_release_id,
                artifact_id="source-evidence-v1",
                content=source_artifact_content,
            ),
        ),
        status_payloads={
            **values["status_payloads"],
            source_release_id: source_projection.payload,
        },
        committed_at=datetime(2026, 8, 1, 0, 4, 40, tzinfo=UTC),
    )

    assert seal == store.read_validation_seal(seal.run_id)
    counts = store.authoritative_row_counts()
    assert counts["stage6b_validation_release_heads"] == 2
    assert counts["stage6b_validation_pin_releases"] == 2
    assert counts["stage6b_validation_pin_artifacts"] == 2
    assert counts["stage6b_validation_cas_links"] == 6
