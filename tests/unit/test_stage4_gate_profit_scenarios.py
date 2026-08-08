from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system import RuleApprovalRecord, RuleApprovalRegistry, RuleApprovalScope
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import EventState, GateOutcome, HashDigest, PositionState
from invest_system.strategies.industrial_event.stage4_context_industry import (
    BeneficiaryTier,
    ContextDisposition,
    Stage4ContextIndustryResult,
    Stage4RuleAssessment,
    Stage4RuleEvaluationState,
)
from invest_system.strategies.industrial_event.stage4_event_semantics import (
    AssumptionKnowledge,
    AuditKnowledgeGraph,
    E4PublicAssessment,
    EconomicQuantification,
    EventStateAssessment,
    FactKnowledge,
    PartyEventAssessment,
    Stage4EventResult,
    Stage4EventRuleAssessment,
)
from invest_system.strategies.industrial_event.stage4_gate_profit_scenarios import (
    STAGE4_4A1_RULE_BUNDLE_SHA256,
    STAGE4_4A2_RULE_BUNDLE_SHA256,
    STAGE4_4A3_RULE_APPROVAL_ID,
    STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A3_RULE_BUNDLE_SHA256,
    STAGE4_4A3_RULES_SHA256,
    ApprovedStage4GateRules,
    CounterfactualProfitBridge,
    DecimalInterval,
    DriverDirection,
    EconomicInputState,
    ProbabilityCalibration,
    ProfitComponent,
    ProfitComponentName,
    ProfitTrack,
    Scenario,
    ScenarioDriver,
    ScenarioDriverName,
    ScenarioFinancials,
    ScenarioKind,
    ScenarioMigrationReplay,
    ScenarioSet,
    Stage4GateCase,
    Stage4GateCompatibilityError,
    bind_counterfactual_bridge_hashes,
    bind_scenario_set_content_hash,
    evaluate_stage4_gates,
)

MACHINE_DIR = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
RULE_BUNDLE_PATH = MACHINE_DIR / (
    "industrial_event_stage4_4a3_gate_profit_scenarios_v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = MACHINE_DIR / (
    "industrial_event_stage4_4a3_gate_profit_scenarios_v0.1.0.approval.json"
)
APPROVAL_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A3四道门利润分母与情景批准记录_v0.1.md"
)
DRAFT_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A3四道门利润分母与情景规则包_v0.1.md"
)

AS_OF = datetime(2025, 1, 5, tzinfo=UTC)
E4_AT = datetime(2025, 1, 10, tzinfo=UTC)
CUTOFF = datetime(2025, 1, 12, tzinfo=UTC)
CASE_ID = "stage4_gate_case_001"
FACT_ID = "fact_gate_economic_001"
ASSUMPTION_ID = "assumption_gate_base_001"


def _hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _context_assessment(
    rule_id: str, outcome: GateOutcome = GateOutcome.PASS
) -> Stage4RuleAssessment:
    return Stage4RuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(f"{rule_id.lower().replace('-', '_')}_test",),
        supporting_fact_ids=(FACT_ID,),
        conflicting_fact_ids=(),
    )


def _context_result(
    *,
    beneficiary: GateOutcome = GateOutcome.PASS,
    tier: BeneficiaryTier = BeneficiaryTier.PROFIT_BENEFICIARY,
    eligible: bool = True,
    bundle_hash: str = STAGE4_4A1_RULE_BUNDLE_SHA256,
) -> Stage4ContextIndustryResult:
    return Stage4ContextIndustryResult(
        case_id=CASE_ID,
        context_admission=_context_assessment("FR-CTX-001"),
        historical_context=_context_assessment("FR-CTX-002"),
        bottleneck_assessment=_context_assessment("FR-IND-001"),
        beneficiary_assessment=_context_assessment("FR-IND-002", beneficiary),
        context_disposition=ContextDisposition.DECISION_POOL,
        bottleneck_qualified=True,
        beneficiary_tier=tier,
        four_gate_eligible=eligible,
        rule_bundle_hash=HashDigest(algorithm="sha256", value=bundle_hash),
        rule_approval_id="approved_4a1",
        rule_approval_record_hash=_hash("a"),
    )


