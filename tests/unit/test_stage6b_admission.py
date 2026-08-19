from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system.canonical import canonical_json_bytes
from invest_system.consumption import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ArtifactReceiptItem,
    DeliveryTransport,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    SchemaValidationResult,
)
from invest_system.domain.rule_approval import (
    RuleApprovalRegistry,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.integrations.investment_research_kb.http_client import (
    VerifiedHTTPDocument,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes as provider_canonical_json_bytes,
)
from invest_system.models import (
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
)
from invest_system.retention import (
    ReleaseRetentionClosure,
    ReleaseRetentionNode,
    RetentionArtifact,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    STAGE6B_AUTHORITY_ORIGIN,
    STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE,
    Stage6BAdmissionError,
    Stage6BHistoricalAdmissionEnvelope,
    Stage6BHistoricalAdmissionRequest,
    Stage6BValidationPreregistration,
    issue_stage6b_validation_confirmation,
    project_stage6b_status_evidence,
    stage6b_status_response_payloads,
)
from invest_system.strategies.industrial_event.stage6b_governance import (
    STAGE6_6B_APPROVAL_SCOPE,
    STAGE6_6B_RULE_APPROVAL_ID,
    STAGE6_6B_RULE_APPROVAL_RECORD_SHA256,
    STAGE6_6B_RULE_BUNDLE_ID,
    STAGE6_6B_RULE_BUNDLE_SHA256,
    STAGE6_6B_RULE_BUNDLE_VERSION,
    STAGE6_STRATEGY_ID,
    require_stage6b_admission_validation_capability,
)

RULE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
APPROVED_BUNDLE = RULE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.rule-bundle.json"
)
APPROVAL_RECORD = RULE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.approval.json"
)
TRANSPORT_FIXTURE = Path(
    "contracts/providers/investment_research_kb/stage6b-transport-v1/"
    "vendor/contracts/fixtures/stage6b-public-transport.v1.json"
)
CODE_COMMIT = "a" * 40
RUNTIME_LOCK = HashDigest(algorithm="sha256", value="b" * 64)
SEMANTIC_CONFIG = HashDigest(algorithm="sha256", value="c" * 64)
ARTIFACT_HASH = HashDigest(algorithm="sha256", value="d" * 64)
MANIFEST_HASH = HashDigest(algorithm="sha256", value="e" * 64)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _capability(repository_root: Path) -> Any:
    document = rule_bundle_document_from_json_value(_json(repository_root / APPROVED_BUNDLE))
    approval = rule_approval_record_from_json_value(_json(repository_root / APPROVAL_RECORD))
    return require_stage6b_admission_validation_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )


def _fixture_response(repository_root: Path) -> dict[str, Any]:
    fixture = _json(repository_root / TRANSPORT_FIXTURE)
    response = fixture["http_examples"]["release_status_success"]["response"]
    assert isinstance(response, dict)
    return deepcopy(response)


def _strategy_input_ref() -> StrategyInputRef:
    return StrategyInputRef(
        schema_version="1.0.0",
        dataset_release_id="rel_stage6b_transport_fixture",
        knowledge_cutoff=datetime(2026, 8, 1, tzinfo=UTC),
        release_manifest_schema_version="1.0.0",
        manifest_hash=MANIFEST_HASH,
    )


def _verified_status_document(
    repository_root: Path,
    *,
    response: dict[str, Any] | None = None,
    response_bytes: bytes | None = None,
) -> VerifiedHTTPDocument:
    selected = _fixture_response(repository_root) if response is None else response
    body = provider_canonical_json_bytes(selected) if response_bytes is None else response_bytes
    return VerifiedHTTPDocument(
        operation="get_dataset_release_status_history",
        request_path=("/api/v1/dataset-releases/rel_stage6b_transport_fixture/status"),
        release_id="rel_stage6b_transport_fixture",
        request_id="req-stage6b-fixture",
        knowledge_cutoff="2026-08-01T00:00:00.000000Z",
        response_sha256=sha256(body).hexdigest(),
        response_bytes=body,
        data=selected["data"],
        authority_eligible=False,
    )


def _projection(repository_root: Path, *, checked_at: datetime) -> Any:
    return project_stage6b_status_evidence(
        _verified_status_document(repository_root),
        strategy_input_ref=_strategy_input_ref(),
        checked_at=checked_at,
        status_observation_id="status_observation_stage6b_root",
    )


