from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import (
    DecisionState,
    ExpectationClass,
    GateOutcome,
    HashDigest,
    PositionState,
)
from invest_system.strategies.industrial_event import (
    STAGE4_4A3_RULE_BUNDLE_SHA256,
    STAGE4_4A4_RULE_APPROVAL_ID,
    STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A4_RULE_BUNDLE_SHA256,
    STAGE4_4A4_RULES_SHA256,
    ApprovedStage4ExpectationValuationExitRules,
    DecimalInterval,
    EconomicBasis,
    EvidenceExitKind,
    EvidenceExitTrigger,
    ExitDisposition,
    ExpectationSnapshot,
    HoldingKind,
    MarketPricingState,
    PreE4MarketContext,
    PriorExpectationState,
    ProfitTrack,
    ProofPlan,
    ScenarioEquityValueSet,
    Stage4ExitInput,
    Stage4ExpectationValuationExitCase,
    Stage4GateResult,
    Stage4GateRuleAssessment,
    Stage4RuleEvaluationState,
    Stage4ValuationSet,
    SyntheticHoldingSnapshot,
    SyntheticResearchPriceAssumption,
    TriggerState,
    ValuationComponent,
    ValuationComponentRole,
    VersionedArtifactIdentity,
    bind_expectation_snapshot,
    bind_pre_e4_market_context,
    bind_proof_plan,
    bind_stage4_valuation_set,
    bind_synthetic_holding_snapshot,
    bind_synthetic_price_assumption,
    evaluate_stage4_expectation_valuation_exit,
)

MACHINE_DIR = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
RULE_BUNDLE_PATH = MACHINE_DIR / (
    "industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = MACHINE_DIR / (
    "industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0.approval.json"
)
APPROVAL_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A4市场预期估值与退出批准记录_v0.1.md"
)
DRAFT_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A4市场预期估值与退出规则包_v0.1.md"
)

CASE_ID = "stage4_4a4_case_001"
SNAPSHOT_AT = datetime(2025, 1, 5, tzinfo=UTC)
E4_AT = datetime(2025, 1, 10, tzinfo=UTC)
CUTOFF = datetime(2025, 1, 12, tzinfo=UTC)


def _hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _identity(identifier: str, *, as_of: datetime = SNAPSHOT_AT) -> VersionedArtifactIdentity:
    return VersionedArtifactIdentity(
        artifact_id=identifier,
        version="0.1.0",
        as_of=as_of,
        knowledge_cutoff=CUTOFF,
        supersedes_artifact_id=None,
        declared_content_hash=_hash("0"),
    )


def _basis() -> EconomicBasis:
    return EconomicBasis(
        event_identity="event_order_001",
        subject_scope="issuer_001",
        product_scope="product_001",
        currency="CNY",
        unit="CNY_million",
        effective_period="2025-01-10/2026-01-10",
        obligation_basis="binding_minimum",
        profit_basis="parent_normalized_profit",
        fcf_basis="incremental_fcf",
        material_conditions=("acceptance", "non_cancelable_floor"),
    )


def _assessment(rule_id: str, outcome: GateOutcome = GateOutcome.PASS) -> Stage4GateRuleAssessment:
    return Stage4GateRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=("test_upstream",),
    )


def _upstream(*, gate2: GateOutcome = GateOutcome.PASS) -> Stage4GateResult:
    return Stage4GateResult(
        case_id=CASE_ID,
        gate_1=_assessment("FR-GATE-001"),
        scenario_validation=_assessment("FR-GATE-003"),
        gate_2=_assessment("FR-GATE-002", gate2),
        gate_3=Stage4GateRuleAssessment(
            rule_id="FR-GATE-004",
            evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
            outcome=None,
            reason_codes=("rule_batch_not_approved",),
        ),
        gate_4=Stage4GateRuleAssessment(
            rule_id="FR-GATE-005",
            evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
            outcome=None,
            reason_codes=("rule_batch_not_approved",),
        ),
        overall_outcome=gate2,
        profit_track=ProfitTrack.STANDARD,
        base_counterfactual_profit="100",
        downside_counterfactual_profit="80",
        counterfactual_profit_interval=DecimalInterval("90", "110"),
        base_incremental_profit="20",
        base_incremental_fcf="18",
        base_profit_materiality="0.20",
        gate2_research_qualified=gate2 is GateOutcome.PASS,
        remaining_gate_ids=("FR-GATE-004", "FR-GATE-005"),
        full_stage4_decision=None,
        position_state=PositionState.FLAT,
        target_weight=None,
        order_intent=None,
        rule_bundle_hash=HashDigest(algorithm="sha256", value=STAGE4_4A3_RULE_BUNDLE_SHA256),
        rule_approval_id="rule_approval_stage4_4a3_gate_profit_scenarios_v0_1_0",
        rule_approval_record_hash=_hash("a"),
    )


