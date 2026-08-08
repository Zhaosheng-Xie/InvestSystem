"""Approved Stage 4 / 4A-3 Gate 1/2 and scenario semantics.

This module is deliberately a pure, provider-neutral synthetic research
evaluator.  It performs no I/O, cannot read a KB delivery surface, and grants
no backtest, paper, shadow, live, position, or order authority.
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
    EventState,
    GateOutcome,
    HashDigest,
    PositionState,
    RuleStatus,
)

from .stage4_context_industry import (
    BeneficiaryTier,
    Stage4ContextIndustryResult,
    Stage4RuleEvaluationState,
)
from .stage4_event_semantics import AuditKnowledgeGraph, Stage4EventResult

STAGE4_4A3_RULE_BUNDLE_ID = "industrial_event_stage4_4a3_gate_profit_scenarios"
STAGE4_4A3_RULE_BUNDLE_VERSION = "0.1.0"
STAGE4_4A3_RULE_APPROVAL_ID = "rule_approval_stage4_4a3_gate_profit_scenarios_v0_1_0"
STAGE4_4A3_RULE_BUNDLE_SHA256 = "e6936e9c236fd7ed3a67eb8c5e01cb02d23d8fa20c8fcd7a3ccbd615220619b2"
STAGE4_4A3_RULES_SHA256 = "146c8c497f529a0b7c675882522f4928877c96093449b5e0245fb6cfb71a05f0"
STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256 = (
    "786944b9263a7571632dbc5a2c92dcb1deb1431f8946f113ee883495dac5281a"
)
STAGE4_4A3_RULE_VERSION = "0.1.0"
STAGE4_4A1_RULE_BUNDLE_SHA256 = "5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d"
STAGE4_4A2_RULE_BUNDLE_SHA256 = "9f9f5cf843347a1918a894be1151c0ef720bd6318daa1077657e97e9324d6560"

STAGE4_4A3_REQUIREMENT_IDS = ("FR-GATE-001", "FR-GATE-002", "FR-GATE-003")
STAGE4_REMAINING_GATE_IDS = ("FR-GATE-004", "FR-GATE-005")

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_PROBABILITY_RE = re.compile(r"^(?:0\.[0-9]{6}|1\.000000)$")
_ISO_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _freeze_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    result = tuple(_require_id(field_name, value) for value in values)
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
        raise ValueError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be a finite decimal")
    return parsed


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


class EconomicInputState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


class ProfitTrack(StrEnum):
    STANDARD = "standard_track"
    FRAGILE_SHADOW = "fragile_profit_shadow_track"
    UNDETERMINED = "undetermined"


class ScenarioKind(StrEnum):
    BASE = "base"
    DOWNSIDE = "downside"
    UPSIDE = "upside"
    STRESS = "stress"


class DriverDirection(StrEnum):
    BASE = "base"
    INHERITED = "inherited"
    BETTER = "better"
    WORSE = "worse"


class ProfitComponentName(StrEnum):
    RECURRING_OPERATING_REVENUE = "recurring_operating_revenue"
    RECURRING_OPERATING_COST = "recurring_operating_cost"
    RECURRING_SELLING_EXPENSE = "recurring_selling_expense"
    RECURRING_ADMINISTRATIVE_EXPENSE = "recurring_administrative_expense"
    RECURRING_RESEARCH_EXPENSE = "recurring_research_expense"
    NET_FINANCE_COST = "net_finance_cost"
    RECURRING_IMPAIRMENT_AND_CREDIT_LOSSES = "recurring_impairment_and_credit_losses"
    RECURRING_OTHER_OPERATING_INCOME = "recurring_other_operating_income"
    RECURRING_INVESTMENT_AND_ASSOCIATE_INCOME = "recurring_investment_and_associate_income"
    NORMALIZED_INCOME_TAX = "normalized_income_tax"
    MINORITY_INTEREST_DEDUCTION = "minority_interest_deduction"


class ScenarioDriverName(StrEnum):
    BINDING_AMOUNT_OR_QUANTITY = "binding_amount_or_quantity"
    NET_UNIT_PRICE = "net_unit_price"
    DELIVERY_AND_ACCEPTANCE_TIMING = "delivery_and_acceptance_timing"
    NTM_REVENUE_RECOGNITION = "ntm_revenue_recognition"
    INCREMENTAL_OPERATING_COST_OR_MARGIN = "incremental_operating_cost_or_margin"
    INCREMENTAL_OPERATING_EXPENSE = "incremental_operating_expense"
    TAX_AND_SURCHARGES = "tax_and_surcharges"
    FINANCING_COST = "financing_cost"
    MINORITY_INTEREST = "minority_interest"
    NON_CASH_ITEMS = "non_cash_items"
    WORKING_CAPITAL = "working_capital"
    CAPEX = "capex"
    CASH_COLLECTION_TIMING = "cash_collection_timing"
    FX_RATE_AND_TRANSLATION_BASIS = "fx_rate_and_translation_basis"


@dataclass(frozen=True, slots=True)
class DecimalInterval(CanonicalModel):
    lower: str
    upper: str

    def __post_init__(self) -> None:
        lower = _decimal("lower", self.lower)
        upper = _decimal("upper", self.upper)
        assert lower is not None and upper is not None
        if lower > upper:
            raise ValueError("interval lower must be <= upper")


@dataclass(frozen=True, slots=True)
class ProfitComponent(CanonicalModel):
    name: ProfitComponentName
    state: EconomicInputState
    point: str | None
    interval: DecimalInterval | None
    fact_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _coerce_enum("name", ProfitComponentName, self.name))
        object.__setattr__(self, "state", _coerce_enum("state", EconomicInputState, self.state))
        _decimal("point", self.point)
        if self.interval is not None and not isinstance(self.interval, DecimalInterval):
            raise TypeError("interval must be a DecimalInterval or None")
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))
        object.__setattr__(
            self, "assumption_ids", _freeze_ids("assumption_ids", self.assumption_ids)
        )


@dataclass(frozen=True, slots=True)
class CounterfactualProfitBridge(CanonicalModel):
    bridge_id: str
    bridge_version: str
    components: tuple[ProfitComponent, ...]
    declared_profit: str | None
    declared_interval: DecimalInterval | None
    calculation_input_hash: HashDigest
    result_hash: HashDigest
    contains_event_effect: bool = False
    double_counting: bool = False
    event_removal_quantified: bool = True
    interval_reliable: bool = True

    def __post_init__(self) -> None:
        _require_id("bridge_id", self.bridge_id)
        _require_text("bridge_version", self.bridge_version)
        if not isinstance(self.components, (list, tuple)) or any(
            not isinstance(item, ProfitComponent) for item in self.components
        ):
            raise TypeError("components must contain ProfitComponent values")
        names = tuple(item.name for item in self.components)
        if len(names) != len(set(names)):
            raise ValueError("components must not repeat a component name")
        object.__setattr__(self, "components", tuple(self.components))
        _decimal("declared_profit", self.declared_profit)
        if self.declared_interval is not None and not isinstance(
            self.declared_interval, DecimalInterval
        ):
            raise TypeError("declared_interval must be a DecimalInterval or None")
        for field_name in ("calculation_input_hash", "result_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")


@dataclass(frozen=True, slots=True)
class ScenarioDriver(CanonicalModel):
    name: ScenarioDriverName
    state: EconomicInputState
    value: str | None
    unit: str | None
    supported_interval: str | None
    as_of: datetime | None
    fact_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    direction: DriverDirection = DriverDirection.BASE
    change_reason: str | None = None
    trigger: str | None = None
    falsifier: str | None = None
    unbound_growth_assumption: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _coerce_enum("name", ScenarioDriverName, self.name))
        object.__setattr__(self, "state", _coerce_enum("state", EconomicInputState, self.state))
        object.__setattr__(
            self, "direction", _coerce_enum("direction", DriverDirection, self.direction)
        )
        if self.value is not None:
            _require_text("value", self.value)
        if self.unit is not None:
            _require_text("unit", self.unit)
        if self.supported_interval is not None:
            _require_text("supported_interval", self.supported_interval)
        if self.as_of is not None:
            object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))
        object.__setattr__(
            self, "assumption_ids", _freeze_ids("assumption_ids", self.assumption_ids)
        )


@dataclass(frozen=True, slots=True)
class ScenarioFinancials(CanonicalModel):
    ntm_recognizable_revenue: str | None
    incremental_operating_cost: str | None
    incremental_operating_expense: str | None
    incremental_tax_and_surcharges: str | None
    incremental_financing_cost: str | None
    minority_interest_deduction: str | None
    incremental_non_cash_items: str | None
    incremental_working_capital: str | None
    incremental_capex: str | None
    declared_incremental_profit: str | None
    declared_incremental_fcf: str | None
    peak_external_financing_need: str | None
    minimum_liquidity_headroom: str | None
    irreversible_writeoff: str | None
    fact_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    derived_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "ntm_recognizable_revenue",
            "incremental_operating_cost",
            "incremental_operating_expense",
            "incremental_tax_and_surcharges",
            "incremental_financing_cost",
            "minority_interest_deduction",
            "incremental_non_cash_items",
            "incremental_working_capital",
            "incremental_capex",
            "declared_incremental_profit",
            "declared_incremental_fcf",
            "peak_external_financing_need",
            "minimum_liquidity_headroom",
            "irreversible_writeoff",
        ):
            _decimal(field_name, getattr(self, field_name))
        for field_name in ("fact_ids", "assumption_ids", "derived_ids"):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))


@dataclass(frozen=True, slots=True)
class Scenario(CanonicalModel):
    kind: ScenarioKind
    drivers: tuple[ScenarioDriver, ...]
    financials: ScenarioFinancials
    reason_codes: tuple[str, ...]
    probability: str | None = None
    nonmonotonic_stress_reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _coerce_enum("kind", ScenarioKind, self.kind))
        if not isinstance(self.drivers, (list, tuple)) or any(
            not isinstance(item, ScenarioDriver) for item in self.drivers
        ):
            raise TypeError("drivers must contain ScenarioDriver values")
        object.__setattr__(self, "drivers", tuple(self.drivers))
        if not isinstance(self.financials, ScenarioFinancials):
            raise TypeError("financials must be ScenarioFinancials")
        object.__setattr__(self, "reason_codes", _freeze_ids("reason_codes", self.reason_codes))
        object.__setattr__(
            self,
            "nonmonotonic_stress_reason_codes",
            _freeze_ids("nonmonotonic_stress_reason_codes", self.nonmonotonic_stress_reason_codes),
        )
        _decimal("probability", self.probability)


@dataclass(frozen=True, slots=True)
class ProbabilityCalibration(CanonicalModel):
    sample_ref: str
    method_id: str
    method_version: str
    as_of: datetime

    def __post_init__(self) -> None:
        for field_name in ("sample_ref", "method_id"):
            _require_id(field_name, getattr(self, field_name))
        _require_text("method_version", self.method_version)
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))


@dataclass(frozen=True, slots=True)
class ScenarioMigrationReplay(CanonicalModel):
    previous_content_hash: HashDigest
    fixed_input_hash: HashDigest
    replay_result_hash: HashDigest
    expected_replay_result_hash: HashDigest
    replayable: bool

    def __post_init__(self) -> None:
        for field_name in (
            "previous_content_hash",
            "fixed_input_hash",
            "replay_result_hash",
            "expected_replay_result_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")


@dataclass(frozen=True, slots=True)
class ScenarioSet(CanonicalModel):
    scenario_set_id: str
    version: str
    as_of: datetime
    e4_first_public_at: datetime
    knowledge_cutoff: datetime
    ntm_start_date: str
    ntm_end_date_exclusive: str
    presentation_currency: str
    contract_currency: str
    fx_translation_date: str | None
    fx_version: str | None
    fx_fact_ids: tuple[str, ...]
    fx_assumption_ids: tuple[str, ...]
    scenarios: tuple[Scenario, ...]
    calibration: ProbabilityCalibration | None
    supersedes_scenario_set_id: str | None
    migration_replay: ScenarioMigrationReplay | None
    declared_content_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("scenario_set_id", self.scenario_set_id)
        _require_text("version", self.version)
        for field_name in ("as_of", "e4_first_public_at", "knowledge_cutoff"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("ntm_start_date", "ntm_end_date_exclusive"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _ISO_DATE_RE.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be an ISO date")
        for field_name in ("presentation_currency", "contract_currency"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or len(value) != 3 or not value.isupper():
                raise ValueError(f"{field_name} must be an uppercase ISO-style currency code")
        if (
            self.fx_translation_date is not None
            and _ISO_DATE_RE.fullmatch(self.fx_translation_date) is None
        ):
            raise ValueError("fx_translation_date must be an ISO date or None")
        if self.fx_version is not None:
            _require_text("fx_version", self.fx_version)
        for field_name in ("fx_fact_ids", "fx_assumption_ids"):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        if not isinstance(self.scenarios, (list, tuple)) or any(
            not isinstance(item, Scenario) for item in self.scenarios
        ):
            raise TypeError("scenarios must contain Scenario values")
        object.__setattr__(self, "scenarios", tuple(self.scenarios))
        if self.calibration is not None and not isinstance(
            self.calibration, ProbabilityCalibration
        ):
            raise TypeError("calibration must be ProbabilityCalibration or None")
        if self.supersedes_scenario_set_id is not None:
            _require_id("supersedes_scenario_set_id", self.supersedes_scenario_set_id)
        if self.migration_replay is not None and not isinstance(
            self.migration_replay, ScenarioMigrationReplay
        ):
            raise TypeError("migration_replay must be ScenarioMigrationReplay or None")
        if not isinstance(self.declared_content_hash, HashDigest):
            raise TypeError("declared_content_hash must be a HashDigest")


def scenario_set_content_sha256(value: ScenarioSet) -> str:
    """Hash a scenario set while excluding its self-referential declared hash."""

    if not isinstance(value, ScenarioSet):
        raise TypeError("value must be a ScenarioSet")
    projected = value.to_json_value()
    del projected["declared_content_hash"]
    return canonical_sha256(projected)


def bind_scenario_set_content_hash(value: ScenarioSet) -> ScenarioSet:
    """Return an immutable copy bound to its canonical, self-excluding hash."""

    return replace(value, declared_content_hash=_hash(scenario_set_content_sha256(value)))


def counterfactual_bridge_hashes(
    value: CounterfactualProfitBridge,
) -> tuple[HashDigest, HashDigest]:
    """Calculate the input and result identities of one profit bridge."""

    if not isinstance(value, CounterfactualProfitBridge):
        raise TypeError("value must be a CounterfactualProfitBridge")
    calculation_hash = _hash(
        canonical_sha256(
            {
                "bridge_id": value.bridge_id,
                "bridge_version": value.bridge_version,
                "components": value.components,
                "contains_event_effect": value.contains_event_effect,
                "double_counting": value.double_counting,
                "event_removal_quantified": value.event_removal_quantified,
                "interval_reliable": value.interval_reliable,
            }
        )
    )
    result_hash = _hash(
        canonical_sha256(
            {
                "calculation_input_hash": calculation_hash,
                "declared_profit": value.declared_profit,
                "declared_interval": value.declared_interval,
            }
        )
    )
    return calculation_hash, result_hash


def bind_counterfactual_bridge_hashes(
    value: CounterfactualProfitBridge,
) -> CounterfactualProfitBridge:
    """Return an immutable bridge copy with its calculation identities bound."""

    calculation_hash, result_hash = counterfactual_bridge_hashes(value)
    return replace(
        value,
        calculation_input_hash=calculation_hash,
        result_hash=result_hash,
    )


@dataclass(frozen=True, slots=True)
class Stage4GateCase(CanonicalModel):
    case_id: str
    context_result: Stage4ContextIndustryResult
    event_result: Stage4EventResult
    knowledge_graph: AuditKnowledgeGraph
    base_counterfactual_bridge: CounterfactualProfitBridge
    downside_counterfactual_bridge: CounterfactualProfitBridge
    scenario_set: ScenarioSet

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        expected_types = (
            ("context_result", Stage4ContextIndustryResult),
            ("event_result", Stage4EventResult),
            ("knowledge_graph", AuditKnowledgeGraph),
            ("base_counterfactual_bridge", CounterfactualProfitBridge),
            ("downside_counterfactual_bridge", CounterfactualProfitBridge),
            ("scenario_set", ScenarioSet),
        )
        for field_name, expected_type in expected_types:
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} must be {expected_type.__name__}")


@dataclass(frozen=True, slots=True)
class Stage4GateRuleAssessment(CanonicalModel):
    rule_id: str
    evaluation_state: Stage4RuleEvaluationState
    outcome: GateOutcome | None
    reason_codes: tuple[str, ...]
    fact_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    derived_ids: tuple[str, ...] = ()
    rule_version: str = field(default=STAGE4_4A3_RULE_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.rule_id not in (*STAGE4_4A3_REQUIREMENT_IDS, *STAGE4_REMAINING_GATE_IDS):
            raise ValueError("rule_id is not a Stage 4 gate requirement")
        object.__setattr__(
            self,
            "evaluation_state",
            _coerce_enum("evaluation_state", Stage4RuleEvaluationState, self.evaluation_state),
        )
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        object.__setattr__(self, "reason_codes", _freeze_ids("reason_codes", self.reason_codes))
        for field_name in ("fact_ids", "assumption_ids", "derived_ids"):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        if self.evaluation_state is Stage4RuleEvaluationState.EVALUATED:
            if self.outcome is None or not self.reason_codes:
                raise ValueError("evaluated rule requires an outcome and reason code")
        elif self.outcome is not None or len(self.reason_codes) != 1:
            raise ValueError("not_evaluated rule requires outcome=None and one reason code")


@dataclass(frozen=True, slots=True)
class Stage4GateResult(CanonicalModel):
    case_id: str
    gate_1: Stage4GateRuleAssessment
    scenario_validation: Stage4GateRuleAssessment
    gate_2: Stage4GateRuleAssessment
    gate_3: Stage4GateRuleAssessment
    gate_4: Stage4GateRuleAssessment
    overall_outcome: GateOutcome
    profit_track: ProfitTrack
    base_counterfactual_profit: str | None
    downside_counterfactual_profit: str | None
    counterfactual_profit_interval: DecimalInterval | None
    base_incremental_profit: str | None
    base_incremental_fcf: str | None
    base_profit_materiality: str | None
    gate2_research_qualified: bool
    remaining_gate_ids: tuple[str, ...]
    full_stage4_decision: None
    position_state: PositionState
    target_weight: None
    order_intent: None
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    approval_scope: RuleApprovalScope = field(
        default=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION, init=False
    )
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)


class Stage4GateCompatibilityError(ValueError):
    """Stable fail-closed rejection for a non-approved 4A-3 capability."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


