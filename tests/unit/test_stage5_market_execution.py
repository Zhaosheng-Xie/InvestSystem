from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import GateOutcome, HashDigest
from invest_system.strategies.industrial_event import (
    ApprovedStage5MarketExecutionRules,
    CostSchedule,
    ImpactCurve,
    ImpactNode,
    MarketDataQuality,
    MarketObservation,
    MarketObservationSet,
    MarketRuleImplementationState,
    MarketRuleSet,
    ProposalReferencePrice,
    SecuritySessionState,
    Stage4CompleteResult,
    Stage4CompleteSyntheticCase,
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    Stage5MarketExecutionCase,
    SyntheticApprovalFixture,
    TimingPrecision,
    TradeSide,
    TradingCalendar,
    TradingSession,
    VersionedArtifactIdentity,
    bind_stage4_valuation_set,
    bind_stage5_artifact,
    bind_synthetic_holding_snapshot,
    evaluate_complete_stage4,
    evaluate_stage5_market_execution,
    require_stage5_rule_capability,
    stage5_market_execution_replay_sha256,
)
from unit import test_stage4_complete_engine as stage4_support

ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)
SOURCE_HASH = HashDigest(algorithm="sha256", value="1" * 64)
CONFIG_HASH = HashDigest(algorithm="sha256", value="2" * 64)
PUBLISHED = datetime(2024, 12, 1, tzinfo=UTC)
EFFECTIVE = datetime(2025, 1, 1, tzinfo=UTC)
PROCESSING = datetime(2025, 1, 17, 1, 0, tzinfo=UTC)
PROPOSAL_AT = datetime(2025, 1, 17, 1, 30, tzinfo=UTC)
APPROVED_AT = datetime(2025, 1, 17, 2, 0, tzinfo=UTC)


def _one(repository_root: Path, filename: str) -> Path:
    matches = tuple(repository_root.rglob(filename))
    assert len(matches) == 1
    return matches[0]


def _approved_rules(repository_root: Path) -> ApprovedStage5MarketExecutionRules:
    bundle = rule_bundle_document_from_json_value(
        json.loads(
            _one(
                repository_root,
                "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.rule-bundle.json",
            ).read_text(encoding="utf-8")
        )
    )
    approval = rule_approval_record_from_json_value(
        json.loads(
            _one(
                repository_root,
                "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.approval.json",
            ).read_text(encoding="utf-8")
        )
    )
    capability = require_stage5_rule_capability(
        bundle,
        registry=RuleApprovalRegistry((approval,)),
    )
    return ApprovedStage5MarketExecutionRules.from_approved_bundle(bundle, capability)


def _identity(artifact_id: str, *, as_of: datetime = EFFECTIVE) -> VersionedArtifactIdentity:
    return VersionedArtifactIdentity(
        artifact_id=artifact_id,
        version="0.1.0",
        as_of=as_of,
        knowledge_cutoff=as_of,
        supersedes_artifact_id=None,
        declared_content_hash=ZERO_HASH,
    )


def _stage4(
    repository_root: Path,
) -> tuple[Stage4CompleteSyntheticCase, Stage4CompleteResult]:
    base = stage4_support._case()
    assert base.valuation_set.scenario_equity_values is not None
    scenarios = replace(
        base.valuation_set.scenario_equity_values,
        base=replace(base.valuation_set.scenario_equity_values.base, lower="1600", upper="1700"),
        downside=replace(
            base.valuation_set.scenario_equity_values.downside,
            lower="700",
            upper="750",
        ),
        upside=replace(
            base.valuation_set.scenario_equity_values.upside,
            lower="1800",
            upper="1900",
        ),
        stress=replace(
            base.valuation_set.scenario_equity_values.stress,
            lower="600",
            upper="650",
        ),
    )
    valuation = bind_stage4_valuation_set(
        replace(base.valuation_set, scenario_equity_values=scenarios)
    )
    assert base.exit_input.holding_snapshot is not None
    holding = bind_synthetic_holding_snapshot(
        replace(
            base.exit_input.holding_snapshot,
            established_valuation_hash=valuation.identity.declared_content_hash,
        )
    )
    case = replace(
        base,
        valuation_set=valuation,
        exit_input=replace(base.exit_input, holding_snapshot=holding),
    )
    result = evaluate_complete_stage4(case, stage4_support._capabilities(repository_root))
    assert result.overall_outcome is GateOutcome.PASS
    return case, result


