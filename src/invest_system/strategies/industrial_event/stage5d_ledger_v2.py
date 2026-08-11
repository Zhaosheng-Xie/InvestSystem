"""Minimal source-driven Stage 5D Ledger V2 kernel.

This module is intentionally narrower than the complete Stage 5D-1 engine.  It
supports an attributed synthetic opening, Stage 5C BUY/SELL fills, their cash
and security settlement transitions, and an explicit no-fill opening.  It is
pure, deterministic, in-memory, and grants no execution or persistence
authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from fractions import Fraction

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.models import CanonicalModel, HashDigest

STAGE5D_V2_SLICE_SCHEMA_VERSION = "0.2.0"


class Stage5DV2EventType(StrEnum):
    OPENING_BALANCE = "OPENING_BALANCE"
    OPENING_POSITION = "OPENING_POSITION"
    BUY_TRADE = "BUY_TRADE"
    SELL_TRADE = "SELL_TRADE"
    BUY_CASH_SETTLEMENT = "BUY_CASH_SETTLEMENT"
    SELL_CASH_SETTLEMENT = "SELL_CASH_SETTLEMENT"
    SELL_CASH_AVAILABLE = "SELL_CASH_AVAILABLE"
    SECURITY_SETTLEMENT = "SECURITY_SETTLEMENT"
    SECURITY_SELLABLE = "SECURITY_SELLABLE"


STAGE5D_V2_EVENT_PRIORITY = {
    Stage5DV2EventType.OPENING_BALANCE: 10,
    Stage5DV2EventType.OPENING_POSITION: 11,
    Stage5DV2EventType.BUY_TRADE: 40,
    Stage5DV2EventType.SELL_TRADE: 40,
    Stage5DV2EventType.BUY_CASH_SETTLEMENT: 80,
    Stage5DV2EventType.SELL_CASH_SETTLEMENT: 80,
    Stage5DV2EventType.SECURITY_SETTLEMENT: 81,
    Stage5DV2EventType.SECURITY_SELLABLE: 82,
    Stage5DV2EventType.SELL_CASH_AVAILABLE: 83,
}


class Stage5DV2Account(StrEnum):
    CASH_AVAILABLE = "CASH_AVAILABLE"
    CASH_PAYABLE = "CASH_PAYABLE"
    CASH_RECEIVABLE = "CASH_RECEIVABLE"
    CASH_SETTLED_UNAVAILABLE = "CASH_SETTLED_UNAVAILABLE"
    OPENING_CONTROL = "OPENING_CONTROL"
    SECURITY_COST_PRINCIPAL = "SECURITY_COST_PRINCIPAL"
    SECURITY_COST_FEE = "SECURITY_COST_FEE"
    SECURITY_COST_TAX = "SECURITY_COST_TAX"
    SECURITY_COST_SLIPPAGE = "SECURITY_COST_SLIPPAGE"
    SECURITY_COST_BASIS_ADJUSTMENT = "SECURITY_COST_BASIS_ADJUSTMENT"
    SECURITY_UNSETTLED = "SECURITY_UNSETTLED"
    SECURITY_UNSELLABLE = "SECURITY_UNSELLABLE"
    SECURITY_SELLABLE = "SECURITY_SELLABLE"
    SECURITY_CONTROL = "SECURITY_CONTROL"
    SELL_PROCEEDS_CONTROL = "SELL_PROCEEDS_CONTROL"
    REALIZED_COST_BASIS_CONTROL = "REALIZED_COST_BASIS_CONTROL"
    REALIZED_FEE = "REALIZED_FEE"
    REALIZED_TAX = "REALIZED_TAX"
    REALIZED_SLIPPAGE = "REALIZED_SLIPPAGE"


class Stage5DV2SourceRole(StrEnum):
    STAGE5C_CASE = "STAGE5C_CASE"
    STAGE5C_RESULT = "STAGE5C_RESULT"
    ACCOUNT_SNAPSHOT = "ACCOUNT_SNAPSHOT"
    INITIAL_LEDGER = "INITIAL_LEDGER"
    OPENING_ATTRIBUTION = "OPENING_ATTRIBUTION"
    ORDER_INTENT = "ORDER_INTENT"
    FILL = "FILL"
    MARKET_OBSERVATION = "MARKET_OBSERVATION"
    MARKET_RULE = "MARKET_RULE"
    COST_SCHEDULE = "COST_SCHEDULE"
    IMPACT_CURVE = "IMPACT_CURVE"
    SETTLEMENT_TERMS = "SETTLEMENT_TERMS"


class Stage5DV2ReplayStatus(StrEnum):
    RECONCILED = "RECONCILED"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


_ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{name} must be a non-empty string of at most 256 characters")
    return value


def _decimal(name: str, value: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a finite decimal") from error
    if not parsed.is_finite():
        raise ValueError(f"{name} must be a finite decimal")
    if non_negative and parsed < 0:
        raise ValueError(f"{name} must be non-negative")
    return parsed


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _hash(value: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(value))


@dataclass(frozen=True, slots=True)
class Stage5DV2SourceRef(CanonicalModel):
    role: Stage5DV2SourceRole
    object_id: str
    content_hash: HashDigest

    def __post_init__(self) -> None:
        if not isinstance(self.role, Stage5DV2SourceRole):
            raise TypeError("role must be Stage5DV2SourceRole")
        _text("object_id", self.object_id)
        if not isinstance(self.content_hash, HashDigest):
            raise TypeError("content_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage5DV2Posting(CanonicalModel):
    account: Stage5DV2Account
    unit: str
    security_id: str | None
    debit: str
    credit: str

    def __post_init__(self) -> None:
        if not isinstance(self.account, Stage5DV2Account):
            raise TypeError("account must be Stage5DV2Account")
        _text("unit", self.unit)
        if self.security_id is not None:
            _text("security_id", self.security_id)
        debit = _decimal("debit", self.debit, non_negative=True)
        credit = _decimal("credit", self.credit, non_negative=True)
        if (debit == 0) == (credit == 0):
            raise ValueError("exactly one of debit and credit must be positive")
        object.__setattr__(self, "debit", _decimal_text(debit))
        object.__setattr__(self, "credit", _decimal_text(credit))


@dataclass(frozen=True, slots=True)
class Stage5DV2CostComponents(CanonicalModel):
    principal: str
    fee: str
    tax: str
    slippage: str
    basis_adjustment: str

    def __post_init__(self) -> None:
        for name in ("principal", "fee", "tax", "slippage", "basis_adjustment"):
            parsed = _decimal(name, getattr(self, name), non_negative=True)
            object.__setattr__(self, name, _decimal_text(parsed))

    def total(self) -> Decimal:
        return sum(
            (
                Decimal(self.principal),
                Decimal(self.fee),
                Decimal(self.tax),
                Decimal(self.slippage),
                Decimal(self.basis_adjustment),
            ),
            Decimal(0),
        )


@dataclass(frozen=True, slots=True)
class Stage5DV2CostComponentDelta(CanonicalModel):
    """Signed change to the five cost buckets of one lot."""

    principal: str
    fee: str
    tax: str
    slippage: str
    basis_adjustment: str

    def __post_init__(self) -> None:
        for name in ("principal", "fee", "tax", "slippage", "basis_adjustment"):
            parsed = _decimal(name, getattr(self, name))
            object.__setattr__(self, name, _decimal_text(parsed))

    def total(self) -> Decimal:
        return sum(
            (
                Decimal(self.principal),
                Decimal(self.fee),
                Decimal(self.tax),
                Decimal(self.slippage),
                Decimal(self.basis_adjustment),
            ),
            Decimal(0),
        )


@dataclass(frozen=True, slots=True)
class Stage5DV2OpeningLotAttribution(CanonicalModel):
    """Content-addressed five-component attribution for a Stage 5C opening lot."""

    attribution_id: str
    strategy_id: str
    account_fixture_id: str
    lot_id: str
    security_id: str
    acquired_at: datetime
    quantity: int
    sellable_quantity: int
    governing_market_rule_hash: HashDigest
    source_lot_hash: HashDigest
    cost_components: Stage5DV2CostComponents
    declared_content_hash: HashDigest
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for name in (
            "attribution_id",
            "strategy_id",
            "account_fixture_id",
            "lot_id",
            "security_id",
        ):
            _text(name, getattr(self, name))
        object.__setattr__(
            self,
            "acquired_at",
            normalize_utc(self.acquired_at, field_name="acquired_at"),
        )
        if (
            isinstance(self.quantity, bool)
            or not isinstance(self.quantity, int)
            or self.quantity <= 0
        ):
            raise ValueError("quantity must be a positive integer")
        if (
            isinstance(self.sellable_quantity, bool)
            or not isinstance(self.sellable_quantity, int)
            or not 0 <= self.sellable_quantity <= self.quantity
        ):
            raise ValueError("sellable_quantity must be between zero and quantity")
        for name in (
            "governing_market_rule_hash",
            "source_lot_hash",
            "declared_content_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        if not isinstance(self.cost_components, Stage5DV2CostComponents):
            raise TypeError("cost_components must be Stage5DV2CostComponents")


def stage5d_v2_opening_attribution_sha256(value: Stage5DV2OpeningLotAttribution) -> str:
    projected = value.to_json_value()
    del projected["declared_content_hash"]
    return canonical_sha256(projected)


def bind_stage5d_v2_opening_attribution(
    value: Stage5DV2OpeningLotAttribution,
) -> Stage5DV2OpeningLotAttribution:
    if not isinstance(value, Stage5DV2OpeningLotAttribution):
        raise TypeError("value must be Stage5DV2OpeningLotAttribution")
    return replace(
        value,
        declared_content_hash=_hash(
            {
                key: item
                for key, item in value.to_json_value().items()
                if key != "declared_content_hash"
            }
        ),
    )


@dataclass(frozen=True, slots=True)
class Stage5DV2LotEffect(CanonicalModel):
    lot_id: str
    security_id: str
    acquired_at: datetime
    source_fill_hash: HashDigest
    quantity_delta: int
    unsettled_quantity_delta: int
    unsellable_quantity_delta: int
    sellable_quantity_delta: int
    cost_components_delta: Stage5DV2CostComponents | Stage5DV2CostComponentDelta

    def __post_init__(self) -> None:
        _text("lot_id", self.lot_id)
        _text("security_id", self.security_id)
        object.__setattr__(
            self,
            "acquired_at",
            normalize_utc(self.acquired_at, field_name="acquired_at"),
        )
        if not isinstance(self.source_fill_hash, HashDigest):
            raise TypeError("source_fill_hash must be HashDigest")
        for name in (
            "quantity_delta",
            "unsettled_quantity_delta",
            "unsellable_quantity_delta",
            "sellable_quantity_delta",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
        if not isinstance(
            self.cost_components_delta,
            (Stage5DV2CostComponents, Stage5DV2CostComponentDelta),
        ):
            raise TypeError("cost_components_delta must be a typed V2 cost delta")
        if (
            self.quantity_delta == 0
            and self.unsettled_quantity_delta == 0
            and self.unsellable_quantity_delta == 0
            and self.sellable_quantity_delta == 0
            and self.cost_components_delta.total() == 0
        ):
            raise ValueError("lot effect must change quantity, state, or cost")


@dataclass(frozen=True, slots=True)
class Stage5DV2Event(CanonicalModel):
    event_id: str
    event_type: Stage5DV2EventType
    strategy_id: str
    account_fixture_id: str
    security_id: str | None
    effective_at: datetime
    source_refs: tuple[Stage5DV2SourceRef, ...]
    prior_event_hashes: tuple[HashDigest, ...]
    postings: tuple[Stage5DV2Posting, ...]
    lot_effects: tuple[Stage5DV2LotEffect, ...]
    declared_canonical_hash: HashDigest
    event_type_priority: int = field(init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _text("event_id", self.event_id)
        if not isinstance(self.event_type, Stage5DV2EventType):
            raise TypeError("event_type must be Stage5DV2EventType")
        object.__setattr__(self, "event_type_priority", STAGE5D_V2_EVENT_PRIORITY[self.event_type])
        _text("strategy_id", self.strategy_id)
        _text("account_fixture_id", self.account_fixture_id)
        if self.security_id is not None:
            _text("security_id", self.security_id)
        object.__setattr__(
            self,
            "effective_at",
            normalize_utc(self.effective_at, field_name="effective_at"),
        )
        sources = tuple(self.source_refs)
        if not sources or any(not isinstance(item, Stage5DV2SourceRef) for item in sources):
            raise ValueError("source_refs must contain typed source references")
        if len({item.role for item in sources}) != len(sources):
            raise ValueError("source roles must be unique within the minimal slice")
        object.__setattr__(self, "source_refs", tuple(sorted(sources, key=lambda x: x.role.value)))
        prior = tuple(self.prior_event_hashes)
        if any(not isinstance(item, HashDigest) for item in prior):
            raise TypeError("prior_event_hashes must contain HashDigest values")
        object.__setattr__(self, "prior_event_hashes", prior)
        postings = tuple(self.postings)
        effects = tuple(self.lot_effects)
        if any(not isinstance(item, Stage5DV2Posting) for item in postings):
            raise TypeError("postings must contain Stage5DV2Posting values")
        if any(not isinstance(item, Stage5DV2LotEffect) for item in effects):
            raise TypeError("lot_effects must contain Stage5DV2LotEffect values")
        object.__setattr__(self, "postings", postings)
        object.__setattr__(self, "lot_effects", effects)
        if not isinstance(self.declared_canonical_hash, HashDigest):
            raise TypeError("declared_canonical_hash must be HashDigest")


def stage5d_v2_event_sha256(value: Stage5DV2Event) -> str:
    projected = value.to_json_value()
    del projected["declared_canonical_hash"]
    return canonical_sha256(projected)


def bind_stage5d_v2_event(value: Stage5DV2Event) -> Stage5DV2Event:
    if not isinstance(value, Stage5DV2Event):
        raise TypeError("value must be Stage5DV2Event")
    return replace(
        value,
        declared_canonical_hash=_hash(
            {
                key: item
                for key, item in value.to_json_value().items()
                if key != "declared_canonical_hash"
            }
        ),
    )


@dataclass(frozen=True, slots=True)
class Stage5DV2Balance(CanonicalModel):
    account: Stage5DV2Account
    unit: str
    security_id: str | None
    debit_less_credit: str


@dataclass(frozen=True, slots=True)
class Stage5DV2DerivedLot(CanonicalModel):
    lot_id: str
    security_id: str
    acquired_at: datetime
    source_fill_hash: HashDigest
    quantity: int
    unsettled_quantity: int
    unsellable_quantity: int
    sellable_quantity: int
    cost_components: Stage5DV2CostComponents


@dataclass(frozen=True, slots=True)
class Stage5DV2DerivedState(CanonicalModel):
    balances: tuple[Stage5DV2Balance, ...]
    lots: tuple[Stage5DV2DerivedLot, ...]
    journal_head_hash: HashDigest
    available_cash: str
    cash_payable: str

    def actual_quantity(self, security_id: str) -> int:
        return sum(item.quantity for item in self.lots if item.security_id == security_id)

    def sellable_quantity(self, security_id: str) -> int:
        return sum(item.sellable_quantity for item in self.lots if item.security_id == security_id)


@dataclass(frozen=True, slots=True)
class Stage5DV2ReplayResult(CanonicalModel):
    schema_version: str
    status: Stage5DV2ReplayStatus
    reason_codes: tuple[str, ...]
    replay_as_of: datetime
    projected_events: tuple[Stage5DV2Event, ...]
    accepted_events: tuple[Stage5DV2Event, ...]
    future_events: tuple[Stage5DV2Event, ...]
    derived_state: Stage5DV2DerivedState | None
    replay_hash: HashDigest
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    atomic_durable_commit: bool = field(default=False, init=False)
    complete_stage5d_replay: bool = field(default=False, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)


def _posting_deltas(
    event: Stage5DV2Event,
) -> dict[tuple[Stage5DV2Account, str, str | None], Decimal]:
    values: dict[tuple[Stage5DV2Account, str, str | None], Decimal] = {}
    for posting in event.postings:
        key = (posting.account, posting.unit, posting.security_id)
        values[key] = values.get(key, Decimal(0)) + Decimal(posting.debit) - Decimal(posting.credit)
    return values


def _source_roles(event: Stage5DV2Event) -> set[Stage5DV2SourceRole]:
    return {item.role for item in event.source_refs}


def _balanced(event: Stage5DV2Event) -> bool:
    by_unit: dict[str, tuple[Decimal, Decimal]] = {}
    for posting in event.postings:
        debit, credit = by_unit.get(posting.unit, (Decimal(0), Decimal(0)))
        by_unit[posting.unit] = (
            debit + Decimal(posting.debit),
            credit + Decimal(posting.credit),
        )
    return bool(by_unit) and all(debit == credit for debit, credit in by_unit.values())


def _cost_values(
    value: Stage5DV2CostComponents | Stage5DV2CostComponentDelta,
) -> dict[str, Decimal]:
    return {
        name: Decimal(getattr(value, name))
        for name in ("principal", "fee", "tax", "slippage", "basis_adjustment")
    }


def _exact_pro_rata(value: Decimal, take: int, quantity: int) -> Decimal | None:
    """Return an exact terminating pro-rata decimal, or fail closed."""

    if quantity <= 0 or take < 0 or take > quantity:
        return None
    if take == quantity:
        return value
    ratio = Fraction(value) * Fraction(take, quantity)
    denominator = ratio.denominator
    while denominator % 2 == 0:
        denominator //= 2
    while denominator % 5 == 0:
        denominator //= 5
    if denominator != 1:
        return None
    return Decimal(ratio.numerator) / Decimal(ratio.denominator)


def _validate_event(event: Stage5DV2Event) -> str | None:
    roles = _source_roles(event)
    deltas = _posting_deltas(event)
    if not _balanced(event):
        return "STAGE5D_V2_EVENT_NOT_BALANCED"
    if event.event_type is Stage5DV2EventType.OPENING_BALANCE:
        if event.security_id is not None or event.lot_effects:
            return "STAGE5D_V2_OPENING_SCOPE_INVALID"
        if roles != {
            Stage5DV2SourceRole.STAGE5C_CASE,
            Stage5DV2SourceRole.ACCOUNT_SNAPSHOT,
            Stage5DV2SourceRole.INITIAL_LEDGER,
        }:
            return "STAGE5D_V2_OPENING_SOURCE_SET_INVALID"
        cash = deltas.get((Stage5DV2Account.CASH_AVAILABLE, "CNY", None), Decimal(0))
        control = deltas.get((Stage5DV2Account.OPENING_CONTROL, "CNY", None), Decimal(0))
        if cash <= 0 or control != -cash or len(deltas) != 2:
            return "STAGE5D_V2_OPENING_POSTINGS_INVALID"
        return None
    if event.event_type is Stage5DV2EventType.OPENING_POSITION:
        if event.security_id is None or len(event.lot_effects) != 1:
            return "STAGE5D_V2_OPENING_POSITION_SCOPE_INVALID"
        if roles != {
            Stage5DV2SourceRole.STAGE5C_CASE,
            Stage5DV2SourceRole.ACCOUNT_SNAPSHOT,
            Stage5DV2SourceRole.INITIAL_LEDGER,
            Stage5DV2SourceRole.OPENING_ATTRIBUTION,
        }:
            return "STAGE5D_V2_OPENING_POSITION_SOURCE_SET_INVALID"
        effect = event.lot_effects[0]
        components = effect.cost_components_delta
        if (
            effect.security_id != event.security_id
            or effect.quantity_delta <= 0
            or effect.unsettled_quantity_delta != 0
            or effect.unsellable_quantity_delta < 0
            or effect.sellable_quantity_delta < 0
            or effect.unsellable_quantity_delta + effect.sellable_quantity_delta
            != effect.quantity_delta
            or any(value < 0 for value in _cost_values(components).values())
        ):
            return "STAGE5D_V2_OPENING_POSITION_LOT_INVALID"
        component_accounts = {
            "principal": Stage5DV2Account.SECURITY_COST_PRINCIPAL,
            "fee": Stage5DV2Account.SECURITY_COST_FEE,
            "tax": Stage5DV2Account.SECURITY_COST_TAX,
            "slippage": Stage5DV2Account.SECURITY_COST_SLIPPAGE,
            "basis_adjustment": Stage5DV2Account.SECURITY_COST_BASIS_ADJUSTMENT,
        }
        for name, account in component_accounts.items():
            if deltas.get((account, "CNY", event.security_id), Decimal(0)) != Decimal(
                getattr(components, name)
            ):
                return "STAGE5D_V2_OPENING_POSITION_COST_MISMATCH"
        opening_expected_keys: set[tuple[Stage5DV2Account, str, str | None]] = {
            (account, "CNY", event.security_id)
            for name, account in component_accounts.items()
            if Decimal(getattr(components, name)) != 0
        }
        opening_expected_keys.add((Stage5DV2Account.OPENING_CONTROL, "CNY", None))
        if effect.unsellable_quantity_delta != 0:
            opening_expected_keys.add(
                (Stage5DV2Account.SECURITY_UNSELLABLE, event.security_id, event.security_id)
            )
        if effect.sellable_quantity_delta != 0:
            opening_expected_keys.add(
                (Stage5DV2Account.SECURITY_SELLABLE, event.security_id, event.security_id)
            )
        opening_expected_keys.add(
            (Stage5DV2Account.SECURITY_CONTROL, event.security_id, event.security_id)
        )
        if set(deltas) != opening_expected_keys:
            return "STAGE5D_V2_OPENING_POSITION_ACCOUNT_SET_INVALID"
        opening_control = deltas.get((Stage5DV2Account.OPENING_CONTROL, "CNY", None), Decimal(0))
        unsellable = deltas.get(
            (Stage5DV2Account.SECURITY_UNSELLABLE, event.security_id, event.security_id),
            Decimal(0),
        )
        sellable = deltas.get(
            (Stage5DV2Account.SECURITY_SELLABLE, event.security_id, event.security_id),
            Decimal(0),
        )
        control = deltas.get(
            (Stage5DV2Account.SECURITY_CONTROL, event.security_id, event.security_id),
            Decimal(0),
        )
        if (
            opening_control != -components.total()
            or unsellable != effect.unsellable_quantity_delta
            or sellable != effect.sellable_quantity_delta
            or control != -effect.quantity_delta
        ):
            return "STAGE5D_V2_OPENING_POSITION_POSTINGS_INVALID"
        return None
    if event.security_id is None:
        return "STAGE5D_V2_SECURITY_SCOPE_MISSING"
    if event.event_type is Stage5DV2EventType.BUY_TRADE:
        if (
            roles
            != {
                Stage5DV2SourceRole.STAGE5C_CASE,
                Stage5DV2SourceRole.STAGE5C_RESULT,
                Stage5DV2SourceRole.ORDER_INTENT,
                Stage5DV2SourceRole.FILL,
                Stage5DV2SourceRole.MARKET_OBSERVATION,
                Stage5DV2SourceRole.MARKET_RULE,
                Stage5DV2SourceRole.COST_SCHEDULE,
                Stage5DV2SourceRole.IMPACT_CURVE,
            }
            or len(event.lot_effects) != 1
        ):
            return "STAGE5D_V2_BUY_SOURCE_OR_LOT_INVALID"
        effect = event.lot_effects[0]
        components = effect.cost_components_delta
        if (
            effect.security_id != event.security_id
            or effect.quantity_delta <= 0
            or effect.unsettled_quantity_delta != effect.quantity_delta
            or effect.unsellable_quantity_delta != 0
            or effect.sellable_quantity_delta != 0
        ):
            return "STAGE5D_V2_BUY_LOT_EFFECT_INVALID"
        expected = {
            Stage5DV2Account.SECURITY_COST_PRINCIPAL: Decimal(components.principal),
            Stage5DV2Account.SECURITY_COST_FEE: Decimal(components.fee),
            Stage5DV2Account.SECURITY_COST_TAX: Decimal(components.tax),
            Stage5DV2Account.SECURITY_COST_SLIPPAGE: Decimal(components.slippage),
            Stage5DV2Account.SECURITY_COST_BASIS_ADJUSTMENT: Decimal(components.basis_adjustment),
        }
        for account, amount in expected.items():
            actual = deltas.get((account, "CNY", event.security_id), Decimal(0))
            if actual != amount:
                return "STAGE5D_V2_BUY_COST_COMPONENT_MISMATCH"
        payable = deltas.get((Stage5DV2Account.CASH_PAYABLE, "CNY", None), Decimal(0))
        unsettled = deltas.get(
            (Stage5DV2Account.SECURITY_UNSETTLED, event.security_id, event.security_id),
            Decimal(0),
        )
        control = deltas.get(
            (Stage5DV2Account.SECURITY_CONTROL, event.security_id, event.security_id),
            Decimal(0),
        )
        if (
            payable != -components.total()
            or unsettled != effect.quantity_delta
            or control != -unsettled
        ):
            return "STAGE5D_V2_BUY_POSTINGS_INVALID"
        return None
    if event.event_type is Stage5DV2EventType.SELL_TRADE:
        if (
            roles
            != {
                Stage5DV2SourceRole.STAGE5C_CASE,
                Stage5DV2SourceRole.STAGE5C_RESULT,
                Stage5DV2SourceRole.ORDER_INTENT,
                Stage5DV2SourceRole.FILL,
                Stage5DV2SourceRole.MARKET_OBSERVATION,
                Stage5DV2SourceRole.MARKET_RULE,
                Stage5DV2SourceRole.COST_SCHEDULE,
                Stage5DV2SourceRole.IMPACT_CURVE,
            }
            or not event.lot_effects
        ):
            return "STAGE5D_V2_SELL_SOURCE_OR_LOT_INVALID"
        removed_components = {
            name: -sum(
                (Decimal(getattr(item.cost_components_delta, name)) for item in event.lot_effects),
                Decimal(0),
            )
            for name in ("principal", "fee", "tax", "slippage", "basis_adjustment")
        }
        if any(
            effect.security_id != event.security_id
            or effect.quantity_delta >= 0
            or effect.unsettled_quantity_delta != 0
            or effect.unsellable_quantity_delta != 0
            or effect.sellable_quantity_delta != effect.quantity_delta
            or any(value > 0 for value in _cost_values(effect.cost_components_delta).values())
            for effect in event.lot_effects
        ):
            return "STAGE5D_V2_SELL_LOT_EFFECT_INVALID"
        component_accounts = {
            "principal": Stage5DV2Account.SECURITY_COST_PRINCIPAL,
            "fee": Stage5DV2Account.SECURITY_COST_FEE,
            "tax": Stage5DV2Account.SECURITY_COST_TAX,
            "slippage": Stage5DV2Account.SECURITY_COST_SLIPPAGE,
            "basis_adjustment": Stage5DV2Account.SECURITY_COST_BASIS_ADJUSTMENT,
        }
        for name, account in component_accounts.items():
            if (
                deltas.get((account, "CNY", event.security_id), Decimal(0))
                != -removed_components[name]
            ):
                return "STAGE5D_V2_SELL_COST_COMPONENT_MISMATCH"
        removed_quantity = -sum(item.quantity_delta for item in event.lot_effects)
        cash_receivable = deltas.get((Stage5DV2Account.CASH_RECEIVABLE, "CNY", None), Decimal(0))
        realized_fee = deltas.get((Stage5DV2Account.REALIZED_FEE, "CNY", None), Decimal(0))
        realized_tax = deltas.get((Stage5DV2Account.REALIZED_TAX, "CNY", None), Decimal(0))
        realized_slippage = deltas.get(
            (Stage5DV2Account.REALIZED_SLIPPAGE, "CNY", None), Decimal(0)
        )
        proceeds = deltas.get((Stage5DV2Account.SELL_PROCEEDS_CONTROL, "CNY", None), Decimal(0))
        realized_basis = deltas.get(
            (Stage5DV2Account.REALIZED_COST_BASIS_CONTROL, "CNY", None), Decimal(0)
        )
        security_control = deltas.get(
            (Stage5DV2Account.SECURITY_CONTROL, event.security_id, event.security_id),
            Decimal(0),
        )
        sellable = deltas.get(
            (Stage5DV2Account.SECURITY_SELLABLE, event.security_id, event.security_id),
            Decimal(0),
        )
        sell_expected_keys: set[tuple[Stage5DV2Account, str, str | None]] = {
            (Stage5DV2Account.CASH_RECEIVABLE, "CNY", None),
            (Stage5DV2Account.SELL_PROCEEDS_CONTROL, "CNY", None),
            (Stage5DV2Account.REALIZED_COST_BASIS_CONTROL, "CNY", None),
            (Stage5DV2Account.SECURITY_CONTROL, event.security_id, event.security_id),
            (Stage5DV2Account.SECURITY_SELLABLE, event.security_id, event.security_id),
        }
        for amount, account in (
            (realized_fee, Stage5DV2Account.REALIZED_FEE),
            (realized_tax, Stage5DV2Account.REALIZED_TAX),
            (realized_slippage, Stage5DV2Account.REALIZED_SLIPPAGE),
        ):
            if amount != 0:
                sell_expected_keys.add((account, "CNY", None))
        for name, account in component_accounts.items():
            if removed_components[name] != 0:
                sell_expected_keys.add((account, "CNY", event.security_id))
        if set(deltas) != sell_expected_keys:
            return "STAGE5D_V2_SELL_ACCOUNT_SET_INVALID"
        if (
            cash_receivable <= 0
            or any(value < 0 for value in (realized_fee, realized_tax, realized_slippage))
            or proceeds >= 0
            or realized_basis != sum(removed_components.values(), Decimal(0))
            or cash_receivable + realized_fee + realized_tax + realized_slippage != -proceeds
            or security_control != removed_quantity
            or sellable != -removed_quantity
        ):
            return "STAGE5D_V2_SELL_POSTINGS_INVALID"
        return None
    if roles != {
        Stage5DV2SourceRole.FILL,
        Stage5DV2SourceRole.SETTLEMENT_TERMS,
        Stage5DV2SourceRole.MARKET_RULE,
    }:
        return "STAGE5D_V2_SETTLEMENT_SOURCE_SET_INVALID"
    if event.event_type is Stage5DV2EventType.BUY_CASH_SETTLEMENT:
        if event.lot_effects:
            return "STAGE5D_V2_CASH_SETTLEMENT_HAS_LOT_EFFECT"
        payable = deltas.get((Stage5DV2Account.CASH_PAYABLE, "CNY", None), Decimal(0))
        cash = deltas.get((Stage5DV2Account.CASH_AVAILABLE, "CNY", None), Decimal(0))
        if payable <= 0 or cash != -payable or len(deltas) != 2:
            return "STAGE5D_V2_CASH_SETTLEMENT_POSTINGS_INVALID"
        return None
    if event.event_type is Stage5DV2EventType.SELL_CASH_SETTLEMENT:
        if event.lot_effects:
            return "STAGE5D_V2_CASH_SETTLEMENT_HAS_LOT_EFFECT"
        receivable = deltas.get((Stage5DV2Account.CASH_RECEIVABLE, "CNY", None), Decimal(0))
        unavailable = deltas.get(
            (Stage5DV2Account.CASH_SETTLED_UNAVAILABLE, "CNY", None), Decimal(0)
        )
        if receivable >= 0 or unavailable != -receivable or len(deltas) != 2:
            return "STAGE5D_V2_SELL_CASH_SETTLEMENT_POSTINGS_INVALID"
        return None
    if event.event_type is Stage5DV2EventType.SELL_CASH_AVAILABLE:
        if event.lot_effects:
            return "STAGE5D_V2_CASH_AVAILABILITY_HAS_LOT_EFFECT"
        unavailable = deltas.get(
            (Stage5DV2Account.CASH_SETTLED_UNAVAILABLE, "CNY", None), Decimal(0)
        )
        available = deltas.get((Stage5DV2Account.CASH_AVAILABLE, "CNY", None), Decimal(0))
        if unavailable >= 0 or available != -unavailable or len(deltas) != 2:
            return "STAGE5D_V2_SELL_CASH_AVAILABILITY_POSTINGS_INVALID"
        return None
    if len(event.lot_effects) != 1:
        return "STAGE5D_V2_SECURITY_SETTLEMENT_LOT_MISSING"
    effect = event.lot_effects[0]
    if effect.security_id != event.security_id or effect.cost_components_delta.total() != 0:
        return "STAGE5D_V2_SECURITY_SETTLEMENT_LOT_INVALID"
    quantity = effect.quantity_delta
    if quantity != 0:
        return "STAGE5D_V2_SECURITY_SETTLEMENT_CHANGES_TOTAL_QUANTITY"
    if event.event_type is Stage5DV2EventType.SECURITY_SETTLEMENT:
        transition_quantity = effect.unsellable_quantity_delta
        if (
            transition_quantity <= 0
            or effect.unsettled_quantity_delta != -transition_quantity
            or effect.sellable_quantity_delta != 0
        ):
            return "STAGE5D_V2_SECURITY_SETTLEMENT_EFFECT_INVALID"
        debit_account = Stage5DV2Account.SECURITY_UNSELLABLE
        credit_account = Stage5DV2Account.SECURITY_UNSETTLED
    else:
        transition_quantity = effect.sellable_quantity_delta
        if (
            transition_quantity <= 0
            or effect.unsellable_quantity_delta != -transition_quantity
            or effect.unsettled_quantity_delta != 0
        ):
            return "STAGE5D_V2_SECURITY_SELLABLE_EFFECT_INVALID"
        debit_account = Stage5DV2Account.SECURITY_SELLABLE
        credit_account = Stage5DV2Account.SECURITY_UNSELLABLE
    debit = deltas.get((debit_account, event.security_id, event.security_id), Decimal(0))
    credit = deltas.get((credit_account, event.security_id, event.security_id), Decimal(0))
    if debit != transition_quantity or credit != -transition_quantity or len(deltas) != 2:
        return "STAGE5D_V2_SECURITY_STATE_POSTINGS_INVALID"
    return None


def _blocked(
    status: Stage5DV2ReplayStatus,
    reason: str,
    as_of: datetime,
    projected: tuple[Stage5DV2Event, ...],
    accepted: tuple[Stage5DV2Event, ...] = (),
) -> Stage5DV2ReplayResult:
    value = Stage5DV2ReplayResult(
        schema_version=STAGE5D_V2_SLICE_SCHEMA_VERSION,
        status=status,
        reason_codes=(reason,),
        replay_as_of=as_of,
        projected_events=projected,
        accepted_events=accepted,
        future_events=tuple(item for item in projected if item not in accepted),
        derived_state=None,
        replay_hash=_ZERO_HASH,
    )
    return replace(
        value,
        replay_hash=_hash(
            {key: item for key, item in value.to_json_value().items() if key != "replay_hash"}
        ),
    )


@dataclass(slots=True)
class _MutableLot:
    security_id: str
    acquired_at: datetime
    source_fill_hash: HashDigest
    quantity: int = 0
    unsettled: int = 0
    unsellable: int = 0
    sellable: int = 0
    principal: Decimal = Decimal(0)
    fee: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    slippage: Decimal = Decimal(0)
    basis_adjustment: Decimal = Decimal(0)


def _validate_fifo_sell(
    event: Stage5DV2Event,
    lots: dict[str, _MutableLot],
) -> str | None:
    requested = -sum(item.quantity_delta for item in event.lot_effects)
    remaining = requested
    expected: list[tuple[_MutableLot, str, int, dict[str, Decimal]]] = []
    for lot_id, lot in sorted(lots.items(), key=lambda item: (item[1].acquired_at, item[0])):
        if lot.security_id != event.security_id or lot.sellable <= 0 or remaining == 0:
            continue
        take = min(lot.sellable, remaining)
        components: dict[str, Decimal] = {}
        for name in ("principal", "fee", "tax", "slippage", "basis_adjustment"):
            value = _exact_pro_rata(getattr(lot, name), take, lot.quantity)
            if value is None:
                return "STAGE5D_V2_FIFO_COST_NOT_EXACTLY_REPRESENTABLE"
            components[name] = value
        expected.append((lot, lot_id, take, components))
        remaining -= take
    if remaining != 0 or len(expected) != len(event.lot_effects):
        return "STAGE5D_V2_FIFO_SELLABLE_QUANTITY_INSUFFICIENT"
    for effect, (lot, lot_id, take, components) in zip(event.lot_effects, expected, strict=True):
        if (
            effect.lot_id != lot_id
            or effect.security_id != lot.security_id
            or effect.acquired_at != lot.acquired_at
            or effect.source_fill_hash != lot.source_fill_hash
            or effect.quantity_delta != -take
            or effect.sellable_quantity_delta != -take
            or effect.unsettled_quantity_delta != 0
            or effect.unsellable_quantity_delta != 0
            or any(
                Decimal(getattr(effect.cost_components_delta, name)) != -amount
                for name, amount in components.items()
            )
        ):
            return "STAGE5D_V2_FIFO_LOT_REMOVAL_MISMATCH"
    return None


def replay_stage5d_v2_slice(
    events: tuple[Stage5DV2Event, ...],
    *,
    as_of: datetime,
) -> Stage5DV2ReplayResult:
    """Validate, canonically order, and replay the minimal V2 journal."""

    replay_as_of = normalize_utc(as_of, field_name="as_of")
    projected = tuple(
        sorted(
            tuple(events),
            key=lambda item: (item.effective_at, item.event_type_priority, item.event_id),
        )
    )
    if not projected:
        return _blocked(
            Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
            "STAGE5D_V2_JOURNAL_EMPTY",
            replay_as_of,
            projected,
        )
    if any(not isinstance(item, Stage5DV2Event) for item in projected):
        raise TypeError("events must contain Stage5DV2Event values")
    if len({item.event_id for item in projected}) != len(projected):
        return _blocked(
            Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
            "STAGE5D_V2_EVENT_ID_DUPLICATE",
            replay_as_of,
            projected,
        )
    scopes = {(item.strategy_id, item.account_fixture_id) for item in projected}
    if len(scopes) != 1:
        return _blocked(
            Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
            "STAGE5D_V2_SCOPE_MIXED",
            replay_as_of,
            projected,
        )
    if (
        projected[0].event_type is not Stage5DV2EventType.OPENING_BALANCE
        or sum(item.event_type is Stage5DV2EventType.OPENING_BALANCE for item in projected) != 1
    ):
        return _blocked(
            Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
            "STAGE5D_V2_SINGLE_OPENING_REQUIRED",
            replay_as_of,
            projected,
        )
    expected_prefix: tuple[HashDigest, ...] = ()
    for event in projected:
        if event.declared_canonical_hash.value != stage5d_v2_event_sha256(event):
            return _blocked(
                Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
                "STAGE5D_V2_EVENT_HASH_DRIFT",
                replay_as_of,
                projected,
            )
        if event.prior_event_hashes != expected_prefix:
            return _blocked(
                Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
                "STAGE5D_V2_EXACT_FULL_PREFIX_MISMATCH",
                replay_as_of,
                projected,
            )
        semantic_failure = _validate_event(event)
        if semantic_failure is not None:
            return _blocked(
                Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                semantic_failure,
                replay_as_of,
                projected,
            )
        expected_prefix += (event.declared_canonical_hash,)

    accepted = tuple(item for item in projected if item.effective_at <= replay_as_of)
    if not accepted or accepted[0].event_type is not Stage5DV2EventType.OPENING_BALANCE:
        return _blocked(
            Stage5DV2ReplayStatus.PRECHECK_BLOCKED,
            "STAGE5D_V2_OPENING_NOT_AVAILABLE_AT_REPLAY_TIME",
            replay_as_of,
            projected,
        )

    balances: dict[tuple[Stage5DV2Account, str, str | None], Decimal] = {}
    lots: dict[str, _MutableLot] = {}
    for event in accepted:
        if event.event_type is Stage5DV2EventType.SELL_TRADE:
            fifo_failure = _validate_fifo_sell(event, lots)
            if fifo_failure is not None:
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    fifo_failure,
                    replay_as_of,
                    projected,
                    accepted,
                )
        for posting in event.postings:
            key = (posting.account, posting.unit, posting.security_id)
            balances[key] = (
                balances.get(key, Decimal(0)) + Decimal(posting.debit) - Decimal(posting.credit)
            )
        for effect in event.lot_effects:
            current = lots.get(effect.lot_id)
            if current is None:
                if effect.quantity_delta <= 0:
                    return _blocked(
                        Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                        "STAGE5D_V2_LOT_MISSING_BEFORE_STATE_TRANSITION",
                        replay_as_of,
                        projected,
                        accepted,
                    )
                current = _MutableLot(
                    security_id=effect.security_id,
                    acquired_at=effect.acquired_at,
                    source_fill_hash=effect.source_fill_hash,
                )
                lots[effect.lot_id] = current
            if (
                current.security_id != effect.security_id
                or current.source_fill_hash != effect.source_fill_hash
            ):
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    "STAGE5D_V2_LOT_LINEAGE_DRIFT",
                    replay_as_of,
                    projected,
                    accepted,
                )
            current.quantity += effect.quantity_delta
            current.unsettled += effect.unsettled_quantity_delta
            current.unsellable += effect.unsellable_quantity_delta
            current.sellable += effect.sellable_quantity_delta
            for name in ("principal", "fee", "tax", "slippage", "basis_adjustment"):
                setattr(
                    current,
                    name,
                    getattr(current, name) + Decimal(getattr(effect.cost_components_delta, name)),
                )
            quantities = (
                current.quantity,
                current.unsettled,
                current.unsellable,
                current.sellable,
            )
            if any(value < 0 for value in quantities) or quantities[0] != sum(quantities[1:]):
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    "STAGE5D_V2_LOT_STATE_NOT_CONSERVED",
                    replay_as_of,
                    projected,
                    accepted,
                )
            if any(
                getattr(current, name) < 0
                for name in ("principal", "fee", "tax", "slippage", "basis_adjustment")
            ):
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    "STAGE5D_V2_LOT_COST_COMPONENT_NEGATIVE",
                    replay_as_of,
                    projected,
                    accepted,
                )
        if balances.get((Stage5DV2Account.CASH_AVAILABLE, "CNY", None), Decimal(0)) < 0:
            return _blocked(
                Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                "STAGE5D_V2_NEGATIVE_AVAILABLE_CASH",
                replay_as_of,
                projected,
                accepted,
            )
        if (
            balances.get((Stage5DV2Account.CASH_RECEIVABLE, "CNY", None), Decimal(0)) < 0
            or balances.get((Stage5DV2Account.CASH_SETTLED_UNAVAILABLE, "CNY", None), Decimal(0))
            < 0
        ):
            return _blocked(
                Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                "STAGE5D_V2_NEGATIVE_RECEIVABLE_OR_SETTLED_UNAVAILABLE_CASH",
                replay_as_of,
                projected,
                accepted,
            )

    derived_lots = tuple(
        Stage5DV2DerivedLot(
            lot_id=lot_id,
            security_id=value.security_id,
            acquired_at=value.acquired_at,
            source_fill_hash=value.source_fill_hash,
            quantity=value.quantity,
            unsettled_quantity=value.unsettled,
            unsellable_quantity=value.unsellable,
            sellable_quantity=value.sellable,
            cost_components=Stage5DV2CostComponents(
                principal=_decimal_text(value.principal),
                fee=_decimal_text(value.fee),
                tax=_decimal_text(value.tax),
                slippage=_decimal_text(value.slippage),
                basis_adjustment=_decimal_text(value.basis_adjustment),
            ),
        )
        for lot_id, value in sorted(lots.items())
        if value.quantity > 0
    )
    component_accounts = {
        "principal": Stage5DV2Account.SECURITY_COST_PRINCIPAL,
        "fee": Stage5DV2Account.SECURITY_COST_FEE,
        "tax": Stage5DV2Account.SECURITY_COST_TAX,
        "slippage": Stage5DV2Account.SECURITY_COST_SLIPPAGE,
        "basis_adjustment": Stage5DV2Account.SECURITY_COST_BASIS_ADJUSTMENT,
    }
    for security_id in {item.security_id for item in derived_lots}:
        scoped_lots = tuple(item for item in derived_lots if item.security_id == security_id)
        for component, account in component_accounts.items():
            ledger_value = balances.get((account, "CNY", security_id), Decimal(0))
            lot_value = sum(
                (Decimal(getattr(item.cost_components, component)) for item in scoped_lots),
                Decimal(0),
            )
            if ledger_value != lot_value:
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    "STAGE5D_V2_SECURITY_COST_TO_LOT_MISMATCH",
                    replay_as_of,
                    projected,
                    accepted,
                )
        quantity_accounts = {
            "unsettled_quantity": Stage5DV2Account.SECURITY_UNSETTLED,
            "unsellable_quantity": Stage5DV2Account.SECURITY_UNSELLABLE,
            "sellable_quantity": Stage5DV2Account.SECURITY_SELLABLE,
        }
        for attribute, account in quantity_accounts.items():
            ledger_value = balances.get((account, security_id, security_id), Decimal(0))
            lot_value = sum((getattr(item, attribute) for item in scoped_lots), 0)
            if ledger_value != lot_value:
                return _blocked(
                    Stage5DV2ReplayStatus.RECONCILIATION_BLOCKED,
                    "STAGE5D_V2_SECURITY_QUANTITY_TO_LOT_MISMATCH",
                    replay_as_of,
                    projected,
                    accepted,
                )

    balance_values = tuple(
        Stage5DV2Balance(
            account=key[0],
            unit=key[1],
            security_id=key[2],
            debit_less_credit=_decimal_text(value),
        )
        for key, value in sorted(
            balances.items(), key=lambda item: (item[0][0].value, item[0][1], item[0][2] or "")
        )
        if value != 0
    )
    accepted_hashes = tuple(item.declared_canonical_hash for item in accepted)
    head = _hash(
        {
            "schema_version": STAGE5D_V2_SLICE_SCHEMA_VERSION,
            "accepted_event_hashes": accepted_hashes,
        }
    )
    state = Stage5DV2DerivedState(
        balances=balance_values,
        lots=derived_lots,
        journal_head_hash=head,
        available_cash=_decimal_text(
            balances.get((Stage5DV2Account.CASH_AVAILABLE, "CNY", None), Decimal(0))
        ),
        cash_payable=_decimal_text(
            -balances.get((Stage5DV2Account.CASH_PAYABLE, "CNY", None), Decimal(0))
        ),
    )
    value = Stage5DV2ReplayResult(
        schema_version=STAGE5D_V2_SLICE_SCHEMA_VERSION,
        status=Stage5DV2ReplayStatus.RECONCILED,
        reason_codes=("STAGE5D_V2_MINIMAL_SOURCE_DRIVEN_SLICE_RECONCILED",),
        replay_as_of=replay_as_of,
        projected_events=projected,
        accepted_events=accepted,
        future_events=tuple(item for item in projected if item.effective_at > replay_as_of),
        derived_state=state,
        replay_hash=_ZERO_HASH,
    )
    return replace(
        value,
        replay_hash=_hash(
            {key: item for key, item in value.to_json_value().items() if key != "replay_hash"}
        ),
    )


__all__ = [
    "STAGE5D_V2_EVENT_PRIORITY",
    "STAGE5D_V2_SLICE_SCHEMA_VERSION",
    "Stage5DV2Account",
    "Stage5DV2Balance",
    "Stage5DV2CostComponents",
    "Stage5DV2CostComponentDelta",
    "Stage5DV2DerivedLot",
    "Stage5DV2DerivedState",
    "Stage5DV2Event",
    "Stage5DV2EventType",
    "Stage5DV2LotEffect",
    "Stage5DV2OpeningLotAttribution",
    "Stage5DV2Posting",
    "Stage5DV2ReplayResult",
    "Stage5DV2ReplayStatus",
    "Stage5DV2SourceRef",
    "Stage5DV2SourceRole",
    "bind_stage5d_v2_opening_attribution",
    "bind_stage5d_v2_event",
    "replay_stage5d_v2_slice",
    "stage5d_v2_opening_attribution_sha256",
    "stage5d_v2_event_sha256",
]
