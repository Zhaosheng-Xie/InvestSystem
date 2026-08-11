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
    Stage5DV2EventType,
    Stage5DV2ReplayStatus,
    bind_stage5d_v2_event,
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

BUY_RESULT_SHA256 = "5ed4251d36aeee13c1061fec0b38731e724db7117354b37137340bb22d7d2da6"
BUY_SLICE_REPLAY_SHA256 = "5934029c7ba1c8fe7a4e9376e800d92d25659e7cca0fb06563e84b135fb0eb4b"
BUY_V2_REPLAY_SHA256 = "be8d28c85b76a9df230232964ec3bf0f99637e8f6ca5a890b2e7266bc2ff5dbd"
BUY_V2_EVENT_SHA256 = (
    "154e9904dc69fa21e251e4124d916102b658994d1c2c1f5d9cec8312a21bfb47",
    "c01ed072a5cc92b4d9780e78a13bdf816171f5e009915ba92b082f5a21701539",
    "e381e20c848f341d0ba3c41ba4462dad1b16137a85587422a4a47df1abe74053",
    "a1511909dc50caecd0317d66c3a4a61b59d883a632111015cac219bf8b397846",
    "d941623c338f83b1868bcbce452eea2d2ca96585e968183e0daf7c5843b39b61",
)
BUY_V2_HEAD_SHA256 = "dc1c0d489e0449a22f2212d3d884137d34db4797703907398055311dd58a5739"

NO_FILL_RESULT_SHA256 = "50ac2367cedd57f0fcd3aafb2e99f677858d979e0753e96eaba5f1087670670c"
NO_FILL_SLICE_REPLAY_SHA256 = "595c050e74e2ac4708e18a57931d1134040d029bc49d4565fc1058b2b07502f1"
NO_FILL_V2_REPLAY_SHA256 = "52f7f1c7e2971edbd5a32e47d3da652006b3725402df15e415e1547b400deb5d"
NO_FILL_EVENT_SHA256 = "02da2c5027316625ca3dcf21e5a4e278364a25ccfdaef96ff95024cd6618d95f"
NO_FILL_HEAD_SHA256 = "64fd04f93cd3f8013cbd6084d02612151cd807cfd929d189837474f3823e84d1"


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
    result = evaluate_stage5d_source_driven_ledger_slice(
        case,
        market_rules,
        portfolio_rules,
        _capability(repository_root),
    )
    return case, market_rules, portfolio_rules, result


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


def test_nonempty_opening_sell_is_explicitly_outside_the_first_slice(
    repository_root: Path,
) -> None:
    _, _, _, result = _evaluate(repository_root, sell=True)

    assert result.status is Stage5DSourceDrivenSliceStatus.UNSUPPORTED_SLICE
    assert result.reason_codes == ("STAGE5D_V2_SLICE_REQUIRES_EMPTY_SYNTHETIC_OPENING",)
    assert result.v2_replay is None
