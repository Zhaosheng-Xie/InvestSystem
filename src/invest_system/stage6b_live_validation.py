"""Prepare and execute one isolated Stage 6B public-HTTPS validation seal.

The producer handoff is parsed through the already pinned Stage 3D Context
Pack contract.  Content is validated before the Stage 6B admission window;
the existing Stage 6B orchestrator then performs fresh status reads for every
Release in the exact retention closure and writes only to an isolated
validation store.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_json_bytes, normalize_utc
from invest_system.consumption import (
    ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ArtifactReceiptItem,
    DeliveryTransport,
    SchemaValidationResult,
)
from invest_system.domain.rule_approval import (
    RuleApprovalRegistry,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    KBTransportContractCatalog,
    Stage3DArtifactExpectation,
    Stage3DExpectation,
    Stage3DValidationResult,
    manifest_sha256,
    sealed_manifest_bytes,
    validate_stage3d_http_context_pack,
)
from invest_system.integrations.investment_research_kb.reference_fixture import (
    CONSUMER_CONTRACT_VERSION,
)
from invest_system.models import HashDigest, StrategyInputRef
from invest_system.retention import (
    ArtifactPayload,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
    ReleaseRetentionNode,
    RetentionArtifact,
)
from invest_system.stage6b_http_admission import (
    Stage6BHTTPValidationAdmissionResult,
    execute_stage6b_public_https_validation_admission,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    STAGE6B_AUTHORITY_ORIGIN,
    Stage6BHistoricalAdmissionRequest,
    Stage6BValidationPreregistration,
)
from invest_system.strategies.industrial_event.stage6b_governance import (
    require_stage6b_admission_validation_capability,
)
from invest_system.strategies.industrial_event.stage6b_validation_store import (
    Stage6BValidationStore,
)

type InjectedClock = Callable[[], datetime]

_RULE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
_APPROVED_BUNDLE = _RULE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.rule-bundle.json"
)
_APPROVAL_RECORD = _RULE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.approval.json"
)


class Stage6BLiveValidationError(ValueError):
    """Stable fail-closed error raised before an isolated seal is published."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Stage6BLivePreparedAdmission:
    """Content-validated, zero-authority inputs for the fresh status window."""

    preregistration: Stage6BValidationPreregistration
    request: Stage6BHistoricalAdmissionRequest
    receipt: ArtifactConsumptionReceipt
    closure: ReleaseRetentionClosure
    fetch_observation: ArtifactFetchObservation
    manifest_payloads: tuple[ReleaseManifestPayload, ...]
    artifact_payloads: tuple[ArtifactPayload, ...]
    stage3d_validation: Stage3DValidationResult
    handoff_sha256: str
    validation_only: bool = True
    authority_eligible: bool = False

    def __post_init__(self) -> None:
        if self.request.strategy_input_ref != self.receipt.strategy_input_ref or (
            self.request.strategy_input_ref != self.closure.root_strategy_input_ref
        ):
            raise ValueError("prepared admission root identities differ")
        if type(self.validation_only) is not bool or not self.validation_only:
            raise ValueError("prepared admission must be validation-only")
        if type(self.authority_eligible) is not bool or self.authority_eligible:
            raise ValueError("prepared admission must remain authority-ineligible")
        if self.stage3d_validation.authority_eligible:
            raise ValueError("Stage 3D validation unexpectedly carried authority")
        if len(self.handoff_sha256) != 64:
            raise ValueError("handoff_sha256 must be SHA-256")


@dataclass(frozen=True, slots=True)
class Stage6BLiveValidationResult:
    """Sanitized result combining content validation and the isolated seal."""

    admission: Stage6BHTTPValidationAdmissionResult
    content_response_sha256: tuple[tuple[str, str], ...]
    content_artifact_sha256: tuple[tuple[str, str], ...]
    handoff_sha256: str
    validation_only: bool = True
    authority_eligible: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "content_response_sha256", tuple(sorted(self.content_response_sha256))
        )
        object.__setattr__(
            self, "content_artifact_sha256", tuple(sorted(self.content_artifact_sha256))
        )
        if len(self.handoff_sha256) != 64:
            raise ValueError("handoff_sha256 must be SHA-256")
        if type(self.validation_only) is not bool or not self.validation_only:
            raise ValueError("live validation result must be validation-only")
        if type(self.authority_eligible) is not bool or self.authority_eligible:
            raise ValueError("live validation result must remain authority-ineligible")


