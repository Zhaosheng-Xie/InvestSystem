from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5_governance import (
    ApprovedStage5MarketExecutionRules,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    ImpactNode,
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    Stage5MarketCandidate,
    Stage5MarketExecutionCase,
    Stage5SubmissionReductionConstraint,
    TradeSide,
    bind_stage5_artifact,
    bind_stage5_submission_constraint_candidate,
    evaluate_stage5_market_execution,
    evaluate_stage5_market_execution_constrained,
    plan_stage5_market_candidate,
    stage5_constrained_market_execution_replay_sha256,
)
from unit import test_stage5_market_execution as stage5b_support

ZERO = HashDigest(algorithm="sha256", value="0" * 64)


def _provisional_constraint(
    case: Stage5MarketExecutionCase,
    *,
    maximum_quantity: int,
    maximum_gross_notional: str,
    maximum_cash_outflow: str | None,
    maximum_transaction_cost_reserve: str | None,
    maximum_sellable_quantity: int | None,
) -> Stage5SubmissionReductionConstraint:
    return bind_stage5_artifact(
        Stage5SubmissionReductionConstraint(
            identity=stage5b_support._identity(
                "stage5c_provisional_constraint",
                as_of=stage5b_support.APPROVED_AT,
            ),
            case_id=case.case_id,
            strategy_id=case.strategy_id,
            security_id=case.security_id,
            account_fixture_id=case.account_fixture_id,
            action_intent=case.action_intent,
            as_of=stage5b_support.APPROVED_AT,
            effective_approved_quantity=case.synthetic_approval_fixture.approved_quantity,
            maximum_quantity=maximum_quantity,
            maximum_gross_notional=maximum_gross_notional,
            maximum_cash_outflow=maximum_cash_outflow,
            maximum_transaction_cost_reserve=maximum_transaction_cost_reserve,
            maximum_sellable_quantity=maximum_sellable_quantity,
            candidate_hash=ZERO,
            candidate_session_id=None,
            candidate_observation_id=None,
            candidate_at=None,
            candidate_market_rule_hash=None,
            candidate_cost_schedule_hash=None,
            candidate_impact_curve_hash=None,
            target_hash=stage5b_support.SOURCE_HASH,
            portfolio_approval_hash=stage5b_support.SOURCE_HASH,
            market_approval_hash=case.synthetic_approval_fixture.identity.declared_content_hash,
            source_account_snapshot_hash=stage5b_support.SOURCE_HASH,
            source_initial_ledger_hash=stage5b_support.SOURCE_HASH,
            source_risk_cluster_hash=stage5b_support.SOURCE_HASH,
            source_market_regime_hash=stage5b_support.SOURCE_HASH,
            expected_ledger_head_hash=stage5b_support.SOURCE_HASH,
            reason_codes=("STAGE5C_TEST_REDUCTION_ONLY",),
        )
    )


def _plan_and_bind(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
    provisional: Stage5SubmissionReductionConstraint,
) -> tuple[Stage5MarketCandidate, Stage5SubmissionReductionConstraint]:
    candidate = plan_stage5_market_candidate(case, rules, provisional)
    return candidate, bind_stage5_submission_constraint_candidate(provisional, candidate)


def test_constrained_flow_chooses_first_window_after_recomputing_gate(
    repository_root: Path,
) -> None:
    rules = stage5b_support._approved_rules(repository_root)
    first = stage5b_support._session(20)
    second = stage5b_support._session(21)
    steep_impact = stage5b_support._impact(
        nodes=(ImpactNode("0", "0"), ImpactNode("0.05", "0.20")),
    )
    case = stage5b_support._case(
        repository_root,
        sessions=(first, second),
        observations=(
            stage5b_support._observation(first, volume=10_000),
            stage5b_support._observation(second, volume=80_000),
        ),
        impacts=(steep_impact,),
    )
    standalone = evaluate_stage5_market_execution(case, rules)
    assert standalone.fill is not None
    assert standalone.fill.observation_id == f"observation_{second.session_id}"

    provisional = _provisional_constraint(
        case,
        maximum_quantity=100,
        maximum_gross_notional="10000",
        maximum_cash_outflow="10000",
        maximum_transaction_cost_reserve="20",
        maximum_sellable_quantity=None,
    )
    candidate, bound = _plan_and_bind(case, rules, provisional)
    projection = evaluate_stage5_market_execution_constrained(case, rules, bound)

    assert candidate.candidate_observation_id == f"observation_{first.session_id}"
    assert bound.candidate_hash == candidate.candidate_hash
    result = projection.market_execution_result
    assert result.status is Stage5ExecutionStatus.FILLED
    assert (
        result.fill is not None and result.fill.observation_id == candidate.candidate_observation_id
    )
    assert result.cancelled_quantity == 0
    assert projection.effective_approved_quantity == 1_000
    assert projection.unsubmitted_quantity == 900
    assert projection.unfilled_cancelled_quantity == 0
    assert all(event.event_type.value != "CANCELLED" for event in result.events)
    assert projection.replay_hash.value == stage5_constrained_market_execution_replay_sha256(
        case,
        candidate,
        bound,
        result,
    )


