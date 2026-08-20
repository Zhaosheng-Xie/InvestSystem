"""First anonymous synthetic Stage 6C kernel slice.

This pure module validates the holdout-isolation contract and computes the
approved exact TWR/benchmark estimator from caller-supplied anonymous synthetic
NAV points. It performs no I/O, historical run, walk-forward search, bootstrap,
holdout read, persistence, or trading action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, InvalidOperation, localcontext
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import ApprovedRuleCapability, RuleApprovalScope, RuleStatus
from invest_system.models import CanonicalModel, HashDigest

from .stage6c_governance import (
    STAGE6_6C_APPROVAL_SCOPE,
    STAGE6_6C_RULE_APPROVAL_ID,
    STAGE6_6C_RULE_APPROVAL_RECORD_SHA256,
    STAGE6_6C_RULE_BUNDLE_ID,
    STAGE6_6C_RULE_BUNDLE_SHA256,
    STAGE6_6C_RULE_BUNDLE_VERSION,
)

STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION = "0.1.0"
STAGE6C_DECIMAL_CONTEXT_ID = "stage6c-decimal-p50-half-even-v1"
STAGE6C_HOLDOUT_START = datetime.fromisoformat("2025-12-31T16:00:00+00:00")
STAGE6C_HOLDOUT_END_EXCLUSIVE = datetime.fromisoformat("2026-07-28T16:00:00+00:00")
STAGE6C_KNOWLEDGE_CUTOFF_CAP = datetime.fromisoformat("2026-07-28T14:13:31.303929+00:00")
_DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_SIGNED_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class Stage6CSyntheticKernelStatus(StrEnum):
    TWR_RECONCILED = "TWR_RECONCILED"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"


def _require_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical ID")


def _require_bool(field_name: str, value: bool) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _require_decimal(field_name: str, value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical non-negative decimal")
    parsed = Decimal(value)
    if positive and parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


@dataclass(frozen=True, slots=True)
class Stage6CDevelopmentProjection(CanonicalModel):
    schema_version: str
    projection_id: str
    source_release_closure_hash: HashDigest
    projection_rule_hash: HashDigest
    generation_code_hash: HashDigest
    generation_config_hash: HashDigest
    decision_time_exclusive: datetime
    synthetic: bool
    validation_only: bool
    contains_holdout_records: bool
    contains_holdout_metadata_proxy: bool
    authority_eligible: bool
    projection_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported development projection schema_version")
        _require_id("projection_id", self.projection_id)
        for field_name in (
            "source_release_closure_hash",
            "projection_rule_hash",
            "generation_code_hash",
            "generation_config_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        object.__setattr__(
            self,
            "decision_time_exclusive",
            normalize_utc(self.decision_time_exclusive, field_name="decision_time_exclusive"),
        )
        for field_name in (
            "synthetic",
            "validation_only",
            "contains_holdout_records",
            "contains_holdout_metadata_proxy",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only:
            raise ValueError("development projection must be anonymous synthetic validation")
        if self.contains_holdout_records or self.contains_holdout_metadata_proxy:
            raise ValueError("development projection must not contain holdout information")
        if self.authority_eligible:
            raise ValueError("development projection must remain authority-ineligible")
        if not isinstance(self.projection_hash, HashDigest) or self.projection_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("projection_hash differs")

    @classmethod
    def create(
        cls,
        *,
        projection_id: str,
        source_release_closure_hash: HashDigest,
        projection_rule_hash: HashDigest,
        generation_code_hash: HashDigest,
        generation_config_hash: HashDigest,
        decision_time_exclusive: datetime = STAGE6C_HOLDOUT_START,
    ) -> Stage6CDevelopmentProjection:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "projection_id": projection_id,
            "source_release_closure_hash": source_release_closure_hash,
            "projection_rule_hash": projection_rule_hash,
            "generation_code_hash": generation_code_hash,
            "generation_config_hash": generation_config_hash,
            "decision_time_exclusive": normalize_utc(
                decision_time_exclusive, field_name="decision_time_exclusive"
            ),
            "synthetic": True,
            "validation_only": True,
            "contains_holdout_records": False,
            "contains_holdout_metadata_proxy": False,
            "authority_eligible": False,
        }
        return cls(**payload, projection_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "projection_id": self.projection_id,
            "source_release_closure_hash": self.source_release_closure_hash,
            "projection_rule_hash": self.projection_rule_hash,
            "generation_code_hash": self.generation_code_hash,
            "generation_config_hash": self.generation_config_hash,
            "decision_time_exclusive": self.decision_time_exclusive,
            "synthetic": self.synthetic,
            "validation_only": self.validation_only,
            "contains_holdout_records": self.contains_holdout_records,
            "contains_holdout_metadata_proxy": self.contains_holdout_metadata_proxy,
            "authority_eligible": self.authority_eligible,
        }


@dataclass(frozen=True, slots=True)
class Stage6DHoldoutCommitment(CanonicalModel):
    schema_version: str
    commitment_id: str
    holdout_start_inclusive: datetime
    holdout_end_exclusive: datetime
    knowledge_cutoff_cap: datetime
    source_release_closure_hash: HashDigest
    opaque_holdout_artifact_commitment: HashDigest
    custodian_id: str
    generation_code_hash: HashDigest
    generation_config_hash: HashDigest
    sealed_at: datetime
    synthetic: bool
    validation_only: bool
    allows_artifact_read: bool
    authority_eligible: bool
    commitment_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported holdout commitment schema_version")
        _require_id("commitment_id", self.commitment_id)
        _require_id("custodian_id", self.custodian_id)
        for field_name in (
            "holdout_start_inclusive",
            "holdout_end_exclusive",
            "knowledge_cutoff_cap",
            "sealed_at",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        if not (
            self.holdout_start_inclusive < self.knowledge_cutoff_cap < self.holdout_end_exclusive
        ):
            raise ValueError("holdout temporal bounds differ")
        for field_name in (
            "source_release_closure_hash",
            "opaque_holdout_artifact_commitment",
            "generation_code_hash",
            "generation_config_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        for field_name in (
            "synthetic",
            "validation_only",
            "allows_artifact_read",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only:
            raise ValueError("holdout commitment must be anonymous synthetic validation")
        if self.allows_artifact_read or self.authority_eligible:
            raise ValueError("holdout commitment cannot grant access or authority")
        if not isinstance(self.commitment_hash, HashDigest) or self.commitment_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("commitment_hash differs")

    @classmethod
    def create(
        cls,
        *,
        commitment_id: str,
        holdout_start_inclusive: datetime,
        holdout_end_exclusive: datetime,
        knowledge_cutoff_cap: datetime,
        source_release_closure_hash: HashDigest,
        opaque_holdout_artifact_commitment: HashDigest,
        custodian_id: str,
        generation_code_hash: HashDigest,
        generation_config_hash: HashDigest,
        sealed_at: datetime,
    ) -> Stage6DHoldoutCommitment:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "commitment_id": commitment_id,
            "holdout_start_inclusive": normalize_utc(
                holdout_start_inclusive, field_name="holdout_start_inclusive"
            ),
            "holdout_end_exclusive": normalize_utc(
                holdout_end_exclusive, field_name="holdout_end_exclusive"
            ),
            "knowledge_cutoff_cap": normalize_utc(
                knowledge_cutoff_cap, field_name="knowledge_cutoff_cap"
            ),
            "source_release_closure_hash": source_release_closure_hash,
            "opaque_holdout_artifact_commitment": opaque_holdout_artifact_commitment,
            "custodian_id": custodian_id,
            "generation_code_hash": generation_code_hash,
            "generation_config_hash": generation_config_hash,
            "sealed_at": normalize_utc(sealed_at, field_name="sealed_at"),
            "synthetic": True,
            "validation_only": True,
            "allows_artifact_read": False,
            "authority_eligible": False,
        }
        return cls(**payload, commitment_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "commitment_id",
                "holdout_start_inclusive",
                "holdout_end_exclusive",
                "knowledge_cutoff_cap",
                "source_release_closure_hash",
                "opaque_holdout_artifact_commitment",
                "custodian_id",
                "generation_code_hash",
                "generation_config_hash",
                "sealed_at",
                "synthetic",
                "validation_only",
                "allows_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CHoldoutIsolationEvidence(CanonicalModel):
    schema_version: str
    evidence_id: str
    projection_hash: HashDigest
    commitment_hash: HashDigest
    development_namespace_id: str
    holdout_namespace_id: str
    process_has_holdout_read_access: bool
    holdout_mounted_or_linked: bool
    canary_read_denied: bool
    holdout_read_count: int
    checked_at: datetime
    synthetic: bool
    validation_only: bool
    authority_eligible: bool
    evidence_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported isolation evidence schema_version")
        _require_id("evidence_id", self.evidence_id)
        _require_id("development_namespace_id", self.development_namespace_id)
        _require_id("holdout_namespace_id", self.holdout_namespace_id)
        if self.development_namespace_id == self.holdout_namespace_id:
            raise ValueError("development and holdout namespaces must differ")
        if not isinstance(self.projection_hash, HashDigest) or not isinstance(
            self.commitment_hash, HashDigest
        ):
            raise TypeError("isolation evidence hashes must be HashDigest")
        for field_name in (
            "process_has_holdout_read_access",
            "holdout_mounted_or_linked",
            "canary_read_denied",
            "synthetic",
            "validation_only",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if isinstance(self.holdout_read_count, bool) or not isinstance(
            self.holdout_read_count, int
        ):
            raise TypeError("holdout_read_count must be integer")
        if self.holdout_read_count < 0:
            raise ValueError("holdout_read_count must be non-negative")
        object.__setattr__(
            self,
            "checked_at",
            normalize_utc(self.checked_at, field_name="checked_at"),
        )
        if not self.synthetic or not self.validation_only or self.authority_eligible:
            raise ValueError("isolation evidence must remain anonymous synthetic validation")
        if not isinstance(self.evidence_hash, HashDigest) or self.evidence_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("evidence_hash differs")

    @classmethod
    def create(
        cls,
        *,
        evidence_id: str,
        projection_hash: HashDigest,
        commitment_hash: HashDigest,
        development_namespace_id: str,
        holdout_namespace_id: str,
        process_has_holdout_read_access: bool,
        holdout_mounted_or_linked: bool,
        canary_read_denied: bool,
        holdout_read_count: int,
        checked_at: datetime,
    ) -> Stage6CHoldoutIsolationEvidence:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "evidence_id": evidence_id,
            "projection_hash": projection_hash,
            "commitment_hash": commitment_hash,
            "development_namespace_id": development_namespace_id,
            "holdout_namespace_id": holdout_namespace_id,
            "process_has_holdout_read_access": process_has_holdout_read_access,
            "holdout_mounted_or_linked": holdout_mounted_or_linked,
            "canary_read_denied": canary_read_denied,
            "holdout_read_count": holdout_read_count,
            "checked_at": normalize_utc(checked_at, field_name="checked_at"),
            "synthetic": True,
            "validation_only": True,
            "authority_eligible": False,
        }
        return cls(**payload, evidence_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "evidence_id",
                "projection_hash",
                "commitment_hash",
                "development_namespace_id",
                "holdout_namespace_id",
                "process_has_holdout_read_access",
                "holdout_mounted_or_linked",
                "canary_read_denied",
                "holdout_read_count",
                "checked_at",
                "synthetic",
                "validation_only",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CDailyNavPoint(CanonicalModel):
    session_index: int
    session_date: str
    strategy_nav: str
    benchmark_nav: str

    def __post_init__(self) -> None:
        if isinstance(self.session_index, bool) or not isinstance(self.session_index, int):
            raise TypeError("session_index must be integer")
        if self.session_index < 0:
            raise ValueError("session_index must be non-negative")
        if not isinstance(self.session_date, str) or _DATE_RE.fullmatch(self.session_date) is None:
            raise ValueError("session_date must be YYYY-MM-DD")
        _require_decimal("strategy_nav", self.strategy_nav, positive=True)
        _require_decimal("benchmark_nav", self.benchmark_nav, positive=True)


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticKernelCase(CanonicalModel):
    schema_version: str
    case_id: str
    projection: Stage6CDevelopmentProjection
    holdout_commitment: Stage6DHoldoutCommitment
    isolation_evidence: Stage6CHoldoutIsolationEvidence
    nav_points: tuple[Stage6CDailyNavPoint, ...]
    external_cash_flow: str
    decimal_context_id: str
    synthetic: bool
    validation_only: bool
    not_a_formal_historical_run: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    case_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported kernel case schema_version")
        _require_id("case_id", self.case_id)
        if not isinstance(self.projection, Stage6CDevelopmentProjection):
            raise TypeError("projection must be Stage6CDevelopmentProjection")
        if not isinstance(self.holdout_commitment, Stage6DHoldoutCommitment):
            raise TypeError("holdout_commitment must be Stage6DHoldoutCommitment")
        if not isinstance(self.isolation_evidence, Stage6CHoldoutIsolationEvidence):
            raise TypeError("isolation_evidence must be Stage6CHoldoutIsolationEvidence")
        points = tuple(self.nav_points)
        if len(points) < 2 or any(not isinstance(point, Stage6CDailyNavPoint) for point in points):
            raise ValueError("nav_points must contain at least two typed points")
        if tuple(point.session_index for point in points) != tuple(range(len(points))):
            raise ValueError("nav_points session_index must be contiguous from zero")
        dates = tuple(point.session_date for point in points)
        if dates != tuple(sorted(dates)) or len(dates) != len(set(dates)):
            raise ValueError("nav_points dates must be unique and increasing")
        object.__setattr__(self, "nav_points", points)
        if _require_decimal("external_cash_flow", self.external_cash_flow) != 0:
            raise ValueError("external_cash_flow must be zero")
        if self.decimal_context_id != STAGE6C_DECIMAL_CONTEXT_ID:
            raise ValueError("decimal_context_id differs")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_formal_historical_run",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only or not self.not_a_formal_historical_run:
            raise ValueError("kernel case must be anonymous synthetic and non-formal")
        if self.holdout_artifact_read or self.authority_eligible:
            raise ValueError("kernel case cannot read holdout or carry authority")
        if not isinstance(self.case_hash, HashDigest) or self.case_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("case_hash differs")

    @classmethod
    def create(
        cls,
        *,
        case_id: str,
        projection: Stage6CDevelopmentProjection,
        holdout_commitment: Stage6DHoldoutCommitment,
        isolation_evidence: Stage6CHoldoutIsolationEvidence,
        nav_points: tuple[Stage6CDailyNavPoint, ...],
    ) -> Stage6CSyntheticKernelCase:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "case_id": case_id,
            "projection": projection,
            "holdout_commitment": holdout_commitment,
            "isolation_evidence": isolation_evidence,
            "nav_points": nav_points,
            "external_cash_flow": "0",
            "decimal_context_id": STAGE6C_DECIMAL_CONTEXT_ID,
            "synthetic": True,
            "validation_only": True,
            "not_a_formal_historical_run": True,
            "holdout_artifact_read": False,
            "authority_eligible": False,
        }
        return cls(**payload, case_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "case_id",
                "projection",
                "holdout_commitment",
                "isolation_evidence",
                "nav_points",
                "external_cash_flow",
                "decimal_context_id",
                "synthetic",
                "validation_only",
                "not_a_formal_historical_run",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticKernelResult(CanonicalModel):
    schema_version: str
    case_hash: HashDigest
    status: Stage6CSyntheticKernelStatus
    failure_reasons: tuple[str, ...]
    session_count: int
    daily_excess_factors: tuple[str, ...]
    gross_excess_factor: str | None
    annualized_net_excess_percentage_points: str | None
    decimal_context_id: str
    synthetic: bool
    validation_only: bool
    not_a_complete_stage6c_walk_forward: bool
    formal_historical_run: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    replay_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported kernel result schema_version")
        if not isinstance(self.case_hash, HashDigest):
            raise TypeError("case_hash must be HashDigest")
        object.__setattr__(self, "status", Stage6CSyntheticKernelStatus(self.status))
        reasons = tuple(self.failure_reasons)
        if len(reasons) != len(set(reasons)):
            raise ValueError("failure_reasons must be unique")
        for reason in reasons:
            _require_id("failure_reasons", reason)
        object.__setattr__(self, "failure_reasons", reasons)
        if isinstance(self.session_count, bool) or not isinstance(self.session_count, int):
            raise TypeError("session_count must be integer")
        if self.session_count < 0:
            raise ValueError("session_count must be non-negative")
        factors = tuple(self.daily_excess_factors)
        for factor in factors:
            _require_decimal("daily_excess_factors", factor, positive=True)
        object.__setattr__(self, "daily_excess_factors", factors)
        if self.status is Stage6CSyntheticKernelStatus.TWR_RECONCILED:
            if reasons or self.session_count < 1 or len(factors) != self.session_count:
                raise ValueError("reconciled result shape differs")
            if self.gross_excess_factor is None or (
                self.annualized_net_excess_percentage_points is None
            ):
                raise ValueError("reconciled result requires TWR values")
            _require_decimal("gross_excess_factor", self.gross_excess_factor, positive=True)
            if _SIGNED_DECIMAL_RE.fullmatch(self.annualized_net_excess_percentage_points) is None:
                raise ValueError("annualized_net_excess_percentage_points differs")
        else:
            if (
                not reasons
                or factors
                or self.gross_excess_factor is not None
                or (self.annualized_net_excess_percentage_points is not None)
            ):
                raise ValueError("blocked result must not publish partial TWR")
        if self.decimal_context_id != STAGE6C_DECIMAL_CONTEXT_ID:
            raise ValueError("decimal_context_id differs")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_complete_stage6c_walk_forward",
            "formal_historical_run",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if (
            not self.synthetic
            or not self.validation_only
            or (not self.not_a_complete_stage6c_walk_forward)
        ):
            raise ValueError("result scope differs")
        if any(
            (
                self.formal_historical_run,
                self.holdout_artifact_read,
                self.persists_state,
                self.authority_eligible,
            )
        ):
            raise ValueError("result exceeded synthetic kernel authority")
        if not isinstance(self.replay_hash, HashDigest) or self.replay_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("replay_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "case_hash",
                "status",
                "failure_reasons",
                "session_count",
                "daily_excess_factors",
                "gross_excess_factor",
                "annualized_net_excess_percentage_points",
                "decimal_context_id",
                "synthetic",
                "validation_only",
                "not_a_complete_stage6c_walk_forward",
                "formal_historical_run",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


def _require_capability(capability: ApprovedRuleCapability) -> None:
    if not isinstance(capability, ApprovedRuleCapability):
        raise TypeError("capability must be ApprovedRuleCapability")
    actual = (
        capability.approval_id,
        capability.bundle_id,
        capability.bundle_version,
        capability.bundle_hash.value,
        capability.approval_record_hash.value,
        capability.approval_scope,
        capability.rule_status,
    )
    expected = (
        STAGE6_6C_RULE_APPROVAL_ID,
        STAGE6_6C_RULE_BUNDLE_ID,
        STAGE6_6C_RULE_BUNDLE_VERSION,
        STAGE6_6C_RULE_BUNDLE_SHA256,
        STAGE6_6C_RULE_APPROVAL_RECORD_SHA256,
        STAGE6_6C_APPROVAL_SCOPE,
        RuleStatus.APPROVED,
    )
    if actual != expected or capability.approval_scope is not (
        RuleApprovalScope.STAGE6_DEVELOPMENT_WALK_FORWARD_VALIDATION
    ):
        raise ValueError("kernel requires the exact approved Stage 6C capability")


def _failure(case: Stage6CSyntheticKernelCase) -> tuple[str, ...]:
    reasons: list[str] = []
    projection = case.projection
    commitment = case.holdout_commitment
    evidence = case.isolation_evidence
    if projection.decision_time_exclusive != commitment.holdout_start_inclusive:
        reasons.append("HOLDOUT_BOUNDARY_MISMATCH")
    if (
        projection.decision_time_exclusive != STAGE6C_HOLDOUT_START
        or commitment.holdout_start_inclusive != STAGE6C_HOLDOUT_START
        or commitment.holdout_end_exclusive != STAGE6C_HOLDOUT_END_EXCLUSIVE
        or commitment.knowledge_cutoff_cap != STAGE6C_KNOWLEDGE_CUTOFF_CAP
    ):
        reasons.append("HOLDOUT_BOUNDARY_NOT_APPROVED")
    if projection.source_release_closure_hash != commitment.source_release_closure_hash:
        reasons.append("SOURCE_CLOSURE_MISMATCH")
    if evidence.projection_hash != projection.projection_hash or (
        evidence.commitment_hash != commitment.commitment_hash
    ):
        reasons.append("ISOLATION_EVIDENCE_BINDING_MISMATCH")
    if evidence.process_has_holdout_read_access:
        reasons.append("HOLDOUT_READ_ACCESS_PRESENT")
    if evidence.holdout_mounted_or_linked:
        reasons.append("HOLDOUT_MOUNTED_OR_LINKED")
    if not evidence.canary_read_denied:
        reasons.append("HOLDOUT_CANARY_NOT_DENIED")
    if evidence.holdout_read_count != 0:
        reasons.append("HOLDOUT_READ_COUNT_NONZERO")
    return tuple(reasons)


def _build_result(
    case: Stage6CSyntheticKernelCase,
    *,
    status: Stage6CSyntheticKernelStatus,
    failure_reasons: tuple[str, ...],
    factors: tuple[str, ...] = (),
    gross: str | None = None,
    annualized: str | None = None,
) -> Stage6CSyntheticKernelResult:
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "case_hash": case.case_hash,
        "status": status,
        "failure_reasons": failure_reasons,
        "session_count": len(factors),
        "daily_excess_factors": factors,
        "gross_excess_factor": gross,
        "annualized_net_excess_percentage_points": annualized,
        "decimal_context_id": STAGE6C_DECIMAL_CONTEXT_ID,
        "synthetic": True,
        "validation_only": True,
        "not_a_complete_stage6c_walk_forward": True,
        "formal_historical_run": False,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CSyntheticKernelResult(**payload, replay_hash=_hash(payload))


def evaluate_stage6c_synthetic_twr_kernel(
    case: Stage6CSyntheticKernelCase,
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CSyntheticKernelResult:
    """Validate isolation and compute exact synthetic TWR without side effects."""

    if not isinstance(case, Stage6CSyntheticKernelCase):
        raise TypeError("case must be Stage6CSyntheticKernelCase")
    _require_capability(capability)
    failure = _failure(case)
    if failure:
        return _build_result(
            case,
            status=Stage6CSyntheticKernelStatus.PRECHECK_BLOCKED,
            failure_reasons=failure,
        )
    try:
        with localcontext(_DECIMAL_CONTEXT):
            factors: list[Decimal] = []
            points = case.nav_points
            for previous, current in zip(points[:-1], points[1:], strict=True):
                strategy_factor = Decimal(current.strategy_nav) / Decimal(previous.strategy_nav)
                benchmark_factor = Decimal(current.benchmark_nav) / Decimal(previous.benchmark_nav)
                factors.append(strategy_factor / benchmark_factor)
            gross = Decimal(1)
            for factor in factors:
                gross *= factor
            exponent = Decimal(252) / Decimal(len(factors))
            annualized = (gross**exponent - Decimal(1)) * Decimal(100)
            factor_text = tuple(_decimal_text(value) for value in factors)
            return _build_result(
                case,
                status=Stage6CSyntheticKernelStatus.TWR_RECONCILED,
                failure_reasons=(),
                factors=factor_text,
                gross=_decimal_text(gross),
                annualized=_decimal_text(annualized),
            )
    except (InvalidOperation, ZeroDivisionError) as exc:
        raise ValueError("synthetic TWR calculation failed closed") from exc


__all__ = [
    "STAGE6C_DECIMAL_CONTEXT_ID",
    "STAGE6C_HOLDOUT_START",
    "STAGE6C_HOLDOUT_END_EXCLUSIVE",
    "STAGE6C_KNOWLEDGE_CUTOFF_CAP",
    "STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION",
    "Stage6CDailyNavPoint",
    "Stage6CDevelopmentProjection",
    "Stage6CHoldoutIsolationEvidence",
    "Stage6CSyntheticKernelCase",
    "Stage6CSyntheticKernelResult",
    "Stage6CSyntheticKernelStatus",
    "Stage6DHoldoutCommitment",
    "evaluate_stage6c_synthetic_twr_kernel",
]
