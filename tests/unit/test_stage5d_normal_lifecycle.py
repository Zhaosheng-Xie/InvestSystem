from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal, getcontext
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system.canonical import canonical_sha256
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5d_lifecycle_inputs import (
    Stage5DNormalLifecycleMaterializedInputs,
)
from invest_system.strategies.industrial_event.stage5d_normal_lifecycle import (
    STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256,
    Stage5DLifecycleJournalEntryKind,
    Stage5DNormalLifecycleCase,
    Stage5DNormalLifecyclePurpose,
    Stage5DNormalLifecycleStatus,
    evaluate_stage5d_normal_lifecycle,
)
from unit import test_stage5d_bounded_replay as bounded_support
from unit import test_stage5d_lifecycle_input_materialization as input_support
from unit import test_stage5d_source_driven_ledger_slice as source_support

GOLDEN_PATH = Path("tests/fixtures/stage5d/normal-lifecycle-evaluator-golden.v0.1.0.json")
GOLDEN_RAW_SHA256 = "59219933c28c9552dc434a8a5a79525aa49f23bafdac65c2701922b498034225"


def _case(
    repository_root: Path,
    *,
    purpose: Stage5DNormalLifecyclePurpose = Stage5DNormalLifecyclePurpose.RESEARCH_VALIDATION,
    source_hash: HashDigest | None = None,
    inputs: Stage5DNormalLifecycleMaterializedInputs | None = None,
) -> tuple[Stage5DNormalLifecycleCase, object, object]:
    _, market_rules, portfolio_rules, entry_case = bounded_support._inputs(repository_root)
    return (
        Stage5DNormalLifecycleCase(
            case_id="stage5d_normal_lifecycle_case_001",
            entry_case=entry_case,
            materialized_inputs=inputs or input_support._materialized_inputs(repository_root),
            purpose=purpose,
            source_complete_replay_hash=source_hash,
            code_commit="stage5d-normal-lifecycle-evaluator-v0.1",
            semantic_config_hash=HashDigest(algorithm="sha256", value="a" * 64),
            injected_clock=datetime(2025, 4, 15, tzinfo=UTC),
        ),
        market_rules,
        portfolio_rules,
    )


def _evaluate(repository_root: Path):  # type: ignore[no-untyped-def]
    case, market_rules, portfolio_rules = _case(repository_root)
    result = evaluate_stage5d_normal_lifecycle(
        case,
        market_rules,  # type: ignore[arg-type]
        portfolio_rules,  # type: ignore[arg-type]
        source_support._capability(repository_root),
    )
    return case, result


def test_normal_lifecycle_recomputes_continuous_buy_to_full_exit(
    repository_root: Path,
) -> None:
    _, result = _evaluate(repository_root)

    assert result.status is Stage5DNormalLifecycleStatus.COMPLETE
    assert result.reason_codes == ("STAGE5D_NORMAL_LIFECYCLE_COMPLETE",)
    assert result.input_set_hash.value == STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256
    assert result.same_call_entry_and_exit_recomputed is True
    assert result.financial_replay is not None
    assert result.financial_replay.derived_state is not None
    assert result.financial_replay.derived_state.lots == ()
    assert result.financial_replay.derived_state.available_cash == "99971.95"
    assert len(result.financial_replay.projected_events) == 8
    assert len(result.journal_entries) == 67
    assert tuple(item.ordinal for item in result.journal_entries) == tuple(range(67))
    assert (
        sum(
            item.kind is Stage5DLifecycleJournalEntryKind.FINANCIAL_EVENT
            for item in result.journal_entries
        )
        == 8
    )
    assert (
        sum(
            item.kind is Stage5DLifecycleJournalEntryKind.MARK_TO_MARKET
            for item in result.journal_entries
        )
        == 59
    )
    for ordinal, entry in enumerate(result.journal_entries):
        assert entry.prior_entry_hashes == tuple(
            item.entry_hash for item in result.journal_entries[:ordinal]
        )


