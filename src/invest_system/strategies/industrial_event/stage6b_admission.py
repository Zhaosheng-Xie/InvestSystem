"""Pure Stage 6B admission contracts and status-evidence issuer seam.

This module deliberately performs no filesystem, SQLite, or network I/O.  It
maps bytes already returned by the pinned read-only HTTP client into an opaque
status-evidence receipt, issues a complete-closure validation confirmation,
and closes the immutable admission envelope.  A separate validation store is
responsible for the approved seal-last transaction.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType
from typing import Any

from invest_system.canonical import canonical_json_bytes, format_utc, normalize_utc
from invest_system.consumption import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ProviderReleaseStatus,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    ReleaseStatusObservation,
    SchemaValidationResult,
)
from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.integrations.investment_research_kb.http_client import VerifiedHTTPDocument
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes as provider_canonical_json_bytes,
)
from invest_system.models import (
    CanonicalModel,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
)
from invest_system.retention import ReleaseRetentionClosure

from .stage6b_governance import (
    STAGE6_6B_APPROVAL_SCOPE,
    STAGE6_6B_AUTHORITY_CONTRACT_SHA256,
    STAGE6_6B_RULE_APPROVAL_ID,
    STAGE6_6B_RULE_APPROVAL_RECORD_SHA256,
    STAGE6_6B_RULE_BUNDLE_ID,
    STAGE6_6B_RULE_BUNDLE_SHA256,
    STAGE6_6B_RULE_BUNDLE_VERSION,
    STAGE6_STRATEGY_ID,
)

STAGE6B_ADMISSION_SCHEMA_VERSION = "0.1.0"
STAGE6B_CONFIRMATION_SCHEMA_VERSION = "1.0.0"
STAGE6B_AUTHORITY_ID = "kb_public_https_status_v1"
STAGE6B_AUTHORITY_ORIGIN = "https://82.157.112.120"
STAGE6B_STATUS_PATH_TEMPLATE = "/api/v1/dataset-releases/{release_id}/status"
STAGE6B_TRANSPORT_SNAPSHOT_SHA256 = (
    "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169"
)
STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE = timedelta(seconds=300)
STAGE6B_MAX_CLOCK_SKEW = timedelta(seconds=30)
STAGE6B_CONFIRMATION_TTL = timedelta(seconds=300)
STAGE6B_TRANSACTION_PROFILE = "stage6b_isolated_validation_seal_v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_STATUS_EVIDENCE_ISSUER = object()


class Stage6BAdmissionStatus(StrEnum):
    SEALED_VALIDATION_ONLY = "SEALED_VALIDATION_ONLY"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    STATUS_UNCONFIRMED = "STATUS_UNCONFIRMED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"
    IMMUTABLE_IDENTITY_CONFLICT = "IMMUTABLE_IDENTITY_CONFLICT"
    ATOMIC_COMMIT_BLOCKED = "ATOMIC_COMMIT_BLOCKED"
    AUDIT_REPLAY_ONLY = "AUDIT_REPLAY_ONLY"


class Stage6BAdmissionError(ValueError):
    """Stable fail-closed Stage 6B contract or issuer error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _require_id(field_name: str, value: str, *, exact_release: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical ASCII identifier")
    if exact_release and value.casefold() == "latest":
        raise ValueError(f"{field_name} must be exact, not latest")
    return value


def _require_bool(field_name: str, value: bool, *, expected: bool) -> None:
    if type(value) is not bool or value is not expected:
        raise ValueError(f"{field_name} must be {expected!r}")


def _digest(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _identity_hash(payload: Mapping[str, Any]) -> HashDigest:
    return _digest(sha256(canonical_json_bytes(payload)).hexdigest())


def _parse_canonical_utc(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not UTC")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not UTC") from exc
    if format_utc(parsed) != value:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not canonical UTC")
    return parsed


def _hash_value(value: Any, *, field_name: str) -> HashDigest:
    if not isinstance(value, dict) or set(value) != {"algorithm", "value"}:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", f"{field_name} is not a SHA-256 object"
        )
    try:
        return HashDigest(algorithm=value["algorithm"], value=value["value"])
    except (TypeError, ValueError) as exc:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", f"{field_name} is not a SHA-256 object"
        ) from exc


def _capability_hash(capability: ApprovedRuleCapability) -> HashDigest:
    return _digest(sha256(capability.to_canonical_bytes()).hexdigest())


def _require_stage6b_capability(capability: ApprovedRuleCapability) -> None:
    if not isinstance(capability, ApprovedRuleCapability):
        raise TypeError("capability must be an ApprovedRuleCapability")
    if (
        capability.strategy_id != STAGE6_STRATEGY_ID
        or capability.bundle_id != STAGE6_6B_RULE_BUNDLE_ID
        or capability.bundle_version != STAGE6_6B_RULE_BUNDLE_VERSION
        or capability.bundle_hash.value != STAGE6_6B_RULE_BUNDLE_SHA256
        or capability.approval_id != STAGE6_6B_RULE_APPROVAL_ID
        or capability.approval_record_hash.value != STAGE6_6B_RULE_APPROVAL_RECORD_SHA256
        or capability.approval_scope is not STAGE6_6B_APPROVAL_SCOPE
        or capability.rule_status is not RuleStatus.APPROVED
    ):
        raise Stage6BAdmissionError(
            "STAGE6B_CAPABILITY_MISMATCH",
            "admission requires the exact Stage 6B validation capability",
        )


