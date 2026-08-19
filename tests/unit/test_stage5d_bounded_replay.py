"""Acceptance tests for the preregistered bounded Stage 5D replay."""

from __future__ import annotations

import copy
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

import pytest

from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5_governance import (
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    Stage5PortfolioLedgerCase,
)
from invest_system.strategies.industrial_event.stage5d_bounded_replay import (
    STAGE5D_EVENT_SEMANTIC_MAP_SHA256,
    STAGE5D_FIRST_REPLAY_PREREGISTRATION_SHA256,
    STAGE5D_PNL_FORMULA_MAP_SHA256,
    Stage5DBoundedMark,
    Stage5DBoundedReplayCase,
    Stage5DBoundedReplayPurpose,
    Stage5DBoundedReplayResult,
    Stage5DBoundedReplayStatus,
    Stage5DPnlDriver,
    Stage5DPnlRealization,
    evaluate_stage5d_bounded_complete_replay,
    stage5d_bounded_complete_replay_sha256,
)
from invest_system.strategies.industrial_event.stage5d_ledger_v2 import (
    Stage5DV2EventType,
)
from unit import test_stage5_portfolio_ledger as stage5c_support
from unit import test_stage5d_source_driven_ledger_slice as source_slice_support

_BEGINNING = datetime(2025, 1, 20, 2, 10, tzinfo=UTC)
_ENDING = datetime(2025, 1, 21, 7, 1, tzinfo=UTC)
_CONFIG_HASH = HashDigest(
    algorithm="sha256",
    value="0e9a6398bc166c599bc9bf4b9a4acb33e987ed7541f224523a58e343872d1f24",
)
COMPLETE_REPLAY_SHA256 = "f5ed17d1bf9944d35b7a5afa36e68df0fc40d12c277874ea01d02d1e0bd59225"
REMATERIALIZED_V2_REPLAY_SHA256 = "6bf96f43bdbd1aa8deabd922362241ad628f12f8a74325af7ada4e8973d40127"
REMATERIALIZED_V2_HEAD_SHA256 = "e375af373c99b84dac549ddbcb0d8b21ba861931aedeb8a6353c999991a3a836"
BEGINNING_VALUATION_SHA256 = "c2172191fdb12693d62e904e2906c489e4ee2aa0d2a26fedfab6f13cca763a2f"
ENDING_VALUATION_SHA256 = "3147da9fb4dd710f91f0c4735eec374d83eadbaab3bc1b9239706aa1d4dc11b9"
PNL_SHA256 = "379579fe80bda776fea99c3d9df841395a390178a4067111a2a941c75c637680"


def _mark() -> Stage5DBoundedMark:
    return Stage5DBoundedMark(
        mark_id="synthetic_mark_600000_20250121_close",
        security_id="600000.SH",
        price="8",
        currency="CNY",
        observed_at=datetime(2025, 1, 21, 7, 0, tzinfo=UTC),
        available_at=_ENDING,
        source_kind="synthetic_preregistered_close_mark",
    )


def _inputs(
    repository_root: Path,
) -> tuple[
    Stage5PortfolioLedgerCase,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
    Stage5DBoundedReplayCase,
]:
    raw_case, market_rules, portfolio_rules = stage5c_support._case(repository_root)
    bounded_case = Stage5DBoundedReplayCase(
        preregistration_hash=HashDigest(
            algorithm="sha256",
            value=STAGE5D_FIRST_REPLAY_PREREGISTRATION_SHA256,
        ),
        stage5c_case=raw_case,
        beginning_at=_BEGINNING,
        ending_at=_ENDING,
        mark_coverage_complete=True,
        ending_mark=_mark(),
        corporate_action_ids=(),
        external_cash_flow_ids=(),
        purpose=Stage5DBoundedReplayPurpose.RESEARCH_VALIDATION,
        source_complete_replay_hash=None,
        code_commit="6c0858a038eda05d65703055a3da420da7063a19",
        semantic_config_hash=_CONFIG_HASH,
    )
    return raw_case, market_rules, portfolio_rules, bounded_case