def test_normal_lifecycle_produces_sixty_source_driven_daily_returns(
    repository_root: Path,
) -> None:
    _, result = _evaluate(repository_root)
    assert result.valuation_series is not None
    series = result.valuation_series

    assert len(series.points) == 61
    assert len(series.daily_return_factors) == 60
    assert series.points[0].nav == "100000"
    assert all(item.nav == "99986.77" for item in series.points[1:60])
    assert series.points[60].nav == "99971.95"
    assert series.points[0].actual_quantity == 0
    assert all(item.actual_quantity == 200 for item in series.points[1:60])
    assert series.points[60].actual_quantity == 0
    assert all(item.mark_price == "8" for item in series.points[1:60])
    assert series.points[60].mark_price is None
    assert series.points[60].cash_available == "98386.77"
    assert series.points[60].cash_receivable == "1585.18"
    assert Decimal(series.points[60].cash_available) + Decimal(
        series.points[60].cash_receivable
    ) == Decimal(series.points[60].nav)


def test_normal_lifecycle_reconciles_eighteen_cell_pnl_and_completed_trade(
    repository_root: Path,
) -> None:
    _, result = _evaluate(repository_root)
    assert result.pnl is not None
    assert result.completed_trade is not None
    pnl = result.pnl
    trade = result.completed_trade

    assert len(pnl.lifetime_beginning_matrix.cells) == 18
    assert len(pnl.exit_beginning_matrix.cells) == 18
    assert len(pnl.ending_matrix.cells) == 18
    assert len(pnl.exit_period_cells) == 18
    assert pnl.lifetime_beginning_matrix.total == "0"
    assert pnl.exit_beginning_matrix.total == "-13.23"
    assert pnl.ending_matrix.total == "-28.05"
    assert pnl.lifetime_total_pnl == "-28.05"
    assert pnl.exit_period_total_pnl == "-14.82"
    assert sum((Decimal(item.amount) for item in pnl.exit_period_cells), Decimal(0)) == Decimal(
        "-14.82"
    )
    assert trade.quantity == 200
    assert trade.position_closed_at == datetime(2025, 4, 11, 2, 31, tzinfo=UTC)
    assert trade.ledger_settled_at == datetime(2025, 4, 14, 2, 11, tzinfo=UTC)
    assert trade.position_closed_at < trade.ledger_settled_at
    assert trade.reconciled is True
    assert trade.not_a_real_completed_trade is True
    assert trade.authority_eligible is False


def test_normal_lifecycle_is_deterministic_and_zero_authority(repository_root: Path) -> None:
    first = _evaluate(repository_root)[1]
    second = _evaluate(repository_root)[1]

    assert first == second
    assert first.complete_replay_hash == second.complete_replay_hash
    assert first.replay_complete and first.valuation_complete and first.pnl_complete
    assert first.reconciled is True
    assert first.audit_only is False
    assert first.authority_eligible is False
    assert first.external_state_mutated is False
    assert first.persists_state is False
    assert first.authorizes_backtest is False
    assert first.authorizes_paper is False
    assert first.authorizes_shadow is False
    assert first.authorizes_live is False
    assert first.authorizes_positions is False
    assert first.authorizes_orders is False
    assert first.connects_broker is False
    assert first.reads_kb_internal_state is False
    assert first.writes_kb is False


def test_normal_lifecycle_audit_replay_requires_exact_source_hash(
    repository_root: Path,
) -> None:
    source = _evaluate(repository_root)[1]
    audit_case, market_rules, portfolio_rules = _case(
        repository_root,
        purpose=Stage5DNormalLifecyclePurpose.AUDIT_REPLAY,
        source_hash=source.complete_replay_hash,
    )
    audit = evaluate_stage5d_normal_lifecycle(
        audit_case,
        market_rules,  # type: ignore[arg-type]
        portfolio_rules,  # type: ignore[arg-type]
        source_support._capability(repository_root),
    )
    wrong_case = replace(
        audit_case,
        source_complete_replay_hash=HashDigest(algorithm="sha256", value="f" * 64),
    )
    wrong = evaluate_stage5d_normal_lifecycle(
        wrong_case,
        market_rules,  # type: ignore[arg-type]
        portfolio_rules,  # type: ignore[arg-type]
        source_support._capability(repository_root),
    )

    assert audit.status is Stage5DNormalLifecycleStatus.COMPLETE
    assert audit.audit_only is True
    assert audit.reason_codes == ("STAGE5D_NORMAL_LIFECYCLE_AUDIT_REPLAY_COMPLETE",)
    assert audit.valuation_series == source.valuation_series
    assert audit.pnl == source.pnl
    assert audit.completed_trade == source.completed_trade
    assert wrong.status is Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED
    assert wrong.reason_codes == ("STAGE5D_NORMAL_LIFECYCLE_AUDIT_SOURCE_MISMATCH",)
    assert wrong.valuation_series is None
    assert wrong.pnl is None
    assert wrong.completed_trade is None