def _session(day: int, *, suffix: str = "a") -> TradingSession:
    return TradingSession(
        session_id=f"session_202501{day:02d}_{suffix}",
        local_trade_date=f"2025-01-{day:02d}",
        session_kind="continuous_auction",
        opens_at=datetime(2025, 1, day, 2, 10, tzinfo=UTC),
        closes_at=datetime(2025, 1, day, 7, 0, tzinfo=UTC),
    )


def _rule(**overrides: object) -> MarketRuleSet:
    values: dict[str, object] = {
        "identity": _identity("market_rule_sse_main_standard"),
        "venue": "SSE",
        "board": "MAIN",
        "security_type": "EQUITY",
        "risk_label_scope": "STANDARD",
        "published_at": PUBLISHED,
        "effective_from": EFFECTIVE,
        "effective_to": None,
        "source_document_ids": ("sse_trading_rule_fixture",),
        "source_byte_hashes": (SOURCE_HASH,),
        "rule_clause_refs": ("fixture_clause_1",),
        "implementation_state": MarketRuleImplementationState.EFFECTIVE,
        "allowed_session_kinds": ("continuous_auction",),
        "order_types": ("LIMIT",),
        "price_tick": "0.01",
        "lower_price_limit": "7",
        "upper_price_limit": "11",
        "buy_lot_size": 100,
        "sell_lot_size": 100,
        "allow_odd_lot_sell": True,
        "same_day_sellable": False,
        "settlement_cycle_days": 1,
        "suspension_resume_rule": "synthetic_fixture_rule",
        "ex_rights_ex_dividend_rule": "explicit_unadjusted_price",
    }
    values.update(overrides)
    return bind_stage5_artifact(MarketRuleSet(**values))  # type: ignore[arg-type]


def _calendar(sessions: tuple[TradingSession, ...]) -> TradingCalendar:
    return bind_stage5_artifact(
        TradingCalendar(
            identity=_identity("sse_calendar_2025"),
            venue="SSE",
            market_timezone="Asia/Shanghai",
            published_at=PUBLISHED,
            effective_from=EFFECTIVE,
            effective_to=None,
            source_document_ids=("sse_calendar_fixture",),
            source_byte_hashes=(SOURCE_HASH,),
            sessions=sessions,
        )
    )


def _state(session: TradingSession, **overrides: object) -> SecuritySessionState:
    values: dict[str, object] = {
        "identity": _identity(f"state_{session.session_id}", as_of=session.opens_at),
        "security_id": "600000.SH",
        "session_id": session.session_id,
        "listed_and_eligible": True,
        "suspended": False,
        "one_price_limit_up": False,
        "one_price_limit_down": False,
        "verified_opposing_liquidity": True,
        "quote_legal_and_provable": True,
    }
    values.update(overrides)
    return bind_stage5_artifact(SecuritySessionState(**values))  # type: ignore[arg-type]


def _observation(
    session: TradingSession,
    *,
    benchmark: str = "8",
    volume: int = 10_000,
    quality: MarketDataQuality = MarketDataQuality.MINUTE,
) -> MarketObservation:
    start = session.opens_at.replace(minute=30)
    end = start.replace(minute=31)
    turnover = str(int(benchmark) * volume) if quality is MarketDataQuality.DAILY else "80000"
    if quality is MarketDataQuality.DAILY:
        start = session.opens_at
        end = session.closes_at
    return MarketObservation(
        observation_id=f"observation_{session.session_id}",
        session_id=session.session_id,
        data_quality=quality,
        window_start=start,
        window_end=end,
        available_at=end,
        volume=volume,
        turnover=turnover,
        benchmark_price=benchmark,
    )


def _observations(values: tuple[MarketObservation, ...]) -> MarketObservationSet:
    return bind_stage5_artifact(
        MarketObservationSet(
            identity=_identity("market_observation_set", as_of=values[-1].window_end),
            security_id="600000.SH",
            observations=values,
        )
    )