def _expectation(
    *,
    prior_state: PriorExpectationState = PriorExpectationState.EXPLICITLY_ABSENT,
    as_of: datetime = SNAPSHOT_AT,
) -> ExpectationSnapshot:
    value = ExpectationSnapshot(
        identity=_identity("expectation_001", as_of=as_of),
        e4_first_public_at=E4_AT,
        basis=_basis(),
        prior_state=prior_state,
        prior_binding_interval=(
            DecimalInterval("10", "20")
            if prior_state is PriorExpectationState.BINDING_EXPECTED
            else None
        ),
        prior_profit_interval=(
            DecimalInterval("5", "10")
            if prior_state is PriorExpectationState.BINDING_EXPECTED
            else None
        ),
        prior_fcf_interval=(
            DecimalInterval("4", "9")
            if prior_state is PriorExpectationState.BINDING_EXPECTED
            else None
        ),
        coverage_by_material_dimension=("amount", "period", "profit", "fcf"),
        explicit_absence_fact_ids=("fact_prior_absence",),
        fact_ids=("fact_prior_absence",),
        assumption_ids=(),
        derived_ids=(),
    )
    return bind_expectation_snapshot(value)


def _market(*, price: str = "8") -> PreE4MarketContext:
    value = PreE4MarketContext(
        identity=_identity("market_context_001"),
        window_start_at=SNAPSHOT_AT,
        window_end_at=E4_AT - timedelta(microseconds=1),
        price=price,
        fully_diluted_shares="100",
        benchmark_id="csi300",
        benchmark_return="0.01",
        security_return="0.02",
        security_turnover="1000",
        reference_turnover="900",
        security_price_observation_ref="price_fact_001",
        fully_diluted_shares_ref="shares_fact_001",
        source_refs=("market_source_001",),
        method_id="pre_e4_context",
        method_version="1",
        method_hash=_hash("b"),
    )
    return bind_pre_e4_market_context(value)


def _valuation(
    *,
    base: DecimalInterval | None = None,
    downside: DecimalInterval | None = None,
    duplicate_component: bool = False,
) -> Stage4ValuationSet:
    components = (
        ValuationComponent(
            component_id="base_component",
            economic_key="base_cashflow",
            role=ValuationComponentRole.BASE_BUSINESS,
            period="finite_base",
            fact_ids=("fact_base",),
            assumption_ids=(),
            scenario_scope=("base", "downside", "stress", "upside"),
        ),
        ValuationComponent(
            component_id="event_component",
            economic_key=("base_cashflow" if duplicate_component else "event_cashflow"),
            role=ValuationComponentRole.EVENT_INCREMENTAL,
            period="finite_event",
            fact_ids=("fact_event",),
            assumption_ids=(),
            scenario_scope=("base", "downside", "stress", "upside"),
        ),
    )
    value = Stage4ValuationSet(
        identity=_identity("valuation_001", as_of=E4_AT),
        basis=_basis(),
        primary_method_id="finite_dcf",
        method_version="1",
        method_hash=_hash("c"),
        explicit_input_refs=("valuation_input_001",),
        base_business_equity_value=DecimalInterval("600", "650"),
        event_finite_life_value=DecimalInterval("250", "300"),
        scenario_equity_values=ScenarioEquityValueSet(
            base=base or DecimalInterval("1150", "1250"),
            downside=downside or DecimalInterval("925", "1000"),
            upside=DecimalInterval("1400", "1500"),
            stress=DecimalInterval("800", "850"),
        ),
        fully_diluted_shares="100",
        tax_basis="post_tax",
        minority_basis="after_minority",
        ownership_basis="parent_attributable",
        components=components,
    )
    return bind_stage4_valuation_set(value)


