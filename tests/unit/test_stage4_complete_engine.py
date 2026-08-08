from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, replace
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import DecisionState, GateOutcome, PositionState, RunMode
from invest_system.strategies.industrial_event import (
    STAGE4_4A3_RULES_SHA256,
    STAGE4_4A4_RULES_SHA256,
    STAGE4_COMPLETE_INVENTORY_SHA256,
    STAGE4_COMPLETE_RULE_APPROVAL_ID,
    STAGE4_COMPLETE_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_COMPLETE_RULE_BUNDLE_ID,
    STAGE4_COMPLETE_RULE_BUNDLE_SHA256,
    STAGE4_COMPLETE_RULE_BUNDLE_VERSION,
    STAGE4_COMPLETE_RULES_SHA256,
    ApprovedStage4CompleteCapabilities,
    ApprovedStage4CompleteRules,
    AuditKnowledgeGraph,
    CompleteStage4EvaluationState,
    DecimalInterval,
    EvidenceConclusion,
    ExitDisposition,
    HoldingKind,
    ScenarioKind,
    Stage4CompleteSyntheticCase,
    Stage4ExitInput,
    bind_expectation_snapshot,
    bind_pre_e4_market_context,
    bind_proof_plan,
    bind_stage4_valuation_set,
    bind_synthetic_holding_snapshot,
    bind_synthetic_price_assumption,
    complete_stage4_replay_sha256,
    evaluate_complete_stage4,
    require_stage4_rule_capability,
    stage4_rule_inventory_from_json_value,
)
from unit import test_stage4_context_industry as context_support
from unit import test_stage4_event_semantics as event_support
from unit import test_stage4_expectation_valuation_exit as expectation_support
from unit import test_stage4_gate_profit_scenarios as gate_support

CASE_ID = expectation_support.CASE_ID
COMPANY_ID = "company_001"
INDUSTRY_NODE_ID = "industry_node_001"
LOGICAL_EVENT_ID = "logical_event_001"


def _machine_artifact(repository_root: Path, filename: str) -> Path:
    matches = tuple(repository_root.rglob(filename))
    assert len(matches) == 1
    return matches[0]