@dataclass(frozen=True, slots=True)
class Stage6BStatusResponsePayload:
    """Non-canonical raw status bytes prepared for the IS content-addressed cache."""

    release_id: str
    content: bytes
    response_bytes_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("release_id", self.release_id, exact_release=True)
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("content must be non-empty bytes")
        if not isinstance(self.response_bytes_hash, HashDigest):
            raise TypeError("response_bytes_hash must be a HashDigest")
        if sha256(self.content).hexdigest() != self.response_bytes_hash.value:
            raise ValueError("response_bytes_hash differs from content")


def _status_evidence_identity(
    *,
    schema_version: str,
    evidence_id: str,
    strategy_input_ref: StrategyInputRef,
    status_observation_id: str,
    response_bytes_hash: HashDigest,
    status_event_id: str,
    status_event_hash: HashDigest,
    status_sequence: int,
    status_recorded_at: datetime,
    provider_snapshot_at: datetime,
    checked_at: datetime,
    authority_id: str,
    authority_contract_hash: HashDigest,
    transport_snapshot_hash: HashDigest,
    status: ProviderReleaseStatus,
    validation_only: bool,
    authority_eligible: bool,
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "evidence_id": evidence_id,
        "strategy_input_ref": strategy_input_ref,
        "status_observation_id": status_observation_id,
        "response_bytes_hash": response_bytes_hash,
        "status_event_id": status_event_id,
        "status_event_hash": status_event_hash,
        "status_sequence": status_sequence,
        "status": status,
        "status_recorded_at": status_recorded_at,
        "provider_snapshot_at": provider_snapshot_at,
        "checked_at": checked_at,
        "authority_id": authority_id,
        "authority_contract_hash": authority_contract_hash,
        "transport_snapshot_hash": transport_snapshot_hash,
        "validation_only": validation_only,
        "authority_eligible": authority_eligible,
    }