def _price(*, synthetic: bool = True) -> SyntheticResearchPriceAssumption:
    value = SyntheticResearchPriceAssumption(
        identity=_identity("price_assumption_001", as_of=E4_AT),
        price="10",
        fully_diluted_shares="100",
        explicit_cost_rate="0",
        explicit_slippage_rate="0",
        currency="CNY",
        unit="CNY_million",
        source_fixture_ref="fixture_price_001",
        synthetic=synthetic,
    )
    return bind_synthetic_price_assumption(value)


def _proof(*, days: int = 120) -> ProofPlan:
    value = ProofPlan(
        identity=_identity("proof_plan_001", as_of=E4_AT),
        observable_falsifier_ids=("falsifier_001", "falsifier_002"),
        next_public_verification_event_id="verification_001",
        verification_within_trading_days=days,
        trading_calendar_version="calendar_v1",
    )
    return bind_proof_plan(value)


def _evidence_triggers(
    *,
    confirmed: EvidenceExitKind | None = None,
    unknown: EvidenceExitKind | None = None,
) -> tuple[EvidenceExitTrigger, ...]:
    return tuple(
        EvidenceExitTrigger(
            trigger_id=f"trigger_{kind.value}",
            kind=kind,
            state=(
                TriggerState.CONFIRMED
                if kind is confirmed
                else TriggerState.UNKNOWN
                if kind is unknown
                else TriggerState.REFUTED
            ),
            observable_condition=f"observe {kind.value}",
            evaluation_window="proof_window",
            source_type="public_evidence",
            component_ids=("event_component",),
            fact_ids=(("fact_exit",) if kind is confirmed else ()),
        )
        for kind in EvidenceExitKind
    )


def _holding(
    *,
    loss: str = "50",
    budget: str = "100",
    valuation_hash: HashDigest | None = None,
) -> SyntheticHoldingSnapshot:
    value = SyntheticHoldingSnapshot(
        identity=_identity("holding_001", as_of=E4_AT),
        case_id=CASE_ID,
        registered_account_loss_budget_amount=budget,
        current_actual_loss_amount=loss,
        currency="CNY",
        established_rule_hash=HashDigest(algorithm="sha256", value=STAGE4_4A4_RULE_BUNDLE_SHA256),
        established_valuation_hash=valuation_hash or _valuation().identity.declared_content_hash,
    )
    return bind_synthetic_holding_snapshot(value)


def _exit(
    *,
    holding: SyntheticHoldingSnapshot | None = None,
    triggers: tuple[EvidenceExitTrigger, ...] | None = None,
    elapsed: int = 30,
    verification_confirmed: bool = True,
    current_market_cap: str = "800",
    current_base_lower: str = "1150",
    new_evidence: bool = False,
    reunderwriting_passed: bool = True,
) -> Stage4ExitInput:
    return Stage4ExitInput(
        holding_kind=HoldingKind.SYNTHETIC_HOLDING,
        holding_snapshot=holding or _holding(),
        evidence_triggers=triggers or _evidence_triggers(),
        elapsed_trading_days=elapsed,
        trading_calendar_version="calendar_v1",
        preregistered_verification_event_confirmed=verification_confirmed,
        current_market_cap=current_market_cap,
        current_base_value_lower=current_base_lower,
        new_e5_e6_value_evidence=new_evidence,
        reunderwriting_passed=reunderwriting_passed,
    )