def _event_assessment(
    rule_id: str, outcome: GateOutcome = GateOutcome.PASS
) -> Stage4EventRuleAssessment:
    return Stage4EventRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(f"{rule_id.lower().replace('-', '_')}_test",),
        supporting_fact_ids=(FACT_ID,),
        conflicting_fact_ids=(),
    )


def _event_result(
    *,
    e4: GateOutcome = GateOutcome.PASS,
    state_outcome: GateOutcome = GateOutcome.PASS,
    state: EventState = EventState.E4,
    evidence_ready: bool = True,
    bundle_hash: str = STAGE4_4A2_RULE_BUNDLE_SHA256,
) -> Stage4EventResult:
    attained = (EventState.E0, EventState.E1, EventState.E2, EventState.E3, state)
    return Stage4EventResult(
        case_id=CASE_ID,
        audit_layers=_event_assessment("FR-EVT-004"),
        party_and_pit=PartyEventAssessment(
            assessment=_event_assessment("FR-EVT-002"),
            earliest_legal_public_fact_id=FACT_ID,
            cross_party_corroboration_ready=True,
        ),
        e4_public=E4PublicAssessment(
            assessment=_event_assessment("FR-EVT-003", e4),
            independent_gate_evidence_ready=evidence_ready,
            economic_quantification=EconomicQuantification.KNOWN,
            future_profit_gate_must_abstain=False,
        ),
        event_state=EventStateAssessment(
            assessment=_event_assessment("FR-EVT-001", state_outcome),
            attained_states=attained,
            highest_nonterminal_state=state,
            candidate_highest_nonterminal_state=state,
            terminal_type=None,
            revision_created=False,
            duplicate_observation=False,
            last_confirmed_state=state,
        ),
        overall_outcome=GateOutcome.PASS,
        rule_bundle_hash=HashDigest(algorithm="sha256", value=bundle_hash),
        rule_approval_id="approved_4a2",
        rule_approval_record_hash=_hash("b"),
    )


def _graph(*, fact_available_at: datetime = AS_OF) -> AuditKnowledgeGraph:
    fact = FactKnowledge(
        provider_fact_id=FACT_ID,
        subject="synthetic company",
        predicate="synthetic economic input",
        value_ref="value_001",
        available_at=fact_available_at,
        evidence_ids=("evidence_001",),
        input_ref="synthetic_gate_input",
        lineage_group_id="lineage_001",
    )
    assumption = AssumptionKnowledge(
        assumption_id=ASSUMPTION_ID,
        as_of=AS_OF,
        scenario_id="scenario_base",
        rationale="Falsifiable synthetic scenario assumption",
        dependency_ids=(FACT_ID,),
        observable_falsification_conditions=("condition_001",),
        created_by="strategy_research",
        version="0.1.0",
        input_ref="synthetic_gate_input",
    )
    return AuditKnowledgeGraph(facts=(fact,), assumptions=(assumption,))


def _component(name: ProfitComponentName, value: str) -> ProfitComponent:
    return ProfitComponent(
        name=name,
        state=EconomicInputState.KNOWN,
        point=value,
        interval=DecimalInterval(value, value),
        fact_ids=(FACT_ID,),
    )


