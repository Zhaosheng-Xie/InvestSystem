"""Approved Stage 4 / 4A-4 expectation, valuation, and exit semantics.

The evaluator is pure and provider-neutral.  It accepts only InvestSystem-owned
anonymous synthetic research inputs and can emit research labels, never run or
trading authority.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import (
    CanonicalModel,
    DecisionState,
    ExpectationClass,
    GateOutcome,
    HashDigest,
    PositionState,
    RuleStatus,
)

from .stage4_context_industry import Stage4RuleEvaluationState
from .stage4_gate_profit_scenarios import (
    STAGE4_4A1_RULE_BUNDLE_SHA256,
    STAGE4_4A2_RULE_BUNDLE_SHA256,
    STAGE4_4A3_RULE_BUNDLE_SHA256,
    DecimalInterval,
    Stage4GateResult,
)

STAGE4_4A4_RULE_BUNDLE_ID = "industrial_event_stage4_4a4_expectation_valuation_exit"
STAGE4_4A4_RULE_BUNDLE_VERSION = "0.1.0"
STAGE4_4A4_RULE_APPROVAL_ID = "rule_approval_stage4_4a4_expectation_valuation_exit_v0_1_0"
STAGE4_4A4_RULE_BUNDLE_SHA256 = "6ad34d6534b646eb0eb4fcab73c9da13e0738af0d3ae0d296143a48129ee1762"
STAGE4_4A4_RULES_SHA256 = "d1d2e03d78f0a78c63e073916da87f9177bb2e7151bd1d4d9ec959cd865545e2"
STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256 = (
    "8b75674537a9b8939cd259e2efb5a46752282714f19b23e181d9509ae09b919e"
)
STAGE4_4A4_RULE_VERSION = "0.1.0"
STAGE4_4A4_REQUIREMENT_IDS = ("FR-GATE-004", "FR-GATE-005", "FR-EXIT-001")

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid ASCII ID")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _freeze_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    result = tuple(_require_id(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result))


def _freeze_texts(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    result = tuple(_require_text(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result))


def _decimal(field_name: str, value: str | None) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical decimal string or None")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - regex already guards this
        raise ValueError(f"{field_name} must be finite") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


class PriorExpectationState(StrEnum):
    EXPLICITLY_ABSENT = "explicitly_absent"
    DIRECTIONAL_NONBINDING = "directional_nonbinding"
    BINDING_EXPECTED = "binding_expected"


class MarketPricingState(StrEnum):
    FULLY_REFLECTED = "fully_reflected"
    NOT_FULLY_REFLECTED = "not_fully_reflected"
    INDETERMINATE = "indeterminate"


class ValuationComponentRole(StrEnum):
    BASE_BUSINESS = "base_business"
    EVENT_INCREMENTAL = "event_incremental"


class HoldingKind(StrEnum):
    NO_POSITION = "no_position"
    SYNTHETIC_HOLDING = "synthetic_holding"


class TriggerState(StrEnum):
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class EvidenceExitKind(StrEnum):
    OBLIGATION_CANCELLED = "obligation_cancelled"
    ACCEPTANCE_FAILED = "acceptance_failed"
    DELAY_BEYOND_WINDOW = "delay_beyond_window"
    PRICE_OR_QUANTITY_REDUCED = "price_or_quantity_reduced"
    COUNTERPARTY_CREDIT_DETERIORATED = "counterparty_credit_deteriorated"
    PROFIT_BRIDGE_INVALIDATED = "profit_bridge_invalidated"


_SYSTEM_EXIT_TRIGGER_IDS = frozenset({"risk_budget_exit", "time_exit", "value_exit"})


class ExitEvaluationState(StrEnum):
    EVALUATED = "evaluated"
    BLOCKED = "blocked"


class ExitDisposition(StrEnum):
    HOLD = "HOLD"
    REUNDERWRITE_REQUIRED = "REUNDERWRITE_REQUIRED"
    EXIT_CANDIDATE = "EXIT_CANDIDATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class VersionedArtifactIdentity(CanonicalModel):
    artifact_id: str
    version: str
    as_of: datetime
    knowledge_cutoff: datetime
    supersedes_artifact_id: str | None
    declared_content_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("artifact_id", self.artifact_id)
        _require_text("version", self.version)
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        object.__setattr__(
            self,
            "knowledge_cutoff",
            normalize_utc(self.knowledge_cutoff, field_name="knowledge_cutoff"),
        )
        if self.supersedes_artifact_id is not None:
            _require_id("supersedes_artifact_id", self.supersedes_artifact_id)
        if not isinstance(self.declared_content_hash, HashDigest):
            raise TypeError("declared_content_hash must be a HashDigest")


@dataclass(frozen=True, slots=True)
class EconomicBasis(CanonicalModel):
    event_identity: str
    subject_scope: str
    product_scope: str
    currency: str
    unit: str
    effective_period: str
    obligation_basis: str
    profit_basis: str
    fcf_basis: str
    material_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "event_identity",
            "subject_scope",
            "product_scope",
            "effective_period",
            "obligation_basis",
            "profit_basis",
            "fcf_basis",
        ):
            _require_text(field_name, getattr(self, field_name))
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be an uppercase ISO-style code")
        _require_text("unit", self.unit)
        object.__setattr__(
            self,
            "material_conditions",
            _freeze_texts("material_conditions", self.material_conditions),
        )


@dataclass(frozen=True, slots=True)
class ExpectationSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    e4_first_public_at: datetime
    basis: EconomicBasis
    prior_state: PriorExpectationState
    prior_binding_interval: DecimalInterval | None
    prior_profit_interval: DecimalInterval | None
    prior_fcf_interval: DecimalInterval | None
    coverage_by_material_dimension: tuple[str, ...]
    explicit_absence_fact_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    derived_ids: tuple[str, ...]
    coverage_complete: bool = True
    conflicting: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        object.__setattr__(
            self,
            "e4_first_public_at",
            normalize_utc(self.e4_first_public_at, field_name="e4_first_public_at"),
        )
        if not isinstance(self.basis, EconomicBasis):
            raise TypeError("basis must be EconomicBasis")
        object.__setattr__(
            self,
            "prior_state",
            _coerce_enum("prior_state", PriorExpectationState, self.prior_state),
        )
        for field_name in (
            "prior_binding_interval",
            "prior_profit_interval",
            "prior_fcf_interval",
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, DecimalInterval):
                raise TypeError(f"{field_name} must be DecimalInterval or None")
        object.__setattr__(
            self,
            "coverage_by_material_dimension",
            _freeze_texts("coverage_by_material_dimension", self.coverage_by_material_dimension),
        )
        for field_name in (
            "explicit_absence_fact_ids",
            "fact_ids",
            "assumption_ids",
            "derived_ids",
        ):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class PreE4MarketContext(CanonicalModel):
    identity: VersionedArtifactIdentity
    window_start_at: datetime
    window_end_at: datetime
    price: str | None
    fully_diluted_shares: str | None
    benchmark_id: str | None
    benchmark_return: str | None
    security_return: str | None
    security_turnover: str | None
    reference_turnover: str | None
    security_price_observation_ref: str | None
    fully_diluted_shares_ref: str | None
    source_refs: tuple[str, ...]
    method_id: str | None
    method_version: str | None
    method_hash: HashDigest | None
    conflicting: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        for field_name in ("window_start_at", "window_end_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        for field_name in (
            "price",
            "fully_diluted_shares",
            "benchmark_return",
            "security_return",
            "security_turnover",
            "reference_turnover",
        ):
            _decimal(field_name, getattr(self, field_name))
        object.__setattr__(self, "source_refs", _freeze_ids("source_refs", self.source_refs))
        for field_name in (
            "benchmark_id",
            "security_price_observation_ref",
            "fully_diluted_shares_ref",
            "method_id",
            "method_version",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_text(field_name, value)
        if self.method_hash is not None and not isinstance(self.method_hash, HashDigest):
            raise TypeError("method_hash must be HashDigest or None")


@dataclass(frozen=True, slots=True)
class ValuationComponent(CanonicalModel):
    component_id: str
    economic_key: str
    role: ValuationComponentRole
    period: str
    fact_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    binding_public_obligation: bool = True
    unbound_growth_assumption: bool = False
    scenario_scope: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_id("component_id", self.component_id)
        _require_id("economic_key", self.economic_key)
        object.__setattr__(self, "role", _coerce_enum("role", ValuationComponentRole, self.role))
        _require_text("period", self.period)
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))
        object.__setattr__(
            self, "assumption_ids", _freeze_ids("assumption_ids", self.assumption_ids)
        )
        object.__setattr__(
            self,
            "scenario_scope",
            _freeze_texts("scenario_scope", self.scenario_scope),
        )


@dataclass(frozen=True, slots=True)
class ScenarioEquityValueSet(CanonicalModel):
    base: DecimalInterval
    downside: DecimalInterval
    upside: DecimalInterval
    stress: DecimalInterval

    def __post_init__(self) -> None:
        if any(
            not isinstance(getattr(self, field_name), DecimalInterval)
            for field_name in ("base", "downside", "upside", "stress")
        ):
            raise TypeError("all scenario values must be DecimalInterval")


@dataclass(frozen=True, slots=True)
class Stage4ValuationSet(CanonicalModel):
    identity: VersionedArtifactIdentity
    basis: EconomicBasis
    primary_method_id: str | None
    method_version: str | None
    method_hash: HashDigest | None
    explicit_input_refs: tuple[str, ...]
    base_business_equity_value: DecimalInterval | None
    event_finite_life_value: DecimalInterval | None
    scenario_equity_values: ScenarioEquityValueSet | None
    fully_diluted_shares: str | None
    tax_basis: str | None
    minority_basis: str | None
    ownership_basis: str | None
    components: tuple[ValuationComponent, ...]
    explicit_discount_factors: bool = True
    single_event_terminal_value_used: bool = False
    calculation_graph_acyclic: bool = True
    cross_method_selected_for_pass: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        if not isinstance(self.basis, EconomicBasis):
            raise TypeError("basis must be EconomicBasis")
        if self.method_hash is not None and not isinstance(self.method_hash, HashDigest):
            raise TypeError("method_hash must be HashDigest or None")
        for field_name in (
            "primary_method_id",
            "method_version",
            "tax_basis",
            "minority_basis",
            "ownership_basis",
        ):
            value = getattr(self, field_name)
            if value is not None:
                _require_text(field_name, value)
        object.__setattr__(
            self,
            "explicit_input_refs",
            _freeze_ids("explicit_input_refs", self.explicit_input_refs),
        )
        for field_name in ("base_business_equity_value", "event_finite_life_value"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, DecimalInterval):
                raise TypeError(f"{field_name} must be DecimalInterval or None")
        if self.scenario_equity_values is not None and not isinstance(
            self.scenario_equity_values, ScenarioEquityValueSet
        ):
            raise TypeError("scenario_equity_values must be ScenarioEquityValueSet or None")
        _decimal("fully_diluted_shares", self.fully_diluted_shares)
        if not isinstance(self.components, (list, tuple)) or any(
            not isinstance(item, ValuationComponent) for item in self.components
        ):
            raise TypeError("components must contain ValuationComponent values")
        object.__setattr__(self, "components", tuple(self.components))


@dataclass(frozen=True, slots=True)
class SyntheticResearchPriceAssumption(CanonicalModel):
    identity: VersionedArtifactIdentity
    price: str | None
    fully_diluted_shares: str | None
    explicit_cost_rate: str | None
    explicit_slippage_rate: str | None
    currency: str
    unit: str
    source_fixture_ref: str | None
    synthetic: bool = True
    not_first_actual_executable_price: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        for field_name in (
            "price",
            "fully_diluted_shares",
            "explicit_cost_rate",
            "explicit_slippage_rate",
        ):
            _decimal(field_name, getattr(self, field_name))
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be an uppercase ISO-style code")
        _require_text("unit", self.unit)
        if self.source_fixture_ref is not None:
            _require_id("source_fixture_ref", self.source_fixture_ref)


@dataclass(frozen=True, slots=True)
class ProofPlan(CanonicalModel):
    identity: VersionedArtifactIdentity
    observable_falsifier_ids: tuple[str, ...]
    next_public_verification_event_id: str | None
    verification_within_trading_days: int | None
    trading_calendar_version: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        object.__setattr__(
            self,
            "observable_falsifier_ids",
            _freeze_ids("observable_falsifier_ids", self.observable_falsifier_ids),
        )
        if self.next_public_verification_event_id is not None:
            _require_id("next_public_verification_event_id", self.next_public_verification_event_id)
        if self.trading_calendar_version is not None:
            _require_text("trading_calendar_version", self.trading_calendar_version)
        if self.verification_within_trading_days is not None and (
            isinstance(self.verification_within_trading_days, bool)
            or not isinstance(self.verification_within_trading_days, int)
            or self.verification_within_trading_days < 0
        ):
            raise ValueError("verification_within_trading_days must be non-negative or None")


@dataclass(frozen=True, slots=True)
class EvidenceExitTrigger(CanonicalModel):
    trigger_id: str
    kind: EvidenceExitKind
    state: TriggerState
    observable_condition: str
    evaluation_window: str
    source_type: str
    component_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    preregistered: bool = True

    def __post_init__(self) -> None:
        _require_id("trigger_id", self.trigger_id)
        object.__setattr__(self, "kind", _coerce_enum("kind", EvidenceExitKind, self.kind))
        object.__setattr__(self, "state", _coerce_enum("state", TriggerState, self.state))
        for field_name in ("observable_condition", "evaluation_window", "source_type"):
            _require_text(field_name, getattr(self, field_name))
        object.__setattr__(self, "component_ids", _freeze_ids("component_ids", self.component_ids))
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))


@dataclass(frozen=True, slots=True)
class SyntheticHoldingSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    case_id: str
    registered_account_loss_budget_amount: str | None
    current_actual_loss_amount: str | None
    currency: str
    established_rule_hash: HashDigest
    established_valuation_hash: HashDigest
    synthetic: bool = True
    authorizes_execution: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.identity, VersionedArtifactIdentity):
            raise TypeError("identity must be VersionedArtifactIdentity")
        _require_id("case_id", self.case_id)
        for field_name in (
            "registered_account_loss_budget_amount",
            "current_actual_loss_amount",
        ):
            _decimal(field_name, getattr(self, field_name))
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be an uppercase ISO-style code")
        for field_name in ("established_rule_hash", "established_valuation_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage4ExitInput(CanonicalModel):
    holding_kind: HoldingKind
    holding_snapshot: SyntheticHoldingSnapshot | None
    evidence_triggers: tuple[EvidenceExitTrigger, ...]
    elapsed_trading_days: int | None
    trading_calendar_version: str | None
    preregistered_verification_event_confirmed: bool | None
    current_market_cap: str | None
    current_base_value_lower: str | None
    new_e5_e6_value_evidence: bool | None
    reunderwriting_passed: bool | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "holding_kind", _coerce_enum("holding_kind", HoldingKind, self.holding_kind)
        )
        if self.holding_snapshot is not None and not isinstance(
            self.holding_snapshot, SyntheticHoldingSnapshot
        ):
            raise TypeError("holding_snapshot must be SyntheticHoldingSnapshot or None")
        if not isinstance(self.evidence_triggers, (list, tuple)) or any(
            not isinstance(item, EvidenceExitTrigger) for item in self.evidence_triggers
        ):
            raise TypeError("evidence_triggers must contain EvidenceExitTrigger values")
        object.__setattr__(
            self,
            "evidence_triggers",
            tuple(
                sorted(self.evidence_triggers, key=lambda item: (item.kind.value, item.trigger_id))
            ),
        )
        if self.elapsed_trading_days is not None and (
            isinstance(self.elapsed_trading_days, bool)
            or not isinstance(self.elapsed_trading_days, int)
            or self.elapsed_trading_days < 0
        ):
            raise ValueError("elapsed_trading_days must be non-negative or None")
        for field_name in ("current_market_cap", "current_base_value_lower"):
            _decimal(field_name, getattr(self, field_name))
        if self.trading_calendar_version is not None:
            _require_text("trading_calendar_version", self.trading_calendar_version)


@dataclass(frozen=True, slots=True)
class Stage4ExpectationValuationExitCase(CanonicalModel):
    case_id: str
    knowledge_cutoff: datetime
    e4_first_public_at: datetime
    upstream_gate_result: Stage4GateResult
    e4_basis: EconomicBasis
    e4_binding_obligation_interval: DecimalInterval
    e4_incremental_profit_interval: DecimalInterval
    e4_incremental_fcf_interval: DecimalInterval
    expectation_snapshot: ExpectationSnapshot
    pre_e4_market_context: PreE4MarketContext
    valuation_set: Stage4ValuationSet
    price_assumption: SyntheticResearchPriceAssumption
    proof_plan: ProofPlan
    exit_input: Stage4ExitInput
    anonymous_synthetic_fixture: bool = True
    reads_kb_internal_state: bool = False

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        for field_name in ("knowledge_cutoff", "e4_first_public_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.upstream_gate_result, Stage4GateResult):
            raise TypeError("upstream_gate_result must be Stage4GateResult")
        if not isinstance(self.e4_basis, EconomicBasis):
            raise TypeError("e4_basis must be EconomicBasis")
        for field_name in (
            "e4_binding_obligation_interval",
            "e4_incremental_profit_interval",
            "e4_incremental_fcf_interval",
        ):
            if not isinstance(getattr(self, field_name), DecimalInterval):
                raise TypeError(f"{field_name} must be DecimalInterval")
        expected = (
            ("expectation_snapshot", ExpectationSnapshot),
            ("pre_e4_market_context", PreE4MarketContext),
            ("valuation_set", Stage4ValuationSet),
            ("price_assumption", SyntheticResearchPriceAssumption),
            ("proof_plan", ProofPlan),
            ("exit_input", Stage4ExitInput),
        )
        for field_name, expected_type in expected:
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} must be {expected_type.__name__}")


ArtifactValue = (
    ExpectationSnapshot
    | PreE4MarketContext
    | Stage4ValuationSet
    | SyntheticResearchPriceAssumption
    | ProofPlan
    | SyntheticHoldingSnapshot
)


def stage4_artifact_content_sha256(value: ArtifactValue) -> str:
    """Hash one 4A-4 artifact excluding its self-referential declared hash."""

    projected = value.to_json_value()
    identity = projected.get("identity")
    if not isinstance(identity, dict):
        raise TypeError("artifact identity projection must be an object")
    del identity["declared_content_hash"]
    return canonical_sha256(projected)


def _bound_identity(
    identity: VersionedArtifactIdentity, content_hash: str
) -> VersionedArtifactIdentity:
    return replace(identity, declared_content_hash=_hash(content_hash))


def bind_expectation_snapshot(value: ExpectationSnapshot) -> ExpectationSnapshot:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


def bind_pre_e4_market_context(value: PreE4MarketContext) -> PreE4MarketContext:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


def bind_stage4_valuation_set(value: Stage4ValuationSet) -> Stage4ValuationSet:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


def bind_synthetic_price_assumption(
    value: SyntheticResearchPriceAssumption,
) -> SyntheticResearchPriceAssumption:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


def bind_proof_plan(value: ProofPlan) -> ProofPlan:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


def bind_synthetic_holding_snapshot(value: SyntheticHoldingSnapshot) -> SyntheticHoldingSnapshot:
    return replace(
        value, identity=_bound_identity(value.identity, stage4_artifact_content_sha256(value))
    )


@dataclass(frozen=True, slots=True)
class Stage4A4GateAssessment(CanonicalModel):
    rule_id: str
    evaluation_state: Stage4RuleEvaluationState
    outcome: GateOutcome | None
    reason_codes: tuple[str, ...]
    rule_hash: HashDigest
    rule_version: str = field(default=STAGE4_4A4_RULE_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.rule_id not in ("FR-GATE-004", "FR-GATE-005"):
            raise ValueError("rule_id must be a 4A-4 gate rule")
        object.__setattr__(
            self,
            "evaluation_state",
            _coerce_enum("evaluation_state", Stage4RuleEvaluationState, self.evaluation_state),
        )
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        object.__setattr__(self, "reason_codes", _freeze_ids("reason_codes", self.reason_codes))
        if not isinstance(self.rule_hash, HashDigest):
            raise TypeError("rule_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage4A4GateResult(CanonicalModel):
    gate_3: Stage4A4GateAssessment
    gate_4: Stage4A4GateAssessment
    overall_outcome: GateOutcome
    public_expectation_class: ExpectationClass | None
    market_pricing_state: MarketPricingState | None
    market_implied_event_value: DecimalInterval | None
    net_base_remaining_return: str | None
    net_downside_return: str | None
    downside_loss: str | None
    reward_to_downside: str | None
    research_decision_label: DecisionState | None
    position_state: PositionState = field(default=PositionState.FLAT, init=False)
    target_weight: None = field(default=None, init=False)
    approved_weight: None = field(default=None, init=False)
    actual_weight: None = field(default=None, init=False)
    approver: None = field(default=None, init=False)
    order_intent: None = field(default=None, init=False)
    full_stage4_capability: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class Stage4ExitResult(CanonicalModel):
    evaluation_state: ExitEvaluationState
    disposition: ExitDisposition | None
    trigger_states: tuple[tuple[str, TriggerState], ...]
    confirmed_trigger_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    rule_hash: HashDigest
    rule_version: str = field(default=STAGE4_4A4_RULE_VERSION, init=False)
    order_intent: None = field(default=None, init=False)
    target_weight: None = field(default=None, init=False)
    authorizes_execution: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "evaluation_state",
            _coerce_enum("evaluation_state", ExitEvaluationState, self.evaluation_state),
        )
        if self.disposition is not None:
            object.__setattr__(
                self,
                "disposition",
                _coerce_enum("disposition", ExitDisposition, self.disposition),
            )
        object.__setattr__(
            self,
            "confirmed_trigger_ids",
            _freeze_ids("confirmed_trigger_ids", self.confirmed_trigger_ids),
        )
        object.__setattr__(self, "reason_codes", _freeze_ids("reason_codes", self.reason_codes))
        if not isinstance(self.rule_hash, HashDigest):
            raise TypeError("rule_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage4ExpectationValuationExitResult(CanonicalModel):
    case_id: str
    gate_result: Stage4A4GateResult
    exit_result: Stage4ExitResult
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    replay_hash: HashDigest
    approval_scope: RuleApprovalScope = field(
        default=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION, init=False
    )
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)


class Stage4ExpectationValuationExitCompatibilityError(ValueError):
    """Stable fail-closed rejection for a non-approved 4A-4 capability."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