def _complete_admission(repository_root: Path) -> dict[str, Any]:
    capability = _capability(repository_root)
    strategy_input_ref = _strategy_input_ref()
    preregistration = Stage6BValidationPreregistration.create(
        preregistration_id="stage6b_validation_preregistration",
        frozen_at=datetime(2026, 8, 1, 0, 3, tzinfo=UTC),
    )
    request = Stage6BHistoricalAdmissionRequest.create(
        request_id="stage6b_admission_request",
        run_id="stage6b_validation_run",
        strategy_input_ref=strategy_input_ref,
        capability=capability,
        code_commit=CODE_COMMIT,
        runtime_environment_lock_hash=RUNTIME_LOCK,
        semantic_config_hash=SEMANTIC_CONFIG,
        injected_clock=datetime(2026, 8, 1, 0, 3, 59, tzinfo=UTC),
        preregistration=preregistration,
    )
    artifact = ArtifactReceiptItem(
        artifact_id="market-daily-v1",
        item_type="market_daily",
        artifact_hash=ARTIFACT_HASH,
        size_bytes=100,
        record_count=1,
    )
    receipt = ArtifactConsumptionReceipt.create(
        consumer_contract_version="1.0.0",
        strategy_input_ref=strategy_input_ref,
        artifacts=(artifact,),
    )
    closure = ReleaseRetentionClosure.create(
        root_strategy_input_ref=strategy_input_ref,
        releases=(
            ReleaseRetentionNode(
                strategy_input_ref=strategy_input_ref,
                manifest_document_hash=HashDigest(algorithm="sha256", value="f" * 64),
                manifest_size_bytes=200,
                artifacts=(
                    RetentionArtifact(
                        artifact_id=artifact.artifact_id,
                        item_type=artifact.item_type,
                        artifact_hash=artifact.artifact_hash,
                        size_bytes=artifact.size_bytes,
                        record_count=artifact.record_count,
                    ),
                ),
            ),
        ),
    )
    projection = _projection(
        repository_root,
        checked_at=datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),
    )
    confirmation = issue_stage6b_validation_confirmation(
        confirmation_id="stage6b_validation_confirmation",
        request=request,
        receipt=receipt,
        closure=closure,
        evidences=(projection.evidence,),
        confirmed_at=datetime(2026, 8, 1, 0, 4, 31, tzinfo=UTC),
    )
    fetch_observation = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="artifact_fetch_stage6b_root",
        release_id=strategy_input_ref.dataset_release_id,
        strategy_input_ref=strategy_input_ref,
        observed_at=datetime(2026, 8, 1, 0, 3, 58, tzinfo=UTC),
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        source_endpoint=STAGE6B_AUTHORITY_ORIGIN,
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=(artifact.artifact_id,),
        response_or_export_bytes_hash=HashDigest(algorithm="sha256", value="1" * 64),
        local_cache_keys=(f"sha256:{artifact.artifact_hash.value}",),
    )
    admission_observation = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="release_admission_stage6b_root",
        release_id=strategy_input_ref.dataset_release_id,
        strategy_input_ref=strategy_input_ref,
        observed_at=datetime(2026, 8, 1, 0, 4, 32, tzinfo=UTC),
        status_observation_id=projection.observation.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
    )
    manifest = StrategyRunManifest(
        strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        run_id=request.run_id,
        created_at=datetime(2026, 8, 1, 0, 4, 33, tzinfo=UTC),
        strategy_id=STAGE6_STRATEGY_ID,
        strategy_version="0.1.0",
        code_commit=CODE_COMMIT,
        rule_bundle_id=STAGE6_6B_RULE_BUNDLE_ID,
        rule_bundle_version=STAGE6_6B_RULE_BUNDLE_VERSION,
        rule_bundle_hash=HashDigest(algorithm="sha256", value=STAGE6_6B_RULE_BUNDLE_SHA256),
        rule_status=RuleStatus.APPROVED,
        rule_approval_id=STAGE6_6B_RULE_APPROVAL_ID,
        rule_approval_record_hash=HashDigest(
            algorithm="sha256", value=STAGE6_6B_RULE_APPROVAL_RECORD_SHA256
        ),
        rule_approval_scope=STAGE6_6B_APPROVAL_SCOPE.value,
        config_hash=SEMANTIC_CONFIG,
        strategy_input_ref=strategy_input_ref,
        input_envelope_hash=request.request_hash,
        strategy_case_envelope_hash=None,
        strategy_case_input_hash=None,
        synthetic_fixture_id=None,
        synthetic_fixture_version=None,
        synthetic_fixture_payload_hash=None,
        input_path="stage6b_validation",
        synthetic=False,
        validation_only=True,
        not_a_published_release=False,
        not_strategy_evidence=True,
        authorizes_positions=False,
        authorizes_orders=False,
        artifact_consumption_receipt_hash=receipt.receipt_hash,
        artifact_fetch_observation_id=fetch_observation.observation_id,
        release_status_observation_id=projection.observation.observation_id,
        release_admission_observation_id=admission_observation.observation_id,
        random_seed=0,
        run_mode=RunMode.RESEARCH,
        runtime_environment_lock_hash=RUNTIME_LOCK,
    )
    envelope = Stage6BHistoricalAdmissionEnvelope.create(
        request=request,
        preregistration=preregistration,
        receipt=receipt,
        closure=closure,
        fetch_observation=fetch_observation,
        status_evidences=(projection.evidence,),
        status_observations=(projection.observation,),
        admission_observation=admission_observation,
        manifest=manifest,
        confirmation=confirmation,
    )
    return {
        "capability": capability,
        "preregistration": preregistration,
        "request": request,
        "receipt": receipt,
        "closure": closure,
        "projection": projection,
        "confirmation": confirmation,
        "fetch_observation": fetch_observation,
        "admission_observation": admission_observation,
        "manifest": manifest,
        "envelope": envelope,
    }


