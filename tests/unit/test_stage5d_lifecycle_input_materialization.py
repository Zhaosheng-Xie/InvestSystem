from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system.canonical import canonical_sha256
from invest_system.models import HashDigest, RunMode
from invest_system.strategies.industrial_event import stage5d_lifecycle_inputs
from invest_system.strategies.industrial_event.stage5_execution_contracts import (
    InitialLedgerSnapshot,
    MarketRegime,
    PortfolioApprovalDecision,
    SettlementAvailabilityTerms,
    SettlementMoment,
    SettlementMomentKind,
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
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    Stage5MarketExecutionCase,
    TradeSide,
    TradingSession,
    bind_stage5_artifact,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    Stage5PortfolioLedgerCase,
    evaluate_stage5_portfolio_ledger,
)
from invest_system.strategies.industrial_event.stage5_portfolio_risk import (
    evaluate_stage5_portfolio_target,
)
from invest_system.strategies.industrial_event.stage5d_lifecycle_inputs import (
    STAGE5D_LIFECYCLE_EXIT_ORIGIN,
    STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
    STAGE6C_V02_APPROVAL_ID,
    STAGE6C_V02_APPROVAL_RECORD_RAW_SHA256,
    STAGE6C_V02_APPROVED_BUNDLE_RAW_SHA256,
    STAGE6C_V02_SPECIFICATION_SHA256,
    Stage5DExitInputClosure,
    Stage5DLifecycleCalendar,
    Stage5DLifecycleMarkCoverage,
    Stage5DLifecycleMarkObservation,
    Stage5DLifecycleMarkSet,
    Stage5DLifecycleSession,
    Stage5DNormalLifecycleMaterializedInputs,
    Stage5DValidationHorizonExitMandate,
    bind_stage5d_exit_input_closure,
    bind_stage5d_exit_mandate,
    bind_stage5d_lifecycle_calendar,
    bind_stage5d_lifecycle_mark,
    bind_stage5d_lifecycle_mark_coverage,
    bind_stage5d_lifecycle_mark_set,
    bind_stage5d_lifecycle_session,
    bind_stage5d_normal_lifecycle_inputs,
)
from unit import test_stage5_market_execution as stage5b_support
from unit import test_stage5_portfolio_ledger as stage5c_support

PREREGISTRATION_PATH = Path(
    "tests/fixtures/stage5d/normal-lifecycle-exit-replay-preregistration.v0.1.0.json"
)
PREREGISTRATION_RAW_SHA256 = "67f707e5e2f5cdfca4af45a71639ce91df222f7b5149125e654bfe9d1355a72b"
INPUT_LOCK_PATH = Path("tests/fixtures/stage5d/normal-lifecycle-exit-input-lock.v0.1.0.json")
INPUT_LOCK_RAW_SHA256 = "ba3b810be7a632ad1b909a7e0e0b942e0de9fb47010e9e3a5c80f77b60c6e8bc"
INPUT_CONTRACT_RAW_SHA256 = "ce7be6923eaa02c8e460437d577cbabf24fc73474d7ee2196c2d5cc03befff52"
INPUT_SET_ID = "stage5d_normal_lifecycle_inputs_001"
MANDATE_ID = "stage5d_validation_horizon_exit_mandate_001"
SECURITY_ID = "600000.SH"
ACCOUNT_ID = "anonymous_account_001"
STRATEGY_ID = "industrial_bottleneck_event"
ENTRY_FILL_ID = "synthetic_fill_b11033004c59d2aaef7256e0"
ENTRY_FILL_SHA256 = "18b198a25001a41dc9a566f236d37234469a8725edc9f2f63473bcdf372af020"
ENTRY_REPLAY_SHA256 = "f5ed17d1bf9944d35b7a5afa36e68df0fc40d12c277874ea01d02d1e0bd59225"
ENTRY_HEAD_SHA256 = "e375af373c99b84dac549ddbcb0d8b21ba861931aedeb8a6353c999991a3a836"
ENTRY_LOT_SHA256 = "5f24ef77c4594d4aef340c21fc3bed1144b3aaf26efa013386578fd528ce0233"
EXIT_DECISION_AT = datetime(2025, 4, 11, 2, 10, tzinfo=UTC)
EXIT_FILL_AT = datetime(2025, 4, 11, 2, 31, tzinfo=UTC)
SETTLEMENT_AT = datetime(2025, 4, 14, 2, 10, tzinfo=UTC)
AVAILABLE_AT = datetime(2025, 4, 14, 2, 11, tzinfo=UTC)
ZERO = HashDigest(algorithm="sha256", value="0" * 64)