@pytest.mark.parametrize(
    ("maximum_cash_outflow", "cost_reserve"),
    (("810", "20"), ("10000", "1")),
)
def test_buy_reserve_is_enforced_before_submission(
    repository_root: Path,
    maximum_cash_outflow: str,
    cost_reserve: str,
) -> None:
    rules = stage5b_support._approved_rules(repository_root)
    case = stage5b_support._case(repository_root)
    provisional = _provisional_constraint(
        case,
        maximum_quantity=100,
        maximum_gross_notional="10000",
        maximum_cash_outflow=maximum_cash_outflow,
        maximum_transaction_cost_reserve=cost_reserve,
        maximum_sellable_quantity=None,
    )
    candidate, bound = _plan_and_bind(case, rules, provisional)

    projection = evaluate_stage5_market_execution_constrained(case, rules, bound)

    assert candidate.candidate_at is None
    assert projection.market_execution_result.order_intent is None
    assert projection.market_execution_result.fill is None
    assert projection.unsubmitted_quantity == 1_000
    assert projection.unfilled_cancelled_quantity == 0


def test_sell_constraint_enforces_portfolio_notional_cap(repository_root: Path) -> None:
    rules = stage5b_support._approved_rules(repository_root)
    base = stage5b_support._case(repository_root)
    approval = stage5b_support._approval(
        base.proposal_reference_price,
        identity=stage5b_support._identity(
            "stage5c_sell_market_approval",
            as_of=stage5b_support.APPROVED_AT,
        ),
        action_intent=Stage5ActionIntent.EXIT,
        approved_quantity=200,
    )
    case = replace(
        base,
        action_intent=Stage5ActionIntent.EXIT,
        proposed_quantity=200,
        synthetic_approval_fixture=approval,
        cost_schedules=(
            stage5b_support._cost(
                identity=stage5b_support._identity("stage5c_sell_cost"),
                side=TradeSide.SELL,
                tax_rate="0.001",
            ),
        ),
        impact_curves=(
            stage5b_support._impact(
                identity=stage5b_support._identity("stage5c_sell_impact"),
                side=TradeSide.SELL,
            ),
        ),
        risk_exit_mandate_ref="stage5c_synthetic_exit_mandate",
    )
    provisional = _provisional_constraint(
        case,
        maximum_quantity=200,
        maximum_gross_notional="100",
        maximum_cash_outflow=None,
        maximum_transaction_cost_reserve=None,
        maximum_sellable_quantity=200,
    )
    candidate, bound = _plan_and_bind(case, rules, provisional)

    projection = evaluate_stage5_market_execution_constrained(case, rules, bound)

    fill = projection.market_execution_result.fill
    assert fill is not None
    assert Decimal(fill.gross_notional) <= Decimal("100")
    assert projection.unsubmitted_quantity == 200 - fill.quantity
    assert projection.unfilled_cancelled_quantity == 0
    assert projection.market_candidate == candidate


def test_constrained_execution_rejects_drift_from_final_candidate(
    repository_root: Path,
) -> None:
    rules = stage5b_support._approved_rules(repository_root)
    case = stage5b_support._case(repository_root)
    provisional = _provisional_constraint(
        case,
        maximum_quantity=100,
        maximum_gross_notional="10000",
        maximum_cash_outflow="10000",
        maximum_transaction_cost_reserve="20",
        maximum_sellable_quantity=None,
    )
    candidate, bound = _plan_and_bind(case, rules, provisional)
    drifted = bind_stage5_artifact(
        replace(
            bound,
            candidate_observation_id="different_observation",
            identity=replace(bound.identity, declared_content_hash=ZERO),
        )
    )

    projection = evaluate_stage5_market_execution_constrained(case, rules, drifted)

    assert candidate.candidate_at is not None
    assert projection.market_execution_result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert projection.market_execution_result.reason_codes == (
        "SUBMISSION_REDUCTION_CANDIDATE_MISMATCH",
    )
    assert projection.market_execution_result.fill is None