def test_official_status_fixture_projects_content_bound_zero_authority_evidence(
    repository_root: Path,
) -> None:
    checked_at = datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC)
    first = _projection(repository_root, checked_at=checked_at)
    second = _projection(repository_root, checked_at=checked_at)

    assert first == second
    assert first.evidence.status.value == "published"
    assert first.evidence.status_sequence == 3
    assert first.evidence.authority_eligible is False
    assert first.evidence.validation_only is True
    assert sha256(first.payload.content).hexdigest() == (first.evidence.response_bytes_hash.value)
    assert stage6b_status_response_payloads((first,))[first.evidence.release_id] == (first.payload)


def test_status_projection_fails_closed_on_bytes_identity_chain_and_time(
    repository_root: Path,
) -> None:
    response = _fixture_response(repository_root)
    wrong_request = _verified_status_document(repository_root, response=response)
    wrong_request = replace(wrong_request, request_id="req-other")
    with pytest.raises(Stage6BAdmissionError, match="STATUS_DOCUMENT_IDENTITY_MISMATCH"):
        project_stage6b_status_evidence(
            wrong_request,
            strategy_input_ref=_strategy_input_ref(),
            checked_at=datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),
            status_observation_id="status_observation_stage6b_root",
        )

    document = _verified_status_document(repository_root, response=response)
    document = replace(document, response_bytes=document.response_bytes + b" ")
    with pytest.raises(Stage6BAdmissionError, match="STATUS_RESPONSE_HASH_MISMATCH"):
        project_stage6b_status_evidence(
            document,
            strategy_input_ref=_strategy_input_ref(),
            checked_at=datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),
            status_observation_id="status_observation_stage6b_root",
        )

    with pytest.raises(Stage6BAdmissionError, match="STATUS_STALE"):
        _projection(
            repository_root,
            checked_at=datetime(2026, 8, 1, 0, 4, tzinfo=UTC)
            + STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE
            + timedelta(microseconds=1),
        )


def test_complete_validation_admission_is_deterministic_and_never_evaluates(
    repository_root: Path,
) -> None:
    first = _complete_admission(repository_root)
    second = _complete_admission(repository_root)
    envelope = first["envelope"]

    assert envelope == second["envelope"]
    assert envelope.strategy_evaluator_calls == 0
    assert envelope.validation_only is True
    assert envelope.authority_eligible is False
    assert envelope.manifest.authorizes_positions is False
    assert envelope.manifest.authorizes_orders is False
    assert envelope.pin_release_ids == ("rel_stage6b_transport_fixture",)
    assert envelope.pin_artifact_keys == ("rel_stage6b_transport_fixture:market-daily-v1",)
    assert envelope.confirmation.items == (first["projection"].evidence,)
    assert (
        envelope.envelope_hash.value
        == sha256(canonical_json_bytes(envelope.identity_payload())).hexdigest()
    )


def test_complete_closure_manifest_and_observation_drift_fail_closed(
    repository_root: Path,
) -> None:
    values = _complete_admission(repository_root)

    with pytest.raises(Stage6BAdmissionError, match="CONFIRMATION_CLOSURE_MISMATCH"):
        issue_stage6b_validation_confirmation(
            confirmation_id="stage6b_validation_confirmation",
            request=values["request"],
            receipt=values["receipt"],
            closure=values["closure"],
            evidences=(),
            confirmed_at=datetime(2026, 8, 1, 0, 4, 31, tzinfo=UTC),
        )

    drifted_manifest = replace(
        values["manifest"],
        config_hash=HashDigest(algorithm="sha256", value="2" * 64),
    )
    with pytest.raises(Stage6BAdmissionError, match="MANIFEST_MISMATCH"):
        Stage6BHistoricalAdmissionEnvelope.create(
            request=values["request"],
            preregistration=values["preregistration"],
            receipt=values["receipt"],
            closure=values["closure"],
            fetch_observation=values["fetch_observation"],
            status_evidences=(values["projection"].evidence,),
            status_observations=(values["projection"].observation,),
            admission_observation=values["admission_observation"],
            manifest=drifted_manifest,
            confirmation=values["confirmation"],
        )

    drifted_fetch = replace(
        values["fetch_observation"],
        artifact_ids=("different-artifact",),
    )
    with pytest.raises(Stage6BAdmissionError, match="ROOT_OBSERVATION_MISMATCH"):
        Stage6BHistoricalAdmissionEnvelope.create(
            request=values["request"],
            preregistration=values["preregistration"],
            receipt=values["receipt"],
            closure=values["closure"],
            fetch_observation=drifted_fetch,
            status_evidences=(values["projection"].evidence,),
            status_observations=(values["projection"].observation,),
            admission_observation=values["admission_observation"],
            manifest=values["manifest"],
            confirmation=values["confirmation"],
        )
