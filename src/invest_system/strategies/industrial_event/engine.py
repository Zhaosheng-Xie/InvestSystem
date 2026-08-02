"""Pure Stage 2B industrial-event evaluation engine.

The engine consumes only provider-neutral synthetic validation input plus an
exact approved rule capability.  It performs no I/O and has no storage,
portfolio, execution, or order authority.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from itertools import combinations
from math import gcd
from typing import TypedDict

from invest_system.canonical import JsonValue, canonical_sha256
from invest_system.domain.rule_approval import ApprovedRuleCapability, RuleBundleDocument
from invest_system.domain.synthetic_fixture import ApprovedSyntheticFixtureCapability
from invest_system.models import (
    GATE_RESULT_SCHEMA_VERSION,
    DecisionState,
    EventState,
    ExpectationClass,
    GateEvaluationState,
    GateId,
    GateOutcome,
    GateResult,
    HashDigest,
)

from .models import (
    CASE_MATERIAL_HASH_PREDICATE,
    COMPLETE_CASE_PAYLOAD_PREDICATE,
    INDUSTRIAL_EVENT_CASE_SEMANTIC_SCHEMA_VERSION,
    ContractExpectationTerms,
    EvidenceChain,
    EvidenceSupport,
    ExpectationInput,
    IndustrialEventCase,
    IndustrialEventDecision,
    MinimumObligationKind,
    ProfitBridge,
    ProfitBridgeInput,
    ScenarioValuation,
    ValuationInput,
)
from .rules import (
    INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256,
    INDUSTRIAL_EVENT_RULE_BUNDLE_VERSION,
    INDUSTRIAL_EVENT_STRATEGY_ID,
    ApprovedIndustrialEventRules,
)

_GATE_ORDER = (
    GateId.AUTHENTICITY,
    GateId.PROFIT_MATERIALITY,
    GateId.EXPECTATION_GAP,
    GateId.EXECUTABLE_RETURN,
)
_RULE_ID_BY_GATE = {
    GateId.AUTHENTICITY: "S2B-G1-001",
    GateId.PROFIT_MATERIALITY: "S2B-G2-001",
    GateId.EXPECTATION_GAP: "S2B-G3-001",
    GateId.EXECUTABLE_RETURN: "S2B-G4-001",
}


class IndustrialEventEvaluationError(ValueError):
    """A fail-closed contract error that must not be converted into a Gate pass."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class _GateContext(TypedDict):
    gate_id: GateId
    evaluated_at: datetime


class _GateReferences(TypedDict, total=False):
    supporting_fact_ids: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...]