def _capabilities(repository_root: Path) -> ApprovedStage4CompleteCapabilities:
    inventory_path = _machine_artifact(
        repository_root,
        "industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json",
    )
    complete_bundle_path = _machine_artifact(
        repository_root,
        "industrial_event_stage4_4b_complete_engine_integration_v0.1.0.rule-bundle.json",
    )
    complete_approval_path = _machine_artifact(
        repository_root,
        "industrial_event_stage4_4b_complete_engine_integration_v0.1.0.approval.json",
    )
    inventory = stage4_rule_inventory_from_json_value(
        json.loads(inventory_path.read_text(encoding="utf-8"))
    )
    document = rule_bundle_document_from_json_value(
        json.loads(complete_bundle_path.read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads(complete_approval_path.read_text(encoding="utf-8"))
    )
    capability = require_stage4_rule_capability(
        document,
        inventory,
        registry=RuleApprovalRegistry((approval,)),
    )
    complete = ApprovedStage4CompleteRules.from_approved_bundle(
        document,
        capability,
        inventory,
    )
    return ApprovedStage4CompleteCapabilities.compose(
        complete=complete,
        context_industry=context_support._approved_rules(repository_root),
        event=event_support._approved_rules(repository_root),
        gate_profit_scenarios=gate_support._approved_rules(repository_root),
        expectation_valuation_exit=expectation_support._approved_rules(repository_root),
    )


def _event_graph_for_complete_case() -> AuditKnowledgeGraph:
    input_ref = context_support._context().input_id
    event_graph = event_support._knowledge_graph()
    gate_graph = gate_support._graph()
    return replace(
        event_graph,
        facts=tuple(replace(item, input_ref=input_ref) for item in event_graph.facts)
        + tuple(replace(item, input_ref=input_ref) for item in gate_graph.facts),
        assumptions=tuple(replace(item, input_ref=input_ref) for item in event_graph.assumptions)
        + tuple(replace(item, input_ref=input_ref) for item in gate_graph.assumptions),
        derived=tuple(replace(item, input_ref=input_ref) for item in event_graph.derived),
        judgments=tuple(replace(item, input_ref=input_ref) for item in event_graph.judgments),
    )


def _case(**overrides: object) -> Stage4CompleteSyntheticCase:
    context_case = replace(context_support._case(), case_id=CASE_ID)
    context = context_case.context
    parties = tuple(
        replace(item, legal_entity_id=COMPANY_ID) if item.role.value == "listed_company" else item
        for item in event_support._party_links()
    )
    event_case = replace(
        event_support._case(graph=_event_graph_for_complete_case(), parties=parties),
        case_id=CASE_ID,
        input_ref=context.input_id,
        knowledge_cutoff=context.knowledge_cutoff,
        decision_at=context.decision_at,
    )
    basis = replace(
        expectation_support._basis(),
        event_identity=LOGICAL_EVENT_ID,
        subject_scope=COMPANY_ID,
    )
    expectation_value = expectation_support._expectation()
    expectation = bind_expectation_snapshot(
        replace(
            expectation_value,
            identity=replace(
                expectation_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
            basis=basis,
        )
    )
    market_value = expectation_support._market()
    market = bind_pre_e4_market_context(
        replace(
            market_value,
            identity=replace(
                market_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
        )
    )
    valuation_value = expectation_support._valuation()
    valuation = bind_stage4_valuation_set(
        replace(
            valuation_value,
            identity=replace(
                valuation_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
            basis=basis,
        )
    )
    price_value = expectation_support._price()
    price = bind_synthetic_price_assumption(
        replace(
            price_value,
            identity=replace(
                price_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
        )
    )
    proof_value = expectation_support._proof()
    proof = bind_proof_plan(
        replace(
            proof_value,
            identity=replace(
                proof_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
        )
    )
    holding_value = expectation_support._holding(
        valuation_hash=valuation.identity.declared_content_hash
    )
    holding = bind_synthetic_holding_snapshot(
        replace(
            holding_value,
            identity=replace(
                holding_value.identity,
                knowledge_cutoff=context.knowledge_cutoff,
            ),
        )
    )
    exit_input = expectation_support._exit(holding=holding)
    values: dict[str, object] = {
        "case_id": CASE_ID,
        "company_id": COMPANY_ID,
        "industry_node_id": INDUSTRY_NODE_ID,
        "logical_event_id": LOGICAL_EVENT_ID,
        "knowledge_cutoff": context.knowledge_cutoff,
        "e4_first_public_at": event_support.AS_OF,
        "context_case": context_case,
        "event_case": event_case,
        "base_counterfactual_bridge": gate_support._bridge(),
        "downside_counterfactual_bridge": gate_support._bridge(revenue="180", declared="80"),
        "scenario_set": gate_support._rebind(
            gate_support._scenario_set(),
            knowledge_cutoff=context.knowledge_cutoff,
        ),
        "e4_basis": basis,
        "e4_binding_obligation_interval": DecimalInterval("100", "120"),
        "e4_incremental_profit_interval": DecimalInterval("20", "25"),
        "e4_incremental_fcf_interval": DecimalInterval("10", "15"),
        "expectation_snapshot": expectation,
        "pre_e4_market_context": market,
        "valuation_set": valuation,
        "price_assumption": price,
        "proof_plan": proof,
        "exit_input": exit_input,
    }
    values.update(overrides)
    return Stage4CompleteSyntheticCase(**values)  # type: ignore[arg-type]


def test_4b_artifacts_bind_exact_owner_approval_and_inventory(repository_root: Path) -> None:
    bundle_path = _machine_artifact(
        repository_root,
        "industrial_event_stage4_4b_complete_engine_integration_v0.1.0.rule-bundle.json",
    )
    approval_path = _machine_artifact(
        repository_root,
        "industrial_event_stage4_4b_complete_engine_integration_v0.1.0.approval.json",
    )
    document = rule_bundle_document_from_json_value(
        json.loads(bundle_path.read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads(approval_path.read_text(encoding="utf-8"))
    )

    assert document.bundle_hash().value == STAGE4_COMPLETE_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE4_COMPLETE_RULES_SHA256
    assert approval.approval_id == STAGE4_COMPLETE_RULE_APPROVAL_ID
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.canonical_sha256() == STAGE4_COMPLETE_RULE_APPROVAL_RECORD_SHA256
    inventory_binding = document.rules["stage4_rule_inventory"]
    assert isinstance(inventory_binding, Mapping)
    inventory_hash = inventory_binding["inventory_hash"]
    assert isinstance(inventory_hash, Mapping)
    assert inventory_hash["value"] == STAGE4_COMPLETE_INVENTORY_SHA256
    source_binding = document.rules["approval_source_binding"]
    approval_binding = document.rules["document_binding"]
    integration = document.rules["complete_engine_integration"]
    assert isinstance(source_binding, Mapping)
    assert isinstance(approval_binding, Mapping)
    assert isinstance(integration, Mapping)
    specification_path = source_binding["specification_path"]
    draft_path = source_binding["draft_proposal_path"]
    approval_document_path = approval_binding["path"]
    assert isinstance(specification_path, str)
    assert isinstance(draft_path, str)
    assert isinstance(approval_document_path, str)
    specification_hash = source_binding["specification_hash"]
    approval_document_hash = approval_binding["hash"]
    assert isinstance(specification_hash, Mapping)
    assert isinstance(approval_document_hash, Mapping)
    assert (
        sha256((repository_root / specification_path).read_bytes()).hexdigest()
        == (specification_hash["value"])
    )
    assert (
        sha256((repository_root / approval_document_path).read_bytes()).hexdigest()
        == (approval_document_hash["value"])
    )
    draft_document = rule_bundle_document_from_json_value(
        json.loads((repository_root / draft_path).read_text(encoding="utf-8"))
    )
    draft_bundle_hash = source_binding["draft_bundle_hash"]
    approved_decision_ids = integration["approved_decision_ids"]
    assert isinstance(draft_bundle_hash, Mapping)
    assert isinstance(approved_decision_ids, (list, tuple))
    assert draft_document.bundle_hash().value == draft_bundle_hash["value"]
    assert tuple(approved_decision_ids) == tuple(f"4B-{index:02d}" for index in range(1, 17))


def test_complete_engine_runs_raw_inputs_through_all_four_batches(repository_root: Path) -> None:
    result = evaluate_complete_stage4(_case(), _capabilities(repository_root))

    assert result.evaluation_state is CompleteStage4EvaluationState.COMPLETED
    assert result.context_result is not None
    assert result.event_result is not None
    assert result.gate_profit_result is not None
    assert result.expectation_valuation_exit_result is not None
    assert result.overall_outcome is GateOutcome.PASS
    assert result.research_decision_label is DecisionState.TRADE_READY
    assert result.unified_gate_view.gate_1.outcome is GateOutcome.PASS
    assert result.unified_gate_view.gate_2.outcome is GateOutcome.PASS
    assert result.unified_gate_view.gate_3.outcome is GateOutcome.PASS
    assert result.unified_gate_view.gate_4.outcome is GateOutcome.PASS
    assert [item.batch_id for item in result.local_result_hashes] == [
        "4A-1",
        "4A-2",
        "4A-3",
        "4A-4",
    ]
    local_results = (
        result.context_result,
        result.event_result,
        result.gate_profit_result,
        result.expectation_valuation_exit_result,
    )
    assert [item.result_hash.value for item in result.local_result_hashes] == [
        canonical_sha256(item) for item in local_results
    ]
    assert result.unified_gate_view.gate_1.source_rule_hash.value == STAGE4_4A3_RULES_SHA256
    assert result.unified_gate_view.gate_4.source_rule_hash.value == STAGE4_4A4_RULES_SHA256
    assert result.complete_capability.batch_id == "4B"
    assert result.complete_capability.bundle_id == STAGE4_COMPLETE_RULE_BUNDLE_ID
    assert result.complete_capability.bundle_version == STAGE4_COMPLETE_RULE_BUNDLE_VERSION
    assert result.complete_capability.bundle_hash.value == STAGE4_COMPLETE_RULE_BUNDLE_SHA256
    assert result.complete_capability.rules_hash.value == STAGE4_COMPLETE_RULES_SHA256
    assert all(item.bundle_version == "0.1.0" for item in result.local_capabilities)
    assert result.replay_hash.value == complete_stage4_replay_sha256(result)


def test_complete_engine_outputs_no_real_world_or_trading_authority(repository_root: Path) -> None:
    result = evaluate_complete_stage4(_case(), _capabilities(repository_root))

    assert result.complete_stage4_synthetic_capability is True
    assert result.position_state is PositionState.FLAT
    assert result.formal_strategy_run_manifest is None
    assert result.target_weight is None
    assert result.approved_weight is None
    assert result.actual_weight is None
    assert result.approver is None
    assert result.order_intent is None
    assert result.kb_current_status_authority is False
    assert all(
        getattr(result, field_name) is False
        for field_name in (
            "authorizes_backtest",
            "authorizes_paper",
            "authorizes_shadow",
            "authorizes_live",
            "authorizes_positions",
            "authorizes_portfolio",
            "authorizes_execution",
            "authorizes_pnl",
            "authorizes_orders",
        )
    )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"run_mode": RunMode.BACKTEST}, "STAGE4_COMPLETE_SCOPE_OR_CROSS_REPOSITORY_VIOLATION"),
        (
            {"reads_kb_internal_state": True},
            "STAGE4_COMPLETE_SCOPE_OR_CROSS_REPOSITORY_VIOLATION",
        ),
        (
            {"carries_kb_current_status_authority": True},
            "STAGE4_COMPLETE_SCOPE_OR_CROSS_REPOSITORY_VIOLATION",
        ),
        ({"company_id": "company_drift"}, "STAGE4_COMPLETE_COMPANY_IDENTITY_MISMATCH"),
        (
            {"industry_node_id": "industry_node_drift"},
            "STAGE4_COMPLETE_INDUSTRY_NODE_IDENTITY_MISMATCH",
        ),
        ({"logical_event_id": "event_drift"}, "STAGE4_COMPLETE_EVENT_IDENTITY_MISMATCH"),
    ],
)
def test_complete_engine_preflight_fails_closed_before_local_evaluation(
    repository_root: Path,
    overrides: dict[str, object],
    reason: str,
) -> None:
    result = evaluate_complete_stage4(_case(**overrides), _capabilities(repository_root))

    assert result.evaluation_state is CompleteStage4EvaluationState.BLOCKED_BEFORE_EVALUATION
    assert result.overall_outcome is GateOutcome.BLOCKED
    assert result.reason_codes == (reason,)
    assert result.context_result is None
    assert result.event_result is None
    assert result.gate_profit_result is None
    assert result.expectation_valuation_exit_result is None
    assert result.local_result_hashes == ()


def test_complete_engine_blocks_cross_batch_incremental_fcf_drift(repository_root: Path) -> None:
    case = _case(e4_incremental_fcf_interval=DecimalInterval("11", "15"))
    result = evaluate_complete_stage4(case, _capabilities(repository_root))

    assert result.evaluation_state is CompleteStage4EvaluationState.BLOCKED_DURING_COMPOSITION
    assert result.overall_outcome is GateOutcome.BLOCKED
    assert result.reason_codes == ("STAGE4_COMPLETE_INCREMENTAL_FCF_BINDING_MISMATCH",)
    assert result.gate_profit_result is not None
    assert result.expectation_valuation_exit_result is None
    assert [item.batch_id for item in result.local_result_hashes] == ["4A-1", "4A-2", "4A-3"]


def test_complete_engine_preserves_exact_gate_boundaries(repository_root: Path) -> None:
    case = _case()
    base = next(item for item in case.scenario_set.scenarios if item.kind is ScenarioKind.BASE)
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
    scenario_set = gate_support._rebind(
        case.scenario_set,
        scenarios=tuple(
            base if item.kind is ScenarioKind.BASE else item for item in case.scenario_set.scenarios
        ),
    )
    result = evaluate_complete_stage4(
        replace(
            case,
            scenario_set=scenario_set,
            e4_incremental_profit_interval=DecimalInterval("10", "15"),
            e4_incremental_fcf_interval=DecimalInterval("5", "10"),
        ),
        _capabilities(repository_root),
    )

    assert result.overall_outcome is GateOutcome.PASS
    assert result.gate_profit_result is not None
    assert result.gate_profit_result.base_profit_materiality == "0.1"
    assert result.net_base_remaining_return == "0.15"
    assert result.reward_to_downside == "2"


@pytest.mark.parametrize(
    ("source_batch", "expected_outcome"),
    [("4A-1", GateOutcome.BLOCKED), ("4A-2", GateOutcome.REJECT)],
)
def test_complete_engine_propagates_upstream_failure_and_short_circuits_later_gates(
    repository_root: Path,
    source_batch: str,
    expected_outcome: GateOutcome,
) -> None:
    case = _case()
    if source_batch == "4A-1":
        context_case = replace(
            case.context_case,
            beneficiary=context_support._beneficiary(technical=EvidenceConclusion.REFUTED),
        )
        case = replace(case, context_case=context_case)
    else:
        event_case = replace(
            case.event_case,
            e4_public=event_support._e4(binding=EvidenceConclusion.REFUTED),
        )
        case = replace(case, event_case=event_case)

    result = evaluate_complete_stage4(case, _capabilities(repository_root))

    assert result.evaluation_state is CompleteStage4EvaluationState.COMPLETED
    assert result.overall_outcome is expected_outcome
    assert result.unified_gate_view.gate_1.outcome is expected_outcome
    assert result.unified_gate_view.gate_2.outcome is None
    assert result.unified_gate_view.gate_3.outcome is None
    assert result.unified_gate_view.gate_4.outcome is None


def test_complete_engine_propagates_gate2_gate3_gate4_and_abstain_outcomes(
    repository_root: Path,
) -> None:
    capabilities = _capabilities(repository_root)
    base_case = _case()
    gate2_reject = evaluate_complete_stage4(
        replace(
            base_case,
            base_counterfactual_bridge=gate_support._bridge(
                revenue="400",
                declared="300",
            ),
        ),
        capabilities,
    )
    fully_reflected_market = bind_pre_e4_market_context(
        replace(base_case.pre_e4_market_context, price="10")
    )
    gate3_reject = evaluate_complete_stage4(
        replace(base_case, pre_e4_market_context=fully_reflected_market),
        capabilities,
    )
    long_proof = bind_proof_plan(
        replace(base_case.proof_plan, verification_within_trading_days=121)
    )
    gate4_reject = evaluate_complete_stage4(
        replace(base_case, proof_plan=long_proof),
        capabilities,
    )
    touching_market = bind_pre_e4_market_context(
        replace(base_case.pre_e4_market_context, price="8.5")
    )
    abstain = evaluate_complete_stage4(
        replace(base_case, pre_e4_market_context=touching_market),
        capabilities,
    )

    assert gate2_reject.overall_outcome is GateOutcome.REJECT
    assert gate2_reject.unified_gate_view.gate_2.outcome is GateOutcome.REJECT
    assert gate3_reject.overall_outcome is GateOutcome.REJECT
    assert gate3_reject.unified_gate_view.gate_3.outcome is GateOutcome.REJECT
    assert gate4_reject.overall_outcome is GateOutcome.REJECT
    assert gate4_reject.unified_gate_view.gate_4.outcome is GateOutcome.REJECT
    assert abstain.overall_outcome is GateOutcome.ABSTAIN
    assert abstain.unified_gate_view.gate_3.outcome is GateOutcome.ABSTAIN


def test_complete_engine_keeps_fragile_profit_label_without_shadow_authority(
    repository_root: Path,
) -> None:
    case = _case()
    base = next(item for item in case.scenario_set.scenarios if item.kind is ScenarioKind.BASE)
    base = replace(
        base,
        financials=replace(
            base.financials,
            incremental_working_capital="15",
            declared_incremental_fcf="0",
        ),
    )
    scenario_set = gate_support._rebind(
        case.scenario_set,
        scenarios=tuple(
            base if item.kind is ScenarioKind.BASE else item for item in case.scenario_set.scenarios
        ),
    )
    result = evaluate_complete_stage4(
        replace(
            case,
            scenario_set=scenario_set,
            e4_incremental_fcf_interval=DecimalInterval("0", "5"),
        ),
        _capabilities(repository_root),
    )

    assert result.overall_outcome is GateOutcome.SHADOW_ONLY
    assert result.research_decision_label is DecisionState.SHADOW_ONLY
    assert result.authorizes_shadow is False
    assert result.unified_gate_view.gate_3.outcome is None


def test_exit_is_independent_and_never_rewrites_passing_gates(repository_root: Path) -> None:
    capabilities = _capabilities(repository_root)
    base_case = _case()
    no_position = Stage4ExitInput(
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
    no_position_result = evaluate_complete_stage4(
        replace(base_case, exit_input=no_position),
        capabilities,
    )
    holding = base_case.exit_input.holding_snapshot
    assert holding is not None
    invalid_holding = bind_synthetic_holding_snapshot(
        replace(holding, established_valuation_hash=event_support._hash("f"))
    )
    invalid_exit_result = evaluate_complete_stage4(
        replace(
            base_case,
            exit_input=replace(base_case.exit_input, holding_snapshot=invalid_holding),
        ),
        capabilities,
    )

    assert no_position_result.overall_outcome is GateOutcome.PASS
    assert no_position_result.exit_disposition is ExitDisposition.NOT_APPLICABLE
    assert invalid_exit_result.overall_outcome is GateOutcome.PASS
    assert invalid_exit_result.exit_disposition is None
    assert invalid_exit_result.unified_gate_view.gate_4.outcome is GateOutcome.PASS


def test_complete_engine_rejects_nested_cutoff_drift_before_evaluation(
    repository_root: Path,
) -> None:
    case = _case()
    drifted_scenarios = gate_support._rebind(
        case.scenario_set,
        knowledge_cutoff=gate_support.CUTOFF,
    )
    result = evaluate_complete_stage4(
        replace(case, scenario_set=drifted_scenarios),
        _capabilities(repository_root),
    )

    assert result.evaluation_state is CompleteStage4EvaluationState.BLOCKED_BEFORE_EVALUATION
    assert result.reason_codes == ("STAGE4_COMPLETE_KNOWLEDGE_CUTOFF_MISMATCH",)


def test_complete_engine_replay_is_deterministic_and_input_sensitive(repository_root: Path) -> None:
    capabilities = _capabilities(repository_root)
    base_case = _case()
    first = evaluate_complete_stage4(base_case, capabilities)
    second = evaluate_complete_stage4(_case(), capabilities)
    changed_price = bind_synthetic_price_assumption(
        replace(base_case.price_assumption, price="10.01")
    )
    changed = evaluate_complete_stage4(
        replace(base_case, price_assumption=changed_price),
        capabilities,
    )

    assert first.to_json_value() == second.to_json_value()
    assert first.replay_hash == second.replay_hash
    assert first.input_hash != changed.input_hash
    assert first.replay_hash != changed.replay_hash


def test_complete_result_rejects_forged_identity_outcome_and_state(repository_root: Path) -> None:
    result = evaluate_complete_stage4(_case(), _capabilities(repository_root))

    with pytest.raises(ValueError, match="exact approved 4B capability"):
        replace(
            result,
            complete_capability=replace(
                result.complete_capability,
                approval_id="forged-approval",
            ),
        )
    with pytest.raises(ValueError, match="deterministic gate aggregation"):
        replace(result, overall_outcome=GateOutcome.REJECT)
    with pytest.raises(ValueError, match="result presence differs"):
        replace(
            result,
            evaluation_state=CompleteStage4EvaluationState.BLOCKED_BEFORE_EVALUATION,
        )


def test_complete_case_has_no_partial_result_injection_fields() -> None:
    field_names = {item.name for item in fields(Stage4CompleteSyntheticCase)}

    assert field_names.isdisjoint(
        {
            "context_result",
            "event_result",
            "gate_profit_result",
            "expectation_valuation_exit_result",
            "overall_outcome",
        }
    )
