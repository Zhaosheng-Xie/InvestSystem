"""Typed contracts for the owner-approved Stage 5C synthetic slice.

The objects in this module are anonymous, immutable and content-addressed.
They carry no broker/account authority and do not read KB or market state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.models import CanonicalModel, HashDigest

from .stage4_expectation_valuation_exit import VersionedArtifactIdentity
from .stage5_market_execution import Stage5ActionIntent

STAGE5C_CONTRACT_SCHEMA_VERSION = "0.1.0"
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def _id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty text")
    return value


def _decimal(field_name: str, value: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be an exact decimal string")
    parsed = Decimal(value)
    if non_negative and parsed < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return parsed


def _utc(field_name: str, value: datetime) -> datetime:
    return normalize_utc(value, field_name=field_name)


def _identity(value: VersionedArtifactIdentity) -> None:
    if not isinstance(value, VersionedArtifactIdentity):
        raise TypeError("identity must be VersionedArtifactIdentity")


def _hashes(field_name: str, values: tuple[HashDigest, ...]) -> tuple[HashDigest, ...]:
    values = tuple(values)
    if any(not isinstance(value, HashDigest) for value in values):
        raise TypeError(f"{field_name} must contain HashDigest values")
    return values


def _texts(
    field_name: str, values: tuple[str, ...], *, allow_empty: bool = False
) -> tuple[str, ...]:
    values = tuple(values)
    if not allow_empty and not values:
        raise ValueError(f"{field_name} must not be empty")
    for value in values:
        _text(field_name, value)
    return values


class MarketRegime(StrEnum):
    NORMAL = "NORMAL"
    DEFENSIVE = "DEFENSIVE"
    CRISIS = "CRISIS"


class RiskClusterType(StrEnum):
    COMPANY = "company"
    CUSTOMER = "customer"
    PRODUCT_PRICE = "product_price"
    POLICY_CATALYST = "policy_catalyst"
    COMMON_LIQUIDITY = "common_liquidity"


class PortfolioApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RecoveryApprovalDecision(StrEnum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class SettlementMomentKind(StrEnum):
    SECURITY_SETTLEMENT = "SECURITY_SETTLEMENT"
    SECURITY_SELLABLE = "SECURITY_SELLABLE"
    BUY_CASH_PAYABLE = "BUY_CASH_PAYABLE"
    SELL_PROCEEDS_RECEIVABLE = "SELL_PROCEEDS_RECEIVABLE"
    SELL_CASH_SETTLEMENT = "SELL_CASH_SETTLEMENT"
    SELL_CASH_AVAILABLE = "SELL_CASH_AVAILABLE"


@dataclass(frozen=True, slots=True)
class SyntheticRecoveryRecord(CanonicalModel):
    """Content-addressed proof for a synthetic STOPPED-state recovery.

    This record carries references only.  It does not grant real account,
    position, order or owner authority, and it is valid only in the exact
    Stage 5 synthetic research-validation scope.
    """

    identity: VersionedArtifactIdentity
    strategy_id: str
    account_fixture_id: str
    prior_stopped_ledger_event_id: str
    prior_stopped_ledger_event_hash: HashDigest
    prior_stopped_ledger_head_hash: HashDigest
    recovery_ledger_event_id: str
    recovery_ledger_event_hash: HashDigest
    account_ledger_head_hash: HashDigest
    attribution_ref: str
    attribution_hash: HashDigest
    rule_check_ref: str
    rule_check_hash: HashDigest
    owner_approval_ref: str
    owner_approval_hash: HashDigest
    owner_approval_decision: RecoveryApprovalDecision
    prior_stopped_at: datetime
    owner_approval_at: datetime
    effective_at: datetime
    approval_scope: str = "stage5_synthetic_execution_validation"
    run_mode: str = "research"
    synthetic: bool = True
    append_only: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        for name in (
            "strategy_id",
            "account_fixture_id",
            "prior_stopped_ledger_event_id",
            "recovery_ledger_event_id",
            "attribution_ref",
            "rule_check_ref",
            "owner_approval_ref",
        ):
            _id(name, getattr(self, name))
        for name in (
            "prior_stopped_ledger_event_hash",
            "prior_stopped_ledger_head_hash",
            "recovery_ledger_event_hash",
            "account_ledger_head_hash",
            "attribution_hash",
            "rule_check_hash",
            "owner_approval_hash",
        ):
            value = getattr(self, name)
            if not isinstance(value, HashDigest):
                raise TypeError(f"{name} must be HashDigest")
            if value.value == "0" * 64:
                raise ValueError(f"{name} must not use the zero-hash sentinel")
        if not isinstance(self.owner_approval_decision, RecoveryApprovalDecision):
            raise TypeError("owner_approval_decision must be RecoveryApprovalDecision")
        object.__setattr__(
            self,
            "prior_stopped_at",
            _utc("prior_stopped_at", self.prior_stopped_at),
        )
        object.__setattr__(
            self,
            "owner_approval_at",
            _utc("owner_approval_at", self.owner_approval_at),
        )
        object.__setattr__(self, "effective_at", _utc("effective_at", self.effective_at))
        if self.identity.as_of != self.effective_at:
            raise ValueError("recovery identity as_of must equal effective_at")
        if self.identity.knowledge_cutoff > self.effective_at:
            raise ValueError("recovery knowledge_cutoff must not postdate effective_at")
        if not self.prior_stopped_at < self.owner_approval_at <= self.effective_at:
            raise ValueError("recovery times must satisfy stopped < owner approval <= effective")
        if self.prior_stopped_ledger_event_id == self.recovery_ledger_event_id:
            raise ValueError("stopped and recovery ledger events must be distinct")
        if (
            self.prior_stopped_ledger_event_hash == self.recovery_ledger_event_hash
            or self.prior_stopped_ledger_head_hash == self.account_ledger_head_hash
        ):
            raise ValueError("append-only recovery must advance event and journal identities")
        if (
            self.approval_scope != "stage5_synthetic_execution_validation"
            or self.run_mode != "research"
            or not self.synthetic
            or not self.append_only
        ):
            raise ValueError("recovery record exceeds the synthetic research boundary")


@dataclass(frozen=True, slots=True)
class SyntheticLotSnapshot(CanonicalModel):
    lot_id: str
    security_id: str
    acquired_at: datetime
    quantity: int
    sellable_quantity: int
    full_cost: str
    governing_market_rule_hash: HashDigest

    def __post_init__(self) -> None:
        _id("lot_id", self.lot_id)
        _id("security_id", self.security_id)
        object.__setattr__(self, "acquired_at", _utc("acquired_at", self.acquired_at))
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
        _decimal("full_cost", self.full_cost, non_negative=True)
        if not isinstance(self.governing_market_rule_hash, HashDigest):
            raise TypeError("governing_market_rule_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class SyntheticPositionSnapshot(CanonicalModel):
    security_id: str
    company_id: str
    market_value: str
    lots: tuple[SyntheticLotSnapshot, ...]

    def __post_init__(self) -> None:
        _id("security_id", self.security_id)
        _id("company_id", self.company_id)
        _decimal("market_value", self.market_value, non_negative=True)
        lots = tuple(self.lots)
        if not lots or any(not isinstance(lot, SyntheticLotSnapshot) for lot in lots):
            raise ValueError("positions require one or more typed lots")
        if any(lot.security_id != self.security_id for lot in lots):
            raise ValueError("position lots must have the same security_id")
        if len({lot.lot_id for lot in lots}) != len(lots):
            raise ValueError("lot_id values must be unique within a position")
        object.__setattr__(self, "lots", lots)

    @property
    def quantity(self) -> int:
        return sum(lot.quantity for lot in self.lots)

    @property
    def sellable_quantity(self) -> int:
        return sum(lot.sellable_quantity for lot in self.lots)


@dataclass(frozen=True, slots=True)
class RiskClusterExposure(CanonicalModel):
    cluster_type: RiskClusterType
    cluster_id: str
    market_value: str
    planned_loss: str

    def __post_init__(self) -> None:
        if not isinstance(self.cluster_type, RiskClusterType):
            raise TypeError("cluster_type must be RiskClusterType")
        _id("cluster_id", self.cluster_id)
        _decimal("market_value", self.market_value, non_negative=True)
        _decimal("planned_loss", self.planned_loss, non_negative=True)


@dataclass(frozen=True, slots=True)
class SyntheticAccountSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    strategy_id: str
    account_fixture_id: str
    base_currency: str
    settled_cash: str
    reserved_cash: str
    available_cash: str
    unsettled_cash_receivable: str
    unsettled_cash_payable: str
    positions: tuple[SyntheticPositionSnapshot, ...]
    net_asset_value: str
    adjusted_high_water_mark: str
    declared_drawdown: str
    risk_cluster_exposures: tuple[RiskClusterExposure, ...]
    aggregate_open_planned_loss: str
    prior_stopped: bool
    ledger_head_hash: HashDigest | None = None
    synthetic_recovery_record: SyntheticRecoveryRecord | None = None
    # Compatibility sentinels only.  Arbitrary hash + bool attestations are no
    # longer a valid recovery path and non-empty legacy values are rejected.
    synthetic_recovery_record_hash: HashDigest | None = None
    synthetic_recovery_approved: bool = False
    synthetic: bool = True
    no_broker_binding: bool = True
    leverage: bool = False
    shorting: bool = False
    negative_cash: bool = False

    def __post_init__(self) -> None:
        _identity(self.identity)
        _id("strategy_id", self.strategy_id)
        _id("account_fixture_id", self.account_fixture_id)
        if self.base_currency != "CNY":
            raise ValueError("base_currency must be CNY")
        settled = _decimal("settled_cash", self.settled_cash, non_negative=True)
        reserved = _decimal("reserved_cash", self.reserved_cash, non_negative=True)
        available = _decimal("available_cash", self.available_cash, non_negative=True)
        receivable = _decimal(
            "unsettled_cash_receivable", self.unsettled_cash_receivable, non_negative=True
        )
        payable = _decimal("unsettled_cash_payable", self.unsettled_cash_payable, non_negative=True)
        if reserved > settled or available != settled - reserved:
            raise ValueError("available cash must equal settled cash less reserved cash")
        positions = tuple(self.positions)
        if any(not isinstance(item, SyntheticPositionSnapshot) for item in positions):
            raise TypeError("positions must contain SyntheticPositionSnapshot values")
        if len({item.security_id for item in positions}) != len(positions):
            raise ValueError("security positions must be unique")
        object.__setattr__(self, "positions", positions)
        nav = _decimal("net_asset_value", self.net_asset_value, non_negative=True)
        high_water = _decimal(
            "adjusted_high_water_mark", self.adjusted_high_water_mark, non_negative=True
        )
        drawdown = _decimal("declared_drawdown", self.declared_drawdown, non_negative=True)
        if nav <= 0 or high_water <= 0:
            raise ValueError("NAV and adjusted high-water mark must be positive")
        if nav > high_water:
            raise ValueError("adjusted high-water mark must not be below current NAV")
        expected_drawdown = max(Decimal(0), Decimal(1) - nav / high_water)
        if drawdown != expected_drawdown:
            raise ValueError("declared_drawdown must equal the approved formula")
        position_value = sum(Decimal(item.market_value) for item in positions)
        if nav != settled + receivable - payable + position_value:
            raise ValueError("synthetic NAV must reconcile to cash, net receivables and positions")
        if position_value / nav > Decimal(1):
            raise ValueError("gross and net long weights must not exceed one")
        exposures = tuple(self.risk_cluster_exposures)
        if any(not isinstance(item, RiskClusterExposure) for item in exposures):
            raise TypeError("risk_cluster_exposures must contain typed values")
        identities = {(item.cluster_type, item.cluster_id) for item in exposures}
        if len(identities) != len(exposures):
            raise ValueError("risk-cluster exposure identities must be unique")
        object.__setattr__(self, "risk_cluster_exposures", exposures)
        _decimal(
            "aggregate_open_planned_loss",
            self.aggregate_open_planned_loss,
            non_negative=True,
        )
        if self.ledger_head_hash is not None and not isinstance(self.ledger_head_hash, HashDigest):
            raise TypeError("ledger_head_hash must be HashDigest or None")
        if self.synthetic_recovery_record is not None and not isinstance(
            self.synthetic_recovery_record, SyntheticRecoveryRecord
        ):
            raise TypeError("synthetic_recovery_record must be SyntheticRecoveryRecord or None")
        if self.synthetic_recovery_record_hash is not None or self.synthetic_recovery_approved:
            raise ValueError(
                "legacy recovery hash/boolean attestations are forbidden; use a typed record"
            )
        if not self.prior_stopped and self.synthetic_recovery_record is not None:
            raise ValueError("recovery evidence is valid only after a prior stopped state")
        if (
            not self.synthetic
            or not self.no_broker_binding
            or self.leverage
            or self.shorting
            or self.negative_cash
        ):
            raise ValueError("account snapshot exceeds the approved anonymous long-only boundary")

    def position(self, security_id: str) -> SyntheticPositionSnapshot | None:
        return next((item for item in self.positions if item.security_id == security_id), None)


@dataclass(frozen=True, slots=True)
class RiskClusterAssignment(CanonicalModel):
    cluster_type: RiskClusterType
    cluster_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.cluster_type, RiskClusterType):
            raise TypeError("cluster_type must be RiskClusterType")
        _id("cluster_id", self.cluster_id)


@dataclass(frozen=True, slots=True)
class RiskClusterSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    strategy_id: str
    security_id: str
    company_id: str
    assignments: tuple[RiskClusterAssignment, ...]
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        for name in ("strategy_id", "security_id", "company_id"):
            _id(name, getattr(self, name))
        assignments = tuple(self.assignments)
        if any(not isinstance(item, RiskClusterAssignment) for item in assignments):
            raise TypeError("assignments must contain RiskClusterAssignment values")
        types = {item.cluster_type for item in assignments}
        if not set(RiskClusterType).issubset(types):
            raise ValueError("all five required risk-cluster types must be assigned")
        identities = tuple((item.cluster_type, item.cluster_id) for item in assignments)
        if len(set(identities)) != len(identities):
            raise ValueError("risk-cluster (type, id) assignments must be unique")
        object.__setattr__(self, "assignments", assignments)
        if not self.synthetic:
            raise ValueError("risk-cluster snapshot must be synthetic")


@dataclass(frozen=True, slots=True)
class MarketRegimeSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    regime: MarketRegime | None
    synthetic_fixture: bool
    real_classifier_approved: bool = False

    def __post_init__(self) -> None:
        _identity(self.identity)
        if self.regime is not None and not isinstance(self.regime, MarketRegime):
            raise TypeError("regime must be MarketRegime or None")
        if not self.synthetic_fixture or self.real_classifier_approved:
            raise ValueError("Stage 5C permits only an explicit synthetic regime fixture")


@dataclass(frozen=True, slots=True)
class StressScenarioInput(CanonicalModel):
    identity: VersionedArtifactIdentity
    scenario_return: str | None
    basis_id: str
    comparable_to_account_nav: bool
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        _id("basis_id", self.basis_id)
        if self.scenario_return is not None:
            _decimal("scenario_return", self.scenario_return)
        if not self.synthetic:
            raise ValueError("stress scenario must be synthetic")


@dataclass(frozen=True, slots=True)
class PortfolioSizingInputs(CanonicalModel):
    identity: VersionedArtifactIdentity
    proposal_reference_price_hash: HashDigest
    liquidity_capacity_value: str
    worst_applicable_cost_reserve: str
    values_are_comparable_cny: bool
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        if not isinstance(self.proposal_reference_price_hash, HashDigest):
            raise TypeError("proposal_reference_price_hash must be HashDigest")
        _decimal("liquidity_capacity_value", self.liquidity_capacity_value, non_negative=True)
        _decimal(
            "worst_applicable_cost_reserve",
            self.worst_applicable_cost_reserve,
            non_negative=True,
        )
        if not self.values_are_comparable_cny or not self.synthetic:
            raise ValueError("sizing inputs must be comparable synthetic CNY values")


@dataclass(frozen=True, slots=True)
class SettlementMoment(CanonicalModel):
    kind: SettlementMomentKind
    local_trade_date: str
    effective_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SettlementMomentKind):
            raise TypeError("kind must be SettlementMomentKind")
        try:
            datetime.strptime(self.local_trade_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("local_trade_date must use YYYY-MM-DD") from error
        object.__setattr__(self, "effective_at", _utc("effective_at", self.effective_at))


@dataclass(frozen=True, slots=True)
class SettlementAvailabilityTerms(CanonicalModel):
    identity: VersionedArtifactIdentity
    venue: str
    board: str
    security_type: str
    risk_label: str
    trade_local_date: str
    market_rule_hash: HashDigest
    moments: tuple[SettlementMoment, ...]
    source_document_ids: tuple[str, ...]
    source_byte_hashes: tuple[HashDigest, ...]
    same_day_sellable: bool
    special_exception_id: str | None
    retrospective_backfill: bool = False
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        for name in ("venue", "board", "security_type", "risk_label"):
            _id(name, getattr(self, name))
        try:
            datetime.strptime(self.trade_local_date, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError("trade_local_date must use YYYY-MM-DD") from error
        if not isinstance(self.market_rule_hash, HashDigest):
            raise TypeError("market_rule_hash must be HashDigest")
        moments = tuple(self.moments)
        if any(not isinstance(item, SettlementMoment) for item in moments):
            raise TypeError("moments must contain SettlementMoment values")
        kinds = tuple(item.kind for item in moments)
        if set(kinds) != set(SettlementMomentKind) or len(kinds) != len(SettlementMomentKind):
            raise ValueError("all settlement and availability moments are required exactly once")
        object.__setattr__(self, "moments", moments)
        object.__setattr__(
            self, "source_document_ids", _texts("source_document_ids", self.source_document_ids)
        )
        object.__setattr__(
            self, "source_byte_hashes", _hashes("source_byte_hashes", self.source_byte_hashes)
        )
        if self.special_exception_id is not None:
            _id("special_exception_id", self.special_exception_id)
        if self.retrospective_backfill or not self.synthetic:
            raise ValueError("settlement terms must be PIT-safe synthetic fixtures")

    def moment(self, kind: SettlementMomentKind) -> SettlementMoment:
        return next(item for item in self.moments if item.kind is kind)


@dataclass(frozen=True, slots=True)
class InitialLedgerSnapshot(CanonicalModel):
    identity: VersionedArtifactIdentity
    strategy_id: str
    account_fixture_id: str
    account_snapshot_hash: HashDigest
    expected_head_hash: HashDigest
    head_observed_at: datetime
    no_intervening_events_attested: bool
    prior_event_hashes: tuple[HashDigest, ...]
    empty_stage5c_opening_projection: bool = True
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        _id("strategy_id", self.strategy_id)
        _id("account_fixture_id", self.account_fixture_id)
        for name in ("account_snapshot_hash", "expected_head_hash"):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        object.__setattr__(
            self,
            "head_observed_at",
            _utc("head_observed_at", self.head_observed_at),
        )
        object.__setattr__(
            self,
            "prior_event_hashes",
            _hashes("prior_event_hashes", self.prior_event_hashes),
        )
        if (
            self.identity.as_of > self.head_observed_at
            or self.identity.knowledge_cutoff > self.head_observed_at
        ):
            raise ValueError("initial ledger identity must be PIT-safe at head_observed_at")
        if (
            self.prior_event_hashes
            or not self.no_intervening_events_attested
            or not self.empty_stage5c_opening_projection
            or not self.synthetic
        ):
            raise ValueError("Stage 5C accepts only an explicit empty prior journal")


@dataclass(frozen=True, slots=True)
class SyntheticCorporateActionSet(CanonicalModel):
    identity: VersionedArtifactIdentity
    security_id: str
    applicable_action_ids: tuple[str, ...]
    explicitly_empty_for_stage5c: bool
    synthetic: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        _id("security_id", self.security_id)
        actions = tuple(self.applicable_action_ids)
        for action_id in actions:
            _id("applicable_action_ids", action_id)
        object.__setattr__(self, "applicable_action_ids", actions)
        if actions or not self.explicitly_empty_for_stage5c or not self.synthetic:
            raise ValueError("Stage 5C requires an explicit empty corporate-action set")


@dataclass(frozen=True, slots=True)
class RiskConstraintValue(CanonicalModel):
    constraint_id: str
    value_cny: str

    def __post_init__(self) -> None:
        _id("constraint_id", self.constraint_id)
        _decimal("value_cny", self.value_cny, non_negative=True)


@dataclass(frozen=True, slots=True)
class PortfolioTarget(CanonicalModel):
    identity: VersionedArtifactIdentity
    case_id: str
    security_id: str
    account_fixture_id: str
    action_intent: Stage5ActionIntent
    proposal_reference_price_hash: HashDigest
    account_snapshot_hash: HashDigest
    risk_cluster_hash: HashDigest
    market_regime_hash: HashDigest
    stress_scenario_hash: HashDigest
    sizing_inputs_hash: HashDigest
    selected_rounding_market_rule_hash: HashDigest | None
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    stress_loss_rate: str
    planned_account_loss_rate: str
    constraint_values: tuple[RiskConstraintValue, ...]
    target_value: str
    target_quantity: int
    rounded_target_value: str
    binding_constraint_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _identity(self.identity)
        for name in ("case_id", "security_id", "account_fixture_id"):
            _id(name, getattr(self, name))
        if not isinstance(self.action_intent, Stage5ActionIntent):
            raise TypeError("action_intent must be Stage5ActionIntent")
        for name in (
            "proposal_reference_price_hash",
            "account_snapshot_hash",
            "risk_cluster_hash",
            "market_regime_hash",
            "stress_scenario_hash",
            "sizing_inputs_hash",
            "rule_bundle_hash",
            "rule_approval_record_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        if self.selected_rounding_market_rule_hash is not None and not isinstance(
            self.selected_rounding_market_rule_hash,
            HashDigest,
        ):
            raise TypeError("selected_rounding_market_rule_hash must be HashDigest or None")
        _id("rule_approval_id", self.rule_approval_id)
        _decimal("stress_loss_rate", self.stress_loss_rate, non_negative=True)
        _decimal("planned_account_loss_rate", self.planned_account_loss_rate, non_negative=True)
        values = tuple(self.constraint_values)
        if not values or any(not isinstance(item, RiskConstraintValue) for item in values):
            raise ValueError("constraint_values must contain typed values")
        object.__setattr__(self, "constraint_values", values)
        _decimal("target_value", self.target_value, non_negative=True)
        if (
            isinstance(self.target_quantity, bool)
            or not isinstance(self.target_quantity, int)
            or self.target_quantity < 0
        ):
            raise ValueError("target_quantity must be a non-negative integer")
        _decimal("rounded_target_value", self.rounded_target_value, non_negative=True)
        object.__setattr__(
            self,
            "binding_constraint_ids",
            _texts("binding_constraint_ids", self.binding_constraint_ids),
        )
        object.__setattr__(self, "reason_codes", _texts("reason_codes", self.reason_codes))


@dataclass(frozen=True, slots=True)
class SyntheticPortfolioApproval(CanonicalModel):
    identity: VersionedArtifactIdentity
    case_id: str
    security_id: str
    account_fixture_id: str
    action_intent: Stage5ActionIntent
    decision: PortfolioApprovalDecision
    target_hash: HashDigest
    portfolio_risk_evaluation_hash: HashDigest
    market_approval_hash: HashDigest
    approved_at: datetime
    expires_at: datetime
    approved_quantity: int
    approved_notional_cap: str
    approved_planned_loss_cap: str
    reason_codes: tuple[str, ...]
    synthetic: bool = True
    may_only_reduce: bool = True

    def __post_init__(self) -> None:
        _identity(self.identity)
        for name in ("case_id", "security_id", "account_fixture_id"):
            _id(name, getattr(self, name))
        if not isinstance(self.action_intent, Stage5ActionIntent):
            raise TypeError("action_intent must be Stage5ActionIntent")
        if not isinstance(self.decision, PortfolioApprovalDecision):
            raise TypeError("decision must be PortfolioApprovalDecision")
        for name in (
            "target_hash",
            "portfolio_risk_evaluation_hash",
            "market_approval_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        object.__setattr__(self, "approved_at", _utc("approved_at", self.approved_at))
        object.__setattr__(self, "expires_at", _utc("expires_at", self.expires_at))
        if self.approved_at >= self.expires_at:
            raise ValueError("portfolio approval must expire after approval")
        if self.identity.as_of != self.approved_at:
            raise ValueError("portfolio approval identity as_of must equal approved_at")
        if self.identity.knowledge_cutoff > self.approved_at:
            raise ValueError("portfolio approval knowledge_cutoff must not postdate approved_at")
        if (
            isinstance(self.approved_quantity, bool)
            or not isinstance(self.approved_quantity, int)
            or self.approved_quantity < 0
        ):
            raise ValueError("approved_quantity must be non-negative")
        notional = _decimal("approved_notional_cap", self.approved_notional_cap, non_negative=True)
        planned_loss = _decimal(
            "approved_planned_loss_cap", self.approved_planned_loss_cap, non_negative=True
        )
        if self.decision is PortfolioApprovalDecision.APPROVED and (
            self.approved_quantity == 0 or notional == 0
        ):
            raise ValueError("approved portfolio decisions require positive quantity and notional")
        if self.decision is PortfolioApprovalDecision.REJECTED and (
            self.approved_quantity != 0 or notional != 0 or planned_loss != 0
        ):
            raise ValueError("rejected portfolio decisions require zero caps")
        object.__setattr__(self, "reason_codes", _texts("reason_codes", self.reason_codes))
        if not self.synthetic or not self.may_only_reduce:
            raise ValueError("portfolio approval must be synthetic and reduction-only")


type Stage5CArtifact = (
    SyntheticRecoveryRecord
    | SyntheticAccountSnapshot
    | RiskClusterSnapshot
    | MarketRegimeSnapshot
    | StressScenarioInput
    | PortfolioSizingInputs
    | SettlementAvailabilityTerms
    | InitialLedgerSnapshot
    | SyntheticCorporateActionSet
    | PortfolioTarget
    | SyntheticPortfolioApproval
)


def stage5c_artifact_content_sha256(value: Stage5CArtifact) -> str:
    """Hash a Stage 5C artifact without its self-referential declared hash."""

    projected = value.to_json_value()
    identity = projected.get("identity")
    if not isinstance(identity, dict):
        raise TypeError("artifact identity projection must be an object")
    del identity["declared_content_hash"]
    return canonical_sha256(projected)


def bind_stage5c_artifact[ArtifactT: Stage5CArtifact](value: ArtifactT) -> ArtifactT:
    """Return a Stage 5C artifact with its deterministic content hash bound."""

    identity = replace(
        value.identity,
        declared_content_hash=HashDigest(
            algorithm="sha256",
            value=stage5c_artifact_content_sha256(value),
        ),
    )
    return replace(value, identity=identity)


def stage5c_initial_ledger_head_sha256(account_snapshot_hash: HashDigest) -> str:
    """Hash the explicit empty-journal head used by the Stage 5C vertical slice."""

    return canonical_sha256(
        {
            "schema_version": STAGE5C_CONTRACT_SCHEMA_VERSION,
            "account_snapshot_hash": account_snapshot_hash,
            "prior_event_hashes": (),
        }
    )