def _bridge(*, revenue: str = "200", declared: str = "100") -> CounterfactualProfitBridge:
    values = {
        ProfitComponentName.RECURRING_OPERATING_REVENUE: revenue,
        ProfitComponentName.RECURRING_OPERATING_COST: "50",
        ProfitComponentName.RECURRING_SELLING_EXPENSE: "10",
        ProfitComponentName.RECURRING_ADMINISTRATIVE_EXPENSE: "10",
        ProfitComponentName.RECURRING_RESEARCH_EXPENSE: "5",
        ProfitComponentName.NET_FINANCE_COST: "5",
        ProfitComponentName.RECURRING_IMPAIRMENT_AND_CREDIT_LOSSES: "0",
        ProfitComponentName.RECURRING_OTHER_OPERATING_INCOME: "0",
        ProfitComponentName.RECURRING_INVESTMENT_AND_ASSOCIATE_INCOME: "0",
        ProfitComponentName.NORMALIZED_INCOME_TAX: "15",
        ProfitComponentName.MINORITY_INTEREST_DEDUCTION: "5",
    }
    return bind_counterfactual_bridge_hashes(
        CounterfactualProfitBridge(
            bridge_id="counterfactual_bridge_001",
            bridge_version="0.1.0",
            components=tuple(_component(name, values[name]) for name in ProfitComponentName),
            declared_profit=declared,
            declared_interval=DecimalInterval(declared, declared),
            calculation_input_hash=_hash("c"),
            result_hash=_hash("d"),
        )
    )


def _driver(
    name: ScenarioDriverName,
    *,
    direction: DriverDirection,
    value: str = "1",
    trigger: str | None = None,
    unbound: bool = False,
) -> ScenarioDriver:
    return ScenarioDriver(
        name=name,
        state=EconomicInputState.KNOWN,
        value=value,
        unit="synthetic_unit",
        supported_interval="synthetic supported interval",
        as_of=AS_OF,
        fact_ids=(FACT_ID,),
        direction=direction,
        change_reason=(
            "supported change"
            if direction in {DriverDirection.BETTER, DriverDirection.WORSE}
            else None
        ),
        trigger=trigger or "observable driver trigger",
        falsifier="observable falsifier",
        unbound_growth_assumption=unbound,
    )


def _drivers(kind: ScenarioKind) -> tuple[ScenarioDriver, ...]:
    result = [
        _driver(
            name,
            direction=DriverDirection.BASE
            if kind is ScenarioKind.BASE
            else DriverDirection.INHERITED,
        )
        for name in ScenarioDriverName
    ]
    if kind is ScenarioKind.DOWNSIDE:
        result[0] = _driver(result[0].name, direction=DriverDirection.WORSE, value="0.8")
    elif kind is ScenarioKind.UPSIDE:
        result[0] = _driver(
            result[0].name,
            direction=DriverDirection.BETTER,
            value="1.2",
            trigger="new binding public order",
            unbound=True,
        )
    elif kind is ScenarioKind.STRESS:
        result[0] = _driver(result[0].name, direction=DriverDirection.WORSE, value="0.5")
    return tuple(result)


def _financials(kind: ScenarioKind) -> ScenarioFinancials:
    parameters = {
        ScenarioKind.BASE: ("50", "20", "10", "10", "10", "5", "5", "5"),
        ScenarioKind.DOWNSIDE: ("35", "5", "-5", "20", "5", "10", "5", "5"),
        ScenarioKind.UPSIDE: ("60", "30", "20", "5", "20", "1", "5", "5"),
        ScenarioKind.STRESS: ("20", "-10", "-20", "40", "-5", "30", "5", "5"),
    }
    revenue, profit, fcf, financing, liquidity, writeoff, working, capex = parameters[kind]
    return ScenarioFinancials(
        ntm_recognizable_revenue=revenue,
        incremental_operating_cost="20",
        incremental_operating_expense="5",
        incremental_tax_and_surcharges="2",
        incremental_financing_cost="2",
        minority_interest_deduction="1",
        incremental_non_cash_items="0",
        incremental_working_capital=working,
        incremental_capex=capex,
        declared_incremental_profit=profit,
        declared_incremental_fcf=fcf,
        peak_external_financing_need=financing,
        minimum_liquidity_headroom=liquidity,
        irreversible_writeoff=writeoff,
        fact_ids=(FACT_ID,),
        assumption_ids=(ASSUMPTION_ID,),
    )


def _scenario(kind: ScenarioKind) -> Scenario:
    return Scenario(
        kind=kind,
        drivers=_drivers(kind),
        financials=_financials(kind),
        reason_codes=(f"{kind.value}_supported_path",),
    )


