"""Fail-closed pre-engine orchestration for Stage 2B failure injections.

The normal strategy engine must never see an input that failed Release,
schema, PIT, synthetic-provenance, decimal, or rule-governance checks.  This
module turns an exact, registered failure-injection payload into an immutable
run-failure audit and deliberately does not invoke the supplied strategy
evaluator.

The sparse payloads handled here are InvestSystem-owned synthetic validation
fixtures.  They are not KB Releases and do not replace the Stage 2A provider
admission/storage path.  Existing Stage 2A value objects are reused where the
fixture expresses the same contract (hash identity and provider status).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import JsonValue, freeze_json, normalize_utc
from invest_system.consumption import ProviderReleaseStatus
from invest_system.domain.rule_approval import ApprovedRuleCapability, RuleBundleDocument
from invest_system.domain.synthetic_fixture import (
    FailureInjectionFixtureRegistration,
    SyntheticFixtureRegistry,
)
from invest_system.models import CanonicalModel, DecisionState, HashDigest

from .rules import INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256

STAGE2B_RUN_FAILURE_AUDIT_SCHEMA_VERSION = "0.1.0-draft"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_STRING_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_HEX_64_RE = re.compile(r"^[0-9a-f]{64}$")


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _required_string(payload: Mapping[str, JsonValue], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_PAYLOAD_INVALID",
            f"{field_name} must be a non-empty string",
        )
    return value


def _required_mapping(payload: Mapping[str, JsonValue], field_name: str) -> Mapping[str, JsonValue]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_PAYLOAD_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _parse_utc(value: str, *, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith("Z") else value)
    except ValueError as exc:
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_PAYLOAD_INVALID",
            f"{field_name} must be an RFC 3339 timestamp",
        ) from exc
    return normalize_utc(parsed, field_name=field_name)


def _hash_from_text(value: str, *, field_name: str) -> HashDigest:
    if _HEX_64_RE.fullmatch(value) is None:
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_PAYLOAD_INVALID",
            f"{field_name} must be a lowercase SHA-256 digest",
        )
    return HashDigest(algorithm="sha256", value=value)


class Stage2BPreEngineAdmissionError(ValueError):
    """Stable fail-closed error for an invalid failure-injection definition."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class Stage2BFailureLayer(StrEnum):
    STAGE2A_ADMISSION = "stage2a_admission"
    STAGE2A_VALIDATION = "stage2a_validation"
    PIT_VALIDATION = "pit_validation"
    SYNTHETIC_INPUT_VALIDATION = "synthetic_input_validation"
    RULE_GOVERNANCE = "rule_governance"


class Stage2BBlockerCode(StrEnum):
    MANIFEST_HASH_MISMATCH = "MANIFEST_HASH_MISMATCH"
    RELEASE_WITHDRAWN = "RELEASE_WITHDRAWN"
    SCHEMA_UNSUPPORTED = "SCHEMA_UNSUPPORTED"
    PIT_VIOLATION = "PIT_VIOLATION"
    STRATEGY_USABLE_AT_AFTER_DECISION = "STRATEGY_USABLE_AT_AFTER_DECISION"
    DECIMAL_STRING_REQUIRED = "DECIMAL_STRING_REQUIRED"
    DECIMAL_STRING_NONCANONICAL = "DECIMAL_STRING_NONCANONICAL"
    SYNTHETIC_INPUT_AUTHORITY_FORBIDDEN = "SYNTHETIC_INPUT_AUTHORITY_FORBIDDEN"
    SYNTHETIC_FACT_PROVENANCE_MISSING = "SYNTHETIC_FACT_PROVENANCE_MISSING"
    RULE_BUNDLE_HASH_NOT_APPROVED = "RULE_BUNDLE_HASH_NOT_APPROVED"


