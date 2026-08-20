"""Anonymous synthetic Stage 6C candidate, fold, and coverage kernel.

The module is outcome-blind and pure. It accepts no return, NAV, P&L, or
holdout bytes and performs no I/O. It freezes the candidate population, plans
the approved 2022-2025 folds, and evaluates the approved coverage/observable
selection-balance gates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.models import CanonicalModel, HashDigest

from .stage6c_synthetic_kernel import (
    STAGE6C_HOLDOUT_START,
    STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
    require_stage6c_synthetic_capability,
)

STAGE6C_MAX_LABEL_SESSIONS = 120
STAGE6C_EMBARGO_SESSIONS = 20
STAGE6C_HOLDOUT_START_SESSION_INDEX = 1764
_DECIMAL_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_SHANGHAI = ZoneInfo("Asia/Shanghai")


class Stage6CCandidateDisposition(StrEnum):
    TRADE_READY = "TRADE_READY"
    SHADOW_ONLY = "SHADOW_ONLY"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    BLOCKED = "BLOCKED"
    NO_FILL = "NO_FILL"


class Stage6CSecurityState(StrEnum):
    NORMAL = "NORMAL"
    SUSPENDED = "SUSPENDED"
    PRICE_LIMITED = "PRICE_LIMITED"


class Stage6CCoverageAuditStatus(StrEnum):
    COVERAGE_READY = "COVERAGE_READY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"


@dataclass(frozen=True, slots=True)
class _FoldSpec:
    fold_id: str
    calendar_year: int
    evaluation_start_session_index: int
    evaluation_end_session_index: int
    start_local_date: str
    end_exclusive_local_date: str


_FOLD_SPECS = (
    _FoldSpec("WF-2022", 2022, 756, 1008, "2022-01-01", "2023-01-01"),
    _FoldSpec("WF-2023", 2023, 1008, 1260, "2023-01-01", "2024-01-01"),
    _FoldSpec("WF-2024", 2024, 1260, 1512, "2024-01-01", "2025-01-01"),
    _FoldSpec("WF-2025", 2025, 1512, 1764, "2025-01-01", "2026-01-01"),
)
_YEAR_SESSION_RANGES = {
    2019: (0, 252),
    2020: (252, 504),
    2021: (504, 756),
    2022: (756, 1008),
    2023: (1008, 1260),
    2024: (1260, 1512),
    2025: (1512, STAGE6C_HOLDOUT_START_SESSION_INDEX),
}


def _require_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical ID")


def _require_bool(field_name: str, value: bool) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _decimal(field_name: str, value: str, *, positive: bool = False) -> Decimal:
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
class Stage6CSyntheticCandidate(CanonicalModel):
    schema_version: str
    candidate_id: str
    economic_event_id: str
    listed_company_id: str
    decision_time: datetime
    decision_session_index: int
    label_end_session_index: int
    calendar_year: int
    level_1_industry: str
    event_type: str
    e4_state: str
    float_market_cap: str
    prior_20_session_adv: str
    prior_120_session_beta: str
    security_state: Stage6CSecurityState
    disposition: Stage6CCandidateDisposition
    supported: bool
    support_failure_category: str | None
    synthetic: bool
    validation_only: bool
    outcome_fields_present: bool
    authority_eligible: bool
    candidate_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported candidate schema_version")
        for field_name in (
            "candidate_id",
            "economic_event_id",
            "listed_company_id",
            "level_1_industry",
            "event_type",
            "e4_state",
        ):
            _require_id(field_name, getattr(self, field_name))
        object.__setattr__(
            self,
            "decision_time",
            normalize_utc(self.decision_time, field_name="decision_time"),
        )
        if self.decision_time >= STAGE6C_HOLDOUT_START:
            raise ValueError("candidate decision_time must remain outside holdout")
        for field_name in ("decision_session_index", "label_end_session_index"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if not (
            self.decision_session_index
            <= self.label_end_session_index
            <= self.decision_session_index + STAGE6C_MAX_LABEL_SESSIONS
        ):
            raise ValueError("candidate label interval exceeds the approved horizon")
        if isinstance(self.calendar_year, bool) or not isinstance(self.calendar_year, int):
            raise TypeError("calendar_year must be integer")
        if self.calendar_year != self.decision_time.astimezone(_SHANGHAI).year:
            raise ValueError("calendar_year differs from Asia/Shanghai decision_time")
        year_range = _YEAR_SESSION_RANGES.get(self.calendar_year)
        if year_range is None or not (year_range[0] <= self.decision_session_index < year_range[1]):
            raise ValueError("decision_session_index differs from approved synthetic year range")
        _decimal("float_market_cap", self.float_market_cap, positive=True)
        _decimal("prior_20_session_adv", self.prior_20_session_adv, positive=True)
        _decimal("prior_120_session_beta", self.prior_120_session_beta)
        object.__setattr__(self, "security_state", Stage6CSecurityState(self.security_state))
        object.__setattr__(self, "disposition", Stage6CCandidateDisposition(self.disposition))
        for field_name in (
            "supported",
            "synthetic",
            "validation_only",
            "outcome_fields_present",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if self.supported:
            if self.support_failure_category is not None:
                raise ValueError("supported candidate cannot have support_failure_category")
        else:
            if self.support_failure_category is None:
                raise ValueError("unsupported candidate requires support_failure_category")
            _require_id("support_failure_category", self.support_failure_category)
        if not self.synthetic or not self.validation_only:
            raise ValueError("candidate must be anonymous synthetic validation")
        if self.outcome_fields_present or self.authority_eligible:
            raise ValueError("candidate must remain outcome-blind and authority-ineligible")
        if not isinstance(self.candidate_hash, HashDigest) or self.candidate_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("candidate_hash differs")

    @classmethod
    def create(
        cls,
        *,
        candidate_id: str,
        economic_event_id: str,
        listed_company_id: str,
        decision_time: datetime,
        decision_session_index: int,
        label_end_session_index: int,
        level_1_industry: str,
        event_type: str,
        e4_state: str,
        float_market_cap: str,
        prior_20_session_adv: str,
        prior_120_session_beta: str,
        security_state: Stage6CSecurityState,
        disposition: Stage6CCandidateDisposition,
        supported: bool,
        support_failure_category: str | None,
    ) -> Stage6CSyntheticCandidate:
        normalized = normalize_utc(decision_time, field_name="decision_time")
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "candidate_id": candidate_id,
            "economic_event_id": economic_event_id,
            "listed_company_id": listed_company_id,
            "decision_time": normalized,
            "decision_session_index": decision_session_index,
            "label_end_session_index": label_end_session_index,
            "calendar_year": normalized.astimezone(_SHANGHAI).year,
            "level_1_industry": level_1_industry,
            "event_type": event_type,
            "e4_state": e4_state,
            "float_market_cap": float_market_cap,
            "prior_20_session_adv": prior_20_session_adv,
            "prior_120_session_beta": prior_120_session_beta,
            "security_state": security_state,
            "disposition": disposition,
            "supported": supported,
            "support_failure_category": support_failure_category,
            "synthetic": True,
            "validation_only": True,
            "outcome_fields_present": False,
            "authority_eligible": False,
        }
        return cls(**payload, candidate_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "candidate_id",
                "economic_event_id",
                "listed_company_id",
                "decision_time",
                "decision_session_index",
                "label_end_session_index",
                "calendar_year",
                "level_1_industry",
                "event_type",
                "e4_state",
                "float_market_cap",
                "prior_20_session_adv",
                "prior_120_session_beta",
                "security_state",
                "disposition",
                "supported",
                "support_failure_category",
                "synthetic",
                "validation_only",
                "outcome_fields_present",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CCandidateInventory(CanonicalModel):
    schema_version: str
    inventory_id: str
    projection_hash: HashDigest
    candidates: tuple[Stage6CSyntheticCandidate, ...]
    candidate_hashes: tuple[HashDigest, ...]
    synthetic: bool
    validation_only: bool
    holdout_candidates_present: bool
    performance_fields_present: bool
    authority_eligible: bool
    inventory_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported inventory schema_version")
        _require_id("inventory_id", self.inventory_id)
        if not isinstance(self.projection_hash, HashDigest):
            raise TypeError("projection_hash must be HashDigest")
        candidates = tuple(
            sorted(self.candidates, key=lambda value: (value.decision_time, value.candidate_id))
        )
        if not candidates or any(
            not isinstance(item, Stage6CSyntheticCandidate) for item in candidates
        ):
            raise ValueError("candidates must contain typed values")
        ids = tuple(item.candidate_id for item in candidates)
        units = tuple(
            (item.economic_event_id, item.listed_company_id, item.decision_time)
            for item in candidates
        )
        if len(ids) != len(set(ids)) or len(units) != len(set(units)):
            raise ValueError("candidate IDs and research units must be unique")
        object.__setattr__(self, "candidates", candidates)
        expected_hashes = tuple(item.candidate_hash for item in candidates)
        if tuple(self.candidate_hashes) != expected_hashes:
            raise ValueError("candidate_hashes differ from canonical candidate order")
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_candidates_present",
            "performance_fields_present",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only:
            raise ValueError("inventory must remain anonymous synthetic validation")
        if (
            self.holdout_candidates_present
            or self.performance_fields_present
            or self.authority_eligible
        ):
            raise ValueError("inventory exceeded outcome-blind synthetic scope")
        if not isinstance(self.inventory_hash, HashDigest) or self.inventory_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("inventory_hash differs")

    @classmethod
    def create(
        cls,
        *,
        inventory_id: str,
        projection_hash: HashDigest,
        candidates: tuple[Stage6CSyntheticCandidate, ...],
    ) -> Stage6CCandidateInventory:
        ordered = tuple(
            sorted(candidates, key=lambda value: (value.decision_time, value.candidate_id))
        )
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "inventory_id": inventory_id,
            "projection_hash": projection_hash,
            "candidates": ordered,
            "candidate_hashes": tuple(item.candidate_hash for item in ordered),
            "synthetic": True,
            "validation_only": True,
            "holdout_candidates_present": False,
            "performance_fields_present": False,
            "authority_eligible": False,
        }
        return cls(**payload, inventory_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "inventory_id",
                "projection_hash",
                "candidates",
                "candidate_hashes",
                "synthetic",
                "validation_only",
                "holdout_candidates_present",
                "performance_fields_present",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CFoldPlan(CanonicalModel):
    fold_id: str
    calendar_year: int
    evaluation_start_session_index: int
    evaluation_end_session_index: int
    start_local_date: str
    end_exclusive_local_date: str
    training_candidate_ids: tuple[str, ...]
    evaluation_candidate_ids: tuple[str, ...]
    embargo_sessions: int
    maximum_label_sessions: int
    plan_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("fold_id", self.fold_id)
        for field_name in (
            "training_candidate_ids",
            "evaluation_candidate_ids",
        ):
            values = tuple(getattr(self, field_name))
            if values != tuple(sorted(values)) or len(values) != len(set(values)):
                raise ValueError(f"{field_name} must be sorted and unique")
            for value in values:
                _require_id(field_name, value)
            object.__setattr__(self, field_name, values)
        if set(self.training_candidate_ids) & set(self.evaluation_candidate_ids):
            raise ValueError("training and evaluation candidates must be disjoint")
        if self.embargo_sessions != STAGE6C_EMBARGO_SESSIONS or (
            self.maximum_label_sessions != STAGE6C_MAX_LABEL_SESSIONS
        ):
            raise ValueError("fold purge/embargo profile differs")
        if not isinstance(self.plan_hash, HashDigest) or self.plan_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("plan_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "fold_id",
                "calendar_year",
                "evaluation_start_session_index",
                "evaluation_end_session_index",
                "start_local_date",
                "end_exclusive_local_date",
                "training_candidate_ids",
                "evaluation_candidate_ids",
                "embargo_sessions",
                "maximum_label_sessions",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CFoldPlanSet(CanonicalModel):
    schema_version: str
    inventory_hash: HashDigest
    folds: tuple[Stage6CFoldPlan, ...]
    synthetic: bool
    validation_only: bool
    holdout_fold_present: bool
    authority_eligible: bool
    plan_set_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported fold plan schema_version")
        if not isinstance(self.inventory_hash, HashDigest):
            raise TypeError("inventory_hash must be HashDigest")
        folds = tuple(self.folds)
        if tuple(fold.fold_id for fold in folds) != tuple(spec.fold_id for spec in _FOLD_SPECS):
            raise ValueError("fold inventory differs from approved 2022-2025 closed world")
        object.__setattr__(self, "folds", folds)
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_fold_present",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if (
            not self.synthetic
            or not self.validation_only
            or self.holdout_fold_present
            or (self.authority_eligible)
        ):
            raise ValueError("fold plan exceeded anonymous synthetic 6C scope")
        if not isinstance(self.plan_set_hash, HashDigest) or self.plan_set_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("plan_set_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "inventory_hash": self.inventory_hash,
            "folds": self.folds,
            "synthetic": self.synthetic,
            "validation_only": self.validation_only,
            "holdout_fold_present": self.holdout_fold_present,
            "authority_eligible": self.authority_eligible,
        }


@dataclass(frozen=True, slots=True)
class Stage6CContinuousBalanceStat(CanonicalModel):
    feature: str
    supported_mean: str | None
    unsupported_mean: str | None
    absolute_standardized_mean_difference: str | None
    passes: bool

    def __post_init__(self) -> None:
        _require_id("feature", self.feature)
        values = (
            self.supported_mean,
            self.unsupported_mean,
            self.absolute_standardized_mean_difference,
        )
        if any(value is None for value in values):
            if any(value is not None for value in values):
                raise ValueError("continuous balance values must be all present or all absent")
        else:
            for value in values:
                assert value is not None
                _decimal("continuous_balance", value)
        _require_bool("passes", self.passes)


@dataclass(frozen=True, slots=True)
class Stage6CCategoricalBalanceStat(CanonicalModel):
    dimension: str
    category: str
    candidate_count: int
    supported_count: int
    unsupported_count: int
    population_share: str
    coverage: str
    supported_group_share: str | None
    unsupported_group_share: str | None
    absolute_proportion_difference: str | None
    material: bool
    passes: bool

    def __post_init__(self) -> None:
        _require_id("dimension", self.dimension)
        _require_id("category", self.category)
        for field_name in ("candidate_count", "supported_count", "unsupported_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.supported_count + self.unsupported_count != self.candidate_count:
            raise ValueError("categorical counts do not reconcile")
        for field_name in ("population_share", "coverage"):
            _decimal(field_name, getattr(self, field_name))
        optional = (
            self.supported_group_share,
            self.unsupported_group_share,
            self.absolute_proportion_difference,
        )
        if any(value is None for value in optional):
            if any(value is not None for value in optional):
                raise ValueError("categorical group shares must be all present or absent")
        else:
            for value in optional:
                assert value is not None
                _decimal("categorical_balance", value)
        _require_bool("material", self.material)
        _require_bool("passes", self.passes)


@dataclass(frozen=True, slots=True)
class Stage6CYearCoverage(CanonicalModel):
    calendar_year: int
    candidate_count: int
    supported_count: int
    coverage: str | None
    passes: bool

    def __post_init__(self) -> None:
        if isinstance(self.calendar_year, bool) or not isinstance(self.calendar_year, int):
            raise TypeError("calendar_year must be integer")
        for field_name in ("candidate_count", "supported_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.supported_count > self.candidate_count:
            raise ValueError("year supported_count exceeds candidate_count")
        if self.coverage is None:
            if self.candidate_count != 0:
                raise ValueError("non-empty year requires coverage")
        else:
            _decimal("coverage", self.coverage)
        _require_bool("passes", self.passes)


@dataclass(frozen=True, slots=True)
class Stage6CCoverageAuditResult(CanonicalModel):
    schema_version: str
    inventory_hash: HashDigest
    fold_plan_set_hash: HashDigest
    status: Stage6CCoverageAuditStatus
    failure_reasons: tuple[str, ...]
    caveats: tuple[str, ...]
    candidate_count: int
    supported_count: int
    unsupported_count: int
    aggregate_coverage: str
    year_coverage: tuple[Stage6CYearCoverage, ...]
    continuous_balance: tuple[Stage6CContinuousBalanceStat, ...]
    categorical_balance: tuple[Stage6CCategoricalBalanceStat, ...]
    outcome_fields_read: bool
    synthetic: bool
    validation_only: bool
    not_a_complete_stage6c_walk_forward: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    replay_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported coverage result schema_version")
        if not isinstance(self.inventory_hash, HashDigest) or not isinstance(
            self.fold_plan_set_hash, HashDigest
        ):
            raise TypeError("coverage source hashes must be HashDigest")
        object.__setattr__(self, "status", Stage6CCoverageAuditStatus(self.status))
        for field_name in ("failure_reasons", "caveats"):
            values = tuple(getattr(self, field_name))
            if values != tuple(sorted(set(values))):
                raise ValueError(f"{field_name} must be sorted and unique")
            for value in values:
                _require_id(field_name, value)
            object.__setattr__(self, field_name, values)
        for field_name in ("candidate_count", "supported_count", "unsupported_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.supported_count + self.unsupported_count != self.candidate_count:
            raise ValueError("coverage counts do not reconcile")
        _decimal("aggregate_coverage", self.aggregate_coverage)
        object.__setattr__(self, "year_coverage", tuple(self.year_coverage))
        object.__setattr__(self, "continuous_balance", tuple(self.continuous_balance))
        object.__setattr__(self, "categorical_balance", tuple(self.categorical_balance))
        for field_name in (
            "outcome_fields_read",
            "synthetic",
            "validation_only",
            "not_a_complete_stage6c_walk_forward",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if (
            self.outcome_fields_read
            or not self.synthetic
            or not self.validation_only
            or (not self.not_a_complete_stage6c_walk_forward)
        ):
            raise ValueError("coverage result exceeded outcome-blind synthetic scope")
        if self.holdout_artifact_read or self.persists_state or self.authority_eligible:
            raise ValueError("coverage result exceeded authority boundary")
        if self.status is Stage6CCoverageAuditStatus.COVERAGE_READY and self.failure_reasons:
            raise ValueError("ready coverage result cannot have failures")
        if self.status is not Stage6CCoverageAuditStatus.COVERAGE_READY and not (
            self.failure_reasons
        ):
            raise ValueError("non-ready coverage result requires failures")
        if not isinstance(self.replay_hash, HashDigest) or self.replay_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("coverage replay_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "inventory_hash",
                "fold_plan_set_hash",
                "status",
                "failure_reasons",
                "caveats",
                "candidate_count",
                "supported_count",
                "unsupported_count",
                "aggregate_coverage",
                "year_coverage",
                "continuous_balance",
                "categorical_balance",
                "outcome_fields_read",
                "synthetic",
                "validation_only",
                "not_a_complete_stage6c_walk_forward",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


def plan_stage6c_synthetic_folds(
    inventory: Stage6CCandidateInventory,
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CFoldPlanSet:
    if not isinstance(inventory, Stage6CCandidateInventory):
        raise TypeError("inventory must be Stage6CCandidateInventory")
    require_stage6c_synthetic_capability(capability)
    plans: list[Stage6CFoldPlan] = []
    for spec in _FOLD_SPECS:
        training = tuple(
            sorted(
                candidate.candidate_id
                for candidate in inventory.candidates
                if candidate.decision_session_index < spec.evaluation_start_session_index
                and candidate.label_end_session_index
                < spec.evaluation_start_session_index - STAGE6C_EMBARGO_SESSIONS
            )
        )
        evaluation = tuple(
            sorted(
                candidate.candidate_id
                for candidate in inventory.candidates
                if candidate.calendar_year == spec.calendar_year
                and spec.evaluation_start_session_index
                <= candidate.decision_session_index
                < spec.evaluation_end_session_index
                and candidate.label_end_session_index < STAGE6C_HOLDOUT_START_SESSION_INDEX
            )
        )
        payload: dict[str, Any] = {
            "fold_id": spec.fold_id,
            "calendar_year": spec.calendar_year,
            "evaluation_start_session_index": spec.evaluation_start_session_index,
            "evaluation_end_session_index": spec.evaluation_end_session_index,
            "start_local_date": spec.start_local_date,
            "end_exclusive_local_date": spec.end_exclusive_local_date,
            "training_candidate_ids": training,
            "evaluation_candidate_ids": evaluation,
            "embargo_sessions": STAGE6C_EMBARGO_SESSIONS,
            "maximum_label_sessions": STAGE6C_MAX_LABEL_SESSIONS,
        }
        plans.append(Stage6CFoldPlan(**payload, plan_hash=_hash(payload)))
    result_payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "inventory_hash": inventory.inventory_hash,
        "folds": tuple(plans),
        "synthetic": True,
        "validation_only": True,
        "holdout_fold_present": False,
        "authority_eligible": False,
    }
    return Stage6CFoldPlanSet(**result_payload, plan_set_hash=_hash(result_payload))


def _mean(values: tuple[Decimal, ...]) -> Decimal:
    return sum(values, Decimal(0)) / Decimal(len(values))


def _population_variance(values: tuple[Decimal, ...], mean: Decimal) -> Decimal:
    return sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(len(values))


def _continuous_stat(
    feature: str,
    supported: tuple[Decimal, ...],
    unsupported: tuple[Decimal, ...],
) -> Stage6CContinuousBalanceStat:
    if not supported or not unsupported:
        return Stage6CContinuousBalanceStat(feature, None, None, None, True)
    supported_mean = _mean(supported)
    unsupported_mean = _mean(unsupported)
    pooled_variance = (
        _population_variance(supported, supported_mean)
        + _population_variance(unsupported, unsupported_mean)
    ) / Decimal(2)
    difference = abs(supported_mean - unsupported_mean)
    if pooled_variance == 0:
        smd = Decimal(0) if difference == 0 else Decimal("999999999")
    else:
        smd = difference / pooled_variance.sqrt()
    return Stage6CContinuousBalanceStat(
        feature=feature,
        supported_mean=_decimal_text(supported_mean),
        unsupported_mean=_decimal_text(unsupported_mean),
        absolute_standardized_mean_difference=_decimal_text(smd),
        passes=smd <= Decimal("0.10"),
    )


def evaluate_stage6c_synthetic_coverage(
    inventory: Stage6CCandidateInventory,
    fold_plans: Stage6CFoldPlanSet,
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CCoverageAuditResult:
    if not isinstance(inventory, Stage6CCandidateInventory):
        raise TypeError("inventory must be Stage6CCandidateInventory")
    if not isinstance(fold_plans, Stage6CFoldPlanSet):
        raise TypeError("fold_plans must be Stage6CFoldPlanSet")
    require_stage6c_synthetic_capability(capability)
    precheck: list[str] = []
    if fold_plans.inventory_hash != inventory.inventory_hash:
        precheck.append("FOLD_INVENTORY_HASH_MISMATCH")
    expected_fold_set = plan_stage6c_synthetic_folds(inventory, capability=capability)
    if fold_plans != expected_fold_set:
        precheck.append("FOLD_PLAN_RECOMPUTATION_MISMATCH")

    candidates = inventory.candidates
    supported = tuple(candidate for candidate in candidates if candidate.supported)
    unsupported = tuple(candidate for candidate in candidates if not candidate.supported)
    total_count = len(candidates)
    supported_count = len(supported)
    unsupported_count = len(unsupported)
    with localcontext(_DECIMAL_CONTEXT):
        aggregate_coverage = Decimal(supported_count) / Decimal(total_count)
        failures = list(precheck)
        caveats: list[str] = []
        if supported_count == 0:
            failures.append("SUPPORTED_SET_EMPTY")
        if aggregate_coverage < Decimal("0.80"):
            failures.append("AGGREGATE_COVERAGE_BELOW_0_80")
        if unsupported_count < 15:
            caveats.append("UNSUPPORTED_COUNT_LT_15_NO_PROOF_OF_NO_SELECTION_BIAS")
        if unsupported_count == 0:
            caveats.append("UNSUPPORTED_SET_EMPTY_NO_SELECTION_COMPARISON")

        year_stats: list[Stage6CYearCoverage] = []
        for spec in _FOLD_SPECS:
            values = tuple(
                candidate
                for candidate in candidates
                if candidate.calendar_year == spec.calendar_year
            )
            year_supported = sum(candidate.supported for candidate in values)
            if not values:
                failures.append("YEAR_COVERAGE_DENOMINATOR_EMPTY")
                year_stats.append(Stage6CYearCoverage(spec.calendar_year, 0, 0, None, False))
                continue
            ratio = Decimal(year_supported) / Decimal(len(values))
            passes = ratio >= Decimal("0.70")
            if not passes:
                failures.append("YEAR_COVERAGE_BELOW_0_70")
            year_stats.append(
                Stage6CYearCoverage(
                    spec.calendar_year,
                    len(values),
                    year_supported,
                    _decimal_text(ratio),
                    passes,
                )
            )

        continuous: list[Stage6CContinuousBalanceStat] = []
        for feature in (
            "float_market_cap",
            "prior_20_session_adv",
            "prior_120_session_beta",
        ):
            stat = _continuous_stat(
                feature,
                tuple(Decimal(getattr(candidate, feature)) for candidate in supported),
                tuple(Decimal(getattr(candidate, feature)) for candidate in unsupported),
            )
            continuous.append(stat)
            if not stat.passes:
                failures.append("CONTINUOUS_SMD_ABOVE_0_10")

        dimensions: tuple[tuple[str, Any], ...] = (
            ("calendar_year", lambda value: str(value.calendar_year)),
            ("level_1_industry", lambda value: value.level_1_industry),
            ("event_type", lambda value: value.event_type),
            ("e4_state", lambda value: value.e4_state),
            ("security_state", lambda value: value.security_state.value),
        )
        categorical: list[Stage6CCategoricalBalanceStat] = []
        for dimension, getter in dimensions:
            categories = sorted({getter(candidate) for candidate in candidates})
            for category in categories:
                values = tuple(
                    candidate for candidate in candidates if getter(candidate) == category
                )
                category_supported = sum(candidate.supported for candidate in values)
                category_unsupported = len(values) - category_supported
                population_share = Decimal(len(values)) / Decimal(total_count)
                coverage = Decimal(category_supported) / Decimal(len(values))
                material = len(values) >= 15 and population_share >= Decimal("0.05")
                supported_share = (
                    Decimal(category_supported) / Decimal(supported_count)
                    if supported_count
                    else None
                )
                unsupported_share = (
                    Decimal(category_unsupported) / Decimal(unsupported_count)
                    if unsupported_count
                    else None
                )
                difference = (
                    abs(supported_share - unsupported_share)
                    if supported_share is not None and unsupported_share is not None
                    else None
                )
                passes = True
                if material and coverage < Decimal("0.60"):
                    failures.append("MATERIAL_CATEGORY_COVERAGE_BELOW_0_60")
                    passes = False
                if material and difference is not None and difference > Decimal("0.10"):
                    failures.append("CATEGORY_PROPORTION_DIFFERENCE_ABOVE_0_10")
                    passes = False
                categorical.append(
                    Stage6CCategoricalBalanceStat(
                        dimension=dimension,
                        category=category,
                        candidate_count=len(values),
                        supported_count=category_supported,
                        unsupported_count=category_unsupported,
                        population_share=_decimal_text(population_share),
                        coverage=_decimal_text(coverage),
                        supported_group_share=(
                            _decimal_text(supported_share) if supported_share is not None else None
                        ),
                        unsupported_group_share=(
                            _decimal_text(unsupported_share)
                            if unsupported_share is not None
                            else None
                        ),
                        absolute_proportion_difference=(
                            _decimal_text(difference) if difference is not None else None
                        ),
                        material=material,
                        passes=passes,
                    )
                )

    unique_failures = tuple(sorted(set(failures)))
    status = (
        Stage6CCoverageAuditStatus.PRECHECK_BLOCKED
        if precheck
        else (
            Stage6CCoverageAuditStatus.INSUFFICIENT_EVIDENCE
            if unique_failures
            else Stage6CCoverageAuditStatus.COVERAGE_READY
        )
    )
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "inventory_hash": inventory.inventory_hash,
        "fold_plan_set_hash": fold_plans.plan_set_hash,
        "status": status,
        "failure_reasons": unique_failures,
        "caveats": tuple(sorted(set(caveats))),
        "candidate_count": total_count,
        "supported_count": supported_count,
        "unsupported_count": unsupported_count,
        "aggregate_coverage": _decimal_text(aggregate_coverage),
        "year_coverage": tuple(year_stats),
        "continuous_balance": tuple(continuous),
        "categorical_balance": tuple(categorical),
        "outcome_fields_read": False,
        "synthetic": True,
        "validation_only": True,
        "not_a_complete_stage6c_walk_forward": True,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CCoverageAuditResult(**payload, replay_hash=_hash(payload))


__all__ = [
    "STAGE6C_EMBARGO_SESSIONS",
    "STAGE6C_MAX_LABEL_SESSIONS",
    "STAGE6C_HOLDOUT_START_SESSION_INDEX",
    "Stage6CCandidateDisposition",
    "Stage6CCandidateInventory",
    "Stage6CCategoricalBalanceStat",
    "Stage6CContinuousBalanceStat",
    "Stage6CCoverageAuditResult",
    "Stage6CCoverageAuditStatus",
    "Stage6CFoldPlan",
    "Stage6CFoldPlanSet",
    "Stage6CSecurityState",
    "Stage6CSyntheticCandidate",
    "Stage6CYearCoverage",
    "evaluate_stage6c_synthetic_coverage",
    "plan_stage6c_synthetic_folds",
]