def _scenario_set(
    *,
    scenarios: tuple[Scenario, ...] | None = None,
    presentation_currency: str = "CNY",
    contract_currency: str = "CNY",
) -> ScenarioSet:
    value = ScenarioSet(
        scenario_set_id="scenario_set_001",
        version="0.1.0",
        as_of=E4_AT,
        e4_first_public_at=E4_AT,
        knowledge_cutoff=CUTOFF,
        ntm_start_date="2025-01-10",
        ntm_end_date_exclusive="2026-01-10",
        presentation_currency=presentation_currency,
        contract_currency=contract_currency,
        fx_translation_date=None,
        fx_version=None,
        fx_fact_ids=(),
        fx_assumption_ids=(),
        scenarios=scenarios or tuple(_scenario(kind) for kind in ScenarioKind),
        calibration=None,
        supersedes_scenario_set_id=None,
        migration_replay=None,
        declared_content_hash=_hash("0"),
    )
    return bind_scenario_set_content_hash(value)


def _case(
    *,
    context: Stage4ContextIndustryResult | None = None,
    event: Stage4EventResult | None = None,
    graph: AuditKnowledgeGraph | None = None,
    base_bridge: CounterfactualProfitBridge | None = None,
    downside_bridge: CounterfactualProfitBridge | None = None,
    scenario_set: ScenarioSet | None = None,
) -> Stage4GateCase:
    return Stage4GateCase(
        case_id=CASE_ID,
        context_result=context or _context_result(),
        event_result=event or _event_result(),
        knowledge_graph=graph or _graph(),
        base_counterfactual_bridge=base_bridge or _bridge(),
        downside_counterfactual_bridge=downside_bridge or _bridge(revenue="180", declared="80"),
        scenario_set=scenario_set or _scenario_set(),
    )


def _approved_rules(repository_root: Path) -> ApprovedStage4GateRules:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    capability = RuleApprovalRegistry((approval,)).require(document)
    return ApprovedStage4GateRules.from_approved_bundle(document, capability)


def _rebind(value: ScenarioSet, **changes: object) -> ScenarioSet:
    return bind_scenario_set_content_hash(
        replace(value, **changes, declared_content_hash=_hash("0"))  # type: ignore[arg-type]
    )


