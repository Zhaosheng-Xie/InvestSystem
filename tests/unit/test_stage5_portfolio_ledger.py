from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    RuleApprovalRegistry,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import HashDigest, RunMode
from invest_system.strategies.industrial_event.stage5_execution_contracts import (
    InitialLedgerSnapshot,
    MarketRegime,
    MarketRegimeSnapshot,
    PortfolioApprovalDecision,
    PortfolioSizingInputs,
    RiskClusterAssignment,
    RiskClusterExposure,
    RiskClusterSnapshot,
    RiskClusterType,
    SettlementAvailabilityTerms,
    SettlementMoment,
    SettlementMomentKind,
    StressScenarioInput,
    SyntheticAccountSnapshot,
    SyntheticCorporateActionSet,
    SyntheticLotSnapshot,
    SyntheticPortfolioApproval,
    SyntheticPositionSnapshot,
    bind_stage5c_artifact,
    stage5c_initial_ledger_head_sha256,
)
from invest_system.strategies.industrial_event.stage5_governance import (
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
    require_stage5_rule_capability,
)
from invest_system.strategies.industrial_event.stage5_ledger import (
    STAGE5C_LEDGER_PRIORITY,
    LedgerAccountCode,
    LedgerEvent,
    LedgerEventType,
    LedgerPosting,
    LedgerReplayStatus,
    bind_ledger_event,
    replay_stage5c_ledger,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    Stage5MarketExecutionCase,
    TradeSide,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    Stage5PortfolioLedgerCase,
    evaluate_stage5_portfolio_ledger,
    stage5c_portfolio_ledger_projection_sha256,
)
from invest_system.strategies.industrial_event.stage5_portfolio_risk import (
    evaluate_stage5_portfolio_target,
)
from unit import test_stage5_market_execution as stage5b_support

ZERO = HashDigest(algorithm="sha256", value="0" * 64)


def _rules(
    repository_root: Path,
) -> tuple[ApprovedStage5MarketExecutionRules, ApprovedStage5PortfolioLedgerRules]:
    bundle = rule_bundle_document_from_json_value(
        json.loads(
            stage5b_support._one(
                repository_root,
                "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.rule-bundle.json",
            ).read_text(encoding="utf-8")
        )
    )
    approval = rule_approval_record_from_json_value(
        json.loads(
            stage5b_support._one(
                repository_root,
                "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.approval.json",
            ).read_text(encoding="utf-8")
        )
    )
    capability = require_stage5_rule_capability(
        bundle,
        registry=RuleApprovalRegistry((approval,)),
    )
    return (
        ApprovedStage5MarketExecutionRules.from_approved_bundle(bundle, capability),
        ApprovedStage5PortfolioLedgerRules.from_approved_bundle(bundle, capability),
    )


def _risk_exposures(
    *, market_value: str = "0", planned_loss: str = "0"
) -> tuple[RiskClusterExposure, ...]:
    return tuple(
        RiskClusterExposure(
            cluster_type,
            f"cluster_{cluster_type.value}",
            market_value,
            planned_loss,
        )
        for cluster_type in RiskClusterType
    )


def _buy_account(*, drawdown: str = "0") -> SyntheticAccountSnapshot:
    high_water = Decimal("100000")
    nav = high_water * (Decimal(1) - Decimal(drawdown))
    return bind_stage5c_artifact(
        SyntheticAccountSnapshot(
            identity=stage5b_support._identity(
                "synthetic_buy_account_stage5c",
                as_of=stage5b_support.APPROVED_AT,
            ),
            strategy_id="industrial_bottleneck_event",
            account_fixture_id="anonymous_account_001",
            base_currency="CNY",
            settled_cash=str(nav),
            reserved_cash="0",
            available_cash=str(nav),
            unsettled_cash_receivable="0",
            unsettled_cash_payable="0",
            positions=(),
            net_asset_value=str(nav),
            adjusted_high_water_mark=str(high_water),
            declared_drawdown=drawdown,
            risk_cluster_exposures=_risk_exposures(),
            aggregate_open_planned_loss="0",
            prior_stopped=False,
            synthetic_recovery_record_hash=None,
            synthetic_recovery_approved=False,
        )
    )


def _sell_account(raw: Stage5MarketExecutionCase) -> SyntheticAccountSnapshot:
    market_rule_hash = raw.market_rule_sets[0].identity.declared_content_hash
    position = SyntheticPositionSnapshot(
        security_id=raw.security_id,
        company_id="company_600000",
        market_value="10000",
        lots=(
            SyntheticLotSnapshot(
                "opening_lot_001",
                raw.security_id,
                datetime(2025, 1, 2, 3, 0, tzinfo=UTC),
                100,
                100,
                "700",
                market_rule_hash,
            ),
            SyntheticLotSnapshot(
                "opening_lot_002",
                raw.security_id,
                datetime(2025, 1, 3, 3, 0, tzinfo=UTC),
                200,
                150,
                "1600",
                market_rule_hash,
            ),
        ),
    )
    return bind_stage5c_artifact(
        SyntheticAccountSnapshot(
            identity=stage5b_support._identity(
                "synthetic_sell_account_stage5c",
                as_of=stage5b_support.APPROVED_AT,
            ),
            strategy_id=raw.strategy_id,
            account_fixture_id=raw.account_fixture_id,
            base_currency="CNY",
            settled_cash="90000",
            reserved_cash="0",
            available_cash="90000",
            unsettled_cash_receivable="0",
            unsettled_cash_payable="0",
            positions=(position,),
            net_asset_value="100000",
            adjusted_high_water_mark="100000",
            declared_drawdown="0",
            risk_cluster_exposures=_risk_exposures(market_value="10000", planned_loss="100"),
            aggregate_open_planned_loss="100",
            prior_stopped=False,
            synthetic_recovery_record_hash=None,
            synthetic_recovery_approved=False,
        )
    )