def _decimal(field_name: str, value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise IndustrialEventEvaluationError(
            "DECIMAL_INVALID", f"{field_name} must be an exact decimal string"
        ) from exc
    if not parsed.is_finite():
        raise IndustrialEventEvaluationError("DECIMAL_INVALID", f"{field_name} must be finite")
    return parsed


def decimal_to_canonical_text(value: Decimal) -> str:
    """Serialize a finite Decimal without exponent, trailing zeros, or negative zero."""

    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError("value must be a finite Decimal")
    if value == 0:
        return "0"
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def decimal_to_display_text(value: Decimal, *, places: int = 6) -> str:
    """Apply only the approved presentation rounding, never a Gate comparison."""

    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError("value must be a finite Decimal")
    if isinstance(places, bool) or not isinstance(places, int) or places < 0:
        raise ValueError("places must be a non-negative integer")
    quantum = Decimal(1).scaleb(-places)
    with localcontext() as context:
        context.prec = max(80, len(value.as_tuple().digits) + places + 8)
        return format(value.quantize(quantum, rounding=ROUND_HALF_EVEN), f".{places}f")


def resolve_contract_effectiveness(
    contract_effective: bool | None,
    material_conditions_satisfied: bool | None,
) -> bool | None:
    """Apply the approved tri-state OR for the E4 effectiveness condition."""

    for field_name, value in (
        ("contract_effective", contract_effective),
        ("material_conditions_satisfied", material_conditions_satisfied),
    ):
        if value is not None and not isinstance(value, bool):
            raise TypeError(f"{field_name} must be a boolean or None")
    if contract_effective is True or material_conditions_satisfied is True:
        return True
    if contract_effective is False and material_conditions_satisfied is False:
        return False
    return None


def resolve_economic_closure(
    *,
    contract_signed_or_formally_ordered: bool | None,
    contract_effective: bool | None,
    material_conditions_satisfied: bool | None,
    binding_minimum_obligation: bool | None,
    minimum_obligation_kind: MinimumObligationKind | None,
    cancellation_can_zero_minimum: bool | None,
    return_or_acceptance_can_zero_minimum: bool | None,
) -> bool | None:
    """Resolve the approved E4 economic closure with conservative tri-state AND.

    A known-open link returns ``False`` even when another link remains unknown:
    that is an established E3.5 condition, not an E4 uncertainty.  ``None`` is
    returned only when no link is known open and at least one required link is
    still unknown.
    """

    for field_name, value in (
        ("contract_signed_or_formally_ordered", contract_signed_or_formally_ordered),
        ("binding_minimum_obligation", binding_minimum_obligation),
        ("cancellation_can_zero_minimum", cancellation_can_zero_minimum),
        ("return_or_acceptance_can_zero_minimum", return_or_acceptance_can_zero_minimum),
    ):
        if value is not None and not isinstance(value, bool):
            raise TypeError(f"{field_name} must be a boolean or None")
    if minimum_obligation_kind is not None and not isinstance(
        minimum_obligation_kind, MinimumObligationKind
    ):
        raise TypeError("minimum_obligation_kind must be MinimumObligationKind or None")

    effective = resolve_contract_effectiveness(
        contract_effective,
        material_conditions_satisfied,
    )
    conditions: tuple[bool | None, ...] = (
        contract_signed_or_formally_ordered,
        effective,
        binding_minimum_obligation,
        (None if binding_minimum_obligation is True and minimum_obligation_kind is None else True),
        (None if cancellation_can_zero_minimum is None else not cancellation_can_zero_minimum),
        (
            None
            if return_or_acceptance_can_zero_minimum is None
            else not return_or_acceptance_can_zero_minimum
        ),
    )
    if any(condition is False for condition in conditions):
        return False
    if any(condition is None for condition in conditions):
        return None
    return True


def _integer_digits(value: int) -> tuple[int, ...]:
    """Return base-10 digits without relying on Python's int-to-string limit."""

    remaining = abs(value)
    if remaining == 0:
        return (0,)
    digits: list[int] = []
    while remaining:
        remaining, digit = divmod(remaining, 10)
        digits.append(digit)
    return tuple(reversed(digits))


def _scaled_integer(value: Decimal) -> tuple[int, int]:
    """Represent a finite Decimal exactly as ``coefficient * 10**exponent``."""

    if not value.is_finite():
        raise IndustrialEventEvaluationError("DECIMAL_INVALID", "exact arithmetic requires finite")
    parts = value.as_tuple()
    if not isinstance(parts.exponent, int):
        raise IndustrialEventEvaluationError("DECIMAL_INVALID", "finite exponent is required")
    coefficient = 0
    for digit in parts.digits:
        coefficient = coefficient * 10 + digit
    if parts.sign:
        coefficient = -coefficient
    return coefficient, parts.exponent


def _from_scaled_integer(coefficient: int, exponent: int) -> Decimal:
    sign = 1 if coefficient < 0 else 0
    return Decimal((sign, _integer_digits(coefficient), exponent))


def _exact_sum(*values: Decimal) -> Decimal:
    if not values:
        return Decimal(0)
    parts = tuple(_scaled_integer(value) for value in values)
    common_exponent = min(exponent for _, exponent in parts)
    coefficient = sum(item * (10 ** (exponent - common_exponent)) for item, exponent in parts)
    return _from_scaled_integer(coefficient, common_exponent)


def _exact_negate(value: Decimal) -> Decimal:
    coefficient, exponent = _scaled_integer(value)
    return _from_scaled_integer(-coefficient, exponent)


def _exact_difference(left: Decimal, right: Decimal) -> Decimal:
    return _exact_sum(left, _exact_negate(right))


def _exact_product(left: Decimal, right: Decimal) -> Decimal:
    left_coefficient, left_exponent = _scaled_integer(left)
    right_coefficient, right_exponent = _scaled_integer(right)
    return _from_scaled_integer(
        left_coefficient * right_coefficient,
        left_exponent + right_exponent,
    )


def _exact_ratio_components(numerator: Decimal, denominator: Decimal) -> tuple[int, int]:
    numerator_coefficient, numerator_exponent = _scaled_integer(numerator)
    denominator_coefficient, denominator_exponent = _scaled_integer(denominator)
    if denominator_coefficient == 0:
        raise IndustrialEventEvaluationError("DECIMAL_DIVISION_BY_ZERO", "denominator is zero")
    exponent_difference = numerator_exponent - denominator_exponent
    if exponent_difference >= 0:
        numerator_coefficient *= 10**exponent_difference
    else:
        denominator_coefficient *= 10 ** (-exponent_difference)
    if denominator_coefficient < 0:
        numerator_coefficient = -numerator_coefficient
        denominator_coefficient = -denominator_coefficient
    divisor = gcd(abs(numerator_coefficient), denominator_coefficient)
    return numerator_coefficient // divisor, denominator_coefficient // divisor


def _audit_ratio(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Serialize an exact ratio independently from every Gate comparison.

    Terminating decimal ratios are returned exactly.  Repeating ratios use a
    deterministic dynamic precision derived from both exact integer operands;
    no value returned here is ever used to decide a Gate outcome.
    """

    exact_numerator, exact_denominator = _exact_ratio_components(numerator, denominator)
    remaining = exact_denominator
    powers_of_two = 0
    powers_of_five = 0
    while remaining % 2 == 0:
        remaining //= 2
        powers_of_two += 1
    while remaining % 5 == 0:
        remaining //= 5
        powers_of_five += 1
    if remaining == 1:
        scale = max(powers_of_two, powers_of_five)
        scaled_numerator = (
            exact_numerator * (2 ** (scale - powers_of_two)) * (5 ** (scale - powers_of_five))
        )
        return _from_scaled_integer(scaled_numerator, -scale)

    precision = max(
        80,
        len(_integer_digits(exact_numerator)) + len(_integer_digits(exact_denominator)) + 32,
    )
    with localcontext() as context:
        context.prec = precision
        context.rounding = ROUND_HALF_EVEN
        return Decimal(exact_numerator) / Decimal(exact_denominator)


def _gate(
    *,
    gate_id: GateId,
    evaluated_at: datetime,
    outcome: GateOutcome,
    reason_codes: tuple[str, ...],
    supporting_fact_ids: tuple[str, ...] = (),
    conflicting_fact_ids: tuple[str, ...] = (),
    details: Mapping[str, JsonValue] | None = None,
) -> GateResult:
    if not reason_codes:
        raise IndustrialEventEvaluationError(
            "GATE_REASON_REQUIRED", "every evaluated gate must have a reason code"
        )
    return GateResult(
        schema_version=GATE_RESULT_SCHEMA_VERSION,
        gate_id=gate_id,
        evaluation_state=GateEvaluationState.EVALUATED,
        outcome=outcome,
        evaluated_at=evaluated_at,
        rule_id=_RULE_ID_BY_GATE[gate_id],
        rule_version=INDUSTRIAL_EVENT_RULE_BUNDLE_VERSION,
        supporting_fact_ids=tuple(sorted(supporting_fact_ids)),
        conflicting_fact_ids=tuple(sorted(conflicting_fact_ids)),
        reason_codes=reason_codes,
        details=details or {},
    )


def _skipped(*, gate_id: GateId, evaluated_at: datetime, terminal: GateResult) -> GateResult:
    if terminal.outcome is None:
        raise IndustrialEventEvaluationError(
            "SHORT_CIRCUIT_TERMINAL_INVALID", "terminal Gate must have an evaluated outcome"
        )
    if terminal.gate_id is GateId.AUTHENTICITY and terminal.outcome is GateOutcome.SHADOW_ONLY:
        reason = "event_state_e3_5"
    else:
        gate_prefix = {
            GateId.AUTHENTICITY: "gate_1",
            GateId.PROFIT_MATERIALITY: "gate_2",
            GateId.EXPECTATION_GAP: "gate_3",
            GateId.EXECUTABLE_RETURN: "gate_4",
        }[terminal.gate_id]
        reason = f"{gate_prefix}_{terminal.outcome.value.lower()}"
    return GateResult(
        schema_version=GATE_RESULT_SCHEMA_VERSION,
        gate_id=gate_id,
        evaluation_state=GateEvaluationState.NOT_EVALUATED,
        outcome=None,
        evaluated_at=evaluated_at,
        rule_id=_RULE_ID_BY_GATE[gate_id],
        rule_version=INDUSTRIAL_EVENT_RULE_BUNDLE_VERSION,
        short_circuit_reason_code=reason,
        reason_codes=(reason,),
        details={"terminal_outcome": terminal.outcome.value if terminal.outcome else None},
    )


def _all_referenced_fact_ids(case: IndustrialEventCase) -> tuple[str, ...]:
    references: list[str] = []
    event = case.commercial_event
    references.extend(event.supporting_fact_ids)
    references.extend(event.conflicting_fact_ids)
    for chain in event.evidence_chains:
        references.extend(chain.fact_ids)
    if case.profit_bridge is not None:
        references.extend(case.profit_bridge.supporting_fact_ids)
        references.extend(case.profit_bridge.conflicting_fact_ids)
    if case.expectation is not None:
        references.extend(case.expectation.supporting_fact_ids)
        if case.expectation.prior_snapshot is not None:
            references.extend(case.expectation.prior_snapshot.supporting_fact_ids)
            references.extend(case.expectation.prior_snapshot.conflicting_fact_ids)
    if case.valuation is not None:
        references.extend(case.valuation.supporting_fact_ids)
    return tuple(sorted(set(references)))


def _validate_fact_bindings(case: IndustrialEventCase) -> None:
    facts = {fact.fact_id: fact for fact in case.strategy_input.verified_knowledge_input.facts}
    unknown = sorted(set(_all_referenced_fact_ids(case)) - set(facts))
    if unknown:
        raise IndustrialEventEvaluationError(
            "FACT_REFERENCE_UNKNOWN",
            f"typed strategy input references facts absent from VerifiedKnowledgeInput: {unknown!r}",
        )
    for chain in case.commercial_event.evidence_chains:
        available_evidence = {
            evidence_id for fact_id in chain.fact_ids for evidence_id in facts[fact_id].evidence_ids
        }
        unknown_evidence = sorted(set(chain.evidence_ids) - available_evidence)
        if unknown_evidence:
            raise IndustrialEventEvaluationError(
                "EVIDENCE_REFERENCE_UNKNOWN",
                f"chain {chain.chain_id!r} references evidence not bound to its facts: "
                f"{unknown_evidence!r}",
            )


def _validate_case_payload_bindings(case: IndustrialEventCase) -> None:
    verified_facts = case.strategy_input.verified_knowledge_input.facts
    payload_facts = tuple(
        fact for fact in verified_facts if fact.predicate == COMPLETE_CASE_PAYLOAD_PREDICATE
    )
    if len(payload_facts) != 1:
        raise IndustrialEventEvaluationError(
            "COMPLETE_CASE_PAYLOAD_FACT_REQUIRED",
            "VKI must contain exactly one complete case semantic payload Fact",
        )
    payload_fact = payload_facts[0]
    if payload_fact.subject_id != case.case_id:
        raise IndustrialEventEvaluationError(
            "COMPLETE_CASE_PAYLOAD_SUBJECT_MISMATCH",
            "complete case payload Fact subject_id must equal case_id",
        )
    complete_payload = payload_fact.value
    if not isinstance(complete_payload, Mapping) or set(complete_payload) != {
        "case_input_schema_version",
        "raw_semantic_source",
        "strategy_case_payload",
    }:
        raise IndustrialEventEvaluationError(
            "COMPLETE_CASE_PAYLOAD_SHAPE_INVALID",
            "complete case payload must contain only its version, raw source, and typed payload",
        )
    if (
        complete_payload["case_input_schema_version"]
        != INDUSTRIAL_EVENT_CASE_SEMANTIC_SCHEMA_VERSION
    ):
        raise IndustrialEventEvaluationError(
            "COMPLETE_CASE_PAYLOAD_VERSION_UNSUPPORTED",
            "complete case payload schema version is unsupported",
        )
    raw_semantic_source = complete_payload["raw_semantic_source"]
    strategy_case_payload = complete_payload["strategy_case_payload"]
    if not isinstance(raw_semantic_source, Mapping) or not raw_semantic_source:
        raise IndustrialEventEvaluationError(
            "RAW_SEMANTIC_SOURCE_REQUIRED",
            "complete case payload must preserve a non-empty raw semantic source",
        )
    if not isinstance(strategy_case_payload, Mapping):
        raise IndustrialEventEvaluationError(
            "STRATEGY_CASE_PAYLOAD_REQUIRED",
            "complete case payload must preserve the typed strategy case payload",
        )

    semantic_hash = case.semantic_input_hash().value
    if canonical_sha256(strategy_case_payload) != semantic_hash:
        raise IndustrialEventEvaluationError(
            "STRATEGY_CASE_PAYLOAD_HASH_MISMATCH",
            "typed strategy payload does not match IndustrialEventCase semantic identity",
        )
    complete_payload_hash = canonical_sha256(complete_payload)

    material_facts = tuple(
        fact for fact in verified_facts if fact.predicate == CASE_MATERIAL_HASH_PREDICATE
    )
    if len(material_facts) != 1:
        raise IndustrialEventEvaluationError(
            "CASE_MATERIAL_HASH_FACT_REQUIRED",
            "VKI must contain exactly one synthetic case-material hash Fact",
        )
    material_fact = material_facts[0]
    if material_fact.subject_id != case.case_id:
        raise IndustrialEventEvaluationError(
            "CASE_MATERIAL_HASH_SUBJECT_MISMATCH",
            "case-material hash Fact subject_id must equal case_id",
        )
    if not isinstance(material_fact.value, str) or material_fact.value != semantic_hash:
        raise IndustrialEventEvaluationError(
            "CASE_MATERIAL_HASH_MISMATCH",
            "case-material hash Fact does not bind the complete strategy business DTO",
        )

    expected_metadata: Mapping[str, JsonValue] = {
        "not_a_published_release": True,
        "not_strategy_evidence": True,
        "complete_case_payload_hash": complete_payload_hash,
        "semantic_payload_hash": semantic_hash,
        "synthetic": True,
        "validation_only": True,
    }
    for fact in (payload_fact, material_fact):
        if dict(fact.metadata) != dict(expected_metadata):
            raise IndustrialEventEvaluationError(
                "CASE_PAYLOAD_METADATA_MISMATCH",
                "case payload Facts must carry exact provenance and corresponding hashes",
            )


def _validate_pit(case: IndustrialEventCase) -> None:
    knowledge_cutoff = (
        case.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff
    )
    if knowledge_cutoff > case.decision_at:
        raise IndustrialEventEvaluationError(
            "PIT_DECISION_BEFORE_CUTOFF", "knowledge_cutoff must be <= decision_at"
        )
    if case.commercial_event.e4_first_public_at > knowledge_cutoff:
        raise IndustrialEventEvaluationError(
            "PIT_FUTURE_EVENT",
            "E4 first-public time is after the admitted knowledge cutoff",
        )


def _require_fixture_capability(
    case: IndustrialEventCase,
    capability: ApprovedSyntheticFixtureCapability,
) -> HashDigest:
    if not isinstance(capability, ApprovedSyntheticFixtureCapability):
        raise TypeError("fixture_capability must be an ApprovedSyntheticFixtureCapability")
    if capability.registry_snapshot_hash.value != INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256:
        raise IndustrialEventEvaluationError(
            "SYNTHETIC_FIXTURE_REGISTRY_UNTRUSTED",
            "fixture capability is not issued from the pinned Stage 2B registry snapshot",
        )

    strategy_input = case.strategy_input
    verified = strategy_input.verified_knowledge_input
    input_envelope_hash = HashDigest(
        algorithm="sha256",
        value=strategy_input.canonical_sha256(),
    )
    verified_input_hash = HashDigest(
        algorithm="sha256",
        value=verified.canonical_sha256(),
    )
    strategy_case_input_hash = case.semantic_input_hash()
    strategy_case_envelope_hash = HashDigest(
        algorithm="sha256",
        value=case.canonical_sha256(),
    )
    capability.require_exact(
        strategy_id=INDUSTRIAL_EVENT_STRATEGY_ID,
        case_id=case.case_id,
        fixture_id=strategy_input.fixture_id,
        fixture_version=strategy_input.fixture_version,
        dataset_release_id=verified.strategy_input_ref.dataset_release_id,
        input_id=verified.input_id,
        input_envelope_hash=input_envelope_hash,
        verified_input_hash=verified_input_hash,
        strategy_case_input_hash=strategy_case_input_hash,
        strategy_case_envelope_hash=strategy_case_envelope_hash,
    )
    return strategy_case_envelope_hash


def _independent_evidence_subset(
    chains: tuple[EvidenceChain, ...],
    *,
    minimum_chains: int,
    minimum_authoritative: int,
) -> tuple[EvidenceChain, ...] | None:
    eligible = tuple(chain for chain in chains if not chain.derivative_of_another_chain)
    required_authoritative_supports = {
        EvidenceSupport.CONTRACT_SIGNED_OR_FORMALLY_PLACED,
        EvidenceSupport.CONTRACT_EFFECTIVE,
        EvidenceSupport.BINDING_MINIMUM_OBLIGATION,
    }
    for size in range(minimum_chains, len(eligible) + 1):
        for subset in combinations(eligible, size):
            if len({chain.source_document_id for chain in subset}) != size:
                continue
            if len({chain.publisher_id for chain in subset}) != size:
                continue
            if len({chain.acquisition_chain_id for chain in subset}) != size:
                continue
            if len({chain.content_hash.value for chain in subset}) != size:
                continue
            evidence_count = sum(len(chain.evidence_ids) for chain in subset)
            if len({item for chain in subset for item in chain.evidence_ids}) != evidence_count:
                continue
            fact_count = sum(len(chain.fact_ids) for chain in subset)
            if len({item for chain in subset for item in chain.fact_ids}) != fact_count:
                continue
            if sum(chain.authoritative_original for chain in subset) < minimum_authoritative:
                continue
            if not any(
                chain.authoritative_original
                and required_authoritative_supports.issubset(set(chain.supports))
                for chain in subset
            ):
                continue
            return tuple(subset)
    return None


def _evaluate_gate_1(
    case: IndustrialEventCase,
    rules: ApprovedIndustrialEventRules,
) -> tuple[EventState, GateResult]:
    event = case.commercial_event
    common: _GateContext = {
        "gate_id": GateId.AUTHENTICITY,
        "evaluated_at": case.decision_at,
    }
    references: _GateReferences = {
        "supporting_fact_ids": event.supporting_fact_ids,
        "conflicting_fact_ids": event.conflicting_fact_ids,
    }
    if event.material_conflict:
        return EventState.E3, _gate(
            **common,
            **references,
            outcome=GateOutcome.ABSTAIN,
            reason_codes=("e4_material_fact_conflict",),
        )

    economic_closure = resolve_economic_closure(
        contract_signed_or_formally_ordered=event.contract_signed_or_formally_ordered,
        contract_effective=event.contract_effective,
        material_conditions_satisfied=event.material_conditions_satisfied,
        binding_minimum_obligation=event.binding_minimum_obligation,
        minimum_obligation_kind=event.minimum_obligation_kind,
        cancellation_can_zero_minimum=event.cancellation_can_zero_minimum,
        return_or_acceptance_can_zero_minimum=(event.return_or_acceptance_can_zero_minimum),
    )
    if economic_closure is False:
        if event.strong_commercial_clue:
            return EventState.E3_5, _gate(
                **common,
                **references,
                outcome=GateOutcome.SHADOW_ONLY,
                reason_codes=("minimum_economic_obligation_not_closed",),
            )
        return EventState.E3, _gate(
            **common,
            **references,
            outcome=GateOutcome.REJECT,
            reason_codes=("e4_and_strong_commercial_clue_absent",),
        )
    if (
        event.authorized_public_evidence is None
        or event.ownership_path_verified is None
        or economic_closure is None
    ):
        reason = (
            "profit_attribution_path_unknown"
            if event.ownership_path_verified is None
            else "minimum_obligation_kind_unknown"
            if event.binding_minimum_obligation is True and event.minimum_obligation_kind is None
            else "e4_key_commercial_fact_unknown"
        )
        return EventState.E3, _gate(
            **common,
            **references,
            outcome=GateOutcome.ABSTAIN,
            reason_codes=(reason,),
        )
    if event.authorized_public_evidence is False or event.ownership_path_verified is False:
        return EventState.E3, _gate(
            **common,
            **references,
            outcome=GateOutcome.REJECT,
            reason_codes=("e4_identity_or_public_authority_failed",),
        )

    selected = _independent_evidence_subset(
        event.evidence_chains,
        minimum_chains=rules.minimum_independent_evidence_chains,
        minimum_authoritative=rules.minimum_authoritative_original_chains,
    )
    if selected is None:
        return EventState.E4, _gate(
            **common,
            **references,
            outcome=GateOutcome.ABSTAIN,
            reason_codes=("insufficient_independent_evidence_chains",),
            details={
                "minimum_independent_chains": rules.minimum_independent_evidence_chains,
                "minimum_authoritative_originals": (rules.minimum_authoritative_original_chains),
            },
        )
    selected_fact_ids = tuple(
        sorted(set(event.supporting_fact_ids).union(*(chain.fact_ids for chain in selected)))
    )
    pass_reason = (
        "e4_minimum_quantity_and_evidence_satisfied"
        if event.minimum_obligation_kind is MinimumObligationKind.QUANTITY
        else "e4_and_independent_evidence_satisfied"
    )
    return EventState.E4, _gate(
        gate_id=GateId.AUTHENTICITY,
        evaluated_at=case.decision_at,
        outcome=GateOutcome.PASS,
        reason_codes=(pass_reason,),
        supporting_fact_ids=selected_fact_ids,
        conflicting_fact_ids=event.conflicting_fact_ids,
        details={"selected_evidence_chain_ids": tuple(chain.chain_id for chain in selected)},
    )


_PROFIT_DECIMAL_FIELDS = (
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
)


def _evaluate_gate_2(
    case: IndustrialEventCase,
    inputs: ProfitBridgeInput | None,
    rules: ApprovedIndustrialEventRules,
) -> tuple[GateResult, ProfitBridge | None]:
    common: _GateContext = {
        "gate_id": GateId.PROFIT_MATERIALITY,
        "evaluated_at": case.decision_at,
    }
    if inputs is None:
        return (
            _gate(
                **common,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("profit_bridge_missing",),
            ),
            None,
        )
    references: _GateReferences = {
        "supporting_fact_ids": inputs.supporting_fact_ids,
        "conflicting_fact_ids": inputs.conflicting_fact_ids,
    }
    missing = tuple(field for field in _PROFIT_DECIMAL_FIELDS if getattr(inputs, field) is None)
    if missing:
        reason = (
            "price_and_recognizable_revenue_unknown"
            if "ntm_recognizable_revenue" in missing
            and case.commercial_event.minimum_obligation_kind is MinimumObligationKind.QUANTITY
            else "profit_bridge_required_field_unknown"
        )
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=(reason,),
                details={"missing_fields": missing},
            ),
            None,
        )
    if inputs.conflicting_fact_ids:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("profit_bridge_fact_conflict",),
            ),
            None,
        )
    policy_flags = (
        inputs.units_consistent,
        inputs.attribution_verified,
        inputs.counterfactual_bridge_verified,
    )
    if inputs.currency != rules.currency:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("profit_bridge_currency_mismatch",),
            ),
            None,
        )
    if any(flag is not True for flag in policy_flags):
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("profit_bridge_scope_or_unit_unverified",),
            ),
            None,
        )
    values = {field: _decimal(field, getattr(inputs, field)) for field in _PROFIT_DECIMAL_FIELDS}
    nonnegative_fields = (
        "ntm_recognizable_revenue",
        "incremental_operating_expense",
        "incremental_tax_and_surcharges",
        "minority_interest_deduction",
        "incremental_capex",
    )
    margin = values["incremental_gross_margin_rate"]
    if any(values[field] < 0 for field in nonnegative_fields) or not (0 <= margin <= 1):
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("profit_bridge_decimal_domain_invalid",),
            ),
            None,
        )

    gross_profit = _exact_product(values["ntm_recognizable_revenue"], margin)
    parent_profit = _exact_sum(
        gross_profit,
        _exact_negate(values["incremental_operating_expense"]),
        _exact_negate(values["incremental_tax_and_surcharges"]),
        _exact_negate(values["minority_interest_deduction"]),
    )
    free_cash_flow = _exact_sum(
        parent_profit,
        values["incremental_non_cash_items"],
        _exact_negate(values["incremental_working_capital"]),
        _exact_negate(values["incremental_capex"]),
    )
    base = values["counterfactual_ntm_normalized_parent_profit_base"]
    downside = values["counterfactual_ntm_normalized_parent_profit_downside"]
    materiality = _audit_ratio(parent_profit, base) if base > 0 else None

    bridge = ProfitBridge(
        currency=rules.currency,
        incremental_gross_profit=decimal_to_canonical_text(gross_profit),
        ntm_incremental_parent_normalized_profit=decimal_to_canonical_text(parent_profit),
        ntm_incremental_free_cash_flow=decimal_to_canonical_text(free_cash_flow),
        profit_materiality=(
            decimal_to_canonical_text(materiality) if materiality is not None else None
        ),
    )
    if base <= 0 or downside <= 0:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.SHADOW_ONLY,
                reason_codes=("fragile_profit_shadow_track",),
                details={"profit_bridge": bridge.to_json_value()},
            ),
            bridge,
        )
    assert materiality is not None
    threshold_profit = _exact_product(rules.profit_materiality_threshold, base)
    outcome = GateOutcome.PASS if parent_profit >= threshold_profit else GateOutcome.REJECT
    reason = (
        "profit_materiality_at_or_above_threshold"
        if outcome is GateOutcome.PASS
        else "profit_materiality_below_threshold"
    )
    return (
        _gate(
            **common,
            **references,
            outcome=outcome,
            reason_codes=(reason,),
            details={
                "profit_bridge": bridge.to_json_value(),
                "threshold": decimal_to_canonical_text(rules.profit_materiality_threshold),
                "display_profit_materiality": decimal_to_display_text(materiality),
            },
        ),
        bridge,
    )


def _terms_match_except_amount(
    prior: ContractExpectationTerms,
    current: ContractExpectationTerms,
) -> bool:
    return (
        prior.counterparty_scope == current.counterparty_scope
        and prior.product_scope == current.product_scope
        and prior.currency == current.currency
        and prior.effective_period == current.effective_period
        and prior.material_conditions == current.material_conditions
    )


def _evaluate_gate_3(
    case: IndustrialEventCase,
    inputs: ExpectationInput | None,
    rules: ApprovedIndustrialEventRules,
) -> tuple[GateResult, ExpectationClass]:
    common: _GateContext = {
        "gate_id": GateId.EXPECTATION_GAP,
        "evaluated_at": case.decision_at,
    }
    if inputs is None or inputs.prior_snapshot is None:
        return (
            _gate(
                **common,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("prior_expectation_snapshot_unknown",),
            ),
            ExpectationClass.UNKNOWN,
        )
    snapshot = inputs.prior_snapshot
    supporting = tuple(sorted(set(inputs.supporting_fact_ids).union(snapshot.supporting_fact_ids)))
    references: _GateReferences = {
        "supporting_fact_ids": supporting,
        "conflicting_fact_ids": snapshot.conflicting_fact_ids,
    }
    cutoff = case.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff
    if (
        snapshot.material_conflict
        or not snapshot.explicit_public_statement
        or snapshot.based_only_on_search_absence
        or snapshot.available_at >= case.commercial_event.e4_first_public_at
        or snapshot.available_at > cutoff
        or not _terms_match_except_amount(snapshot.terms, inputs.current_terms)
        or snapshot.terms.currency != rules.currency
        or inputs.current_terms.currency != rules.currency
        or snapshot.terms.binding_minimum_amount is None
        or inputs.current_terms.binding_minimum_amount is None
    ):
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("prior_expectation_not_strictly_reconstructable",),
            ),
            ExpectationClass.UNKNOWN,
        )
    prior = _decimal("prior_binding_minimum_amount", snapshot.terms.binding_minimum_amount)
    current = _decimal(
        "current_binding_minimum_amount", inputs.current_terms.binding_minimum_amount
    )
    if prior < 0 or current <= 0:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("expectation_amount_relation_unsupported",),
            ),
            ExpectationClass.UNKNOWN,
        )
    if prior == 0:
        expectation_class = ExpectationClass.UNEXPECTED
        outcome = GateOutcome.PASS
        reason = "binding_minimum_was_explicitly_zero"
    elif prior < current:
        expectation_class = ExpectationClass.PARTIALLY_PRICED
        outcome = GateOutcome.PASS
        reason = "prior_positive_but_strictly_lower"
    elif prior == current:
        expectation_class = ExpectationClass.FULLY_PRICED
        outcome = GateOutcome.REJECT
        reason = "prior_and_e4_terms_identical"
    else:
        expectation_class = ExpectationClass.UNKNOWN
        outcome = GateOutcome.ABSTAIN
        reason = "prior_above_actual_or_unsupported_relation"
    return (
        _gate(
            **common,
            **references,
            outcome=outcome,
            reason_codes=(reason,),
            details={"expectation_class": expectation_class.value},
        ),
        expectation_class,
    )


_VALUATION_DECIMAL_FIELDS = (
    "base_business_equity_value",
    "event_finite_life_incremental_fcf_present_value",
    "downside_scenario_equity_value",
    "fully_diluted_shares",
    "first_executable_price",
    "explicit_cost_rate",
    "explicit_slippage_rate",
)


def _evaluate_gate_4(
    case: IndustrialEventCase,
    inputs: ValuationInput | None,
    rules: ApprovedIndustrialEventRules,
) -> tuple[GateResult, ScenarioValuation | None]:
    common: _GateContext = {
        "gate_id": GateId.EXECUTABLE_RETURN,
        "evaluated_at": case.decision_at,
    }
    if inputs is None:
        return (
            _gate(
                **common,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("valuation_input_missing",),
            ),
            None,
        )
    references: _GateReferences = {"supporting_fact_ids": inputs.supporting_fact_ids}
    missing = tuple(field for field in _VALUATION_DECIMAL_FIELDS if getattr(inputs, field) is None)
    if inputs.first_executable_at is None:
        missing += ("first_executable_at",)
    if inputs.next_verification_trading_days is None:
        missing += ("next_verification_trading_days",)
    if missing:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("valuation_required_field_unknown",),
                details={"missing_fields": missing},
            ),
            None,
        )
    if (
        inputs.currency != rules.currency
        or inputs.base_business_excludes_event_value is not True
        or inputs.event_value_is_finite_life is not True
    ):
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("valuation_scope_or_double_counting_unverified",),
            ),
            None,
        )
    cutoff = case.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff
    assert inputs.first_executable_at is not None
    if inputs.first_executable_at > cutoff or inputs.first_executable_at > case.decision_at:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("first_executable_price_not_pit_available",),
            ),
            None,
        )
    values = {field: _decimal(field, getattr(inputs, field)) for field in _VALUATION_DECIMAL_FIELDS}
    if (
        values["base_business_equity_value"] < 0
        or values["event_finite_life_incremental_fcf_present_value"] < 0
        or values["downside_scenario_equity_value"] < 0
        or values["fully_diluted_shares"] <= 0
        or values["first_executable_price"] <= 0
        or values["explicit_cost_rate"] < 0
        or values["explicit_slippage_rate"] < 0
    ):
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("valuation_decimal_domain_invalid",),
            ),
            None,
        )
    market_cap = _exact_product(values["first_executable_price"], values["fully_diluted_shares"])
    base_value = _exact_sum(
        values["base_business_equity_value"],
        values["event_finite_life_incremental_fcf_present_value"],
    )
    friction = _exact_sum(values["explicit_cost_rate"], values["explicit_slippage_rate"])
    market_cap_with_friction = _exact_product(
        market_cap,
        _exact_sum(Decimal(1), friction),
    )
    net_base_numerator = _exact_difference(base_value, market_cap_with_friction)
    net_downside_numerator = _exact_difference(
        values["downside_scenario_equity_value"], market_cap_with_friction
    )
    downside_loss_numerator = (
        _exact_negate(net_downside_numerator) if net_downside_numerator < 0 else Decimal(0)
    )
    net_base = _audit_ratio(net_base_numerator, market_cap)
    net_downside = _audit_ratio(net_downside_numerator, market_cap)
    downside_loss = _audit_ratio(downside_loss_numerator, market_cap)
    reward = (
        _audit_ratio(net_base_numerator, downside_loss_numerator)
        if downside_loss_numerator > 0
        else None
    )
    valuation = ScenarioValuation(
        currency=rules.currency,
        first_executable_market_cap=decimal_to_canonical_text(market_cap),
        base_scenario_equity_value=decimal_to_canonical_text(base_value),
        downside_scenario_equity_value=decimal_to_canonical_text(
            values["downside_scenario_equity_value"]
        ),
        explicit_friction_rate=decimal_to_canonical_text(friction),
        net_base_remaining_return=decimal_to_canonical_text(net_base),
        net_downside_return=decimal_to_canonical_text(net_downside),
        downside_loss=decimal_to_canonical_text(downside_loss),
        reward_to_downside=decimal_to_canonical_text(reward) if reward is not None else None,
    )
    if downside_loss_numerator <= 0:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("downside_loss_not_positive",),
                details={"scenario_valuation": valuation.to_json_value()},
            ),
            valuation,
        )
    assert inputs.next_verification_trading_days is not None
    if inputs.next_verification_trading_days > rules.next_verification_trading_days_max:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.REJECT,
                reason_codes=("verification_window_above_limit",),
                details={"scenario_valuation": valuation.to_json_value()},
            ),
            valuation,
        )
    if len(case.falsifiers) < 2:
        return (
            _gate(
                **common,
                **references,
                outcome=GateOutcome.ABSTAIN,
                reason_codes=("minimum_falsifiers_missing",),
                details={"scenario_valuation": valuation.to_json_value()},
            ),
            valuation,
        )
    assert reward is not None
    minimum_base_return_numerator = _exact_product(
        rules.net_base_return_threshold,
        market_cap,
    )
    minimum_reward_numerator = _exact_product(
        rules.reward_to_downside_threshold,
        downside_loss_numerator,
    )
    passed = (
        net_base_numerator >= minimum_base_return_numerator
        and net_base_numerator >= minimum_reward_numerator
    )
    outcome = GateOutcome.PASS if passed else GateOutcome.REJECT
    reason = "return_odds_and_window_pass" if passed else "executable_return_below_threshold"
    return (
        _gate(
            **common,
            **references,
            outcome=outcome,
            reason_codes=(reason,),
            details={
                "scenario_valuation": valuation.to_json_value(),
                "net_base_threshold": decimal_to_canonical_text(rules.net_base_return_threshold),
                "reward_to_downside_threshold": decimal_to_canonical_text(
                    rules.reward_to_downside_threshold
                ),
                "display_net_base_return": decimal_to_display_text(net_base),
                "display_reward_to_downside": decimal_to_display_text(reward),
            },
        ),
        valuation,
    )


def _decision_for_outcome(outcome: GateOutcome) -> DecisionState:
    mapping = {
        GateOutcome.REJECT: DecisionState.REJECT,
        GateOutcome.ABSTAIN: DecisionState.ABSTAIN,
        GateOutcome.SHADOW_ONLY: DecisionState.SHADOW_ONLY,
    }
    if outcome not in mapping:
        raise IndustrialEventEvaluationError(
            "TERMINAL_OUTCOME_INVALID", f"unexpected terminal Gate outcome: {outcome.value}"
        )
    return mapping[outcome]


def _facts_from_gates(gates: Iterable[GateResult]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    gate_tuple = tuple(gates)
    supporting = tuple(
        sorted({fact_id for gate in gate_tuple for fact_id in gate.supporting_fact_ids})
    )
    conflicting = tuple(
        sorted({fact_id for gate in gate_tuple for fact_id in gate.conflicting_fact_ids})
    )
    return supporting, conflicting


def evaluate_industrial_event(
    case: IndustrialEventCase,
    *,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
    fixture_capability: ApprovedSyntheticFixtureCapability,
) -> IndustrialEventDecision:
    """Evaluate one research-only synthetic case using an exact approved bundle."""

    if not isinstance(case, IndustrialEventCase):
        raise TypeError("case must be an IndustrialEventCase")
    rules = ApprovedIndustrialEventRules.from_approved_bundle(
        rule_document,
        approval_capability,
    )
    strategy_input = case.strategy_input
    if not (
        strategy_input.synthetic
        and strategy_input.validation_only
        and strategy_input.not_a_published_release
        and strategy_input.not_strategy_evidence
        and not strategy_input.authorizes_positions
        and not strategy_input.authorizes_orders
    ):
        raise IndustrialEventEvaluationError(
            "SYNTHETIC_AUTHORITY_INVALID", "strategy input crossed its validation-only boundary"
        )
    if case.run_mode.value != "research":
        raise IndustrialEventEvaluationError(
            "RUN_MODE_FORBIDDEN", "Stage 2B synthetic evaluation is research-only"
        )
    if not strategy_input.fixture_id.startswith("synthetic_fixture_stage2b_"):
        raise IndustrialEventEvaluationError(
            "FIXTURE_ID_NOT_APPROVED",
            "fixture_id must use the approved Stage 2B synthetic namespace",
        )
    if strategy_input.fixture_version != rules.fixture_version:
        raise IndustrialEventEvaluationError(
            "FIXTURE_VERSION_NOT_APPROVED", "fixture_version does not match the approved profile"
        )
    release_id = strategy_input.verified_knowledge_input.strategy_input_ref.dataset_release_id
    if not release_id.startswith(rules.dataset_release_id_prefix):
        raise IndustrialEventEvaluationError(
            "FIXTURE_RELEASE_NAMESPACE_INVALID", "synthetic Release namespace is required"
        )
    _validate_case_payload_bindings(case)
    _validate_fact_bindings(case)
    _validate_pit(case)
    strategy_case_envelope_hash = _require_fixture_capability(case, fixture_capability)

    event_state, gate_1 = _evaluate_gate_1(case, rules)
    gates: list[GateResult] = [gate_1]
    profit_bridge: ProfitBridge | None = None
    expectation_class: ExpectationClass | None = None
    scenario_valuation: ScenarioValuation | None = None

    if gate_1.outcome is GateOutcome.PASS:
        gate_2, profit_bridge = _evaluate_gate_2(case, case.profit_bridge, rules)
        gates.append(gate_2)
    else:
        gate_2 = None
    if gate_2 is not None and gate_2.outcome is GateOutcome.PASS:
        gate_3, expectation_class = _evaluate_gate_3(case, case.expectation, rules)
        gates.append(gate_3)
    else:
        gate_3 = None
    if gate_3 is not None and gate_3.outcome is GateOutcome.PASS:
        gate_4, scenario_valuation = _evaluate_gate_4(case, case.valuation, rules)
        gates.append(gate_4)
    else:
        gate_4 = None

    terminal = gates[-1]
    while len(gates) < len(_GATE_ORDER):
        gates.append(
            _skipped(
                gate_id=_GATE_ORDER[len(gates)],
                evaluated_at=case.decision_at,
                terminal=terminal,
            )
        )
    if gate_4 is not None and gate_4.outcome is GateOutcome.PASS:
        decision_state = DecisionState.TRADE_READY
    else:
        if terminal.outcome is None or terminal.outcome is GateOutcome.PASS:
            raise IndustrialEventEvaluationError(
                "DECISION_AGGREGATION_INVALID", "terminal Gate did not determine a result"
            )
        decision_state = _decision_for_outcome(terminal.outcome)

    supporting, conflicting = _facts_from_gates(gates)
    return IndustrialEventDecision(
        case_id=case.case_id,
        decision_at=case.decision_at,
        event_state=event_state,
        decision_state=decision_state,
        gate_results=tuple(gates),
        rule_bundle_hash=rules.bundle_hash,
        approval_id=rules.approval_id,
        strategy_case_envelope_hash=strategy_case_envelope_hash,
        supporting_fact_ids=supporting,
        conflicting_fact_ids=conflicting,
        falsifiers=case.falsifiers,
        profit_bridge=profit_bridge,
        expectation_class=expectation_class,
        scenario_valuation=scenario_valuation,
    )