def test_4a3_artifacts_bind_exact_owner_approval(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    assert document.bundle_hash().value == STAGE4_4A3_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE4_4A3_RULES_SHA256
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_id == STAGE4_4A3_RULE_APPROVAL_ID
    assert approval.canonical_sha256() == STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256
    source = document.rules["approved_source_binding"]
    binding = document.rules["document_binding"]
    assert isinstance(source, Mapping) and isinstance(source["hash"], Mapping)
    assert isinstance(binding, Mapping) and isinstance(binding["hash"], Mapping)
    assert (
        sha256((repository_root / DRAFT_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == source["hash"]["value"]
    )
    assert (
        sha256((repository_root / APPROVAL_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == binding["hash"]["value"]
    )


def test_approved_capability_rejects_semantic_drift(repository_root: Path) -> None:
    value = json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    document = rule_bundle_document_from_json_value(value)
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    value["rules"]["rule_modules"]["FR-GATE-002"]["profit_materiality"]["threshold"] = "0.09"
    drifted = rule_bundle_document_from_json_value(value)
    with pytest.raises(ValueError, match="RULE_BUNDLE_HASH_NOT_APPROVED"):
        RuleApprovalRegistry((approval,)).require(drifted)
    assert document.bundle_hash().value == approval.bundle_hash.value


def test_approved_capability_rejects_wrong_scope(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = RuleApprovalRecord(
        approval_id=STAGE4_4A3_RULE_APPROVAL_ID,
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 8, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="synthetic_wrong_scope_test",
    )
    capability = RuleApprovalRegistry((approval,)).require(document)
    with pytest.raises(Stage4GateCompatibilityError) as exc_info:
        ApprovedStage4GateRules.from_approved_bundle(document, capability)
    assert exc_info.value.code == "STAGE4_4A3_RULE_SCOPE_UNSUPPORTED"


def test_fr_gate_001_and_002_pass_exact_boundary(repository_root: Path) -> None:
    value = _scenario_set()
    base = next(item for item in value.scenarios if item.kind is ScenarioKind.BASE)
    base = replace(
        base,
        financials=replace(
            base.financials,
            ntm_recognizable_revenue="40",
            incremental_working_capital="2",
            incremental_capex="3",
            declared_incremental_profit="10",
            declared_incremental_fcf="5",
        ),
    )
    scenarios = tuple(base if item.kind is ScenarioKind.BASE else item for item in value.scenarios)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.gate_1.outcome is GateOutcome.PASS
    assert result.scenario_validation.outcome is GateOutcome.PASS
    assert result.gate_2.outcome is GateOutcome.PASS
    assert result.base_profit_materiality == "0.1"
    assert result.gate2_research_qualified is True


def test_partial_completion_keeps_future_gates_and_trading_closed(repository_root: Path) -> None:
    result = evaluate_stage4_gates(_case(), _approved_rules(repository_root))
    assert result.gate_3.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED
    assert result.gate_4.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED
    assert result.remaining_gate_ids == ("FR-GATE-004", "FR-GATE-005")
    assert result.full_stage4_decision is None
    assert result.position_state is PositionState.FLAT
    assert result.target_weight is None and result.order_intent is None
    assert not any(
        (
            result.authorizes_backtest,
            result.authorizes_paper,
            result.authorizes_shadow,
            result.authorizes_live,
            result.authorizes_positions,
            result.authorizes_orders,
        )
    )


def test_gate1_reject_short_circuits_later_rules(repository_root: Path) -> None:
    context = _context_result(
        beneficiary=GateOutcome.REJECT, tier=BeneficiaryTier.NONE, eligible=False
    )
    result = evaluate_stage4_gates(_case(context=context), _approved_rules(repository_root))
    assert result.gate_1.outcome is GateOutcome.REJECT
    assert result.scenario_validation.outcome is None
    assert result.gate_2.outcome is None
    assert result.overall_outcome is GateOutcome.REJECT


def test_gate1_e3_5_is_research_label_not_shadow_authority(repository_root: Path) -> None:
    event = _event_result(state_outcome=GateOutcome.ABSTAIN, state=EventState.E3_5)
    result = evaluate_stage4_gates(_case(event=event), _approved_rules(repository_root))
    assert result.gate_1.outcome is GateOutcome.SHADOW_ONLY
    assert result.authorizes_shadow is False


def test_gate1_upstream_hash_mismatch_blocks(repository_root: Path) -> None:
    result = evaluate_stage4_gates(
        _case(context=_context_result(bundle_hash="f" * 64)), _approved_rules(repository_root)
    )
    assert result.gate_1.outcome is GateOutcome.BLOCKED


def test_gate1_unknown_upstream_evidence_abstains(repository_root: Path) -> None:
    event = _event_result(evidence_ready=False)
    result = evaluate_stage4_gates(_case(event=event), _approved_rules(repository_root))
    assert result.gate_1.outcome is GateOutcome.ABSTAIN
    assert result.gate_2.outcome is None


def test_missing_foreign_exchange_material_abstains(repository_root: Path) -> None:
    scenario_set = _scenario_set(contract_currency="USD")
    result = evaluate_stage4_gates(
        _case(scenario_set=scenario_set), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.ABSTAIN
    assert result.gate_2.outcome is None


def test_future_fact_reference_blocks(repository_root: Path) -> None:
    graph = _graph(fact_available_at=E4_AT + timedelta(seconds=1))
    result = evaluate_stage4_gates(_case(graph=graph), _approved_rules(repository_root))
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_scenario_hash_drift_blocks(repository_root: Path) -> None:
    scenario_set = replace(_scenario_set(), version="0.1.1")
    result = evaluate_stage4_gates(
        _case(scenario_set=scenario_set), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED
    assert result.scenario_validation.reason_codes == ("SCENARIO_CONTENT_HASH_MISMATCH",)


def test_driver_metadata_missing_abstains(repository_root: Path) -> None:
    value = _scenario_set()
    base = next(item for item in value.scenarios if item.kind is ScenarioKind.BASE)
    base = replace(
        base,
        drivers=(replace(base.drivers[0], supported_interval=None), *base.drivers[1:]),
    )
    scenarios = tuple(base if item.kind is ScenarioKind.BASE else item for item in value.scenarios)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.ABSTAIN


def test_migration_replay_hash_mismatch_blocks(repository_root: Path) -> None:
    value = _scenario_set()
    migration = ScenarioMigrationReplay(
        previous_content_hash=_hash("1"),
        fixed_input_hash=_hash("2"),
        replay_result_hash=_hash("3"),
        expected_replay_result_hash=_hash("4"),
        replayable=True,
    )
    scenario_set = _rebind(
        value,
        version="0.2.0",
        supersedes_scenario_set_id="scenario_set_000",
        migration_replay=migration,
    )
    result = evaluate_stage4_gates(
        _case(scenario_set=scenario_set), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_missing_required_scenario_abstains(repository_root: Path) -> None:
    value = _scenario_set()
    scenario_set = _rebind(value, scenarios=value.scenarios[:-1])
    result = evaluate_stage4_gates(
        _case(scenario_set=scenario_set), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.ABSTAIN


def test_inherited_driver_value_drift_blocks(repository_root: Path) -> None:
    value = _scenario_set()
    downside = next(item for item in value.scenarios if item.kind is ScenarioKind.DOWNSIDE)
    inherited = downside.drivers[1]
    changed = replace(inherited, value="2")
    downside = replace(downside, drivers=(downside.drivers[0], changed, *downside.drivers[2:]))
    scenarios = tuple(
        downside if item.kind is ScenarioKind.DOWNSIDE else item for item in value.scenarios
    )
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_unbound_growth_outside_upside_blocks(repository_root: Path) -> None:
    value = _scenario_set()
    base = next(item for item in value.scenarios if item.kind is ScenarioKind.BASE)
    base = replace(
        base, drivers=(replace(base.drivers[0], unbound_growth_assumption=True), *base.drivers[1:])
    )
    scenarios = tuple(base if item.kind is ScenarioKind.BASE else item for item in value.scenarios)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_probability_sum_must_be_exact(repository_root: Path) -> None:
    value = _scenario_set()
    probabilities = {
        ScenarioKind.BASE: "0.5",
        ScenarioKind.DOWNSIDE: "0.3",
        ScenarioKind.UPSIDE: "0.3",
    }
    scenarios = tuple(
        replace(item, probability=probabilities.get(item.kind)) for item in value.scenarios
    )
    calibration = ProbabilityCalibration("sample_001", "method_001", "0.1.0", AS_OF)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios, calibration=calibration)),
        _approved_rules(repository_root),
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_probability_must_be_in_unit_interval(repository_root: Path) -> None:
    value = _scenario_set()
    probabilities = {
        ScenarioKind.BASE: "1.100000",
        ScenarioKind.DOWNSIDE: "-0.100000",
        ScenarioKind.UPSIDE: "0.000000",
    }
    scenarios = tuple(
        replace(item, probability=probabilities.get(item.kind)) for item in value.scenarios
    )
    calibration = ProbabilityCalibration("sample_001", "method_001", "0.1.0", AS_OF)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios, calibration=calibration)),
        _approved_rules(repository_root),
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_optional_probabilities_accept_exact_calibrated_sum(repository_root: Path) -> None:
    value = _scenario_set()
    probabilities = {
        ScenarioKind.BASE: "0.500000",
        ScenarioKind.DOWNSIDE: "0.300000",
        ScenarioKind.UPSIDE: "0.200000",
    }
    scenarios = tuple(
        replace(item, probability=probabilities.get(item.kind)) for item in value.scenarios
    )
    calibration = ProbabilityCalibration("sample_001", "method_001", "0.1.0", AS_OF)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios, calibration=calibration)),
        _approved_rules(repository_root),
    )
    assert result.scenario_validation.outcome is GateOutcome.PASS
    assert result.gate_2.outcome is GateOutcome.PASS


def test_counterfactual_double_counting_blocks(repository_root: Path) -> None:
    bridge = bind_counterfactual_bridge_hashes(replace(_bridge(), double_counting=True))
    result = evaluate_stage4_gates(_case(base_bridge=bridge), _approved_rules(repository_root))
    assert result.gate_2.outcome is GateOutcome.BLOCKED


def test_counterfactual_calculation_hash_drift_blocks(repository_root: Path) -> None:
    bridge = replace(_bridge(), calculation_input_hash=_hash("9"))
    result = evaluate_stage4_gates(_case(base_bridge=bridge), _approved_rules(repository_root))
    assert result.gate_2.outcome is GateOutcome.BLOCKED


def test_unknown_counterfactual_component_abstains(repository_root: Path) -> None:
    bridge = _bridge()
    component = replace(
        bridge.components[0], state=EconomicInputState.UNKNOWN, point=None, interval=None
    )
    bridge = bind_counterfactual_bridge_hashes(
        replace(bridge, components=(component, *bridge.components[1:]))
    )
    result = evaluate_stage4_gates(_case(base_bridge=bridge), _approved_rules(repository_root))
    assert result.gate_2.outcome is GateOutcome.ABSTAIN


def test_fragile_profit_track_never_computes_ratio(repository_root: Path) -> None:
    bridge = _bridge(revenue="100", declared="0")
    result = evaluate_stage4_gates(_case(base_bridge=bridge), _approved_rules(repository_root))
    assert result.profit_track is ProfitTrack.FRAGILE_SHADOW
    assert result.gate_2.outcome is GateOutcome.SHADOW_ONLY
    assert result.base_profit_materiality is None


def test_materiality_below_threshold_rejects(repository_root: Path) -> None:
    base = _scenario(ScenarioKind.BASE)
    base = replace(
        base,
        financials=replace(
            base.financials,
            ntm_recognizable_revenue="39",
            declared_incremental_profit="9",
            declared_incremental_fcf="-1",
        ),
    )
    value = _scenario_set()
    scenarios = tuple(base if item.kind is ScenarioKind.BASE else item for item in value.scenarios)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.gate_2.outcome is GateOutcome.REJECT
    assert result.base_profit_materiality == "0.09"


def test_material_profit_with_nonpositive_cash_is_shadow_only(repository_root: Path) -> None:
    base = _scenario(ScenarioKind.BASE)
    base = replace(
        base,
        financials=replace(
            base.financials, incremental_working_capital="15", declared_incremental_fcf="0"
        ),
    )
    value = _scenario_set()
    scenarios = tuple(base if item.kind is ScenarioKind.BASE else item for item in value.scenarios)
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.gate_2.outcome is GateOutcome.SHADOW_ONLY
    assert result.authorizes_shadow is False


def test_invalid_profit_ordering_blocks(repository_root: Path) -> None:
    upside = _scenario(ScenarioKind.UPSIDE)
    upside = replace(
        upside,
        financials=replace(
            upside.financials,
            ntm_recognizable_revenue="45",
            declared_incremental_profit="15",
            declared_incremental_fcf="5",
        ),
    )
    value = _scenario_set()
    scenarios = tuple(
        upside if item.kind is ScenarioKind.UPSIDE else item for item in value.scenarios
    )
    result = evaluate_stage4_gates(
        _case(scenario_set=_rebind(value, scenarios=scenarios)), _approved_rules(repository_root)
    )
    assert result.scenario_validation.outcome is GateOutcome.BLOCKED


def test_runtime_type_cannot_be_forged() -> None:
    with pytest.raises(Stage4GateCompatibilityError, match="STAGE4_4A3_RULE_ISSUER_INVALID"):
        ApprovedStage4GateRules(
            _issuer=object(),
            bundle_hash=_hash("1"),
            approval_record_hash=_hash("2"),
            approval_id=STAGE4_4A3_RULE_APPROVAL_ID,
            materiality_threshold=Decimal("0.10"),
        )