def test_normal_lifecycle_rejects_any_other_input_set_before_evaluation(
    repository_root: Path,
) -> None:
    inputs = input_support._materialized_inputs(repository_root)
    with pytest.raises(ValueError, match="input_set_hash"):
        _case(
            repository_root,
            inputs=replace(
                inputs,
                input_set_hash=HashDigest(algorithm="sha256", value="f" * 64),
            ),
        )


def test_normal_lifecycle_matches_exact_machine_golden(repository_root: Path) -> None:
    case, result = _evaluate(repository_root)
    raw = json.loads((repository_root / GOLDEN_PATH).read_text(encoding="utf-8"))
    identities = raw["identities"]

    assert sha256((repository_root / GOLDEN_PATH).read_bytes()).hexdigest() == GOLDEN_RAW_SHA256
    assert canonical_sha256(case) == identities["case_sha256"]
    assert result.complete_replay_hash.value == identities["complete_replay_sha256"]
    assert result.financial_replay is not None
    assert result.financial_replay.replay_hash.value == identities["financial_replay_sha256"]
    assert result.final_journal_head_hash is not None
    assert result.final_journal_head_hash.value == identities["final_journal_head_sha256"]
    assert result.valuation_series is not None
    assert result.valuation_series.series_hash.value == identities["valuation_series_sha256"]
    assert (
        result.valuation_series.points[0].valuation_hash.value
        == (identities["first_valuation_sha256"])
    )
    assert (
        result.valuation_series.points[1].valuation_hash.value
        == (identities["holding_valuation_sha256"])
    )
    assert (
        result.valuation_series.points[60].valuation_hash.value
        == (identities["exit_valuation_sha256"])
    )
    assert result.pnl is not None
    assert result.pnl.pnl_hash.value == identities["pnl_sha256"]
    assert result.completed_trade is not None
    assert result.completed_trade.record_hash.value == identities["completed_trade_sha256"]
    assert result.completed_trade.entry_fill_hash.value == identities["entry_fill_sha256"]
    assert result.completed_trade.exit_fill_hash.value == identities["exit_fill_sha256"]
    assert result.exit_stage5c_result_hash is not None
    assert result.exit_stage5c_result_hash.value == identities["exit_stage5c_result_sha256"]
    assert result.exit_source_slice_hash is not None
    assert result.exit_source_slice_hash.value == identities["exit_source_slice_sha256"]


def test_normal_lifecycle_is_independent_of_ambient_decimal_context(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = _case(repository_root)
    capability = source_support._capability(repository_root)
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        changed = evaluate_stage5d_normal_lifecycle(
            case,
            market_rules,  # type: ignore[arg-type]
            portfolio_rules,  # type: ignore[arg-type]
            capability,
        )
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding

    baseline = evaluate_stage5d_normal_lifecycle(
        case,
        market_rules,  # type: ignore[arg-type]
        portfolio_rules,  # type: ignore[arg-type]
        capability,
    )
    assert changed == baseline


def test_normal_lifecycle_contract_rejects_partial_or_drifted_financial_output(
    repository_root: Path,
) -> None:
    result = _evaluate(repository_root)[1]
    assert result.valuation_series is not None
    assert result.pnl is not None

    with pytest.raises(ValueError, match="blocked normal lifecycle"):
        replace(result, status=Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED)
    with pytest.raises(ValueError, match="daily return factors"):
        replace(
            result.valuation_series,
            daily_return_factors=("1.01", *result.valuation_series.daily_return_factors[1:]),
        )
    with pytest.raises(ValueError, match="contributions"):
        replace(result.pnl, ending_contributions=result.pnl.ending_contributions[:-1])