_STAGE4_4A4_RULE_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4ExpectationValuationExitRules:
    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    minimum_net_base_remaining_return: Decimal
    minimum_reward_to_downside: Decimal
    maximum_proof_window_trading_days: int

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        minimum_net_base_remaining_return: Decimal,
        minimum_reward_to_downside: Decimal,
        maximum_proof_window_trading_days: int,
    ) -> None:
        if _issuer is not _STAGE4_4A4_RULE_ISSUER:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_RULE_ISSUER_INVALID",
                "4A-4 typed rules require an exact approved capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(
            self, "minimum_net_base_remaining_return", minimum_net_base_remaining_return
        )
        object.__setattr__(self, "minimum_reward_to_downside", minimum_reward_to_downside)
        object.__setattr__(
            self, "maximum_proof_window_trading_days", maximum_proof_window_trading_days
        )

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage4ExpectationValuationExitRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be ApprovedRuleCapability")
        identity = (
            "industrial_bottleneck_event",
            STAGE4_4A4_RULE_BUNDLE_ID,
            STAGE4_4A4_RULE_BUNDLE_VERSION,
        )
        if (document.strategy_id, document.bundle_id, document.bundle_version) != identity or (
            capability.strategy_id,
            capability.bundle_id,
            capability.bundle_version,
        ) != identity:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_RULE_IDENTITY_UNSUPPORTED", "identity differs from approved 4A-4"
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_RULE_DOCUMENT_NOT_APPROVED", "document must declare approved"
            )
        if capability.approval_scope is not RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_RULE_SCOPE_UNSUPPORTED", "only Stage 4 synthetic research is approved"
            )
        if capability.bundle_hash != document.bundle_hash() or (
            document.bundle_hash().value != STAGE4_4A4_RULE_BUNDLE_SHA256
        ):
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_RULE_HASH_UNSUPPORTED", "capability must bind the pinned bundle"
            )
        if capability.approval_id != STAGE4_4A4_RULE_APPROVAL_ID:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_APPROVAL_ID_UNSUPPORTED", "owner approval ID differs"
            )
        if capability.approval_record_hash.value != STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_APPROVAL_RECORD_UNSUPPORTED", "owner approval record differs"
            )
        if canonical_sha256(document.rules) != STAGE4_4A4_RULES_SHA256:
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_MACHINE_SEMANTICS_UNSUPPORTED", "machine semantics differ"
            )
        modules = document.rules.get("rule_modules")
        dependencies = document.rules.get("approved_upstream_dependencies")
        if not isinstance(modules, Mapping) or set(modules) != set(STAGE4_4A4_REQUIREMENT_IDS):
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_MACHINE_SEMANTICS_INVALID", "rule module set differs"
            )
        expected_dependencies = {
            "4A-1": STAGE4_4A1_RULE_BUNDLE_SHA256,
            "4A-2": STAGE4_4A2_RULE_BUNDLE_SHA256,
            "4A-3": STAGE4_4A3_RULE_BUNDLE_SHA256,
        }
        if not isinstance(dependencies, Mapping):
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_UPSTREAM_DEPENDENCY_UNSUPPORTED",
                "4A-4 must bind exact approved 4A-1 through 4A-3 bundles",
            )
        for batch, digest in expected_dependencies.items():
            dependency = dependencies.get(batch)
            if not isinstance(dependency, Mapping) or dependency.get("bundle_hash") != digest:
                raise Stage4ExpectationValuationExitCompatibilityError(
                    "STAGE4_4A4_UPSTREAM_DEPENDENCY_UNSUPPORTED",
                    "4A-4 must bind exact approved 4A-1 through 4A-3 bundles",
                )
        gate4 = modules["FR-GATE-005"]
        if not isinstance(gate4, Mapping):
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_MACHINE_SEMANTICS_INVALID", "Gate 4 module must be an object"
            )
        calculation = gate4.get("gate_4_calculation")
        proof = gate4.get("proof_window")
        if (
            not isinstance(calculation, Mapping)
            or calculation.get("minimum_net_base_remaining_return") != "0.15"
            or calculation.get("minimum_reward_to_downside") != "2.00"
            or not isinstance(proof, Mapping)
            or proof.get("maximum_trading_days") != 120
        ):
            raise Stage4ExpectationValuationExitCompatibilityError(
                "STAGE4_4A4_THRESHOLD_UNSUPPORTED", "approved thresholds differ"
            )
        return cls(
            _issuer=_STAGE4_4A4_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            minimum_net_base_remaining_return=Decimal("0.15"),
            minimum_reward_to_downside=Decimal("2.00"),
            maximum_proof_window_trading_days=120,
        )


