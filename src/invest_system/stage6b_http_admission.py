"""Public-HTTPS Stage 6B validation admission orchestration.

All public status reads finish before the validation store begins its SQLite
transaction.  The orchestration constructs observations, confirmation, and
manifest from verified response bytes; it never calls a strategy evaluator.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from invest_system.canonical import canonical_json_bytes, normalize_utc
from invest_system.consumption import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
)
from invest_system.integrations.investment_research_kb.http_client import (
    KBHTTPClientError,
    KBReadOnlyHTTPClient,
)
from invest_system.integrations.investment_research_kb.stage6b_status import (
    project_stage6b_status_evidence,
)
from invest_system.integrations.investment_research_kb.transport_contracts import (
    TRANSPORT_SOURCE_COMMIT,
)
from invest_system.models import (
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
)
from invest_system.retention import (
    ArtifactPayload,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    STAGE6B_AUTHORITY_ORIGIN,
    STAGE6B_TRANSPORT_SNAPSHOT_SHA256,
    Stage6BAdmissionError,
    Stage6BHistoricalAdmissionEnvelope,
    Stage6BHistoricalAdmissionRequest,
    Stage6BStatusEvidenceProjection,
    Stage6BStatusResponsePayload,
    Stage6BValidationPreregistration,
    issue_stage6b_validation_confirmation,
)
from invest_system.strategies.industrial_event.stage6b_governance import (
    STAGE6_6B_APPROVAL_SCOPE,
    STAGE6_6B_RULE_APPROVAL_ID,
    STAGE6_6B_RULE_BUNDLE_ID,
    STAGE6_6B_RULE_BUNDLE_VERSION,
    STAGE6_STRATEGY_ID,
)
from invest_system.strategies.industrial_event.stage6b_validation_store import (
    Stage6BHistoricalRunAdmissionSeal,
    Stage6BValidationStore,
)

type InjectedClock = Callable[[], datetime]


@dataclass(frozen=True, slots=True)
class Stage6BHTTPValidationAdmissionResult:
    """Non-authoritative receipt for one public-HTTPS validation seal."""

    seal: Stage6BHistoricalRunAdmissionSeal
    envelope: Stage6BHistoricalAdmissionEnvelope
    response_sha256_by_release: tuple[tuple[str, str], ...]
    public_https_calls: int
    validation_only: bool
    authority_eligible: bool
    strategy_evaluator_calls: int

    def __post_init__(self) -> None:
        if not isinstance(self.seal, Stage6BHistoricalRunAdmissionSeal) or not isinstance(
            self.envelope, Stage6BHistoricalAdmissionEnvelope
        ):
            raise TypeError("result seal/envelope types differ")
        if self.seal.envelope_hash != self.envelope.envelope_hash:
            raise ValueError("result seal/envelope identity differs")
        values = tuple(sorted(self.response_sha256_by_release))
        if not values or len({release_id for release_id, _ in values}) != len(values):
            raise ValueError("response SHA set must equal unique closure releases")
        if any(len(value) != 64 for _, value in values):
            raise ValueError("response SHA must be SHA-256")
        object.__setattr__(self, "response_sha256_by_release", values)
        if self.public_https_calls != len(values):
            raise ValueError("public HTTPS call count differs from response set")
        if type(self.validation_only) is not bool or not self.validation_only:
            raise ValueError("result must be validation-only")
        if type(self.authority_eligible) is not bool or self.authority_eligible:
            raise ValueError("result must not be authority eligible")
        if self.strategy_evaluator_calls != 0:
            raise ValueError("strategy_evaluator_calls must be zero")


def _derived_id(prefix: str, *, run_id: str, release_id: str | None = None) -> str:
    digest = sha256(
        canonical_json_bytes(
            {
                "prefix": prefix,
                "run_id": run_id,
                "release_id": release_id,
            }
        )
    ).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _clock_now(clock: InjectedClock, *, field_name: str) -> datetime:
    value = clock()
    return normalize_utc(value, field_name=field_name)


def fetch_stage6b_closure_status_evidence(
    client: KBReadOnlyHTTPClient,
    *,
    request: Stage6BHistoricalAdmissionRequest,
    closure: ReleaseRetentionClosure,
    clock: InjectedClock,
) -> tuple[Stage6BStatusEvidenceProjection, ...]:
    """Fetch every closure status over the exact approved public HTTPS origin."""

    if not isinstance(client, KBReadOnlyHTTPClient):
        raise TypeError("client must be a KBReadOnlyHTTPClient")
    if not isinstance(request, Stage6BHistoricalAdmissionRequest):
        raise TypeError("request must be a Stage6BHistoricalAdmissionRequest")
    if not isinstance(closure, ReleaseRetentionClosure):
        raise TypeError("closure must be a ReleaseRetentionClosure")
    if closure.root_strategy_input_ref != request.strategy_input_ref:
        raise Stage6BAdmissionError("ROOT_INPUT_MISMATCH", "request and closure root differ")
    if (
        client.base_url != STAGE6B_AUTHORITY_ORIGIN
        or client.contract_snapshot_lock_sha256 != STAGE6B_TRANSPORT_SNAPSHOT_SHA256
        or client.contract_source_commit != TRANSPORT_SOURCE_COMMIT
    ):
        raise Stage6BAdmissionError(
            "PRECHECK_BLOCKED", "HTTP client authority or transport identity differs"
        )
    projections: list[Stage6BStatusEvidenceProjection] = []
    for node in closure.releases:
        try:
            document = client.get_status_history(node.release_id)
        except KBHTTPClientError as exc:
            raise Stage6BAdmissionError(
                "STATUS_UNCONFIRMED", f"public status read failed for {node.release_id}"
            ) from exc
        projections.append(
            project_stage6b_status_evidence(
                document,
                strategy_input_ref=node.strategy_input_ref,
                checked_at=_clock_now(clock, field_name="status_checked_at"),
                status_observation_id=_derived_id(
                    "stage6b_status", run_id=request.run_id, release_id=node.release_id
                ),
            )
        )
    return tuple(sorted(projections, key=lambda item: item.evidence.release_id))


def execute_stage6b_public_https_validation_admission(
    client: KBReadOnlyHTTPClient,
    store: Stage6BValidationStore,
    *,
    request: Stage6BHistoricalAdmissionRequest,
    preregistration: Stage6BValidationPreregistration,
    receipt: ArtifactConsumptionReceipt,
    closure: ReleaseRetentionClosure,
    fetch_observation: ArtifactFetchObservation,
    manifest_payloads: Iterable[ReleaseManifestPayload],
    artifact_payloads: Iterable[ArtifactPayload],
    strategy_version: str,
    random_seed: int,
    clock: InjectedClock,
) -> Stage6BHTTPValidationAdmissionResult:
    """Fetch, reconcile, and seal one isolated Stage 6B validation admission."""

    if not isinstance(store, Stage6BValidationStore):
        raise TypeError("store must be a Stage6BValidationStore")
    projections = fetch_stage6b_closure_status_evidence(
        client,
        request=request,
        closure=closure,
        clock=clock,
    )
    confirmed_at = _clock_now(clock, field_name="confirmed_at")
    confirmation = issue_stage6b_validation_confirmation(
        confirmation_id=_derived_id("stage6b_confirmation", run_id=request.run_id),
        request=request,
        receipt=receipt,
        closure=closure,
        evidences=tuple(item.evidence for item in projections),
        confirmed_at=confirmed_at,
    )
    root_release_id = request.strategy_input_ref.dataset_release_id
    root_projection = next(
        item for item in projections if item.evidence.release_id == root_release_id
    )
    admission_observed_at = _clock_now(clock, field_name="admission_observed_at")
    admission_observation = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=_derived_id("stage6b_admission", run_id=request.run_id),
        release_id=root_release_id,
        strategy_input_ref=request.strategy_input_ref,
        observed_at=admission_observed_at,
        status_observation_id=root_projection.observation.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
    )
    manifest_created_at = _clock_now(clock, field_name="manifest_created_at")
    manifest = StrategyRunManifest(
        strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        run_id=request.run_id,
        created_at=manifest_created_at,
        strategy_id=STAGE6_STRATEGY_ID,
        strategy_version=strategy_version,
        code_commit=request.code_commit,
        rule_bundle_id=STAGE6_6B_RULE_BUNDLE_ID,
        rule_bundle_version=STAGE6_6B_RULE_BUNDLE_VERSION,
        rule_bundle_hash=request.rule_bundle_hash,
        rule_status=RuleStatus.APPROVED,
        rule_approval_id=STAGE6_6B_RULE_APPROVAL_ID,
        rule_approval_record_hash=request.approval_record_hash,
        rule_approval_scope=STAGE6_6B_APPROVAL_SCOPE.value,
        config_hash=request.semantic_config_hash,
        strategy_input_ref=request.strategy_input_ref,
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
        release_status_observation_id=root_projection.observation.observation_id,
        release_admission_observation_id=admission_observation.observation_id,
        random_seed=random_seed,
        run_mode=RunMode.RESEARCH,
        runtime_environment_lock_hash=request.runtime_environment_lock_hash,
    )
    envelope = Stage6BHistoricalAdmissionEnvelope.create(
        request=request,
        preregistration=preregistration,
        receipt=receipt,
        closure=closure,
        fetch_observation=fetch_observation,
        status_evidences=tuple(item.evidence for item in projections),
        status_observations=tuple(item.observation for item in projections),
        admission_observation=admission_observation,
        manifest=manifest,
        confirmation=confirmation,
    )
    status_payloads: Mapping[str, Stage6BStatusResponsePayload] = {
        item.evidence.release_id: item.payload for item in projections
    }
    seal = store.commit_validation_admission(
        envelope,
        manifest_payloads=manifest_payloads,
        artifact_payloads=artifact_payloads,
        status_payloads=status_payloads,
        committed_at=_clock_now(clock, field_name="committed_at"),
    )
    return Stage6BHTTPValidationAdmissionResult(
        seal=seal,
        envelope=envelope,
        response_sha256_by_release=tuple(
            (item.evidence.release_id, item.evidence.response_bytes_hash.value)
            for item in projections
        ),
        public_https_calls=len(projections),
        validation_only=True,
        authority_eligible=False,
        strategy_evaluator_calls=0,
    )