@dataclass(frozen=True, slots=True)
class Stage2BFailureInjectionRequest(CanonicalModel):
    """One exact failure-injection attempt presented to the pre-engine boundary."""

    failure_audit_id: str
    case_id: str
    fixture_version: str
    observed_at: datetime
    failure_payload: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        _require_id("failure_audit_id", self.failure_audit_id)
        _require_id("case_id", self.case_id)
        if not isinstance(self.fixture_version, str) or not self.fixture_version:
            raise ValueError("fixture_version must be a non-empty string")
        object.__setattr__(
            self,
            "observed_at",
            normalize_utc(self.observed_at, field_name="observed_at"),
        )
        if not isinstance(self.failure_payload, Mapping):
            raise TypeError("failure_payload must be a mapping")
        frozen = freeze_json(self.failure_payload, path="$.failure_payload")
        if not isinstance(frozen, Mapping):
            raise TypeError("failure_payload must freeze to a mapping")
        object.__setattr__(self, "failure_payload", frozen)

    @property
    def fixture_id(self) -> str:
        return _required_string(self.failure_payload, "fixture_id")


@dataclass(frozen=True, slots=True)
class Stage2BRunFailureAudit(CanonicalModel):
    """Immutable audit emitted instead of a normal run Manifest or decision."""

    failure_audit_id: str
    case_id: str
    fixture_id: str
    fixture_version: str
    dataset_release_id: str
    input_id: str
    failed_at: datetime
    failure_layer: Stage2BFailureLayer
    blocker_code: Stage2BBlockerCode
    fixture_registration_id: str
    fixture_registration_hash: HashDigest
    fixture_registry_snapshot_hash: HashDigest
    failure_payload_hash: HashDigest
    schema_version: str = field(
        default=STAGE2B_RUN_FAILURE_AUDIT_SCHEMA_VERSION,
        init=False,
    )
    decision_state: DecisionState = field(default=DecisionState.BLOCKED, init=False)
    strategy_evaluator_calls: int = field(default=0, init=False)
    normal_strategy_run_manifest_created: bool = field(default=False, init=False)
    decision_record_created: bool = field(default=False, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "failure_audit_id",
            "case_id",
            "fixture_id",
            "dataset_release_id",
            "input_id",
            "fixture_registration_id",
        ):
            _require_id(field_name, getattr(self, field_name))
        if not isinstance(self.fixture_version, str) or not self.fixture_version:
            raise ValueError("fixture_version must be a non-empty string")
        object.__setattr__(
            self,
            "failed_at",
            normalize_utc(self.failed_at, field_name="failed_at"),
        )
        try:
            layer = (
                self.failure_layer
                if isinstance(self.failure_layer, Stage2BFailureLayer)
                else Stage2BFailureLayer(self.failure_layer)
            )
            blocker = (
                self.blocker_code
                if isinstance(self.blocker_code, Stage2BBlockerCode)
                else Stage2BBlockerCode(self.blocker_code)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("failure layer or blocker code is unsupported") from exc
        object.__setattr__(self, "failure_layer", layer)
        object.__setattr__(self, "blocker_code", blocker)
        for field_name in (
            "fixture_registration_hash",
            "fixture_registry_snapshot_hash",
            "failure_payload_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")


@dataclass(frozen=True, slots=True)
class Stage2BPreEngineBlockedResult:
    """Explicit short-circuit result; normal run artifacts cannot be attached."""

    failure_audit: Stage2BRunFailureAudit
    strategy_evaluator_calls: int = field(default=0, init=False)
    strategy_run_manifest: None = field(default=None, init=False)
    decision_record: None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.failure_audit, Stage2BRunFailureAudit):
            raise TypeError("failure_audit must be a Stage2BRunFailureAudit")