def _assessment(
    rule_id: str,
    outcome: GateOutcome,
    reason: str,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> Stage4A4GateAssessment:
    return Stage4A4GateAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(reason,),
        rule_hash=rules.bundle_hash,
    )


def _not_evaluated(
    rule_id: str,
    reason: str,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> Stage4A4GateAssessment:
    return Stage4A4GateAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
        outcome=None,
        reason_codes=(reason,),
        rule_hash=rules.bundle_hash,
    )


def _interval_decimal(value: DecimalInterval) -> tuple[Decimal, Decimal]:
    return Decimal(value.lower), Decimal(value.upper)


def _artifact_failure(case: Stage4ExpectationValuationExitCase) -> str | None:
    if not case.anonymous_synthetic_fixture or case.reads_kb_internal_state:
        return "STAGE4_4A4_INPUT_SCOPE_OR_CROSS_REPOSITORY_VIOLATION"
    artifacts: list[ArtifactValue] = [
        case.expectation_snapshot,
        case.pre_e4_market_context,
        case.valuation_set,
        case.price_assumption,
        case.proof_plan,
    ]
    identities: set[str] = set()
    for artifact in artifacts:
        if artifact.identity.artifact_id in identities:
            return "STAGE4_4A4_ARTIFACT_ID_DUPLICATED"
        identities.add(artifact.identity.artifact_id)
        if artifact.identity.declared_content_hash.value != stage4_artifact_content_sha256(
            artifact
        ):
            return "STAGE4_4A4_ARTIFACT_HASH_MISMATCH"
        if (
            artifact.identity.as_of > artifact.identity.knowledge_cutoff
            or artifact.identity.knowledge_cutoff > case.knowledge_cutoff
        ):
            return "STAGE4_4A4_ARTIFACT_PIT_INVALID"
    return None