def read_stage6b_credential_env(path: Path) -> tuple[str, str]:
    """Read the two allowed credentials without putting their values in errors."""

    if not isinstance(path, Path):
        raise TypeError("path must be a pathlib.Path")
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise Stage6BLiveValidationError(
                "CREDENTIAL_ENV_INVALID", "credential file contains an invalid line"
            )
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {"KB_BASE_URL", "KB_BEARER_TOKEN"} or key in values:
            raise Stage6BLiveValidationError(
                "CREDENTIAL_ENV_INVALID", "credential file keys differ"
            )
        values[key] = value.strip().strip('"').strip("'")
    if set(values) != {"KB_BASE_URL", "KB_BEARER_TOKEN"} or not all(values.values()):
        raise Stage6BLiveValidationError("CREDENTIAL_ENV_INVALID", "credential file is incomplete")
    return values["KB_BASE_URL"], values["KB_BEARER_TOKEN"]


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Stage6BLiveValidationError("LOCAL_RULE_INVALID", "local rule file is not an object")
    return value


def _derived_id(prefix: str, *, expectation: Stage3DExpectation, observed_at: datetime) -> str:
    digest = sha256(
        canonical_json_bytes(
            {
                "prefix": prefix,
                "handoff_sha256": expectation.handoff_sha256,
                "observed_at": normalize_utc(observed_at, field_name="observed_at"),
            }
        )
    ).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _artifact_item(
    expectation: Stage3DArtifactExpectation,
    *,
    record_count: int | None,
) -> ArtifactReceiptItem:
    return ArtifactReceiptItem(
        artifact_id=expectation.artifact_id,
        item_type=expectation.item_type,
        artifact_hash=HashDigest(algorithm="sha256", value=expectation.sha256),
        size_bytes=expectation.size_bytes,
        record_count=record_count,
    )


def _retention_artifact(
    expectation: Stage3DArtifactExpectation,
    *,
    record_count: int | None,
) -> RetentionArtifact:
    item = _artifact_item(expectation, record_count=record_count)
    return RetentionArtifact(
        artifact_id=item.artifact_id,
        item_type=item.item_type,
        artifact_hash=item.artifact_hash,
        size_bytes=item.size_bytes,
        record_count=item.record_count,
    )


def _require_manifest_identity(
    manifest: dict[str, Any],
    *,
    release_id: str,
    manifest_hash: str,
    knowledge_cutoff: datetime,
) -> None:
    cutoff = knowledge_cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
    declared = manifest.get("manifest_hash")
    if (
        manifest.get("release_id") != release_id
        or manifest.get("knowledge_cutoff") != cutoff
        or manifest_sha256(manifest) != manifest_hash
        or not isinstance(declared, dict)
        or declared != {"algorithm": "sha256", "value": manifest_hash}
    ):
        raise Stage6BLiveValidationError(
            "MANIFEST_IDENTITY_MISMATCH", f"validated Manifest differs for {release_id}"
        )


def _download_exact_artifacts(
    client: KBReadOnlyHTTPClient,
    expectation: Stage3DExpectation,
) -> dict[tuple[str, str], bytes]:
    downloaded: dict[tuple[str, str], bytes] = {}
    for release_id, item in (
        (expectation.context_release_id, expectation.context_artifact),
        (expectation.context_release_id, expectation.context_schema_artifact),
        (expectation.evidence_release_id, expectation.evidence_artifact),
        (expectation.evidence_release_id, expectation.evidence_schema_artifact),
    ):
        artifact = client.download_artifact(
            release_id,
            item.artifact_id,
            expected_sha256=item.sha256,
            expected_size_bytes=item.size_bytes,
        )
        if artifact.sha256 != item.sha256:
            raise Stage6BLiveValidationError(
                "ARTIFACT_IDENTITY_MISMATCH", f"validated artifact differs: {item.artifact_id}"
            )
        downloaded[(release_id, item.artifact_id)] = artifact.content
    return downloaded