def _cost(**overrides: object) -> CostSchedule:
    values: dict[str, object] = {
        "identity": _identity("cost_sse_buy_standard"),
        "venue": "SSE",
        "security_type": "EQUITY",
        "side": TradeSide.BUY,
        "account_fee_version": "synthetic_fee_v1",
        "published_at": PUBLISHED,
        "effective_from": EFFECTIVE,
        "effective_to": None,
        "exchange_fee_rate": "0.0001",
        "regulatory_fee_rate": "0.00002",
        "transfer_fee_rate": "0.00001",
        "tax_rate": "0",
        "broker_commission_rate": "0.0003",
        "broker_minimum_commission": "5",
        "rounding_unit": "0.01",
        "currency": "CNY",
        "source_document_ids": ("cost_schedule_fixture",),
        "source_byte_hashes": (SOURCE_HASH,),
    }
    values.update(overrides)
    return bind_stage5_artifact(CostSchedule(**values))  # type: ignore[arg-type]


def _impact(**overrides: object) -> ImpactCurve:
    values: dict[str, object] = {
        "identity": _identity("impact_sse_buy_minute"),
        "venue": "SSE",
        "security_type": "EQUITY",
        "side": TradeSide.BUY,
        "data_quality": MarketDataQuality.MINUTE,
        "published_at": PUBLISHED,
        "effective_from": EFFECTIVE,
        "effective_to": None,
        "nodes": (ImpactNode("0", "0"), ImpactNode("0.05", "0.01")),
        "source_document_ids": ("impact_curve_fixture",),
        "source_byte_hashes": (SOURCE_HASH,),
    }
    values.update(overrides)
    return bind_stage5_artifact(ImpactCurve(**values))  # type: ignore[arg-type]


def _proposal() -> ProposalReferencePrice:
    return bind_stage5_artifact(
        ProposalReferencePrice(
            identity=_identity("proposal_reference_price", as_of=PROPOSAL_AT),
            security_id="600000.SH",
            observed_at=PROPOSAL_AT,
            price="8",
            source_fixture_ref="proposal_price_fixture",
        )
    )


def _approval(proposal: ProposalReferencePrice, **overrides: object) -> SyntheticApprovalFixture:
    values: dict[str, object] = {
        "identity": _identity("synthetic_approval", as_of=APPROVED_AT),
        "case_id": stage4_support.CASE_ID,
        "security_id": "600000.SH",
        "account_fixture_id": "anonymous_account_001",
        "action_intent": Stage5ActionIntent.ENTER,
        "approved_at": APPROVED_AT,
        "expires_at": datetime(2025, 1, 31, tzinfo=UTC),
        "approved_quantity": 1_000,
        "approved_notional_cap": "10000",
        "proposal_reference_price_hash": proposal.identity.declared_content_hash,
    }
    values.update(overrides)
    return bind_stage5_artifact(SyntheticApprovalFixture(**values))  # type: ignore[arg-type]


def _case(
    repository_root: Path,
    *,
    sessions: tuple[TradingSession, ...] | None = None,
    states: tuple[SecuritySessionState, ...] | None = None,
    observations: tuple[MarketObservation, ...] | None = None,
    market_rules: tuple[MarketRuleSet, ...] | None = None,
    costs: tuple[CostSchedule, ...] | None = None,
    impacts: tuple[ImpactCurve, ...] | None = None,
    timing_precision: TimingPrecision = TimingPrecision.EXACT,
    approval_overrides: dict[str, object] | None = None,
) -> Stage5MarketExecutionCase:
    stage4_case, stage4_result = _stage4(repository_root)
    actual_sessions = sessions or (_session(20),)
    actual_states = states or tuple(_state(item) for item in actual_sessions)
    actual_observations = observations or tuple(_observation(item) for item in actual_sessions)
    proposal = _proposal()
    approval = _approval(proposal, **(approval_overrides or {}))
    return Stage5MarketExecutionCase(
        case_id=stage4_support.CASE_ID,
        strategy_id="industrial_bottleneck_event",
        security_id="600000.SH",
        account_fixture_id="anonymous_account_001",
        venue="SSE",
        board="MAIN",
        security_type="EQUITY",
        risk_label="STANDARD",
        account_fee_version="synthetic_fee_v1",
        action_intent=Stage5ActionIntent.ENTER,
        knowledge_cutoff=stage4_case.knowledge_cutoff,
        decision_at=stage4_case.context_case.context.decision_at,
        strategy_processing_completed_at=PROCESSING,
        timing_precision=timing_precision,
        decision_local_trade_date="2025-01-17",
        stage4_case=stage4_case,
        stage4_complete_result=stage4_result,
        stage4_replay_hash=stage4_result.replay_hash,
        proposal_reference_price=proposal,
        proposed_quantity=1_200,
        synthetic_approval_fixture=approval,
        market_rule_sets=market_rules or (_rule(),),
        trading_calendar=_calendar(actual_sessions),
        security_session_states=actual_states,
        market_observation_set=_observations(actual_observations),
        cost_schedules=costs if costs is not None else (_cost(),),
        impact_curves=impacts if impacts is not None else (_impact(),),
        add_reunderwriting_ref=None,
        risk_exit_mandate_ref=None,
        code_commit="synthetic-stage5b-test",
        config_hash=CONFIG_HASH,
        injected_clock=datetime(2025, 2, 1, tzinfo=UTC),
    )


