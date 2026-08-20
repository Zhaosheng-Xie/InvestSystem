from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256
from unit import test_stage5d_bounded_replay as bounded_support
from unit import test_stage5d_source_driven_ledger_slice as source_support

PREREGISTRATION_PATH = Path(
    "tests/fixtures/stage5d/normal-lifecycle-exit-replay-preregistration.v0.1.0.json"
)
DOCUMENT_PATH = Path("docs/validation/stage5d-normal-lifecycle-exit-replay-preregistration-v0.1.md")
PREREGISTRATION_RAW_SHA256 = "67f707e5e2f5cdfca4af45a71639ce91df222f7b5149125e654bfe9d1355a72b"
DOCUMENT_SHA256 = "b6b0939dd43d20c14fd3241675583c835009435c46321d8c3bcc518d9f9fa69c"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _fixture(repository_root: Path) -> dict[str, Any]:
    return _json(repository_root / PREREGISTRATION_PATH)


def _synthetic_weekdays() -> tuple[date, ...]:
    values: list[date] = []
    current = date(2025, 1, 20)
    while len(values) < 60:
        if current.weekday() < 5:
            values.append(current)
        current += timedelta(days=1)
    return tuple(values)


def test_normal_lifecycle_preregistration_has_exact_frozen_identity(
    repository_root: Path,
) -> None:
    fixture_path = repository_root / PREREGISTRATION_PATH
    document_path = repository_root / DOCUMENT_PATH
    fixture = _fixture(repository_root)

    assert sha256(fixture_path.read_bytes()).hexdigest() == PREREGISTRATION_RAW_SHA256
    assert sha256(document_path.read_bytes()).hexdigest() == DOCUMENT_SHA256
    assert fixture["schema_version"] == "0.1.0"
    assert fixture["status"] == "frozen_for_input_materialization_review"
    assert fixture["input_materialization_authorized"] is False
    assert fixture["evaluator_implementation_authorized"] is False
    assert fixture["baseline_commit"] == "39db014cf90b5ed351c915fa23b3fc2c7cf441eb"
    assert fixture["document_binding"] == {
        "path": DOCUMENT_PATH.as_posix(),
        "sha256": DOCUMENT_SHA256,
    }


def test_global_path_selects_reusable_lifecycle_not_another_fixed_sell(
    repository_root: Path,
) -> None:
    fixture = _fixture(repository_root)
    decision = fixture["global_path_decision"]
    seam = fixture["public_seam_requirements"]

    assert decision["selected"] == "NORMAL_LIFECYCLE_PLUS_SESSION_VALUATION_SEAM"
    assert set(decision["rejected"]) == {
        "FIXED_SELL_RESULT_ONLY",
        "FULL_SECURITIES_ACCOUNTING_PLATFORM_BEFORE_CENSUS",
        "FORMAL_ADMISSION_OR_MIGRATION_BEFORE_COMPLETED_TRADE",
    }
    assert decision["does_not_close_readiness_item"] is True
    assert seam["same_path_must_be_reusable_for_target_and_peer"] is True
    assert seam["benchmark_specific_frictionless_path_forbidden"] is True
    assert seam["peer_basket_orchestration_in_current_slice"] is False
    assert seam["portfolio_nav_in_current_slice"] is False
    assert fixture["lifecycle_identity"]["public_contract_must_be_security_neutral"] is True
    identity = fixture["lifecycle_identity"]
    assert identity["exit_origin"] == "STAGE6C_VALIDATION_HORIZON_LIQUIDATION"
    assert identity["does_not_validate_stage4_fr_exit_001"] is True
    upstream = fixture["upstream_bindings"]
    assert upstream["stage6c_v02_specification_sha256"] == (
        "3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368"
    )
    assert upstream["stage6c_v02_approved_bundle_raw_sha256"] == (
        "77e76205b2d4de2163b914bcab2fffb0baa2087e6b89c543dfb538ac366e863a"
    )