def _valuation_failure(value: Stage4ValuationSet) -> tuple[GateOutcome, str] | None:
    if (
        not value.calculation_graph_acyclic
        or value.single_event_terminal_value_used
        or value.cross_method_selected_for_pass
    ):
        return GateOutcome.BLOCKED, "VALUATION_GRAPH_DOUBLE_COUNT_OR_METHOD_SELECTION"
    if not value.explicit_discount_factors:
        return GateOutcome.ABSTAIN, "VALUATION_DISCOUNT_FACTORS_MISSING"
    if (
        value.primary_method_id is None
        or value.method_version is None
        or value.method_hash is None
        or not value.explicit_input_refs
        or value.base_business_equity_value is None
        or value.event_finite_life_value is None
        or value.scenario_equity_values is None
        or value.fully_diluted_shares is None
        or value.tax_basis is None
        or value.minority_basis is None
        or value.ownership_basis is None
        or not value.components
    ):
        return GateOutcome.ABSTAIN, "VALUATION_REQUIRED_INPUT_MISSING"
    component_ids = [item.component_id for item in value.components]
    economic_keys = [item.economic_key for item in value.components]
    if len(component_ids) != len(set(component_ids)) or len(economic_keys) != len(
        set(economic_keys)
    ):
        return GateOutcome.BLOCKED, "VALUATION_COMPONENT_DOUBLE_COUNT"
    for component in value.components:
        if not (component.fact_ids or component.assumption_ids):
            return GateOutcome.ABSTAIN, "VALUATION_COMPONENT_SUPPORT_MISSING"
        if component.unbound_growth_assumption and (
            component.role is not ValuationComponentRole.EVENT_INCREMENTAL
            or component.scenario_scope != ("upside",)
        ):
            return GateOutcome.BLOCKED, "UNBOUND_GROWTH_OUTSIDE_UPSIDE"
        if (
            component.role is ValuationComponentRole.EVENT_INCREMENTAL
            and "base" in component.scenario_scope
            and not component.binding_public_obligation
        ):
            return GateOutcome.BLOCKED, "UNBOUND_EVENT_VALUE_IN_BASE"
    values = value.scenario_equity_values
    assert values is not None
    upside = _interval_decimal(values.upside)
    base = _interval_decimal(values.base)
    downside = _interval_decimal(values.downside)
    stress = _interval_decimal(values.stress)
    if not (
        upside[0] >= base[0] >= downside[0] >= stress[0]
        and upside[1] >= base[1] >= downside[1] >= stress[1]
    ):
        return GateOutcome.BLOCKED, "VALUATION_SCENARIO_INTERVAL_ORDER_INVALID"
    return None