def _case(
    *,
    upstream: Stage4GateResult | None = None,
    expectation: ExpectationSnapshot | None = None,
    market: PreE4MarketContext | None = None,
    valuation: Stage4ValuationSet | None = None,
    price: SyntheticResearchPriceAssumption | None = None,
    proof: ProofPlan | None = None,
    exit_input: Stage4ExitInput | None = None,
    anonymous: bool = True,
    reads_kb: bool = False,
) -> Stage4ExpectationValuationExitCase:
    valuation_value = valuation or _valuation()
    exit_value = exit_input or _exit(
        holding=_holding(valuation_hash=valuation_value.identity.declared_content_hash)
    )
    return Stage4ExpectationValuationExitCase(
        case_id=CASE_ID,
        knowledge_cutoff=CUTOFF,
        e4_first_public_at=E4_AT,
        upstream_gate_result=upstream or _upstream(),
        e4_basis=_basis(),
        e4_binding_obligation_interval=DecimalInterval("100", "120"),
        e4_incremental_profit_interval=DecimalInterval("20", "25"),
        e4_incremental_fcf_interval=DecimalInterval("18", "23"),
        expectation_snapshot=expectation or _expectation(),
        pre_e4_market_context=market or _market(),
        valuation_set=valuation_value,
        price_assumption=price or _price(),
        proof_plan=proof or _proof(),
        exit_input=exit_value,
        anonymous_synthetic_fixture=anonymous,
        reads_kb_internal_state=reads_kb,
    )


def _approved_rules(repository_root: Path) -> ApprovedStage4ExpectationValuationExitRules:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    capability = RuleApprovalRegistry((approval,)).require(document)
    return ApprovedStage4ExpectationValuationExitRules.from_approved_bundle(document, capability)