def _detect_blocker(
    payload: Mapping[str, JsonValue],
    *,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
) -> tuple[Stage2BFailureLayer, Stage2BBlockerCode] | None:
    if "declared_manifest_hash" in payload or "actual_manifest_hash" in payload:
        declared = _hash_from_text(
            _required_string(payload, "declared_manifest_hash"),
            field_name="declared_manifest_hash",
        )
        actual = _hash_from_text(
            _required_string(payload, "actual_manifest_hash"),
            field_name="actual_manifest_hash",
        )
        if declared != actual:
            return (
                Stage2BFailureLayer.STAGE2A_ADMISSION,
                Stage2BBlockerCode.MANIFEST_HASH_MISMATCH,
            )

    if "provider_current_status" in payload:
        try:
            status = ProviderReleaseStatus(_required_string(payload, "provider_current_status"))
        except ValueError as exc:
            raise Stage2BPreEngineAdmissionError(
                "FAILURE_INJECTION_PAYLOAD_INVALID",
                "provider_current_status is unsupported",
            ) from exc
        if status is ProviderReleaseStatus.WITHDRAWN:
            return (
                Stage2BFailureLayer.STAGE2A_ADMISSION,
                Stage2BBlockerCode.RELEASE_WITHDRAWN,
            )

    if "release_manifest_schema_version" in payload:
        requested = _required_string(payload, "release_manifest_schema_version")
        supported = payload.get("supported_release_manifest_schema_versions")
        if not isinstance(supported, tuple) or any(
            not isinstance(item, str) or not item for item in supported
        ):
            raise Stage2BPreEngineAdmissionError(
                "FAILURE_INJECTION_PAYLOAD_INVALID",
                "supported_release_manifest_schema_versions must be a string array",
            )
        if requested not in supported:
            return (
                Stage2BFailureLayer.STAGE2A_VALIDATION,
                Stage2BBlockerCode.SCHEMA_UNSUPPORTED,
            )

    if "fact_available_at" in payload or "knowledge_cutoff" in payload:
        available_at = _parse_utc(
            _required_string(payload, "fact_available_at"),
            field_name="fact_available_at",
        )
        knowledge_cutoff = _parse_utc(
            _required_string(payload, "knowledge_cutoff"),
            field_name="knowledge_cutoff",
        )
        if available_at > knowledge_cutoff:
            return Stage2BFailureLayer.PIT_VALIDATION, Stage2BBlockerCode.PIT_VIOLATION

    if "strategy_reviewed_at" in payload:
        available_at = _parse_utc(
            _required_string(payload, "available_at"),
            field_name="available_at",
        )
        reviewed_at = _parse_utc(
            _required_string(payload, "strategy_reviewed_at"),
            field_name="strategy_reviewed_at",
        )
        decision_at = _parse_utc(
            _required_string(payload, "decision_at"),
            field_name="decision_at",
        )
        strategy_usable_at = max(available_at, reviewed_at)
        if strategy_usable_at > decision_at:
            return (
                Stage2BFailureLayer.PIT_VALIDATION,
                Stage2BBlockerCode.STRATEGY_USABLE_AT_AFTER_DECISION,
            )

    if "materialization_instruction" in payload:
        instruction = _required_mapping(payload, "materialization_instruction")
        replacement_type = _required_string(instruction, "replacement_json_type")
        if replacement_type != "string":
            return (
                Stage2BFailureLayer.SYNTHETIC_INPUT_VALIDATION,
                Stage2BBlockerCode.DECIMAL_STRING_REQUIRED,
            )

    if "replacement_value" in payload:
        replacement = payload.get("replacement_value")
        if not isinstance(replacement, str):
            return (
                Stage2BFailureLayer.SYNTHETIC_INPUT_VALIDATION,
                Stage2BBlockerCode.DECIMAL_STRING_REQUIRED,
            )
        if _DECIMAL_STRING_RE.fullmatch(replacement) is None:
            return (
                Stage2BFailureLayer.SYNTHETIC_INPUT_VALIDATION,
                Stage2BBlockerCode.DECIMAL_STRING_NONCANONICAL,
            )

    if "authorizes_orders" in payload or "validation_only" in payload:
        if payload.get("validation_only") is not True or payload.get("authorizes_orders") is True:
            return (
                Stage2BFailureLayer.SYNTHETIC_INPUT_VALIDATION,
                Stage2BBlockerCode.SYNTHETIC_INPUT_AUTHORITY_FORBIDDEN,
            )

    if "fact_metadata" in payload:
        metadata = _required_mapping(payload, "fact_metadata")
        if (
            metadata.get("synthetic") is not True
            or metadata.get("not_a_published_release") is not True
        ):
            return (
                Stage2BFailureLayer.SYNTHETIC_INPUT_VALIDATION,
                Stage2BBlockerCode.SYNTHETIC_FACT_PROVENANCE_MISSING,
            )

    if "unknown_bundle_hash" in payload:
        unknown_hash = _hash_from_text(
            _required_string(payload, "unknown_bundle_hash"),
            field_name="unknown_bundle_hash",
        )
        identity_matches = (
            _required_string(payload, "bundle_id")
            == rule_document.bundle_id
            == approval_capability.bundle_id
            and _required_string(payload, "bundle_version")
            == rule_document.bundle_version
            == approval_capability.bundle_version
        )
        approved_document_matches = rule_document.bundle_hash() == approval_capability.bundle_hash
        if (
            identity_matches
            and approved_document_matches
            and unknown_hash != (approval_capability.bundle_hash)
        ):
            return (
                Stage2BFailureLayer.RULE_GOVERNANCE,
                Stage2BBlockerCode.RULE_BUNDLE_HASH_NOT_APPROVED,
            )

    return None


