"""First source-driven Stage 5D Ledger V2 vertical slice."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import ApprovedRuleCapability, RuleApprovalRegistry
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5_governance import (
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ExecutionStatus,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    Stage5PortfolioLedgerCase,
)
from invest_system.strategies.industrial_event.stage5d_governance import (
    require_stage5d_rule_capability,
)
from invest_system.strategies.industrial_event.stage5d_ledger_v2 import (
    Stage5DV2Account,
    Stage5DV2CostComponents,
    Stage5DV2EventType,
    Stage5DV2OpeningLotAttribution,
    Stage5DV2ReplayStatus,
    bind_stage5d_v2_event,
    bind_stage5d_v2_opening_attribution,
    replay_stage5d_v2_slice,
)
from invest_system.strategies.industrial_event.stage5d_stage5c_adapter import (
    Stage5DSourceDrivenSliceResult,
    Stage5DSourceDrivenSliceStatus,
    evaluate_stage5d_source_driven_ledger_slice,
    stage5d_source_driven_slice_sha256,
)
from unit import test_stage5_portfolio_ledger as stage5c_support
from unit import test_stage5d_governance as stage5d_governance_support

BUY_RESULT_SHA256 = "7872330b5e3a93047e305ada37b07dc5aaa946ffbef40b6ca8c0e5dbc2cddc3f"
BUY_SLICE_REPLAY_SHA256 = "225b52cdab7f287524d33abd7c23c1ed2369d55847fee325554dcf97f120a836"
BUY_V2_REPLAY_SHA256 = "81ef794391c3f6c02983d51b0faca9b7398dd1070b1a6fa306fda296a0ec2fdf"
BUY_V2_EVENT_SHA256 = (
    "154e9904dc69fa21e251e4124d916102b658994d1c2c1f5d9cec8312a21bfb47",
    "c01ed072a5cc92b4d9780e78a13bdf816171f5e009915ba92b082f5a21701539",
    "e381e20c848f341d0ba3c41ba4462dad1b16137a85587422a4a47df1abe74053",
    "a1511909dc50caecd0317d66c3a4a61b59d883a632111015cac219bf8b397846",
    "d941623c338f83b1868bcbce452eea2d2ca96585e968183e0daf7c5843b39b61",
)
BUY_V2_HEAD_SHA256 = "a0239ae4fdb21201b898ab32f5cde27d7efbec3ff1fd42b331eae62d9adf0977"

NO_FILL_RESULT_SHA256 = "fbc4c42e0f9b414d338202e777d5733eede8a9cc7faa2cd6097771a146412586"
NO_FILL_SLICE_REPLAY_SHA256 = "43b0bdc621a15f03c4bf0db1865116e781c48b8f2fe7f11a3ad9db9cc477cc12"
NO_FILL_V2_REPLAY_SHA256 = "dd2a8af74839deb1c1e59747ffef145177979642f2c717c3d0655966ef2c7498"
NO_FILL_EVENT_SHA256 = "02da2c5027316625ca3dcf21e5a4e278364a25ccfdaef96ff95024cd6618d95f"
NO_FILL_HEAD_SHA256 = "e0d44ed259769c4fa930c3baf744c0410de03191b55f0875be6302ef448a75f4"

SELL_STAGE5C_RESULT_SHA256 = "12e92312a23c80311c65b0c26232fba552e8efcaffbb3ee32bb32cf59a045234"
SELL_RESULT_SHA256 = "ad539676296172c723807396890ca60d36681a068ab26f22436558caf4671cad"
SELL_SLICE_REPLAY_SHA256 = "89906353e52f05b373f4f0528facc4b6942bc32e36dcad40cd44721332ecbbd2"
SELL_BASIS_REPLAY_SHA256 = "45078a04d6b84c74eb38fb6bdbca3973831740e7140424c851846e8a4744749b"
SELL_V2_REPLAY_SHA256 = "41d8eda4d171268f099b94cdf138fd43674badc837ba371708000d282a1dfc18"
SELL_EVENT_SHA256 = (
    "b1c5d602d6b708479857d2bfd4e3a44ca53a7c731c1d95ea6fac96c6d073dfda",
    "2a6243bd2df7de1cf976e31b08f75dc5fa65251d1e008d1a6a6bd92b9a15fc69",
    "3ac7a71d0a336ad029ddef38fda68fb7fcfe89dc6458422c319e73f479da0037",
    "4e1cd6674e8734b55d1fdd6db0124495186b6f4542c4d852865e4faa202fdfa1",
    "35820477ed21e90640b14cd179a125ca037467910e361769959fbbf0584e5f1e",
    "e5d853daff274c06aabdcb353e33c8e7f46c2971812ec565f34eee10fcdd9058",
)
SELL_HEAD_SHA256 = "88b197c27ace0a2812d43eec69cdd6643c50b11b989c9bba45f77d65a4f38df5"


def _capability(repository_root: Path) -> ApprovedRuleCapability:
    document, approval = stage5d_governance_support._approved_artifacts(repository_root)
    return require_stage5d_rule_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )


def _evaluate(
    repository_root: Path,
    *,
    reject: bool = False,
    sell: bool = False,
) -> tuple[
    Stage5PortfolioLedgerCase,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
    Stage5DSourceDrivenSliceResult,
]:
    case, market_rules, portfolio_rules = stage5c_support._case(
        repository_root,
        reject=reject,
        sell=sell,
    )
    attributions = _sell_attributions(case) if sell else ()
    result = evaluate_stage5d_source_driven_ledger_slice(
        case,
        market_rules,
        portfolio_rules,
        _capability(repository_root),
        opening_attributions=attributions,
    )
    return case, market_rules, portfolio_rules, result


def _sell_attributions(
    case: Stage5PortfolioLedgerCase,
) -> tuple[Stage5DV2OpeningLotAttribution, ...]:
    component_values = {
        "opening_lot_001": ("680", "10", "0", "10", "0"),
        "opening_lot_002": ("1550", "20", "0", "30", "0"),
    }
    values: list[Stage5DV2OpeningLotAttribution] = []
    for position in case.synthetic_account_snapshot.positions:
        for lot in position.lots:
            components = Stage5DV2CostComponents(*component_values[lot.lot_id])
            values.append(
                bind_stage5d_v2_opening_attribution(
                    Stage5DV2OpeningLotAttribution(
                        attribution_id=f"stage5d_v2_attribution:{lot.lot_id}",
                        strategy_id=case.synthetic_account_snapshot.strategy_id,
                        account_fixture_id=case.synthetic_account_snapshot.account_fixture_id,
                        lot_id=lot.lot_id,
                        security_id=lot.security_id,
                        acquired_at=lot.acquired_at,
                        quantity=lot.quantity,
                        sellable_quantity=lot.sellable_quantity,
                        governing_market_rule_hash=lot.governing_market_rule_hash,
                        source_lot_hash=HashDigest(
                            algorithm="sha256",
                            value=canonical_sha256(lot),
                        ),
                        cost_components=components,
                        declared_content_hash=HashDigest(
                            algorithm="sha256",
                            value="0" * 64,
                        ),
                    )
                )
            )
    return tuple(values)


def test_source_driven_buy_recomputes_stage5c_and_replays_v2(
    repository_root: Path,
) -> None:
    case, _, _, result = _evaluate(repository_root)
    repeated = _evaluate(repository_root)[3]

    assert result.status is Stage5DSourceDrivenSliceStatus.BUY_RECONCILED
    assert result.stage5c_result.status is Stage5ExecutionStatus.FILLED
    assert canonical_sha256(result.stage5c_result) == (
        "daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59"
    )
    assert canonical_sha256(result) == BUY_RESULT_SHA256
    assert canonical_sha256(repeated) == BUY_RESULT_SHA256
    assert result.slice_replay_hash.value == BUY_SLICE_REPLAY_SHA256
    assert stage5d_source_driven_slice_sha256(case, result) == BUY_SLICE_REPLAY_SHA256

    replay = result.v2_replay
    assert replay is not None
    assert replay.status is Stage5DV2ReplayStatus.RECONCILED
    assert replay.replay_hash.value == BUY_V2_REPLAY_SHA256
    assert tuple(item.event_type for item in replay.accepted_events) == (
        Stage5DV2EventType.OPENING_BALANCE,
        Stage5DV2EventType.BUY_TRADE,
        Stage5DV2EventType.BUY_CASH_SETTLEMENT,
        Stage5DV2EventType.SECURITY_SETTLEMENT,
        Stage5DV2EventType.SECURITY_SELLABLE,
    )
    assert tuple(item.declared_canonical_hash.value for item in replay.projected_events) == (
        BUY_V2_EVENT_SHA256
    )
    for ordinal, event in enumerate(replay.projected_events):
        assert event.prior_event_hashes == tuple(
            item.declared_canonical_hash for item in replay.projected_events[:ordinal]
        )

    state = replay.derived_state
    assert state is not None
    assert state.available_cash == "98386.77"
    assert state.cash_payable == "0"
    assert state.actual_quantity("600000.SH") == 200
    assert state.sellable_quantity("600000.SH") == 200
    assert state.journal_head_hash.value == BUY_V2_HEAD_SHA256
    assert len(state.lots) == 1
    lot = state.lots[0]
    assert lot.cost_components.to_json_value() == {
        "principal": "1600",
        "fee": "5.23",
        "tax": "0",
        "slippage": "8",
        "basis_adjustment": "0",
    }
    balances = {(item.account, item.security_id): item.debit_less_credit for item in state.balances}
    assert balances[(Stage5DV2Account.SECURITY_COST_PRINCIPAL, "600000.SH")] == "1600"
    assert balances[(Stage5DV2Account.SECURITY_COST_FEE, "600000.SH")] == "5.23"
    assert balances[(Stage5DV2Account.SECURITY_COST_SLIPPAGE, "600000.SH")] == "8"

    assert result.same_call_stage5c_recomputed is True
    assert result.source_driven is True
    assert result.not_stage5d1_complete is True
    assert result.persists_state is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False
    assert result.connects_broker is False
    assert result.reads_kb_internal_state is False


def test_explicit_rejected_no_fill_replays_only_source_bound_opening(
    repository_root: Path,
) -> None:
    case, _, _, result = _evaluate(repository_root, reject=True)

    assert result.status is Stage5DSourceDrivenSliceStatus.NO_FILL_RECONCILED
    assert result.stage5c_result.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
    assert canonical_sha256(result) == NO_FILL_RESULT_SHA256
    assert result.slice_replay_hash.value == NO_FILL_SLICE_REPLAY_SHA256
    assert stage5d_source_driven_slice_sha256(case, result) == NO_FILL_SLICE_REPLAY_SHA256
    replay = result.v2_replay
    assert replay is not None
    assert replay.replay_hash.value == NO_FILL_V2_REPLAY_SHA256
    assert tuple(item.event_type for item in replay.accepted_events) == (
        Stage5DV2EventType.OPENING_BALANCE,
    )
    assert replay.accepted_events[0].declared_canonical_hash.value == NO_FILL_EVENT_SHA256
    state = replay.derived_state
    assert state is not None
    assert state.available_cash == "100000"
    assert state.lots == ()
    assert state.journal_head_hash.value == NO_FILL_HEAD_SHA256


def test_future_security_states_do_not_leak_into_fill_time_prefix(
    repository_root: Path,
) -> None:
    _, _, _, result = _evaluate(repository_root)
    assert result.v2_replay is not None

    fill_time = datetime(2025, 1, 20, 2, 31, tzinfo=UTC)
    prefix = replay_stage5d_v2_slice(result.v2_replay.projected_events, as_of=fill_time)

    assert prefix.status is Stage5DV2ReplayStatus.RECONCILED
    assert tuple(item.event_type for item in prefix.accepted_events) == (
        Stage5DV2EventType.OPENING_BALANCE,
        Stage5DV2EventType.BUY_TRADE,
        Stage5DV2EventType.BUY_CASH_SETTLEMENT,
    )
    assert tuple(item.event_type for item in prefix.future_events) == (
        Stage5DV2EventType.SECURITY_SETTLEMENT,
        Stage5DV2EventType.SECURITY_SELLABLE,
    )
    state = prefix.derived_state
    assert state is not None
    assert state.actual_quantity("600000.SH") == 200
    assert state.sellable_quantity("600000.SH") == 0
    assert state.lots[0].unsettled_quantity == 200


def test_v2_replay_rejects_any_declared_prefix_that_is_not_the_full_prefix(
    repository_root: Path,
) -> None:
    _, _, _, result = _evaluate(repository_root)
    assert result.v2_replay is not None
    events = result.v2_replay.projected_events
    drifted = bind_stage5d_v2_event(replace(events[2], prior_event_hashes=()))

    replay = replay_stage5d_v2_slice(
        (events[0], events[1], drifted, *events[3:]),
        as_of=datetime(2025, 2, 1, tzinfo=UTC),
    )

    assert replay.status is Stage5DV2ReplayStatus.PRECHECK_BLOCKED
    assert replay.reason_codes == ("STAGE5D_V2_EXACT_FULL_PREFIX_MISMATCH",)
    assert replay.derived_state is None


def test_stage5c_artifact_drift_is_not_laundered_into_a_v2_result(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root)
    account = case.synthetic_account_snapshot
    drifted_account = replace(
        account,
        identity=replace(
            account.identity,
            declared_content_hash=HashDigest(algorithm="sha256", value="1" * 64),
        ),
    )
    drifted_case = replace(case, synthetic_account_snapshot=drifted_account)

    result = evaluate_stage5d_source_driven_ledger_slice(
        drifted_case,
        market_rules,
        portfolio_rules,
        _capability(repository_root),
    )

    assert result.status is Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED
    assert result.v2_replay is None
    assert result.stage5c_result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert "STAGE5D_EXACT_STAGE5C_SOURCE_DID_NOT_RECONCILE" in result.reason_codes


def test_source_driven_sell_uses_exact_continuation_and_fifo_components(
    repository_root: Path,
) -> None:
    case, _, _, result = _evaluate(repository_root, sell=True)

    assert result.status is Stage5DSourceDrivenSliceStatus.SELL_RECONCILED
    assert result.stage5c_result.status is Stage5ExecutionStatus.FILLED
    assert canonical_sha256(result.stage5c_result) == SELL_STAGE5C_RESULT_SHA256
    assert canonical_sha256(result) == SELL_RESULT_SHA256
    assert result.slice_replay_hash.value == SELL_SLICE_REPLAY_SHA256
    assert stage5d_source_driven_slice_sha256(case, result) == SELL_SLICE_REPLAY_SHA256
    assert result.continuation_basis_replay_hash is not None
    assert result.continuation_basis_replay_hash.value == SELL_BASIS_REPLAY_SHA256

    replay = result.v2_replay
    assert replay is not None
    assert replay.status is Stage5DV2ReplayStatus.RECONCILED
    assert replay.replay_hash.value == SELL_V2_REPLAY_SHA256
    assert tuple(item.event_type for item in replay.projected_events) == (
        Stage5DV2EventType.OPENING_BALANCE,
        Stage5DV2EventType.OPENING_POSITION,
        Stage5DV2EventType.OPENING_POSITION,
        Stage5DV2EventType.SELL_TRADE,
        Stage5DV2EventType.SELL_CASH_SETTLEMENT,
        Stage5DV2EventType.SELL_CASH_AVAILABLE,
    )
    assert tuple(item.declared_canonical_hash.value for item in replay.projected_events) == (
        SELL_EVENT_SHA256
    )
    state = replay.derived_state
    assert state is not None
    assert state.available_cash == "91585.18"
    assert state.cash_payable == "0"
    assert state.actual_quantity("600000.SH") == 100
    assert state.sellable_quantity("600000.SH") == 50
    assert state.journal_head_hash.value == SELL_HEAD_SHA256
    assert tuple(item.lot_id for item in state.lots) == ("opening_lot_002",)
    assert state.lots[0].cost_components.to_json_value() == {
        "principal": "775",
        "fee": "10",
        "tax": "0",
        "slippage": "15",
        "basis_adjustment": "0",
    }
    balances = {(item.account, item.security_id): item.debit_less_credit for item in state.balances}
    assert balances[(Stage5DV2Account.REALIZED_COST_BASIS_CONTROL, None)] == "1500"
    assert balances[(Stage5DV2Account.REALIZED_FEE, None)] == "5.22"
    assert balances[(Stage5DV2Account.REALIZED_TAX, None)] == "1.6"
    assert balances[(Stage5DV2Account.REALIZED_SLIPPAGE, None)] == "8"
    assert balances[(Stage5DV2Account.SECURITY_COST_PRINCIPAL, "600000.SH")] == "775"


def test_sell_cash_settlement_and_availability_do_not_leak_at_fill_time(
    repository_root: Path,
) -> None:
    _, _, _, result = _evaluate(repository_root, sell=True)
    assert result.v2_replay is not None
    fill_time = datetime(2025, 1, 20, 2, 31, tzinfo=UTC)

    prefix = replay_stage5d_v2_slice(result.v2_replay.projected_events, as_of=fill_time)

    assert prefix.status is Stage5DV2ReplayStatus.RECONCILED
    assert tuple(item.event_type for item in prefix.future_events) == (
        Stage5DV2EventType.SELL_CASH_SETTLEMENT,
        Stage5DV2EventType.SELL_CASH_AVAILABLE,
    )
    state = prefix.derived_state
    assert state is not None
    assert state.available_cash == "90000"
    balances = {(item.account, item.security_id): item.debit_less_credit for item in state.balances}
    assert balances[(Stage5DV2Account.CASH_RECEIVABLE, None)] == "1585.18"
    assert (Stage5DV2Account.CASH_SETTLED_UNAVAILABLE, None) not in balances

    settled = replay_stage5d_v2_slice(
        result.v2_replay.projected_events,
        as_of=datetime(2025, 1, 21, 2, 10, tzinfo=UTC),
    )
    assert settled.status is Stage5DV2ReplayStatus.RECONCILED
    settled_state = settled.derived_state
    assert settled_state is not None
    assert settled_state.available_cash == "90000"
    settled_balances = {
        (item.account, item.security_id): item.debit_less_credit for item in settled_state.balances
    }
    assert (Stage5DV2Account.CASH_RECEIVABLE, None) not in settled_balances
    assert settled_balances[(Stage5DV2Account.CASH_SETTLED_UNAVAILABLE, None)] == "1585.18"


def test_sell_rejects_missing_or_drifted_opening_attribution(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root, sell=True)
    attributions = _sell_attributions(case)
    first = attributions[0]
    drifted = bind_stage5d_v2_opening_attribution(
        replace(
            first,
            cost_components=replace(first.cost_components, principal="681"),
        )
    )

    missing = evaluate_stage5d_source_driven_ledger_slice(
        case,
        market_rules,
        portfolio_rules,
        _capability(repository_root),
    )
    changed = evaluate_stage5d_source_driven_ledger_slice(
        case,
        market_rules,
        portfolio_rules,
        _capability(repository_root),
        opening_attributions=(drifted, *attributions[1:]),
    )

    for result in (missing, changed):
        assert result.status is Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED
        assert result.reason_codes == ("STAGE5D_V2_CONTINUATION_BASIS_CLOSURE_FAILED",)
        assert result.v2_replay is None


def test_v2_replay_rejects_non_fifo_sell_effect_order(
    repository_root: Path,
) -> None:
    _, _, _, result = _evaluate(repository_root, sell=True)
    assert result.v2_replay is not None
    opening = result.v2_replay.projected_events[:3]
    sell = result.v2_replay.projected_events[3]
    drifted = bind_stage5d_v2_event(replace(sell, lot_effects=tuple(reversed(sell.lot_effects))))

    replay = replay_stage5d_v2_slice(
        (*opening, drifted),
        as_of=sell.effective_at,
    )

    assert replay.status is Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED
    assert replay.reason_codes == ("STAGE5D_V2_FIFO_LOT_REMOVAL_MISMATCH",)
    assert replay.derived_state is None