def prepare_stage6b_live_validation(
    *,
    repository_root: Path,
    client: KBReadOnlyHTTPClient,
    catalog: KBTransportContractCatalog,
    expectation: Stage3DExpectation,
    observed_at: datetime,
    code_commit: str,
    runtime_environment_lock_hash: HashDigest,
    semantic_config_hash: HashDigest,
) -> Stage6BLivePreparedAdmission:
    """Validate content and materialize the exact Stage 6B closure in memory."""

    observed = normalize_utc(observed_at, field_name="observed_at")
    if expectation.base_url != STAGE6B_AUTHORITY_ORIGIN:
        raise Stage6BLiveValidationError(
            "AUTHORITY_ORIGIN_MISMATCH", "handoff origin differs from the approved authority"
        )
    stage3d = validate_stage3d_http_context_pack(
        client=client,
        catalog=catalog,
        expectation=expectation,
        observed_at=observed,
        code_commit=code_commit,
        config_hash=semantic_config_hash,
        runtime_environment_lock_hash=runtime_environment_lock_hash,
    )
    if (
        stage3d.authority_eligible
        or stage3d.run_release_status_confirmation_issued
        or (stage3d.persists_state)
    ):
        raise Stage6BLiveValidationError(
            "STAGE3D_BOUNDARY_INVALID", "content validation exceeded its zero-authority boundary"
        )

    context_bundle = client.get_release_bundle(expectation.context_release_id)
    evidence_bundle = client.get_release_bundle(expectation.evidence_release_id)
    _require_manifest_identity(
        context_bundle.manifest.data,
        release_id=expectation.context_release_id,
        manifest_hash=expectation.manifest_hash,
        knowledge_cutoff=expectation.knowledge_cutoff,
    )
    _require_manifest_identity(
        evidence_bundle.manifest.data,
        release_id=expectation.evidence_release_id,
        manifest_hash=expectation.evidence_manifest_hash,
        knowledge_cutoff=expectation.knowledge_cutoff,
    )
    downloaded = _download_exact_artifacts(client, expectation)
    for item in (
        expectation.context_artifact,
        expectation.context_schema_artifact,
        expectation.evidence_artifact,
        expectation.evidence_schema_artifact,
    ):
        if stage3d.artifact_sha256.get(item.artifact_id) != item.sha256:
            raise Stage6BLiveValidationError(
                "CONTENT_REACQUISITION_MISMATCH", f"artifact changed: {item.artifact_id}"
            )

    context_manifest_bytes = sealed_manifest_bytes(context_bundle.manifest.data)
    evidence_manifest_bytes = sealed_manifest_bytes(evidence_bundle.manifest.data)
    evidence_ref = StrategyInputRef(
        schema_version=expectation.strategy_input_ref.schema_version,
        dataset_release_id=expectation.evidence_release_id,
        knowledge_cutoff=expectation.knowledge_cutoff,
        release_manifest_schema_version=str(evidence_bundle.manifest.data["schema_version"]),
        manifest_hash=HashDigest(algorithm="sha256", value=expectation.evidence_manifest_hash),
    )
    root_items = (
        _artifact_item(expectation.context_artifact, record_count=1),
        _artifact_item(expectation.context_schema_artifact, record_count=None),
    )
    receipt = ArtifactConsumptionReceipt.create(
        schema_version=ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
        consumer_contract_version=CONSUMER_CONTRACT_VERSION,
        strategy_input_ref=expectation.strategy_input_ref,
        artifacts=root_items,
    )
    closure = ReleaseRetentionClosure.create(
        root_strategy_input_ref=expectation.strategy_input_ref,
        releases=(
            ReleaseRetentionNode(
                strategy_input_ref=expectation.strategy_input_ref,
                manifest_document_hash=_hash_file_bytes(context_manifest_bytes),
                manifest_size_bytes=len(context_manifest_bytes),
                artifacts=(
                    _retention_artifact(expectation.context_artifact, record_count=1),
                    _retention_artifact(expectation.context_schema_artifact, record_count=None),
                ),
                dependency_release_ids=(expectation.evidence_release_id,),
            ),
            ReleaseRetentionNode(
                strategy_input_ref=evidence_ref,
                manifest_document_hash=_hash_file_bytes(evidence_manifest_bytes),
                manifest_size_bytes=len(evidence_manifest_bytes),
                artifacts=(
                    _retention_artifact(expectation.evidence_artifact, record_count=1),
                    _retention_artifact(expectation.evidence_schema_artifact, record_count=None),
                ),
            ),
        ),
    )

    document = rule_bundle_document_from_json_value(
        _json_object(repository_root / _APPROVED_BUNDLE)
    )
    approval = rule_approval_record_from_json_value(
        _json_object(repository_root / _APPROVAL_RECORD)
    )
    capability = require_stage6b_admission_validation_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )
    run_id = _derived_id("run_stage6b_validation", expectation=expectation, observed_at=observed)
    preregistration = Stage6BValidationPreregistration.create(
        preregistration_id=_derived_id(
            "prereg_stage6b_validation", expectation=expectation, observed_at=observed
        ),
        frozen_at=observed,
    )
    request = Stage6BHistoricalAdmissionRequest.create(
        request_id=_derived_id(
            "request_stage6b_validation", expectation=expectation, observed_at=observed
        ),
        run_id=run_id,
        strategy_input_ref=expectation.strategy_input_ref,
        capability=capability,
        code_commit=code_commit,
        runtime_environment_lock_hash=runtime_environment_lock_hash,
        semantic_config_hash=semantic_config_hash,
        injected_clock=observed,
        preregistration=preregistration,
    )
    fetch_observation = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=_derived_id(
            "fetch_stage6b_validation", expectation=expectation, observed_at=observed
        ),
        release_id=expectation.context_release_id,
        strategy_input_ref=expectation.strategy_input_ref,
        observed_at=observed,
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        source_endpoint=expectation.base_url,
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(item.artifact_id for item in receipt.artifacts),
        local_cache_keys=tuple(f"sha256:{item.artifact_hash.value}" for item in receipt.artifacts),
    )
    manifest_payloads = (
        ReleaseManifestPayload(
            release_id=expectation.context_release_id,
            content=context_manifest_bytes,
        ),
        ReleaseManifestPayload(
            release_id=expectation.evidence_release_id,
            content=evidence_manifest_bytes,
        ),
    )
    artifact_payloads = tuple(
        ArtifactPayload(release_id=release_id, artifact_id=artifact_id, content=content)
        for (release_id, artifact_id), content in sorted(downloaded.items())
    )
    return Stage6BLivePreparedAdmission(
        preregistration=preregistration,
        request=request,
        receipt=receipt,
        closure=closure,
        fetch_observation=fetch_observation,
        manifest_payloads=manifest_payloads,
        artifact_payloads=artifact_payloads,
        stage3d_validation=stage3d,
        handoff_sha256=expectation.handoff_sha256,
    )