def _audit_from_registration(
    request: Stage2BFailureInjectionRequest,
    registration: FailureInjectionFixtureRegistration,
    *,
    registry: SyntheticFixtureRegistry,
    layer: Stage2BFailureLayer,
    blocker: Stage2BBlockerCode,
) -> Stage2BRunFailureAudit:
    return Stage2BRunFailureAudit(
        failure_audit_id=request.failure_audit_id,
        case_id=request.case_id,
        fixture_id=registration.fixture_id,
        fixture_version=registration.fixture_version,
        dataset_release_id=registration.dataset_release_id,
        input_id=registration.input_id,
        failed_at=request.observed_at,
        failure_layer=layer,
        blocker_code=blocker,
        fixture_registration_id=registration.registration_id,
        fixture_registration_hash=HashDigest(
            algorithm="sha256",
            value=registration.canonical_sha256(),
        ),
        fixture_registry_snapshot_hash=registry.snapshot_hash,
        failure_payload_hash=registration.failure_payload_hash,
    )


def orchestrate_stage2b_failure_injection(
    request: Stage2BFailureInjectionRequest,
    *,
    registry: SyntheticFixtureRegistry,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
    strategy_evaluator: Callable[[], Any],
    failure_audit_sink: Callable[[Stage2BRunFailureAudit], None] | None = None,
) -> Stage2BPreEngineBlockedResult:
    """Block one exact failure fixture before the strategy callback can run.

    ``strategy_evaluator`` is intentionally injected at this orchestration
    boundary so acceptance tests and callers can prove the short circuit.  It
    is never called for a registered failure-injection request.
    """

    if not isinstance(request, Stage2BFailureInjectionRequest):
        raise TypeError("request must be a Stage2BFailureInjectionRequest")
    if not isinstance(registry, SyntheticFixtureRegistry):
        raise TypeError("registry must be a SyntheticFixtureRegistry")
    if not isinstance(rule_document, RuleBundleDocument):
        raise TypeError("rule_document must be a RuleBundleDocument")
    if not isinstance(approval_capability, ApprovedRuleCapability):
        raise TypeError("approval_capability must be an ApprovedRuleCapability")
    if not callable(strategy_evaluator):
        raise TypeError("strategy_evaluator must be callable")
    if failure_audit_sink is not None and not callable(failure_audit_sink):
        raise TypeError("failure_audit_sink must be callable or None")
    if registry.snapshot_hash.value != INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256:
        raise Stage2BPreEngineAdmissionError(
            "SYNTHETIC_FIXTURE_REGISTRY_NOT_APPROVED",
            "fixture registry snapshot is outside the approved Stage 2B profile",
        )

    registration = registry.require_failure_payload(
        case_id=request.case_id,
        fixture_id=request.fixture_id,
        fixture_version=request.fixture_version,
        failure_payload=request.failure_payload,
    )
    detected = _detect_blocker(
        request.failure_payload,
        rule_document=rule_document,
        approval_capability=approval_capability,
    )
    if detected is None:
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_DID_NOT_BLOCK",
            "registered failure payload did not violate a pre-engine contract",
        )
    layer, blocker = detected
    if layer.value != registration.failure_layer or blocker.value != (
        registration.expected_blocker_code
    ):
        raise Stage2BPreEngineAdmissionError(
            "FAILURE_INJECTION_EXPECTATION_MISMATCH",
            "detected blocker does not match the trusted fixture registration",
        )

    audit = _audit_from_registration(
        request,
        registration,
        registry=registry,
        layer=layer,
        blocker=blocker,
    )
    if failure_audit_sink is not None:
        failure_audit_sink(audit)
    return Stage2BPreEngineBlockedResult(failure_audit=audit)