def test_entry_lineage_is_exact_and_partial_sell_cannot_be_laundered(
    repository_root: Path,
) -> None:
    fixture = _fixture(repository_root)
    upstream = fixture["upstream_bindings"]
    first_preregistration = _json(
        repository_root
        / "tests/fixtures/stage5d/first-order-contract-replay-preregistration.v0.1.0.json"
    )
    _, _, _, partial_sell = source_support._evaluate(repository_root, sell=True)
    buy_source = source_support._evaluate(repository_root)[3]
    buy_case, _, _, _, bounded_buy = bounded_support._evaluate(repository_root)
    partial = fixture["partial_sell_regression_only"]

    assert (
        canonical_sha256(first_preregistration)
        == (upstream["first_buy_preregistration_canonical_sha256"])
    )
    assert canonical_sha256(partial_sell.stage5c_result) == partial["stage5c_result_sha256"]
    assert canonical_sha256(partial_sell) == partial["source_slice_result_sha256"]
    assert partial_sell.v2_replay is not None
    assert partial_sell.v2_replay.replay_hash.value == partial["v2_replay_sha256"]
    assert partial_sell.v2_replay.derived_state is not None
    assert partial_sell.v2_replay.derived_state.actual_quantity("600000.SH") == 100
    assert (
        partial["opening_quantity"],
        partial["filled_quantity"],
        partial["ending_quantity"],
    ) == (
        300,
        200,
        100,
    )
    assert partial["must_not_be_reused_as_completed_trade"] is True
    assert bounded_buy.rematerialized_v2_replay is not None
    assert bounded_buy.rematerialized_v2_replay.derived_state is not None
    buy_lot = bounded_buy.rematerialized_v2_replay.derived_state.lots[0]
    entry = fixture["entry_source"]
    assert canonical_sha256(buy_case) == upstream["first_buy_stage5c_case_sha256"]
    assert bounded_buy.stage5c_result_hash is not None
    assert bounded_buy.stage5c_result_hash.value == upstream["first_buy_stage5c_result_sha256"]
    assert bounded_buy.complete_replay_hash.value == upstream["first_buy_complete_replay_sha256"]
    assert buy_source.stage5c_result.constrained_market_projection is not None
    buy_fill = buy_source.stage5c_result.constrained_market_projection.market_execution_result.fill
    assert buy_fill is not None
    assert buy_fill.fill_id == upstream["first_buy_fill_id"]
    assert canonical_sha256(buy_fill) == upstream["first_buy_fill_sha256"]
    assert (
        bounded_buy.rematerialized_v2_replay.derived_state.journal_head_hash.value
        == (upstream["first_buy_ending_journal_head_sha256"])
    )
    assert buy_lot.lot_id == entry["lot_id"]
    assert buy_lot.acquired_at.isoformat().replace("+00:00", "Z") == entry[
        "lot_acquired_at"
    ].replace(".000000", "")
    assert canonical_sha256(buy_lot) == entry["derived_lot_canonical_sha256"]
    assert entry["lot_source_fill_sha256"] == upstream["first_buy_fill_sha256"]
    assert fixture["lifecycle_identity"]["single_continuous_journal_required"] is True
    assert fixture["lifecycle_identity"]["exactly_one_opening_event_required"] is True


def test_sixty_session_clock_and_mark_scope_are_unambiguous(
    repository_root: Path,
) -> None:
    fixture = _fixture(repository_root)
    path = fixture["session_path"]
    weekdays = _synthetic_weekdays()

    assert path["baseline_valuation_point_ordinal"] == 0
    assert path["entry_session_ordinal"] == 1
    assert path["exit_session_ordinal"] == 60
    assert path["settlement_tail_session_ordinal"] == 61
    assert path["valuation_point_count"] == 61
    assert path["daily_return_count"] == 60
    assert path["holding_mark_session_ordinals"] == {
        "first_inclusive": 1,
        "last_inclusive": 59,
        "count": 59,
    }
    assert weekdays[0].isoformat() == path["calendar_fixture"]["first_session_date"]
    assert weekdays[-1].isoformat() == path["calendar_fixture"]["last_session_date"]
    assert (weekdays[-1] + timedelta(days=3)).isoformat() == (
        path["calendar_fixture"]["settlement_tail_date"]
    )
    assert path["calendar_fixture"]["not_a_real_exchange_calendar"] is True
    assert path["calendar_fixture"]["must_not_be_used_for_formal_execution"] is True
    assert path["zero_position_requires_no_exit_mark"] is True
    assert path["settlement_tail_does_not_add_horizon_return"] is True
    assert path["exit_fill_at"].startswith(weekdays[-1].isoformat())
    assert path["sell_cash_settlement_at"].startswith(
        path["calendar_fixture"]["settlement_tail_date"]
    )
    assert path["sell_cash_available_at"].startswith(
        path["calendar_fixture"]["settlement_tail_date"]
    )
    assert path["sell_cash_settlement_at"] < path["sell_cash_available_at"]
    assert fixture["holding_marks"]["mark_count"] == 59
    assert fixture["holding_marks"]["caller_supplied_nav_forbidden"] is True
    assert fixture["holding_marks"]["observed_time_utc"] == "07:00:00"
    assert fixture["holding_marks"]["available_and_valuation_time_utc"] == "07:01:00"
    assert path["entry_decision_at"] < path["entry_fill_at"]
    assert path["exit_decision_at"] < path["exit_fill_at"] < path["exit_valuation_at"]


