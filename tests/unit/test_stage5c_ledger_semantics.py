from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5_ledger import (
    STAGE5C_LEDGER_PRIORITY,
    LedgerAccountCode,
    LedgerEvent,
    LedgerEventType,
    LedgerLotEffect,
    LedgerPosting,
    LedgerReplayStatus,
    bind_ledger_event,
    replay_stage5c_ledger,
)

ZERO = HashDigest(algorithm="sha256", value="0" * 64)
RULE_HASH = HashDigest(algorithm="sha256", value="1" * 64)
MARKET_RULE_HASH = HashDigest(algorithm="sha256", value="2" * 64)
NOW = datetime(2025, 1, 20, 9, 30, tzinfo=UTC)
SECURITY = "600000.SH"


def _posting(
    account: LedgerAccountCode,
    unit: str,
    *,
    debit: str = "0",
    credit: str = "0",
) -> LedgerPosting:
    return LedgerPosting(account, unit, debit, credit)


def _event(
    event_type: LedgerEventType,
    suffix: str,
    *,
    at: datetime,
    postings: tuple[LedgerPosting, ...] = (),
    lot_effects: tuple[LedgerLotEffect, ...] = (),
    security_id: str | None = SECURITY,
    source_object_ids: tuple[str, ...] | None = None,
    supersedes: str | None = None,
    strategy_id: str = "industrial_event",
    account_fixture_id: str = "anonymous_account",
) -> LedgerEvent:
    return bind_ledger_event(
        LedgerEvent(
            ledger_event_id=f"ledger_{suffix}",
            idempotency_key=f"idem_{suffix}",
            event_type=event_type,
            event_type_priority=STAGE5C_LEDGER_PRIORITY[event_type],
            strategy_id=strategy_id,
            account_fixture_id=account_fixture_id,
            security_id=security_id,
            effective_at=at,
            trade_date=None if event_type is LedgerEventType.OPENING_BALANCE else "2025-01-20",
            settlement_date=None,
            source_object_ids=source_object_ids or (f"source_{suffix}",),
            source_hashes=(ZERO,),
            postings=postings,
            lot_effects=lot_effects,
            rule_ids=("industrial_event_stage5_5a",),
            rule_versions=("0.1.0",),
            rule_hashes=(RULE_HASH,),
            supersedes_or_reversal_of=supersedes,
            declared_canonical_hash=ZERO,
        )
    )


def _cash_opening() -> LedgerEvent:
    return _event(
        LedgerEventType.OPENING_BALANCE,
        "opening_cash",
        at=NOW,
        security_id=None,
        postings=(
            _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", debit="1000"),
            _posting(LedgerAccountCode.OPENING_CONTROL, "CNY", credit="1000"),
        ),
    )


def _reservation(suffix: str, at: datetime, amount: str = "100") -> LedgerEvent:
    return _event(
        LedgerEventType.CASH_RESERVATION,
        suffix,
        at=at,
        postings=(
            _posting(LedgerAccountCode.CASH_RESERVED, "CNY", debit=amount),
            _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", credit=amount),
        ),
    )


def _buy_fill(
    suffix: str,
    at: datetime,
    *,
    fill_id: str,
    lot_id: str,
) -> LedgerEvent:
    return _event(
        LedgerEventType.TRADE_FILL,
        suffix,
        at=at,
        source_object_ids=(f"order_{suffix}", fill_id),
        postings=(
            _posting(LedgerAccountCode.SECURITY_COST, "CNY", debit="90"),
            _posting(LedgerAccountCode.CASH_PAYABLE, "CNY", credit="90"),
            _posting(LedgerAccountCode.SECURITY_UNSETTLED, SECURITY, debit="1"),
            _posting(LedgerAccountCode.SECURITY_CONTROL, SECURITY, credit="1"),
        ),
        lot_effects=(
            LedgerLotEffect(
                lot_id=lot_id,
                security_id=SECURITY,
                quantity_delta=1,
                sellable_quantity_delta=0,
                full_cost_delta="90",
                acquired_at=at,
                governing_market_rule_hash=MARKET_RULE_HASH,
                source_fill_id=fill_id,
            ),
        ),
    )


