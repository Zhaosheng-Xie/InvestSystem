"""Provider-neutral in-memory append-only double-entry ledger for Stage 5C."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.models import CanonicalModel, HashDigest

from .stage5_decimal import with_stage5_decimal_context

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class LedgerEventType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    CASH_RESERVATION = "CASH_RESERVATION"
    CASH_RELEASE = "CASH_RELEASE"
    SYNTHETIC_ORDER_ACCEPTED = "SYNTHETIC_ORDER_ACCEPTED"
    SYNTHETIC_ORDER_CANCELLED = "SYNTHETIC_ORDER_CANCELLED"
    TRADE_FILL = "TRADE_FILL"
    FEE = "FEE"
    TAX = "TAX"
    TRADE_SETTLEMENT = "TRADE_SETTLEMENT"
    SECURITY_AVAILABILITY = "SECURITY_AVAILABILITY"
    CASH_DIVIDEND = "CASH_DIVIDEND"
    SHARE_DISTRIBUTION = "SHARE_DISTRIBUTION"
    SPLIT_OR_CONSOLIDATION = "SPLIT_OR_CONSOLIDATION"
    RIGHTS_OR_ALLOTMENT = "RIGHTS_OR_ALLOTMENT"
    DELISTING_OR_CASH_OUT = "DELISTING_OR_CASH_OUT"
    MARK_TO_MARKET = "MARK_TO_MARKET"
    EXTERNAL_CASH_FLOW = "EXTERNAL_CASH_FLOW"
    REVERSAL = "REVERSAL"
    REPLACEMENT = "REPLACEMENT"


class LedgerAccountCode(StrEnum):
    CASH_AVAILABLE = "CASH_AVAILABLE"
    CASH_RESERVED = "CASH_RESERVED"
    CASH_RECEIVABLE = "CASH_RECEIVABLE"
    CASH_SETTLED_UNAVAILABLE = "CASH_SETTLED_UNAVAILABLE"
    CASH_PAYABLE = "CASH_PAYABLE"
    SECURITY_COST = "SECURITY_COST"
    FEE_EXPENSE = "FEE_EXPENSE"
    TAX_EXPENSE = "TAX_EXPENSE"
    TRADE_CLEARING = "TRADE_CLEARING"
    OPENING_CONTROL = "OPENING_CONTROL"
    SECURITY_UNSETTLED = "SECURITY_UNSETTLED"
    SECURITY_UNSELLABLE = "SECURITY_UNSELLABLE"
    SECURITY_SELLABLE = "SECURITY_SELLABLE"
    SECURITY_CONTROL = "SECURITY_CONTROL"


class LedgerReplayStatus(StrEnum):
    RECONCILED = "RECONCILED"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


STAGE5C_LEDGER_PRIORITY: dict[LedgerEventType, int] = {
    LedgerEventType.REVERSAL: 5,
    LedgerEventType.OPENING_BALANCE: 10,
    LedgerEventType.CASH_RESERVATION: 20,
    LedgerEventType.SYNTHETIC_ORDER_ACCEPTED: 30,
    LedgerEventType.TRADE_FILL: 40,
    LedgerEventType.FEE: 50,
    LedgerEventType.TAX: 51,
    LedgerEventType.SYNTHETIC_ORDER_CANCELLED: 60,
    LedgerEventType.CASH_RELEASE: 70,
    LedgerEventType.TRADE_SETTLEMENT: 80,
    LedgerEventType.SECURITY_AVAILABILITY: 90,
    LedgerEventType.REPLACEMENT: 95,
    LedgerEventType.CASH_DIVIDEND: 100,
    LedgerEventType.SHARE_DISTRIBUTION: 101,
    LedgerEventType.SPLIT_OR_CONSOLIDATION: 102,
    LedgerEventType.RIGHTS_OR_ALLOTMENT: 103,
    LedgerEventType.DELISTING_OR_CASH_OUT: 104,
    LedgerEventType.MARK_TO_MARKET: 105,
    LedgerEventType.EXTERNAL_CASH_FLOW: 106,
}

_STAGE5C_SUPPORTED_EVENTS = {
    LedgerEventType.OPENING_BALANCE,
    LedgerEventType.CASH_RESERVATION,
    LedgerEventType.CASH_RELEASE,
    LedgerEventType.SYNTHETIC_ORDER_ACCEPTED,
    LedgerEventType.SYNTHETIC_ORDER_CANCELLED,
    LedgerEventType.TRADE_FILL,
    LedgerEventType.FEE,
    LedgerEventType.TAX,
    LedgerEventType.TRADE_SETTLEMENT,
    LedgerEventType.SECURITY_AVAILABILITY,
    LedgerEventType.REVERSAL,
    LedgerEventType.REPLACEMENT,
}

_CNY_ACCOUNTS = {
    LedgerAccountCode.CASH_AVAILABLE,
    LedgerAccountCode.CASH_RESERVED,
    LedgerAccountCode.CASH_RECEIVABLE,
    LedgerAccountCode.CASH_SETTLED_UNAVAILABLE,
    LedgerAccountCode.CASH_PAYABLE,
    LedgerAccountCode.SECURITY_COST,
    LedgerAccountCode.FEE_EXPENSE,
    LedgerAccountCode.TAX_EXPENSE,
    LedgerAccountCode.TRADE_CLEARING,
    LedgerAccountCode.OPENING_CONTROL,
}
_SECURITY_QUANTITY_ACCOUNTS = {
    LedgerAccountCode.SECURITY_UNSETTLED,
    LedgerAccountCode.SECURITY_UNSELLABLE,
    LedgerAccountCode.SECURITY_SELLABLE,
    LedgerAccountCode.SECURITY_CONTROL,
}


def _id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid ASCII ID")
    return value


def _decimal(field_name: str, value: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact decimal string")
    result = Decimal(value)
    if non_negative and result < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return result


def _number(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


@dataclass(frozen=True, slots=True)
class LedgerPosting(CanonicalModel):
    account: LedgerAccountCode
    currency_or_security: str
    debit: str
    credit: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, LedgerAccountCode):
            raise TypeError("account must be LedgerAccountCode")
        _id("currency_or_security", self.currency_or_security)
        debit = _decimal("debit", self.debit, non_negative=True)
        credit = _decimal("credit", self.credit, non_negative=True)
        if debit > 0 and credit > 0:
            raise ValueError("one posting row cannot debit and credit simultaneously")
        if debit == 0 and credit == 0:
            raise ValueError("zero posting rows are forbidden")


@dataclass(frozen=True, slots=True)
class LedgerLotEffect(CanonicalModel):
    lot_id: str
    security_id: str
    quantity_delta: int
    sellable_quantity_delta: int
    full_cost_delta: str
    acquired_at: datetime | None
    governing_market_rule_hash: HashDigest | None
    source_fill_id: str | None

    def __post_init__(self) -> None:
        _id("lot_id", self.lot_id)
        _id("security_id", self.security_id)
        if isinstance(self.quantity_delta, bool) or not isinstance(self.quantity_delta, int):
            raise TypeError("quantity_delta must be an integer")
        if isinstance(self.sellable_quantity_delta, bool) or not isinstance(
            self.sellable_quantity_delta, int
        ):
            raise TypeError("sellable_quantity_delta must be an integer")
        cost = _decimal("full_cost_delta", self.full_cost_delta)
        if self.quantity_delta == 0 and self.sellable_quantity_delta == 0 and cost == 0:
            raise ValueError("lot effects must change quantity, sellability, or full cost")
        if self.acquired_at is not None:
            object.__setattr__(
                self,
                "acquired_at",
                normalize_utc(self.acquired_at, field_name="acquired_at"),
            )
        if self.governing_market_rule_hash is not None and not isinstance(
            self.governing_market_rule_hash, HashDigest
        ):
            raise TypeError("governing_market_rule_hash must be HashDigest")
        if self.source_fill_id is not None:
            _id("source_fill_id", self.source_fill_id)
        if self.quantity_delta > 0 and (
            self.acquired_at is None or self.governing_market_rule_hash is None
        ):
            raise ValueError(
                "positive lot creation requires acquisition and governing-rule identity"
            )


@dataclass(frozen=True, slots=True)
class LedgerEvent(CanonicalModel):
    ledger_event_id: str
    idempotency_key: str
    event_type: LedgerEventType
    event_type_priority: int
    strategy_id: str
    account_fixture_id: str
    security_id: str | None
    effective_at: datetime
    trade_date: str | None
    settlement_date: str | None
    source_object_ids: tuple[str, ...]
    source_hashes: tuple[HashDigest, ...]
    postings: tuple[LedgerPosting, ...]
    lot_effects: tuple[LedgerLotEffect, ...]
    rule_ids: tuple[str, ...]
    rule_versions: tuple[str, ...]
    rule_hashes: tuple[HashDigest, ...]
    supersedes_or_reversal_of: str | None
    declared_canonical_hash: HashDigest

    def __post_init__(self) -> None:
        for name in ("ledger_event_id", "idempotency_key", "strategy_id", "account_fixture_id"):
            _id(name, getattr(self, name))
        if not isinstance(self.event_type, LedgerEventType):
            raise TypeError("event_type must be LedgerEventType")
        if self.event_type_priority != STAGE5C_LEDGER_PRIORITY[self.event_type]:
            raise ValueError("event_type_priority must match the versioned Stage 5C mapping")
        if self.security_id is not None:
            _id("security_id", self.security_id)
        object.__setattr__(
            self,
            "effective_at",
            normalize_utc(self.effective_at, field_name="effective_at"),
        )
        for name in ("trade_date", "settlement_date"):
            value = getattr(self, name)
            if value is not None:
                try:
                    datetime.strptime(value, "%Y-%m-%d")
                except ValueError as error:
                    raise ValueError(f"{name} must use YYYY-MM-DD") from error
        source_ids = tuple(self.source_object_ids)
        for value in source_ids:
            _id("source_object_ids", value)
        object.__setattr__(self, "source_object_ids", source_ids)
        source_hashes = tuple(self.source_hashes)
        if any(not isinstance(value, HashDigest) for value in source_hashes):
            raise TypeError("source_hashes must contain HashDigest values")
        object.__setattr__(self, "source_hashes", source_hashes)
        postings = tuple(self.postings)
        if any(not isinstance(value, LedgerPosting) for value in postings):
            raise TypeError("postings must contain LedgerPosting values")
        object.__setattr__(self, "postings", postings)
        effects = tuple(self.lot_effects)
        if any(not isinstance(value, LedgerLotEffect) for value in effects):
            raise TypeError("lot_effects must contain LedgerLotEffect values")
        object.__setattr__(self, "lot_effects", effects)
        rule_ids = tuple(self.rule_ids)
        rule_versions = tuple(self.rule_versions)
        rule_hashes = tuple(self.rule_hashes)
        if not (len(rule_ids) == len(rule_versions) == len(rule_hashes)):
            raise ValueError("rule identity arrays must have equal lengths")
        for value in (*rule_ids, *rule_versions):
            if not isinstance(value, str) or not value:
                raise ValueError("rule identities must be non-empty strings")
        if any(not isinstance(value, HashDigest) for value in rule_hashes):
            raise TypeError("rule_hashes must contain HashDigest values")
        object.__setattr__(self, "rule_ids", rule_ids)
        object.__setattr__(self, "rule_versions", rule_versions)
        object.__setattr__(self, "rule_hashes", rule_hashes)
        if self.supersedes_or_reversal_of is not None:
            _id("supersedes_or_reversal_of", self.supersedes_or_reversal_of)
        if not isinstance(self.declared_canonical_hash, HashDigest):
            raise TypeError("declared_canonical_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class LedgerBalance(CanonicalModel):
    account: LedgerAccountCode
    currency_or_security: str
    debit_less_credit: str


@dataclass(frozen=True, slots=True)
class DerivedLedgerLot(CanonicalModel):
    lot_id: str
    security_id: str
    acquired_at: datetime
    original_quantity: int
    remaining_quantity: int
    sellable_quantity: int
    remaining_full_cost: str
    governing_market_rule_hash: HashDigest
    source_fill_id: str | None


@dataclass(frozen=True, slots=True)
class DerivedLedgerState(CanonicalModel):
    balances: tuple[LedgerBalance, ...]
    lots: tuple[DerivedLedgerLot, ...]
    journal_head_hash: HashDigest
    available_cash: str
    reserved_cash: str
    unsettled_cash_receivable: str
    unsettled_cash_payable: str
    settled_unavailable_cash: str

    def actual_quantity(self, security_id: str) -> int:
        return sum(lot.remaining_quantity for lot in self.lots if lot.security_id == security_id)

    def sellable_quantity(self, security_id: str) -> int:
        return sum(lot.sellable_quantity for lot in self.lots if lot.security_id == security_id)


@dataclass(frozen=True, slots=True)
class LedgerReplayResult(CanonicalModel):
    status: LedgerReplayStatus
    reason_codes: tuple[str, ...]
    accepted_events: tuple[LedgerEvent, ...]
    derived_state: DerivedLedgerState | None
    in_memory_reconciled: bool
    persists_state: bool = field(default=False, init=False)
    atomic_durable_commit: bool = field(default=False, init=False)
    # Acquisition fees/taxes are separate expense postings while the lot's
    # ``full_cost`` includes them.  Stage 5C can validate each event locally,
    # but the approved Stage 5D P&L/account model is required before these two
    # views may be claimed to reconcile globally.
    full_cost_to_security_cost_reconciled: bool = field(default=False, init=False)


def ledger_event_content_sha256(value: LedgerEvent) -> str:
    projected = value.to_json_value()
    del projected["declared_canonical_hash"]
    return canonical_sha256(projected)


def bind_ledger_event(value: LedgerEvent) -> LedgerEvent:
    return replace(
        value,
        declared_canonical_hash=HashDigest(
            algorithm="sha256",
            value=ledger_event_content_sha256(value),
        ),
    )


def _postings_balance(event: LedgerEvent) -> bool:
    by_unit: dict[str, tuple[Decimal, Decimal]] = {}
    for posting in event.postings:
        debit, credit = by_unit.get(posting.currency_or_security, (Decimal(0), Decimal(0)))
        by_unit[posting.currency_or_security] = (
            debit + Decimal(posting.debit),
            credit + Decimal(posting.credit),
        )
    return all(debit == credit for debit, credit in by_unit.values())


def _inverse_matches(original: LedgerEvent, reversal: LedgerEvent) -> bool:
    original_rows = sorted(
        (
            row.account.value,
            row.currency_or_security,
            Decimal(row.debit),
            Decimal(row.credit),
        )
        for row in original.postings
    )
    reversal_rows = sorted(
        (
            row.account.value,
            row.currency_or_security,
            Decimal(row.credit),
            Decimal(row.debit),
        )
        for row in reversal.postings
    )
    original_effects = sorted(
        (
            effect.lot_id,
            effect.quantity_delta,
            effect.sellable_quantity_delta,
            Decimal(effect.full_cost_delta),
        )
        for effect in original.lot_effects
    )
    reversal_effects = sorted(
        (
            effect.lot_id,
            -effect.quantity_delta,
            -effect.sellable_quantity_delta,
            -Decimal(effect.full_cost_delta),
        )
        for effect in reversal.lot_effects
    )
    return original_rows == reversal_rows and original_effects == reversal_effects


@dataclass(slots=True)
class _LotAccumulator:
    security_id: str
    acquired_at: datetime
    original_quantity: int
    remaining_quantity: int
    sellable_quantity: int
    remaining_full_cost: Decimal
    governing_market_rule_hash: HashDigest
    source_fill_id: str | None


def _signed_posting(
    event: LedgerEvent,
    account: LedgerAccountCode,
    unit: str,
) -> Decimal:
    return sum(
        (
            Decimal(posting.debit) - Decimal(posting.credit)
            for posting in event.postings
            if posting.account is account and posting.currency_or_security == unit
        ),
        Decimal(0),
    )


def _posting_accounts(event: LedgerEvent) -> set[LedgerAccountCode]:
    return {posting.account for posting in event.postings}


def _is_positive_transfer(
    event: LedgerEvent,
    debit_account: LedgerAccountCode,
    credit_account: LedgerAccountCode,
    unit: str,
) -> bool:
    debit = _signed_posting(event, debit_account, unit)
    credit = _signed_posting(event, credit_account, unit)
    return (
        len(event.postings) == 2
        and _posting_accounts(event) == {debit_account, credit_account}
        and debit > 0
        and credit == -debit
    )


def _provenance_failure(event: LedgerEvent) -> str | None:
    if not event.source_object_ids or not event.source_hashes:
        return "LEDGER_EVENT_SOURCE_PROVENANCE_REQUIRED"
    if not event.rule_ids or not event.rule_versions or not event.rule_hashes:
        return "LEDGER_EVENT_RULE_PROVENANCE_REQUIRED"
    return None


def _posting_unit_failure(
    event: LedgerEvent,
    *,
    semantic_type: LedgerEventType | None = None,
) -> str | None:
    scoped_type = semantic_type or event.event_type
    security_units: set[str] = set()
    for posting in event.postings:
        amount = Decimal(posting.debit) + Decimal(posting.credit)
        if posting.account in _CNY_ACCOUNTS:
            if posting.currency_or_security != "CNY":
                return "CNY_LEDGER_ACCOUNT_REQUIRES_CNY_UNIT"
        elif posting.account in _SECURITY_QUANTITY_ACCOUNTS:
            security_units.add(posting.currency_or_security)
            if amount != amount.to_integral_value():
                return "SECURITY_QUANTITY_POSTING_MUST_BE_EXACT_INTEGER"
        else:  # pragma: no cover - exhaustive protection for future enum changes
            return "LEDGER_ACCOUNT_UNIT_POLICY_MISSING"
    if scoped_type is not LedgerEventType.OPENING_BALANCE:
        if event.security_id is None:
            return "NON_OPENING_EVENT_REQUIRES_SECURITY_SCOPE"
        if any(unit != event.security_id for unit in security_units):
            return "SECURITY_POSTING_EVENT_SCOPE_MISMATCH"
    if scoped_type is LedgerEventType.OPENING_BALANCE and event.security_id is not None:
        if any(unit != event.security_id for unit in security_units):
            return "SECURITY_POSTING_EVENT_SCOPE_MISMATCH"
    for effect in event.lot_effects:
        if scoped_type is not LedgerEventType.OPENING_BALANCE and (
            event.security_id is None or effect.security_id != event.security_id
        ):
            return "LOT_EFFECT_EVENT_SCOPE_MISMATCH"
        if (
            effect.quantity_delta != 0 or effect.sellable_quantity_delta != 0
        ) and effect.security_id not in security_units:
            return "LOT_EFFECT_REQUIRES_MATCHING_SECURITY_POSTING"
    return None


def _opening_schema_failure(event: LedgerEvent) -> str | None:
    allowed = {
        LedgerAccountCode.CASH_AVAILABLE,
        LedgerAccountCode.CASH_RESERVED,
        LedgerAccountCode.CASH_RECEIVABLE,
        LedgerAccountCode.CASH_PAYABLE,
        LedgerAccountCode.SECURITY_COST,
        LedgerAccountCode.OPENING_CONTROL,
        LedgerAccountCode.SECURITY_UNSETTLED,
        LedgerAccountCode.SECURITY_UNSELLABLE,
        LedgerAccountCode.SECURITY_SELLABLE,
        LedgerAccountCode.SECURITY_CONTROL,
    }
    if not event.postings or not _posting_accounts(event) <= allowed:
        return "OPENING_BALANCE_POSTING_SCHEMA_INVALID"
    if len({effect.lot_id for effect in event.lot_effects}) != len(event.lot_effects):
        return "OPENING_BALANCE_LOT_ID_DUPLICATE"
    for effect in event.lot_effects:
        if (
            effect.quantity_delta <= 0
            or not 0 <= effect.sellable_quantity_delta <= effect.quantity_delta
            or Decimal(effect.full_cost_delta) < 0
            or effect.source_fill_id is not None
        ):
            return "OPENING_BALANCE_LOT_EFFECT_SCHEMA_INVALID"
    declared_cost = _signed_posting(event, LedgerAccountCode.SECURITY_COST, "CNY")
    lot_cost = sum(
        (Decimal(effect.full_cost_delta) for effect in event.lot_effects),
        Decimal(0),
    )
    if declared_cost != lot_cost:
        return "OPENING_LOT_COST_TO_SECURITY_COST_MISMATCH"
    return None


def _fill_source(event: LedgerEvent) -> str | None:
    values = {
        effect.source_fill_id for effect in event.lot_effects if effect.source_fill_id is not None
    }
    if len(values) != 1:
        return None
    return next(iter(values))


def _fifo_effects_match(
    lots: dict[str, _LotAccumulator],
    security_id: str,
    quantity: int,
    effects: tuple[LedgerLotEffect, ...],
) -> bool:
    remaining = quantity
    expected: dict[str, int] = {}
    for lot_id, lot in sorted(lots.items(), key=lambda item: (item[1].acquired_at, item[0])):
        if lot.security_id != security_id or lot.sellable_quantity <= 0:
            continue
        take = min(remaining, lot.sellable_quantity)
        if take > 0:
            expected[lot_id] = take
            remaining -= take
        if remaining == 0:
            break
    if remaining != 0:
        return False
    actual: dict[str, int] = {}
    for effect in effects:
        if effect.quantity_delta >= 0 or effect.sellable_quantity_delta != effect.quantity_delta:
            return False
        if effect.lot_id in actual:
            return False
        actual[effect.lot_id] = -effect.quantity_delta
    return actual == expected


def _trade_fill_schema_failure(
    event: LedgerEvent,
    lots: dict[str, _LotAccumulator],
    seen_fill_sources: set[str],
    *,
    replacement_of: LedgerEvent | None,
) -> tuple[str | None, str | None]:
    if event.security_id is None or not event.lot_effects:
        return "TRADE_FILL_SECURITY_AND_LOT_EFFECT_REQUIRED", None
    source_fill_id = _fill_source(event)
    if source_fill_id is None or source_fill_id not in event.source_object_ids:
        return "TRADE_FILL_SOURCE_IDENTITY_INVALID", None
    replacement_source = _fill_source(replacement_of) if replacement_of is not None else None
    if source_fill_id in seen_fill_sources and source_fill_id != replacement_source:
        return "SOURCE_FILL_ID_REUSED", None

    security_id = event.security_id
    unsettled = _signed_posting(event, LedgerAccountCode.SECURITY_UNSETTLED, security_id)
    sellable = _signed_posting(event, LedgerAccountCode.SECURITY_SELLABLE, security_id)
    control = _signed_posting(event, LedgerAccountCode.SECURITY_CONTROL, security_id)
    security_cost = _signed_posting(event, LedgerAccountCode.SECURITY_COST, "CNY")
    accounts = _posting_accounts(event)
    if unsettled > 0 and sellable == 0 and control == -unsettled:
        required = {
            LedgerAccountCode.SECURITY_COST,
            LedgerAccountCode.CASH_PAYABLE,
            LedgerAccountCode.SECURITY_UNSETTLED,
            LedgerAccountCode.SECURITY_CONTROL,
        }
        if len(event.postings) != 4 or accounts != required or len(event.lot_effects) != 1:
            return "BUY_FILL_POSTING_OR_LOT_SCHEMA_INVALID", None
        payable = _signed_posting(event, LedgerAccountCode.CASH_PAYABLE, "CNY")
        effect = event.lot_effects[0]
        if (
            security_cost <= 0
            or payable != -security_cost
            or unsettled != unsettled.to_integral_value()
            or effect.quantity_delta != int(unsettled)
            or effect.sellable_quantity_delta != 0
            or Decimal(effect.full_cost_delta) != security_cost
            or effect.acquired_at is None
            or effect.governing_market_rule_hash is None
            or effect.lot_id in lots
            and replacement_of is None
        ):
            return "BUY_FILL_POSTING_OR_LOT_SCHEMA_INVALID", None
        return None, source_fill_id

    if sellable < 0 and unsettled == 0 and control == -sellable:
        required = {
            LedgerAccountCode.CASH_RECEIVABLE,
            LedgerAccountCode.TRADE_CLEARING,
            LedgerAccountCode.SECURITY_SELLABLE,
            LedgerAccountCode.SECURITY_CONTROL,
        }
        allowed = required | {LedgerAccountCode.SECURITY_COST}
        expected_posting_count = 6 if LedgerAccountCode.SECURITY_COST in accounts else 4
        if (
            len(event.postings) != expected_posting_count
            or not required <= accounts
            or not accounts <= allowed
        ):
            return "SELL_FILL_POSTING_SCHEMA_INVALID", None
        quantity = int(-sellable)
        receivable = _signed_posting(event, LedgerAccountCode.CASH_RECEIVABLE, "CNY")
        clearing = _signed_posting(event, LedgerAccountCode.TRADE_CLEARING, "CNY")
        disposed_cost = -security_cost
        effect_cost = -sum(
            (Decimal(effect.full_cost_delta) for effect in event.lot_effects),
            Decimal(0),
        )
        if (
            receivable <= 0
            or security_cost > 0
            or clearing != disposed_cost - receivable
            or effect_cost != disposed_cost
            or not _fifo_effects_match(lots, security_id, quantity, event.lot_effects)
        ):
            return "SELL_FILL_FIFO_POSTING_OR_COST_SCHEMA_INVALID", None
        return None, source_fill_id
    return "TRADE_FILL_SIDE_OR_SECURITY_POSTING_SCHEMA_INVALID", None


def _fee_or_tax_schema_failure(
    event: LedgerEvent,
    semantic_type: LedgerEventType,
    lots: dict[str, _LotAccumulator],
    seen_fill_sources: set[str],
) -> str | None:
    expense_account = (
        LedgerAccountCode.FEE_EXPENSE
        if semantic_type is LedgerEventType.FEE
        else LedgerAccountCode.TAX_EXPENSE
    )
    expense = _signed_posting(event, expense_account, "CNY")
    if expense <= 0:
        return "FEE_OR_TAX_AMOUNT_MUST_BE_POSITIVE"
    accounts = _posting_accounts(event)
    if accounts == {expense_account, LedgerAccountCode.CASH_PAYABLE}:
        if (
            len(event.postings) != 2
            or _signed_posting(event, LedgerAccountCode.CASH_PAYABLE, "CNY") != -expense
        ):
            return "BUY_FEE_OR_TAX_POSTING_SCHEMA_INVALID"
        if len(event.lot_effects) != 1:
            return "BUY_FEE_OR_TAX_LOT_COST_EFFECT_REQUIRED"
        effect = event.lot_effects[0]
        lot = lots.get(effect.lot_id)
        if (
            lot is None
            or effect.quantity_delta != 0
            or effect.sellable_quantity_delta != 0
            or Decimal(effect.full_cost_delta) != expense
            or effect.source_fill_id is None
            or effect.source_fill_id not in seen_fill_sources
            or effect.source_fill_id != lot.source_fill_id
            or effect.source_fill_id not in event.source_object_ids
        ):
            return "BUY_FEE_OR_TAX_LOT_COST_EFFECT_INVALID"
        return None
    if accounts == {expense_account, LedgerAccountCode.CASH_RECEIVABLE}:
        if (
            len(event.postings) != 2
            or _signed_posting(event, LedgerAccountCode.CASH_RECEIVABLE, "CNY") != -expense
            or event.lot_effects
            or not seen_fill_sources.intersection(event.source_object_ids)
        ):
            return "SELL_FEE_OR_TAX_POSTING_SCHEMA_INVALID"
        return None
    return "FEE_OR_TAX_COUNTERACCOUNT_SCHEMA_INVALID"


def _ordinary_semantic_failure(
    event: LedgerEvent,
    semantic_type: LedgerEventType,
    lots: dict[str, _LotAccumulator],
    seen_fill_sources: set[str],
    *,
    replacement_of: LedgerEvent | None = None,
) -> tuple[str | None, str | None]:
    if semantic_type is LedgerEventType.OPENING_BALANCE:
        return _opening_schema_failure(event), None
    if semantic_type in {
        LedgerEventType.SYNTHETIC_ORDER_ACCEPTED,
        LedgerEventType.SYNTHETIC_ORDER_CANCELLED,
    }:
        if event.postings or event.lot_effects:
            return "ORDER_AUDIT_EVENT_MUST_NOT_MUTATE_BALANCES", None
        return None, None
    if semantic_type is LedgerEventType.CASH_RESERVATION:
        if event.lot_effects or not _is_positive_transfer(
            event,
            LedgerAccountCode.CASH_RESERVED,
            LedgerAccountCode.CASH_AVAILABLE,
            "CNY",
        ):
            return "CASH_RESERVATION_POSTING_SCHEMA_INVALID", None
        return None, None
    if semantic_type is LedgerEventType.CASH_RELEASE:
        valid = _is_positive_transfer(
            event,
            LedgerAccountCode.CASH_AVAILABLE,
            LedgerAccountCode.CASH_RESERVED,
            "CNY",
        ) or _is_positive_transfer(
            event,
            LedgerAccountCode.CASH_AVAILABLE,
            LedgerAccountCode.CASH_SETTLED_UNAVAILABLE,
            "CNY",
        )
        if event.lot_effects or not valid:
            return "CASH_RELEASE_POSTING_SCHEMA_INVALID", None
        return None, None
    if semantic_type is LedgerEventType.TRADE_FILL:
        return _trade_fill_schema_failure(
            event,
            lots,
            seen_fill_sources,
            replacement_of=replacement_of,
        )
    if semantic_type in {LedgerEventType.FEE, LedgerEventType.TAX}:
        return _fee_or_tax_schema_failure(event, semantic_type, lots, seen_fill_sources), None
    if semantic_type is LedgerEventType.TRADE_SETTLEMENT:
        valid = (
            _is_positive_transfer(
                event,
                LedgerAccountCode.CASH_PAYABLE,
                LedgerAccountCode.CASH_RESERVED,
                "CNY",
            )
            or _is_positive_transfer(
                event,
                LedgerAccountCode.CASH_SETTLED_UNAVAILABLE,
                LedgerAccountCode.CASH_RECEIVABLE,
                "CNY",
            )
            or (
                event.security_id is not None
                and _is_positive_transfer(
                    event,
                    LedgerAccountCode.SECURITY_UNSELLABLE,
                    LedgerAccountCode.SECURITY_UNSETTLED,
                    event.security_id,
                )
            )
        )
        if event.lot_effects or not valid:
            return "TRADE_SETTLEMENT_POSTING_SCHEMA_INVALID", None
        return None, None
    if semantic_type is LedgerEventType.SECURITY_AVAILABILITY:
        if event.security_id is None or not _is_positive_transfer(
            event,
            LedgerAccountCode.SECURITY_SELLABLE,
            LedgerAccountCode.SECURITY_UNSELLABLE,
            event.security_id,
        ):
            return "SECURITY_AVAILABILITY_POSTING_SCHEMA_INVALID", None
        quantity = int(
            _signed_posting(event, LedgerAccountCode.SECURITY_SELLABLE, event.security_id)
        )
        if not event.lot_effects or any(
            effect.quantity_delta != 0
            or effect.sellable_quantity_delta <= 0
            or Decimal(effect.full_cost_delta) != 0
            or effect.lot_id not in lots
            for effect in event.lot_effects
        ):
            return "SECURITY_AVAILABILITY_LOT_EFFECT_SCHEMA_INVALID", None
        if sum(effect.sellable_quantity_delta for effect in event.lot_effects) != quantity:
            return "SECURITY_AVAILABILITY_LOT_QUANTITY_MISMATCH", None
        return None, None
    return "STAGE5C_EVENT_SEMANTIC_POLICY_MISSING", None


def _blocked(
    status: LedgerReplayStatus,
    reason: str,
    accepted: list[LedgerEvent],
) -> LedgerReplayResult:
    return LedgerReplayResult(
        status=status,
        reason_codes=(reason,),
        accepted_events=tuple(accepted),
        derived_state=None,
        in_memory_reconciled=False,
    )


@with_stage5_decimal_context
def replay_stage5c_ledger(events: tuple[LedgerEvent, ...]) -> LedgerReplayResult:
    """Sort, deduplicate and atomically replay an in-memory Stage 5C journal."""

    ordered = sorted(
        tuple(events),
        key=lambda item: (
            item.effective_at,
            item.event_type_priority,
            item.ledger_event_id,
        ),
    )
    by_key: dict[str, LedgerEvent] = {}
    by_event_id: dict[str, LedgerEvent] = {}
    unique: list[LedgerEvent] = []
    for event in ordered:
        if event.declared_canonical_hash.value != ledger_event_content_sha256(event):
            return _blocked(LedgerReplayStatus.PRECHECK_BLOCKED, "LEDGER_EVENT_HASH_DRIFT", [])
        previous = by_key.get(event.idempotency_key)
        if previous is not None:
            if previous.declared_canonical_hash == event.declared_canonical_hash:
                continue
            return _blocked(
                LedgerReplayStatus.PRECHECK_BLOCKED,
                "IDEMPOTENCY_KEY_CONTENT_CONFLICT",
                [],
            )
        by_key[event.idempotency_key] = event
        if event.ledger_event_id in by_event_id:
            return _blocked(
                LedgerReplayStatus.PRECHECK_BLOCKED,
                "LEDGER_EVENT_ID_DUPLICATE",
                [],
            )
        by_event_id[event.ledger_event_id] = event
        unique.append(event)

    if not unique:
        return _blocked(LedgerReplayStatus.PRECHECK_BLOCKED, "LEDGER_JOURNAL_EMPTY", [])
    if len({(event.strategy_id, event.account_fixture_id) for event in unique}) != 1:
        return _blocked(
            LedgerReplayStatus.PRECHECK_BLOCKED,
            "LEDGER_STRATEGY_OR_ACCOUNT_SCOPE_MIXED",
            [],
        )
    opening_events = tuple(
        event for event in unique if event.event_type is LedgerEventType.OPENING_BALANCE
    )
    if len(opening_events) != 1 or unique[0] is not opening_events[0]:
        return _blocked(
            LedgerReplayStatus.PRECHECK_BLOCKED,
            "EXACTLY_ONE_FIRST_OPENING_BALANCE_REQUIRED",
            [],
        )

    balances: dict[tuple[LedgerAccountCode, str], Decimal] = {}
    lots: dict[str, _LotAccumulator] = {}
    accepted: list[LedgerEvent] = []
    event_by_id: dict[str, LedgerEvent] = {}
    reversed_ids: set[str] = set()
    reversal_by_original: dict[str, str] = {}
    replacement_by_reversal: dict[str, str] = {}
    seen_fill_sources: set[str] = set()
    for event in unique:
        if event.event_type not in _STAGE5C_SUPPORTED_EVENTS:
            return _blocked(
                LedgerReplayStatus.PRECHECK_BLOCKED,
                f"STAGE5D_EVENT_NOT_IMPLEMENTED:{event.event_type.value}",
                [],
            )
        provenance_failure = _provenance_failure(event)
        if provenance_failure is not None:
            return _blocked(
                LedgerReplayStatus.PRECHECK_BLOCKED,
                provenance_failure,
                [],
            )
        if not _postings_balance(event):
            status = (
                LedgerReplayStatus.PRECHECK_BLOCKED
                if event.event_type is LedgerEventType.OPENING_BALANCE
                else LedgerReplayStatus.RECONCILIATION_BLOCKED
            )
            return _blocked(status, "DOUBLE_ENTRY_IMBALANCE", accepted)
        semantic_type = event.event_type
        replacement_original: LedgerEvent | None = None
        new_fill_source: str | None = None
        if event.event_type is LedgerEventType.REVERSAL:
            original = event_by_id.get(event.supersedes_or_reversal_of or "")
            if (
                original is None
                or original.event_type in {LedgerEventType.REVERSAL, LedgerEventType.REPLACEMENT}
                or original.ledger_event_id in reversed_ids
                or not _inverse_matches(original, event)
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "REVERSAL_MUST_EXACTLY_INVERT_ONE_ACTIVE_EVENT",
                    accepted,
                )
            if (
                event.strategy_id,
                event.account_fixture_id,
                event.security_id,
                event.source_object_ids,
                event.source_hashes,
                event.rule_ids,
                event.rule_versions,
                event.rule_hashes,
            ) != (
                original.strategy_id,
                original.account_fixture_id,
                original.security_id,
                original.source_object_ids,
                original.source_hashes,
                original.rule_ids,
                original.rule_versions,
                original.rule_hashes,
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "REVERSAL_SCOPE_OR_PROVENANCE_MISMATCH",
                    accepted,
                )
            reversed_ids.add(original.ledger_event_id)
            reversal_by_original[original.ledger_event_id] = event.ledger_event_id
            semantic_type = original.event_type
        elif event.event_type is LedgerEventType.REPLACEMENT:
            reversal = event_by_id.get(event.supersedes_or_reversal_of or "")
            original = (
                event_by_id.get(reversal.supersedes_or_reversal_of or "")
                if reversal is not None
                else None
            )
            if (
                reversal is None
                or reversal.event_type is not LedgerEventType.REVERSAL
                or original is None
                or reversal.ledger_event_id in replacement_by_reversal
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "REPLACEMENT_REQUIRES_ONE_UNREPLACED_PRIOR_REVERSAL",
                    accepted,
                )
            if (
                event.strategy_id,
                event.account_fixture_id,
                event.security_id,
            ) != (
                original.strategy_id,
                original.account_fixture_id,
                original.security_id,
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "REPLACEMENT_SCOPE_MISMATCH",
                    accepted,
                )
            replacement_by_reversal[reversal.ledger_event_id] = event.ledger_event_id
            semantic_type = original.event_type
            replacement_original = original
        elif event.supersedes_or_reversal_of is not None:
            return _blocked(
                LedgerReplayStatus.PRECHECK_BLOCKED,
                "ORDINARY_EVENT_CANNOT_SUPERSEDE_HISTORY",
                [],
            )

        unit_failure = _posting_unit_failure(event, semantic_type=semantic_type)
        if unit_failure is not None:
            return _blocked(
                (
                    LedgerReplayStatus.PRECHECK_BLOCKED
                    if semantic_type is LedgerEventType.OPENING_BALANCE
                    else LedgerReplayStatus.RECONCILIATION_BLOCKED
                ),
                unit_failure,
                accepted,
            )
        if event.event_type is not LedgerEventType.REVERSAL:
            semantic_failure, new_fill_source = _ordinary_semantic_failure(
                event,
                semantic_type,
                lots,
                seen_fill_sources,
                replacement_of=replacement_original,
            )
            if semantic_failure is not None:
                return _blocked(
                    (
                        LedgerReplayStatus.PRECHECK_BLOCKED
                        if semantic_type is LedgerEventType.OPENING_BALANCE
                        else LedgerReplayStatus.RECONCILIATION_BLOCKED
                    ),
                    semantic_failure,
                    accepted,
                )

        next_balances = dict(balances)
        next_lots = {
            lot_id: _LotAccumulator(
                security_id=lot.security_id,
                acquired_at=lot.acquired_at,
                original_quantity=lot.original_quantity,
                remaining_quantity=lot.remaining_quantity,
                sellable_quantity=lot.sellable_quantity,
                remaining_full_cost=lot.remaining_full_cost,
                governing_market_rule_hash=lot.governing_market_rule_hash,
                source_fill_id=lot.source_fill_id,
            )
            for lot_id, lot in lots.items()
        }
        for posting in event.postings:
            key = (posting.account, posting.currency_or_security)
            next_balances[key] = (
                next_balances.get(key, Decimal(0))
                + Decimal(posting.debit)
                - Decimal(posting.credit)
            )
        for effect in event.lot_effects:
            lot = next_lots.get(effect.lot_id)
            if lot is None:
                if effect.quantity_delta <= 0:
                    return _blocked(
                        LedgerReplayStatus.RECONCILIATION_BLOCKED,
                        "LOT_EFFECT_REFERENCES_UNKNOWN_LOT",
                        accepted,
                    )
                assert effect.acquired_at is not None
                assert effect.governing_market_rule_hash is not None
                lot = _LotAccumulator(
                    security_id=effect.security_id,
                    acquired_at=effect.acquired_at,
                    original_quantity=effect.quantity_delta,
                    remaining_quantity=0,
                    sellable_quantity=0,
                    remaining_full_cost=Decimal(0),
                    governing_market_rule_hash=effect.governing_market_rule_hash,
                    source_fill_id=effect.source_fill_id,
                )
                next_lots[effect.lot_id] = lot
            elif lot.security_id != effect.security_id:
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "LOT_SECURITY_SCOPE_MISMATCH",
                    accepted,
                )
            elif effect.quantity_delta > 0 and event.event_type not in {
                LedgerEventType.REVERSAL,
                LedgerEventType.REPLACEMENT,
            }:
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "IMMUTABLE_LOT_QUANTITY_CANNOT_BE_INCREASED",
                    accepted,
                )
            lot.remaining_quantity += effect.quantity_delta
            lot.sellable_quantity += effect.sellable_quantity_delta
            lot.remaining_full_cost += Decimal(effect.full_cost_delta)
            if (
                lot.remaining_quantity < 0
                or lot.sellable_quantity < 0
                or lot.sellable_quantity > lot.remaining_quantity
                or lot.remaining_full_cost < 0
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "LOT_QUANTITY_OR_COST_IDENTITY_BREACH",
                    accepted,
                )
            if lot.remaining_quantity == 0 and (
                lot.sellable_quantity != 0 or lot.remaining_full_cost != 0
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "ZERO_QUANTITY_LOT_MUST_HAVE_ZERO_SELLABILITY_AND_COST",
                    accepted,
                )

        available = next_balances.get((LedgerAccountCode.CASH_AVAILABLE, "CNY"), Decimal(0))
        reserved = next_balances.get((LedgerAccountCode.CASH_RESERVED, "CNY"), Decimal(0))
        receivable = next_balances.get((LedgerAccountCode.CASH_RECEIVABLE, "CNY"), Decimal(0))
        settled_unavailable = next_balances.get(
            (LedgerAccountCode.CASH_SETTLED_UNAVAILABLE, "CNY"), Decimal(0)
        )
        payable = -next_balances.get((LedgerAccountCode.CASH_PAYABLE, "CNY"), Decimal(0))
        if min(available, reserved, receivable, settled_unavailable, payable) < 0:
            return _blocked(
                LedgerReplayStatus.RECONCILIATION_BLOCKED,
                "NEGATIVE_CASH_RESERVATION_RECEIVABLE_OR_PAYABLE",
                accepted,
            )
        if reserved < payable:
            return _blocked(
                LedgerReplayStatus.RECONCILIATION_BLOCKED,
                "CASH_RESERVATION_BELOW_OPEN_PAYABLE",
                accepted,
            )
        security_cost = next_balances.get((LedgerAccountCode.SECURITY_COST, "CNY"), Decimal(0))
        if security_cost < 0:
            return _blocked(
                LedgerReplayStatus.RECONCILIATION_BLOCKED,
                "NEGATIVE_SECURITY_COST_BALANCE",
                accepted,
            )
        security_ids = {
            unit
            for account, unit in next_balances
            if account
            in {
                LedgerAccountCode.SECURITY_UNSETTLED,
                LedgerAccountCode.SECURITY_UNSELLABLE,
                LedgerAccountCode.SECURITY_SELLABLE,
                LedgerAccountCode.SECURITY_CONTROL,
            }
        } | {lot.security_id for lot in next_lots.values()}
        for security_id in security_ids:
            unsettled = next_balances.get(
                (LedgerAccountCode.SECURITY_UNSETTLED, security_id), Decimal(0)
            )
            unsellable = next_balances.get(
                (LedgerAccountCode.SECURITY_UNSELLABLE, security_id), Decimal(0)
            )
            sellable = next_balances.get(
                (LedgerAccountCode.SECURITY_SELLABLE, security_id), Decimal(0)
            )
            controlled = next_balances.get(
                (LedgerAccountCode.SECURITY_CONTROL, security_id), Decimal(0)
            )
            if min(unsettled, unsellable, sellable) < 0 or (
                unsettled + unsellable + sellable + controlled != 0
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "SECURITY_QUANTITY_IDENTITY_BREACH",
                    accepted,
                )
            lot_quantity = sum(
                lot.remaining_quantity
                for lot in next_lots.values()
                if lot.security_id == security_id
            )
            lot_sellable = sum(
                lot.sellable_quantity
                for lot in next_lots.values()
                if lot.security_id == security_id
            )
            ledger_quantity = unsettled + unsellable + sellable
            if (
                ledger_quantity != ledger_quantity.to_integral_value()
                or sellable != sellable.to_integral_value()
                or Decimal(lot_quantity) != ledger_quantity
                or Decimal(lot_sellable) != sellable
            ):
                return _blocked(
                    LedgerReplayStatus.RECONCILIATION_BLOCKED,
                    "LOT_TO_SECURITY_LEDGER_IDENTITY_BREACH",
                    accepted,
                )
        balances = next_balances
        lots = next_lots
        accepted.append(event)
        event_by_id[event.ledger_event_id] = event
        if new_fill_source is not None:
            seen_fill_sources.add(new_fill_source)

    missing_replacements = set(reversal_by_original.values()) - set(replacement_by_reversal)
    if missing_replacements:
        return _blocked(
            LedgerReplayStatus.RECONCILIATION_BLOCKED,
            "REVERSAL_REQUIRES_EXACTLY_ONE_REPLACEMENT",
            accepted,
        )

    head_hash = HashDigest(
        algorithm="sha256",
        value=canonical_sha256(tuple(event.declared_canonical_hash for event in accepted)),
    )
    state = DerivedLedgerState(
        balances=tuple(
            LedgerBalance(account, unit, _number(amount))
            for (account, unit), amount in sorted(
                balances.items(), key=lambda item: (item[0][0].value, item[0][1])
            )
            if amount != 0
        ),
        lots=tuple(
            DerivedLedgerLot(
                lot_id=lot_id,
                security_id=lot.security_id,
                acquired_at=lot.acquired_at,
                original_quantity=lot.original_quantity,
                remaining_quantity=lot.remaining_quantity,
                sellable_quantity=lot.sellable_quantity,
                remaining_full_cost=_number(lot.remaining_full_cost),
                governing_market_rule_hash=lot.governing_market_rule_hash,
                source_fill_id=lot.source_fill_id,
            )
            for lot_id, lot in sorted(lots.items(), key=lambda item: (item[1].acquired_at, item[0]))
            if lot.remaining_quantity > 0
        ),
        journal_head_hash=head_hash,
        available_cash=_number(balances.get((LedgerAccountCode.CASH_AVAILABLE, "CNY"), Decimal(0))),
        reserved_cash=_number(balances.get((LedgerAccountCode.CASH_RESERVED, "CNY"), Decimal(0))),
        unsettled_cash_receivable=_number(
            balances.get((LedgerAccountCode.CASH_RECEIVABLE, "CNY"), Decimal(0))
        ),
        unsettled_cash_payable=_number(
            -balances.get((LedgerAccountCode.CASH_PAYABLE, "CNY"), Decimal(0))
        ),
        settled_unavailable_cash=_number(
            balances.get((LedgerAccountCode.CASH_SETTLED_UNAVAILABLE, "CNY"), Decimal(0))
        ),
    )
    return LedgerReplayResult(
        status=LedgerReplayStatus.RECONCILED,
        reason_codes=("IN_MEMORY_LEDGER_RECONCILED",),
        accepted_events=tuple(accepted),
        derived_state=state,
        in_memory_reconciled=True,
    )