def _evaluate_gate3(
    case: Stage4ExpectationValuationExitCase,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> tuple[
    Stage4A4GateAssessment,
    ExpectationClass | None,
    MarketPricingState | None,
    DecimalInterval | None,
]:
    upstream = case.upstream_gate_result
    if (
        upstream.case_id != case.case_id
        or upstream.rule_bundle_hash.value != STAGE4_4A3_RULE_BUNDLE_SHA256
    ):
        return (
            _assessment("FR-GATE-004", GateOutcome.BLOCKED, "GATE3_UPSTREAM_IDENTITY_DRIFT", rules),
            None,
            None,
            None,
        )
    if not all(
        assessment.outcome is GateOutcome.PASS
        for assessment in (upstream.gate_1, upstream.scenario_validation, upstream.gate_2)
    ):
        return (
            _not_evaluated("FR-GATE-004", "PRIOR_GATE_NOT_PASS", rules),
            None,
            None,
            None,
        )
    snapshot = case.expectation_snapshot
    market = case.pre_e4_market_context
    valuation = case.valuation_set
    if snapshot.e4_first_public_at != case.e4_first_public_at:
        return (
            _assessment("FR-GATE-004", GateOutcome.BLOCKED, "EXPECTATION_E4_IDENTITY_DRIFT", rules),
            None,
            None,
            None,
        )
    if snapshot.identity.as_of >= case.e4_first_public_at or market.window_end_at >= (
        case.e4_first_public_at
    ):
        return (
            _assessment("FR-GATE-004", GateOutcome.BLOCKED, "GATE3_POST_E4_BACKFILL", rules),
            None,
            None,
            None,
        )
    if market.window_start_at > market.window_end_at:
        return (
            _assessment("FR-GATE-004", GateOutcome.BLOCKED, "MARKET_CONTEXT_WINDOW_INVALID", rules),
            None,
            None,
            None,
        )
    if (
        snapshot.basis.currency != case.e4_basis.currency
        or snapshot.basis.unit != case.e4_basis.unit
    ):
        return (
            _assessment("FR-GATE-004", GateOutcome.BLOCKED, "GATE3_CURRENCY_OR_UNIT_DRIFT", rules),
            None,
            None,
            None,
        )
    if snapshot.basis != case.e4_basis or valuation.basis != case.e4_basis:
        return (
            _assessment(
                "FR-GATE-004", GateOutcome.ABSTAIN, "GATE3_ECONOMIC_BASIS_NOT_COMPARABLE", rules
            ),
            ExpectationClass.UNKNOWN,
            MarketPricingState.INDETERMINATE,
            None,
        )
    if snapshot.conflicting or market.conflicting or not snapshot.coverage_complete:
        return (
            _assessment(
                "FR-GATE-004", GateOutcome.ABSTAIN, "GATE3_PRIOR_OR_MARKET_CONTEXT_UNKNOWN", rules
            ),
            ExpectationClass.UNKNOWN,
            MarketPricingState.INDETERMINATE,
            None,
        )
    market_required = (
        market.price,
        market.fully_diluted_shares,
        market.benchmark_return,
        market.security_return,
        market.security_turnover,
        market.reference_turnover,
        market.security_price_observation_ref,
        market.fully_diluted_shares_ref,
        market.method_id,
        market.method_version,
        market.method_hash,
    )
    if any(item is None for item in market_required) or not market.source_refs:
        return (
            _assessment("FR-GATE-004", GateOutcome.ABSTAIN, "PRE_E4_MARKET_CONTEXT_MISSING", rules),
            None,
            MarketPricingState.INDETERMINATE,
            None,
        )
    assert market.price is not None and market.fully_diluted_shares is not None
    assert market.security_turnover is not None and market.reference_turnover is not None
    if (
        Decimal(market.price) <= 0
        or Decimal(market.fully_diluted_shares) <= 0
        or Decimal(market.security_turnover) < 0
        or Decimal(market.reference_turnover) < 0
    ):
        return (
            _assessment(
                "FR-GATE-004",
                GateOutcome.BLOCKED,
                "PRE_E4_MARKET_VALUE_OR_TURNOVER_INVALID",
                rules,
            ),
            None,
            None,
            None,
        )
    valuation_failure = _valuation_failure(valuation)
    if valuation_failure is not None:
        outcome, reason = valuation_failure
        return _assessment("FR-GATE-004", outcome, reason, rules), None, None, None
    assert valuation.base_business_equity_value is not None
    assert valuation.event_finite_life_value is not None
    market_cap = Decimal(market.price) * Decimal(market.fully_diluted_shares)
    base_lower, base_upper = _interval_decimal(valuation.base_business_equity_value)
    implied = DecimalInterval(str(market_cap - base_upper), str(market_cap - base_lower))
    implied_lower, implied_upper = _interval_decimal(implied)
    event_lower, event_upper = _interval_decimal(valuation.event_finite_life_value)
    if implied_lower >= event_upper:
        pricing = MarketPricingState.FULLY_REFLECTED
    elif implied_upper < event_lower:
        pricing = MarketPricingState.NOT_FULLY_REFLECTED
    else:
        pricing = MarketPricingState.INDETERMINATE
    e4_binding_lower, _ = _interval_decimal(case.e4_binding_obligation_interval)
    e4_profit_lower, e4_profit_upper = _interval_decimal(case.e4_incremental_profit_interval)
    e4_fcf_lower, e4_fcf_upper = _interval_decimal(case.e4_incremental_fcf_interval)
    if snapshot.prior_state is PriorExpectationState.EXPLICITLY_ABSENT:
        expectation = (
            ExpectationClass.UNEXPECTED
            if snapshot.explicit_absence_fact_ids
            and e4_binding_lower > 0
            and e4_profit_lower > 0
            and e4_fcf_lower > 0
            else ExpectationClass.UNKNOWN
        )
    elif snapshot.prior_state is PriorExpectationState.DIRECTIONAL_NONBINDING:
        expectation = ExpectationClass.UNKNOWN
    elif (
        snapshot.prior_profit_interval is None
        or snapshot.prior_fcf_interval is None
        or snapshot.prior_binding_interval is None
    ):
        expectation = ExpectationClass.UNKNOWN
    else:
        _, prior_profit_upper = _interval_decimal(snapshot.prior_profit_interval)
        prior_fcf_lower, prior_fcf_upper = _interval_decimal(snapshot.prior_fcf_interval)
        if (
            e4_profit_lower > prior_profit_upper
            and e4_fcf_lower >= prior_fcf_lower
            and e4_fcf_upper >= prior_fcf_upper
        ):
            expectation = ExpectationClass.PARTIALLY_PRICED
        elif e4_profit_upper <= prior_profit_upper:
            expectation = ExpectationClass.FULLY_PRICED
        else:
            expectation = ExpectationClass.UNKNOWN
    if pricing is MarketPricingState.FULLY_REFLECTED:
        outcome, reason = GateOutcome.REJECT, "GATE3_MARKET_FULLY_REFLECTED"
    elif expectation is ExpectationClass.FULLY_PRICED:
        outcome, reason = GateOutcome.REJECT, "GATE3_ECONOMIC_RESULT_FULLY_PRICED"
    elif pricing is MarketPricingState.INDETERMINATE or expectation is ExpectationClass.UNKNOWN:
        outcome, reason = GateOutcome.ABSTAIN, "GATE3_EXPECTATION_OR_PRICING_INDETERMINATE"
    else:
        outcome, reason = GateOutcome.PASS, "GATE3_POSITIVE_GAP_NOT_FULLY_REFLECTED"
    return _assessment("FR-GATE-004", outcome, reason, rules), expectation, pricing, implied


def _evaluate_gate4(
    case: Stage4ExpectationValuationExitCase,
    gate3: Stage4A4GateAssessment,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> tuple[Stage4A4GateAssessment, tuple[Decimal, Decimal, Decimal, Decimal] | None]:
    if gate3.outcome is not GateOutcome.PASS:
        return _not_evaluated("FR-GATE-005", "PRIOR_GATE_NOT_PASS", rules), None
    valuation = case.valuation_set
    failure = _valuation_failure(valuation)
    if failure is not None:
        outcome, reason = failure
        return _assessment("FR-GATE-005", outcome, reason, rules), None
    price = case.price_assumption
    if not price.synthetic or not price.not_first_actual_executable_price:
        return (
            _assessment(
                "FR-GATE-005", GateOutcome.BLOCKED, "REAL_OR_EXECUTABLE_PRICE_FORBIDDEN", rules
            ),
            None,
        )
    if price.currency != valuation.basis.currency or price.unit != valuation.basis.unit:
        return _assessment(
            "FR-GATE-005", GateOutcome.BLOCKED, "GATE4_PRICE_UNIT_DRIFT", rules
        ), None
    required = (
        price.price,
        price.fully_diluted_shares,
        price.explicit_cost_rate,
        price.explicit_slippage_rate,
        price.source_fixture_ref,
    )
    if any(item is None for item in required):
        return _assessment(
            "FR-GATE-005", GateOutcome.ABSTAIN, "GATE4_PRICE_INPUT_MISSING", rules
        ), None
    assert price.price is not None and price.fully_diluted_shares is not None
    assert price.explicit_cost_rate is not None and price.explicit_slippage_rate is not None
    market_cap = Decimal(price.price) * Decimal(price.fully_diluted_shares)
    friction = Decimal(price.explicit_cost_rate) + Decimal(price.explicit_slippage_rate)
    if market_cap <= 0 or Decimal(price.fully_diluted_shares) <= 0 or friction < 0:
        return _assessment(
            "FR-GATE-005", GateOutcome.BLOCKED, "GATE4_PRICE_OR_FRICTION_INVALID", rules
        ), None
    if valuation.fully_diluted_shares != price.fully_diluted_shares:
        return _assessment(
            "FR-GATE-005", GateOutcome.BLOCKED, "GATE4_SHARE_BASIS_DRIFT", rules
        ), None
    values = valuation.scenario_equity_values
    assert values is not None
    base_value = Decimal(values.base.lower)
    downside_value = Decimal(values.downside.lower)
    upside_value = Decimal(values.upside.lower)
    net_base = base_value / market_cap - Decimal(1) - friction
    net_downside = downside_value / market_cap - Decimal(1) - friction
    downside_loss = abs(min(Decimal(0), net_downside))
    if downside_loss == 0:
        return (
            _assessment("FR-GATE-005", GateOutcome.ABSTAIN, "GATE4_DOWNSIDE_LOSS_ZERO", rules),
            (net_base, net_downside, downside_loss, Decimal(0)),
        )
    reward = net_base / downside_loss
    proof = case.proof_plan
    if (
        len(proof.observable_falsifier_ids) < 2
        or proof.next_public_verification_event_id is None
        or proof.verification_within_trading_days is None
        or proof.trading_calendar_version is None
    ):
        return (
            _assessment("FR-GATE-005", GateOutcome.ABSTAIN, "GATE4_PROOF_PLAN_MISSING", rules),
            (net_base, net_downside, downside_loss, reward),
        )
    if proof.verification_within_trading_days > rules.maximum_proof_window_trading_days:
        return (
            _assessment("FR-GATE-005", GateOutcome.REJECT, "GATE4_PROOF_WINDOW_TOO_LONG", rules),
            (net_base, net_downside, downside_loss, reward),
        )
    if (
        net_base < rules.minimum_net_base_remaining_return
        or reward < rules.minimum_reward_to_downside
    ):
        upside_return = upside_value / market_cap - Decimal(1) - friction
        reason = (
            "GATE4_ONLY_UPSIDE_REACHES_THRESHOLD"
            if upside_return >= rules.minimum_net_base_remaining_return
            else "GATE4_BASE_RETURN_OR_REWARD_BELOW_THRESHOLD"
        )
        return (
            _assessment("FR-GATE-005", GateOutcome.REJECT, reason, rules),
            (net_base, net_downside, downside_loss, reward),
        )
    return (
        _assessment(
            "FR-GATE-005", GateOutcome.PASS, "GATE4_SYNTHETIC_RETURN_AND_REWARD_PASS", rules
        ),
        (net_base, net_downside, downside_loss, reward),
    )


def _blocked_exit(
    reason: str, rules: ApprovedStage4ExpectationValuationExitRules
) -> Stage4ExitResult:
    return Stage4ExitResult(
        evaluation_state=ExitEvaluationState.BLOCKED,
        disposition=None,
        trigger_states=(),
        confirmed_trigger_ids=(),
        reason_codes=(reason,),
        rule_hash=rules.bundle_hash,
    )


def _evaluate_exit(
    case: Stage4ExpectationValuationExitCase,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> Stage4ExitResult:
    value = case.exit_input
    if value.holding_kind is HoldingKind.NO_POSITION:
        if value.holding_snapshot is not None:
            return _blocked_exit("EXIT_NO_POSITION_WITH_HOLDING_SNAPSHOT", rules)
        return Stage4ExitResult(
            evaluation_state=ExitEvaluationState.EVALUATED,
            disposition=ExitDisposition.NOT_APPLICABLE,
            trigger_states=(),
            confirmed_trigger_ids=(),
            reason_codes=("EXIT_NO_POSITION",),
            rule_hash=rules.bundle_hash,
        )
    holding = value.holding_snapshot
    if holding is None:
        return _blocked_exit("EXIT_SYNTHETIC_HOLDING_MISSING", rules)
    if (
        holding.case_id != case.case_id
        or not holding.synthetic
        or holding.authorizes_execution
        or holding.established_rule_hash.value != STAGE4_4A4_RULE_BUNDLE_SHA256
        or holding.established_valuation_hash != case.valuation_set.identity.declared_content_hash
        or holding.identity.declared_content_hash.value != stage4_artifact_content_sha256(holding)
        or holding.identity.as_of > holding.identity.knowledge_cutoff
        or holding.identity.knowledge_cutoff > case.knowledge_cutoff
    ):
        return _blocked_exit("EXIT_HOLDING_IDENTITY_OR_AUTHORITY_INVALID", rules)
    trigger_ids = [item.trigger_id for item in value.evidence_triggers]
    trigger_kinds = [item.kind for item in value.evidence_triggers]
    if (
        len(trigger_ids) != len(set(trigger_ids))
        or len(trigger_kinds) != len(set(trigger_kinds))
        or any(trigger_id in _SYSTEM_EXIT_TRIGGER_IDS for trigger_id in trigger_ids)
    ):
        return _blocked_exit("EXIT_EVIDENCE_TRIGGER_ID_OR_KIND_DUPLICATED", rules)
    if any(not item.preregistered for item in value.evidence_triggers):
        return _blocked_exit("EXIT_EVIDENCE_TRIGGER_NOT_PREREGISTERED", rules)
    states: list[tuple[str, TriggerState]] = [
        (item.trigger_id, item.state) for item in value.evidence_triggers
    ]
    confirmed = [
        item.trigger_id
        for item in value.evidence_triggers
        if item.state is TriggerState.CONFIRMED and item.fact_ids
    ]
    unknown = any(
        item.state is TriggerState.UNKNOWN
        or (item.state is TriggerState.CONFIRMED and not item.fact_ids)
        for item in value.evidence_triggers
    )
    if set(trigger_kinds) != set(EvidenceExitKind):
        unknown = True
    risk_unknown = (
        holding.current_actual_loss_amount is None
        or holding.registered_account_loss_budget_amount is None
    )
    if not risk_unknown:
        assert holding.current_actual_loss_amount is not None
        assert holding.registered_account_loss_budget_amount is not None
        if (
            Decimal(holding.current_actual_loss_amount) < 0
            or Decimal(holding.registered_account_loss_budget_amount) <= 0
        ):
            return _blocked_exit("EXIT_RISK_BUDGET_VALUE_INVALID", rules)
        if Decimal(holding.current_actual_loss_amount) >= Decimal(
            holding.registered_account_loss_budget_amount
        ):
            confirmed.append("risk_budget_exit")
            states.append(("risk_budget_exit", TriggerState.CONFIRMED))
        else:
            states.append(("risk_budget_exit", TriggerState.REFUTED))
    time_unknown = (
        value.elapsed_trading_days is None
        or value.trading_calendar_version is None
        or value.preregistered_verification_event_confirmed is None
    )
    if not time_unknown:
        assert value.elapsed_trading_days is not None
        if (
            value.elapsed_trading_days >= rules.maximum_proof_window_trading_days
            and value.preregistered_verification_event_confirmed is False
        ):
            confirmed.append("time_exit")
            states.append(("time_exit", TriggerState.CONFIRMED))
        else:
            states.append(("time_exit", TriggerState.REFUTED))
    value_unknown = any(
        item is None
        for item in (
            value.current_market_cap,
            value.current_base_value_lower,
            value.new_e5_e6_value_evidence,
        )
    )
    if not value_unknown:
        assert value.current_market_cap is not None and value.current_base_value_lower is not None
        if Decimal(value.current_market_cap) >= Decimal(value.current_base_value_lower) and (
            value.new_e5_e6_value_evidence is False
        ):
            confirmed.append("value_exit")
            states.append(("value_exit", TriggerState.CONFIRMED))
        else:
            states.append(("value_exit", TriggerState.REFUTED))
    if confirmed:
        return Stage4ExitResult(
            evaluation_state=ExitEvaluationState.EVALUATED,
            disposition=ExitDisposition.EXIT_CANDIDATE,
            trigger_states=tuple(states),
            confirmed_trigger_ids=tuple(confirmed),
            reason_codes=("EXIT_CONFIRMED_TRIGGER",),
            rule_hash=rules.bundle_hash,
        )
    if unknown or risk_unknown or time_unknown or value_unknown:
        return Stage4ExitResult(
            evaluation_state=ExitEvaluationState.EVALUATED,
            disposition=None,
            trigger_states=tuple(states),
            confirmed_trigger_ids=(),
            reason_codes=("EXIT_APPLICABLE_TRIGGER_UNKNOWN",),
            rule_hash=rules.bundle_hash,
        )
    if value.new_e5_e6_value_evidence:
        return Stage4ExitResult(
            evaluation_state=ExitEvaluationState.EVALUATED,
            disposition=ExitDisposition.REUNDERWRITE_REQUIRED,
            trigger_states=tuple(states),
            confirmed_trigger_ids=(),
            reason_codes=("EXIT_NEW_E5_E6_REUNDERWRITE",),
            rule_hash=rules.bundle_hash,
        )
    if value.reunderwriting_passed is not True:
        return Stage4ExitResult(
            evaluation_state=ExitEvaluationState.EVALUATED,
            disposition=None,
            trigger_states=tuple(states),
            confirmed_trigger_ids=(),
            reason_codes=("EXIT_REUNDERWRITING_INCOMPLETE",),
            rule_hash=rules.bundle_hash,
        )
    return Stage4ExitResult(
        evaluation_state=ExitEvaluationState.EVALUATED,
        disposition=ExitDisposition.HOLD,
        trigger_states=tuple(states),
        confirmed_trigger_ids=(),
        reason_codes=("EXIT_ALL_APPLICABLE_TRIGGERS_REFUTED",),
        rule_hash=rules.bundle_hash,
    )


def evaluate_stage4_expectation_valuation_exit(
    case: Stage4ExpectationValuationExitCase,
    rules: ApprovedStage4ExpectationValuationExitRules,
) -> Stage4ExpectationValuationExitResult:
    """Evaluate approved 4A-4 rules without issuing full Stage 4 capability."""

    if not isinstance(case, Stage4ExpectationValuationExitCase):
        raise TypeError("case must be Stage4ExpectationValuationExitCase")
    if not isinstance(rules, ApprovedStage4ExpectationValuationExitRules):
        raise TypeError("rules must be ApprovedStage4ExpectationValuationExitRules")
    hard_failure = _artifact_failure(case)
    if hard_failure is not None:
        gate3 = _assessment("FR-GATE-004", GateOutcome.BLOCKED, hard_failure, rules)
        gate4 = _not_evaluated("FR-GATE-005", "PRIOR_GATE_NOT_PASS", rules)
        exit_result = _blocked_exit(hard_failure, rules)
        gate_result = Stage4A4GateResult(
            gate_3=gate3,
            gate_4=gate4,
            overall_outcome=GateOutcome.BLOCKED,
            public_expectation_class=None,
            market_pricing_state=None,
            market_implied_event_value=None,
            net_base_remaining_return=None,
            net_downside_return=None,
            downside_loss=None,
            reward_to_downside=None,
            research_decision_label=DecisionState.BLOCKED,
        )
    else:
        gate3, expectation, pricing, implied = _evaluate_gate3(case, rules)
        gate4, metrics = _evaluate_gate4(case, gate3, rules)
        outcome = gate4.outcome if gate4.outcome is not None else gate3.outcome
        if outcome is None:
            outcome = case.upstream_gate_result.overall_outcome
        decision = {
            GateOutcome.PASS: DecisionState.TRADE_READY,
            GateOutcome.REJECT: DecisionState.REJECT,
            GateOutcome.ABSTAIN: DecisionState.ABSTAIN,
            GateOutcome.BLOCKED: DecisionState.BLOCKED,
            GateOutcome.SHADOW_ONLY: DecisionState.SHADOW_ONLY,
        }[outcome]
        values = metrics or (None, None, None, None)
        gate_result = Stage4A4GateResult(
            gate_3=gate3,
            gate_4=gate4,
            overall_outcome=outcome,
            public_expectation_class=expectation,
            market_pricing_state=pricing,
            market_implied_event_value=implied,
            net_base_remaining_return=(str(values[0]) if values[0] is not None else None),
            net_downside_return=(str(values[1]) if values[1] is not None else None),
            downside_loss=(str(values[2]) if values[2] is not None else None),
            reward_to_downside=(str(values[3]) if values[3] is not None else None),
            research_decision_label=decision,
        )
        exit_result = _evaluate_exit(case, rules)
    replay_hash = _hash(
        canonical_sha256(
            {
                "case": case,
                "gate_result": gate_result,
                "exit_result": exit_result,
                "rule_bundle_hash": rules.bundle_hash,
                "rule_approval_id": rules.approval_id,
                "rule_approval_record_hash": rules.approval_record_hash,
            }
        )
    )
    return Stage4ExpectationValuationExitResult(
        case_id=case.case_id,
        gate_result=gate_result,
        exit_result=exit_result,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
        replay_hash=replay_hash,
    )