def _evaluate(
    repository_root: Path,
    bounded_case: Stage5DBoundedReplayCase | None = None,
) -> tuple[
    Stage5PortfolioLedgerCase,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
    Stage5DBoundedReplayCase,
    Stage5DBoundedReplayResult,
]:
    raw_case, market_rules, portfolio_rules, default_case = _inputs(repository_root)
    selected = bounded_case or default_case
    result = evaluate_stage5d_bounded_complete_replay(
        selected,
        market_rules,
        portfolio_rules,
        source_slice_support._capability(repository_root),
    )
    return raw_case, market_rules, portfolio_rules, selected, result


def test_preregistered_buy_closes_mark_nav_pnl_and_complete_replay(
    repository_root: Path,
) -> None:
    _, _, _, case, result = _evaluate(repository_root)
    repeated = _evaluate(repository_root)[4]

    assert result.status is Stage5DBoundedReplayStatus.COMPLETE
    assert result.reason_codes == ("STAGE5D_FIRST_ORDER_CONTRACT_REPLAY_COMPLETE",)
    assert result.complete_replay_hash.value == COMPLETE_REPLAY_SHA256
    assert result.complete_replay_hash == repeated.complete_replay_hash
    assert result.complete_replay_hash.value == stage5d_bounded_complete_replay_sha256(case, result)
    assert result.event_semantic_map_hash.value == STAGE5D_EVENT_SEMANTIC_MAP_SHA256
    assert result.pnl_formula_map_hash.value == STAGE5D_PNL_FORMULA_MAP_SHA256

    replay = result.rematerialized_v2_replay
    assert replay is not None
    assert replay.replay_hash.value == REMATERIALIZED_V2_REPLAY_SHA256
    assert replay.derived_state is not None
    assert replay.derived_state.journal_head_hash.value == REMATERIALIZED_V2_HEAD_SHA256
    assert tuple(item.event_type for item in replay.accepted_events) == (
        Stage5DV2EventType.OPENING_BALANCE,
        Stage5DV2EventType.BUY_TRADE,
        Stage5DV2EventType.BUY_CASH_SETTLEMENT,
        Stage5DV2EventType.SECURITY_SETTLEMENT,
        Stage5DV2EventType.SECURITY_SELLABLE,
    )
    assert replay.accepted_events[0].effective_at == _BEGINNING
    assert replay.future_events == ()
    for ordinal, event in enumerate(replay.accepted_events):
        assert event.prior_event_hashes == tuple(
            item.declared_canonical_hash for item in replay.accepted_events[:ordinal]
        )

    beginning = result.beginning_valuation
    ending = result.ending_valuation
    assert beginning is not None
    assert ending is not None
    assert beginning.available_cash == "100000"
    assert beginning.actual_quantity == 0
    assert beginning.market_value == "0"
    assert beginning.nav == "100000"
    assert beginning.valuation_hash.value == BEGINNING_VALUATION_SHA256
    assert ending.available_cash == "98386.77"
    assert ending.actual_quantity == 200
    assert ending.sellable_quantity == 200
    assert ending.mark_price == "8"
    assert ending.market_value == "1600"
    assert ending.nav == "99986.77"
    assert ending.valuation_hash.value == ENDING_VALUATION_SHA256

    pnl = result.pnl
    assert pnl is not None
    assert pnl.pnl_hash.value == PNL_SHA256
    assert len(pnl.beginning_matrix.cells) == 18
    assert len(pnl.ending_matrix.cells) == 18
    assert len(pnl.period_cells) == 18
    period = {(item.realization, item.driver): item.amount for item in pnl.period_cells}
    assert period[(Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.PRICE)] == "0"
    assert period[(Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.SLIPPAGE)] == "-8"
    assert period[(Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.FEE)] == "-5.23"
    assert period[(Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.TAX)] == "0"
    assert sum((Decimal(item.amount) for item in pnl.period_cells), Decimal(0)) == Decimal("-13.23")
    assert pnl.period_total_pnl == "-13.23"
    assert [item.formula_term for item in pnl.ending_contributions] == [
        "MV",
        "RB",
        "RS",
        "RF",
    ]
    assert sum(
        (Decimal(item.signed_amount) for item in pnl.ending_contributions), Decimal(0)
    ) == Decimal("-13.23")
    forbidden = {
        (Stage5DPnlRealization.REALIZED, Stage5DPnlDriver.CASH_DIVIDEND),
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.CASH_DIVIDEND),
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.CORPORATE_ACTION_CASH),
        (Stage5DPnlRealization.NON_POSITION_INCOME, Stage5DPnlDriver.PRICE),
        (Stage5DPnlRealization.NON_POSITION_INCOME, Stage5DPnlDriver.SLIPPAGE),
    }
    assert all(period[item] == "0" for item in forbidden)
    assert not any(
        (item.realization, item.driver) in forbidden for item in pnl.ending_contributions
    )

    assert result.replay_complete is True
    assert result.valuation_complete is True
    assert result.pnl_complete is True
    assert result.reconciled is True
    assert result.financial_state_changed is True
    assert result.advances_financial_head is True
    assert result.same_call_stage5c_recomputed is True
    assert result.source_driven is True
    assert result.audit_only is False
    assert result.external_state_mutated is False
    assert result.persists_state is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False
    assert result.connects_broker is False
    assert result.reads_kb_internal_state is False
    assert result.writes_kb is False


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    (
        (
            "corporate_action_ids",
            ("synthetic_action_001",),
            "STAGE5D_CORPORATE_ACTION_OUTSIDE_BOUNDED_SLICE",
        ),
        (
            "external_cash_flow_ids",
            ("synthetic_flow_001",),
            "STAGE5D_EXTERNAL_CASH_FLOW_OUTSIDE_BOUNDED_SLICE",
        ),
        (
            "mark_coverage_complete",
            False,
            "STAGE5D_ENDING_MARK_COVERAGE_UNVERIFIABLE",
        ),
    ),
)
def test_unsupported_inputs_block_before_financial_output(
    repository_root: Path,
    field_name: str,
    value: object,
    reason: str,
) -> None:
    _, _, _, case = _inputs(repository_root)
    if field_name == "corporate_action_ids":
        selected = replace(case, corporate_action_ids=cast(tuple[str, ...], value))
    elif field_name == "external_cash_flow_ids":
        selected = replace(case, external_cash_flow_ids=cast(tuple[str, ...], value))
    else:
        selected = replace(case, mark_coverage_complete=cast(bool, value))
    blocked = _evaluate(repository_root, selected)[4]

    assert blocked.status is Stage5DBoundedReplayStatus.PRECHECK_BLOCKED
    assert blocked.reason_codes == (reason,)
    assert blocked.stage5c_result_hash is None
    assert blocked.rematerialized_v2_replay is None
    assert blocked.beginning_valuation is None
    assert blocked.ending_valuation is None
    assert blocked.pnl is None
    assert blocked.replay_complete is False
    assert blocked.financial_state_changed is False
    assert blocked.source_driven is False
    assert blocked.same_call_stage5c_recomputed is False