def _clusters() -> RiskClusterSnapshot:
    return bind_stage5c_artifact(
        RiskClusterSnapshot(
            identity=stage5b_support._identity(
                "risk_clusters_stage5c", as_of=stage5b_support.APPROVED_AT
            ),
            strategy_id="industrial_bottleneck_event",
            security_id="600000.SH",
            company_id="company_600000",
            assignments=tuple(
                RiskClusterAssignment(cluster_type, f"cluster_{cluster_type.value}")
                for cluster_type in RiskClusterType
            ),
        )
    )


def _regime(value: MarketRegime | None) -> MarketRegimeSnapshot:
    return bind_stage5c_artifact(
        MarketRegimeSnapshot(
            identity=stage5b_support._identity(
                "market_regime_stage5c", as_of=stage5b_support.APPROVED_AT
            ),
            regime=value,
            synthetic_fixture=True,
        )
    )


def _stress() -> StressScenarioInput:
    return bind_stage5c_artifact(
        StressScenarioInput(
            identity=stage5b_support._identity("stress_stage5c", as_of=stage5b_support.APPROVED_AT),
            scenario_return="-0.20",
            basis_id="synthetic_nav_stress",
            comparable_to_account_nav=True,
        )
    )


def _sizing(
    raw: Stage5MarketExecutionCase,
    *,
    cost_reserve: str = "20",
) -> PortfolioSizingInputs:
    return bind_stage5c_artifact(
        PortfolioSizingInputs(
            identity=stage5b_support._identity(
                "portfolio_sizing_stage5c", as_of=stage5b_support.APPROVED_AT
            ),
            proposal_reference_price_hash=raw.proposal_reference_price.identity.declared_content_hash,
            liquidity_capacity_value="50000",
            worst_applicable_cost_reserve=cost_reserve,
            values_are_comparable_cny=True,
        )
    )


def _settlement(raw: Stage5MarketExecutionCase) -> SettlementAvailabilityTerms:
    fill_at = datetime(2025, 1, 20, 2, 31, tzinfo=UTC)
    next_open = datetime(2025, 1, 21, 2, 10, tzinfo=UTC)
    return bind_stage5c_artifact(
        SettlementAvailabilityTerms(
            identity=stage5b_support._identity("settlement_terms_stage5c"),
            venue=raw.venue,
            board=raw.board,
            security_type=raw.security_type,
            risk_label=raw.risk_label,
            trade_local_date="2025-01-20",
            market_rule_hash=raw.market_rule_sets[0].identity.declared_content_hash,
            moments=(
                SettlementMoment(SettlementMomentKind.SECURITY_SETTLEMENT, "2025-01-21", next_open),
                SettlementMoment(SettlementMomentKind.SECURITY_SELLABLE, "2025-01-21", next_open),
                SettlementMoment(SettlementMomentKind.BUY_CASH_PAYABLE, "2025-01-20", fill_at),
                SettlementMoment(
                    SettlementMomentKind.SELL_PROCEEDS_RECEIVABLE,
                    "2025-01-20",
                    fill_at,
                ),
                SettlementMoment(
                    SettlementMomentKind.SELL_CASH_SETTLEMENT,
                    "2025-01-21",
                    next_open,
                ),
                SettlementMoment(
                    SettlementMomentKind.SELL_CASH_AVAILABLE,
                    "2025-01-21",
                    next_open.replace(minute=11),
                ),
            ),
            source_document_ids=("synthetic_settlement_fixture",),
            source_byte_hashes=(stage5b_support.SOURCE_HASH,),
            same_day_sellable=False,
            special_exception_id=None,
        )
    )


def _buy_raw(repository_root: Path) -> Stage5MarketExecutionCase:
    trade_session = stage5b_support._session(20)
    settlement_session = stage5b_support._session(21)
    return stage5b_support._case(
        repository_root,
        sessions=(trade_session, settlement_session),
        observations=(stage5b_support._observation(trade_session),),
    )


def _sell_raw(repository_root: Path) -> Stage5MarketExecutionCase:
    base = _buy_raw(repository_root)
    sell_approval = stage5b_support._approval(
        base.proposal_reference_price,
        identity=stage5b_support._identity(
            "synthetic_sell_approval", as_of=stage5b_support.APPROVED_AT
        ),
        action_intent=Stage5ActionIntent.EXIT,
        approved_quantity=200,
    )
    return replace(
        base,
        action_intent=Stage5ActionIntent.EXIT,
        proposed_quantity=200,
        synthetic_approval_fixture=sell_approval,
        cost_schedules=(
            stage5b_support._cost(
                identity=stage5b_support._identity("cost_sse_sell_standard"),
                side=TradeSide.SELL,
                tax_rate="0.001",
            ),
        ),
        impact_curves=(
            stage5b_support._impact(
                identity=stage5b_support._identity("impact_sse_sell_minute"),
                side=TradeSide.SELL,
            ),
        ),
        risk_exit_mandate_ref="synthetic_risk_exit_mandate",
    )


