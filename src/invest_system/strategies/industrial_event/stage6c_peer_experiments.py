"""Anonymous synthetic Stage 6C peer benchmark and experiment ledger kernel."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.models import CanonicalModel, HashDigest

from .stage6c_candidate_coverage import (
    Stage6CCandidateInventory,
    Stage6CFoldPlanSet,
    Stage6CSyntheticCandidate,
    plan_stage6c_synthetic_folds,
)
from .stage6c_synthetic_kernel import (
    STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
    require_stage6c_synthetic_capability,
)

STAGE6C_MINIMUM_PEERS = 5
STAGE6C_REQUIRED_ABLATION_IDS = (
    "ablation_event_semantics",
    "ablation_industry_company_mapping",
    "ablation_gates",
    "ablation_profit_bridge",
    "ablation_valuation",
    "ablation_exit",
    "ablation_portfolio_risk",
    "ablation_execution",
)
STAGE6C_REQUIRED_STRESS_IDS = (
    "stress_friction_1_0",
    "stress_friction_1_5",
    "stress_friction_2_0",
    "stress_delay_0",
    "stress_delay_1",
    "stress_delay_2",
    "stress_nav_100000",
    "stress_nav_300000",
    "stress_gap",
    "stress_suspension",
    "stress_price_limit",
    "stress_no_opposing_liquidity",
    "stress_half_capacity",
    "stress_mark_missing",
    "stress_mark_stale",
    "stress_mark_same_time_conflict",
)


class Stage6CPeerFallbackLevel(StrEnum):
    SAME_INDUSTRY_SIZE_BETA = "SAME_INDUSTRY_SIZE_BETA"
    SAME_SIZE_BETA_ALL_A_SHARE = "SAME_SIZE_BETA_ALL_A_SHARE"
    SAME_SIZE_ALL_A_SHARE = "SAME_SIZE_ALL_A_SHARE"
    INSUFFICIENT_PEERS = "INSUFFICIENT_PEERS"


class Stage6CPeerBasketStatus(StrEnum):
    READY = "READY"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class Stage6CExperimentKind(StrEnum):
    ABLATION = "ABLATION"
    STRESS = "STRESS"
    EXPLORATORY = "EXPLORATORY"


class Stage6CExperimentOutcomeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _require_id(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value or any(character.isspace() for character in value):
        raise ValueError(f"{field_name} must be a non-empty no-whitespace ID")


def _require_bool(field_name: str, value: bool) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _require_quintile(field_name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError(f"{field_name} must be integer 1 through 5")


@dataclass(frozen=True, slots=True)
class Stage6CPeerMember(CanonicalModel):
    security_id: str
    level_1_industry: str
    float_market_cap_quintile: int
    prior_120_session_beta_quintile: int
    available_at: datetime
    eligible: bool
    stage5d_supported: bool
    synthetic: bool
    validation_only: bool
    outcome_fields_present: bool

    def __post_init__(self) -> None:
        _require_id("security_id", self.security_id)
        _require_id("level_1_industry", self.level_1_industry)
        _require_quintile("float_market_cap_quintile", self.float_market_cap_quintile)
        _require_quintile(
            "prior_120_session_beta_quintile",
            self.prior_120_session_beta_quintile,
        )
        object.__setattr__(
            self,
            "available_at",
            normalize_utc(self.available_at, field_name="available_at"),
        )
        for field_name in (
            "eligible",
            "stage5d_supported",
            "synthetic",
            "validation_only",
            "outcome_fields_present",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only or self.outcome_fields_present:
            raise ValueError("peer member must remain outcome-blind synthetic validation")


@dataclass(frozen=True, slots=True)
class Stage6CPeerSnapshot(CanonicalModel):
    schema_version: str
    snapshot_id: str
    candidate_hash: HashDigest
    candidate_id: str
    target_security_id: str
    decision_time: datetime
    target_level_1_industry: str
    target_float_market_cap_quintile: int
    target_prior_120_session_beta_quintile: int
    members: tuple[Stage6CPeerMember, ...]
    synthetic: bool
    validation_only: bool
    outcome_fields_present: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    snapshot_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported peer snapshot schema_version")
        for field_name in (
            "snapshot_id",
            "candidate_id",
            "target_security_id",
            "target_level_1_industry",
        ):
            _require_id(field_name, getattr(self, field_name))
        if not isinstance(self.candidate_hash, HashDigest):
            raise TypeError("candidate_hash must be HashDigest")
        object.__setattr__(
            self,
            "decision_time",
            normalize_utc(self.decision_time, field_name="decision_time"),
        )
        _require_quintile("target_float_market_cap_quintile", self.target_float_market_cap_quintile)
        _require_quintile(
            "target_prior_120_session_beta_quintile",
            self.target_prior_120_session_beta_quintile,
        )
        members = tuple(sorted(self.members, key=lambda value: value.security_id))
        if not members or any(not isinstance(value, Stage6CPeerMember) for value in members):
            raise ValueError("members must contain typed values")
        ids = tuple(value.security_id for value in members)
        if len(ids) != len(set(ids)):
            raise ValueError("peer member security IDs must be unique")
        object.__setattr__(self, "members", members)
        for field_name in (
            "synthetic",
            "validation_only",
            "outcome_fields_present",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.synthetic or not self.validation_only or self.outcome_fields_present:
            raise ValueError("peer snapshot must remain outcome-blind synthetic validation")
        if self.holdout_artifact_read or self.authority_eligible:
            raise ValueError("peer snapshot exceeded authority boundary")
        if any(value.available_at > self.decision_time for value in members):
            raise ValueError("peer member available_at exceeds candidate decision_time")
        if not isinstance(self.snapshot_hash, HashDigest) or self.snapshot_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("snapshot_hash differs")

    @classmethod
    def create(
        cls,
        *,
        snapshot_id: str,
        candidate: Stage6CSyntheticCandidate,
        target_float_market_cap_quintile: int,
        target_prior_120_session_beta_quintile: int,
        members: tuple[Stage6CPeerMember, ...],
    ) -> Stage6CPeerSnapshot:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "snapshot_id": snapshot_id,
            "candidate_hash": candidate.candidate_hash,
            "candidate_id": candidate.candidate_id,
            "target_security_id": candidate.listed_company_id,
            "decision_time": candidate.decision_time,
            "target_level_1_industry": candidate.level_1_industry,
            "target_float_market_cap_quintile": target_float_market_cap_quintile,
            "target_prior_120_session_beta_quintile": (target_prior_120_session_beta_quintile),
            "members": tuple(sorted(members, key=lambda value: value.security_id)),
            "synthetic": True,
            "validation_only": True,
            "outcome_fields_present": False,
            "holdout_artifact_read": False,
            "authority_eligible": False,
        }
        return cls(**payload, snapshot_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "snapshot_id",
                "candidate_hash",
                "candidate_id",
                "target_security_id",
                "decision_time",
                "target_level_1_industry",
                "target_float_market_cap_quintile",
                "target_prior_120_session_beta_quintile",
                "members",
                "synthetic",
                "validation_only",
                "outcome_fields_present",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CPeerWeight(CanonicalModel):
    security_id: str
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        _require_id("security_id", self.security_id)
        if self.numerator != 1 or isinstance(self.denominator, bool) or self.denominator < 1:
            raise ValueError("peer weights must use exact 1/N rational form")


@dataclass(frozen=True, slots=True)
class Stage6CPeerBasket(CanonicalModel):
    schema_version: str
    candidate_hash: HashDigest
    snapshot_hash: HashDigest
    status: Stage6CPeerBasketStatus
    fallback_level: Stage6CPeerFallbackLevel
    peer_weights: tuple[Stage6CPeerWeight, ...]
    peer_count: int
    failure_reasons: tuple[str, ...]
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    basket_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported peer basket schema_version")
        if not isinstance(self.candidate_hash, HashDigest) or not isinstance(
            self.snapshot_hash, HashDigest
        ):
            raise TypeError("basket source hashes must be HashDigest")
        object.__setattr__(self, "status", Stage6CPeerBasketStatus(self.status))
        object.__setattr__(self, "fallback_level", Stage6CPeerFallbackLevel(self.fallback_level))
        weights = tuple(self.peer_weights)
        if len(weights) != self.peer_count or len({value.security_id for value in weights}) != len(
            weights
        ):
            raise ValueError("peer basket counts or IDs differ")
        object.__setattr__(self, "peer_weights", weights)
        reasons = tuple(sorted(set(self.failure_reasons)))
        if tuple(self.failure_reasons) != reasons:
            raise ValueError("failure_reasons must be sorted and unique")
        object.__setattr__(self, "failure_reasons", reasons)
        if self.status is Stage6CPeerBasketStatus.READY:
            if self.peer_count < STAGE6C_MINIMUM_PEERS or reasons:
                raise ValueError("ready basket requires at least five peers and no failures")
            if any(value.denominator != self.peer_count for value in weights):
                raise ValueError("ready basket weights must be exact and equal")
        elif weights or self.peer_count != 0 or not reasons:
            raise ValueError("insufficient basket cannot publish partial peers")
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if (
            not self.synthetic
            or not self.validation_only
            or self.holdout_artifact_read
            or (self.authority_eligible)
        ):
            raise ValueError("peer basket exceeded synthetic authority")
        if not isinstance(self.basket_hash, HashDigest) or self.basket_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("basket_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "candidate_hash",
                "snapshot_hash",
                "status",
                "fallback_level",
                "peer_weights",
                "peer_count",
                "failure_reasons",
                "synthetic",
                "validation_only",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CPeerBasketSet(CanonicalModel):
    schema_version: str
    inventory_hash: HashDigest
    fold_plan_set_hash: HashDigest
    baskets: tuple[Stage6CPeerBasket, ...]
    ready_count: int
    insufficient_count: int
    all_evaluation_candidates_covered: bool
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    basket_set_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported peer basket set schema_version")
        if not isinstance(self.inventory_hash, HashDigest) or not isinstance(
            self.fold_plan_set_hash, HashDigest
        ):
            raise TypeError("basket set source hashes must be HashDigest")
        baskets = tuple(self.baskets)
        if len({value.candidate_hash for value in baskets}) != len(baskets):
            raise ValueError("peer baskets must bind unique candidates")
        object.__setattr__(self, "baskets", baskets)
        if self.ready_count + self.insufficient_count != len(baskets):
            raise ValueError("peer basket set counts do not reconcile")
        for field_name in (
            "all_evaluation_candidates_covered",
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.all_evaluation_candidates_covered:
            raise ValueError("peer basket set must preserve every evaluation candidate")
        if (
            not self.synthetic
            or not self.validation_only
            or self.holdout_artifact_read
            or (self.authority_eligible)
        ):
            raise ValueError("peer basket set exceeded synthetic authority")
        if not isinstance(self.basket_set_hash, HashDigest) or self.basket_set_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("basket_set_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "inventory_hash",
                "fold_plan_set_hash",
                "baskets",
                "ready_count",
                "insufficient_count",
                "all_evaluation_candidates_covered",
                "synthetic",
                "validation_only",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


def build_stage6c_peer_basket(
    candidate: Stage6CSyntheticCandidate,
    snapshot: Stage6CPeerSnapshot,
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CPeerBasket:
    require_stage6c_synthetic_capability(capability)
    if (
        snapshot.candidate_hash != candidate.candidate_hash
        or snapshot.candidate_id != candidate.candidate_id
        or snapshot.target_security_id != candidate.listed_company_id
        or snapshot.decision_time != candidate.decision_time
        or snapshot.target_level_1_industry != candidate.level_1_industry
    ):
        raise ValueError("peer snapshot candidate binding differs")
    eligible = tuple(
        value
        for value in snapshot.members
        if value.security_id != snapshot.target_security_id
        and value.eligible
        and value.stage5d_supported
        and value.available_at <= snapshot.decision_time
    )
    levels = (
        (
            Stage6CPeerFallbackLevel.SAME_INDUSTRY_SIZE_BETA,
            tuple(
                value
                for value in eligible
                if value.level_1_industry == snapshot.target_level_1_industry
                and value.float_market_cap_quintile == snapshot.target_float_market_cap_quintile
                and value.prior_120_session_beta_quintile
                == snapshot.target_prior_120_session_beta_quintile
            ),
        ),
        (
            Stage6CPeerFallbackLevel.SAME_SIZE_BETA_ALL_A_SHARE,
            tuple(
                value
                for value in eligible
                if value.float_market_cap_quintile == snapshot.target_float_market_cap_quintile
                and value.prior_120_session_beta_quintile
                == snapshot.target_prior_120_session_beta_quintile
            ),
        ),
        (
            Stage6CPeerFallbackLevel.SAME_SIZE_ALL_A_SHARE,
            tuple(
                value
                for value in eligible
                if value.float_market_cap_quintile == snapshot.target_float_market_cap_quintile
            ),
        ),
    )
    chosen_level = Stage6CPeerFallbackLevel.INSUFFICIENT_PEERS
    chosen: tuple[Stage6CPeerMember, ...] = ()
    for level, values in levels:
        if len(values) >= STAGE6C_MINIMUM_PEERS:
            chosen_level = level
            chosen = tuple(sorted(values, key=lambda value: value.security_id))
            break
    if not chosen:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "candidate_hash": candidate.candidate_hash,
            "snapshot_hash": snapshot.snapshot_hash,
            "status": Stage6CPeerBasketStatus.INSUFFICIENT_EVIDENCE,
            "fallback_level": Stage6CPeerFallbackLevel.INSUFFICIENT_PEERS,
            "peer_weights": (),
            "peer_count": 0,
            "failure_reasons": ("PEER_COUNT_BELOW_5",),
            "synthetic": True,
            "validation_only": True,
            "holdout_artifact_read": False,
            "authority_eligible": False,
        }
        return Stage6CPeerBasket(**payload, basket_hash=_hash(payload))
    weights = tuple(Stage6CPeerWeight(value.security_id, 1, len(chosen)) for value in chosen)
    payload = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "candidate_hash": candidate.candidate_hash,
        "snapshot_hash": snapshot.snapshot_hash,
        "status": Stage6CPeerBasketStatus.READY,
        "fallback_level": chosen_level,
        "peer_weights": weights,
        "peer_count": len(weights),
        "failure_reasons": (),
        "synthetic": True,
        "validation_only": True,
        "holdout_artifact_read": False,
        "authority_eligible": False,
    }
    return Stage6CPeerBasket(**payload, basket_hash=_hash(payload))


def build_stage6c_peer_basket_set(
    inventory: Stage6CCandidateInventory,
    fold_plans: Stage6CFoldPlanSet,
    snapshots: tuple[Stage6CPeerSnapshot, ...],
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CPeerBasketSet:
    require_stage6c_synthetic_capability(capability)
    if fold_plans != plan_stage6c_synthetic_folds(inventory, capability=capability):
        raise ValueError("fold plans differ from deterministic recomputation")
    candidate_by_id = {value.candidate_id: value for value in inventory.candidates}
    evaluation_ids = tuple(
        sorted(
            {
                candidate_id
                for fold in fold_plans.folds
                for candidate_id in fold.evaluation_candidate_ids
            }
        )
    )
    snapshot_by_id = {value.candidate_id: value for value in snapshots}
    if len(snapshot_by_id) != len(snapshots) or set(snapshot_by_id) != set(evaluation_ids):
        raise ValueError("peer snapshots must cover every evaluation candidate exactly once")
    baskets = tuple(
        build_stage6c_peer_basket(
            candidate_by_id[candidate_id], snapshot_by_id[candidate_id], capability=capability
        )
        for candidate_id in evaluation_ids
    )
    ready = sum(value.status is Stage6CPeerBasketStatus.READY for value in baskets)
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "inventory_hash": inventory.inventory_hash,
        "fold_plan_set_hash": fold_plans.plan_set_hash,
        "baskets": baskets,
        "ready_count": ready,
        "insufficient_count": len(baskets) - ready,
        "all_evaluation_candidates_covered": True,
        "synthetic": True,
        "validation_only": True,
        "holdout_artifact_read": False,
        "authority_eligible": False,
    }
    return Stage6CPeerBasketSet(**payload, basket_set_hash=_hash(payload))


@dataclass(frozen=True, slots=True)
class Stage6CExperimentRegistration(CanonicalModel):
    schema_version: str
    experiment_id: str
    kind: Stage6CExperimentKind
    scenario_id: str
    parent_preregistration_hash: HashDigest
    registered_at: datetime
    performance_visible_at_registration: bool
    may_enter_current_champion: bool
    synthetic: bool
    validation_only: bool
    authority_eligible: bool
    registration_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported experiment registration schema_version")
        _require_id("experiment_id", self.experiment_id)
        _require_id("scenario_id", self.scenario_id)
        object.__setattr__(self, "kind", Stage6CExperimentKind(self.kind))
        if not isinstance(self.parent_preregistration_hash, HashDigest):
            raise TypeError("parent_preregistration_hash must be HashDigest")
        object.__setattr__(
            self,
            "registered_at",
            normalize_utc(self.registered_at, field_name="registered_at"),
        )
        for field_name in (
            "performance_visible_at_registration",
            "may_enter_current_champion",
            "synthetic",
            "validation_only",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if self.performance_visible_at_registration or self.may_enter_current_champion:
            raise ValueError("experiment registration must be pre-performance diagnostic only")
        if not self.synthetic or not self.validation_only or self.authority_eligible:
            raise ValueError("experiment registration exceeded synthetic authority")
        if not isinstance(self.registration_hash, HashDigest) or self.registration_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("registration_hash differs")

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        kind: Stage6CExperimentKind,
        scenario_id: str,
        parent_preregistration_hash: HashDigest,
        registered_at: datetime,
    ) -> Stage6CExperimentRegistration:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "experiment_id": experiment_id,
            "kind": kind,
            "scenario_id": scenario_id,
            "parent_preregistration_hash": parent_preregistration_hash,
            "registered_at": normalize_utc(registered_at, field_name="registered_at"),
            "performance_visible_at_registration": False,
            "may_enter_current_champion": False,
            "synthetic": True,
            "validation_only": True,
            "authority_eligible": False,
        }
        return cls(**payload, registration_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "experiment_id",
                "kind",
                "scenario_id",
                "parent_preregistration_hash",
                "registered_at",
                "performance_visible_at_registration",
                "may_enter_current_champion",
                "synthetic",
                "validation_only",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CExperimentOutcome(CanonicalModel):
    experiment_id: str
    registration_hash: HashDigest
    source_replay_hash: HashDigest
    status: Stage6CExperimentOutcomeStatus
    result_summary_hash: HashDigest
    synthetic: bool
    validation_only: bool
    may_enter_current_champion: bool
    authority_eligible: bool
    outcome_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("experiment_id", self.experiment_id)
        for field_name in (
            "registration_hash",
            "source_replay_hash",
            "result_summary_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        object.__setattr__(self, "status", Stage6CExperimentOutcomeStatus(self.status))
        for field_name in (
            "synthetic",
            "validation_only",
            "may_enter_current_champion",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if (
            not self.synthetic
            or not self.validation_only
            or self.may_enter_current_champion
            or (self.authority_eligible)
        ):
            raise ValueError("experiment outcome exceeded diagnostic synthetic scope")
        if not isinstance(self.outcome_hash, HashDigest) or self.outcome_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("outcome_hash differs")

    @classmethod
    def create(
        cls,
        *,
        experiment_id: str,
        registration_hash: HashDigest,
        source_replay_hash: HashDigest,
        status: Stage6CExperimentOutcomeStatus,
        result_summary_hash: HashDigest,
    ) -> Stage6CExperimentOutcome:
        payload: dict[str, Any] = {
            "experiment_id": experiment_id,
            "registration_hash": registration_hash,
            "source_replay_hash": source_replay_hash,
            "status": status,
            "result_summary_hash": result_summary_hash,
            "synthetic": True,
            "validation_only": True,
            "may_enter_current_champion": False,
            "authority_eligible": False,
        }
        return cls(**payload, outcome_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "experiment_id",
                "registration_hash",
                "source_replay_hash",
                "status",
                "result_summary_hash",
                "synthetic",
                "validation_only",
                "may_enter_current_champion",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CExperimentLedger(CanonicalModel):
    schema_version: str
    parent_preregistration_hash: HashDigest
    execution_started_at: datetime
    registrations: tuple[Stage6CExperimentRegistration, ...]
    outcomes: tuple[Stage6CExperimentOutcome, ...]
    required_ablation_complete: bool
    required_stress_complete: bool
    exploratory_count: int
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    ledger_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported experiment ledger schema_version")
        if not isinstance(self.parent_preregistration_hash, HashDigest):
            raise TypeError("parent_preregistration_hash must be HashDigest")
        object.__setattr__(
            self,
            "execution_started_at",
            normalize_utc(self.execution_started_at, field_name="execution_started_at"),
        )
        registrations = tuple(self.registrations)
        outcomes = tuple(self.outcomes)
        if len({value.experiment_id for value in registrations}) != len(registrations):
            raise ValueError("experiment registrations must be unique")
        if len({value.experiment_id for value in outcomes}) != len(outcomes):
            raise ValueError("experiment outcomes must be unique")
        object.__setattr__(self, "registrations", registrations)
        object.__setattr__(self, "outcomes", outcomes)
        for field_name in (
            "required_ablation_complete",
            "required_stress_complete",
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            _require_bool(field_name, getattr(self, field_name))
        if not self.required_ablation_complete or not self.required_stress_complete:
            raise ValueError("required experiment closed world must be complete")
        if (
            not self.synthetic
            or not self.validation_only
            or self.holdout_artifact_read
            or (self.persists_state or self.authority_eligible)
        ):
            raise ValueError("experiment ledger exceeded synthetic authority")
        if not isinstance(self.ledger_hash, HashDigest) or self.ledger_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("ledger_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "parent_preregistration_hash",
                "execution_started_at",
                "registrations",
                "outcomes",
                "required_ablation_complete",
                "required_stress_complete",
                "exploratory_count",
                "synthetic",
                "validation_only",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


def build_stage6c_experiment_ledger(
    registrations: tuple[Stage6CExperimentRegistration, ...],
    outcomes: tuple[Stage6CExperimentOutcome, ...],
    *,
    parent_preregistration_hash: HashDigest,
    execution_started_at: datetime,
    capability: ApprovedRuleCapability,
) -> Stage6CExperimentLedger:
    require_stage6c_synthetic_capability(capability)
    started = normalize_utc(execution_started_at, field_name="execution_started_at")
    ordered_registrations = tuple(sorted(registrations, key=lambda value: value.experiment_id))
    ordered_outcomes = tuple(sorted(outcomes, key=lambda value: value.experiment_id))
    registration_by_id = {value.experiment_id: value for value in ordered_registrations}
    outcome_by_id = {value.experiment_id: value for value in ordered_outcomes}
    if len(registration_by_id) != len(ordered_registrations) or (
        len(outcome_by_id) != len(ordered_outcomes)
    ):
        raise ValueError("experiment IDs must be unique")
    if set(registration_by_id) != set(outcome_by_id):
        raise ValueError("every registered experiment requires exactly one outcome")
    for experiment_id, registration in registration_by_id.items():
        outcome = outcome_by_id[experiment_id]
        if registration.parent_preregistration_hash != parent_preregistration_hash or (
            registration.registered_at >= started
        ):
            raise ValueError("experiment must bind parent and be registered before execution")
        if outcome.registration_hash != registration.registration_hash:
            raise ValueError("experiment outcome registration hash differs")
    ablation_registrations = tuple(
        value for value in ordered_registrations if value.kind is Stage6CExperimentKind.ABLATION
    )
    stress_registrations = tuple(
        value for value in ordered_registrations if value.kind is Stage6CExperimentKind.STRESS
    )
    ablation_ids = {value.scenario_id for value in ablation_registrations}
    stress_ids = {value.scenario_id for value in stress_registrations}
    if len(ablation_registrations) != len(STAGE6C_REQUIRED_ABLATION_IDS) or (
        ablation_ids != set(STAGE6C_REQUIRED_ABLATION_IDS)
    ):
        raise ValueError("required ablation closed world differs")
    if len(stress_registrations) != len(STAGE6C_REQUIRED_STRESS_IDS) or (
        stress_ids != set(STAGE6C_REQUIRED_STRESS_IDS)
    ):
        raise ValueError("required stress closed world differs")
    required_ids = ablation_ids | stress_ids
    if any(
        value.kind is Stage6CExperimentKind.EXPLORATORY and value.scenario_id in required_ids
        for value in ordered_registrations
    ):
        raise ValueError("exploratory scenario must not reuse required scenario identity")
    exploratory_count = sum(
        value.kind is Stage6CExperimentKind.EXPLORATORY for value in ordered_registrations
    )
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "parent_preregistration_hash": parent_preregistration_hash,
        "execution_started_at": started,
        "registrations": ordered_registrations,
        "outcomes": ordered_outcomes,
        "required_ablation_complete": True,
        "required_stress_complete": True,
        "exploratory_count": exploratory_count,
        "synthetic": True,
        "validation_only": True,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CExperimentLedger(**payload, ledger_hash=_hash(payload))


__all__ = [
    "STAGE6C_MINIMUM_PEERS",
    "STAGE6C_REQUIRED_ABLATION_IDS",
    "STAGE6C_REQUIRED_STRESS_IDS",
    "Stage6CExperimentKind",
    "Stage6CExperimentLedger",
    "Stage6CExperimentOutcome",
    "Stage6CExperimentOutcomeStatus",
    "Stage6CExperimentRegistration",
    "Stage6CPeerBasket",
    "Stage6CPeerBasketSet",
    "Stage6CPeerBasketStatus",
    "Stage6CPeerFallbackLevel",
    "Stage6CPeerMember",
    "Stage6CPeerSnapshot",
    "Stage6CPeerWeight",
    "build_stage6c_experiment_ledger",
    "build_stage6c_peer_basket",
    "build_stage6c_peer_basket_set",
]