def _digest(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _weekdays() -> tuple[date, ...]:
    values: list[date] = []
    current = date(2025, 1, 20)
    while len(values) < 60:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return tuple(values)


def _at(day: date, value: time) -> datetime:
    return datetime.combine(day, value, tzinfo=UTC)


def _lifecycle_calendar() -> Stage5DLifecycleCalendar:
    sessions = tuple(
        bind_stage5d_lifecycle_session(
            Stage5DLifecycleSession(
                schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
                ordinal=ordinal,
                session_id=f"synthetic_session_{ordinal:03d}",
                local_trade_date=day.isoformat(),
                opens_at=_at(day, time(2, 10)),
                closes_at=_at(day, time(7, 0)),
                valuation_at=_at(day, time(7, 1)),
                session_hash=ZERO,
            )
        )
        for ordinal, day in enumerate(_weekdays(), start=1)
    )
    return bind_stage5d_lifecycle_calendar(
        Stage5DLifecycleCalendar(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            calendar_id="synthetic_weekday_sessions_20250120_60_v0_1",
            sessions=sessions,
            construction_rule="FIRST_60_MONDAY_TO_FRIDAY_DATES_FROM_2025_01_20_INCLUSIVE",
            synthetic=True,
            validation_only=True,
            not_a_real_exchange_calendar=True,
            usable_for_formal_execution=False,
            calendar_hash=ZERO,
        )
    )


def _mark_inputs(
    calendar: Stage5DLifecycleCalendar,
    market_rule_hash: HashDigest,
) -> tuple[Stage5DLifecycleMarkSet, Stage5DLifecycleMarkCoverage]:
    marks: list[Stage5DLifecycleMarkObservation] = []
    for session in calendar.sessions[:59]:
        source_id = f"synthetic_flat_mark_source_{session.ordinal:03d}"
        marks.append(
            bind_stage5d_lifecycle_mark(
                Stage5DLifecycleMarkObservation(
                    schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
                    ordinal=session.ordinal,
                    mark_id=f"synthetic_mark:session_{session.ordinal:03d}",
                    session_id=session.session_id,
                    session_hash=session.session_hash,
                    security_id=SECURITY_ID,
                    price="8",
                    currency="CNY",
                    observed_at=session.closes_at,
                    available_at=session.valuation_at,
                    valuation_at=session.valuation_at,
                    source_id=source_id,
                    source_bytes_hash=_digest(
                        {
                            "source_id": source_id,
                            "session_id": session.session_id,
                            "price": "8",
                            "available_at": session.valuation_at,
                            "synthetic": True,
                        }
                    ),
                    market_rule_hash=market_rule_hash,
                    unadjusted=True,
                    executable=False,
                    synthetic=True,
                    validation_only=True,
                    mark_hash=ZERO,
                )
            )
        )
    mark_set = bind_stage5d_lifecycle_mark_set(
        Stage5DLifecycleMarkSet(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            mark_set_id="synthetic_full_exit_mark_set_001",
            security_id=SECURITY_ID,
            calendar_hash=calendar.calendar_hash,
            marks=tuple(marks),
            mark_set_hash=ZERO,
        )
    )
    coverage = bind_stage5d_lifecycle_mark_coverage(
        Stage5DLifecycleMarkCoverage(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            coverage_id="synthetic_full_exit_mark_coverage_001",
            security_id=SECURITY_ID,
            calendar_hash=calendar.calendar_hash,
            mark_set_hash=mark_set.mark_set_hash,
            expected_session_ordinals=tuple(range(1, 60)),
            observed_mark_ids=tuple(item.mark_id for item in mark_set.marks),
            complete=True,
            contains_future_mark=False,
            coverage_hash=ZERO,
        )
    )
    return mark_set, coverage


def _market_session(day: date, suffix: str) -> TradingSession:
    return TradingSession(
        session_id=f"session_{day.strftime('%Y%m%d')}_{suffix}",
        local_trade_date=day.isoformat(),
        session_kind="continuous_auction",
        opens_at=_at(day, time(2, 10)),
        closes_at=_at(day, time(7, 0)),
    )


def _market_exit_case(repository_root: Path) -> Stage5MarketExecutionCase:
    exit_session = _market_session(date(2025, 4, 11), "exit")
    tail_session = _market_session(date(2025, 4, 14), "tail")
    raw = stage5b_support._case(
        repository_root,
        sessions=(exit_session, tail_session),
        states=(stage5b_support._state(exit_session), stage5b_support._state(tail_session)),
        observations=(stage5b_support._observation(exit_session),),
        costs=(
            stage5b_support._cost(
                identity=stage5b_support._identity("cost_sse_full_exit_standard"),
                side=TradeSide.SELL,
                tax_rate="0.001",
            ),
        ),
        impacts=(
            stage5b_support._impact(
                identity=stage5b_support._identity("impact_sse_full_exit_minute"),
                side=TradeSide.SELL,
            ),
        ),
        approval_overrides={
            "identity": stage5b_support._identity(
                "synthetic_full_exit_approval",
                as_of=EXIT_DECISION_AT,
            ),
            "action_intent": Stage5ActionIntent.EXIT,
            "approved_at": EXIT_DECISION_AT,
            "expires_at": datetime(2025, 4, 14, 7, 0, tzinfo=UTC),
            "approved_quantity": 200,
        },
    )
    proposal_observed_at = datetime(2025, 4, 10, 7, 0, tzinfo=UTC)
    proposal = bind_stage5_artifact(
        replace(
            raw.proposal_reference_price,
            identity=stage5b_support._identity(
                "proposal_reference_price_full_exit",
                as_of=proposal_observed_at,
            ),
            observed_at=proposal_observed_at,
        )
    )
    approval = stage5b_support._approval(
        proposal,
        identity=stage5b_support._identity(
            "synthetic_full_exit_approval",
            as_of=EXIT_DECISION_AT,
        ),
        action_intent=Stage5ActionIntent.EXIT,
        approved_at=EXIT_DECISION_AT,
        expires_at=datetime(2025, 4, 14, 7, 0, tzinfo=UTC),
        approved_quantity=200,
    )
    return replace(
        raw,
        action_intent=Stage5ActionIntent.EXIT,
        strategy_processing_completed_at=datetime(2025, 4, 10, 6, 0, tzinfo=UTC),
        proposal_reference_price=proposal,
        proposed_quantity=200,
        synthetic_approval_fixture=approval,
        add_reunderwriting_ref=None,
        risk_exit_mandate_ref=MANDATE_ID,
        code_commit="synthetic-stage5d-full-exit-inputs",
        injected_clock=datetime(2025, 4, 15, tzinfo=UTC),
    )


def _exit_account(raw: Stage5MarketExecutionCase) -> SyntheticAccountSnapshot:
    market_rule_hash = raw.market_rule_sets[0].identity.declared_content_hash
    lot = SyntheticLotSnapshot(
        lot_id=f"stage5d_v2_lot:{ENTRY_FILL_ID}",
        security_id=raw.security_id,
        acquired_at=datetime(2025, 1, 20, 2, 31, tzinfo=UTC),
        quantity=200,
        sellable_quantity=200,
        full_cost="1613.23",
        governing_market_rule_hash=market_rule_hash,
    )
    position = SyntheticPositionSnapshot(
        security_id=raw.security_id,
        company_id="company_600000",
        market_value="1600",
        lots=(lot,),
    )
    return bind_stage5c_artifact(
        SyntheticAccountSnapshot(
            identity=stage5b_support._identity(
                "synthetic_full_exit_account_stage5c",
                as_of=EXIT_DECISION_AT,
            ),
            strategy_id=raw.strategy_id,
            account_fixture_id=raw.account_fixture_id,
            base_currency="CNY",
            settled_cash="98386.77",
            reserved_cash="0",
            available_cash="98386.77",
            unsettled_cash_receivable="0",
            unsettled_cash_payable="0",
            positions=(position,),
            net_asset_value="99986.77",
            adjusted_high_water_mark="99986.77",
            declared_drawdown="0",
            risk_cluster_exposures=stage5c_support._risk_exposures(
                market_value="1600",
                planned_loss="0",
            ),
            aggregate_open_planned_loss="0",
            prior_stopped=False,
            synthetic_recovery_record_hash=None,
            synthetic_recovery_approved=False,
        )
    )


def _settlement(raw: Stage5MarketExecutionCase) -> SettlementAvailabilityTerms:
    return bind_stage5c_artifact(
        SettlementAvailabilityTerms(
            identity=stage5b_support._identity(
                "settlement_terms_full_exit_stage5d",
                as_of=EXIT_DECISION_AT,
            ),
            venue=raw.venue,
            board=raw.board,
            security_type=raw.security_type,
            risk_label=raw.risk_label,
            trade_local_date="2025-04-11",
            market_rule_hash=raw.market_rule_sets[0].identity.declared_content_hash,
            moments=(
                SettlementMoment(
                    SettlementMomentKind.SECURITY_SETTLEMENT,
                    "2025-04-14",
                    SETTLEMENT_AT,
                ),
                SettlementMoment(
                    SettlementMomentKind.SECURITY_SELLABLE,
                    "2025-04-14",
                    SETTLEMENT_AT,
                ),
                SettlementMoment(
                    SettlementMomentKind.BUY_CASH_PAYABLE,
                    "2025-04-11",
                    EXIT_FILL_AT,
                ),
                SettlementMoment(
                    SettlementMomentKind.SELL_PROCEEDS_RECEIVABLE,
                    "2025-04-11",
                    EXIT_FILL_AT,
                ),
                SettlementMoment(
                    SettlementMomentKind.SELL_CASH_SETTLEMENT,
                    "2025-04-14",
                    SETTLEMENT_AT,
                ),
                SettlementMoment(
                    SettlementMomentKind.SELL_CASH_AVAILABLE,
                    "2025-04-14",
                    AVAILABLE_AT,
                ),
            ),
            source_document_ids=("synthetic_full_exit_settlement_fixture",),
            source_byte_hashes=(stage5b_support.SOURCE_HASH,),
            same_day_sellable=False,
            special_exception_id=None,
        )
    )


def _exit_stage5c_case(
    repository_root: Path,
) -> tuple[
    Stage5PortfolioLedgerCase,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
]:
    market_rules, portfolio_rules = stage5c_support._rules(repository_root)
    raw = _market_exit_case(repository_root)
    account = _exit_account(raw)
    clusters = stage5c_support._clusters()
    regime = stage5c_support._regime(MarketRegime.NORMAL)
    stress = stage5c_support._stress()
    sizing = stage5c_support._sizing(raw)
    target_identity = stage5b_support._identity(
        "portfolio_full_exit_target_stage5d",
        as_of=EXIT_DECISION_AT,
    )
    risk = evaluate_stage5_portfolio_target(
        raw,
        account,
        clusters,
        regime,
        stress,
        sizing,
        target_identity,
        portfolio_rules,
    )
    target = risk.target
    assert target is not None and target.target_quantity == 200
    approval = bind_stage5c_artifact(
        SyntheticPortfolioApproval(
            identity=stage5b_support._identity(
                "portfolio_full_exit_approval_stage5d",
                as_of=EXIT_DECISION_AT,
            ),
            case_id=raw.case_id,
            security_id=raw.security_id,
            account_fixture_id=raw.account_fixture_id,
            action_intent=raw.action_intent,
            decision=PortfolioApprovalDecision.APPROVED,
            target_hash=target.identity.declared_content_hash,
            portfolio_risk_evaluation_hash=_digest(risk),
            market_approval_hash=raw.synthetic_approval_fixture.identity.declared_content_hash,
            approved_at=raw.synthetic_approval_fixture.approved_at,
            expires_at=raw.synthetic_approval_fixture.expires_at,
            approved_quantity=200,
            approved_notional_cap="1600",
            approved_planned_loss_cap="0",
            reason_codes=("SYNTHETIC_VALIDATION_HORIZON_FULL_EXIT",),
        )
    )
    initial = bind_stage5c_artifact(
        InitialLedgerSnapshot(
            identity=stage5b_support._identity(
                "initial_ledger_full_exit_crosscheck_stage5d",
                as_of=EXIT_DECISION_AT,
            ),
            strategy_id=raw.strategy_id,
            account_fixture_id=raw.account_fixture_id,
            account_snapshot_hash=account.identity.declared_content_hash,
            expected_head_hash=HashDigest(
                algorithm="sha256",
                value=stage5c_initial_ledger_head_sha256(account.identity.declared_content_hash),
            ),
            head_observed_at=EXIT_FILL_AT,
            no_intervening_events_attested=True,
            prior_event_hashes=(),
        )
    )
    corporate_actions = bind_stage5c_artifact(
        SyntheticCorporateActionSet(
            identity=stage5b_support._identity(
                "corporate_actions_full_exit_stage5d",
                as_of=EXIT_DECISION_AT,
            ),
            security_id=raw.security_id,
            applicable_action_ids=(),
            explicitly_empty_for_stage5c=True,
        )
    )
    case = Stage5PortfolioLedgerCase(
        case_id=raw.case_id,
        market_execution_case=raw,
        synthetic_account_snapshot=account,
        risk_cluster_snapshot=clusters,
        market_regime_snapshot=regime,
        stress_scenario_input=stress,
        portfolio_sizing_inputs=sizing,
        synthetic_portfolio_approval=approval,
        initial_ledger_snapshot=initial,
        settlement_terms=(_settlement(raw),),
        corporate_action_set=corporate_actions,
        target_identity=target_identity,
        constraint_identity=stage5b_support._identity(
            "submission_constraint_full_exit_stage5d",
            as_of=EXIT_DECISION_AT,
        ),
        code_commit="synthetic-stage5d-full-exit-inputs",
        config_hash=stage5b_support.CONFIG_HASH,
        injected_clock=datetime(2025, 4, 15, tzinfo=UTC),
    )
    return case, market_rules, portfolio_rules


def _mandate() -> Stage5DValidationHorizonExitMandate:
    return bind_stage5d_exit_mandate(
        Stage5DValidationHorizonExitMandate(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            mandate_id=MANDATE_ID,
            candidate_id="synthetic_candidate_optical_contract_001",
            strategy_id=STRATEGY_ID,
            security_id=SECURITY_ID,
            account_fixture_id=ACCOUNT_ID,
            exit_origin=STAGE5D_LIFECYCLE_EXIT_ORIGIN,
            exit_session_ordinal=60,
            exit_decision_at=EXIT_DECISION_AT,
            full_exit_required=True,
            validates_stage4_exit_rule=False,
            stage6c_specification_hash=HashDigest(
                algorithm="sha256",
                value=STAGE6C_V02_SPECIFICATION_SHA256,
            ),
            stage6c_approved_bundle_raw_hash=HashDigest(
                algorithm="sha256",
                value=STAGE6C_V02_APPROVED_BUNDLE_RAW_SHA256,
            ),
            stage6c_approval_record_raw_hash=HashDigest(
                algorithm="sha256",
                value=STAGE6C_V02_APPROVAL_RECORD_RAW_SHA256,
            ),
            stage6c_approval_id=STAGE6C_V02_APPROVAL_ID,
            synthetic=True,
            validation_only=True,
            authority_eligible=False,
            mandate_hash=ZERO,
        )
    )


def _materialized_inputs(repository_root: Path) -> Stage5DNormalLifecycleMaterializedInputs:
    exit_case, _, _ = _exit_stage5c_case(repository_root)
    calendar = _lifecycle_calendar()
    market_rule_hash = exit_case.market_execution_case.market_rule_sets[
        0
    ].identity.declared_content_hash
    mark_set, coverage = _mark_inputs(calendar, market_rule_hash)
    mandate = _mandate()
    market_case = exit_case.market_execution_case
    closure = bind_stage5d_exit_input_closure(
        Stage5DExitInputClosure(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            closure_id="stage5d_full_exit_rule_closure_001",
            exit_stage5c_case_hash=_digest(exit_case),
            exit_mandate_hash=mandate.mandate_hash,
            stage5_market_rule_hashes=tuple(
                item.identity.declared_content_hash for item in market_case.market_rule_sets
            ),
            stage5_trading_calendar_hash=(
                market_case.trading_calendar.identity.declared_content_hash
            ),
            stage5_cost_schedule_hashes=tuple(
                item.identity.declared_content_hash for item in market_case.cost_schedules
            ),
            stage5_impact_curve_hashes=tuple(
                item.identity.declared_content_hash for item in market_case.impact_curves
            ),
            stage5_settlement_terms_hashes=tuple(
                item.identity.declared_content_hash for item in exit_case.settlement_terms
            ),
            synthetic=True,
            validation_only=True,
            closure_hash=ZERO,
        )
    )
    return bind_stage5d_normal_lifecycle_inputs(
        Stage5DNormalLifecycleMaterializedInputs(
            schema_version=STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION,
            input_set_id=INPUT_SET_ID,
            preregistration_raw_hash=HashDigest(
                algorithm="sha256",
                value=PREREGISTRATION_RAW_SHA256,
            ),
            entry_complete_replay_hash=HashDigest(
                algorithm="sha256",
                value=ENTRY_REPLAY_SHA256,
            ),
            entry_ending_journal_head_hash=HashDigest(
                algorithm="sha256",
                value=ENTRY_HEAD_SHA256,
            ),
            entry_derived_lot_hash=HashDigest(
                algorithm="sha256",
                value=ENTRY_LOT_SHA256,
            ),
            exit_stage5c_case=exit_case,
            lifecycle_calendar=calendar,
            mark_set=mark_set,
            mark_coverage=coverage,
            exit_mandate=mandate,
            exit_input_closure=closure,
            exit_account_snapshot_crosscheck_only=True,
            evaluator_implementation_authorized=False,
            run_mode=RunMode.RESEARCH,
            synthetic=True,
            validation_only=True,
            authority_eligible=False,
            persists_state=False,
            connects_broker=False,
            reads_kb_internal_state=False,
            writes_kb=False,
            input_set_hash=ZERO,
        )
    )


def test_materializes_exact_full_exit_stage5c_input_without_lifecycle_evaluator(
    repository_root: Path,
) -> None:
    inputs = _materialized_inputs(repository_root)
    case = inputs.exit_stage5c_case

    assert case.market_execution_case.action_intent is Stage5ActionIntent.EXIT
    assert case.market_execution_case.risk_exit_mandate_ref == MANDATE_ID
    assert case.synthetic_portfolio_approval.approved_quantity == 200
    assert case.synthetic_account_snapshot.positions[0].quantity == 200
    assert case.synthetic_account_snapshot.positions[0].sellable_quantity == 200
    assert case.synthetic_account_snapshot.positions[0].lots[0].full_cost == "1613.23"
    assert case.corporate_action_set.applicable_action_ids == ()
    assert inputs.exit_account_snapshot_crosscheck_only is True
    assert inputs.evaluator_implementation_authorized is False
    assert inputs.input_set_hash.value == canonical_sha256(
        {key: value for key, value in inputs.to_json_value().items() if key != "input_set_hash"}
    )


def test_existing_stage5c_evaluator_confirms_materialized_input_is_full_exit(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _exit_stage5c_case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.constrained_market_projection is not None
    fill = result.constrained_market_projection.market_execution_result.fill
    assert fill is not None
    assert fill.side is TradeSide.SELL
    assert fill.quantity == 200
    assert fill.benchmark_vwap == "8"
    assert fill.fill_price == "7.96"
    assert fill.gross_notional == "1592"
    assert fill.costs.total == "6.82"
    assert fill.cash_effect == "1585.18"
    assert result.ledger_replay is not None
    assert result.ledger_replay.derived_state is not None
    assert result.ledger_replay.derived_state.actual_quantity(SECURITY_ID) == 0


def test_materializes_exact_sixty_session_calendar_and_fifty_nine_pit_marks(
    repository_root: Path,
) -> None:
    inputs = _materialized_inputs(repository_root)
    calendar = inputs.lifecycle_calendar
    marks = inputs.mark_set.marks

    assert len(calendar.sessions) == 60
    assert calendar.sessions[0].local_trade_date == "2025-01-20"
    assert calendar.sessions[-1].local_trade_date == "2025-04-11"
    assert len(marks) == 59
    assert tuple(item.ordinal for item in marks) == tuple(range(1, 60))
    assert all(item.price == "8" and item.unadjusted and not item.executable for item in marks)
    assert all(item.observed_at < item.available_at == item.valuation_at for item in marks)
    assert inputs.mark_coverage.complete is True
    assert inputs.mark_coverage.contains_future_mark is False


def test_materialized_exit_mandate_and_rule_closure_are_exact(repository_root: Path) -> None:
    inputs = _materialized_inputs(repository_root)
    mandate = inputs.exit_mandate
    closure = inputs.exit_input_closure

    assert mandate.exit_origin == STAGE5D_LIFECYCLE_EXIT_ORIGIN
    assert mandate.exit_session_ordinal == 60
    assert mandate.full_exit_required is True
    assert mandate.validates_stage4_exit_rule is False
    assert mandate.stage6c_approval_id == STAGE6C_V02_APPROVAL_ID
    assert closure.exit_stage5c_case_hash.value == canonical_sha256(inputs.exit_stage5c_case)
    assert closure.exit_mandate_hash == mandate.mandate_hash
    assert closure.synthetic and closure.validation_only


@pytest.mark.parametrize(
    ("field_name", "value"),
    (
        ("evaluator_implementation_authorized", True),
        ("authority_eligible", True),
        ("persists_state", True),
        ("connects_broker", True),
        ("reads_kb_internal_state", True),
        ("writes_kb", True),
    ),
)
def test_materialized_inputs_reject_any_authority_or_evaluator_claim(
    repository_root: Path,
    field_name: str,
    value: bool,
) -> None:
    inputs = _materialized_inputs(repository_root)
    with pytest.raises(ValueError, match="authority boundary"):
        bind_stage5d_normal_lifecycle_inputs(
            replace(inputs, **{field_name: value})  # type: ignore[arg-type]
        )


def test_preregistration_bytes_remain_exact(repository_root: Path) -> None:
    assert sha256((repository_root / PREREGISTRATION_PATH).read_bytes()).hexdigest() == (
        PREREGISTRATION_RAW_SHA256
    )


def test_input_lock_closes_all_six_pre_evaluator_hashes(repository_root: Path) -> None:
    lock = _json(repository_root / INPUT_LOCK_PATH)
    inputs = _materialized_inputs(repository_root)
    hashes = lock["materialized_input_hashes"]
    assert isinstance(hashes, dict)

    assert sha256((repository_root / INPUT_LOCK_PATH).read_bytes()).hexdigest() == (
        INPUT_LOCK_RAW_SHA256
    )
    assert (
        sha256(
            (
                repository_root
                / "src/invest_system/strategies/industrial_event/stage5d_lifecycle_inputs.py"
            ).read_bytes()
        ).hexdigest()
        == INPUT_CONTRACT_RAW_SHA256
    )
    assert hashes == {
        "full_exit_stage5c_case_sha256": canonical_sha256(inputs.exit_stage5c_case),
        "synthetic_calendar_sha256": inputs.lifecycle_calendar.calendar_hash.value,
        "mark_observation_set_sha256": inputs.mark_set.mark_set_hash.value,
        "mark_coverage_set_sha256": inputs.mark_coverage.coverage_hash.value,
        "validation_horizon_exit_mandate_sha256": inputs.exit_mandate.mandate_hash.value,
        "exit_market_rule_cost_impact_settlement_closure_sha256": (
            inputs.exit_input_closure.closure_hash.value
        ),
        "input_set_sha256": inputs.input_set_hash.value,
    }
    assert lock["status"] == "MATERIALIZED_INPUTS_FROZEN_EVALUATOR_UNAUTHORIZED"
    assert lock["next_gate"] == "SEPARATE_OWNER_APPROVAL_REQUIRED_BEFORE_LIFECYCLE_EVALUATOR"


def test_input_lock_preserves_null_results_and_zero_authority(repository_root: Path) -> None:
    lock = _json(repository_root / INPUT_LOCK_PATH)
    derived = lock["implementation_derived_hashes"]
    boundary = lock["authorization_boundary"]
    preregistration = _json(repository_root / PREREGISTRATION_PATH)
    assert isinstance(derived, dict)
    assert isinstance(boundary, dict)
    preregistered_inputs = preregistration["required_pre_evaluator_input_hashes"]
    assert isinstance(preregistered_inputs, dict)

    assert all(value is None for value in derived.values())
    assert all(value is None for value in preregistered_inputs.values())
    assert all(value is False for value in boundary.values())
    assert not any(name.startswith("evaluate_") for name in stage5d_lifecycle_inputs.__all__)


def test_materialized_inputs_reject_calendar_mark_and_closure_drift(
    repository_root: Path,
) -> None:
    inputs = _materialized_inputs(repository_root)
    with pytest.raises(ValueError, match="exactly 60"):
        Stage5DLifecycleCalendar(
            **{
                **inputs.lifecycle_calendar.to_json_value(),
                "sessions": inputs.lifecycle_calendar.sessions[:-1],
            }
        )

    first = inputs.mark_set.marks[0]
    with pytest.raises(ValueError, match="PIT or valuation"):
        replace(first, available_at=first.valuation_at + timedelta(seconds=1))

    drifted_closure = bind_stage5d_exit_input_closure(
        replace(
            inputs.exit_input_closure,
            exit_stage5c_case_hash=HashDigest(algorithm="sha256", value="f" * 64),
            closure_hash=ZERO,
        )
    )
    with pytest.raises(ValueError, match="closure case hash"):
        bind_stage5d_normal_lifecycle_inputs(replace(inputs, exit_input_closure=drifted_closure))