def test_complete_coverage_without_eligible_mark_abstains_after_ledger_replay(
    repository_root: Path,
) -> None:
    _, _, _, case = _inputs(repository_root)
    abstain = _evaluate(repository_root, replace(case, ending_mark=None))[4]

    assert abstain.status is Stage5DBoundedReplayStatus.ABSTAIN_INCOMPLETE_PNL
    assert abstain.reason_codes == ("STAGE5D_COMPLETE_COVERAGE_HAS_NO_ELIGIBLE_ENDING_MARK",)
    assert abstain.rematerialized_v2_replay is not None
    assert len(abstain.rematerialized_v2_replay.accepted_events) == 5
    assert abstain.beginning_valuation is None
    assert abstain.ending_valuation is None
    assert abstain.pnl is None
    assert abstain.replay_complete is False
    assert abstain.valuation_complete is False
    assert abstain.pnl_complete is False
    assert abstain.financial_state_changed is True
    assert abstain.advances_financial_head is True


def test_mark_drift_fails_closed_without_partial_nav_or_pnl(repository_root: Path) -> None:
    _, _, _, case = _inputs(repository_root)
    blocked = _evaluate(repository_root, replace(case, ending_mark=replace(_mark(), price="8.01")))[
        4
    ]

    assert blocked.status is Stage5DBoundedReplayStatus.PRECHECK_BLOCKED
    assert blocked.reason_codes == ("STAGE5D_ENDING_MARK_OUTSIDE_PREREGISTERED_EVIDENCE",)
    assert blocked.rematerialized_v2_replay is None
    assert blocked.beginning_valuation is None
    assert blocked.ending_valuation is None
    assert blocked.pnl is None
    assert blocked.source_driven is False
    assert blocked.same_call_stage5c_recomputed is False