def _case(
    repository_root: Path,
    *,
    regime: MarketRegime | None = MarketRegime.NORMAL,
    reject: bool = False,
    sell: bool = False,
    clock: datetime = datetime(2025, 2, 1, tzinfo=UTC),
    cost_reserve: str = "20",
) -> tuple[
    Stage5PortfolioLedgerCase,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
]:
    market_rules, portfolio_rules = _rules(repository_root)
    raw = _sell_raw(repository_root) if sell else _buy_raw(repository_root)
    raw = replace(raw, injected_clock=clock)
    account = _sell_account(raw) if sell else _buy_account()
    clusters = _clusters()
    regime_snapshot = _regime(regime)
    stress = _stress()
    sizing = _sizing(raw, cost_reserve=cost_reserve)
    target_identity = stage5b_support._identity(
        "portfolio_sell_target_stage5c" if sell else "portfolio_buy_target_stage5c",
        as_of=stage5b_support.APPROVED_AT,
    )
    risk = evaluate_stage5_portfolio_target(
        raw,
        account,
        clusters,
        regime_snapshot,
        stress,
        sizing,
        target_identity,
        portfolio_rules,
    )
    target = risk.target
    effective_reject = reject or target is None or target.target_quantity == 0
    target_hash = target.identity.declared_content_hash if target else ZERO
    target_quantity = target.target_quantity if target else 0
    rounded_value = Decimal(target.rounded_target_value) if target else Decimal(0)
    planned_loss = (
        rounded_value * Decimal(target.stress_loss_rate) if target and not sell else Decimal(0)
    )
    approval = bind_stage5c_artifact(
        SyntheticPortfolioApproval(
            identity=stage5b_support._identity(
                "portfolio_approval_stage5c", as_of=stage5b_support.APPROVED_AT
            ),
            case_id=raw.case_id,
            security_id=raw.security_id,
            account_fixture_id=raw.account_fixture_id,
            action_intent=raw.action_intent,
            decision=(
                PortfolioApprovalDecision.REJECTED
                if effective_reject
                else PortfolioApprovalDecision.APPROVED
            ),
            target_hash=target_hash,
            portfolio_risk_evaluation_hash=HashDigest(
                algorithm="sha256",
                value=canonical_sha256(risk),
            ),
            market_approval_hash=raw.synthetic_approval_fixture.identity.declared_content_hash,
            approved_at=raw.synthetic_approval_fixture.approved_at,
            expires_at=raw.synthetic_approval_fixture.expires_at,
            approved_quantity=0 if effective_reject else target_quantity,
            approved_notional_cap="0" if effective_reject else str(rounded_value),
            approved_planned_loss_cap="0" if effective_reject else str(planned_loss),
            reason_codes=("SYNTHETIC_OWNER_TEST_DECISION",),
        )
    )
    initial = bind_stage5c_artifact(
        InitialLedgerSnapshot(
            identity=stage5b_support._identity(
                "initial_ledger_stage5c", as_of=stage5b_support.APPROVED_AT
            ),
            strategy_id=raw.strategy_id,
            account_fixture_id=raw.account_fixture_id,
            account_snapshot_hash=account.identity.declared_content_hash,
            expected_head_hash=HashDigest(
                algorithm="sha256",
                value=stage5c_initial_ledger_head_sha256(account.identity.declared_content_hash),
            ),
            head_observed_at=datetime(2025, 1, 20, 2, 31, tzinfo=UTC),
            no_intervening_events_attested=True,
            prior_event_hashes=(),
        )
    )
    corporate_actions = bind_stage5c_artifact(
        SyntheticCorporateActionSet(
            identity=stage5b_support._identity("corporate_actions_stage5c"),
            security_id=raw.security_id,
            applicable_action_ids=(),
            explicitly_empty_for_stage5c=True,
        )
    )
    stage5c_case = Stage5PortfolioLedgerCase(
        case_id=raw.case_id,
        market_execution_case=raw,
        synthetic_account_snapshot=account,
        risk_cluster_snapshot=clusters,
        market_regime_snapshot=regime_snapshot,
        stress_scenario_input=stress,
        portfolio_sizing_inputs=sizing,
        synthetic_portfolio_approval=approval,
        initial_ledger_snapshot=initial,
        settlement_terms=(_settlement(raw),),
        corporate_action_set=corporate_actions,
        target_identity=target_identity,
        constraint_identity=stage5b_support._identity(
            "submission_constraint_stage5c", as_of=stage5b_support.APPROVED_AT
        ),
        code_commit="synthetic-stage5c-test",
        config_hash=stage5b_support.CONFIG_HASH,
        injected_clock=clock,
    )
    return stage5c_case, market_rules, portfolio_rules


