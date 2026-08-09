"""Adapter from exact constrained Stage 5B output to provider-neutral ledger events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from invest_system.canonical import canonical_sha256
from invest_system.models import CanonicalModel, HashDigest

from .stage5_decimal import with_stage5_decimal_context
from .stage5_execution_contracts import (
    InitialLedgerSnapshot,
    PortfolioSizingInputs,
    SettlementAvailabilityTerms,
    SettlementMomentKind,
    SyntheticAccountSnapshot,
    stage5c_artifact_content_sha256,
    stage5c_initial_ledger_head_sha256,
)
from .stage5_governance import (
    STAGE5_5A_RULE_BUNDLE_ID,
    STAGE5_5A_RULE_BUNDLE_VERSION,
    ApprovedStage5PortfolioLedgerRules,
)
from .stage5_ledger import (
    STAGE5C_LEDGER_PRIORITY,
    LedgerAccountCode,
    LedgerEvent,
    LedgerEventType,
    LedgerLotEffect,
    LedgerPosting,
    bind_ledger_event,
)
from .stage5_market_execution import (
    Stage5ConstrainedMarketExecutionProjection,
    Stage5MarketExecutionCase,
    TradeSide,
    TradingSession,
)


class Stage5FillProjectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _number(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@dataclass(frozen=True, slots=True)
class Stage5FillLedgerProjection(CanonicalModel):
    events: tuple[LedgerEvent, ...]
    unsubmitted_approved_quantity: int
    unfilled_cancelled_quantity: int
    reason_codes: tuple[str, ...]
    projection_hash: HashDigest
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)


def _posting(
    account: LedgerAccountCode,
    unit: str,
    *,
    debit: Decimal = Decimal(0),
    credit: Decimal = Decimal(0),
) -> LedgerPosting:
    return LedgerPosting(account, unit, _number(debit), _number(credit))


def _event(
    *,
    event_type: LedgerEventType,
    case: Stage5MarketExecutionCase,
    effective_at: datetime,
    trade_date: str | None,
    settlement_date: str | None,
    suffix: str,
    source_ids: tuple[str, ...],
    source_hashes: tuple[HashDigest, ...],
    postings: tuple[LedgerPosting, ...] = (),
    lot_effects: tuple[LedgerLotEffect, ...] = (),
    security_id: str | None = None,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> LedgerEvent:
    material = {
        "case_id": case.case_id,
        "event_type": event_type.value,
        "effective_at": effective_at,
        "suffix": suffix,
        "source_hashes": source_hashes,
    }
    identifier = canonical_sha256(material)[:24]
    return bind_ledger_event(
        LedgerEvent(
            ledger_event_id=f"ledger_{event_type.value.lower()}_{identifier}",
            idempotency_key=f"idem_{identifier}",
            event_type=event_type,
            event_type_priority=STAGE5C_LEDGER_PRIORITY[event_type],
            strategy_id=case.strategy_id,
            account_fixture_id=case.account_fixture_id,
            security_id=security_id,
            effective_at=effective_at,
            trade_date=trade_date,
            settlement_date=settlement_date,
            source_object_ids=source_ids,
            source_hashes=source_hashes,
            postings=postings,
            lot_effects=lot_effects,
            rule_ids=(STAGE5_5A_RULE_BUNDLE_ID,),
            rule_versions=(STAGE5_5A_RULE_BUNDLE_VERSION,),
            rule_hashes=(rules.bundle_hash,),
            supersedes_or_reversal_of=None,
            declared_canonical_hash=_hash("0" * 64),
        )
    )


def _opening_event(
    case: Stage5MarketExecutionCase,
    account: SyntheticAccountSnapshot,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> LedgerEvent:
    postings: list[LedgerPosting] = []
    lot_effects: list[LedgerLotEffect] = []
    available = Decimal(account.available_cash)
    reserved = Decimal(account.reserved_cash)
    receivable = Decimal(account.unsettled_cash_receivable)
    payable = Decimal(account.unsettled_cash_payable)
    if available > 0:
        postings.append(_posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", debit=available))
    if reserved > 0:
        postings.append(_posting(LedgerAccountCode.CASH_RESERVED, "CNY", debit=reserved))
    if receivable > 0:
        postings.append(_posting(LedgerAccountCode.CASH_RECEIVABLE, "CNY", debit=receivable))
    if payable > 0:
        postings.append(_posting(LedgerAccountCode.CASH_PAYABLE, "CNY", credit=payable))
    total_cost = Decimal(0)
    for position in account.positions:
        sellable = position.sellable_quantity
        unsellable = position.quantity - sellable
        if sellable > 0:
            postings.append(
                _posting(
                    LedgerAccountCode.SECURITY_SELLABLE,
                    position.security_id,
                    debit=Decimal(sellable),
                )
            )
        if unsellable > 0:
            postings.append(
                _posting(
                    LedgerAccountCode.SECURITY_UNSELLABLE,
                    position.security_id,
                    debit=Decimal(unsellable),
                )
            )
        postings.append(
            _posting(
                LedgerAccountCode.SECURITY_CONTROL,
                position.security_id,
                credit=Decimal(position.quantity),
            )
        )
        for lot in position.lots:
            cost = Decimal(lot.full_cost)
            total_cost += cost
            lot_effects.append(
                LedgerLotEffect(
                    lot_id=lot.lot_id,
                    security_id=lot.security_id,
                    quantity_delta=lot.quantity,
                    sellable_quantity_delta=lot.sellable_quantity,
                    full_cost_delta=lot.full_cost,
                    acquired_at=lot.acquired_at,
                    governing_market_rule_hash=lot.governing_market_rule_hash,
                    source_fill_id=None,
                )
            )
    if total_cost > 0:
        postings.append(_posting(LedgerAccountCode.SECURITY_COST, "CNY", debit=total_cost))
    debit_assets = available + reserved + receivable + total_cost
    control = debit_assets - payable
    if control > 0:
        postings.append(_posting(LedgerAccountCode.OPENING_CONTROL, "CNY", credit=control))
    elif control < 0:
        postings.append(_posting(LedgerAccountCode.OPENING_CONTROL, "CNY", debit=-control))
    return _event(
        event_type=LedgerEventType.OPENING_BALANCE,
        case=case,
        effective_at=account.identity.as_of,
        trade_date=None,
        settlement_date=None,
        suffix="opening",
        source_ids=(account.identity.artifact_id,),
        source_hashes=(account.identity.declared_content_hash,),
        postings=tuple(postings),
        lot_effects=tuple(lot_effects),
        rules=rules,
    )


@with_stage5_decimal_context
def project_stage5_opening_to_ledger(
    case: Stage5MarketExecutionCase,
    account: SyntheticAccountSnapshot,
    initial_ledger: InitialLedgerSnapshot,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> tuple[LedgerEvent, ...]:
    """Project the explicit empty initial head into one balanced opening event."""

    if (
        account.identity.declared_content_hash.value != stage5c_artifact_content_sha256(account)
        or initial_ledger.identity.declared_content_hash.value
        != stage5c_artifact_content_sha256(initial_ledger)
        or initial_ledger.strategy_id != case.strategy_id
        or initial_ledger.account_fixture_id != case.account_fixture_id
        or initial_ledger.account_snapshot_hash != account.identity.declared_content_hash
        or initial_ledger.expected_head_hash.value
        != stage5c_initial_ledger_head_sha256(account.identity.declared_content_hash)
    ):
        raise Stage5FillProjectionError("INITIAL_LEDGER_HEAD_OR_SCOPE_MISMATCH")
    return (_opening_event(case, account, rules),)


def _selected_trade_date(projection: Stage5ConstrainedMarketExecutionProjection) -> str:
    result = projection.market_execution_result
    fill = result.fill
    if fill is None:
        raise Stage5FillProjectionError("CONSTRAINED_FILL_MISSING")
    attempt = next(
        (item for item in result.attempts if item.observation_id == fill.observation_id),
        None,
    )
    if attempt is None:
        raise Stage5FillProjectionError("FILL_ATTEMPT_BINDING_MISSING")
    return attempt.local_trade_date


def _validate_terms(
    case: Stage5MarketExecutionCase,
    projection: Stage5ConstrainedMarketExecutionProjection,
    terms: SettlementAvailabilityTerms,
) -> None:
    if terms.identity.declared_content_hash.value != stage5c_artifact_content_sha256(terms):
        raise Stage5FillProjectionError("SETTLEMENT_TERMS_HASH_DRIFT")
    if terms.special_exception_id is not None:
        raise Stage5FillProjectionError("SETTLEMENT_SPECIAL_EXCEPTION_CONTRACT_NOT_IMPLEMENTED")
    result = projection.market_execution_result
    fill = result.fill
    order = result.order_intent
    if fill is None or order is None:
        return
    if (
        terms.identity.as_of > fill.filled_at
        or terms.identity.knowledge_cutoff > fill.filled_at
        or terms.identity.as_of > case.injected_clock
        or terms.identity.knowledge_cutoff > case.injected_clock
    ):
        raise Stage5FillProjectionError("SETTLEMENT_TERMS_NOT_PIT_AVAILABLE")
    attempt = next(
        (item for item in result.attempts if item.observation_id == fill.observation_id),
        None,
    )
    if (
        attempt is None
        or attempt.market_rule_hash is None
        or terms.market_rule_hash != attempt.market_rule_hash
        or terms.trade_local_date != attempt.local_trade_date
        or terms.venue != case.venue
        or terms.board != case.board
        or terms.security_type != case.security_type
        or terms.risk_label != case.risk_label
    ):
        raise Stage5FillProjectionError("SETTLEMENT_TERMS_SCOPE_OR_RULE_MISMATCH")
    selected_rule = next(
        (
            item
            for item in case.market_rule_sets
            if item.identity.declared_content_hash == attempt.market_rule_hash
        ),
        None,
    )
    if selected_rule is None or selected_rule.same_day_sellable != terms.same_day_sellable:
        raise Stage5FillProjectionError("SETTLEMENT_SELLABILITY_RULE_MISMATCH")
    calendar_dates = tuple(
        dict.fromkeys(session.local_trade_date for session in case.trading_calendar.sessions)
    )
    try:
        trade_date_index = calendar_dates.index(terms.trade_local_date)
        expected_cycle_date = calendar_dates[trade_date_index + selected_rule.settlement_cycle_days]
    except (ValueError, IndexError) as error:
        raise Stage5FillProjectionError("SETTLEMENT_CALENDAR_HORIZON_MISSING") from error

    sessions_by_date: dict[str, list[TradingSession]] = {}
    for session in case.trading_calendar.sessions:
        sessions_by_date.setdefault(session.local_trade_date, []).append(session)
    for moment in terms.moments:
        sessions = sessions_by_date.get(moment.local_trade_date, [])
        if not sessions or not any(
            session.opens_at <= moment.effective_at <= session.closes_at for session in sessions
        ):
            raise Stage5FillProjectionError("SETTLEMENT_MOMENT_OUTSIDE_TRADING_CALENDAR")
    security_settlement = terms.moment(SettlementMomentKind.SECURITY_SETTLEMENT)
    security_sellable = terms.moment(SettlementMomentKind.SECURITY_SELLABLE)
    buy_payable = terms.moment(SettlementMomentKind.BUY_CASH_PAYABLE)
    sell_receivable = terms.moment(SettlementMomentKind.SELL_PROCEEDS_RECEIVABLE)
    sell_settlement = terms.moment(SettlementMomentKind.SELL_CASH_SETTLEMENT)
    sell_available = terms.moment(SettlementMomentKind.SELL_CASH_AVAILABLE)
    if (
        min(
            security_settlement.effective_at,
            security_sellable.effective_at,
            buy_payable.effective_at,
        )
        < fill.filled_at
        or security_sellable.effective_at < security_settlement.effective_at
        or sell_receivable.effective_at != fill.filled_at
        or sell_settlement.effective_at < sell_receivable.effective_at
        or sell_available.effective_at < sell_settlement.effective_at
    ):
        raise Stage5FillProjectionError("SETTLEMENT_MOMENT_ORDER_INVALID")
    same_day = security_sellable.local_trade_date == terms.trade_local_date
    if same_day != terms.same_day_sellable:
        raise Stage5FillProjectionError("SAME_DAY_SELLABILITY_DATE_MISMATCH")
    if (
        security_settlement.local_trade_date != expected_cycle_date
        or sell_settlement.local_trade_date != expected_cycle_date
        or buy_payable.local_trade_date != terms.trade_local_date
        or sell_receivable.local_trade_date != terms.trade_local_date
        or (
            not terms.same_day_sellable and security_sellable.local_trade_date < expected_cycle_date
        )
        or sell_available.local_trade_date < expected_cycle_date
    ):
        raise Stage5FillProjectionError("SETTLEMENT_CYCLE_OR_AVAILABILITY_MISMATCH")


@with_stage5_decimal_context
def project_stage5_fill_to_ledger(
    case: Stage5MarketExecutionCase,
    projection: Stage5ConstrainedMarketExecutionProjection,
    account: SyntheticAccountSnapshot,
    initial_ledger: InitialLedgerSnapshot,
    terms: SettlementAvailabilityTerms,
    sizing: PortfolioSizingInputs,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> Stage5FillLedgerProjection:
    """Create opening and exact fill events without persisting any state."""

    if any(
        value.identity.declared_content_hash.value != stage5c_artifact_content_sha256(value)
        for value in (account, initial_ledger, sizing)
    ):
        raise Stage5FillProjectionError("STAGE5C_LEDGER_INPUT_HASH_DRIFT")
    if (
        initial_ledger.strategy_id != case.strategy_id
        or initial_ledger.account_fixture_id != case.account_fixture_id
        or initial_ledger.account_snapshot_hash != account.identity.declared_content_hash
        or initial_ledger.expected_head_hash.value
        != stage5c_initial_ledger_head_sha256(account.identity.declared_content_hash)
    ):
        raise Stage5FillProjectionError("INITIAL_LEDGER_HEAD_OR_SCOPE_MISMATCH")
    candidate = projection.market_candidate
    # The constrained outer replay is recomputed by the Stage 5C engine where
    # the exact constraint object is available.  Here we accept only its typed
    # projection and still validate its raw 5B preview/result bindings.
    if candidate.market_execution_preview.input_hash.value != canonical_sha256(case):
        raise Stage5FillProjectionError("MARKET_CANDIDATE_INPUT_MISMATCH")
    _validate_terms(case, projection, terms)
    events: list[LedgerEvent] = list(
        project_stage5_opening_to_ledger(case, account, initial_ledger, rules)
    )
    result = projection.market_execution_result
    fill = result.fill
    order = result.order_intent
    if fill is None or order is None:
        value = Stage5FillLedgerProjection(
            events=tuple(events),
            unsubmitted_approved_quantity=projection.unsubmitted_quantity,
            unfilled_cancelled_quantity=projection.unfilled_cancelled_quantity,
            reason_codes=("NO_CONSTRAINED_FILL_TO_PROJECT",),
            projection_hash=_hash("0" * 64),
        )
        return Stage5FillLedgerProjection(
            events=value.events,
            unsubmitted_approved_quantity=value.unsubmitted_approved_quantity,
            unfilled_cancelled_quantity=value.unfilled_cancelled_quantity,
            reason_codes=value.reason_codes,
            projection_hash=_hash(
                canonical_sha256(value.to_json_value() | {"projection_hash": None})
            ),
        )
    trade_date = _selected_trade_date(projection)
    source_ids = (order.order_intent_id, fill.fill_id)
    source_hashes = (
        _hash(canonical_sha256(order)),
        _hash(canonical_sha256(fill)),
        projection.replay_hash,
        terms.identity.declared_content_hash,
    )
    events.append(
        _event(
            event_type=LedgerEventType.SYNTHETIC_ORDER_ACCEPTED,
            case=case,
            effective_at=order.submitted_at,
            trade_date=trade_date,
            settlement_date=None,
            suffix="accepted",
            source_ids=source_ids,
            source_hashes=source_hashes,
            security_id=case.security_id,
            rules=rules,
        )
    )
    gross = Decimal(fill.gross_notional)
    total_cost = Decimal(fill.costs.total)
    fee = total_cost - Decimal(fill.costs.tax)
    tax = Decimal(fill.costs.tax)
    if fill.side is TradeSide.BUY:
        worst_cost = Decimal(sizing.worst_applicable_cost_reserve)
        if worst_cost < total_cost:
            raise Stage5FillProjectionError("WORST_COST_RESERVE_BELOW_ACTUAL_COST")
        reserved = gross + worst_cost
        if reserved > Decimal(account.available_cash):
            raise Stage5FillProjectionError("CASH_RESERVATION_EXCEEDS_AVAILABLE_CASH")
        events.append(
            _event(
                event_type=LedgerEventType.CASH_RESERVATION,
                case=case,
                effective_at=order.submitted_at,
                trade_date=trade_date,
                settlement_date=terms.moment(
                    SettlementMomentKind.BUY_CASH_PAYABLE
                ).local_trade_date,
                suffix="buy_reserve",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(LedgerAccountCode.CASH_RESERVED, "CNY", debit=reserved),
                    _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", credit=reserved),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
        attempt = next(
            item for item in result.attempts if item.observation_id == fill.observation_id
        )
        assert attempt.market_rule_hash is not None
        lot_id = f"lot_{canonical_sha256(fill)[:24]}"
        events.append(
            _event(
                event_type=LedgerEventType.TRADE_FILL,
                case=case,
                effective_at=fill.filled_at,
                trade_date=trade_date,
                settlement_date=terms.moment(
                    SettlementMomentKind.SECURITY_SETTLEMENT
                ).local_trade_date,
                suffix="buy_fill",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(LedgerAccountCode.SECURITY_COST, "CNY", debit=gross),
                    _posting(LedgerAccountCode.CASH_PAYABLE, "CNY", credit=gross),
                    _posting(
                        LedgerAccountCode.SECURITY_UNSETTLED,
                        case.security_id,
                        debit=Decimal(fill.quantity),
                    ),
                    _posting(
                        LedgerAccountCode.SECURITY_CONTROL,
                        case.security_id,
                        credit=Decimal(fill.quantity),
                    ),
                ),
                lot_effects=(
                    LedgerLotEffect(
                        lot_id=lot_id,
                        security_id=case.security_id,
                        quantity_delta=fill.quantity,
                        sellable_quantity_delta=0,
                        full_cost_delta=fill.gross_notional,
                        acquired_at=fill.filled_at,
                        governing_market_rule_hash=attempt.market_rule_hash,
                        source_fill_id=fill.fill_id,
                    ),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
        for event_type, amount, suffix in (
            (LedgerEventType.FEE, fee, "buy_fee"),
            (LedgerEventType.TAX, tax, "buy_tax"),
        ):
            if amount == 0:
                continue
            account_code = (
                LedgerAccountCode.FEE_EXPENSE
                if event_type is LedgerEventType.FEE
                else LedgerAccountCode.TAX_EXPENSE
            )
            events.append(
                _event(
                    event_type=event_type,
                    case=case,
                    effective_at=fill.filled_at,
                    trade_date=trade_date,
                    settlement_date=terms.moment(
                        SettlementMomentKind.BUY_CASH_PAYABLE
                    ).local_trade_date,
                    suffix=suffix,
                    source_ids=source_ids,
                    source_hashes=source_hashes,
                    postings=(
                        _posting(account_code, "CNY", debit=amount),
                        _posting(LedgerAccountCode.CASH_PAYABLE, "CNY", credit=amount),
                    ),
                    lot_effects=(
                        LedgerLotEffect(
                            lot_id=lot_id,
                            security_id=case.security_id,
                            quantity_delta=0,
                            sellable_quantity_delta=0,
                            full_cost_delta=_number(amount),
                            acquired_at=None,
                            governing_market_rule_hash=None,
                            source_fill_id=fill.fill_id,
                        ),
                    ),
                    security_id=case.security_id,
                    rules=rules,
                )
            )
        payable_moment = terms.moment(SettlementMomentKind.BUY_CASH_PAYABLE)
        release = worst_cost - total_cost
        if release > 0:
            events.append(
                _event(
                    event_type=LedgerEventType.CASH_RELEASE,
                    case=case,
                    effective_at=payable_moment.effective_at,
                    trade_date=trade_date,
                    settlement_date=payable_moment.local_trade_date,
                    suffix="unused_cost_reserve",
                    source_ids=source_ids,
                    source_hashes=source_hashes,
                    postings=(
                        _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", debit=release),
                        _posting(LedgerAccountCode.CASH_RESERVED, "CNY", credit=release),
                    ),
                    security_id=case.security_id,
                    rules=rules,
                )
            )
        events.append(
            _event(
                event_type=LedgerEventType.TRADE_SETTLEMENT,
                case=case,
                effective_at=payable_moment.effective_at,
                trade_date=trade_date,
                settlement_date=payable_moment.local_trade_date,
                suffix="buy_cash_settlement",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(LedgerAccountCode.CASH_PAYABLE, "CNY", debit=gross + total_cost),
                    _posting(LedgerAccountCode.CASH_RESERVED, "CNY", credit=gross + total_cost),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
        security_settlement = terms.moment(SettlementMomentKind.SECURITY_SETTLEMENT)
        events.append(
            _event(
                event_type=LedgerEventType.TRADE_SETTLEMENT,
                case=case,
                effective_at=security_settlement.effective_at,
                trade_date=trade_date,
                settlement_date=security_settlement.local_trade_date,
                suffix="buy_security_settlement",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(
                        LedgerAccountCode.SECURITY_UNSELLABLE,
                        case.security_id,
                        debit=Decimal(fill.quantity),
                    ),
                    _posting(
                        LedgerAccountCode.SECURITY_UNSETTLED,
                        case.security_id,
                        credit=Decimal(fill.quantity),
                    ),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
        availability = terms.moment(SettlementMomentKind.SECURITY_SELLABLE)
        events.append(
            _event(
                event_type=LedgerEventType.SECURITY_AVAILABILITY,
                case=case,
                effective_at=availability.effective_at,
                trade_date=trade_date,
                settlement_date=availability.local_trade_date,
                suffix="buy_security_available",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(
                        LedgerAccountCode.SECURITY_SELLABLE,
                        case.security_id,
                        debit=Decimal(fill.quantity),
                    ),
                    _posting(
                        LedgerAccountCode.SECURITY_UNSELLABLE,
                        case.security_id,
                        credit=Decimal(fill.quantity),
                    ),
                ),
                lot_effects=(
                    LedgerLotEffect(
                        lot_id=lot_id,
                        security_id=case.security_id,
                        quantity_delta=0,
                        sellable_quantity_delta=fill.quantity,
                        full_cost_delta="0",
                        acquired_at=None,
                        governing_market_rule_hash=None,
                        source_fill_id=fill.fill_id,
                    ),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
    else:
        position = account.position(case.security_id)
        if position is None or fill.quantity > position.sellable_quantity:
            raise Stage5FillProjectionError("SELL_EXCEEDS_OPENING_SELLABLE_QUANTITY")
        remaining = fill.quantity
        effects: list[LedgerLotEffect] = []
        disposed_cost = Decimal(0)
        for lot in sorted(position.lots, key=lambda item: (item.acquired_at, item.lot_id)):
            if remaining == 0:
                break
            take = min(remaining, lot.sellable_quantity)
            if take == 0:
                continue
            cost = Decimal(lot.full_cost) * Decimal(take) / Decimal(lot.quantity)
            disposed_cost += cost
            effects.append(
                LedgerLotEffect(
                    lot_id=lot.lot_id,
                    security_id=case.security_id,
                    quantity_delta=-take,
                    sellable_quantity_delta=-take,
                    full_cost_delta=_number(-cost),
                    acquired_at=None,
                    governing_market_rule_hash=None,
                    source_fill_id=fill.fill_id,
                )
            )
            remaining -= take
        if remaining:
            raise Stage5FillProjectionError("FIFO_SELLABLE_LOTS_EXHAUSTED")
        fill_postings = [
            _posting(LedgerAccountCode.CASH_RECEIVABLE, "CNY", debit=gross),
            _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", credit=gross),
            _posting(
                LedgerAccountCode.SECURITY_CONTROL,
                case.security_id,
                debit=Decimal(fill.quantity),
            ),
            _posting(
                LedgerAccountCode.SECURITY_SELLABLE,
                case.security_id,
                credit=Decimal(fill.quantity),
            ),
        ]
        if disposed_cost > 0:
            fill_postings.extend(
                (
                    _posting(LedgerAccountCode.TRADE_CLEARING, "CNY", debit=disposed_cost),
                    _posting(LedgerAccountCode.SECURITY_COST, "CNY", credit=disposed_cost),
                )
            )
        events.append(
            _event(
                event_type=LedgerEventType.TRADE_FILL,
                case=case,
                effective_at=fill.filled_at,
                trade_date=trade_date,
                settlement_date=terms.moment(
                    SettlementMomentKind.SELL_CASH_SETTLEMENT
                ).local_trade_date,
                suffix="sell_fill",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=tuple(fill_postings),
                lot_effects=tuple(effects),
                security_id=case.security_id,
                rules=rules,
            )
        )
        for event_type, amount, suffix in (
            (LedgerEventType.FEE, fee, "sell_fee"),
            (LedgerEventType.TAX, tax, "sell_tax"),
        ):
            if amount == 0:
                continue
            account_code = (
                LedgerAccountCode.FEE_EXPENSE
                if event_type is LedgerEventType.FEE
                else LedgerAccountCode.TAX_EXPENSE
            )
            events.append(
                _event(
                    event_type=event_type,
                    case=case,
                    effective_at=fill.filled_at,
                    trade_date=trade_date,
                    settlement_date=terms.moment(
                        SettlementMomentKind.SELL_CASH_SETTLEMENT
                    ).local_trade_date,
                    suffix=suffix,
                    source_ids=source_ids,
                    source_hashes=source_hashes,
                    postings=(
                        _posting(account_code, "CNY", debit=amount),
                        _posting(LedgerAccountCode.CASH_RECEIVABLE, "CNY", credit=amount),
                    ),
                    security_id=case.security_id,
                    rules=rules,
                )
            )
        net_proceeds = gross - total_cost
        if net_proceeds < 0:
            raise Stage5FillProjectionError("SELL_COST_EXCEEDS_GROSS_PROCEEDS")
        settlement = terms.moment(SettlementMomentKind.SELL_CASH_SETTLEMENT)
        events.append(
            _event(
                event_type=LedgerEventType.TRADE_SETTLEMENT,
                case=case,
                effective_at=settlement.effective_at,
                trade_date=trade_date,
                settlement_date=settlement.local_trade_date,
                suffix="sell_cash_settlement",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(
                        LedgerAccountCode.CASH_SETTLED_UNAVAILABLE,
                        "CNY",
                        debit=net_proceeds,
                    ),
                    _posting(
                        LedgerAccountCode.CASH_RECEIVABLE,
                        "CNY",
                        credit=net_proceeds,
                    ),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
        available = terms.moment(SettlementMomentKind.SELL_CASH_AVAILABLE)
        events.append(
            _event(
                event_type=LedgerEventType.CASH_RELEASE,
                case=case,
                effective_at=available.effective_at,
                trade_date=trade_date,
                settlement_date=available.local_trade_date,
                suffix="sell_cash_available",
                source_ids=source_ids,
                source_hashes=source_hashes,
                postings=(
                    _posting(LedgerAccountCode.CASH_AVAILABLE, "CNY", debit=net_proceeds),
                    _posting(
                        LedgerAccountCode.CASH_SETTLED_UNAVAILABLE,
                        "CNY",
                        credit=net_proceeds,
                    ),
                ),
                security_id=case.security_id,
                rules=rules,
            )
        )
    # Stage 5B's cancelled quantity is approved-but-never-submitted.  The order
    # itself is fully filled, so no SYNTHETIC_ORDER_CANCELLED ledger event exists.
    unsubmitted = projection.unsubmitted_quantity
    value = Stage5FillLedgerProjection(
        events=tuple(events),
        unsubmitted_approved_quantity=unsubmitted,
        unfilled_cancelled_quantity=projection.unfilled_cancelled_quantity,
        reason_codes=("EXACT_CONSTRAINED_FILL_PROJECTED",),
        projection_hash=_hash("0" * 64),
    )
    projected = value.to_json_value()
    projected["projection_hash"] = None
    return Stage5FillLedgerProjection(
        events=value.events,
        unsubmitted_approved_quantity=unsubmitted,
        unfilled_cancelled_quantity=projection.unfilled_cancelled_quantity,
        reason_codes=value.reason_codes,
        projection_hash=_hash(canonical_sha256(projected)),
    )