def test_sell_case_is_not_silently_widened_into_the_bounded_replay(
    repository_root: Path,
) -> None:
    _, market_rules, portfolio_rules, case = _inputs(repository_root)
    sell_case = stage5c_support._case(repository_root, sell=True)[0]
    blocked = evaluate_stage5d_bounded_complete_replay(
        replace(case, stage5c_case=sell_case),
        market_rules,
        portfolio_rules,
        source_slice_support._capability(repository_root),
    )

    assert blocked.status is Stage5DBoundedReplayStatus.PRECHECK_BLOCKED
    assert blocked.reason_codes == ("STAGE5D_PREREGISTERED_STAGE5C_CASE_MISMATCH",)
    assert blocked.stage5c_result_hash is None
    assert blocked.rematerialized_v2_replay is None
    assert blocked.beginning_valuation is None
    assert blocked.ending_valuation is None
    assert blocked.pnl is None


def test_bounded_precheck_still_requires_the_exact_stage5d_capability(
    repository_root: Path,
) -> None:
    _, market_rules, portfolio_rules, case = _inputs(repository_root)
    wrong_capability = copy.copy(source_slice_support._capability(repository_root))
    object.__setattr__(
        wrong_capability,
        "bundle_hash",
        HashDigest(algorithm="sha256", value="e" * 64),
    )

    with pytest.raises(ValueError, match="exact approved Stage 5D capability"):
        evaluate_stage5d_bounded_complete_replay(
            replace(case, corporate_action_ids=("synthetic_action_001",)),
            market_rules,
            portfolio_rules,
            wrong_capability,
        )


def test_audit_replay_requires_exact_source_hash_and_remains_zero_authority(
    repository_root: Path,
) -> None:
    _, market_rules, portfolio_rules, case, source = _evaluate(repository_root)
    audit_case = replace(
        case,
        purpose=Stage5DBoundedReplayPurpose.AUDIT_REPLAY,
        source_complete_replay_hash=source.complete_replay_hash,
    )
    audit = evaluate_stage5d_bounded_complete_replay(
        audit_case,
        market_rules,
        portfolio_rules,
        source_slice_support._capability(repository_root),
    )
    wrong = evaluate_stage5d_bounded_complete_replay(
        replace(
            audit_case,
            source_complete_replay_hash=HashDigest(algorithm="sha256", value="f" * 64),
        ),
        market_rules,
        portfolio_rules,
        source_slice_support._capability(repository_root),
    )

    assert audit.status is Stage5DBoundedReplayStatus.COMPLETE
    assert audit.audit_only is True
    assert audit.complete_replay_hash != source.complete_replay_hash
    assert audit.beginning_valuation == source.beginning_valuation
    assert audit.ending_valuation == source.ending_valuation
    assert audit.pnl == source.pnl
    assert audit.external_state_mutated is False
    assert audit.persists_state is False
    assert audit.authorizes_positions is False
    assert audit.authorizes_orders is False
    assert wrong.status is Stage5DBoundedReplayStatus.PRECHECK_BLOCKED
    assert wrong.reason_codes == ("STAGE5D_AUDIT_SOURCE_REPLAY_HASH_MISMATCH",)
    assert wrong.source_driven is True
    assert wrong.same_call_stage5c_recomputed is True
    assert wrong.rematerialized_v2_replay is None
    assert wrong.pnl is None