@dataclass(frozen=True, slots=True, init=False)
class Stage6BStatusEvidence(CanonicalModel):
    """Opaque proof that exact status response bytes closed to a published head."""

    schema_version: str
    evidence_id: str
    strategy_input_ref: StrategyInputRef
    status_observation_id: str
    response_bytes_hash: HashDigest
    status_event_id: str
    status_event_hash: HashDigest
    status_sequence: int
    status: ProviderReleaseStatus
    status_recorded_at: datetime
    provider_snapshot_at: datetime
    checked_at: datetime
    authority_id: str
    authority_contract_hash: HashDigest
    transport_snapshot_hash: HashDigest
    validation_only: bool
    authority_eligible: bool
    evidence_hash: HashDigest

    def __init__(
        self,
        *,
        _issuer: object,
        evidence_id: str,
        strategy_input_ref: StrategyInputRef,
        status_observation_id: str,
        response_bytes_hash: HashDigest,
        status_event_id: str,
        status_event_hash: HashDigest,
        status_sequence: int,
        status_recorded_at: datetime,
        provider_snapshot_at: datetime,
        checked_at: datetime,
    ) -> None:
        if _issuer is not _STATUS_EVIDENCE_ISSUER:
            raise Stage6BAdmissionError(
                "STATUS_EVIDENCE_ISSUER_INVALID",
                "status evidence must be derived from verified response bytes",
            )
        values: dict[str, Any] = {
            "schema_version": STAGE6B_ADMISSION_SCHEMA_VERSION,
            "evidence_id": _require_id("evidence_id", evidence_id),
            "strategy_input_ref": strategy_input_ref,
            "status_observation_id": _require_id("status_observation_id", status_observation_id),
            "response_bytes_hash": response_bytes_hash,
            "status_event_id": _require_id("status_event_id", status_event_id),
            "status_event_hash": status_event_hash,
            "status_sequence": status_sequence,
            "status": ProviderReleaseStatus.PUBLISHED,
            "status_recorded_at": normalize_utc(
                status_recorded_at, field_name="status_recorded_at"
            ),
            "provider_snapshot_at": normalize_utc(
                provider_snapshot_at, field_name="provider_snapshot_at"
            ),
            "checked_at": normalize_utc(checked_at, field_name="checked_at"),
            "authority_id": STAGE6B_AUTHORITY_ID,
            "authority_contract_hash": _digest(STAGE6_6B_AUTHORITY_CONTRACT_SHA256),
            "transport_snapshot_hash": _digest(STAGE6B_TRANSPORT_SNAPSHOT_SHA256),
            "validation_only": True,
            "authority_eligible": False,
        }
        if not isinstance(strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if not isinstance(response_bytes_hash, HashDigest) or not isinstance(
            status_event_hash, HashDigest
        ):
            raise TypeError("response and event hashes must be HashDigest values")
        if isinstance(status_sequence, bool) or not isinstance(status_sequence, int):
            raise TypeError("status_sequence must be an integer")
        if status_sequence < 1:
            raise ValueError("status_sequence must be positive")
        if values["status_recorded_at"] > values["provider_snapshot_at"]:
            raise Stage6BAdmissionError(
                "STATUS_PIT_INVALID", "status event postdates provider snapshot"
            )
        if values["provider_snapshot_at"] - values["checked_at"] > STAGE6B_MAX_CLOCK_SKEW:
            raise Stage6BAdmissionError(
                "STATUS_CLOCK_SKEW", "provider snapshot leads the consumer clock"
            )
        if values["checked_at"] - values["provider_snapshot_at"] > (
            STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE
        ):
            raise Stage6BAdmissionError("STATUS_STALE", "provider snapshot is stale")
        identity = _status_evidence_identity(**values)
        for name, value in values.items():
            object.__setattr__(self, name, value)
        object.__setattr__(self, "evidence_hash", _identity_hash(identity))

    @property
    def release_id(self) -> str:
        return self.strategy_input_ref.dataset_release_id

    def identity_payload(self) -> dict[str, Any]:
        return _status_evidence_identity(
            schema_version=self.schema_version,
            evidence_id=self.evidence_id,
            strategy_input_ref=self.strategy_input_ref,
            status_observation_id=self.status_observation_id,
            response_bytes_hash=self.response_bytes_hash,
            status_event_id=self.status_event_id,
            status_event_hash=self.status_event_hash,
            status_sequence=self.status_sequence,
            status_recorded_at=self.status_recorded_at,
            provider_snapshot_at=self.provider_snapshot_at,
            checked_at=self.checked_at,
            authority_id=self.authority_id,
            authority_contract_hash=self.authority_contract_hash,
            transport_snapshot_hash=self.transport_snapshot_hash,
            status=self.status,
            validation_only=self.validation_only,
            authority_eligible=self.authority_eligible,
        )


@dataclass(frozen=True, slots=True)
class Stage6BStatusEvidenceProjection:
    evidence: Stage6BStatusEvidence
    payload: Stage6BStatusResponsePayload
    observation: ReleaseStatusObservation


def project_stage6b_status_evidence(
    document: VerifiedHTTPDocument,
    *,
    strategy_input_ref: StrategyInputRef,
    checked_at: datetime,
    status_observation_id: str,
) -> Stage6BStatusEvidenceProjection:
    """Reverify one client response and project an opaque Stage 6B evidence receipt."""

    if not isinstance(document, VerifiedHTTPDocument):
        raise TypeError("document must be a VerifiedHTTPDocument")
    if not isinstance(strategy_input_ref, StrategyInputRef):
        raise TypeError("strategy_input_ref must be a StrategyInputRef")
    release_id = strategy_input_ref.dataset_release_id
    if (
        document.operation != "get_dataset_release_status_history"
        or document.release_id != release_id
        or document.request_path != STAGE6B_STATUS_PATH_TEMPLATE.format(release_id=release_id)
        or document.authority_eligible
    ):
        raise Stage6BAdmissionError(
            "STATUS_DOCUMENT_IDENTITY_MISMATCH",
            "verified HTTP document is not the exact zero-authority status response",
        )
    try:
        raw = json.loads(document.response_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", "status response is not UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {"meta", "data"}:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", "status response envelope differs")
    meta = raw["meta"]
    data = raw["data"]
    if not isinstance(meta, dict) or not isinstance(data, dict) or data != document.data:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", "status response data differs from verified document"
        )
    response_hash = sha256(document.response_bytes).hexdigest()
    if response_hash != document.response_sha256:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_HASH_MISMATCH", "status response bytes changed"
        )
    if (
        meta.get("release_id") != release_id
        or meta.get("request_id") != document.request_id
        or data.get("release_id") != release_id
        or meta.get("knowledge_cutoff") != format_utc(strategy_input_ref.knowledge_cutoff)
        or document.knowledge_cutoff != meta.get("knowledge_cutoff")
    ):
        raise Stage6BAdmissionError(
            "STATUS_DOCUMENT_IDENTITY_MISMATCH", "status response five-field identity differs"
        )
    events = data.get("events")
    head = data.get("current_status_event")
    if not isinstance(events, list) or not events or not isinstance(head, dict):
        raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status history is incomplete")
    previous_hash: str | None = None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status event is not an object")
        if event.get("release_id") != release_id or event.get("sequence") != sequence:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status sequence differs")
        previous = event.get("previous_event_hash")
        linked = (
            None
            if previous is None
            else _hash_value(previous, field_name="previous_event_hash").value
        )
        if linked != previous_hash:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status link differs")
        event_hash = _hash_value(event.get("event_hash"), field_name="event_hash")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if sha256(provider_canonical_json_bytes(unsigned)).hexdigest() != event_hash.value:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status self-hash differs")
        previous_hash = event_hash.value
    if head != events[-1] or head.get("status") != ProviderReleaseStatus.PUBLISHED.value:
        raise Stage6BAdmissionError("STATUS_NOT_PUBLISHED", "current status head must be published")
    checked = normalize_utc(checked_at, field_name="checked_at")
    provider_snapshot_at = _parse_canonical_utc(
        meta.get("generated_at"), field_name="meta.generated_at"
    )
    status_recorded_at = _parse_canonical_utc(
        head.get("recorded_at"), field_name="current_status_event.recorded_at"
    )
    status_event_hash = _hash_value(head.get("event_hash"), field_name="event_hash")
    evidence_identity = sha256(
        canonical_json_bytes(
            {
                "release_id": release_id,
                "status_observation_id": status_observation_id,
                "response_bytes_hash": response_hash,
                "checked_at": checked,
            }
        )
    ).hexdigest()
    evidence = Stage6BStatusEvidence(
        _issuer=_STATUS_EVIDENCE_ISSUER,
        evidence_id=f"status_evidence_{evidence_identity[:24]}",
        strategy_input_ref=strategy_input_ref,
        status_observation_id=status_observation_id,
        response_bytes_hash=_digest(response_hash),
        status_event_id=head["event_id"],
        status_event_hash=status_event_hash,
        status_sequence=head["sequence"],
        status_recorded_at=status_recorded_at,
        provider_snapshot_at=provider_snapshot_at,
        checked_at=checked,
    )
    previous = head.get("previous_event_hash")
    observation = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=status_observation_id,
        release_id=release_id,
        strategy_input_ref=strategy_input_ref,
        observed_at=checked,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.PUBLISHED,
        status_event_id=head["event_id"],
        status_event_hash=status_event_hash,
        previous_status_event_hash=(
            None if previous is None else _hash_value(previous, field_name="previous_event_hash")
        ),
        status_sequence=head["sequence"],
        status_recorded_at=status_recorded_at,
    )
    return Stage6BStatusEvidenceProjection(
        evidence=evidence,
        payload=Stage6BStatusResponsePayload(
            release_id=release_id,
            content=document.response_bytes,
            response_bytes_hash=_digest(response_hash),
        ),
        observation=observation,
    )