def _hash_file_bytes(content: bytes) -> HashDigest:
    return HashDigest(algorithm="sha256", value=sha256(content).hexdigest())


def execute_stage6b_live_validation(
    *,
    client: KBReadOnlyHTTPClient,
    store: Stage6BValidationStore,
    prepared: Stage6BLivePreparedAdmission,
    strategy_version: str,
    random_seed: int,
    clock: InjectedClock,
) -> Stage6BLiveValidationResult:
    """Open the fresh status window and publish one isolated validation seal."""

    admission = execute_stage6b_public_https_validation_admission(
        client,
        store,
        request=prepared.request,
        preregistration=prepared.preregistration,
        receipt=prepared.receipt,
        closure=prepared.closure,
        fetch_observation=prepared.fetch_observation,
        manifest_payloads=prepared.manifest_payloads,
        artifact_payloads=prepared.artifact_payloads,
        strategy_version=strategy_version,
        random_seed=random_seed,
        clock=clock,
    )
    return Stage6BLiveValidationResult(
        admission=admission,
        content_response_sha256=tuple(prepared.stage3d_validation.response_sha256.items()),
        content_artifact_sha256=tuple(prepared.stage3d_validation.artifact_sha256.items()),
        handoff_sha256=prepared.handoff_sha256,
    )


__all__ = [
    "Stage6BLivePreparedAdmission",
    "Stage6BLiveValidationError",
    "Stage6BLiveValidationResult",
    "execute_stage6b_live_validation",
    "prepare_stage6b_live_validation",
    "read_stage6b_credential_env",
]