_STAGE4_4A3_RULE_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4GateRules:
    """Exact approved 4A-3 semantics backed by an opaque registry capability."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    materiality_threshold: Decimal

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        materiality_threshold: Decimal,
    ) -> None:
        if _issuer is not _STAGE4_4A3_RULE_ISSUER:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_RULE_ISSUER_INVALID",
                "4A-3 typed rules can only be issued from an approved capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(self, "materiality_threshold", materiality_threshold)

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage4GateRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be a RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be an ApprovedRuleCapability")
        identity = (
            "industrial_bottleneck_event",
            STAGE4_4A3_RULE_BUNDLE_ID,
            STAGE4_4A3_RULE_BUNDLE_VERSION,
        )
        if (document.strategy_id, document.bundle_id, document.bundle_version) != identity or (
            capability.strategy_id,
            capability.bundle_id,
            capability.bundle_version,
        ) != identity:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_RULE_IDENTITY_UNSUPPORTED", "identity differs from approved 4A-3"
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_RULE_DOCUMENT_NOT_APPROVED", "document must declare approved"
            )
        if capability.approval_scope is not RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_RULE_SCOPE_UNSUPPORTED", "only Stage 4 synthetic research is approved"
            )
        if capability.bundle_hash != document.bundle_hash() or (
            document.bundle_hash().value != STAGE4_4A3_RULE_BUNDLE_SHA256
        ):
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_RULE_HASH_UNSUPPORTED", "capability must bind the pinned bundle"
            )
        if capability.approval_id != STAGE4_4A3_RULE_APPROVAL_ID:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_APPROVAL_ID_UNSUPPORTED", "owner approval ID differs"
            )
        if capability.approval_record_hash.value != STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_APPROVAL_RECORD_UNSUPPORTED", "owner approval record differs"
            )
        if canonical_sha256(document.rules) != STAGE4_4A3_RULES_SHA256:
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_MACHINE_SEMANTICS_UNSUPPORTED", "machine semantics differ"
            )
        modules = document.rules.get("rule_modules")
        if not isinstance(modules, Mapping) or set(modules) != set(STAGE4_4A3_REQUIREMENT_IDS):
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_MACHINE_SEMANTICS_INVALID", "rule module set differs"
            )
        gate2 = modules["FR-GATE-002"]
        if not isinstance(gate2, Mapping):
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_MACHINE_SEMANTICS_INVALID", "Gate 2 module must be an object"
            )
        materiality = gate2.get("profit_materiality")
        if not isinstance(materiality, Mapping) or materiality.get("threshold") != "0.10":
            raise Stage4GateCompatibilityError(
                "STAGE4_4A3_THRESHOLD_UNSUPPORTED", "approved threshold is exactly 0.10"
            )
        return cls(
            _issuer=_STAGE4_4A3_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            materiality_threshold=Decimal("0.10"),
        )


def _evaluated(rule_id: str, outcome: GateOutcome, reason: str) -> Stage4GateRuleAssessment:
    return Stage4GateRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(reason,),
    )


def _not_evaluated(rule_id: str, reason: str) -> Stage4GateRuleAssessment:
    return Stage4GateRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
        outcome=None,
        reason_codes=(reason,),
    )


def _gate1(case: Stage4GateCase) -> Stage4GateRuleAssessment:
    context = case.context_result
    event = case.event_result
    if case.case_id != context.case_id or case.case_id != event.case_id:
        return _evaluated("FR-GATE-001", GateOutcome.BLOCKED, "GATE1_CASE_IDENTITY_MISMATCH")
    if context.rule_bundle_hash.value != STAGE4_4A1_RULE_BUNDLE_SHA256 or (
        event.rule_bundle_hash.value != STAGE4_4A2_RULE_BUNDLE_SHA256
    ):
        return _evaluated("FR-GATE-001", GateOutcome.BLOCKED, "GATE1_UPSTREAM_HASH_MISMATCH")
    upstream = (
        context.context_admission.outcome,
        context.historical_context.outcome,
        context.bottleneck_assessment.outcome,
        context.beneficiary_assessment.outcome,
        event.audit_layers.outcome,
        event.party_and_pit.assessment.outcome,
        event.e4_public.assessment.outcome,
        event.event_state.assessment.outcome,
    )
    if GateOutcome.BLOCKED in upstream:
        return _evaluated("FR-GATE-001", GateOutcome.BLOCKED, "GATE1_UPSTREAM_BLOCKED")
    if context.beneficiary_tier is not BeneficiaryTier.PROFIT_BENEFICIARY or (
        context.beneficiary_assessment.outcome is GateOutcome.REJECT
        or event.e4_public.assessment.outcome is GateOutcome.REJECT
    ):
        return _evaluated(
            "FR-GATE-001", GateOutcome.REJECT, "GATE1_NOT_AUTHENTIC_PROFIT_BENEFICIARY"
        )
    state = event.event_state.highest_nonterminal_state
    candidate = event.event_state.candidate_highest_nonterminal_state
    if (
        EventState.E3_5 in (state, candidate)
        and EventState.E4 not in event.event_state.attained_states
    ):
        return _evaluated("FR-GATE-001", GateOutcome.SHADOW_ONLY, "GATE1_CURRENT_STATE_E3_5")
    if GateOutcome.REJECT in upstream:
        return _evaluated("FR-GATE-001", GateOutcome.REJECT, "GATE1_UPSTREAM_REJECTED")
    if GateOutcome.ABSTAIN in upstream or GateOutcome.SHADOW_ONLY in upstream:
        return _evaluated(
            "FR-GATE-001", GateOutcome.ABSTAIN, "GATE1_UPSTREAM_UNKNOWN_OR_CONFLICTED"
        )
    if not context.four_gate_eligible or not event.e4_public.independent_gate_evidence_ready:
        return _evaluated("FR-GATE-001", GateOutcome.ABSTAIN, "GATE1_EVIDENCE_NOT_READY")
    if EventState.E4 not in event.event_state.attained_states:
        return _evaluated("FR-GATE-001", GateOutcome.ABSTAIN, "GATE1_E4_NOT_ATTAINED")
    if any(outcome is not GateOutcome.PASS for outcome in upstream):
        return _evaluated("FR-GATE-001", GateOutcome.ABSTAIN, "GATE1_UPSTREAM_INCOMPLETE")
    return _evaluated("FR-GATE-001", GateOutcome.PASS, "GATE1_AUTHENTICITY_PASSED")


_COMPONENT_SIGNS = {
    ProfitComponentName.RECURRING_OPERATING_REVENUE: 1,
    ProfitComponentName.RECURRING_OPERATING_COST: -1,
    ProfitComponentName.RECURRING_SELLING_EXPENSE: -1,
    ProfitComponentName.RECURRING_ADMINISTRATIVE_EXPENSE: -1,
    ProfitComponentName.RECURRING_RESEARCH_EXPENSE: -1,
    ProfitComponentName.NET_FINANCE_COST: -1,
    ProfitComponentName.RECURRING_IMPAIRMENT_AND_CREDIT_LOSSES: -1,
    ProfitComponentName.RECURRING_OTHER_OPERATING_INCOME: 1,
    ProfitComponentName.RECURRING_INVESTMENT_AND_ASSOCIATE_INCOME: 1,
    ProfitComponentName.NORMALIZED_INCOME_TAX: -1,
    ProfitComponentName.MINORITY_INTEREST_DEDUCTION: -1,
}


def _graph_ids(graph: AuditKnowledgeGraph) -> tuple[set[str], set[str], set[str]]:
    return (
        {item.provider_fact_id for item in graph.facts},
        {item.assumption_id for item in graph.assumptions},
        {item.derived_id for item in graph.derived},
    )


def _reference_failure(case: Stage4GateCase) -> str | None:
    fact_ids, assumption_ids, derived_ids = _graph_ids(case.knowledge_graph)
    referenced_facts = set(case.scenario_set.fx_fact_ids)
    referenced_assumptions = set(case.scenario_set.fx_assumption_ids)
    referenced_derived: set[str] = set()
    for bridge in (case.base_counterfactual_bridge, case.downside_counterfactual_bridge):
        for item in bridge.components:
            referenced_facts.update(item.fact_ids)
            referenced_assumptions.update(item.assumption_ids)
    for scenario in case.scenario_set.scenarios:
        referenced_facts.update(scenario.financials.fact_ids)
        referenced_assumptions.update(scenario.financials.assumption_ids)
        referenced_derived.update(scenario.financials.derived_ids)
        for driver in scenario.drivers:
            referenced_facts.update(driver.fact_ids)
            referenced_assumptions.update(driver.assumption_ids)
    if (
        not referenced_facts <= fact_ids
        or not referenced_assumptions <= assumption_ids
        or (not referenced_derived <= derived_ids)
    ):
        return "SCENARIO_AUDIT_REFERENCE_MISSING"
    facts_by_id = {item.provider_fact_id: item for item in case.knowledge_graph.facts}
    for fact_id in referenced_facts:
        available_at = facts_by_id[fact_id].available_at
        if available_at is None or available_at > case.scenario_set.e4_first_public_at:
            return "SCENARIO_FUTURE_OR_UNTIMED_FACT"
    assumptions_by_id = {item.assumption_id: item for item in case.knowledge_graph.assumptions}
    if any(
        assumptions_by_id[item_id].as_of > case.scenario_set.e4_first_public_at
        for item_id in referenced_assumptions
    ):
        return "SCENARIO_FUTURE_ASSUMPTION"
    derived_by_id = {item.derived_id: item for item in case.knowledge_graph.derived}
    if any(
        derived_by_id[item_id].as_of > case.scenario_set.e4_first_public_at
        for item_id in referenced_derived
    ):
        return "SCENARIO_FUTURE_DERIVED_VALUE"
    return None


def _bridge_values(
    bridge: CounterfactualProfitBridge,
) -> tuple[str | None, Decimal | None, DecimalInterval | None]:
    expected_input_hash, expected_result_hash = counterfactual_bridge_hashes(bridge)
    if (
        bridge.calculation_input_hash != expected_input_hash
        or bridge.result_hash != expected_result_hash
    ):
        return "COUNTERFACTUAL_PROFIT_HASH_OR_FORMULA_MISMATCH", None, None
    if bridge.contains_event_effect or bridge.double_counting:
        return "COUNTERFACTUAL_EVENT_EFFECT_OR_DOUBLE_COUNT", None, None
    if not bridge.event_removal_quantified or not bridge.interval_reliable:
        return "COUNTERFACTUAL_BRIDGE_INCOMPLETE", None, None
    by_name = {item.name: item for item in bridge.components}
    if set(by_name) != set(ProfitComponentName):
        return "COUNTERFACTUAL_COMPONENT_SET_INCOMPLETE", None, None
    if any(item.state is not EconomicInputState.KNOWN for item in bridge.components):
        return "COUNTERFACTUAL_COMPONENT_UNKNOWN", None, None
    if any(
        item.point is None or item.interval is None or not (item.fact_ids or item.assumption_ids)
        for item in bridge.components
    ):
        return "COUNTERFACTUAL_COMPONENT_MATERIAL_MISSING", None, None
    magnitude_names = set(ProfitComponentName) - {
        ProfitComponentName.NET_FINANCE_COST,
        ProfitComponentName.RECURRING_OTHER_OPERATING_INCOME,
        ProfitComponentName.RECURRING_INVESTMENT_AND_ASSOCIATE_INCOME,
    }
    if any(
        item.name in magnitude_names and _decimal("point", item.point) < 0  # type: ignore[operator]
        for item in bridge.components
    ):
        return "COUNTERFACTUAL_SIGN_CONVENTION_INVALID", None, None
    point = Decimal(0)
    lower = Decimal(0)
    upper = Decimal(0)
    for item in bridge.components:
        assert item.point is not None and item.interval is not None
        if not Decimal(item.interval.lower) <= Decimal(item.point) <= Decimal(item.interval.upper):
            return "COUNTERFACTUAL_POINT_OUTSIDE_INTERVAL", None, None
        sign = _COMPONENT_SIGNS[item.name]
        point += Decimal(item.point) * sign
        item_lower = Decimal(item.interval.lower)
        item_upper = Decimal(item.interval.upper)
        if sign == 1:
            lower += item_lower
            upper += item_upper
        else:
            lower -= item_upper
            upper -= item_lower
    interval = DecimalInterval(str(lower), str(upper))
    if bridge.declared_profit is None or Decimal(bridge.declared_profit) != point:
        return "COUNTERFACTUAL_PROFIT_HASH_OR_FORMULA_MISMATCH", None, None
    if bridge.declared_interval != interval:
        return "COUNTERFACTUAL_INTERVAL_MISMATCH", None, None
    return None, point, interval


def _scenario_financial_values(
    financials: ScenarioFinancials,
) -> tuple[str | None, Decimal | None, Decimal | None]:
    fields = (
        financials.ntm_recognizable_revenue,
        financials.incremental_operating_cost,
        financials.incremental_operating_expense,
        financials.incremental_tax_and_surcharges,
        financials.incremental_financing_cost,
        financials.minority_interest_deduction,
        financials.incremental_non_cash_items,
        financials.incremental_working_capital,
        financials.incremental_capex,
        financials.declared_incremental_profit,
        financials.declared_incremental_fcf,
        financials.peak_external_financing_need,
        financials.minimum_liquidity_headroom,
        financials.irreversible_writeoff,
    )
    if any(value is None for value in fields) or not (
        financials.fact_ids or financials.assumption_ids
    ):
        return "SCENARIO_FINANCIALS_MISSING", None, None
    values = [Decimal(value) for value in fields if value is not None]
    revenue, cost, expense, tax, finance, minority, noncash, working, capex = values[:9]
    if any(
        value < 0
        for value in (
            revenue,
            cost,
            expense,
            tax,
            minority,
            working,
            capex,
            values[11],
            values[13],
        )
    ):
        return "SCENARIO_FINANCIAL_SIGN_INVALID", None, None
    profit = revenue - cost - expense - tax - finance - minority
    fcf = profit + noncash - working - capex
    if profit != values[9] or fcf != values[10]:
        return "SCENARIO_FINANCIAL_FORMULA_MISMATCH", None, None
    return None, profit, fcf


def _expected_ntm_end(start: str) -> str:
    year, month, day = (int(part) for part in start.split("-"))
    target_year = year + 1
    # February 29 anchors close on February 28 in the following non-leap year.
    if month == 2 and day == 29:
        day = 28
    return f"{target_year:04d}-{month:02d}-{day:02d}"


def _scenario_validation(
    case: Stage4GateCase,
) -> tuple[Stage4GateRuleAssessment, dict[ScenarioKind, tuple[Decimal, Decimal]]]:
    value = case.scenario_set
    if value.e4_first_public_at > value.knowledge_cutoff or value.as_of > value.knowledge_cutoff:
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_PIT_WINDOW_INVALID"), {}
    if value.ntm_start_date != value.e4_first_public_at.date().isoformat() or (
        value.ntm_end_date_exclusive != _expected_ntm_end(value.ntm_start_date)
    ):
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_NTM_WINDOW_INVALID"), {}
    if value.declared_content_hash.value != scenario_set_content_sha256(value):
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_CONTENT_HASH_MISMATCH"), {}
    if value.supersedes_scenario_set_id is not None and (
        value.migration_replay is None or not value.migration_replay.replayable
    ):
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_MIGRATION_UNREPLAYABLE"), {}
    if value.migration_replay is not None and (
        value.migration_replay.replay_result_hash
        != value.migration_replay.expected_replay_result_hash
    ):
        return _evaluated(
            "FR-GATE-003",
            GateOutcome.BLOCKED,
            "SCENARIO_MIGRATION_REPLAY_HASH_MISMATCH",
        ), {}
    reference_failure = _reference_failure(case)
    if reference_failure is not None:
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, reference_failure), {}
    if value.presentation_currency != value.contract_currency and not (
        value.fx_translation_date
        and value.fx_version
        and (value.fx_fact_ids or value.fx_assumption_ids)
    ):
        return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_FX_MATERIAL_MISSING"), {}
    kinds = tuple(item.kind for item in value.scenarios)
    if len(kinds) != len(set(kinds)):
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_KIND_DUPLICATED"), {}
    if set(kinds) != set(ScenarioKind):
        return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_SET_INCOMPLETE"), {}
    by_kind = {item.kind: item for item in value.scenarios}
    base_drivers = {item.name: item for item in by_kind[ScenarioKind.BASE].drivers}
    if len(base_drivers) != len(by_kind[ScenarioKind.BASE].drivers):
        return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_DRIVER_DUPLICATED"), {}
    if set(base_drivers) != set(ScenarioDriverName):
        return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_DRIVER_MISSING"), {}
    financial_values: dict[ScenarioKind, tuple[Decimal, Decimal]] = {}
    for kind, scenario in by_kind.items():
        drivers = {item.name: item for item in scenario.drivers}
        if len(drivers) != len(scenario.drivers):
            return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_DRIVER_DUPLICATED"), {}
        if set(drivers) != set(ScenarioDriverName):
            return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_DRIVER_MISSING"), {}
        if not scenario.reason_codes:
            return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_REASON_MISSING"), {}
        better = 0
        worse = 0
        for name, driver in drivers.items():
            if (
                driver.state is not EconomicInputState.KNOWN
                or driver.value is None
                or (driver.unit is None or not (driver.fact_ids or driver.assumption_ids))
                or driver.supported_interval is None
                or driver.as_of is None
                or driver.trigger is None
                or driver.falsifier is None
            ):
                return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "SCENARIO_DRIVER_UNKNOWN"), {}
            if driver.as_of > value.e4_first_public_at:
                return _evaluated(
                    "FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_DRIVER_FUTURE_AS_OF"
                ), {}
            if driver.unbound_growth_assumption and kind is not ScenarioKind.UPSIDE:
                return _evaluated(
                    "FR-GATE-003", GateOutcome.BLOCKED, "UNBOUND_GROWTH_OUTSIDE_UPSIDE"
                ), {}
            if kind is ScenarioKind.BASE:
                if driver.direction is not DriverDirection.BASE:
                    return _evaluated(
                        "FR-GATE-003", GateOutcome.BLOCKED, "BASE_DRIVER_DIRECTION_INVALID"
                    ), {}
                continue
            base = base_drivers[name]
            if driver.direction is DriverDirection.INHERITED:
                if (driver.value, driver.unit) != (base.value, base.unit):
                    return _evaluated(
                        "FR-GATE-003", GateOutcome.BLOCKED, "INHERITED_DRIVER_DRIFT"
                    ), {}
            elif driver.direction in (DriverDirection.BETTER, DriverDirection.WORSE):
                if not driver.change_reason:
                    return _evaluated(
                        "FR-GATE-003", GateOutcome.ABSTAIN, "DRIVER_CHANGE_REASON_MISSING"
                    ), {}
                better += driver.direction is DriverDirection.BETTER
                worse += driver.direction is DriverDirection.WORSE
            else:
                return _evaluated(
                    "FR-GATE-003", GateOutcome.BLOCKED, "NONBASE_DRIVER_DIRECTION_INVALID"
                ), {}
        if kind is ScenarioKind.DOWNSIDE and worse == 0:
            return _evaluated(
                "FR-GATE-003", GateOutcome.ABSTAIN, "DOWNSIDE_WORSE_DRIVER_MISSING"
            ), {}
        if kind is ScenarioKind.UPSIDE and (
            better == 0
            or not any(
                item.direction is DriverDirection.BETTER and item.trigger
                for item in drivers.values()
            )
        ):
            return _evaluated(
                "FR-GATE-003", GateOutcome.ABSTAIN, "UPSIDE_TRIGGERED_DRIVER_MISSING"
            ), {}
        if kind is ScenarioKind.STRESS and worse == 0:
            return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "STRESS_DRIVER_MISSING"), {}
        failure, profit, fcf = _scenario_financial_values(scenario.financials)
        if failure is not None:
            outcome = (
                GateOutcome.ABSTAIN
                if failure == "SCENARIO_FINANCIALS_MISSING"
                else GateOutcome.BLOCKED
            )
            return _evaluated("FR-GATE-003", outcome, failure), {}
        assert profit is not None and fcf is not None
        financial_values[kind] = (profit, fcf)
    if not (
        financial_values[ScenarioKind.UPSIDE][0]
        >= financial_values[ScenarioKind.BASE][0]
        >= financial_values[ScenarioKind.DOWNSIDE][0]
    ):
        return _evaluated(
            "FR-GATE-003", GateOutcome.BLOCKED, "SCENARIO_PROFIT_ORDERING_INVALID"
        ), {}
    downside = by_kind[ScenarioKind.DOWNSIDE].financials
    stress = by_kind[ScenarioKind.STRESS].financials
    assert downside.peak_external_financing_need is not None
    assert downside.minimum_liquidity_headroom is not None
    assert downside.irreversible_writeoff is not None
    assert stress.peak_external_financing_need is not None
    assert stress.minimum_liquidity_headroom is not None
    assert stress.irreversible_writeoff is not None
    stress_worse = (
        financial_values[ScenarioKind.STRESS][0] < financial_values[ScenarioKind.DOWNSIDE][0]
        or financial_values[ScenarioKind.STRESS][1] < financial_values[ScenarioKind.DOWNSIDE][1]
        or Decimal(stress.peak_external_financing_need)
        > Decimal(downside.peak_external_financing_need)
        or Decimal(stress.minimum_liquidity_headroom) < Decimal(downside.minimum_liquidity_headroom)
        or Decimal(stress.irreversible_writeoff) > Decimal(downside.irreversible_writeoff)
    )
    if not stress_worse:
        return _evaluated("FR-GATE-003", GateOutcome.ABSTAIN, "STRESS_NOT_STRICTLY_WORSE"), {}
    stress_better = (
        financial_values[ScenarioKind.STRESS][0] > financial_values[ScenarioKind.DOWNSIDE][0]
        or financial_values[ScenarioKind.STRESS][1] > financial_values[ScenarioKind.DOWNSIDE][1]
        or Decimal(stress.peak_external_financing_need)
        < Decimal(downside.peak_external_financing_need)
        or Decimal(stress.minimum_liquidity_headroom) > Decimal(downside.minimum_liquidity_headroom)
        or Decimal(stress.irreversible_writeoff) < Decimal(downside.irreversible_writeoff)
    )
    if stress_better and not by_kind[ScenarioKind.STRESS].nonmonotonic_stress_reason_codes:
        return _evaluated(
            "FR-GATE-003", GateOutcome.ABSTAIN, "STRESS_BETTER_METRIC_UNEXPLAINED"
        ), {}
    probabilities = {kind: scenario.probability for kind, scenario in by_kind.items()}
    if any(value is not None for value in probabilities.values()):
        if probabilities[ScenarioKind.STRESS] is not None:
            return _evaluated(
                "FR-GATE-003", GateOutcome.BLOCKED, "STRESS_PROBABILITY_FORBIDDEN"
            ), {}
        required = [
            probabilities[kind]
            for kind in (ScenarioKind.BASE, ScenarioKind.DOWNSIDE, ScenarioKind.UPSIDE)
        ]
        if any(item is None for item in required) or value.calibration is None:
            return _evaluated(
                "FR-GATE-003", GateOutcome.ABSTAIN, "PROBABILITY_CALIBRATION_INCOMPLETE"
            ), {}
        parsed_probabilities = [Decimal(item) for item in required if item is not None]
        if any(item is None or _PROBABILITY_RE.fullmatch(item) is None for item in required):
            return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "PROBABILITY_SCALE_INVALID"), {}
        if any(item < 0 or item > 1 for item in parsed_probabilities):
            return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "PROBABILITY_OUT_OF_RANGE"), {}
        if value.calibration.as_of > value.e4_first_public_at:
            return _evaluated(
                "FR-GATE-003",
                GateOutcome.BLOCKED,
                "PROBABILITY_CALIBRATION_FUTURE_AS_OF",
            ), {}
        if sum(parsed_probabilities) != Decimal("1.000000"):
            return _evaluated("FR-GATE-003", GateOutcome.BLOCKED, "PROBABILITY_SUM_INVALID"), {}
    return _evaluated("FR-GATE-003", GateOutcome.PASS, "FOUR_SCENARIOS_VALID"), financial_values


def _empty_result(
    case: Stage4GateCase,
    rules: ApprovedStage4GateRules,
    gate1: Stage4GateRuleAssessment,
) -> Stage4GateResult:
    downstream_reason = "PRIOR_GATE_NOT_PASS"
    return Stage4GateResult(
        case_id=case.case_id,
        gate_1=gate1,
        scenario_validation=_not_evaluated("FR-GATE-003", downstream_reason),
        gate_2=_not_evaluated("FR-GATE-002", downstream_reason),
        gate_3=_not_evaluated("FR-GATE-004", "RULE_BATCH_NOT_APPROVED"),
        gate_4=_not_evaluated("FR-GATE-005", "RULE_BATCH_NOT_APPROVED"),
        overall_outcome=gate1.outcome or GateOutcome.BLOCKED,
        profit_track=ProfitTrack.UNDETERMINED,
        base_counterfactual_profit=None,
        downside_counterfactual_profit=None,
        counterfactual_profit_interval=None,
        base_incremental_profit=None,
        base_incremental_fcf=None,
        base_profit_materiality=None,
        gate2_research_qualified=False,
        remaining_gate_ids=STAGE4_REMAINING_GATE_IDS,
        full_stage4_decision=None,
        position_state=PositionState.FLAT,
        target_weight=None,
        order_intent=None,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
    )


def evaluate_stage4_gates(
    case: Stage4GateCase,
    rules: ApprovedStage4GateRules,
) -> Stage4GateResult:
    """Evaluate approved Gate 1/2 semantics and leave Gate 3/4 closed."""

    if not isinstance(case, Stage4GateCase):
        raise TypeError("case must be a Stage4GateCase")
    if not isinstance(rules, ApprovedStage4GateRules):
        raise TypeError("rules must be ApprovedStage4GateRules")
    gate1 = _gate1(case)
    if gate1.outcome is not GateOutcome.PASS:
        return _empty_result(case, rules, gate1)
    scenario_assessment, financial_values = _scenario_validation(case)
    if scenario_assessment.outcome is not GateOutcome.PASS:
        result = _empty_result(case, rules, gate1)
        return replace(
            result,
            scenario_validation=scenario_assessment,
            gate_2=_not_evaluated("FR-GATE-002", "SCENARIO_VALIDATION_NOT_PASS"),
            overall_outcome=scenario_assessment.outcome or GateOutcome.BLOCKED,
        )
    base_failure, base_denominator, denominator_interval = _bridge_values(
        case.base_counterfactual_bridge
    )
    downside_failure, downside_denominator, _ = _bridge_values(case.downside_counterfactual_bridge)
    failure = base_failure or downside_failure
    if failure is not None:
        hard = failure in {
            "COUNTERFACTUAL_EVENT_EFFECT_OR_DOUBLE_COUNT",
            "COUNTERFACTUAL_PROFIT_HASH_OR_FORMULA_MISMATCH",
            "COUNTERFACTUAL_INTERVAL_MISMATCH",
            "COUNTERFACTUAL_SIGN_CONVENTION_INVALID",
            "COUNTERFACTUAL_POINT_OUTSIDE_INTERVAL",
        }
        outcome = GateOutcome.BLOCKED if hard else GateOutcome.ABSTAIN
        gate2 = _evaluated("FR-GATE-002", outcome, failure)
        result = _empty_result(case, rules, gate1)
        return replace(
            result,
            scenario_validation=scenario_assessment,
            gate_2=gate2,
            overall_outcome=outcome,
        )
    assert base_denominator is not None and downside_denominator is not None
    assert denominator_interval is not None
    base_profit, base_fcf = financial_values[ScenarioKind.BASE]
    fragile = (
        base_denominator <= 0
        or downside_denominator <= 0
        or Decimal(denominator_interval.lower) <= 0
    )
    track = ProfitTrack.FRAGILE_SHADOW if fragile else ProfitTrack.STANDARD
    materiality: Decimal | None = None
    if fragile:
        gate2 = _evaluated("FR-GATE-002", GateOutcome.SHADOW_ONLY, "GATE2_FRAGILE_PROFIT_TRACK")
    else:
        materiality = base_profit / base_denominator
        if materiality < rules.materiality_threshold:
            upside_profit = financial_values[ScenarioKind.UPSIDE][0]
            reason = (
                "GATE2_ONLY_UPSIDE_MATERIAL"
                if upside_profit / base_denominator >= rules.materiality_threshold
                else "GATE2_BASE_MATERIALITY_BELOW_THRESHOLD"
            )
            gate2 = _evaluated("FR-GATE-002", GateOutcome.REJECT, reason)
        elif base_profit <= 0 or base_fcf <= 0:
            gate2 = _evaluated(
                "FR-GATE-002", GateOutcome.SHADOW_ONLY, "GATE2_BASE_CASH_NOT_POSITIVE"
            )
        else:
            gate2 = _evaluated("FR-GATE-002", GateOutcome.PASS, "GATE2_PROFIT_AND_CASH_MATERIAL")
    qualified = gate2.outcome is GateOutcome.PASS
    return Stage4GateResult(
        case_id=case.case_id,
        gate_1=gate1,
        scenario_validation=scenario_assessment,
        gate_2=gate2,
        gate_3=_not_evaluated("FR-GATE-004", "RULE_BATCH_NOT_APPROVED"),
        gate_4=_not_evaluated("FR-GATE-005", "RULE_BATCH_NOT_APPROVED"),
        overall_outcome=gate2.outcome or GateOutcome.BLOCKED,
        profit_track=track,
        base_counterfactual_profit=str(base_denominator),
        downside_counterfactual_profit=str(downside_denominator),
        counterfactual_profit_interval=denominator_interval,
        base_incremental_profit=str(base_profit),
        base_incremental_fcf=str(base_fcf),
        base_profit_materiality=str(materiality) if materiality is not None else None,
        gate2_research_qualified=qualified,
        remaining_gate_ids=STAGE4_REMAINING_GATE_IDS,
        full_stage4_decision=None,
        position_state=PositionState.FLAT,
        target_weight=None,
        order_intent=None,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
    )