@dataclass(frozen=True, slots=True)
class Stage6BValidationPreregistration(CanonicalModel):
    schema_version: str
    preregistration_id: str
    frozen_at: datetime
    validation_only: bool
    not_historical_evidence: bool
    isolated_state_and_cache: bool
    preregistration_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6B_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported preregistration schema_version")
        _require_id("preregistration_id", self.preregistration_id)
        object.__setattr__(self, "frozen_at", normalize_utc(self.frozen_at, field_name="frozen_at"))
        _require_bool("validation_only", self.validation_only, expected=True)
        _require_bool("not_historical_evidence", self.not_historical_evidence, expected=True)
        _require_bool("isolated_state_and_cache", self.isolated_state_and_cache, expected=True)
        expected = _identity_hash(self.identity_payload())
        if not isinstance(self.preregistration_hash, HashDigest) or (
            self.preregistration_hash != expected
        ):
            raise ValueError("preregistration_hash differs")

    @classmethod
    def create(
        cls, *, preregistration_id: str, frozen_at: datetime
    ) -> Stage6BValidationPreregistration:
        normalized = normalize_utc(frozen_at, field_name="frozen_at")
        payload = {
            "schema_version": STAGE6B_ADMISSION_SCHEMA_VERSION,
            "preregistration_id": preregistration_id,
            "frozen_at": normalized,
            "validation_only": True,
            "not_historical_evidence": True,
            "isolated_state_and_cache": True,
        }
        return cls(
            schema_version=STAGE6B_ADMISSION_SCHEMA_VERSION,
            preregistration_id=preregistration_id,
            frozen_at=normalized,
            validation_only=True,
            not_historical_evidence=True,
            isolated_state_and_cache=True,
            preregistration_hash=_identity_hash(payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "preregistration_id": self.preregistration_id,
            "frozen_at": self.frozen_at,
            "validation_only": self.validation_only,
            "not_historical_evidence": self.not_historical_evidence,
            "isolated_state_and_cache": self.isolated_state_and_cache,
        }


@dataclass(frozen=True, slots=True)
class Stage6BHistoricalAdmissionRequest(CanonicalModel):
    schema_version: str
    request_id: str
    run_id: str
    strategy_id: str
    purpose: str
    strategy_input_ref: StrategyInputRef
    rule_bundle_hash: HashDigest
    approval_record_hash: HashDigest
    capability_hash: HashDigest
    code_commit: str
    runtime_environment_lock_hash: HashDigest
    semantic_config_hash: HashDigest
    injected_clock: datetime
    preregistration_hash: HashDigest
    transport_snapshot_hash: HashDigest
    authority_contract_hash: HashDigest
    validation_only: bool
    not_historical_evidence: bool
    isolated_state_and_cache: bool
    request_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6B_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported request schema_version")
        _require_id("request_id", self.request_id)
        _require_id("run_id", self.run_id)
        if self.strategy_id != STAGE6_STRATEGY_ID or self.purpose != "stage6b_validation_admission":
            raise ValueError("request scope differs")
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if _GIT_COMMIT_RE.fullmatch(self.code_commit) is None:
            raise ValueError("code_commit must be a full lowercase Git identity")
        for field_name in (
            "rule_bundle_hash",
            "approval_record_hash",
            "capability_hash",
            "runtime_environment_lock_hash",
            "semantic_config_hash",
            "preregistration_hash",
            "transport_snapshot_hash",
            "authority_contract_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        object.__setattr__(
            self, "injected_clock", normalize_utc(self.injected_clock, field_name="injected_clock")
        )
        _require_bool("validation_only", self.validation_only, expected=True)
        _require_bool("not_historical_evidence", self.not_historical_evidence, expected=True)
        _require_bool("isolated_state_and_cache", self.isolated_state_and_cache, expected=True)
        if self.rule_bundle_hash.value != STAGE6_6B_RULE_BUNDLE_SHA256 or (
            self.approval_record_hash.value != STAGE6_6B_RULE_APPROVAL_RECORD_SHA256
            or self.transport_snapshot_hash.value != STAGE6B_TRANSPORT_SNAPSHOT_SHA256
            or self.authority_contract_hash.value != STAGE6_6B_AUTHORITY_CONTRACT_SHA256
        ):
            raise Stage6BAdmissionError("REQUEST_IDENTITY_MISMATCH", "approved identity differs")
        expected = _identity_hash(self.identity_payload())
        if not isinstance(self.request_hash, HashDigest) or self.request_hash != expected:
            raise ValueError("request_hash differs")

    @classmethod
    def create(
        cls,
        *,
        request_id: str,
        run_id: str,
        strategy_input_ref: StrategyInputRef,
        capability: ApprovedRuleCapability,
        code_commit: str,
        runtime_environment_lock_hash: HashDigest,
        semantic_config_hash: HashDigest,
        injected_clock: datetime,
        preregistration: Stage6BValidationPreregistration,
    ) -> Stage6BHistoricalAdmissionRequest:
        _require_stage6b_capability(capability)
        if not isinstance(preregistration, Stage6BValidationPreregistration):
            raise TypeError("preregistration must be a Stage6BValidationPreregistration")
        normalized_clock = normalize_utc(injected_clock, field_name="injected_clock")
        if preregistration.frozen_at > normalized_clock:
            raise Stage6BAdmissionError(
                "PREREGISTRATION_FUTURE", "preregistration postdates the admission request"
            )
        payload = {
            "schema_version": STAGE6B_ADMISSION_SCHEMA_VERSION,
            "request_id": request_id,
            "run_id": run_id,
            "strategy_id": STAGE6_STRATEGY_ID,
            "purpose": "stage6b_validation_admission",
            "strategy_input_ref": strategy_input_ref,
            "rule_bundle_hash": capability.bundle_hash,
            "approval_record_hash": capability.approval_record_hash,
            "capability_hash": _capability_hash(capability),
            "code_commit": code_commit,
            "runtime_environment_lock_hash": runtime_environment_lock_hash,
            "semantic_config_hash": semantic_config_hash,
            "injected_clock": normalized_clock,
            "preregistration_hash": preregistration.preregistration_hash,
            "transport_snapshot_hash": _digest(STAGE6B_TRANSPORT_SNAPSHOT_SHA256),
            "authority_contract_hash": _digest(STAGE6_6B_AUTHORITY_CONTRACT_SHA256),
            "validation_only": True,
            "not_historical_evidence": True,
            "isolated_state_and_cache": True,
        }
        return cls(
            schema_version=STAGE6B_ADMISSION_SCHEMA_VERSION,
            request_id=request_id,
            run_id=run_id,
            strategy_id=STAGE6_STRATEGY_ID,
            purpose="stage6b_validation_admission",
            strategy_input_ref=strategy_input_ref,
            rule_bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            capability_hash=_capability_hash(capability),
            code_commit=code_commit,
            runtime_environment_lock_hash=runtime_environment_lock_hash,
            semantic_config_hash=semantic_config_hash,
            injected_clock=normalized_clock,
            preregistration_hash=preregistration.preregistration_hash,
            transport_snapshot_hash=_digest(STAGE6B_TRANSPORT_SNAPSHOT_SHA256),
            authority_contract_hash=_digest(STAGE6_6B_AUTHORITY_CONTRACT_SHA256),
            validation_only=True,
            not_historical_evidence=True,
            isolated_state_and_cache=True,
            request_hash=_identity_hash(payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_json_value().items() if key != "request_hash"}


@dataclass(frozen=True, slots=True)
class Stage6BRunReleaseStatusConfirmation(CanonicalModel):
    schema_version: str
    confirmation_id: str
    run_id: str
    root_release_id: str
    receipt_hash: HashDigest
    closure_hash: HashDigest
    capability_hash: HashDigest
    authority_id: str
    authority_contract_hash: HashDigest
    requested_at: datetime
    confirmed_at: datetime
    expires_at: datetime
    items: tuple[Stage6BStatusEvidence, ...]
    validation_only: bool
    authority_eligible: bool
    confirmation_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6B_CONFIRMATION_SCHEMA_VERSION:
            raise ValueError("unsupported confirmation schema_version")
        _require_id("confirmation_id", self.confirmation_id)
        _require_id("run_id", self.run_id)
        _require_id("root_release_id", self.root_release_id, exact_release=True)
        if self.authority_id != STAGE6B_AUTHORITY_ID or (
            self.authority_contract_hash.value != STAGE6_6B_AUTHORITY_CONTRACT_SHA256
        ):
            raise ValueError("confirmation authority differs")
        for field_name in ("receipt_hash", "closure_hash", "capability_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        for field_name in ("requested_at", "confirmed_at", "expires_at"):
            object.__setattr__(
                self, field_name, normalize_utc(getattr(self, field_name), field_name=field_name)
            )
        if self.requested_at > self.confirmed_at or (
            self.expires_at - self.confirmed_at != STAGE6B_CONFIRMATION_TTL
        ):
            raise ValueError("confirmation window differs")
        if not isinstance(self.items, (list, tuple)) or not self.items:
            raise ValueError("confirmation items must not be empty")
        if any(type(item) is not Stage6BStatusEvidence for item in self.items):
            raise TypeError("confirmation items must be issuer-created evidence")
        normalized = tuple(sorted(self.items, key=lambda item: item.release_id))
        if len({item.release_id for item in normalized}) != len(normalized):
            raise ValueError("confirmation release IDs must be unique")
        object.__setattr__(self, "items", normalized)
        if self.root_release_id not in {item.release_id for item in normalized}:
            raise ValueError("root release must be confirmed")
        if any(
            item.checked_at < self.requested_at or item.checked_at > self.confirmed_at
            for item in normalized
        ):
            raise ValueError("evidence checked_at is outside the confirmation window")
        _require_bool("validation_only", self.validation_only, expected=True)
        _require_bool("authority_eligible", self.authority_eligible, expected=False)
        expected = _identity_hash(self.identity_payload())
        if not isinstance(self.confirmation_hash, HashDigest) or self.confirmation_hash != expected:
            raise ValueError("confirmation_hash differs")

    def identity_payload(self) -> dict[str, Any]:
        return {
            key: value for key, value in self.to_json_value().items() if key != "confirmation_hash"
        }


def issue_stage6b_validation_confirmation(
    *,
    confirmation_id: str,
    request: Stage6BHistoricalAdmissionRequest,
    receipt: ArtifactConsumptionReceipt,
    closure: ReleaseRetentionClosure,
    evidences: Iterable[Stage6BStatusEvidence],
    confirmed_at: datetime,
) -> Stage6BRunReleaseStatusConfirmation:
    """Issue one complete-closure validation confirmation from opaque evidence."""

    if not isinstance(request, Stage6BHistoricalAdmissionRequest):
        raise TypeError("request must be a Stage6BHistoricalAdmissionRequest")
    if not isinstance(receipt, ArtifactConsumptionReceipt):
        raise TypeError("receipt must be an ArtifactConsumptionReceipt")
    if not isinstance(closure, ReleaseRetentionClosure):
        raise TypeError("closure must be a ReleaseRetentionClosure")
    if receipt.strategy_input_ref != request.strategy_input_ref or (
        closure.root_strategy_input_ref != request.strategy_input_ref
    ):
        raise Stage6BAdmissionError(
            "ROOT_INPUT_MISMATCH", "request, receipt, and closure root differ"
        )
    normalized = tuple(sorted(evidences, key=lambda item: item.release_id))
    if any(type(item) is not Stage6BStatusEvidence for item in normalized):
        raise TypeError("evidences must contain only issuer-created status evidence")
    closure_ids = tuple(node.release_id for node in closure.releases)
    if tuple(sorted(item.release_id for item in normalized)) != closure_ids:
        raise Stage6BAdmissionError(
            "CONFIRMATION_CLOSURE_MISMATCH", "evidence does not equal the complete closure"
        )
    refs = {node.release_id: node.strategy_input_ref for node in closure.releases}
    if any(item.strategy_input_ref != refs[item.release_id] for item in normalized):
        raise Stage6BAdmissionError(
            "CONFIRMATION_INPUT_REF_MISMATCH", "evidence five-field reference differs"
        )
    root_cutoff = closure.root_strategy_input_ref.knowledge_cutoff
    nodes = {node.release_id: node for node in closure.releases}
    for node in closure.releases:
        if node.knowledge_cutoff > root_cutoff or any(
            nodes[dependency].knowledge_cutoff > node.knowledge_cutoff
            for dependency in node.dependency_release_ids
        ):
            raise Stage6BAdmissionError(
                "CLOSURE_CUTOFF_INVALID", "source cutoff postdates its parent or root"
            )
    confirmed = normalize_utc(confirmed_at, field_name="confirmed_at")
    if any(
        confirmed - item.provider_snapshot_at > STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE
        or item.provider_snapshot_at - confirmed > STAGE6B_MAX_CLOCK_SKEW
        for item in normalized
    ):
        raise Stage6BAdmissionError(
            "STATUS_UNCONFIRMED", "status evidence is stale at confirmation"
        )
    payload = {
        "schema_version": STAGE6B_CONFIRMATION_SCHEMA_VERSION,
        "confirmation_id": confirmation_id,
        "run_id": request.run_id,
        "root_release_id": request.strategy_input_ref.dataset_release_id,
        "receipt_hash": receipt.receipt_hash,
        "closure_hash": closure.closure_hash,
        "capability_hash": request.capability_hash,
        "authority_id": STAGE6B_AUTHORITY_ID,
        "authority_contract_hash": request.authority_contract_hash,
        "requested_at": request.injected_clock,
        "confirmed_at": confirmed,
        "expires_at": confirmed + STAGE6B_CONFIRMATION_TTL,
        "items": normalized,
        "validation_only": True,
        "authority_eligible": False,
    }
    return Stage6BRunReleaseStatusConfirmation(
        schema_version=STAGE6B_CONFIRMATION_SCHEMA_VERSION,
        confirmation_id=confirmation_id,
        run_id=request.run_id,
        root_release_id=request.strategy_input_ref.dataset_release_id,
        receipt_hash=receipt.receipt_hash,
        closure_hash=closure.closure_hash,
        capability_hash=request.capability_hash,
        authority_id=STAGE6B_AUTHORITY_ID,
        authority_contract_hash=request.authority_contract_hash,
        requested_at=request.injected_clock,
        confirmed_at=confirmed,
        expires_at=confirmed + STAGE6B_CONFIRMATION_TTL,
        items=normalized,
        validation_only=True,
        authority_eligible=False,
        confirmation_hash=_identity_hash(payload),
    )


def _pin_artifact_keys(closure: ReleaseRetentionClosure) -> tuple[str, ...]:
    return tuple(
        sorted(
            f"{node.release_id}:{artifact.artifact_id}"
            for node in closure.releases
            for artifact in node.artifacts
        )
    )


@dataclass(frozen=True, slots=True)
class Stage6BHistoricalAdmissionEnvelope(CanonicalModel):
    schema_version: str
    request: Stage6BHistoricalAdmissionRequest
    preregistration: Stage6BValidationPreregistration
    receipt: ArtifactConsumptionReceipt
    closure: ReleaseRetentionClosure
    fetch_observation: ArtifactFetchObservation
    status_evidences: tuple[Stage6BStatusEvidence, ...]
    status_observations: tuple[ReleaseStatusObservation, ...]
    admission_observation: ReleaseAdmissionObservation
    manifest: StrategyRunManifest
    confirmation: Stage6BRunReleaseStatusConfirmation
    pin_release_ids: tuple[str, ...]
    pin_artifact_keys: tuple[str, ...]
    transaction_profile: str
    storage_schema_version: str
    code_commit: str
    validation_only: bool
    authority_eligible: bool
    strategy_evaluator_calls: int
    envelope_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6B_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported envelope schema_version")
        for field_name, expected_type in (
            ("request", Stage6BHistoricalAdmissionRequest),
            ("preregistration", Stage6BValidationPreregistration),
            ("receipt", ArtifactConsumptionReceipt),
            ("closure", ReleaseRetentionClosure),
            ("fetch_observation", ArtifactFetchObservation),
            ("admission_observation", ReleaseAdmissionObservation),
            ("manifest", StrategyRunManifest),
            ("confirmation", Stage6BRunReleaseStatusConfirmation),
        ):
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} has the wrong type")
        _require_bool("validation_only", self.validation_only, expected=True)
        _require_bool("authority_eligible", self.authority_eligible, expected=False)
        if self.strategy_evaluator_calls != 0:
            raise ValueError("strategy_evaluator_calls must be zero")
        if self.transaction_profile != STAGE6B_TRANSACTION_PROFILE or (
            self.storage_schema_version != "stage6b-validation-v1"
        ):
            raise ValueError("validation transaction profile differs")
        if self.code_commit != self.request.code_commit:
            raise ValueError("envelope code commit differs")
        expected = _identity_hash(self.identity_payload())
        if not isinstance(self.envelope_hash, HashDigest) or self.envelope_hash != expected:
            raise ValueError("envelope_hash differs")

    @classmethod
    def create(
        cls,
        *,
        request: Stage6BHistoricalAdmissionRequest,
        preregistration: Stage6BValidationPreregistration,
        receipt: ArtifactConsumptionReceipt,
        closure: ReleaseRetentionClosure,
        fetch_observation: ArtifactFetchObservation,
        status_evidences: Iterable[Stage6BStatusEvidence],
        status_observations: Iterable[ReleaseStatusObservation],
        admission_observation: ReleaseAdmissionObservation,
        manifest: StrategyRunManifest,
        confirmation: Stage6BRunReleaseStatusConfirmation,
    ) -> Stage6BHistoricalAdmissionEnvelope:
        if request.preregistration_hash != preregistration.preregistration_hash:
            raise Stage6BAdmissionError(
                "PREREGISTRATION_MISMATCH", "request preregistration differs"
            )
        if receipt.strategy_input_ref != request.strategy_input_ref or (
            closure.root_strategy_input_ref != request.strategy_input_ref
        ):
            raise Stage6BAdmissionError("ROOT_INPUT_MISMATCH", "root input differs")
        evidences = tuple(sorted(status_evidences, key=lambda item: item.release_id))
        observations = tuple(sorted(status_observations, key=lambda item: item.release_id))
        release_ids = tuple(node.release_id for node in closure.releases)
        if tuple(item.release_id for item in evidences) != release_ids or (
            tuple(item.release_id for item in observations) != release_ids
        ):
            raise Stage6BAdmissionError(
                "STATUS_CLOSURE_MISMATCH", "status evidence/observations differ from closure"
            )
        evidence_by_id = {item.status_observation_id: item for item in evidences}
        if set(evidence_by_id) != {item.observation_id for item in observations}:
            raise Stage6BAdmissionError(
                "STATUS_OBSERVATION_MISMATCH", "status evidence and observations differ"
            )
        for observation in observations:
            evidence = evidence_by_id[observation.observation_id]
            if not (
                observation.strategy_input_ref == evidence.strategy_input_ref
                and observation.schema_validation_result is SchemaValidationResult.PASSED
                and observation.status is ProviderReleaseStatus.PUBLISHED
                and observation.status_event_id == evidence.status_event_id
                and observation.status_event_hash == evidence.status_event_hash
                and observation.status_sequence == evidence.status_sequence
                and observation.status_recorded_at == evidence.status_recorded_at
                and observation.observed_at == evidence.checked_at
            ):
                raise Stage6BAdmissionError(
                    "STATUS_OBSERVATION_MISMATCH", "status observation projection differs"
                )
        if confirmation.items != evidences or not (
            confirmation.run_id == request.run_id
            and confirmation.receipt_hash == receipt.receipt_hash
            and confirmation.closure_hash == closure.closure_hash
            and confirmation.capability_hash == request.capability_hash
        ):
            raise Stage6BAdmissionError(
                "CONFIRMATION_MISMATCH", "confirmation differs from admission inputs"
            )
        root_id = request.strategy_input_ref.dataset_release_id
        root_evidence = next(item for item in evidences if item.release_id == root_id)
        if not (
            fetch_observation.release_id == root_id
            and fetch_observation.strategy_input_ref == request.strategy_input_ref
            and fetch_observation.receipt_hash == receipt.receipt_hash
            and fetch_observation.schema_validation_result is SchemaValidationResult.PASSED
            and fetch_observation.artifact_ids
            == tuple(item.artifact_id for item in receipt.artifacts)
            and admission_observation.release_id == root_id
            and admission_observation.strategy_input_ref == request.strategy_input_ref
            and admission_observation.status_observation_id == root_evidence.status_observation_id
            and admission_observation.admission_status is ReleaseAdmissionStatus.AUTHORIZED
        ):
            raise Stage6BAdmissionError(
                "ROOT_OBSERVATION_MISMATCH", "root observations do not close admission"
            )
        if not (
            manifest.run_id == request.run_id
            and manifest.strategy_id == STAGE6_STRATEGY_ID
            and manifest.strategy_input_ref == request.strategy_input_ref
            and manifest.input_envelope_hash == request.request_hash
            and manifest.artifact_consumption_receipt_hash == receipt.receipt_hash
            and manifest.artifact_fetch_observation_id == fetch_observation.observation_id
            and manifest.release_status_observation_id == root_evidence.status_observation_id
            and manifest.release_admission_observation_id == admission_observation.observation_id
            and manifest.rule_status is RuleStatus.APPROVED
            and manifest.rule_bundle_id == STAGE6_6B_RULE_BUNDLE_ID
            and manifest.rule_bundle_version == STAGE6_6B_RULE_BUNDLE_VERSION
            and manifest.rule_bundle_hash.value == STAGE6_6B_RULE_BUNDLE_SHA256
            and manifest.rule_approval_id == STAGE6_6B_RULE_APPROVAL_ID
            and manifest.rule_approval_record_hash is not None
            and manifest.rule_approval_record_hash.value == STAGE6_6B_RULE_APPROVAL_RECORD_SHA256
            and manifest.rule_approval_scope == STAGE6_6B_APPROVAL_SCOPE.value
            and manifest.code_commit == request.code_commit
            and manifest.config_hash == request.semantic_config_hash
            and manifest.runtime_environment_lock_hash == request.runtime_environment_lock_hash
            and manifest.run_mode is RunMode.RESEARCH
            and manifest.input_path == "stage6b_validation"
            and manifest.synthetic is False
            and manifest.validation_only is True
            and manifest.not_a_published_release is False
            and manifest.not_strategy_evidence is True
            and manifest.authorizes_positions is False
            and manifest.authorizes_orders is False
        ):
            raise Stage6BAdmissionError(
                "MANIFEST_MISMATCH", "StrategyRunManifest differs from the validation admission"
            )
        if not (
            fetch_observation.observed_at <= request.injected_clock
            and request.injected_clock <= root_evidence.checked_at
            and root_evidence.checked_at <= admission_observation.observed_at
            and admission_observation.observed_at <= manifest.created_at
            and confirmation.confirmed_at <= manifest.created_at
            and manifest.created_at <= confirmation.expires_at
        ):
            raise Stage6BAdmissionError(
                "ADMISSION_PIT_MISMATCH", "admission artifacts violate the PIT sequence"
            )
        payload = {
            "schema_version": STAGE6B_ADMISSION_SCHEMA_VERSION,
            "request": request,
            "preregistration": preregistration,
            "receipt": receipt,
            "closure": closure,
            "fetch_observation": fetch_observation,
            "status_evidences": evidences,
            "status_observations": observations,
            "admission_observation": admission_observation,
            "manifest": manifest,
            "confirmation": confirmation,
            "pin_release_ids": release_ids,
            "pin_artifact_keys": _pin_artifact_keys(closure),
            "transaction_profile": STAGE6B_TRANSACTION_PROFILE,
            "storage_schema_version": "stage6b-validation-v1",
            "code_commit": request.code_commit,
            "validation_only": True,
            "authority_eligible": False,
            "strategy_evaluator_calls": 0,
        }
        return cls(
            schema_version=STAGE6B_ADMISSION_SCHEMA_VERSION,
            request=request,
            preregistration=preregistration,
            receipt=receipt,
            closure=closure,
            fetch_observation=fetch_observation,
            status_evidences=evidences,
            status_observations=observations,
            admission_observation=admission_observation,
            manifest=manifest,
            confirmation=confirmation,
            pin_release_ids=release_ids,
            pin_artifact_keys=_pin_artifact_keys(closure),
            transaction_profile=STAGE6B_TRANSACTION_PROFILE,
            storage_schema_version="stage6b-validation-v1",
            code_commit=request.code_commit,
            validation_only=True,
            authority_eligible=False,
            strategy_evaluator_calls=0,
            envelope_hash=_identity_hash(payload),
        )

    def identity_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_json_value().items() if key != "envelope_hash"}


def stage6b_status_response_payloads(
    projections: Iterable[Stage6BStatusEvidenceProjection],
) -> Mapping[str, Stage6BStatusResponsePayload]:
    """Return an immutable release-keyed complete payload set for CAS preparation."""

    values = tuple(projections)
    by_release = {item.evidence.release_id: item.payload for item in values}
    if len(by_release) != len(values) or any(
        projection.payload.release_id != projection.evidence.release_id
        or projection.payload.response_bytes_hash != projection.evidence.response_bytes_hash
        for projection in values
    ):
        raise Stage6BAdmissionError(
            "STATUS_PAYLOAD_SET_INVALID", "status payload/evidence set differs"
        )
    return MappingProxyType(dict(sorted(by_release.items())))