def test_4a4_artifacts_bind_exact_owner_approval(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    assert document.bundle_hash().value == STAGE4_4A4_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE4_4A4_RULES_SHA256
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_id == STAGE4_4A4_RULE_APPROVAL_ID
    assert approval.canonical_sha256() == STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256
    source = document.rules["approved_source_binding"]
    binding = document.rules["document_binding"]
    assert isinstance(source, Mapping) and isinstance(source["hash"], Mapping)
    assert isinstance(binding, Mapping) and isinstance(binding["hash"], Mapping)
    assert (
        sha256((repository_root / DRAFT_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == (source["hash"]["value"])
    )
    assert (
        sha256((repository_root / APPROVAL_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == (binding["hash"]["value"])
    )


def test_all_gates_pass_at_exact_threshold_and_keep_zero_authority(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_expectation_valuation_exit(_case(), _approved_rules(repository_root))

    assert result.gate_result.gate_3.outcome is GateOutcome.PASS
    assert result.gate_result.public_expectation_class is ExpectationClass.UNEXPECTED
    assert result.gate_result.market_pricing_state is MarketPricingState.NOT_FULLY_REFLECTED
    assert result.gate_result.gate_4.outcome is GateOutcome.PASS
    assert result.gate_result.net_base_remaining_return == "0.15"
    assert result.gate_result.reward_to_downside == "2"
    assert result.gate_result.research_decision_label is DecisionState.TRADE_READY
    assert result.gate_result.position_state is PositionState.FLAT
    assert result.gate_result.full_stage4_capability is False
    assert result.exit_result.disposition is ExitDisposition.HOLD
    assert result.authorizes_backtest is result.authorizes_orders is False


def test_gate3_fully_reflected_rejects_and_short_circuits_gate4(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(market=_market(price="10")), _approved_rules(repository_root)
    )

    assert result.gate_result.market_pricing_state is MarketPricingState.FULLY_REFLECTED
    assert result.gate_result.gate_3.outcome is GateOutcome.REJECT
    assert result.gate_result.gate_4.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED


def test_directional_prior_abstains(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(expectation=_expectation(prior_state=PriorExpectationState.DIRECTIONAL_NONBINDING)),
        _approved_rules(repository_root),
    )
    assert result.gate_result.gate_3.outcome is GateOutcome.ABSTAIN


def test_binding_prior_with_strictly_higher_profit_and_fcf_passes(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(expectation=_expectation(prior_state=PriorExpectationState.BINDING_EXPECTED)),
        _approved_rules(repository_root),
    )
    assert result.gate_result.public_expectation_class is ExpectationClass.PARTIALLY_PRICED
    assert result.gate_result.gate_3.outcome is GateOutcome.PASS


def test_market_implied_interval_touch_is_indeterminate(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(market=_market(price="8.5")), _approved_rules(repository_root)
    )
    assert result.gate_result.market_pricing_state is MarketPricingState.INDETERMINATE
    assert result.gate_result.gate_3.outcome is GateOutcome.ABSTAIN


def test_nonpositive_pre_e4_market_value_blocks(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(market=_market(price="0")), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_3.outcome is GateOutcome.BLOCKED
    assert result.gate_result.gate_3.reason_codes == ("PRE_E4_MARKET_VALUE_OR_TURNOVER_INVALID",)


def test_post_e4_expectation_backfill_blocks(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(expectation=_expectation(as_of=E4_AT)), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_3.outcome is GateOutcome.BLOCKED


def test_gate4_downside_loss_zero_abstains(repository_root: Path) -> None:
    valuation = _valuation(downside=DecimalInterval("1100", "1125"))
    result = evaluate_stage4_expectation_valuation_exit(
        _case(valuation=valuation), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_4.outcome is GateOutcome.ABSTAIN
    assert result.gate_result.downside_loss == "0"


def test_gate4_only_upside_reaches_threshold_rejects(repository_root: Path) -> None:
    valuation = _valuation(
        base=DecimalInterval("1100", "1200"),
        downside=DecimalInterval("950", "1000"),
    )
    result = evaluate_stage4_expectation_valuation_exit(
        _case(valuation=valuation), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_4.outcome is GateOutcome.REJECT
    assert result.gate_result.gate_4.reason_codes == ("GATE4_ONLY_UPSIDE_REACHES_THRESHOLD",)


def test_proof_window_121_rejects(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(proof=_proof(days=121)), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_4.outcome is GateOutcome.REJECT


def test_duplicate_valuation_economic_component_blocks(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(valuation=_valuation(duplicate_component=True)), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_3.outcome is GateOutcome.BLOCKED


def test_no_position_is_not_applicable(repository_root: Path) -> None:
    exit_input = Stage4ExitInput(
        holding_kind=HoldingKind.NO_POSITION,
        holding_snapshot=None,
        evidence_triggers=(),
        elapsed_trading_days=None,
        trading_calendar_version=None,
        preregistered_verification_event_confirmed=None,
        current_market_cap=None,
        current_base_value_lower=None,
        new_e5_e6_value_evidence=None,
        reunderwriting_passed=None,
    )
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=exit_input), _approved_rules(repository_root)
    )
    assert result.exit_result.disposition is ExitDisposition.NOT_APPLICABLE


@pytest.mark.parametrize("kind", list(EvidenceExitKind))
def test_each_evidence_exit_kind_can_confirm(
    repository_root: Path,
    kind: EvidenceExitKind,
) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(triggers=_evidence_triggers(confirmed=kind))),
        _approved_rules(repository_root),
    )
    assert result.exit_result.disposition is ExitDisposition.EXIT_CANDIDATE
    assert f"trigger_{kind.value}" in result.exit_result.confirmed_trigger_ids


def test_risk_budget_equal_boundary_confirms_exit(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(holding=_holding(loss="100", budget="100"))),
        _approved_rules(repository_root),
    )
    assert "risk_budget_exit" in result.exit_result.confirmed_trigger_ids


def test_time_120_boundary_confirms_exit(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(elapsed=120, verification_confirmed=False)),
        _approved_rules(repository_root),
    )
    assert "time_exit" in result.exit_result.confirmed_trigger_ids


def test_value_equal_boundary_confirms_exit(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(current_market_cap="1150", current_base_lower="1150")),
        _approved_rules(repository_root),
    )
    assert "value_exit" in result.exit_result.confirmed_trigger_ids


def test_unknown_does_not_cancel_confirmed_exit(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(
            exit_input=_exit(
                triggers=_evidence_triggers(
                    confirmed=EvidenceExitKind.OBLIGATION_CANCELLED,
                    unknown=EvidenceExitKind.ACCEPTANCE_FAILED,
                )
            )
        ),
        _approved_rules(repository_root),
    )
    assert result.exit_result.disposition is ExitDisposition.EXIT_CANDIDATE


def test_unknown_without_confirmed_exit_abstains(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(
            exit_input=_exit(
                triggers=_evidence_triggers(unknown=EvidenceExitKind.ACCEPTANCE_FAILED)
            )
        ),
        _approved_rules(repository_root),
    )
    assert result.exit_result.disposition is None


@pytest.mark.parametrize("reserved_or_duplicate", ["risk_budget_exit", "duplicate"])
def test_exit_trigger_identity_collision_blocks(
    repository_root: Path,
    reserved_or_duplicate: str,
) -> None:
    triggers = list(_evidence_triggers())
    trigger_id = (
        "risk_budget_exit"
        if reserved_or_duplicate == "risk_budget_exit"
        else triggers[0].trigger_id
    )
    triggers[1] = replace(triggers[1], trigger_id=trigger_id)
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(triggers=tuple(triggers))), _approved_rules(repository_root)
    )
    assert result.exit_result.evaluation_state.value == "blocked"
    assert result.exit_result.reason_codes == ("EXIT_EVIDENCE_TRIGGER_ID_OR_KIND_DUPLICATED",)


def test_new_e5_e6_evidence_requires_reunderwriting(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(new_evidence=True)), _approved_rules(repository_root)
    )
    assert result.exit_result.disposition is ExitDisposition.REUNDERWRITE_REQUIRED


def test_real_price_or_cross_repository_input_blocks(repository_root: Path) -> None:
    rules = _approved_rules(repository_root)
    real_price = evaluate_stage4_expectation_valuation_exit(
        _case(price=_price(synthetic=False)), rules
    )
    cross_repository = evaluate_stage4_expectation_valuation_exit(_case(reads_kb=True), rules)
    assert real_price.gate_result.gate_4.outcome is GateOutcome.BLOCKED
    assert cross_repository.gate_result.gate_3.outcome is GateOutcome.BLOCKED
    assert cross_repository.exit_result.disposition is None


def test_exit_snapshot_failure_does_not_rewrite_gate_result(repository_root: Path) -> None:
    invalid_holding = _holding(valuation_hash=_hash("f"))
    result = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(holding=invalid_holding)), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_4.outcome is GateOutcome.PASS
    assert result.exit_result.disposition is None
    assert result.exit_result.evaluation_state.value == "blocked"


def test_upstream_nonpass_short_circuits_4a4_gates(repository_root: Path) -> None:
    result = evaluate_stage4_expectation_valuation_exit(
        _case(upstream=_upstream(gate2=GateOutcome.REJECT)), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_3.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED
    assert result.gate_result.gate_4.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED


def test_same_case_rules_and_clock_produce_same_replay_hash(repository_root: Path) -> None:
    rules = _approved_rules(repository_root)
    case = _case()
    first = evaluate_stage4_expectation_valuation_exit(case, rules)
    second = evaluate_stage4_expectation_valuation_exit(case, rules)
    assert first == second
    assert first.replay_hash == second.replay_hash


def test_evidence_trigger_input_order_does_not_change_replay_hash(repository_root: Path) -> None:
    rules = _approved_rules(repository_root)
    triggers = _evidence_triggers()
    forward = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(triggers=triggers)), rules
    )
    reverse = evaluate_stage4_expectation_valuation_exit(
        _case(exit_input=_exit(triggers=tuple(reversed(triggers)))), rules
    )
    assert forward == reverse


def test_artifact_hash_tampering_blocks_before_business_rules(repository_root: Path) -> None:
    expectation = replace(
        _expectation(),
        coverage_complete=False,
    )
    result = evaluate_stage4_expectation_valuation_exit(
        _case(expectation=expectation), _approved_rules(repository_root)
    )
    assert result.gate_result.gate_3.reason_codes == ("STAGE4_4A4_ARTIFACT_HASH_MISMATCH",)
