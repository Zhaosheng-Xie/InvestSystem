"""Pure domain models for the approved Stage 2B industrial-event slice.

The types in this module contain no provider, storage, transport, portfolio, or
execution behavior.  Decimal inputs remain strings at the contract boundary;
the engine parses them into :class:`decimal.Decimal` values and never accepts
binary floating point.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import JsonValue, canonical_sha256, freeze_json, normalize_utc
from invest_system.domain.strategy_input import SyntheticValidationInput
from invest_system.models import (
    CanonicalModel,
    DecisionState,
    EventState,
    ExpectationClass,
    GateId,
    GateOutcome,
    GateResult,
    HashDigest,
    PositionState,
    RunMode,
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

INDUSTRIAL_EVENT_CASE_SEMANTIC_SCHEMA_VERSION = "0.1.0"
CASE_MATERIAL_HASH_PREDICATE = "invest_system.synthetic_case_material_sha256"
COMPLETE_CASE_PAYLOAD_PREDICATE = "stage2b_complete_case_semantic_payload"


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_optional_bool(field_name: str, value: bool | None) -> None:
    if value is not None and not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean or None")


def _require_decimal_text(field_name: str, value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None):
        raise ValueError(f"{field_name} must be a decimal string or None")


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


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


class EvidenceSupport(StrEnum):
    """Claims an evidence chain directly supports in the approved narrow slice."""

    CONTRACT_SIGNED_OR_FORMALLY_PLACED = "contract_signed_or_formally_placed"
    CONTRACT_EFFECTIVE = "contract_effective"
    BINDING_MINIMUM_OBLIGATION = "binding_minimum_obligation"
    PROFIT_ATTRIBUTION = "profit_attribution"
    BUYER_IDENTITY = "buyer_identity"


class MinimumObligationKind(StrEnum):
    """The directly verifiable form of the minimum economic obligation."""

    AMOUNT = "amount"
    QUANTITY = "quantity"
    NON_CANCELLABLE_OBLIGATION = "non_cancellable_obligation"


def _freeze_supports(values: Iterable[EvidenceSupport]) -> tuple[EvidenceSupport, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError("supports must be an ordered list or tuple")
    result = tuple(_coerce_enum("supports", EvidenceSupport, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError("supports must not contain duplicates")
    return tuple(sorted(result, key=lambda value: value.value))


@dataclass(frozen=True, slots=True)
class EvidenceChain(CanonicalModel):
    """One independently acquired public evidence chain."""

    chain_id: str
    source_document_id: str
    publisher_id: str
    acquisition_chain_id: str
    content_hash: HashDigest
    evidence_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    authoritative_original: bool
    supports: tuple[EvidenceSupport, ...]
    derivative_of_another_chain: bool = False

    def __post_init__(self) -> None:
        for field_name in (
            "chain_id",
            "source_document_id",
            "publisher_id",
            "acquisition_chain_id",
        ):
            _require_id(field_name, getattr(self, field_name))
        if not isinstance(self.content_hash, HashDigest):
            raise TypeError("content_hash must be a HashDigest")
        object.__setattr__(self, "evidence_ids", _freeze_ids("evidence_ids", self.evidence_ids))
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))
        if not self.evidence_ids or not self.fact_ids:
            raise ValueError("an evidence chain must reference evidence and facts")
        object.__setattr__(self, "supports", _freeze_supports(self.supports))
        if not self.supports:
            raise ValueError("an evidence chain must declare at least one directly supported claim")
        for field_name in ("authoritative_original", "derivative_of_another_chain"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")


@dataclass(frozen=True, slots=True)
class CommercialEventInput(CanonicalModel):
    """The narrow, evidence-backed facts needed to distinguish E3.5 and E4."""

    strong_commercial_clue: bool
    authorized_public_evidence: bool | None
    ownership_path_verified: bool | None
    contract_signed_or_formally_ordered: bool | None
    contract_effective: bool | None
    material_conditions_satisfied: bool | None
    binding_minimum_obligation: bool | None
    minimum_obligation_kind: MinimumObligationKind | None
    cancellation_can_zero_minimum: bool | None
    return_or_acceptance_can_zero_minimum: bool | None
    e4_first_public_at: datetime
    evidence_chains: tuple[EvidenceChain, ...]
    supporting_fact_ids: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...] = ()
    material_conflict: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.strong_commercial_clue, bool):
            raise TypeError("strong_commercial_clue must be a boolean")
        for field_name in (
            "authorized_public_evidence",
            "ownership_path_verified",
            "contract_signed_or_formally_ordered",
            "contract_effective",
            "material_conditions_satisfied",
            "binding_minimum_obligation",
            "cancellation_can_zero_minimum",
            "return_or_acceptance_can_zero_minimum",
        ):
            _require_optional_bool(field_name, getattr(self, field_name))
        if self.minimum_obligation_kind is not None:
            object.__setattr__(
                self,
                "minimum_obligation_kind",
                _coerce_enum(
                    "minimum_obligation_kind",
                    MinimumObligationKind,
                    self.minimum_obligation_kind,
                ),
            )
            if self.binding_minimum_obligation is not True:
                raise ValueError("minimum_obligation_kind requires binding_minimum_obligation=true")
        object.__setattr__(
            self,
            "e4_first_public_at",
            normalize_utc(self.e4_first_public_at, field_name="e4_first_public_at"),
        )
        if not isinstance(self.evidence_chains, (list, tuple)) or any(
            not isinstance(chain, EvidenceChain) for chain in self.evidence_chains
        ):
            raise TypeError("evidence_chains must contain only EvidenceChain values")
        chain_ids = tuple(chain.chain_id for chain in self.evidence_chains)
        if len(chain_ids) != len(set(chain_ids)):
            raise ValueError("evidence_chains must not repeat chain_id")
        object.__setattr__(
            self,
            "evidence_chains",
            tuple(sorted(self.evidence_chains, key=lambda chain: chain.chain_id)),
        )
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )
        object.__setattr__(
            self,
            "conflicting_fact_ids",
            _freeze_ids("conflicting_fact_ids", self.conflicting_fact_ids),
        )
        if not isinstance(self.material_conflict, bool):
            raise TypeError("material_conflict must be a boolean")
        if self.material_conflict and not self.conflicting_fact_ids:
            raise ValueError("material_conflict requires conflicting_fact_ids")


@dataclass(frozen=True, slots=True)
class ProfitBridgeInput(CanonicalModel):
    currency: str
    ntm_recognizable_revenue: str | None
    incremental_gross_margin_rate: str | None
    incremental_operating_expense: str | None
    incremental_tax_and_surcharges: str | None
    minority_interest_deduction: str | None
    counterfactual_ntm_normalized_parent_profit_base: str | None
    counterfactual_ntm_normalized_parent_profit_downside: str | None
    incremental_non_cash_items: str | None
    incremental_working_capital: str | None
    incremental_capex: str | None
    units_consistent: bool | None
    attribution_verified: bool | None
    counterfactual_bridge_verified: bool | None
    supporting_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("currency", self.currency)
        for field_name in (
            "ntm_recognizable_revenue",
            "incremental_gross_margin_rate",
            "incremental_operating_expense",
            "incremental_tax_and_surcharges",
            "minority_interest_deduction",
            "counterfactual_ntm_normalized_parent_profit_base",
            "counterfactual_ntm_normalized_parent_profit_downside",
            "incremental_non_cash_items",
            "incremental_working_capital",
            "incremental_capex",
        ):
            _require_decimal_text(field_name, getattr(self, field_name))
        for field_name in (
            "units_consistent",
            "attribution_verified",
            "counterfactual_bridge_verified",
        ):
            _require_optional_bool(field_name, getattr(self, field_name))
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )
        object.__setattr__(
            self,
            "conflicting_fact_ids",
            _freeze_ids("conflicting_fact_ids", self.conflicting_fact_ids),
        )


@dataclass(frozen=True, slots=True)
class ProfitBridge(CanonicalModel):
    currency: str
    incremental_gross_profit: str
    ntm_incremental_parent_normalized_profit: str
    ntm_incremental_free_cash_flow: str
    profit_materiality: str | None

    def __post_init__(self) -> None:
        _require_text("currency", self.currency)
        for field_name in (
            "incremental_gross_profit",
            "ntm_incremental_parent_normalized_profit",
            "ntm_incremental_free_cash_flow",
            "profit_materiality",
        ):
            _require_decimal_text(field_name, getattr(self, field_name))


@dataclass(frozen=True, slots=True)
class ContractExpectationTerms(CanonicalModel):
    counterparty_scope: str
    product_scope: str
    currency: str
    binding_minimum_amount: str | None
    effective_period: str
    material_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name in (
            "counterparty_scope",
            "product_scope",
            "currency",
            "effective_period",
        ):
            _require_text(field_name, getattr(self, field_name))
        _require_decimal_text("binding_minimum_amount", self.binding_minimum_amount)
        object.__setattr__(
            self,
            "material_conditions",
            _freeze_texts("material_conditions", self.material_conditions),
        )


@dataclass(frozen=True, slots=True)
class PriorExpectationSnapshot(CanonicalModel):
    terms: ContractExpectationTerms
    available_at: datetime
    explicit_public_statement: bool
    based_only_on_search_absence: bool
    material_conflict: bool
    supporting_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.terms, ContractExpectationTerms):
            raise TypeError("terms must be ContractExpectationTerms")
        object.__setattr__(
            self,
            "available_at",
            normalize_utc(self.available_at, field_name="available_at"),
        )
        for field_name in (
            "explicit_public_statement",
            "based_only_on_search_absence",
            "material_conflict",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )
        object.__setattr__(
            self,
            "conflicting_fact_ids",
            _freeze_ids("conflicting_fact_ids", self.conflicting_fact_ids),
        )
        if self.material_conflict and not self.conflicting_fact_ids:
            raise ValueError("material_conflict requires conflicting_fact_ids")


@dataclass(frozen=True, slots=True)
class ExpectationInput(CanonicalModel):
    current_terms: ContractExpectationTerms
    prior_snapshot: PriorExpectationSnapshot | None
    supporting_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.current_terms, ContractExpectationTerms):
            raise TypeError("current_terms must be ContractExpectationTerms")
        if self.prior_snapshot is not None and not isinstance(
            self.prior_snapshot, PriorExpectationSnapshot
        ):
            raise TypeError("prior_snapshot must be PriorExpectationSnapshot or None")
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )


@dataclass(frozen=True, slots=True)
class ValuationInput(CanonicalModel):
    currency: str
    base_business_equity_value: str | None
    event_finite_life_incremental_fcf_present_value: str | None
    downside_scenario_equity_value: str | None
    fully_diluted_shares: str | None
    first_executable_price: str | None
    explicit_cost_rate: str | None
    explicit_slippage_rate: str | None
    first_executable_at: datetime | None
    next_verification_trading_days: int | None
    base_business_excludes_event_value: bool | None
    event_value_is_finite_life: bool | None
    supporting_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text("currency", self.currency)
        for field_name in (
            "base_business_equity_value",
            "event_finite_life_incremental_fcf_present_value",
            "downside_scenario_equity_value",
            "fully_diluted_shares",
            "first_executable_price",
            "explicit_cost_rate",
            "explicit_slippage_rate",
        ):
            _require_decimal_text(field_name, getattr(self, field_name))
        if self.first_executable_at is not None:
            object.__setattr__(
                self,
                "first_executable_at",
                normalize_utc(self.first_executable_at, field_name="first_executable_at"),
            )
        if self.next_verification_trading_days is not None and (
            isinstance(self.next_verification_trading_days, bool)
            or not isinstance(self.next_verification_trading_days, int)
            or self.next_verification_trading_days < 0
        ):
            raise ValueError(
                "next_verification_trading_days must be a non-negative integer or None"
            )
        for field_name in (
            "base_business_excludes_event_value",
            "event_value_is_finite_life",
        ):
            _require_optional_bool(field_name, getattr(self, field_name))
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )


@dataclass(frozen=True, slots=True)
class ScenarioValuation(CanonicalModel):
    currency: str
    first_executable_market_cap: str
    base_scenario_equity_value: str
    downside_scenario_equity_value: str
    explicit_friction_rate: str
    net_base_remaining_return: str
    net_downside_return: str
    downside_loss: str
    reward_to_downside: str | None

    def __post_init__(self) -> None:
        _require_text("currency", self.currency)
        for field_name in (
            "first_executable_market_cap",
            "base_scenario_equity_value",
            "downside_scenario_equity_value",
            "explicit_friction_rate",
            "net_base_remaining_return",
            "net_downside_return",
            "downside_loss",
            "reward_to_downside",
        ):
            _require_decimal_text(field_name, getattr(self, field_name))


@dataclass(frozen=True, slots=True)
class IndustrialEventCase(CanonicalModel):
    case_id: str
    strategy_input: SyntheticValidationInput
    decision_at: datetime
    commercial_event: CommercialEventInput
    profit_bridge: ProfitBridgeInput | None
    expectation: ExpectationInput | None
    valuation: ValuationInput | None
    falsifiers: tuple[str, ...]
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    validation_only: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        if not isinstance(self.strategy_input, SyntheticValidationInput):
            raise TypeError("strategy_input must be SyntheticValidationInput")
        object.__setattr__(
            self,
            "decision_at",
            normalize_utc(self.decision_at, field_name="decision_at"),
        )
        if not isinstance(self.commercial_event, CommercialEventInput):
            raise TypeError("commercial_event must be CommercialEventInput")
        if self.profit_bridge is not None and not isinstance(self.profit_bridge, ProfitBridgeInput):
            raise TypeError("profit_bridge must be ProfitBridgeInput or None")
        if self.expectation is not None and not isinstance(self.expectation, ExpectationInput):
            raise TypeError("expectation must be ExpectationInput or None")
        if self.valuation is not None and not isinstance(self.valuation, ValuationInput):
            raise TypeError("valuation must be ValuationInput or None")
        object.__setattr__(self, "falsifiers", _freeze_texts("falsifiers", self.falsifiers))
        if self.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff > (
            self.decision_at
        ):
            raise ValueError("knowledge_cutoff must be <= decision_at")

    def semantic_payload(self) -> Mapping[str, JsonValue]:
        """Return the complete strategy business DTO without its provider wrapper.

        The payload deliberately excludes ``strategy_input`` and the derived hash
        itself.  This makes it possible to bind the business DTO into one synthetic
        VKI Fact without creating a self-referential hash cycle.
        """

        payload = freeze_json(
            {
                "schema_version": INDUSTRIAL_EVENT_CASE_SEMANTIC_SCHEMA_VERSION,
                "case_id": self.case_id,
                "decision_at": self.decision_at,
                "commercial_event": self.commercial_event.to_json_value(),
                "profit_bridge": (
                    self.profit_bridge.to_json_value() if self.profit_bridge is not None else None
                ),
                "expectation": (
                    self.expectation.to_json_value() if self.expectation is not None else None
                ),
                "valuation": self.valuation.to_json_value() if self.valuation is not None else None,
                "falsifiers": self.falsifiers,
                "run_mode": self.run_mode.value,
                "validation_only": self.validation_only,
            },
            path="$.industrial_event_case_semantic_payload",
        )
        if not isinstance(payload, Mapping):
            raise TypeError("industrial-event semantic payload must be a mapping")
        return payload

    def semantic_input_hash(self) -> HashDigest:
        """Hash the strategy business DTO independently of provider provenance."""

        return HashDigest(algorithm="sha256", value=canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class IndustrialEventDecision(CanonicalModel):
    case_id: str
    decision_at: datetime
    event_state: EventState
    decision_state: DecisionState
    gate_results: tuple[GateResult, ...]
    rule_bundle_hash: HashDigest
    approval_id: str
    strategy_case_envelope_hash: HashDigest
    supporting_fact_ids: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...]
    falsifiers: tuple[str, ...]
    profit_bridge: ProfitBridge | None = None
    expectation_class: ExpectationClass | None = None
    scenario_valuation: ScenarioValuation | None = None
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    validation_only: bool = field(default=True, init=False)
    synthetic: bool = field(default=True, init=False)
    position_state: PositionState = field(default=PositionState.FLAT, init=False)
    target_weight: str = field(default="0", init=False)
    approved_weight: str = field(default="0", init=False)
    actual_weight: str = field(default="0", init=False)
    approver: None = field(default=None, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        object.__setattr__(
            self,
            "decision_at",
            normalize_utc(self.decision_at, field_name="decision_at"),
        )
        object.__setattr__(
            self,
            "event_state",
            _coerce_enum("event_state", EventState, self.event_state),
        )
        object.__setattr__(
            self,
            "decision_state",
            _coerce_enum("decision_state", DecisionState, self.decision_state),
        )
        gates = tuple(self.gate_results)
        if any(not isinstance(gate, GateResult) for gate in gates):
            raise TypeError("gate_results must contain GateResult values")
        expected_order = (
            GateId.AUTHENTICITY,
            GateId.PROFIT_MATERIALITY,
            GateId.EXPECTATION_GAP,
            GateId.EXECUTABLE_RETURN,
        )
        if tuple(gate.gate_id for gate in gates) != expected_order:
            raise ValueError("gate_results must contain each Gate exactly once in fixed order")
        object.__setattr__(self, "gate_results", gates)
        for field_name in ("rule_bundle_hash", "strategy_case_envelope_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        _require_id("approval_id", self.approval_id)
        object.__setattr__(
            self,
            "supporting_fact_ids",
            _freeze_ids("supporting_fact_ids", self.supporting_fact_ids),
        )
        object.__setattr__(
            self,
            "conflicting_fact_ids",
            _freeze_ids("conflicting_fact_ids", self.conflicting_fact_ids),
        )
        object.__setattr__(self, "falsifiers", _freeze_texts("falsifiers", self.falsifiers))
        if self.profit_bridge is not None and not isinstance(self.profit_bridge, ProfitBridge):
            raise TypeError("profit_bridge must be ProfitBridge or None")
        if self.expectation_class is not None:
            object.__setattr__(
                self,
                "expectation_class",
                _coerce_enum("expectation_class", ExpectationClass, self.expectation_class),
            )
        if self.scenario_valuation is not None and not isinstance(
            self.scenario_valuation, ScenarioValuation
        ):
            raise TypeError("scenario_valuation must be ScenarioValuation or None")
        if self.decision_state is DecisionState.BLOCKED:
            raise ValueError("admission BLOCKED must occur before the strategy engine")
        if self.decision_state is DecisionState.TRADE_READY:
            if self.event_state is not EventState.E4:
                raise ValueError("synthetic TRADE_READY requires E4")
            if any(gate.outcome is not GateOutcome.PASS for gate in gates):
                raise ValueError("synthetic TRADE_READY requires all four Gates to PASS")
            if len(self.falsifiers) < 2:
                raise ValueError("synthetic TRADE_READY requires at least two falsifiers")