def _position_opening() -> LedgerEvent:
    return _event(
        LedgerEventType.OPENING_BALANCE,
        "opening_position",
        at=NOW,
        security_id=None,
        postings=(
            _posting(LedgerAccountCode.SECURITY_COST, "CNY", debit="30"),
            _posting(LedgerAccountCode.OPENING_CONTROL, "CNY", credit="30"),
            _posting(LedgerAccountCode.SECURITY_SELLABLE, SECURITY, debit="2"),
            _posting(LedgerAccountCode.SECURITY_CONTROL, SECURITY, credit="2"),
        ),
        lot_effects=(
            LedgerLotEffect(
                "lot_early",
                SECURITY,
                1,
                1,
                "10",
                NOW - timedelta(days=2),
                MARKET_RULE_HASH,
                None,
            ),
            LedgerLotEffect(
                "lot_late",
                SECURITY,
                1,
                1,
                "20",
                NOW - timedelta(days=1),
                MARKET_RULE_HASH,
                None,
            ),
        ),
    )


def test_partial_buy_journal_is_valid_before_future_settlement_and_availability() -> None:
    opening = _cash_opening()
    reservation = _reservation("reserve_partial", NOW + timedelta(seconds=1))
    fill = _buy_fill(
        "buy_partial",
        NOW + timedelta(seconds=2),
        fill_id="fill_partial",
        lot_id="lot_partial",
    )

    replay = replay_stage5c_ledger((opening, reservation, fill))

    assert replay.status is LedgerReplayStatus.RECONCILED
    assert replay.derived_state is not None
    assert replay.derived_state.actual_quantity(SECURITY) == 1
    assert replay.derived_state.sellable_quantity(SECURITY) == 0
    assert replay.full_cost_to_security_cost_reconciled is False
    assert replay.persists_state is False


def test_fractional_security_posting_and_unbacked_lot_effect_fail_closed() -> None:
    fractional = _event(
        LedgerEventType.OPENING_BALANCE,
        "opening_fractional",
        at=NOW,
        security_id=None,
        postings=(
            _posting(LedgerAccountCode.SECURITY_SELLABLE, SECURITY, debit="1.5"),
            _posting(LedgerAccountCode.SECURITY_CONTROL, SECURITY, credit="1.5"),
        ),
        lot_effects=(
            LedgerLotEffect(
                "lot_fractional",
                SECURITY,
                1,
                1,
                "0",
                NOW,
                MARKET_RULE_HASH,
                None,
            ),
        ),
    )
    unbacked = _event(
        LedgerEventType.OPENING_BALANCE,
        "opening_unbacked_lot",
        at=NOW,
        security_id=None,
        postings=(
            _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", debit="1"),
            _posting(LedgerAccountCode.OPENING_CONTROL, "CNY", credit="1"),
        ),
        lot_effects=(
            LedgerLotEffect(
                "lot_unbacked",
                SECURITY,
                1,
                0,
                "0",
                NOW,
                MARKET_RULE_HASH,
                None,
            ),
        ),
    )

    assert replay_stage5c_ledger((fractional,)).reason_codes == (
        "SECURITY_QUANTITY_POSTING_MUST_BE_EXACT_INTEGER",
    )
    assert replay_stage5c_ledger((unbacked,)).reason_codes == (
        "LOT_EFFECT_REQUIRES_MATCHING_SECURITY_POSTING",
    )