def test_stage5b_first_executable_window_creates_deterministic_partial_fill(
    repository_root: Path,
) -> None:
    rules = _approved_rules(repository_root)
    case = _case(repository_root)

    first = evaluate_stage5_market_execution(case, rules)
    second = evaluate_stage5_market_execution(case, rules)

    assert first == second
    assert first.status is Stage5ExecutionStatus.PARTIALLY_FILLED
    assert first.fill is not None
    assert first.order_intent is not None
    assert first.fill.quantity == 500
    assert first.fill.benchmark_vwap == "8"
    assert first.fill.adverse_slippage_rate == "0.01"
    assert first.fill.fill_price == "8.08"
    assert first.fill.gross_notional == "4040"
    assert first.cancelled_quantity == 500
    assert first.attempts[-1].capacity_quantity == 500
    assert first.attempts[-1].gate_recheck is not None
    assert first.attempts[-1].gate_recheck.current_gate3_outcome is GateOutcome.PASS
    assert first.attempts[-1].gate_recheck.current_gate4_outcome is GateOutcome.PASS
    assert [item.event_type.value for item in first.events] == [
        "SIMULATED_SUBMITTED",
        "SYNTHETIC_FILL",
        "CANCELLED",
    ]
    assert first.replay_hash.value == stage5_market_execution_replay_sha256(case, first)
    assert first.synthetic and first.validation_only
    assert not first.persists_state
    assert not first.authorizes_backtest
    assert not first.authorizes_paper
    assert not first.authorizes_shadow
    assert not first.authorizes_live
    assert not first.authorizes_positions
    assert not first.authorizes_orders
    assert not first.connects_broker


