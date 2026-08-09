"""Stage 5B historical market rules and deterministic synthetic fills.

This module implements only the owner-approved anonymous synthetic execution-
validation slice.  It has no provider, broker, account, portfolio, ledger,
persistence, network, or real-order integration.  All decimal contract values
remain strings; calculation uses :class:`decimal.Decimal`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from typing import Protocol

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import RuleApprovalScope
from invest_system.models import CanonicalModel, DecisionState, GateOutcome, HashDigest, RunMode

from .stage4_complete_engine import (
    CompleteStage4EvaluationState,
    Stage4CompleteResult,
    Stage4CompleteSyntheticCase,
    complete_stage4_replay_sha256,
)
from .stage4_expectation_valuation_exit import (
    ExitDisposition,
    MarketPricingState,
    Stage4ValuationSet,
    VersionedArtifactIdentity,
)
from .stage4_gate_profit_scenarios import DecimalInterval
from .stage5_decimal import with_stage5_decimal_context
from .stage5_governance import (
    STAGE5_APPROVAL_SCOPE,
    STAGE5_STRATEGY_ID,
    ApprovedStage5MarketExecutionRules,
)

STAGE5B_SCHEMA_VERSION = "0.1.0"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class Stage5ActionIntent(StrEnum):
    ENTER = "ENTER"
    ADD = "ADD"
    REDUCE = "REDUCE"
    EXIT = "EXIT"


class TradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class TimingPrecision(StrEnum):
    EXACT = "exact"
    DATE_ONLY = "date_only"


class MarketRuleImplementationState(StrEnum):
    EFFECTIVE = "effective"
    SUSPENDED = "suspended"
    DEFERRED = "deferred"
    REPEALED = "repealed"


class MarketDataQuality(StrEnum):
    ORDER_BOOK = "order_book"
    TICK = "tick"
    MINUTE = "minute"
    DAILY = "daily"


class Stage5ExecutionStatus(StrEnum):
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    ABSTAIN = "ABSTAIN"
    GATE_REJECTED_AT_EXECUTABLE_PRICE = "GATE_REJECTED_AT_EXECUTABLE_PRICE"
    NON_EXECUTABLE = "NON_EXECUTABLE"
    ENTRY_EXPIRED = "ENTRY_EXPIRED"
    TARGET_READY = "TARGET_READY"
    SYNTHETIC_APPROVED = "SYNTHETIC_APPROVED"
    SYNTHETIC_REJECTED = "SYNTHETIC_REJECTED"
    SIMULATED_SUBMITTED = "SIMULATED_SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


class SyntheticEventType(StrEnum):
    SIMULATED_SUBMITTED = "SIMULATED_SUBMITTED"
    SYNTHETIC_FILL = "SYNTHETIC_FILL"
    CANCELLED = "CANCELLED"


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _decimal(field_name: str, value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact decimal string")
    parsed = Decimal(value)
    if positive and parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _non_negative_decimal(field_name: str, value: str) -> Decimal:
    parsed = _decimal(field_name, value)
    if parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _require_identity(value: VersionedArtifactIdentity) -> None:
    if not isinstance(value, VersionedArtifactIdentity):
        raise TypeError("identity must be VersionedArtifactIdentity")


def _require_hashes(field_name: str, values: tuple[HashDigest, ...]) -> tuple[HashDigest, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(f"{field_name} must contain at least one hash")
    result = tuple(values)
    if any(not isinstance(item, HashDigest) for item in result):
        raise TypeError(f"{field_name} must contain HashDigest values")
    if len({item.value for item in result}) != len(result):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result, key=lambda item: item.value))


def _require_texts(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError(f"{field_name} must contain at least one value")
    result = tuple(_require_text(field_name, value) for value in values)
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result))


class _EffectiveDated(Protocol):
    @property
    def published_at(self) -> datetime: ...

    @property
    def effective_from(self) -> datetime: ...

    @property
    def effective_to(self) -> datetime | None: ...


def _normalize_interval(value: _EffectiveDated, *, prefix: str) -> None:
    for name in ("published_at", "effective_from"):
        object.__setattr__(
            value,
            name,
            normalize_utc(getattr(value, name), field_name=f"{prefix}.{name}"),
        )
    effective_to = value.effective_to
    if effective_to is not None:
        normalized = normalize_utc(effective_to, field_name=f"{prefix}.effective_to")
        object.__setattr__(value, "effective_to", normalized)
        if normalized <= value.effective_from:
            raise ValueError(f"{prefix}.effective_to must be after effective_from")
    if value.published_at > value.effective_from:
        raise ValueError(f"{prefix}.published_at must not postdate effective_from")


def _require_local_date(field_name: str, value: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be text")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must use YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{field_name} must use canonical YYYY-MM-DD")
    return value


@dataclass(frozen=True, slots=True)
class MarketRuleSet(CanonicalModel):
    identity: VersionedArtifactIdentity
    venue: str
    board: str
    security_type: str
    risk_label_scope: str
    published_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    source_document_ids: tuple[str, ...]
    source_byte_hashes: tuple[HashDigest, ...]
    rule_clause_refs: tuple[str, ...]
    implementation_state: MarketRuleImplementationState
    allowed_session_kinds: tuple[str, ...]
    order_types: tuple[str, ...]
    price_tick: str
    lower_price_limit: str
    upper_price_limit: str
    buy_lot_size: int
    sell_lot_size: int
    allow_odd_lot_sell: bool
    same_day_sellable: bool
    settlement_cycle_days: int
    suspension_resume_rule: str
    ex_rights_ex_dividend_rule: str
    retrospective_backfill: bool = False

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        for name in ("venue", "board", "security_type", "risk_label_scope"):
            _require_id(name, getattr(self, name))
        _normalize_interval(self, prefix="market_rule_set")
        object.__setattr__(
            self,
            "source_document_ids",
            _require_texts("source_document_ids", self.source_document_ids),
        )
        object.__setattr__(
            self,
            "source_byte_hashes",
            _require_hashes("source_byte_hashes", self.source_byte_hashes),
        )
        object.__setattr__(
            self, "rule_clause_refs", _require_texts("rule_clause_refs", self.rule_clause_refs)
        )
        if not isinstance(self.implementation_state, MarketRuleImplementationState):
            raise TypeError("implementation_state must be MarketRuleImplementationState")
        object.__setattr__(
            self,
            "allowed_session_kinds",
            _require_texts("allowed_session_kinds", self.allowed_session_kinds),
        )
        object.__setattr__(self, "order_types", _require_texts("order_types", self.order_types))
        tick = _decimal("price_tick", self.price_tick, positive=True)
        lower = _non_negative_decimal("lower_price_limit", self.lower_price_limit)
        upper = _decimal("upper_price_limit", self.upper_price_limit, positive=True)
        if (
            lower >= upper
            or (lower / tick) != (lower / tick).to_integral_value()
            or (upper / tick) != (upper / tick).to_integral_value()
        ):
            raise ValueError("price limits must be ordered and legal tick multiples")
        for name in ("buy_lot_size", "sell_lot_size"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if self.settlement_cycle_days < 0:
            raise ValueError("settlement_cycle_days must be non-negative")
        _require_text("suspension_resume_rule", self.suspension_resume_rule)
        _require_text("ex_rights_ex_dividend_rule", self.ex_rights_ex_dividend_rule)


@dataclass(frozen=True, slots=True)
class TradingSession(CanonicalModel):
    session_id: str
    local_trade_date: str
    session_kind: str
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        _require_id("session_id", self.session_id)
        _require_local_date("local_trade_date", self.local_trade_date)
        _require_id("session_kind", self.session_kind)
        object.__setattr__(self, "opens_at", normalize_utc(self.opens_at, field_name="opens_at"))
        object.__setattr__(self, "closes_at", normalize_utc(self.closes_at, field_name="closes_at"))
        if self.opens_at >= self.closes_at:
            raise ValueError("session opens_at must precede closes_at")


@dataclass(frozen=True, slots=True)
class TradingCalendar(CanonicalModel):
    identity: VersionedArtifactIdentity
    venue: str
    market_timezone: str
    published_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    source_document_ids: tuple[str, ...]
    source_byte_hashes: tuple[HashDigest, ...]
    sessions: tuple[TradingSession, ...]
    retrospective_backfill: bool = False

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("venue", self.venue)
        _require_text("market_timezone", self.market_timezone)
        _normalize_interval(self, prefix="trading_calendar")
        object.__setattr__(
            self,
            "source_document_ids",
            _require_texts("source_document_ids", self.source_document_ids),
        )
        object.__setattr__(
            self,
            "source_byte_hashes",
            _require_hashes("source_byte_hashes", self.source_byte_hashes),
        )
        if not isinstance(self.sessions, (list, tuple)) or not self.sessions:
            raise ValueError("sessions must contain at least one TradingSession")
        sessions = tuple(sorted(self.sessions, key=lambda item: (item.opens_at, item.session_id)))
        if any(not isinstance(item, TradingSession) for item in sessions):
            raise TypeError("sessions must contain TradingSession values")
        if len({item.session_id for item in sessions}) != len(sessions):
            raise ValueError("session_id values must be unique")
        if any(
            left.closes_at > right.opens_at
            for left, right in zip(sessions, sessions[1:], strict=False)
        ):
            raise ValueError("trading sessions must not overlap")
        if any(
            not _interval_contains(self.effective_from, self.effective_to, item.opens_at)
            for item in sessions
        ):
            raise ValueError("all sessions must fall within the calendar effective interval")
        object.__setattr__(self, "sessions", sessions)


@dataclass(frozen=True, slots=True)
class SecuritySessionState(CanonicalModel):
    identity: VersionedArtifactIdentity
    security_id: str
    session_id: str
    listed_and_eligible: bool
    suspended: bool
    one_price_limit_up: bool
    one_price_limit_down: bool
    verified_opposing_liquidity: bool
    quote_legal_and_provable: bool

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("security_id", self.security_id)
        _require_id("session_id", self.session_id)


@dataclass(frozen=True, slots=True)
class ProposalReferencePrice(CanonicalModel):
    identity: VersionedArtifactIdentity
    security_id: str
    observed_at: datetime
    price: str
    source_fixture_ref: str
    not_executable_price: bool = True
    synthetic: bool = True

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("security_id", self.security_id)
        object.__setattr__(
            self, "observed_at", normalize_utc(self.observed_at, field_name="observed_at")
        )
        _decimal("price", self.price, positive=True)
        _require_id("source_fixture_ref", self.source_fixture_ref)
        if not self.not_executable_price or not self.synthetic:
            raise ValueError("proposal reference price must be synthetic and non-executable")


@dataclass(frozen=True, slots=True)
class MarketObservation(CanonicalModel):
    observation_id: str
    session_id: str
    data_quality: MarketDataQuality
    window_start: datetime
    window_end: datetime
    available_at: datetime
    volume: int
    turnover: str
    benchmark_price: str

    def __post_init__(self) -> None:
        _require_id("observation_id", self.observation_id)
        _require_id("session_id", self.session_id)
        if not isinstance(self.data_quality, MarketDataQuality):
            raise TypeError("data_quality must be MarketDataQuality")
        for name in ("window_start", "window_end", "available_at"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if self.window_start >= self.window_end or self.available_at > self.window_end:
            raise ValueError("observation window and availability timestamps are invalid")
        if isinstance(self.volume, bool) or not isinstance(self.volume, int) or self.volume < 0:
            raise ValueError("volume must be a non-negative integer")
        _non_negative_decimal("turnover", self.turnover)
        _decimal("benchmark_price", self.benchmark_price, positive=True)


@dataclass(frozen=True, slots=True)
class MarketObservationSet(CanonicalModel):
    identity: VersionedArtifactIdentity
    security_id: str
    observations: tuple[MarketObservation, ...]
    synthetic: bool = True

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("security_id", self.security_id)
        if not isinstance(self.observations, (list, tuple)) or any(
            not isinstance(item, MarketObservation) for item in self.observations
        ):
            raise TypeError("observations must contain MarketObservation values")
        values = tuple(
            sorted(self.observations, key=lambda item: (item.window_end, item.observation_id))
        )
        if len({item.observation_id for item in values}) != len(values):
            raise ValueError("observation_id values must be unique")
        object.__setattr__(self, "observations", values)
        if not self.synthetic:
            raise ValueError("Stage 5B accepts synthetic market observations only")


@dataclass(frozen=True, slots=True)
class CostSchedule(CanonicalModel):
    identity: VersionedArtifactIdentity
    venue: str
    security_type: str
    side: TradeSide
    account_fee_version: str
    published_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    exchange_fee_rate: str
    regulatory_fee_rate: str
    transfer_fee_rate: str
    tax_rate: str
    broker_commission_rate: str
    broker_minimum_commission: str
    rounding_unit: str
    currency: str
    source_document_ids: tuple[str, ...]
    source_byte_hashes: tuple[HashDigest, ...]
    retrospective_backfill: bool = False

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("venue", self.venue)
        _require_id("security_type", self.security_type)
        if not isinstance(self.side, TradeSide):
            raise TypeError("side must be TradeSide")
        _require_text("account_fee_version", self.account_fee_version)
        _normalize_interval(self, prefix="cost_schedule")
        for name in (
            "exchange_fee_rate",
            "regulatory_fee_rate",
            "transfer_fee_rate",
            "tax_rate",
            "broker_commission_rate",
            "broker_minimum_commission",
        ):
            _non_negative_decimal(name, getattr(self, name))
        _decimal("rounding_unit", self.rounding_unit, positive=True)
        if len(self.currency) != 3 or not self.currency.isupper():
            raise ValueError("currency must be an uppercase ISO-style code")
        object.__setattr__(
            self,
            "source_document_ids",
            _require_texts("source_document_ids", self.source_document_ids),
        )
        object.__setattr__(
            self,
            "source_byte_hashes",
            _require_hashes("source_byte_hashes", self.source_byte_hashes),
        )


@dataclass(frozen=True, slots=True)
class ImpactNode(CanonicalModel):
    participation_rate: str
    adverse_slippage_rate: str

    def __post_init__(self) -> None:
        participation = _non_negative_decimal("participation_rate", self.participation_rate)
        slippage = _non_negative_decimal("adverse_slippage_rate", self.adverse_slippage_rate)
        if participation > 1 or slippage > 1:
            raise ValueError("impact rates must be between zero and one")


@dataclass(frozen=True, slots=True)
class ImpactCurve(CanonicalModel):
    identity: VersionedArtifactIdentity
    venue: str
    security_type: str
    side: TradeSide
    data_quality: MarketDataQuality
    published_at: datetime
    effective_from: datetime
    effective_to: datetime | None
    nodes: tuple[ImpactNode, ...]
    source_document_ids: tuple[str, ...]
    source_byte_hashes: tuple[HashDigest, ...]
    retrospective_backfill: bool = False

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        _require_id("venue", self.venue)
        _require_id("security_type", self.security_type)
        if not isinstance(self.side, TradeSide):
            raise TypeError("side must be TradeSide")
        if not isinstance(self.data_quality, MarketDataQuality):
            raise TypeError("data_quality must be MarketDataQuality")
        _normalize_interval(self, prefix="impact_curve")
        if (
            not isinstance(self.nodes, (list, tuple))
            or len(self.nodes) < 2
            or any(not isinstance(item, ImpactNode) for item in self.nodes)
        ):
            raise ValueError("impact curve must contain at least two ImpactNode values")
        nodes = tuple(self.nodes)
        rates = tuple(Decimal(item.participation_rate) for item in nodes)
        slippages = tuple(Decimal(item.adverse_slippage_rate) for item in nodes)
        if rates[0] != 0 or any(
            left >= right for left, right in zip(rates, rates[1:], strict=False)
        ):
            raise ValueError("impact participation must start at zero and strictly increase")
        if any(left > right for left, right in zip(slippages, slippages[1:], strict=False)):
            raise ValueError("adverse slippage must be monotonic non-decreasing")
        object.__setattr__(self, "nodes", nodes)
        object.__setattr__(
            self,
            "source_document_ids",
            _require_texts("source_document_ids", self.source_document_ids),
        )
        object.__setattr__(
            self,
            "source_byte_hashes",
            _require_hashes("source_byte_hashes", self.source_byte_hashes),
        )


@dataclass(frozen=True, slots=True)
class SyntheticApprovalFixture(CanonicalModel):
    identity: VersionedArtifactIdentity
    case_id: str
    security_id: str
    account_fixture_id: str
    action_intent: Stage5ActionIntent
    approved_at: datetime
    expires_at: datetime
    approved_quantity: int
    approved_notional_cap: str
    proposal_reference_price_hash: HashDigest
    synthetic: bool = True
    may_only_reduce: bool = True

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        for name in ("case_id", "security_id", "account_fixture_id"):
            _require_id(name, getattr(self, name))
        if not isinstance(self.action_intent, Stage5ActionIntent):
            raise TypeError("action_intent must be Stage5ActionIntent")
        for name in ("approved_at", "expires_at"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if self.approved_at >= self.expires_at:
            raise ValueError("synthetic approval must expire after approval")
        if (
            isinstance(self.approved_quantity, bool)
            or not isinstance(self.approved_quantity, int)
            or self.approved_quantity <= 0
        ):
            raise ValueError("approved_quantity must be a positive integer")
        _decimal("approved_notional_cap", self.approved_notional_cap, positive=True)
        if not isinstance(self.proposal_reference_price_hash, HashDigest):
            raise TypeError("proposal_reference_price_hash must be HashDigest")
        if not self.synthetic or not self.may_only_reduce:
            raise ValueError("approval fixture must be synthetic and reduction-only")


@dataclass(frozen=True, slots=True)
class Stage5SubmissionReductionConstraint(CanonicalModel):
    """Content-addressed, reduction-only limits issued by the Stage 5C engine.

    The market executor does not interpret portfolio semantics.  It only applies
    these already-computed ceilings to each executable quote before creating a
    synthetic order or fill.
    """

    identity: VersionedArtifactIdentity
    case_id: str
    strategy_id: str
    security_id: str
    account_fixture_id: str
    action_intent: Stage5ActionIntent
    as_of: datetime
    effective_approved_quantity: int
    maximum_quantity: int
    maximum_gross_notional: str | None
    maximum_cash_outflow: str | None
    maximum_transaction_cost_reserve: str | None
    maximum_sellable_quantity: int | None
    candidate_hash: HashDigest
    candidate_session_id: str | None
    candidate_observation_id: str | None
    candidate_at: datetime | None
    candidate_market_rule_hash: HashDigest | None
    candidate_cost_schedule_hash: HashDigest | None
    candidate_impact_curve_hash: HashDigest | None
    target_hash: HashDigest
    portfolio_approval_hash: HashDigest
    market_approval_hash: HashDigest
    source_account_snapshot_hash: HashDigest
    source_initial_ledger_hash: HashDigest
    source_risk_cluster_hash: HashDigest
    source_market_regime_hash: HashDigest
    expected_ledger_head_hash: HashDigest
    reason_codes: tuple[str, ...]
    synthetic: bool = True
    validation_only: bool = True
    may_only_reduce: bool = True

    def __post_init__(self) -> None:
        _require_identity(self.identity)
        for name in ("case_id", "strategy_id", "security_id", "account_fixture_id"):
            _require_id(name, getattr(self, name))
        if not isinstance(self.action_intent, Stage5ActionIntent):
            raise TypeError("action_intent must be Stage5ActionIntent")
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        if (
            isinstance(self.effective_approved_quantity, bool)
            or not isinstance(self.effective_approved_quantity, int)
            or self.effective_approved_quantity < 0
        ):
            raise ValueError("effective_approved_quantity must be non-negative")
        if (
            isinstance(self.maximum_quantity, bool)
            or not isinstance(self.maximum_quantity, int)
            or self.maximum_quantity < 0
        ):
            raise ValueError("maximum_quantity must be a non-negative integer")
        if self.maximum_quantity > self.effective_approved_quantity:
            raise ValueError("maximum_quantity cannot exceed effective approval")
        for name in ("candidate_session_id", "candidate_observation_id"):
            value = getattr(self, name)
            if value is not None:
                _require_id(name, value)
        if self.candidate_at is not None:
            object.__setattr__(
                self,
                "candidate_at",
                normalize_utc(self.candidate_at, field_name="candidate_at"),
            )
        side = _side(self.action_intent)
        if side is TradeSide.BUY:
            if (
                self.maximum_gross_notional is None
                or self.maximum_cash_outflow is None
                or self.maximum_transaction_cost_reserve is None
                or self.maximum_sellable_quantity is not None
            ):
                raise ValueError(
                    "buy constraints require gross-notional, cash-outflow and cost-reserve caps"
                )
            _non_negative_decimal("maximum_gross_notional", self.maximum_gross_notional)
            _non_negative_decimal("maximum_cash_outflow", self.maximum_cash_outflow)
            _non_negative_decimal(
                "maximum_transaction_cost_reserve",
                self.maximum_transaction_cost_reserve,
            )
        elif (
            self.maximum_gross_notional is None
            or self.maximum_cash_outflow is not None
            or self.maximum_transaction_cost_reserve is not None
            or self.maximum_sellable_quantity is None
        ):
            raise ValueError(
                "sell constraints require gross-notional and sellable-quantity caps only"
            )
        elif (
            isinstance(self.maximum_sellable_quantity, bool)
            or not isinstance(self.maximum_sellable_quantity, int)
            or self.maximum_sellable_quantity < 0
        ):
            raise ValueError("maximum_sellable_quantity must be a non-negative integer")
        else:
            _non_negative_decimal("maximum_gross_notional", self.maximum_gross_notional)
        for name in (
            "candidate_hash",
            "target_hash",
            "portfolio_approval_hash",
            "market_approval_hash",
            "source_account_snapshot_hash",
            "source_initial_ledger_hash",
            "source_risk_cluster_hash",
            "source_market_regime_hash",
            "expected_ledger_head_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        for name in (
            "candidate_market_rule_hash",
            "candidate_cost_schedule_hash",
            "candidate_impact_curve_hash",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, HashDigest):
                raise TypeError(f"{name} must be HashDigest or None")
        candidate_parts = (
            self.candidate_session_id,
            self.candidate_observation_id,
            self.candidate_at,
            self.candidate_market_rule_hash,
            self.candidate_cost_schedule_hash,
            self.candidate_impact_curve_hash,
        )
        if any(value is None for value in candidate_parts) and any(
            value is not None for value in candidate_parts
        ):
            raise ValueError("candidate binding fields must be either complete or all None")
        object.__setattr__(
            self,
            "reason_codes",
            _require_texts("reason_codes", self.reason_codes),
        )
        if not self.synthetic or not self.validation_only or not self.may_only_reduce:
            raise ValueError("submission constraints must be synthetic reduction-only fixtures")


@dataclass(frozen=True, slots=True)
class Stage5MarketExecutionCase(CanonicalModel):
    case_id: str
    strategy_id: str
    security_id: str
    account_fixture_id: str
    venue: str
    board: str
    security_type: str
    risk_label: str
    account_fee_version: str
    action_intent: Stage5ActionIntent
    knowledge_cutoff: datetime
    decision_at: datetime
    strategy_processing_completed_at: datetime
    timing_precision: TimingPrecision
    decision_local_trade_date: str
    stage4_case: Stage4CompleteSyntheticCase
    stage4_complete_result: Stage4CompleteResult
    stage4_replay_hash: HashDigest
    proposal_reference_price: ProposalReferencePrice
    proposed_quantity: int
    synthetic_approval_fixture: SyntheticApprovalFixture
    market_rule_sets: tuple[MarketRuleSet, ...]
    trading_calendar: TradingCalendar
    security_session_states: tuple[SecuritySessionState, ...]
    market_observation_set: MarketObservationSet
    cost_schedules: tuple[CostSchedule, ...]
    impact_curves: tuple[ImpactCurve, ...]
    add_reunderwriting_ref: str | None
    risk_exit_mandate_ref: str | None
    code_commit: str
    config_hash: HashDigest
    injected_clock: datetime
    run_mode: RunMode = RunMode.RESEARCH
    anonymous_synthetic_fixture: bool = True
    validation_only: bool = True
    reads_kb_internal_state: bool = False
    connects_broker: bool = False

    def __post_init__(self) -> None:
        for name in (
            "case_id",
            "strategy_id",
            "security_id",
            "account_fixture_id",
            "venue",
            "board",
            "security_type",
            "risk_label",
        ):
            _require_id(name, getattr(self, name))
        _require_text("account_fee_version", self.account_fee_version)
        if not isinstance(self.action_intent, Stage5ActionIntent):
            raise TypeError("action_intent must be Stage5ActionIntent")
        for name in (
            "knowledge_cutoff",
            "decision_at",
            "strategy_processing_completed_at",
            "injected_clock",
        ):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if self.knowledge_cutoff > self.decision_at:
            raise ValueError("knowledge_cutoff must not postdate decision_at")
        if self.decision_at > self.strategy_processing_completed_at:
            raise ValueError("decision_at must not postdate strategy processing completion")
        if not isinstance(self.timing_precision, TimingPrecision):
            raise TypeError("timing_precision must be TimingPrecision")
        _require_local_date("decision_local_trade_date", self.decision_local_trade_date)
        if not isinstance(self.stage4_case, Stage4CompleteSyntheticCase):
            raise TypeError("stage4_case must be Stage4CompleteSyntheticCase")
        if not isinstance(self.stage4_complete_result, Stage4CompleteResult):
            raise TypeError("stage4_complete_result must be Stage4CompleteResult")
        if not isinstance(self.stage4_replay_hash, HashDigest):
            raise TypeError("stage4_replay_hash must be HashDigest")
        if not isinstance(self.proposal_reference_price, ProposalReferencePrice):
            raise TypeError("proposal_reference_price must be ProposalReferencePrice")
        if not isinstance(self.synthetic_approval_fixture, SyntheticApprovalFixture):
            raise TypeError("synthetic_approval_fixture must be SyntheticApprovalFixture")
        if not isinstance(self.trading_calendar, TradingCalendar):
            raise TypeError("trading_calendar must be TradingCalendar")
        if not isinstance(self.market_observation_set, MarketObservationSet):
            raise TypeError("market_observation_set must be MarketObservationSet")
        if any(not isinstance(item, MarketRuleSet) for item in self.market_rule_sets):
            raise TypeError("market_rule_sets must contain MarketRuleSet values")
        if any(not isinstance(item, SecuritySessionState) for item in self.security_session_states):
            raise TypeError("security_session_states must contain SecuritySessionState values")
        if any(not isinstance(item, CostSchedule) for item in self.cost_schedules):
            raise TypeError("cost_schedules must contain CostSchedule values")
        if any(not isinstance(item, ImpactCurve) for item in self.impact_curves):
            raise TypeError("impact_curves must contain ImpactCurve values")
        object.__setattr__(self, "market_rule_sets", tuple(self.market_rule_sets))
        object.__setattr__(self, "security_session_states", tuple(self.security_session_states))
        object.__setattr__(self, "cost_schedules", tuple(self.cost_schedules))
        object.__setattr__(self, "impact_curves", tuple(self.impact_curves))
        if (
            isinstance(self.proposed_quantity, bool)
            or not isinstance(self.proposed_quantity, int)
            or self.proposed_quantity <= 0
        ):
            raise ValueError("proposed_quantity must be a positive integer")
        for name in ("add_reunderwriting_ref", "risk_exit_mandate_ref"):
            value = getattr(self, name)
            if value is not None:
                _require_id(name, value)
        _require_text("code_commit", self.code_commit)
        if not isinstance(self.config_hash, HashDigest):
            raise TypeError("config_hash must be HashDigest")
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be RunMode")


@dataclass(frozen=True, slots=True)
class SyntheticCostBreakdown(CanonicalModel):
    exchange_fee: str
    regulatory_fee: str
    transfer_fee: str
    tax: str
    broker_commission: str
    total: str


@dataclass(frozen=True, slots=True)
class Stage5GateRecheck(CanonicalModel):
    historical_gate3_outcome: GateOutcome
    current_market_pricing_state: MarketPricingState | None
    current_gate3_outcome: GateOutcome
    current_gate4_outcome: GateOutcome | None
    net_base_remaining_return: str | None
    net_downside_return: str | None
    downside_loss: str | None
    reward_to_downside: str | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SyntheticOrderIntent(CanonicalModel):
    order_intent_id: str
    case_id: str
    security_id: str
    account_fixture_id: str
    side: TradeSide
    quantity: int
    limit_price: str
    time_in_force: str
    submitted_at: datetime
    market_rule_hash: HashDigest
    cost_schedule_hash: HashDigest
    impact_curve_hash: HashDigest
    synthetic: bool = True
    validation_only: bool = True
    broker_route: None = field(default=None, init=False)
    real_account: None = field(default=None, init=False)


@dataclass(frozen=True, slots=True)
class SyntheticFill(CanonicalModel):
    fill_id: str
    order_intent_id: str
    security_id: str
    side: TradeSide
    quantity: int
    benchmark_vwap: str
    adverse_slippage_rate: str
    fill_price: str
    gross_notional: str
    costs: SyntheticCostBreakdown
    cash_effect: str
    filled_at: datetime
    observation_id: str
    synthetic: bool = True
    validation_only: bool = True


@dataclass(frozen=True, slots=True)
class SyntheticExecutionEvent(CanonicalModel):
    event_time: datetime
    event_type_priority: int
    stable_event_id: str
    event_type: SyntheticEventType
    quantity: int


@dataclass(frozen=True, slots=True)
class Stage5ExecutionAttempt(CanonicalModel):
    attempt_day: int
    local_trade_date: str
    session_id: str
    observation_id: str | None
    status: Stage5ExecutionStatus
    reason_codes: tuple[str, ...]
    market_rule_hash: HashDigest | None
    cost_schedule_hash: HashDigest | None
    impact_curve_hash: HashDigest | None
    capacity_quantity: int | None
    candidate_quantity: int | None
    gate_recheck: Stage5GateRecheck | None


@dataclass(frozen=True, slots=True)
class Stage5MarketExecutionResult(CanonicalModel):
    schema_version: str
    case_id: str
    status: Stage5ExecutionStatus
    reason_codes: tuple[str, ...]
    input_hash: HashDigest
    stage4_replay_hash: HashDigest
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    execution_eligible_from: datetime
    proposal_reference_price_hash: HashDigest
    attempts: tuple[Stage5ExecutionAttempt, ...]
    order_intent: SyntheticOrderIntent | None
    fill: SyntheticFill | None
    events: tuple[SyntheticExecutionEvent, ...]
    cancelled_quantity: int
    replay_hash: HashDigest
    approval_scope: RuleApprovalScope = field(default=STAGE5_APPROVAL_SCOPE, init=False)
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_real_accounts: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)
    connects_broker: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class Stage5MarketCandidate(CanonicalModel):
    """No-side-effect Stage 5B candidate used by the Stage 5C seam."""

    schema_version: str
    case_input_hash: HashDigest
    market_execution_preview: Stage5MarketExecutionResult
    candidate_session_id: str | None
    candidate_observation_id: str | None
    candidate_at: datetime | None
    candidate_market_rule_hash: HashDigest | None
    candidate_cost_schedule_hash: HashDigest | None
    candidate_impact_curve_hash: HashDigest | None
    candidate_hash: HashDigest
    preview_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class Stage5ConstrainedMarketExecutionProjection(CanonicalModel):
    """Stage 5B output bound to an exact Stage 5C reduction constraint."""

    schema_version: str
    market_candidate: Stage5MarketCandidate
    constraint_hash: HashDigest
    market_execution_result: Stage5MarketExecutionResult
    effective_approved_quantity: int
    unsubmitted_quantity: int
    unfilled_cancelled_quantity: int
    replay_hash: HashDigest
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)


Stage5Artifact = (
    MarketRuleSet
    | TradingCalendar
    | SecuritySessionState
    | ProposalReferencePrice
    | MarketObservationSet
    | CostSchedule
    | ImpactCurve
    | SyntheticApprovalFixture
    | Stage5SubmissionReductionConstraint
)


def stage5_artifact_content_sha256(value: Stage5Artifact) -> str:
    """Hash a Stage 5B artifact without its self-referential declared hash."""

    projected = value.to_json_value()
    identity = projected.get("identity")
    if not isinstance(identity, dict):
        raise TypeError("artifact identity projection must be an object")
    del identity["declared_content_hash"]
    return canonical_sha256(projected)


def bind_stage5_artifact[ArtifactT: Stage5Artifact](value: ArtifactT) -> ArtifactT:
    """Return the artifact with its deterministic content hash bound."""

    identity = replace(
        value.identity,
        declared_content_hash=_hash(stage5_artifact_content_sha256(value)),
    )
    return replace(value, identity=identity)


def stage5_market_execution_replay_sha256(
    case: Stage5MarketExecutionCase,
    result: Stage5MarketExecutionResult,
) -> str:
    """Hash every Stage 5B input and deterministic output except the self hash."""

    projected = result.to_json_value()
    del projected["replay_hash"]
    return canonical_sha256({"case": case, "result": projected})


def stage5_constrained_market_execution_replay_sha256(
    case: Stage5MarketExecutionCase,
    candidate: Stage5MarketCandidate,
    constraint: Stage5SubmissionReductionConstraint,
    result: Stage5MarketExecutionResult,
) -> str:
    """Hash a constrained projection without weakening the Stage 5B replay."""

    return canonical_sha256(
        {
            "schema_version": "0.2.0",
            "case": case,
            "market_candidate": candidate,
            "constraint": constraint,
            "market_execution_result": result,
        }
    )


def stage5_market_candidate_sha256(
    case: Stage5MarketExecutionCase,
    preview: Stage5MarketExecutionResult,
    *,
    candidate_session_id: str | None,
    candidate_observation_id: str | None,
    candidate_at: datetime | None,
    candidate_market_rule_hash: HashDigest | None,
    candidate_cost_schedule_hash: HashDigest | None,
    candidate_impact_curve_hash: HashDigest | None,
) -> str:
    """Bind the exact raw case and no-side-effect market preview."""

    return canonical_sha256(
        {
            "schema_version": "0.2.0",
            "case": case,
            "market_execution_preview": preview,
            "selected_candidate": {
                "session_id": candidate_session_id,
                "observation_id": candidate_observation_id,
                "candidate_at": candidate_at,
                "market_rule_hash": candidate_market_rule_hash,
                "cost_schedule_hash": candidate_cost_schedule_hash,
                "impact_curve_hash": candidate_impact_curve_hash,
            },
        }
    )


def _artifact_failure(value: Stage5Artifact) -> str | None:
    if value.identity.declared_content_hash.value != stage5_artifact_content_sha256(value):
        return f"ARTIFACT_HASH_DRIFT:{value.identity.artifact_id}"
    return None


def _interval_contains(
    effective_from: datetime,
    effective_to: datetime | None,
    at: datetime,
) -> bool:
    return effective_from <= at and (effective_to is None or at < effective_to)


def _intervals_overlap(
    left_from: datetime,
    left_to: datetime | None,
    right_from: datetime,
    right_to: datetime | None,
) -> bool:
    return (left_to is None or right_from < left_to) and (right_to is None or left_from < right_to)


def _has_rule_overlap(values: tuple[MarketRuleSet, ...]) -> bool:
    for index, left in enumerate(values):
        left_scope = (left.venue, left.board, left.security_type, left.risk_label_scope)
        for right in values[index + 1 :]:
            right_scope = (right.venue, right.board, right.security_type, right.risk_label_scope)
            if left_scope == right_scope and _intervals_overlap(
                left.effective_from,
                left.effective_to,
                right.effective_from,
                right.effective_to,
            ):
                return True
    return False


def _has_cost_overlap(values: tuple[CostSchedule, ...]) -> bool:
    for index, left in enumerate(values):
        left_scope = (left.venue, left.security_type, left.side, left.account_fee_version)
        for right in values[index + 1 :]:
            right_scope = (right.venue, right.security_type, right.side, right.account_fee_version)
            if left_scope == right_scope and _intervals_overlap(
                left.effective_from,
                left.effective_to,
                right.effective_from,
                right.effective_to,
            ):
                return True
    return False


def _has_impact_overlap(values: tuple[ImpactCurve, ...]) -> bool:
    for index, left in enumerate(values):
        left_scope = (left.venue, left.security_type, left.side, left.data_quality)
        for right in values[index + 1 :]:
            right_scope = (right.venue, right.security_type, right.side, right.data_quality)
            if left_scope == right_scope and _intervals_overlap(
                left.effective_from,
                left.effective_to,
                right.effective_from,
                right.effective_to,
            ):
                return True
    return False


def _precheck_failure(case: Stage5MarketExecutionCase) -> str | None:
    if (
        case.strategy_id != STAGE5_STRATEGY_ID
        or case.run_mode is not RunMode.RESEARCH
        or not case.anonymous_synthetic_fixture
        or not case.validation_only
        or case.reads_kb_internal_state
        or case.connects_broker
    ):
        return "STAGE5B_AUTHORITY_BOUNDARY_VIOLATION"
    if (
        case.stage4_case.case_id != case.case_id
        or case.stage4_complete_result.case_id != case.case_id
    ):
        return "STAGE4_CASE_ID_MISMATCH"
    if case.stage4_case.input_hash() != case.stage4_complete_result.input_hash:
        return "STAGE4_INPUT_HASH_MISMATCH"
    if (
        case.stage4_replay_hash != case.stage4_complete_result.replay_hash
        or complete_stage4_replay_sha256(case.stage4_complete_result)
        != case.stage4_replay_hash.value
    ):
        return "STAGE4_REPLAY_HASH_MISMATCH"
    if case.stage4_case.knowledge_cutoff != case.knowledge_cutoff:
        return "STAGE4_KNOWLEDGE_CUTOFF_MISMATCH"
    proposal = case.proposal_reference_price
    approval = case.synthetic_approval_fixture
    if (
        proposal.security_id != case.security_id
        or case.market_observation_set.security_id != case.security_id
        or case.trading_calendar.venue != case.venue
    ):
        return "STAGE5B_SCOPE_MISMATCH"
    if any(state.security_id != case.security_id for state in case.security_session_states):
        return "SECURITY_SESSION_SCOPE_MISMATCH"
    if (
        approval.case_id != case.case_id
        or approval.security_id != case.security_id
        or approval.account_fixture_id != case.account_fixture_id
        or approval.action_intent is not case.action_intent
    ):
        return "SYNTHETIC_APPROVAL_SCOPE_MISMATCH"
    if approval.approved_quantity > case.proposed_quantity:
        return "SYNTHETIC_APPROVAL_INCREASE_FORBIDDEN"
    if approval.proposal_reference_price_hash != proposal.identity.declared_content_hash:
        return "PROPOSAL_REFERENCE_PRICE_BINDING_MISMATCH"
    if not (case.strategy_processing_completed_at <= proposal.observed_at < approval.approved_at):
        return "PROPOSAL_REFERENCE_PRICE_WINDOW_INVALID"
    artifacts: tuple[Stage5Artifact, ...] = (
        *case.market_rule_sets,
        case.trading_calendar,
        *case.security_session_states,
        proposal,
        case.market_observation_set,
        *case.cost_schedules,
        *case.impact_curves,
        approval,
    )
    for artifact in artifacts:
        failure = _artifact_failure(artifact)
        if failure is not None:
            return failure
    if _has_rule_overlap(case.market_rule_sets):
        return "MARKET_RULE_EFFECTIVE_INTERVAL_OVERLAP"
    if _has_cost_overlap(case.cost_schedules):
        return "COST_SCHEDULE_EFFECTIVE_INTERVAL_OVERLAP"
    if _has_impact_overlap(case.impact_curves):
        return "IMPACT_CURVE_EFFECTIVE_INTERVAL_OVERLAP"
    if (
        any(item.retrospective_backfill for item in case.market_rule_sets)
        or case.trading_calendar.retrospective_backfill
        or any(item.retrospective_backfill for item in case.cost_schedules)
        or any(item.retrospective_backfill for item in case.impact_curves)
    ):
        return "CURRENT_RULE_BACKFILL_INTO_HISTORY_FORBIDDEN"
    state_session_ids = tuple(item.session_id for item in case.security_session_states)
    if len(set(state_session_ids)) != len(state_session_ids):
        return "SECURITY_SESSION_STATE_DUPLICATE"
    calendar_session_ids = {item.session_id for item in case.trading_calendar.sessions}
    if any(item not in calendar_session_ids for item in state_session_ids):
        return "SECURITY_SESSION_NOT_IN_CALENDAR"
    if any(
        item.session_id not in calendar_session_ids
        for item in case.market_observation_set.observations
    ):
        return "MARKET_OBSERVATION_SESSION_NOT_IN_CALENDAR"
    stage4 = case.stage4_complete_result
    if case.action_intent in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD):
        if (
            stage4.evaluation_state is not CompleteStage4EvaluationState.COMPLETED
            or stage4.overall_outcome is not GateOutcome.PASS
            or stage4.research_decision_label is not DecisionState.TRADE_READY
        ):
            return "ENTER_OR_ADD_REQUIRES_EXACT_STAGE4_PASS"
        four_gates = (
            stage4.unified_gate_view.gate_1,
            stage4.unified_gate_view.gate_2,
            stage4.unified_gate_view.gate_3,
            stage4.unified_gate_view.gate_4,
        )
        if any(item.outcome is not GateOutcome.PASS for item in four_gates):
            return "ENTER_OR_ADD_REQUIRES_FOUR_GATE_PASS"
        if case.action_intent is Stage5ActionIntent.ADD and case.add_reunderwriting_ref is None:
            return "ADD_REQUIRES_E5_OR_E6_REUNDERWRITING"
    elif (
        stage4.exit_disposition is not ExitDisposition.EXIT_CANDIDATE
        and case.risk_exit_mandate_ref is None
    ):
        return "REDUCE_OR_EXIT_REQUIRES_EXIT_CANDIDATE_OR_RISK_MANDATE"
    return None


def _submission_constraint_failure(
    case: Stage5MarketExecutionCase,
    constraint: Stage5SubmissionReductionConstraint,
) -> str | None:
    if (
        constraint.case_id != case.case_id
        or constraint.strategy_id != case.strategy_id
        or constraint.security_id != case.security_id
        or constraint.account_fixture_id != case.account_fixture_id
        or constraint.action_intent is not case.action_intent
    ):
        return "SUBMISSION_REDUCTION_CONSTRAINT_SCOPE_MISMATCH"
    if (
        constraint.effective_approved_quantity > case.synthetic_approval_fixture.approved_quantity
        or constraint.maximum_quantity > constraint.effective_approved_quantity
    ):
        return "SUBMISSION_REDUCTION_CONSTRAINT_INCREASE_FORBIDDEN"
    if (
        constraint.market_approval_hash
        != case.synthetic_approval_fixture.identity.declared_content_hash
    ):
        return "SUBMISSION_REDUCTION_CONSTRAINT_APPROVAL_MISMATCH"
    if (
        constraint.maximum_sellable_quantity is not None
        and constraint.maximum_quantity > constraint.maximum_sellable_quantity
    ):
        return "SUBMISSION_REDUCTION_CONSTRAINT_SELLABLE_MISMATCH"
    return _artifact_failure(constraint)


def _side(action: Stage5ActionIntent) -> TradeSide:
    return (
        TradeSide.BUY
        if action in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD)
        else TradeSide.SELL
    )


def _select_market_rule(
    case: Stage5MarketExecutionCase,
    at: datetime,
) -> tuple[MarketRuleSet | None, str | None]:
    matches = tuple(
        item
        for item in case.market_rule_sets
        if (item.venue, item.board, item.security_type, item.risk_label_scope)
        == (case.venue, case.board, case.security_type, case.risk_label)
        and _interval_contains(item.effective_from, item.effective_to, at)
    )
    if len(matches) != 1:
        return None, (
            "MARKET_RULE_EFFECTIVE_INTERVAL_GAP"
            if not matches
            else "MARKET_RULE_EFFECTIVE_INTERVAL_OVERLAP"
        )
    rule = matches[0]
    if rule.published_at > at:
        return None, "MARKET_RULE_NOT_PUBLISHED_AT_EXECUTION_TIME"
    if rule.implementation_state is not MarketRuleImplementationState.EFFECTIVE:
        return None, "MARKET_RULE_NOT_EFFECTIVE"
    return rule, None


def _select_cost(
    case: Stage5MarketExecutionCase,
    side: TradeSide,
    at: datetime,
) -> CostSchedule | None:
    matches = tuple(
        item
        for item in case.cost_schedules
        if (item.venue, item.security_type, item.side, item.account_fee_version)
        == (case.venue, case.security_type, side, case.account_fee_version)
        and _interval_contains(item.effective_from, item.effective_to, at)
        and item.published_at <= at
    )
    return matches[0] if len(matches) == 1 else None


def _select_impact(
    case: Stage5MarketExecutionCase,
    side: TradeSide,
    quality: MarketDataQuality,
    at: datetime,
) -> ImpactCurve | None:
    matches = tuple(
        item
        for item in case.impact_curves
        if (item.venue, item.security_type, item.side, item.data_quality)
        == (case.venue, case.security_type, side, quality)
        and _interval_contains(item.effective_from, item.effective_to, at)
        and item.published_at <= at
    )
    return matches[0] if len(matches) == 1 else None


def _round_to_tick(value: Decimal, tick: Decimal, side: TradeSide) -> Decimal:
    rounding = ROUND_CEILING if side is TradeSide.BUY else ROUND_FLOOR
    return (value / tick).to_integral_value(rounding=rounding) * tick


def _round_fee(value: Decimal, unit: Decimal) -> Decimal:
    return (value / unit).to_integral_value(rounding=ROUND_CEILING) * unit


def _interpolate_impact(curve: ImpactCurve, participation: Decimal) -> Decimal | None:
    nodes = tuple(
        (Decimal(item.participation_rate), Decimal(item.adverse_slippage_rate))
        for item in curve.nodes
    )
    if participation < nodes[0][0] or participation > nodes[-1][0]:
        return None
    for left, right in zip(nodes, nodes[1:], strict=False):
        if participation == left[0]:
            return left[1]
        if left[0] < participation <= right[0]:
            ratio = (participation - left[0]) / (right[0] - left[0])
            return left[1] + ratio * (right[1] - left[1])
    return nodes[-1][1]


def _costs(gross: Decimal, schedule: CostSchedule) -> SyntheticCostBreakdown:
    unit = Decimal(schedule.rounding_unit)
    exchange = _round_fee(gross * Decimal(schedule.exchange_fee_rate), unit)
    regulatory = _round_fee(gross * Decimal(schedule.regulatory_fee_rate), unit)
    transfer = _round_fee(gross * Decimal(schedule.transfer_fee_rate), unit)
    tax = _round_fee(gross * Decimal(schedule.tax_rate), unit)
    commission = max(
        _round_fee(gross * Decimal(schedule.broker_commission_rate), unit),
        Decimal(schedule.broker_minimum_commission),
    )
    commission = _round_fee(commission, unit)
    total = exchange + regulatory + transfer + tax + commission
    return SyntheticCostBreakdown(
        exchange_fee=_canonical_decimal(exchange),
        regulatory_fee=_canonical_decimal(regulatory),
        transfer_fee=_canonical_decimal(transfer),
        tax=_canonical_decimal(tax),
        broker_commission=_canonical_decimal(commission),
        total=_canonical_decimal(total),
    )


@dataclass(frozen=True, slots=True)
class _Quote:
    quantity: int
    participation: Decimal
    slippage: Decimal
    fill_price: Decimal
    gross: Decimal
    costs: SyntheticCostBreakdown


def _quote(
    quantity: int,
    observation: MarketObservation,
    rule: MarketRuleSet,
    curve: ImpactCurve,
    cost: CostSchedule,
    side: TradeSide,
) -> _Quote | None:
    participation = Decimal(quantity) / Decimal(observation.volume)
    slippage = _interpolate_impact(curve, participation)
    if slippage is None:
        return None
    benchmark = Decimal(observation.benchmark_price)
    raw_fill = (
        benchmark * (Decimal(1) + slippage)
        if side is TradeSide.BUY
        else benchmark * (Decimal(1) - slippage)
    )
    fill_price = _round_to_tick(raw_fill, Decimal(rule.price_tick), side)
    if (
        fill_price < Decimal(rule.lower_price_limit)
        or fill_price > Decimal(rule.upper_price_limit)
        or (side is TradeSide.BUY and fill_price < benchmark)
        or (side is TradeSide.SELL and fill_price > benchmark)
    ):
        return None
    gross = fill_price * Decimal(quantity)
    return _Quote(
        quantity=quantity,
        participation=participation,
        slippage=slippage,
        fill_price=fill_price,
        gross=gross,
        costs=_costs(gross, cost),
    )


def _affordable_quote(
    maximum_quantity: int,
    lot_size: int,
    notional_cap: Decimal,
    observation: MarketObservation,
    rule: MarketRuleSet,
    curve: ImpactCurve,
    cost: CostSchedule,
    side: TradeSide,
    maximum_cash_outflow: Decimal | None = None,
    maximum_transaction_cost_reserve: Decimal | None = None,
) -> _Quote | None:
    """Find the greatest deterministic lot that stays within the approved notional cap."""

    lot_count = maximum_quantity // lot_size
    low = 1
    high = lot_count
    best: _Quote | None = None
    while low <= high:
        middle = (low + high) // 2
        candidate = _quote(
            middle * lot_size,
            observation,
            rule,
            curve,
            cost,
            side,
        )
        actual_transaction_cost = (
            Decimal(candidate.costs.total)
            if candidate is not None and side is TradeSide.BUY
            else Decimal(0)
        )
        reserved_cash_outflow = (
            candidate.gross + maximum_transaction_cost_reserve
            if candidate is not None
            and side is TradeSide.BUY
            and maximum_transaction_cost_reserve is not None
            else Decimal(0)
        )
        if (
            candidate is not None
            and candidate.gross <= notional_cap
            and (
                maximum_transaction_cost_reserve is None
                or actual_transaction_cost <= maximum_transaction_cost_reserve
            )
            and (maximum_cash_outflow is None or reserved_cash_outflow <= maximum_cash_outflow)
        ):
            best = candidate
            low = middle + 1
        else:
            high = middle - 1
    return best


def _interval_values(value: DecimalInterval) -> tuple[Decimal, Decimal]:
    return Decimal(value.lower), Decimal(value.upper)


def _gate_recheck(
    case: Stage5MarketExecutionCase,
    quote: _Quote,
    rules: ApprovedStage5MarketExecutionRules,
) -> Stage5GateRecheck:
    stage4 = case.stage4_complete_result
    historical_gate3 = stage4.unified_gate_view.gate_3.outcome
    if historical_gate3 is None:
        historical_gate3 = GateOutcome.BLOCKED
    valuation: Stage4ValuationSet = case.stage4_case.valuation_set
    if (
        valuation.base_business_equity_value is None
        or valuation.event_finite_life_value is None
        or valuation.scenario_equity_values is None
        or valuation.fully_diluted_shares is None
    ):
        return Stage5GateRecheck(
            historical_gate3_outcome=historical_gate3,
            current_market_pricing_state=None,
            current_gate3_outcome=GateOutcome.ABSTAIN,
            current_gate4_outcome=None,
            net_base_remaining_return=None,
            net_downside_return=None,
            downside_loss=None,
            reward_to_downside=None,
            reason_codes=("EXECUTABLE_GATE_VALUATION_INPUT_MISSING",),
        )
    shares = Decimal(valuation.fully_diluted_shares)
    if shares <= 0:
        return Stage5GateRecheck(
            historical_gate3_outcome=historical_gate3,
            current_market_pricing_state=None,
            current_gate3_outcome=GateOutcome.BLOCKED,
            current_gate4_outcome=None,
            net_base_remaining_return=None,
            net_downside_return=None,
            downside_loss=None,
            reward_to_downside=None,
            reason_codes=("EXECUTABLE_GATE_SHARE_BASIS_INVALID",),
        )
    market_cap = quote.fill_price * shares
    base_business_lower, base_business_upper = _interval_values(
        valuation.base_business_equity_value
    )
    event_lower, event_upper = _interval_values(valuation.event_finite_life_value)
    implied_lower = market_cap - base_business_upper
    implied_upper = market_cap - base_business_lower
    if implied_lower >= event_upper:
        pricing = MarketPricingState.FULLY_REFLECTED
    elif implied_upper < event_lower:
        pricing = MarketPricingState.NOT_FULLY_REFLECTED
    else:
        pricing = MarketPricingState.INDETERMINATE
    expectation = stage4.public_expectation_class
    current_gate3: GateOutcome
    if historical_gate3 is not GateOutcome.PASS:
        current_gate3 = historical_gate3
        gate3_reason = "HISTORICAL_GATE3_NOT_PASS"
    elif pricing is MarketPricingState.FULLY_REFLECTED:
        current_gate3 = GateOutcome.REJECT
        gate3_reason = "CURRENT_EXECUTABLE_MARKET_FULLY_REFLECTED"
    elif (
        pricing is MarketPricingState.INDETERMINATE
        or expectation is None
        or (expectation.value == "unknown")
    ):
        current_gate3 = GateOutcome.ABSTAIN
        gate3_reason = "CURRENT_EXECUTABLE_MARKET_REFLECTION_INDETERMINATE"
    elif expectation.value == "fully_priced":
        current_gate3 = GateOutcome.REJECT
        gate3_reason = "FROZEN_PUBLIC_EXPECTATION_FULLY_PRICED"
    else:
        current_gate3 = GateOutcome.PASS
        gate3_reason = "CURRENT_EXECUTABLE_GATE3_PASS"
    if current_gate3 is not GateOutcome.PASS:
        return Stage5GateRecheck(
            historical_gate3_outcome=historical_gate3,
            current_market_pricing_state=pricing,
            current_gate3_outcome=current_gate3,
            current_gate4_outcome=None,
            net_base_remaining_return=None,
            net_downside_return=None,
            downside_loss=None,
            reward_to_downside=None,
            reason_codes=(gate3_reason, "EXECUTABLE_GATE4_NOT_EVALUATED"),
        )
    values = valuation.scenario_equity_values
    base_value = Decimal(values.base.lower)
    downside_value = Decimal(values.downside.lower)
    upside_value = Decimal(values.upside.lower)
    total_cost = Decimal(quote.costs.total)
    friction = total_cost / quote.gross
    net_base = base_value / market_cap - Decimal(1) - friction
    net_downside = downside_value / market_cap - Decimal(1) - friction
    downside_loss = abs(min(Decimal(0), net_downside))
    if downside_loss == 0:
        return Stage5GateRecheck(
            historical_gate3_outcome=historical_gate3,
            current_market_pricing_state=pricing,
            current_gate3_outcome=current_gate3,
            current_gate4_outcome=GateOutcome.ABSTAIN,
            net_base_remaining_return=_canonical_decimal(net_base),
            net_downside_return=_canonical_decimal(net_downside),
            downside_loss="0",
            reward_to_downside=None,
            reason_codes=(gate3_reason, "EXECUTABLE_GATE4_DOWNSIDE_LOSS_ZERO"),
        )
    reward = net_base / downside_loss
    if (
        net_base < rules.minimum_net_base_remaining_return
        or reward < rules.minimum_reward_to_downside
    ):
        upside_return = upside_value / market_cap - Decimal(1) - friction
        gate4_reason = (
            "EXECUTABLE_GATE4_ONLY_UPSIDE_REACHES_THRESHOLD"
            if upside_return >= rules.minimum_net_base_remaining_return
            else "EXECUTABLE_GATE4_RETURN_OR_REWARD_BELOW_THRESHOLD"
        )
        gate4 = GateOutcome.REJECT
    else:
        gate4_reason = "EXECUTABLE_GATE4_PASS"
        gate4 = GateOutcome.PASS
    return Stage5GateRecheck(
        historical_gate3_outcome=historical_gate3,
        current_market_pricing_state=pricing,
        current_gate3_outcome=current_gate3,
        current_gate4_outcome=gate4,
        net_base_remaining_return=_canonical_decimal(net_base),
        net_downside_return=_canonical_decimal(net_downside),
        downside_loss=_canonical_decimal(downside_loss),
        reward_to_downside=_canonical_decimal(reward),
        reason_codes=(gate3_reason, gate4_reason),
    )


def _result(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
    *,
    status: Stage5ExecutionStatus,
    reason_codes: tuple[str, ...],
    eligible_from: datetime,
    attempts: tuple[Stage5ExecutionAttempt, ...] = (),
    order_intent: SyntheticOrderIntent | None = None,
    fill: SyntheticFill | None = None,
    events: tuple[SyntheticExecutionEvent, ...] = (),
    cancelled_quantity: int = 0,
) -> Stage5MarketExecutionResult:
    value = Stage5MarketExecutionResult(
        schema_version=STAGE5B_SCHEMA_VERSION,
        case_id=case.case_id,
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        input_hash=_hash(canonical_sha256(case)),
        stage4_replay_hash=case.stage4_replay_hash,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
        execution_eligible_from=eligible_from,
        proposal_reference_price_hash=case.proposal_reference_price.identity.declared_content_hash,
        attempts=attempts,
        order_intent=order_intent,
        fill=fill,
        events=tuple(
            sorted(
                events,
                key=lambda item: (
                    item.event_time,
                    item.event_type_priority,
                    item.stable_event_id,
                ),
            )
        ),
        cancelled_quantity=cancelled_quantity,
        replay_hash=_hash("0" * 64),
    )
    return replace(value, replay_hash=_hash(stage5_market_execution_replay_sha256(case, value)))


def _attempt(
    *,
    day: int,
    session: TradingSession,
    status: Stage5ExecutionStatus,
    reasons: tuple[str, ...],
    observation: MarketObservation | None = None,
    market_rule: MarketRuleSet | None = None,
    cost: CostSchedule | None = None,
    impact: ImpactCurve | None = None,
    capacity: int | None = None,
    quantity: int | None = None,
    gate: Stage5GateRecheck | None = None,
) -> Stage5ExecutionAttempt:
    return Stage5ExecutionAttempt(
        attempt_day=day,
        local_trade_date=session.local_trade_date,
        session_id=session.session_id,
        observation_id=observation.observation_id if observation is not None else None,
        status=status,
        reason_codes=reasons,
        market_rule_hash=(
            market_rule.identity.declared_content_hash if market_rule is not None else None
        ),
        cost_schedule_hash=cost.identity.declared_content_hash if cost is not None else None,
        impact_curve_hash=impact.identity.declared_content_hash if impact is not None else None,
        capacity_quantity=capacity,
        candidate_quantity=quantity,
        gate_recheck=gate,
    )


def _observation_failure(
    observation: MarketObservation,
    session: TradingSession,
    state: SecuritySessionState,
    rule: MarketRuleSet,
    side: TradeSide,
    eligible_from: datetime,
) -> str | None:
    if session.session_kind not in rule.allowed_session_kinds:
        return "SESSION_KIND_NOT_ALLOWED_BY_HISTORICAL_RULE"
    if "LIMIT" not in rule.order_types:
        return "SYNTHETIC_LIMIT_ORDER_NOT_ALLOWED_BY_HISTORICAL_RULE"
    if not (
        session.opens_at <= observation.window_start < observation.window_end <= session.closes_at
    ):
        return "OBSERVATION_OUTSIDE_TRADING_SESSION"
    if observation.data_quality is MarketDataQuality.DAILY:
        if eligible_from > session.opens_at:
            return "DAILY_DATA_REQUIRES_ELIGIBILITY_BEFORE_OPEN"
        if observation.volume <= 0 or Decimal(observation.turnover) <= 0:
            return "DAILY_VWAP_REQUIRES_POSITIVE_VOLUME_AND_TURNOVER"
        if Decimal(observation.benchmark_price) != (
            Decimal(observation.turnover) / Decimal(observation.volume)
        ):
            return "DAILY_BENCHMARK_MUST_EQUAL_TURNOVER_DIVIDED_BY_VOLUME"
    elif observation.window_start < eligible_from:
        return "INTRADAY_WINDOW_PRECEDES_EXECUTION_ELIGIBILITY"
    if not state.listed_and_eligible:
        return "SECURITY_NOT_ELIGIBLE"
    if state.suspended:
        return "SECURITY_SUSPENDED"
    if side is TradeSide.BUY and state.one_price_limit_up:
        return "ONE_PRICE_LIMIT_UP_BUY"
    if side is TradeSide.SELL and state.one_price_limit_down:
        return "ONE_PRICE_LIMIT_DOWN_SELL"
    if not state.verified_opposing_liquidity:
        return "NO_VERIFIED_OPPOSING_LIQUIDITY"
    if not state.quote_legal_and_provable:
        return "ILLEGAL_OR_UNPROVABLE_QUOTE"
    if observation.volume <= 0:
        return "ZERO_VOLUME"
    benchmark = Decimal(observation.benchmark_price)
    if benchmark < Decimal(rule.lower_price_limit) or benchmark > Decimal(rule.upper_price_limit):
        return "BENCHMARK_OUTSIDE_EFFECTIVE_PRICE_LIMIT"
    return None


def _evaluate_stage5_market_execution(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
    constraint: Stage5SubmissionReductionConstraint | None,
) -> Stage5MarketExecutionResult:
    """Evaluate historical rules and create at most one deterministic synthetic fill."""

    if not isinstance(case, Stage5MarketExecutionCase):
        raise TypeError("case must be Stage5MarketExecutionCase")
    if not isinstance(rules, ApprovedStage5MarketExecutionRules):
        raise TypeError("rules must be ApprovedStage5MarketExecutionRules")
    eligible_from = max(
        case.decision_at,
        case.strategy_processing_completed_at,
        case.synthetic_approval_fixture.approved_at,
    )
    failure = _precheck_failure(case)
    if failure is None and constraint is not None:
        if not isinstance(constraint, Stage5SubmissionReductionConstraint):
            raise TypeError("constraint must be Stage5SubmissionReductionConstraint")
        failure = _submission_constraint_failure(case, constraint)
    if failure is not None:
        return _result(
            case,
            rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=(failure,),
            eligible_from=eligible_from,
        )
    side = _side(case.action_intent)
    sessions = tuple(
        item
        for item in case.trading_calendar.sessions
        if item.closes_at > eligible_from
        and (
            case.timing_precision is TimingPrecision.EXACT
            or (
                item.local_trade_date > case.decision_local_trade_date
                and item.opens_at >= eligible_from
            )
        )
    )
    trade_dates = tuple(dict.fromkeys(item.local_trade_date for item in sessions))
    if case.action_intent in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD):
        trade_dates = trade_dates[: rules.entry_attempt_days]
    if not trade_dates:
        return _result(
            case,
            rules,
            status=Stage5ExecutionStatus.NON_EXECUTABLE,
            reason_codes=("NO_ELIGIBLE_TRADING_SESSION",),
            eligible_from=eligible_from,
        )
    states = {item.session_id: item for item in case.security_session_states}
    observations_by_session: dict[str, tuple[MarketObservation, ...]] = {}
    for session in sessions:
        observations_by_session[session.session_id] = tuple(
            item
            for item in case.market_observation_set.observations
            if item.session_id == session.session_id
        )
    attempts: list[Stage5ExecutionAttempt] = []
    saw_abstain = False
    last_status = Stage5ExecutionStatus.NON_EXECUTABLE
    last_reasons: tuple[str, ...] = ("NO_EXECUTABLE_WINDOW",)
    for day, trade_date in enumerate(trade_dates, start=1):
        stop_this_day = False
        day_sessions = tuple(item for item in sessions if item.local_trade_date == trade_date)
        for session in day_sessions:
            if stop_this_day:
                break
            session_rule, session_rule_failure = _select_market_rule(
                case,
                max(session.opens_at, eligible_from),
            )
            if session_rule_failure is not None or session_rule is None:
                attempts.append(
                    _attempt(
                        day=day,
                        session=session,
                        status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
                        reasons=(session_rule_failure or "MARKET_RULE_UNKNOWN",),
                    )
                )
                return _result(
                    case,
                    rules,
                    status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
                    reason_codes=(session_rule_failure or "MARKET_RULE_UNKNOWN",),
                    eligible_from=eligible_from,
                    attempts=tuple(attempts),
                )
            state = states.get(session.session_id)
            if state is None:
                saw_abstain = True
                last_status = Stage5ExecutionStatus.ABSTAIN
                last_reasons = ("SECURITY_SESSION_STATE_MISSING",)
                attempts.append(
                    _attempt(
                        day=day,
                        session=session,
                        status=last_status,
                        reasons=last_reasons,
                    )
                )
                continue
            observations = observations_by_session[session.session_id]
            if not observations:
                saw_abstain = True
                last_status = Stage5ExecutionStatus.ABSTAIN
                last_reasons = ("MARKET_OBSERVATION_MISSING",)
                attempts.append(
                    _attempt(
                        day=day,
                        session=session,
                        status=last_status,
                        reasons=last_reasons,
                    )
                )
                continue
            for observation in observations:
                if observation.window_end > case.synthetic_approval_fixture.expires_at:
                    last_status = Stage5ExecutionStatus.CANCELLED
                    last_reasons = ("SYNTHETIC_APPROVAL_EXPIRED",)
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            status=last_status,
                            reasons=last_reasons,
                        )
                    )
                    stop_this_day = True
                    break
                market_rule, market_failure = _select_market_rule(case, observation.window_end)
                if market_failure is not None or market_rule is None:
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
                            reasons=(market_failure or "MARKET_RULE_UNKNOWN",),
                        )
                    )
                    return _result(
                        case,
                        rules,
                        status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
                        reason_codes=(market_failure or "MARKET_RULE_UNKNOWN",),
                        eligible_from=eligible_from,
                        attempts=tuple(attempts),
                    )
                observation_failure = _observation_failure(
                    observation,
                    session,
                    state,
                    market_rule,
                    side,
                    eligible_from,
                )
                if observation_failure is not None:
                    last_status = Stage5ExecutionStatus.NON_EXECUTABLE
                    last_reasons = (observation_failure,)
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            status=last_status,
                            reasons=last_reasons,
                        )
                    )
                    continue
                lot_size = (
                    market_rule.buy_lot_size
                    if side is TradeSide.BUY
                    else (1 if market_rule.allow_odd_lot_sell else market_rule.sell_lot_size)
                )
                capacity = (
                    int(Decimal(observation.volume) * rules.maximum_participation_rate) // lot_size
                ) * lot_size
                approved_quantity = (
                    case.synthetic_approval_fixture.approved_quantity // lot_size
                ) * lot_size
                candidate_quantity = min(capacity, approved_quantity)
                if constraint is not None:
                    candidate_quantity = min(candidate_quantity, constraint.maximum_quantity)
                if candidate_quantity < lot_size:
                    last_status = Stage5ExecutionStatus.NON_EXECUTABLE
                    last_reasons = ("MINIMUM_LOT_EXCEEDS_CAP",)
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            status=last_status,
                            reasons=last_reasons,
                            capacity=capacity,
                            quantity=0,
                        )
                    )
                    continue
                cost = _select_cost(case, side, observation.window_end)
                impact = _select_impact(
                    case,
                    side,
                    observation.data_quality,
                    observation.window_end,
                )
                if cost is None or impact is None:
                    saw_abstain = True
                    last_status = Stage5ExecutionStatus.ABSTAIN
                    last_reasons = (
                        "HISTORICAL_COST_SCHEDULE_MISSING"
                        if cost is None
                        else "HISTORICAL_IMPACT_CURVE_MISSING",
                    )
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            cost=cost,
                            impact=impact,
                            status=last_status,
                            reasons=last_reasons,
                            capacity=capacity,
                            quantity=candidate_quantity,
                        )
                    )
                    stop_this_day = True
                    break
                requested_participation = Decimal(candidate_quantity) / Decimal(observation.volume)
                if _interpolate_impact(impact, requested_participation) is None:
                    saw_abstain = True
                    last_status = Stage5ExecutionStatus.ABSTAIN
                    last_reasons = ("IMPACT_CURVE_EXTRAPOLATION_FORBIDDEN",)
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            cost=cost,
                            impact=impact,
                            status=last_status,
                            reasons=last_reasons,
                            capacity=capacity,
                            quantity=candidate_quantity,
                        )
                    )
                    stop_this_day = True
                    break
                quote = _affordable_quote(
                    candidate_quantity,
                    lot_size,
                    min(
                        Decimal(case.synthetic_approval_fixture.approved_notional_cap),
                        (
                            Decimal(constraint.maximum_gross_notional)
                            if constraint is not None
                            and constraint.maximum_gross_notional is not None
                            else Decimal(case.synthetic_approval_fixture.approved_notional_cap)
                        ),
                    ),
                    observation,
                    market_rule,
                    impact,
                    cost,
                    side,
                    (
                        Decimal(constraint.maximum_cash_outflow)
                        if constraint is not None and constraint.maximum_cash_outflow is not None
                        else None
                    ),
                    (
                        Decimal(constraint.maximum_transaction_cost_reserve)
                        if constraint is not None
                        and constraint.maximum_transaction_cost_reserve is not None
                        else None
                    ),
                )
                if quote is None:
                    last_status = Stage5ExecutionStatus.NON_EXECUTABLE
                    last_reasons = ("MINIMUM_LOT_OR_ADVERSE_PRICE_EXCEEDS_CAP",)
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            cost=cost,
                            impact=impact,
                            status=last_status,
                            reasons=last_reasons,
                            capacity=capacity,
                            quantity=0,
                        )
                    )
                    continue
                gate = _gate_recheck(case, quote, rules)
                if side is TradeSide.BUY and (
                    gate.current_gate3_outcome is not GateOutcome.PASS
                    or gate.current_gate4_outcome is not GateOutcome.PASS
                ):
                    last_status = Stage5ExecutionStatus.GATE_REJECTED_AT_EXECUTABLE_PRICE
                    last_reasons = gate.reason_codes
                    attempts.append(
                        _attempt(
                            day=day,
                            session=session,
                            observation=observation,
                            market_rule=market_rule,
                            cost=cost,
                            impact=impact,
                            status=last_status,
                            reasons=last_reasons,
                            capacity=capacity,
                            quantity=quote.quantity,
                            gate=gate,
                        )
                    )
                    if GateOutcome.ABSTAIN in (
                        gate.current_gate3_outcome,
                        gate.current_gate4_outcome,
                    ):
                        saw_abstain = True
                    stop_this_day = True
                    break
                identity_material = {
                    "case_id": case.case_id,
                    "session_id": session.session_id,
                    "observation_id": observation.observation_id,
                    "quantity": quote.quantity,
                    "fill_price": _canonical_decimal(quote.fill_price),
                }
                identity_hash = canonical_sha256(identity_material)
                order_id = f"synthetic_order_{identity_hash[:24]}"
                fill_id = f"synthetic_fill_{identity_hash[:24]}"
                order = SyntheticOrderIntent(
                    order_intent_id=order_id,
                    case_id=case.case_id,
                    security_id=case.security_id,
                    account_fixture_id=case.account_fixture_id,
                    side=side,
                    quantity=quote.quantity,
                    limit_price=_canonical_decimal(quote.fill_price),
                    time_in_force=rules.order_time_in_force,
                    submitted_at=observation.window_end,
                    market_rule_hash=market_rule.identity.declared_content_hash,
                    cost_schedule_hash=cost.identity.declared_content_hash,
                    impact_curve_hash=impact.identity.declared_content_hash,
                )
                total_cost = Decimal(quote.costs.total)
                cash_effect = (
                    -(quote.gross + total_cost)
                    if side is TradeSide.BUY
                    else quote.gross - total_cost
                )
                fill = SyntheticFill(
                    fill_id=fill_id,
                    order_intent_id=order_id,
                    security_id=case.security_id,
                    side=side,
                    quantity=quote.quantity,
                    benchmark_vwap=observation.benchmark_price,
                    adverse_slippage_rate=_canonical_decimal(quote.slippage),
                    fill_price=_canonical_decimal(quote.fill_price),
                    gross_notional=_canonical_decimal(quote.gross),
                    costs=quote.costs,
                    cash_effect=_canonical_decimal(cash_effect),
                    filled_at=observation.window_end,
                    observation_id=observation.observation_id,
                )
                effective_approved = (
                    constraint.effective_approved_quantity
                    if constraint is not None
                    else case.synthetic_approval_fixture.approved_quantity
                )
                approved_remainder = effective_approved - quote.quantity
                if constraint is not None:
                    # The constrained quantity is the submitted DAY intent and is
                    # filled deterministically in this slice.  Approval above that
                    # ceiling was never submitted, so it is not a cancelled order.
                    cancelled = 0
                    status = Stage5ExecutionStatus.FILLED
                    fill_reason = (
                        "STAGE5C_APPROVED_REMAINDER_NOT_SUBMITTED"
                        if approved_remainder > 0
                        else "STAGE5C_CONSTRAINED_FIRST_EXECUTABLE_WINDOW_FILLED"
                    )
                else:
                    cancelled = approved_remainder
                    status = (
                        Stage5ExecutionStatus.PARTIALLY_FILLED
                        if cancelled > 0
                        else Stage5ExecutionStatus.FILLED
                    )
                    fill_reason = (
                        "SYNTHETIC_PARTIAL_FILL_WITH_DAY_REMAINDER_CANCELLED"
                        if cancelled > 0
                        else "SYNTHETIC_FIRST_EXECUTABLE_WINDOW_FILLED"
                    )
                attempts.append(
                    _attempt(
                        day=day,
                        session=session,
                        observation=observation,
                        market_rule=market_rule,
                        cost=cost,
                        impact=impact,
                        status=status,
                        reasons=(fill_reason,),
                        capacity=capacity,
                        quantity=quote.quantity,
                        gate=gate,
                    )
                )
                events = [
                    SyntheticExecutionEvent(
                        event_time=observation.window_end,
                        event_type_priority=10,
                        stable_event_id=f"event_submit_{identity_hash[:20]}",
                        event_type=SyntheticEventType.SIMULATED_SUBMITTED,
                        quantity=quote.quantity,
                    ),
                    SyntheticExecutionEvent(
                        event_time=observation.window_end,
                        event_type_priority=20,
                        stable_event_id=f"event_fill_{identity_hash[:20]}",
                        event_type=SyntheticEventType.SYNTHETIC_FILL,
                        quantity=quote.quantity,
                    ),
                ]
                if cancelled > 0 and constraint is None:
                    events.append(
                        SyntheticExecutionEvent(
                            event_time=session.closes_at,
                            event_type_priority=30,
                            stable_event_id=f"event_cancel_{identity_hash[:20]}",
                            event_type=SyntheticEventType.CANCELLED,
                            quantity=cancelled,
                        )
                    )
                return _result(
                    case,
                    rules,
                    status=status,
                    reason_codes=(fill_reason,),
                    eligible_from=eligible_from,
                    attempts=tuple(attempts),
                    order_intent=order,
                    fill=fill,
                    events=tuple(events),
                    cancelled_quantity=cancelled,
                )
    if (
        case.action_intent in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD)
        and len(trade_dates) == rules.entry_attempt_days
        and not saw_abstain
    ):
        terminal_reasons = last_reasons
        if constraint is not None:
            terminal_reasons = tuple(
                dict.fromkeys(reason for attempt in attempts for reason in attempt.reason_codes)
            )
        return _result(
            case,
            rules,
            status=Stage5ExecutionStatus.ENTRY_EXPIRED,
            reason_codes=("ENTRY_UNFILLED_AFTER_DAY_THREE", *terminal_reasons),
            eligible_from=eligible_from,
            attempts=tuple(attempts),
        )
    final_status = Stage5ExecutionStatus.ABSTAIN if saw_abstain else last_status
    final_reasons = last_reasons
    if constraint is not None:
        final_reasons = tuple(
            dict.fromkeys(reason for attempt in attempts for reason in attempt.reason_codes)
        )
    return _result(
        case,
        rules,
        status=final_status,
        reason_codes=final_reasons,
        eligible_from=eligible_from,
        attempts=tuple(attempts),
    )


def evaluate_stage5_market_execution(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
) -> Stage5MarketExecutionResult:
    """Run the exact standalone Stage 5B v0.1 synthetic market slice."""

    return _evaluate_stage5_market_execution(case, rules, None)


@with_stage5_decimal_context
def plan_stage5_market_candidate(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
    constraint: Stage5SubmissionReductionConstraint | None = None,
) -> Stage5MarketCandidate:
    """Plan the first executable market window for the supplied ceilings.

    Without a constraint this is the unchanged standalone Stage 5B preview.  A
    Stage 5C caller may pass a content-addressed provisional constraint whose
    candidate binding is still empty.  The planner applies only its reduction
    ceilings while it scans the normal chronological window stream; it never
    uses an unconstrained fill to choose the constrained candidate.
    """

    if constraint is not None and not isinstance(constraint, Stage5SubmissionReductionConstraint):
        raise TypeError("constraint must be Stage5SubmissionReductionConstraint or None")
    preview = _evaluate_stage5_market_execution(case, rules, constraint)
    selected_attempt = next(
        (
            item
            for item in preview.attempts
            if preview.fill is not None and item.observation_id == preview.fill.observation_id
        ),
        None,
    )
    selected_observation = (
        next(
            (
                item
                for item in case.market_observation_set.observations
                if selected_attempt is not None
                and item.observation_id == selected_attempt.observation_id
            ),
            None,
        )
        if selected_attempt is not None
        else None
    )
    candidate_session_id = selected_attempt.session_id if selected_attempt is not None else None
    candidate_observation_id = (
        selected_attempt.observation_id if selected_attempt is not None else None
    )
    candidate_at = selected_observation.window_end if selected_observation is not None else None
    candidate_market_rule_hash = (
        selected_attempt.market_rule_hash if selected_attempt is not None else None
    )
    candidate_cost_schedule_hash = (
        selected_attempt.cost_schedule_hash if selected_attempt is not None else None
    )
    candidate_impact_curve_hash = (
        selected_attempt.impact_curve_hash if selected_attempt is not None else None
    )
    candidate_hash = _hash(
        stage5_market_candidate_sha256(
            case,
            preview,
            candidate_session_id=candidate_session_id,
            candidate_observation_id=candidate_observation_id,
            candidate_at=candidate_at,
            candidate_market_rule_hash=candidate_market_rule_hash,
            candidate_cost_schedule_hash=candidate_cost_schedule_hash,
            candidate_impact_curve_hash=candidate_impact_curve_hash,
        )
    )
    return Stage5MarketCandidate(
        schema_version="0.2.0",
        case_input_hash=_hash(canonical_sha256(case)),
        market_execution_preview=preview,
        candidate_session_id=candidate_session_id,
        candidate_observation_id=candidate_observation_id,
        candidate_at=candidate_at,
        candidate_market_rule_hash=candidate_market_rule_hash,
        candidate_cost_schedule_hash=candidate_cost_schedule_hash,
        candidate_impact_curve_hash=candidate_impact_curve_hash,
        candidate_hash=candidate_hash,
    )


def bind_stage5_submission_constraint_candidate(
    constraint: Stage5SubmissionReductionConstraint,
    candidate: Stage5MarketCandidate,
) -> Stage5SubmissionReductionConstraint:
    """Bind a provisional reduction constraint to its planned final candidate."""

    if not isinstance(constraint, Stage5SubmissionReductionConstraint):
        raise TypeError("constraint must be Stage5SubmissionReductionConstraint")
    if not isinstance(candidate, Stage5MarketCandidate):
        raise TypeError("candidate must be Stage5MarketCandidate")
    candidate_at = candidate.candidate_at
    identity = replace(
        constraint.identity,
        as_of=candidate_at if candidate_at is not None else constraint.as_of,
        declared_content_hash=_hash("0" * 64),
    )
    return bind_stage5_artifact(
        replace(
            constraint,
            identity=identity,
            as_of=candidate_at if candidate_at is not None else constraint.as_of,
            candidate_hash=candidate.candidate_hash,
            candidate_session_id=candidate.candidate_session_id,
            candidate_observation_id=candidate.candidate_observation_id,
            candidate_at=candidate_at,
            candidate_market_rule_hash=candidate.candidate_market_rule_hash,
            candidate_cost_schedule_hash=candidate.candidate_cost_schedule_hash,
            candidate_impact_curve_hash=candidate.candidate_impact_curve_hash,
        )
    )


def _constraint_binds_candidate(
    constraint: Stage5SubmissionReductionConstraint,
    candidate: Stage5MarketCandidate,
) -> bool:
    if (
        constraint.candidate_hash != candidate.candidate_hash
        or constraint.candidate_session_id != candidate.candidate_session_id
        or constraint.candidate_observation_id != candidate.candidate_observation_id
        or constraint.candidate_at != candidate.candidate_at
        or constraint.candidate_market_rule_hash != candidate.candidate_market_rule_hash
        or constraint.candidate_cost_schedule_hash != candidate.candidate_cost_schedule_hash
        or constraint.candidate_impact_curve_hash != candidate.candidate_impact_curve_hash
    ):
        return False
    return candidate.candidate_at is None or constraint.as_of == candidate.candidate_at


@with_stage5_decimal_context
def evaluate_stage5_market_execution_constrained(
    case: Stage5MarketExecutionCase,
    rules: ApprovedStage5MarketExecutionRules,
    constraint: Stage5SubmissionReductionConstraint,
) -> Stage5ConstrainedMarketExecutionProjection:
    """Run Stage 5B with an exact, reduction-only Stage 5C constraint.

    The outer projection binds the constraint to the otherwise unchanged 5B
    case/result replay.  It remains a synthetic research-validation artifact.
    """

    if not isinstance(constraint, Stage5SubmissionReductionConstraint):
        raise TypeError("constraint must be Stage5SubmissionReductionConstraint")
    candidate = plan_stage5_market_candidate(case, rules, constraint)
    eligible_from = max(
        case.decision_at,
        case.strategy_processing_completed_at,
        case.synthetic_approval_fixture.approved_at,
    )
    constraint_failure = _submission_constraint_failure(case, constraint)
    if constraint_failure is not None:
        result = _result(
            case,
            rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=(constraint_failure,),
            eligible_from=eligible_from,
        )
    elif not _constraint_binds_candidate(constraint, candidate):
        result = _result(
            case,
            rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("SUBMISSION_REDUCTION_CANDIDATE_MISMATCH",),
            eligible_from=eligible_from,
        )
    elif constraint.maximum_quantity == 0:
        result = _result(
            case,
            rules,
            status=Stage5ExecutionStatus.SYNTHETIC_REJECTED,
            reason_codes=("STAGE5C_ZERO_SUBMITTABLE_QUANTITY",),
            eligible_from=eligible_from,
            attempts=candidate.market_execution_preview.attempts,
        )
    else:
        result = candidate.market_execution_preview
    constraint_hash = _hash(canonical_sha256(constraint))
    submitted_quantity = result.order_intent.quantity if result.order_intent is not None else 0
    filled_quantity = result.fill.quantity if result.fill is not None else 0
    return Stage5ConstrainedMarketExecutionProjection(
        schema_version="0.2.0",
        market_candidate=candidate,
        constraint_hash=constraint_hash,
        market_execution_result=result,
        effective_approved_quantity=constraint.effective_approved_quantity,
        unsubmitted_quantity=constraint.effective_approved_quantity - submitted_quantity,
        unfilled_cancelled_quantity=submitted_quantity - filled_quantity,
        replay_hash=_hash(
            stage5_constrained_market_execution_replay_sha256(case, candidate, constraint, result)
        ),
    )