def test_full_exit_events_cash_nav_and_pnl_golden_reconcile(
    repository_root: Path,
) -> None:
    fixture = _fixture(repository_root)
    entry = fixture["entry_source"]
    exit_source = fixture["exit_source"]
    valuation = fixture["valuation_golden"]
    pnl = fixture["pnl_golden"]
    events = fixture["required_financial_event_inventory"]

    assert [event["ordinal"] for event in events] == list(range(8))
    assert [event["event_type"] for event in events] == [
        "OPENING_BALANCE",
        "BUY_TRADE",
        "BUY_CASH_SETTLEMENT",
        "SECURITY_SETTLEMENT",
        "SECURITY_SELLABLE",
        "SELL_TRADE",
        "SELL_CASH_SETTLEMENT",
        "SELL_CASH_AVAILABLE",
    ]
    assert "OPENING_POSITION" not in {event["event_type"] for event in events}
    mark_events = fixture["required_mark_memo_event_inventory"]
    assert mark_events == {
        "event_type": "MARK_TO_MARKET",
        "event_count": 59,
        "session_ordinals_first_last": [1, 59],
        "effective_at_formula": "max(observed_at, available_at)",
        "changes_financial_balances": False,
        "enters_canonical_journal": True,
    }
    assert fixture["projected_event_count"] == len(events) + mark_events["event_count"] == 67
    assert fixture["old_buy_head_is_source_anchor_not_new_prefix_head"] is True
    assert Decimal(entry["post_buy_available_cash"]) + Decimal("1600") == Decimal(
        valuation["holding_session_nav"]
    )
    assert Decimal(exit_source["gross_execution_proceeds"]) - Decimal(exit_source["fee"]) - Decimal(
        exit_source["tax"]
    ) == Decimal(exit_source["net_receivable"])
    assert Decimal(entry["post_buy_available_cash"]) + Decimal(
        exit_source["net_receivable"]
    ) == Decimal(exit_source["ending_cash"])
    assert Decimal(exit_source["ending_nav"]) - Decimal(valuation["baseline_nav"]) == Decimal(
        pnl["lifetime_total_pnl"]
    )
    assert Decimal(exit_source["ending_nav"]) - Decimal(valuation["holding_session_nav"]) == (
        Decimal(pnl["exit_period_total_pnl"])
    )
    assert len(pnl["cell_order"]) == len(set(pnl["cell_order"])) == 18
    for key in ("beginning_matrix_cells", "ending_matrix_cells", "exit_period_matrix_cells"):
        assert len(pnl[key]) == 18
    assert sum(map(Decimal, pnl["beginning_matrix_cells"])) == Decimal(
        pnl["beginning_matrix_total"]
    )
    assert sum(map(Decimal, pnl["ending_matrix_cells"])) == Decimal(pnl["ending_matrix_total"])
    assert sum(map(Decimal, pnl["exit_period_matrix_cells"])) == Decimal(
        pnl["exit_period_total_pnl"]
    )
    assert tuple(
        Decimal(ending) - Decimal(beginning)
        for beginning, ending in zip(
            pnl["beginning_matrix_cells"],
            pnl["ending_matrix_cells"],
            strict=True,
        )
    ) == tuple(map(Decimal, pnl["exit_period_matrix_cells"]))
    assert pnl["exit_period_boundary"] == (
        "(2025-04-10T07:01:00.000000Z, 2025-04-11T07:01:00.000000Z]"
    )
    assert pnl["period_unrealized_slippage_reclassification"] == "8"
    assert pnl["period_unrealized_fee_reclassification"] == "5.23"
    assert pnl["settlement_tail_pnl"] == "0"
    exit_cash = valuation["exit_session_cash_buckets"]
    tail_cash = valuation["settlement_tail_cash_buckets"]
    assert Decimal(exit_cash["available"]) + Decimal(exit_cash["receivable"]) == Decimal(
        valuation["exit_session_nav"]
    )
    assert Decimal(tail_cash["available"]) == Decimal(valuation["settlement_tail_nav"])
    assert entry["quantity"] == exit_source["quantity"]
    assert exit_source["ending_lot_count"] == 0
    assert (exit_source["ending_quantity"], exit_source["ending_sellable_quantity"]) == (0, 0)
    assert fixture["completion_semantics"]["position_closed_and_ledger_settled_are_distinct"]
    assert fixture["completion_semantics"]["not_a_real_completed_trade"] is True


def test_preregistration_freezes_no_implementation_hash_or_runtime_authority(
    repository_root: Path,
) -> None:
    fixture = _fixture(repository_root)
    scope = fixture["scope"]

    assert fixture["required_pre_evaluator_input_hashes"]
    assert all(value is None for value in fixture["required_pre_evaluator_input_hashes"].values())
    assert fixture["evaluator_must_not_be_implemented_until_input_hashes_non_null"] is True
    assert fixture["implementation_derived_hashes"]
    assert all(value is None for value in fixture["implementation_derived_hashes"].values())
    assert fixture["owner_approval_required_before_input_materialization"] is True
    assert fixture["separate_owner_approval_required_before_evaluator_implementation"] is True
    assert scope["synthetic"] is True
    assert scope["validation_only"] is True
    assert scope["authority_eligible"] is False
    assert all(value is False for key, value in scope.items() if key.startswith("authorizes_"))
    assert scope["connects_broker"] is False
    assert scope["persists_state"] is False
    assert scope["reads_kb_internal_state"] is False
    assert scope["writes_kb"] is False
    assert fixture["completion_gate"]["security_neutral_public_contract"] is True