def test_balanced_but_wrong_cash_release_schema_is_rejected() -> None:
    malformed = _event(
        LedgerEventType.CASH_RELEASE,
        "malformed_release",
        at=NOW + timedelta(seconds=1),
        postings=(
            _posting(LedgerAccountCode.FEE_EXPENSE, "CNY", debit="1"),
            _posting(LedgerAccountCode.OPENING_CONTROL, "CNY", credit="1"),
        ),
    )

    replay = replay_stage5c_ledger((_cash_opening(), malformed))

    assert replay.status is LedgerReplayStatus.RECONCILIATION_BLOCKED
    assert replay.reason_codes == ("CASH_RELEASE_POSTING_SCHEMA_INVALID",)


def test_fill_source_is_unique_and_buy_fill_creates_exactly_one_lot() -> None:
    opening = _cash_opening()
    first_reservation = _reservation("reserve_first", NOW + timedelta(seconds=1))
    first_fill = _buy_fill(
        "buy_first",
        NOW + timedelta(seconds=2),
        fill_id="fill_reused",
        lot_id="lot_first",
    )
    second_reservation = _reservation("reserve_second", NOW + timedelta(seconds=3))
    second_fill = _buy_fill(
        "buy_second",
        NOW + timedelta(seconds=4),
        fill_id="fill_reused",
        lot_id="lot_second",
    )

    replay = replay_stage5c_ledger(
        (opening, first_reservation, first_fill, second_reservation, second_fill)
    )

    assert replay.status is LedgerReplayStatus.RECONCILIATION_BLOCKED
    assert replay.reason_codes == ("SOURCE_FILL_ID_REUSED",)


def test_under_reserved_payable_and_oversell_are_reconciliation_blocks() -> None:
    under_reserved = replay_stage5c_ledger(
        (
            _cash_opening(),
            _reservation("reserve_too_little", NOW + timedelta(seconds=1), "50"),
            _buy_fill(
                "buy_above_reserve",
                NOW + timedelta(seconds=2),
                fill_id="fill_above_reserve",
                lot_id="lot_above_reserve",
            ),
        )
    )
    oversell = _event(
        LedgerEventType.TRADE_FILL,
        "oversell",
        at=NOW + timedelta(seconds=1),
        source_object_ids=("order_oversell", "fill_oversell"),
        postings=(
            _posting(LedgerAccountCode.CASH_RECEIVABLE, "CNY", debit="100"),
            _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", credit="100"),
            _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", debit="30"),
            _posting(LedgerAccountCode.SECURITY_COST, "CNY", credit="30"),
            _posting(LedgerAccountCode.SECURITY_CONTROL, SECURITY, debit="3"),
            _posting(LedgerAccountCode.SECURITY_SELLABLE, SECURITY, credit="3"),
        ),
        lot_effects=(
            LedgerLotEffect(
                "lot_early",
                SECURITY,
                -1,
                -1,
                "-10",
                None,
                None,
                "fill_oversell",
            ),
            LedgerLotEffect(
                "lot_late",
                SECURITY,
                -2,
                -2,
                "-20",
                None,
                None,
                "fill_oversell",
            ),
        ),
    )
    oversold = replay_stage5c_ledger((_position_opening(), oversell))

    assert under_reserved.reason_codes == ("CASH_RESERVATION_BELOW_OPEN_PAYABLE",)
    assert oversold.reason_codes == ("SELL_FILL_FIFO_POSTING_OR_COST_SCHEMA_INVALID",)


def test_sell_must_consume_sellable_lots_in_fifo_order() -> None:
    sell = _event(
        LedgerEventType.TRADE_FILL,
        "sell_late_lot_first",
        at=NOW + timedelta(seconds=1),
        source_object_ids=("order_sell", "fill_sell"),
        postings=(
            _posting(LedgerAccountCode.CASH_RECEIVABLE, "CNY", debit="100"),
            _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", credit="100"),
            _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", debit="20"),
            _posting(LedgerAccountCode.SECURITY_COST, "CNY", credit="20"),
            _posting(LedgerAccountCode.SECURITY_CONTROL, SECURITY, debit="1"),
            _posting(LedgerAccountCode.SECURITY_SELLABLE, SECURITY, credit="1"),
        ),
        lot_effects=(
            LedgerLotEffect(
                "lot_late",
                SECURITY,
                -1,
                -1,
                "-20",
                None,
                None,
                "fill_sell",
            ),
        ),
    )

    replay = replay_stage5c_ledger((_position_opening(), sell))

    assert replay.status is LedgerReplayStatus.RECONCILIATION_BLOCKED
    assert replay.reason_codes == ("SELL_FILL_FIFO_POSTING_OR_COST_SCHEMA_INVALID",)