def test_stage5b_full_fill_at_or_below_capacity(repository_root: Path) -> None:
    case = _case(
        repository_root,
        approval_overrides={"approved_quantity": 400},
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.fill is not None and result.fill.quantity == 400
    assert result.cancelled_quantity == 0
    assert [item.event_type.value for item in result.events] == [
        "SIMULATED_SUBMITTED",
        "SYNTHETIC_FILL",
    ]


def test_stage5b_skips_non_executable_window_without_hindsight_price_choice(
    repository_root: Path,
) -> None:
    first = _session(20)
    second = _session(21)
    case = _case(
        repository_root,
        sessions=(first, second),
        states=(_state(first, one_price_limit_up=True), _state(second)),
        observations=(_observation(first), _observation(second)),
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.PARTIALLY_FILLED
    assert result.fill is not None
    assert result.fill.observation_id == f"observation_{second.session_id}"
    assert result.attempts[0].reason_codes == ("ONE_PRICE_LIMIT_UP_BUY",)
    assert result.attempts[1].attempt_day == 2


def test_stage5b_market_rule_overlap_fails_closed(repository_root: Path) -> None:
    first = _rule()
    second = _rule(
        identity=_identity("market_rule_overlap"),
        effective_from=datetime(2025, 1, 10, tzinfo=UTC),
    )
    case = _case(repository_root, market_rules=(first, second))

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("MARKET_RULE_EFFECTIVE_INTERVAL_OVERLAP",)
    assert result.fill is None


def test_stage5b_market_rule_gap_fails_before_market_data_use(repository_root: Path) -> None:
    expired_rule = _rule(effective_to=datetime(2025, 1, 19, tzinfo=UTC))
    case = _case(repository_root, market_rules=(expired_rule,), observations=())

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("MARKET_RULE_EFFECTIVE_INTERVAL_GAP",)
    assert result.attempts[0].observation_id is None


def test_stage5b_missing_historical_cost_abstains(repository_root: Path) -> None:
    case = _case(repository_root, costs=())

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.ABSTAIN
    assert result.reason_codes == ("HISTORICAL_COST_SCHEDULE_MISSING",)
    assert result.order_intent is None
    assert result.fill is None


def test_stage5b_current_executable_price_reruns_gate3_and_gate4(
    repository_root: Path,
) -> None:
    session = _session(20)
    case = _case(
        repository_root,
        sessions=(session,),
        observations=(_observation(session, benchmark="10"),),
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.GATE_REJECTED_AT_EXECUTABLE_PRICE
    gate = result.attempts[-1].gate_recheck
    assert gate is not None
    assert gate.historical_gate3_outcome is GateOutcome.PASS
    assert gate.current_gate3_outcome is GateOutcome.REJECT
    assert gate.current_market_pricing_state is not None
    assert result.order_intent is None


def test_stage5b_entry_expires_only_after_three_inclusive_trade_dates(
    repository_root: Path,
) -> None:
    sessions = (_session(20), _session(21), _session(22))
    case = _case(
        repository_root,
        sessions=sessions,
        states=tuple(_state(item, suspended=True) for item in sessions),
        observations=tuple(_observation(item) for item in sessions),
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.ENTRY_EXPIRED
    assert result.reason_codes[0] == "ENTRY_UNFILLED_AFTER_DAY_THREE"
    assert [item.attempt_day for item in result.attempts] == [1, 2, 3]


def test_stage5b_date_only_input_moves_to_next_full_session(repository_root: Path) -> None:
    same_day = _session(17)
    next_day = _session(20)
    case = _case(
        repository_root,
        sessions=(same_day, next_day),
        states=(_state(same_day), _state(next_day)),
        observations=(_observation(same_day), _observation(next_day)),
        timing_precision=TimingPrecision.DATE_ONLY,
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.fill is not None
    assert result.fill.observation_id == f"observation_{next_day.session_id}"
    assert all(item.session_id != same_day.session_id for item in result.attempts)


def test_stage5b_daily_vwap_is_turnover_divided_by_volume(repository_root: Path) -> None:
    session = _session(20)
    daily = _observation(session, quality=MarketDataQuality.DAILY)
    daily_curve = _impact(
        identity=_identity("impact_sse_buy_daily"),
        data_quality=MarketDataQuality.DAILY,
    )
    case = _case(
        repository_root,
        sessions=(session,),
        observations=(daily,),
        impacts=(daily_curve,),
    )

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.PARTIALLY_FILLED
    assert result.fill is not None and result.fill.benchmark_vwap == "8"


def test_stage5b_content_hash_drift_blocks_before_execution(repository_root: Path) -> None:
    rule = replace(_rule(), identity=replace(_rule().identity, declared_content_hash=ZERO_HASH))
    case = _case(repository_root, market_rules=(rule,))

    result = evaluate_stage5_market_execution(case, _approved_rules(repository_root))

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes[0].startswith("ARTIFACT_HASH_DRIFT:")


def test_stage5b_rejects_non_monotonic_impact_curve() -> None:
    with pytest.raises(ValueError, match="monotonic"):
        ImpactCurve(
            identity=_identity("bad_impact"),
            venue="SSE",
            security_type="EQUITY",
            side=TradeSide.BUY,
            data_quality=MarketDataQuality.MINUTE,
            published_at=PUBLISHED,
            effective_from=EFFECTIVE,
            effective_to=None,
            nodes=(ImpactNode("0", "0.02"), ImpactNode("0.05", "0.01")),
            source_document_ids=("impact_curve_fixture",),
            source_byte_hashes=(SOURCE_HASH,),
        )