def test_stage5c_buy_target_constraint_fill_and_ledger_reconcile(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.portfolio_risk_evaluation is not None
    assert result.portfolio_risk_evaluation.target is not None
    assert result.portfolio_risk_evaluation.target.target_quantity == 300
    assert result.submission_constraint is not None
    assert result.submission_constraint.maximum_quantity == 300
    assert result.constrained_market_projection is not None
    fill = result.constrained_market_projection.market_execution_result.fill
    assert fill is not None and fill.quantity == 200
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    assert result.ledger_replay.derived_state is not None
    assert result.ledger_replay.derived_state.actual_quantity("600000.SH") == 200
    assert result.ledger_replay.derived_state.sellable_quantity("600000.SH") == 200
    assert result.position_layers is not None
    assert (
        result.position_layers.target_quantity,
        result.position_layers.approved_quantity,
        result.position_layers.submitted_quantity,
        result.position_layers.filled_quantity,
        result.position_layers.actual_quantity,
    ) == (300, 300, 200, 200, 200)
    assert result.fill_ledger_projection is not None
    assert result.fill_ledger_projection.unsubmitted_approved_quantity == 100
    assert result.fill_ledger_projection.unfilled_cancelled_quantity == 0
    event_types = {event.event_type for event in result.ledger_replay.accepted_events}
    assert {
        LedgerEventType.CASH_RESERVATION,
        LedgerEventType.TRADE_FILL,
        LedgerEventType.TRADE_SETTLEMENT,
        LedgerEventType.SECURITY_AVAILABILITY,
    } <= event_types
    assert result.projection_replay_hash.value == stage5c_portfolio_ledger_projection_sha256(
        case, result
    )
    assert result.persists_state is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False


def test_stage5c_replay_is_as_of_injected_clock_without_future_sellability(
    repository_root: Path,
) -> None:
    replay_clock = datetime(2025, 1, 20, 2, 31, tzinfo=UTC)
    case, market_rules, portfolio_rules = _case(repository_root, clock=replay_clock)

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.ledger_replay_as_of == replay_clock
    assert result.fill_ledger_projection is not None
    assert any(event.effective_at > replay_clock for event in result.fill_ledger_projection.events)
    assert result.ledger_replay is not None
    assert all(event.effective_at <= replay_clock for event in result.ledger_replay.accepted_events)
    assert result.ledger_replay.derived_state is not None
    assert result.ledger_replay.derived_state.actual_quantity("600000.SH") == 200
    assert result.ledger_replay.derived_state.sellable_quantity("600000.SH") == 0


def _reduce_portfolio_approval(
    case: Stage5PortfolioLedgerCase,
    *,
    quantity: int | None = None,
    notional_cap: str | None = None,
    planned_loss_cap: str | None = None,
) -> Stage5PortfolioLedgerCase:
    approval = case.synthetic_portfolio_approval
    reduced = bind_stage5c_artifact(
        replace(
            approval,
            approved_quantity=(approval.approved_quantity if quantity is None else quantity),
            approved_notional_cap=(
                approval.approved_notional_cap if notional_cap is None else notional_cap
            ),
            approved_planned_loss_cap=(
                approval.approved_planned_loss_cap if planned_loss_cap is None else planned_loss_cap
            ),
        )
    )
    return replace(case, synthetic_portfolio_approval=reduced)


@pytest.mark.parametrize(
    ("quantity", "notional_cap", "planned_loss_cap", "expected_fill"),
    (
        (100, None, None, 100),
        (None, "900", None, 100),
        (None, None, "180", 100),
        (None, None, "150", 0),
    ),
)
def test_stage5c_each_portfolio_approval_cap_reduces_before_submission(
    repository_root: Path,
    quantity: int | None,
    notional_cap: str | None,
    planned_loss_cap: str | None,
    expected_fill: int,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    reduced_case = _reduce_portfolio_approval(
        case,
        quantity=quantity,
        notional_cap=notional_cap,
        planned_loss_cap=planned_loss_cap,
    )

    result = evaluate_stage5_portfolio_ledger(reduced_case, market_rules, portfolio_rules)

    fill = (
        result.constrained_market_projection.market_execution_result.fill
        if result.constrained_market_projection is not None
        else None
    )
    assert (fill.quantity if fill is not None else 0) == expected_fill
    if expected_fill == 0:
        assert result.position_layers is not None
        assert result.position_layers.submitted_quantity == 0


def test_stage5c_worst_cost_reserve_blocks_before_order_or_fill(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root, cost_reserve="1")

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.market_candidate is not None
    assert result.market_candidate.candidate_at is None
    assert result.constrained_market_projection is None
    assert result.fill_ledger_projection is None
    assert any(
        "MINIMUM_LOT_OR_ADVERSE_PRICE_EXCEEDS_CAP" in attempt.reason_codes
        for attempt in result.market_candidate.market_execution_preview.attempts
    )


def test_stage5c_sell_notional_approval_cap_reduces_before_submission(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root, sell=True)
    reduced_case = _reduce_portfolio_approval(case, notional_cap="900")

    result = evaluate_stage5_portfolio_ledger(reduced_case, market_rules, portfolio_rules)

    assert result.constrained_market_projection is not None
    fill = result.constrained_market_projection.market_execution_result.fill
    assert fill is not None
    assert 0 < fill.quantity < case.synthetic_portfolio_approval.approved_quantity
    assert Decimal(fill.gross_notional) <= Decimal("900")


def test_stage5c_sell_uses_sellable_quantity_fifo_and_separate_cash_availability(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root, sell=True)

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    state = result.ledger_replay.derived_state
    assert state is not None
    assert state.actual_quantity("600000.SH") == 100
    assert state.sellable_quantity("600000.SH") == 50
    assert tuple(lot.lot_id for lot in state.lots) == ("opening_lot_002",)
    assert state.lots[0].remaining_quantity == 100
    assert state.lots[0].sellable_quantity == 50
    assert state.lots[0].remaining_full_cost == "800"
    assert Decimal(state.available_cash) > Decimal("90000")
    assert state.settled_unavailable_cash == "0"
    assert result.position_layers is not None
    assert result.position_layers.actual_quantity == 100


def test_stage5c_explicit_rejection_never_plans_or_submits_market(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root, reject=True)

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
    assert result.market_candidate is None
    assert result.submission_constraint is None
    assert result.constrained_market_projection is None
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    assert result.position_layers is not None
    assert result.position_layers.approved_quantity == 0
    assert result.position_layers.actual_quantity == 0


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    (
        ("run_mode", RunMode.BACKTEST),
        ("anonymous_synthetic_fixture", False),
        ("validation_only", False),
        ("reads_kb_internal_state", True),
        ("connects_broker", True),
        ("persists_state", True),
    ),
)
def test_stage5c_authority_boundary_fails_closed(
    repository_root: Path,
    field_name: str,
    field_value: object,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)

    result = evaluate_stage5_portfolio_ledger(
        replace(case, **{field_name: field_value}),  # type: ignore[arg-type]
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("STAGE5C_AUTHORITY_BOUNDARY_VIOLATION",)
    assert result.market_candidate is None
    assert result.constrained_market_projection is None


def test_stage5c_rejects_clock_drift_and_future_stage5c_inputs(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    clock_drift = evaluate_stage5_portfolio_ledger(
        replace(case, injected_clock=case.injected_clock + timedelta(seconds=1)),
        market_rules,
        portfolio_rules,
    )
    assert clock_drift.reason_codes == ("STAGE5B_AND_STAGE5C_CLOCK_MISMATCH",)

    future = case.injected_clock + timedelta(seconds=1)
    future_actions = bind_stage5c_artifact(
        replace(
            case.corporate_action_set,
            identity=replace(
                case.corporate_action_set.identity,
                as_of=future,
                knowledge_cutoff=future,
                declared_content_hash=ZERO,
            ),
        )
    )
    future_input = evaluate_stage5_portfolio_ledger(
        replace(case, corporate_action_set=future_actions),
        market_rules,
        portfolio_rules,
    )
    assert future_input.reason_codes == ("STAGE5C_INPUT_NOT_PIT_AVAILABLE",)


def test_stage5c_rejects_target_input_knowledge_known_only_after_approval(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    future_cutoff = case.synthetic_portfolio_approval.approved_at + timedelta(seconds=1)
    future_sizing = bind_stage5c_artifact(
        replace(
            case.portfolio_sizing_inputs,
            identity=replace(
                case.portfolio_sizing_inputs.identity,
                knowledge_cutoff=future_cutoff,
            ),
        )
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, portfolio_sizing_inputs=future_sizing),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("STAGE5C_TARGET_INPUT_NOT_PIT_AT_APPROVAL",)
    assert result.market_candidate is None


def test_stage5c_rejects_candidate_attestation_known_only_after_candidate(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    future_cutoff = case.initial_ledger_snapshot.head_observed_at + timedelta(seconds=1)
    future_actions = bind_stage5c_artifact(
        replace(
            case.corporate_action_set,
            identity=replace(
                case.corporate_action_set.identity,
                as_of=future_cutoff,
                knowledge_cutoff=future_cutoff,
            ),
        )
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, corporate_action_set=future_actions),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("STAGE5C_CANDIDATE_INPUT_NOT_PIT_AVAILABLE",)
    assert result.market_candidate is not None
    assert result.constrained_market_projection is None


def test_stage5c_sizing_source_identity_changes_every_downstream_binding(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    baseline = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    drifted_sizing = bind_stage5c_artifact(
        replace(
            case.portfolio_sizing_inputs,
            identity=replace(
                case.portfolio_sizing_inputs.identity,
                artifact_id="portfolio_sizing_inputs_stage5c_revised_source",
                supersedes_artifact_id=case.portfolio_sizing_inputs.identity.artifact_id,
            ),
        )
    )
    drifted_risk = evaluate_stage5_portfolio_target(
        case.market_execution_case,
        case.synthetic_account_snapshot,
        case.risk_cluster_snapshot,
        case.market_regime_snapshot,
        case.stress_scenario_input,
        drifted_sizing,
        case.target_identity,
        portfolio_rules,
    )
    assert drifted_risk.target is not None
    assert baseline.portfolio_risk_evaluation is not None
    assert baseline.portfolio_risk_evaluation.target is not None
    assert (
        drifted_risk.target.identity.declared_content_hash
        != baseline.portfolio_risk_evaluation.target.identity.declared_content_hash
    )

    stale_approval_result = evaluate_stage5_portfolio_ledger(
        replace(case, portfolio_sizing_inputs=drifted_sizing),
        market_rules,
        portfolio_rules,
    )
    assert stale_approval_result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert stale_approval_result.reason_codes == (
        "PORTFOLIO_APPROVAL_INCREASE_OR_TARGET_BINDING_MISMATCH",
    )

    rebound_approval = bind_stage5c_artifact(
        replace(
            case.synthetic_portfolio_approval,
            target_hash=drifted_risk.target.identity.declared_content_hash,
            portfolio_risk_evaluation_hash=HashDigest(
                algorithm="sha256",
                value=canonical_sha256(drifted_risk),
            ),
        )
    )
    rebound = evaluate_stage5_portfolio_ledger(
        replace(
            case,
            portfolio_sizing_inputs=drifted_sizing,
            synthetic_portfolio_approval=rebound_approval,
        ),
        market_rules,
        portfolio_rules,
    )

    assert rebound.status is Stage5ExecutionStatus.FILLED
    assert baseline.submission_constraint is not None
    assert rebound.submission_constraint is not None
    assert baseline.constrained_market_projection is not None
    assert rebound.constrained_market_projection is not None
    assert baseline.ledger_replay is not None and baseline.ledger_replay.derived_state is not None
    assert rebound.ledger_replay is not None and rebound.ledger_replay.derived_state is not None
    assert rebound.portfolio_approval_hash != baseline.portfolio_approval_hash
    assert (
        rebound.submission_constraint.identity.declared_content_hash
        != baseline.submission_constraint.identity.declared_content_hash
    )
    assert (
        rebound.constrained_market_projection.replay_hash
        != baseline.constrained_market_projection.replay_hash
    )
    assert (
        rebound.ledger_replay.derived_state.journal_head_hash
        != baseline.ledger_replay.derived_state.journal_head_hash
    )
    assert rebound.projection_replay_hash != baseline.projection_replay_hash


def test_stage5c_cross_account_snapshot_is_rejected(repository_root: Path) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    other_account = bind_stage5c_artifact(
        replace(case.synthetic_account_snapshot, account_fixture_id="anonymous_account_002")
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, synthetic_account_snapshot=other_account),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("STAGE5C_SCOPE_MISMATCH",)


def test_stage5c_unknown_regime_abstains_before_market_candidate(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root, regime=None)

    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.ABSTAIN
    assert result.reason_codes == ("MARKET_REGIME_UNKNOWN",)
    assert result.market_candidate is None
    assert result.ledger_replay is None


def test_stage5c_target_bound_approval_cannot_be_reused(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    drifted = bind_stage5c_artifact(
        replace(
            case.synthetic_portfolio_approval,
            target_hash=HashDigest(algorithm="sha256", value="f" * 64),
        )
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, synthetic_portfolio_approval=drifted),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("PORTFOLIO_APPROVAL_INCREASE_OR_TARGET_BINDING_MISMATCH",)


@pytest.mark.parametrize(
    ("regime", "drawdown", "expected_quantity", "expected_band", "survival"),
    (
        (MarketRegime.NORMAL, "0", 300, "NORMAL", False),
        (MarketRegime.DEFENSIVE, "0", 100, "NORMAL", False),
        (MarketRegime.CRISIS, "0", 0, "NORMAL", False),
        (MarketRegime.NORMAL, "0.08", 100, "CAUTION_NO_ADDITIONS", False),
        (MarketRegime.NORMAL, "0.12", 0, "DERISK_ONLY", False),
        (MarketRegime.NORMAL, "0.15", 0, "STOPPED", False),
        (MarketRegime.NORMAL, "0.20", 0, "SURVIVAL_LIMIT_BREACH", True),
    ),
)
def test_stage5c_regime_and_drawdown_equalities_enter_stricter_band(
    repository_root: Path,
    regime: MarketRegime,
    drawdown: str,
    expected_quantity: int,
    expected_band: str,
    survival: bool,
) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = stage5b_support._case(repository_root)
    account = _buy_account(drawdown=drawdown)

    risk = evaluate_stage5_portfolio_target(
        raw,
        account,
        _clusters(),
        _regime(regime),
        _stress(),
        _sizing(raw),
        stage5b_support._identity(
            f"target_{regime.value}_{drawdown.replace('.', '_')}",
            as_of=stage5b_support.APPROVED_AT,
        ),
        portfolio_rules,
    )

    assert risk.target is not None
    assert risk.target.target_quantity == expected_quantity
    assert risk.drawdown_band == expected_band
    assert risk.survival_limit_breach is survival


def test_stage5c_drawdown_eight_percent_forbids_addition(repository_root: Path) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = replace(
        stage5b_support._case(repository_root),
        action_intent=Stage5ActionIntent.ADD,
    )

    risk = evaluate_stage5_portfolio_target(
        raw,
        _buy_account(drawdown="0.08"),
        _clusters(),
        _regime(MarketRegime.NORMAL),
        _stress(),
        _sizing(raw),
        stage5b_support._identity("target_add_drawdown_008", as_of=stage5b_support.APPROVED_AT),
        portfolio_rules,
    )

    assert risk.target is not None
    assert risk.target.target_quantity == 0
    assert risk.reason_codes == ("DRAWDOWN_ADDITION_FORBIDDEN",)


def test_stage5c_missing_required_cluster_exposure_abstains(
    repository_root: Path,
) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = stage5b_support._case(repository_root)
    account = bind_stage5c_artifact(
        replace(
            _buy_account(),
            risk_cluster_exposures=_buy_account().risk_cluster_exposures[:-1],
        )
    )

    risk = evaluate_stage5_portfolio_target(
        raw,
        account,
        _clusters(),
        _regime(MarketRegime.NORMAL),
        _stress(),
        _sizing(raw),
        stage5b_support._identity("target_missing_cluster", as_of=stage5b_support.APPROVED_AT),
        portfolio_rules,
    )

    assert risk.status is Stage5ExecutionStatus.ABSTAIN
    assert risk.reason_codes == ("REQUIRED_RISK_CLUSTER_EXPOSURE_MISSING",)


@pytest.mark.parametrize(
    ("boundary", "expected_binding"),
    (
        ("company", "company_remaining"),
        ("cluster_loss", "cluster:company:cluster_company"),
        ("aggregate_loss", "aggregate_risk_remaining"),
    ),
)
def test_stage5c_existing_exposure_at_hard_cap_leaves_zero_new_risk(
    repository_root: Path,
    boundary: str,
    expected_binding: str,
) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = _buy_raw(repository_root)
    if boundary == "company":
        account = _sell_account(raw)
    elif boundary == "cluster_loss":
        base = _buy_account()
        exposures = tuple(
            replace(exposure, planned_loss="1500")
            if exposure.cluster_type is RiskClusterType.COMPANY
            else exposure
            for exposure in base.risk_cluster_exposures
        )
        account = bind_stage5c_artifact(replace(base, risk_cluster_exposures=exposures))
    else:
        account = bind_stage5c_artifact(replace(_buy_account(), aggregate_open_planned_loss="4000"))

    risk = evaluate_stage5_portfolio_target(
        raw,
        account,
        _clusters(),
        _regime(MarketRegime.NORMAL),
        _stress(),
        _sizing(raw),
        stage5b_support._identity(f"target_{boundary}_boundary", as_of=stage5b_support.APPROVED_AT),
        portfolio_rules,
    )

    assert risk.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
    assert risk.target is not None
    assert risk.target.target_quantity == 0
    assert expected_binding in risk.target.binding_constraint_ids


def test_stage5c_stopped_state_never_recovers_automatically(
    repository_root: Path,
) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = stage5b_support._case(repository_root)
    stopped_without_record = bind_stage5c_artifact(replace(_buy_account(), prior_stopped=True))

    blocked = evaluate_stage5_portfolio_target(
        raw,
        stopped_without_record,
        _clusters(),
        _regime(MarketRegime.NORMAL),
        _stress(),
        _sizing(raw),
        stage5b_support._identity("target_stopped_no_recovery", as_of=stage5b_support.APPROVED_AT),
        portfolio_rules,
    )
    assert blocked.target is not None
    assert blocked.target.target_quantity == 0
    assert blocked.reason_codes == ("STOPPED_STATE_RECOVERY_RECORD_MISSING",)


@pytest.mark.parametrize("scenario_return", ("-0.05", "-0.10", "0"))
def test_stage5c_stress_loss_floor_is_ten_percent(
    repository_root: Path,
    scenario_return: str,
) -> None:
    _, portfolio_rules = _rules(repository_root)
    raw = stage5b_support._case(repository_root)
    stress = bind_stage5c_artifact(replace(_stress(), scenario_return=scenario_return))

    risk = evaluate_stage5_portfolio_target(
        raw,
        _buy_account(),
        _clusters(),
        _regime(MarketRegime.NORMAL),
        stress,
        _sizing(raw),
        stage5b_support._identity(
            f"target_stress_{scenario_return.replace('-', 'm').replace('.', '_')}",
            as_of=stage5b_support.APPROVED_AT,
        ),
        portfolio_rules,
    )

    assert risk.target is not None
    assert risk.target.stress_loss_rate == "0.1"
    assert risk.target.target_quantity == 600


def test_stage5c_ledger_idempotency_and_conflict(repository_root: Path) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    assert result.ledger_replay is not None
    opening = result.ledger_replay.accepted_events[0]

    duplicate = replay_stage5c_ledger((opening, opening))
    assert duplicate.status is LedgerReplayStatus.RECONCILED
    assert len(duplicate.accepted_events) == 1

    conflict = bind_ledger_event(
        replace(
            opening,
            ledger_event_id="ledger_opening_conflict",
            source_object_ids=("different_source",),
            declared_canonical_hash=ZERO,
        )
    )
    blocked = replay_stage5c_ledger((opening, conflict))
    assert blocked.status is LedgerReplayStatus.PRECHECK_BLOCKED
    assert blocked.reason_codes == ("IDEMPOTENCY_KEY_CONTENT_CONFLICT",)


def test_stage5c_ledger_rejects_early_cash_release_and_5d_events(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    assert result.ledger_replay is not None
    opening = result.ledger_replay.accepted_events[0]
    release = next(
        event
        for event in result.ledger_replay.accepted_events
        if event.event_type is LedgerEventType.CASH_RELEASE
    )

    early = replay_stage5c_ledger((opening, release))
    assert early.status is LedgerReplayStatus.RECONCILIATION_BLOCKED
    assert early.reason_codes == ("NEGATIVE_CASH_RESERVATION_RECEIVABLE_OR_PAYABLE",)

    mark = bind_ledger_event(
        LedgerEvent(
            ledger_event_id="ledger_mark_stage5d_forbidden",
            idempotency_key="idem_mark_stage5d_forbidden",
            event_type=LedgerEventType.MARK_TO_MARKET,
            event_type_priority=STAGE5C_LEDGER_PRIORITY[LedgerEventType.MARK_TO_MARKET],
            strategy_id=opening.strategy_id,
            account_fixture_id=opening.account_fixture_id,
            security_id="600000.SH",
            effective_at=opening.effective_at + timedelta(seconds=1),
            trade_date=None,
            settlement_date=None,
            source_object_ids=("mark_fixture",),
            source_hashes=(ZERO,),
            postings=(),
            lot_effects=(),
            rule_ids=opening.rule_ids,
            rule_versions=opening.rule_versions,
            rule_hashes=opening.rule_hashes,
            supersedes_or_reversal_of=None,
            declared_canonical_hash=ZERO,
        )
    )
    forbidden = replay_stage5c_ledger((opening, mark))
    assert forbidden.status is LedgerReplayStatus.PRECHECK_BLOCKED
    assert forbidden.reason_codes == ("STAGE5D_EVENT_NOT_IMPLEMENTED:MARK_TO_MARKET",)


def test_stage5c_ledger_requires_balanced_postings(repository_root: Path) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    assert result.ledger_replay is not None
    opening = result.ledger_replay.accepted_events[0]
    reservation = next(
        event
        for event in result.ledger_replay.accepted_events
        if event.event_type is LedgerEventType.CASH_RESERVATION
    )
    bad_postings = (
        reservation.postings[0],
        LedgerPosting(
            LedgerAccountCode.CASH_AVAILABLE,
            "CNY",
            "0",
            "1",
        ),
    )
    unbalanced = bind_ledger_event(
        replace(
            reservation,
            ledger_event_id="ledger_unbalanced_reservation",
            idempotency_key="idem_unbalanced_reservation",
            postings=bad_postings,
            declared_canonical_hash=ZERO,
        )
    )

    blocked = replay_stage5c_ledger((opening, unbalanced))
    assert blocked.status is LedgerReplayStatus.RECONCILIATION_BLOCKED
    assert blocked.reason_codes == ("DOUBLE_ENTRY_IMBALANCE",)


def test_stage5c_ledger_correction_requires_reversal_then_replacement(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    assert result.ledger_replay is not None
    opening = result.ledger_replay.accepted_events[0]
    reservation = next(
        event
        for event in result.ledger_replay.accepted_events
        if event.event_type is LedgerEventType.CASH_RESERVATION
    )
    reversal = bind_ledger_event(
        LedgerEvent(
            ledger_event_id="ledger_reversal_reservation",
            idempotency_key="idem_reversal_reservation",
            event_type=LedgerEventType.REVERSAL,
            event_type_priority=STAGE5C_LEDGER_PRIORITY[LedgerEventType.REVERSAL],
            strategy_id=reservation.strategy_id,
            account_fixture_id=reservation.account_fixture_id,
            security_id=reservation.security_id,
            effective_at=reservation.effective_at + timedelta(seconds=1),
            trade_date=reservation.trade_date,
            settlement_date=reservation.settlement_date,
            source_object_ids=reservation.source_object_ids,
            source_hashes=reservation.source_hashes,
            postings=tuple(
                LedgerPosting(
                    posting.account,
                    posting.currency_or_security,
                    posting.credit,
                    posting.debit,
                )
                for posting in reservation.postings
            ),
            lot_effects=(),
            rule_ids=reservation.rule_ids,
            rule_versions=reservation.rule_versions,
            rule_hashes=reservation.rule_hashes,
            supersedes_or_reversal_of=reservation.ledger_event_id,
            declared_canonical_hash=ZERO,
        )
    )
    replacement = bind_ledger_event(
        LedgerEvent(
            ledger_event_id="ledger_replacement_reservation",
            idempotency_key="idem_replacement_reservation",
            event_type=LedgerEventType.REPLACEMENT,
            event_type_priority=STAGE5C_LEDGER_PRIORITY[LedgerEventType.REPLACEMENT],
            strategy_id=reservation.strategy_id,
            account_fixture_id=reservation.account_fixture_id,
            security_id=reservation.security_id,
            effective_at=reservation.effective_at + timedelta(seconds=2),
            trade_date=reservation.trade_date,
            settlement_date=reservation.settlement_date,
            source_object_ids=reservation.source_object_ids,
            source_hashes=reservation.source_hashes,
            postings=reservation.postings,
            lot_effects=(),
            rule_ids=reservation.rule_ids,
            rule_versions=reservation.rule_versions,
            rule_hashes=reservation.rule_hashes,
            supersedes_or_reversal_of=reversal.ledger_event_id,
            declared_canonical_hash=ZERO,
        )
    )

    replay = replay_stage5c_ledger((opening, reservation, reversal, replacement))

    assert replay.status is LedgerReplayStatus.RECONCILED
    assert replay.derived_state is not None
    assert Decimal(replay.derived_state.reserved_cash) > 0


def test_stage5c_requires_exact_settlement_terms_for_selected_rule(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    wrong_terms = bind_stage5c_artifact(
        replace(
            case.settlement_terms[0],
            market_rule_hash=HashDigest(algorithm="sha256", value="a" * 64),
        )
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, settlement_terms=(wrong_terms,)),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.ABSTAIN
    assert result.reason_codes == ("EXACT_SETTLEMENT_TERMS_MISSING_OR_AMBIGUOUS",)


def test_stage5c_rejects_settlement_cycle_not_derived_from_calendar(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    terms = case.settlement_terms[0]
    invalid_moments = tuple(
        replace(
            moment,
            local_trade_date="2025-01-20",
            effective_at=datetime(2025, 1, 20, 2, 31, tzinfo=UTC),
        )
        if moment.kind is SettlementMomentKind.SECURITY_SETTLEMENT
        else moment
        for moment in terms.moments
    )
    invalid_terms = bind_stage5c_artifact(replace(terms, moments=invalid_moments))

    result = evaluate_stage5_portfolio_ledger(
        replace(case, settlement_terms=(invalid_terms,)),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.RECONCILIATION_BLOCKED
    assert result.reason_codes == ("SETTLEMENT_CYCLE_OR_AVAILABILITY_MISMATCH",)


def test_stage5c_rejects_settlement_terms_not_known_at_fill_time(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    terms = case.settlement_terms[0]
    future = datetime(2025, 1, 22, tzinfo=UTC)
    future_identity = replace(
        terms.identity,
        as_of=future,
        knowledge_cutoff=future,
        declared_content_hash=ZERO,
    )
    future_terms = bind_stage5c_artifact(replace(terms, identity=future_identity))

    result = evaluate_stage5_portfolio_ledger(
        replace(case, settlement_terms=(future_terms,)),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.RECONCILIATION_BLOCKED
    assert result.reason_codes == ("SETTLEMENT_TERMS_NOT_PIT_AVAILABLE",)