def test_reversal_requires_one_replacement_and_cannot_be_replaced_twice() -> None:
    opening = _cash_opening()
    reservation = _reservation("reserve_corrected", NOW + timedelta(seconds=1))
    reversal = _event(
        LedgerEventType.REVERSAL,
        "reverse_reservation",
        at=NOW + timedelta(seconds=2),
        postings=tuple(
            LedgerPosting(
                posting.account,
                posting.currency_or_security,
                posting.credit,
                posting.debit,
            )
            for posting in reservation.postings
        ),
        source_object_ids=reservation.source_object_ids,
        supersedes=reservation.ledger_event_id,
    )
    # Exact reversal provenance is part of the correction contract.
    reversal = bind_ledger_event(
        replace(
            reversal,
            source_hashes=reservation.source_hashes,
            rule_ids=reservation.rule_ids,
            rule_versions=reservation.rule_versions,
            rule_hashes=reservation.rule_hashes,
            declared_canonical_hash=ZERO,
        )
    )
    replacement = _event(
        LedgerEventType.REPLACEMENT,
        "replacement_reservation",
        at=NOW + timedelta(seconds=3),
        postings=reservation.postings,
        source_object_ids=reservation.source_object_ids,
        supersedes=reversal.ledger_event_id,
    )
    duplicate_replacement = _event(
        LedgerEventType.REPLACEMENT,
        "replacement_reservation_again",
        at=NOW + timedelta(seconds=4),
        postings=reservation.postings,
        source_object_ids=reservation.source_object_ids,
        supersedes=reversal.ledger_event_id,
    )

    dangling = replay_stage5c_ledger((opening, reservation, reversal))
    duplicate = replay_stage5c_ledger(
        (opening, reservation, reversal, replacement, duplicate_replacement)
    )

    assert dangling.reason_codes == ("REVERSAL_REQUIRES_EXACTLY_ONE_REPLACEMENT",)
    assert duplicate.reason_codes == ("REPLACEMENT_REQUIRES_ONE_UNREPLACED_PRIOR_REVERSAL",)


def test_provenance_scope_and_stage5d_events_fail_closed() -> None:
    opening = _cash_opening()
    missing_provenance = bind_ledger_event(
        replace(
            opening,
            source_object_ids=(),
            source_hashes=(),
            declared_canonical_hash=ZERO,
        )
    )
    mixed_scope = replace(
        _reservation("mixed_scope", NOW + timedelta(seconds=1)),
        strategy_id="theme_rotation",
    )
    mixed_scope = bind_ledger_event(replace(mixed_scope, declared_canonical_hash=ZERO))
    mark = _event(
        LedgerEventType.MARK_TO_MARKET,
        "stage5d_mark",
        at=NOW + timedelta(seconds=1),
        postings=(),
    )

    assert replay_stage5c_ledger((missing_provenance,)).reason_codes == (
        "LEDGER_EVENT_SOURCE_PROVENANCE_REQUIRED",
    )
    assert replay_stage5c_ledger((opening, mixed_scope)).reason_codes == (
        "LEDGER_STRATEGY_OR_ACCOUNT_SCOPE_MIXED",
    )
    assert replay_stage5c_ledger((opening, mark)).reason_codes == (
        "STAGE5D_EVENT_NOT_IMPLEMENTED:MARK_TO_MARKET",
    )
