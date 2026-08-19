"""Bounded complete replay for the preregistered first Stage 5D BUY case.

The evaluator deliberately supports one anonymous synthetic historical case.
It recomputes Stage 5C in the same call, rematerializes the V2 opening at the
registered beginning, values the two inclusive journal prefixes, and produces
the approved 3 x 6 P&L matrix.  It performs no I/O and grants no execution or
persistence authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleStatus,
)
from invest_system.models import CanonicalModel, HashDigest, RunMode

from .stage5_decimal import STAGE5_DECIMAL_CONTEXT_ID, with_stage5_decimal_context
from .stage5_governance import (
    STAGE5_5A_RULE_APPROVAL_ID,
    STAGE5_5A_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5A_RULE_BUNDLE_SHA256,
    STAGE5_STRATEGY_ID,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from .stage5_market_execution import Stage5ActionIntent, TradeSide
from .stage5_portfolio_ledger_engine import Stage5PortfolioLedgerCase
from .stage5d_governance import (
    STAGE5_5D_APPROVAL_SCOPE,
    STAGE5_5D_RULE_APPROVAL_ID,
    STAGE5_5D_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5D_RULE_BUNDLE_ID,
    STAGE5_5D_RULE_BUNDLE_SHA256,
    STAGE5_5D_RULE_BUNDLE_VERSION,
)
from .stage5d_ledger_v2 import (
    Stage5DV2Account,
    Stage5DV2DerivedState,
    Stage5DV2Event,
    Stage5DV2EventType,
    Stage5DV2ReplayResult,
    Stage5DV2ReplayStatus,
    bind_stage5d_v2_event,
    replay_stage5d_v2_slice,
)
from .stage5d_stage5c_adapter import (
    Stage5DSourceDrivenSliceResult,
    Stage5DSourceDrivenSliceStatus,
    evaluate_stage5d_source_driven_ledger_slice,
)

STAGE5D_BOUNDED_REPLAY_SCHEMA_VERSION = "0.1.0"
STAGE5D_FIRST_REPLAY_PREREGISTRATION_SHA256 = (
    "f7042c49f72b693d1c9ae5892b1d454be07cf6ad0851c499b47b2fead55492bc"
)
STAGE5D_FIRST_REPLAY_STAGE5C_CASE_SHA256 = (
    "06a9eaac57fec706b7bda7566494256cd0df045e1bdab2d826a1a85066a1ee62"
)
STAGE5D_FIRST_REPLAY_STAGE5C_RESULT_SHA256 = (
    "daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59"
)
STAGE5D_FIRST_REPLAY_SOURCE_SLICE_SHA256 = (
    "7872330b5e3a93047e305ada37b07dc5aaa946ffbef40b6ca8c0e5dbc2cddc3f"
)
STAGE5D_EVENT_SEMANTIC_MAP_SHA256 = (
    "5c7eee2e0f53a0c53a37fdce39d5096458a9d010ff081b1da1e328fce72ddcb3"
)
STAGE5D_PNL_FORMULA_MAP_SHA256 = "00b0576d2a0e040fa33d143a50235ab86db26ecdfdf4897b31b7cf017a2ffd88"

_BEGINNING_AT = datetime.fromisoformat("2025-01-20T02:10:00+00:00")
_ENDING_AT = datetime.fromisoformat("2025-01-21T07:01:00+00:00")
_MARK_OBSERVED_AT = datetime.fromisoformat("2025-01-21T07:00:00+00:00")
_ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)
_EVENT_INVENTORY = (
    Stage5DV2EventType.OPENING_BALANCE,
    Stage5DV2EventType.BUY_TRADE,
    Stage5DV2EventType.BUY_CASH_SETTLEMENT,
    Stage5DV2EventType.SECURITY_SETTLEMENT,
    Stage5DV2EventType.SECURITY_SELLABLE,
)


class Stage5DBoundedReplayPurpose(StrEnum):
    RESEARCH_VALIDATION = "RESEARCH_VALIDATION"
    AUDIT_REPLAY = "AUDIT_REPLAY"


class Stage5DBoundedReplayStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    ABSTAIN_INCOMPLETE_PNL = "ABSTAIN_INCOMPLETE_PNL"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


class Stage5DPnlRealization(StrEnum):
    REALIZED = "realized"
    UNREALIZED = "unrealized"
    NON_POSITION_INCOME = "non_position_income"


class Stage5DPnlDriver(StrEnum):
    PRICE = "price"
    SLIPPAGE = "slippage"
    FEE = "fee"
    TAX = "tax"
    CASH_DIVIDEND = "cash_dividend"
    CORPORATE_ACTION_CASH = "corporate_action_cash"


def _hash(value: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(value))


def _text(name: str, value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{name} must be a non-empty string of at most 256 characters")
    return value


def _decimal(name: str, value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{name} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{name} must be a finite decimal") from error
    if not parsed.is_finite() or (positive and parsed <= 0):
        raise ValueError(f"{name} must be {'positive' if positive else 'finite'}")
    return parsed


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@dataclass(frozen=True, slots=True)
class Stage5DBoundedMark(CanonicalModel):
    mark_id: str
    security_id: str
    price: str
    currency: str
    observed_at: datetime
    available_at: datetime
    source_kind: str
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_executable_price: bool = field(default=True, init=False)

    def __post_init__(self) -> None:
        for name in ("mark_id", "security_id", "currency", "source_kind"):
            _text(name, getattr(self, name))
        object.__setattr__(
            self, "price", _decimal_text(_decimal("price", self.price, positive=True))
        )
        observed = normalize_utc(self.observed_at, field_name="observed_at")
        available = normalize_utc(self.available_at, field_name="available_at")
        if observed > available:
            raise ValueError("observed_at must not postdate available_at")
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class Stage5DBoundedReplayCase(CanonicalModel):
    preregistration_hash: HashDigest
    stage5c_case: Stage5PortfolioLedgerCase
    beginning_at: datetime
    ending_at: datetime
    mark_coverage_complete: bool
    ending_mark: Stage5DBoundedMark | None
    corporate_action_ids: tuple[str, ...]
    external_cash_flow_ids: tuple[str, ...]
    purpose: Stage5DBoundedReplayPurpose
    source_complete_replay_hash: HashDigest | None
    code_commit: str
    semantic_config_hash: HashDigest

    def __post_init__(self) -> None:
        if not isinstance(self.preregistration_hash, HashDigest):
            raise TypeError("preregistration_hash must be HashDigest")
        if not isinstance(self.stage5c_case, Stage5PortfolioLedgerCase):
            raise TypeError("stage5c_case must be Stage5PortfolioLedgerCase")
        beginning = normalize_utc(self.beginning_at, field_name="beginning_at")
        ending = normalize_utc(self.ending_at, field_name="ending_at")
        if beginning >= ending:
            raise ValueError("beginning_at must precede ending_at")
        object.__setattr__(self, "beginning_at", beginning)
        object.__setattr__(self, "ending_at", ending)
        if type(self.mark_coverage_complete) is not bool:
            raise TypeError("mark_coverage_complete must be bool")
        if self.ending_mark is not None and not isinstance(self.ending_mark, Stage5DBoundedMark):
            raise TypeError("ending_mark must be Stage5DBoundedMark or None")
        for name in ("corporate_action_ids", "external_cash_flow_ids"):
            values = tuple(getattr(self, name))
            if any(not isinstance(item, str) or not item for item in values):
                raise ValueError(f"{name} must contain non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{name} must be unique")
            object.__setattr__(self, name, values)
        if not isinstance(self.purpose, Stage5DBoundedReplayPurpose):
            raise TypeError("purpose must be Stage5DBoundedReplayPurpose")
        if self.purpose is Stage5DBoundedReplayPurpose.AUDIT_REPLAY:
            if not isinstance(self.source_complete_replay_hash, HashDigest):
                raise ValueError("audit replay requires source_complete_replay_hash")
        elif self.source_complete_replay_hash is not None:
            raise ValueError("research validation cannot carry source_complete_replay_hash")
        _text("code_commit", self.code_commit)
        if not isinstance(self.semantic_config_hash, HashDigest):
            raise TypeError("semantic_config_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage5DBoundedValuation(CanonicalModel):
    as_of: datetime
    security_id: str
    available_cash: str
    trade_cash_receivable: str
    trade_cash_payable: str
    actual_quantity: int
    sellable_quantity: int
    mark_price: str | None
    market_value: str
    nav: str
    journal_head_hash: HashDigest
    valuation_hash: HashDigest


@dataclass(frozen=True, slots=True)
class Stage5DPnlCell(CanonicalModel):
    realization: Stage5DPnlRealization
    driver: Stage5DPnlDriver
    amount: str


@dataclass(frozen=True, slots=True)
class Stage5DPnlContribution(CanonicalModel):
    as_of: datetime
    realization: Stage5DPnlRealization
    driver: Stage5DPnlDriver
    formula_term: str
    source_event_id: str
    source_lot_id: str | None
    signed_amount: str


@dataclass(frozen=True, slots=True)
class Stage5DPnlMatrix(CanonicalModel):
    as_of: datetime
    cells: tuple[Stage5DPnlCell, ...]
    total: str


@dataclass(frozen=True, slots=True)
class Stage5DBoundedPnl(CanonicalModel):
    formula_map_hash: HashDigest
    beginning_matrix: Stage5DPnlMatrix
    ending_matrix: Stage5DPnlMatrix
    period_cells: tuple[Stage5DPnlCell, ...]
    ending_contributions: tuple[Stage5DPnlContribution, ...]
    net_external_cash_inflow: str
    period_total_pnl: str
    pnl_hash: HashDigest


@dataclass(frozen=True, slots=True)
class Stage5DBoundedReplayResult(CanonicalModel):
    schema_version: str
    status: Stage5DBoundedReplayStatus
    reason_codes: tuple[str, ...]
    input_hash: HashDigest
    preregistration_hash: HashDigest
    stage5c_case_hash: HashDigest
    stage5c_result_hash: HashDigest | None
    source_slice_hash: HashDigest | None
    stage5a_rule_bundle_hash: HashDigest
    stage5d_rule_bundle_hash: HashDigest
    stage5d_approval_id: str
    stage5d_approval_record_hash: HashDigest
    event_semantic_map_hash: HashDigest
    pnl_formula_map_hash: HashDigest
    rematerialized_v2_replay: Stage5DV2ReplayResult | None
    beginning_valuation: Stage5DBoundedValuation | None
    ending_valuation: Stage5DBoundedValuation | None
    pnl: Stage5DBoundedPnl | None
    purpose: Stage5DBoundedReplayPurpose
    source_complete_replay_hash: HashDigest | None
    complete_replay_hash: HashDigest
    replay_complete: bool
    valuation_complete: bool
    pnl_complete: bool
    reconciled: bool
    financial_state_changed: bool
    advances_financial_head: bool
    decimal_context_id: str = field(default=STAGE5_DECIMAL_CONTEXT_ID, init=False)
    approval_scope: RuleApprovalScope = field(default=STAGE5_5D_APPROVAL_SCOPE, init=False)
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    source_driven: bool = False
    same_call_stage5c_recomputed: bool = False
    audit_only: bool = field(default=False)
    external_state_mutated: bool = field(default=False, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_real_accounts: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)
    connects_broker: bool = field(default=False, init=False)
    reads_kb_internal_state: bool = field(default=False, init=False)
    writes_kb: bool = field(default=False, init=False)


def stage5d_bounded_complete_replay_sha256(
    case: Stage5DBoundedReplayCase,
    result: Stage5DBoundedReplayResult,
) -> str:
    projected = result.to_json_value()
    del projected["complete_replay_hash"]
    return canonical_sha256({"case": case, "result": projected})


def _bind_valuation(value: Stage5DBoundedValuation) -> Stage5DBoundedValuation:
    projected = value.to_json_value()
    del projected["valuation_hash"]
    return replace(value, valuation_hash=_hash(projected))


def _bind_pnl(value: Stage5DBoundedPnl) -> Stage5DBoundedPnl:
    projected = value.to_json_value()
    del projected["pnl_hash"]
    return replace(value, pnl_hash=_hash(projected))


def _result(
    case: Stage5DBoundedReplayCase,
    *,
    status: Stage5DBoundedReplayStatus,
    reason_codes: tuple[str, ...],
    source: Stage5DSourceDrivenSliceResult | None = None,
    replay: Stage5DV2ReplayResult | None = None,
    beginning: Stage5DBoundedValuation | None = None,
    ending: Stage5DBoundedValuation | None = None,
    pnl: Stage5DBoundedPnl | None = None,
) -> Stage5DBoundedReplayResult:
    complete = status is Stage5DBoundedReplayStatus.COMPLETE
    ledger_reconciled = replay is not None and replay.status is Stage5DV2ReplayStatus.RECONCILED
    financial_state_changed = (
        ledger_reconciled and replay is not None and len(replay.accepted_events) > 1
    )
    value = Stage5DBoundedReplayResult(
        schema_version=STAGE5D_BOUNDED_REPLAY_SCHEMA_VERSION,
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        input_hash=_hash(case),
        preregistration_hash=case.preregistration_hash,
        stage5c_case_hash=_hash(case.stage5c_case),
        stage5c_result_hash=source.stage5c_result_hash if source is not None else None,
        source_slice_hash=_hash(source) if source is not None else None,
        stage5a_rule_bundle_hash=HashDigest(algorithm="sha256", value=STAGE5_5A_RULE_BUNDLE_SHA256),
        stage5d_rule_bundle_hash=HashDigest(algorithm="sha256", value=STAGE5_5D_RULE_BUNDLE_SHA256),
        stage5d_approval_id=STAGE5_5D_RULE_APPROVAL_ID,
        stage5d_approval_record_hash=HashDigest(
            algorithm="sha256", value=STAGE5_5D_RULE_APPROVAL_RECORD_SHA256
        ),
        event_semantic_map_hash=HashDigest(
            algorithm="sha256", value=STAGE5D_EVENT_SEMANTIC_MAP_SHA256
        ),
        pnl_formula_map_hash=HashDigest(algorithm="sha256", value=STAGE5D_PNL_FORMULA_MAP_SHA256),
        rematerialized_v2_replay=replay,
        beginning_valuation=beginning,
        ending_valuation=ending,
        pnl=pnl,
        purpose=case.purpose,
        source_complete_replay_hash=case.source_complete_replay_hash,
        complete_replay_hash=_ZERO_HASH,
        replay_complete=complete,
        valuation_complete=complete,
        pnl_complete=complete,
        reconciled=complete,
        financial_state_changed=financial_state_changed,
        advances_financial_head=financial_state_changed,
        source_driven=source is not None,
        same_call_stage5c_recomputed=source is not None,
        audit_only=case.purpose is Stage5DBoundedReplayPurpose.AUDIT_REPLAY,
    )
    return replace(
        value,
        complete_replay_hash=HashDigest(
            algorithm="sha256",
            value=stage5d_bounded_complete_replay_sha256(case, value),
        ),
    )


def _preregistered_input_failure(case: Stage5DBoundedReplayCase) -> str | None:
    raw = case.stage5c_case.market_execution_case
    if case.preregistration_hash.value != STAGE5D_FIRST_REPLAY_PREREGISTRATION_SHA256:
        return "STAGE5D_PREREGISTRATION_IDENTITY_MISMATCH"
    if canonical_sha256(case.stage5c_case) != STAGE5D_FIRST_REPLAY_STAGE5C_CASE_SHA256:
        return "STAGE5D_PREREGISTERED_STAGE5C_CASE_MISMATCH"
    if case.beginning_at != _BEGINNING_AT or case.ending_at != _ENDING_AT:
        return "STAGE5D_PREREGISTERED_HORIZON_MISMATCH"
    if (
        raw.action_intent is not Stage5ActionIntent.ENTER
        or raw.security_id != "600000.SH"
        or raw.account_fixture_id != "anonymous_account_001"
    ):
        return "STAGE5D_ACTION_SECURITY_OR_ACCOUNT_OUTSIDE_BOUNDED_SLICE"
    if case.corporate_action_ids:
        return "STAGE5D_CORPORATE_ACTION_OUTSIDE_BOUNDED_SLICE"
    if case.external_cash_flow_ids:
        return "STAGE5D_EXTERNAL_CASH_FLOW_OUTSIDE_BOUNDED_SLICE"
    if not case.mark_coverage_complete:
        return "STAGE5D_ENDING_MARK_COVERAGE_UNVERIFIABLE"
    mark = case.ending_mark
    if mark is not None and (
        mark.mark_id != "synthetic_mark_600000_20250121_close"
        or mark.security_id != "600000.SH"
        or mark.price != "8"
        or mark.currency != "CNY"
        or mark.observed_at != _MARK_OBSERVED_AT
        or mark.available_at != _ENDING_AT
        or mark.source_kind != "synthetic_preregistered_close_mark"
    ):
        return "STAGE5D_ENDING_MARK_OUTSIDE_PREREGISTERED_EVIDENCE"
    return None


def _require_exact_governance(
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
    capability: ApprovedRuleCapability,
) -> None:
    if not isinstance(market_rules, ApprovedStage5MarketExecutionRules):
        raise TypeError("market_rules must be ApprovedStage5MarketExecutionRules")
    if not isinstance(portfolio_rules, ApprovedStage5PortfolioLedgerRules):
        raise TypeError("portfolio_rules must be ApprovedStage5PortfolioLedgerRules")
    for rules in (market_rules, portfolio_rules):
        if (
            rules.bundle_hash.value != STAGE5_5A_RULE_BUNDLE_SHA256
            or rules.approval_id != STAGE5_5A_RULE_APPROVAL_ID
            or rules.approval_record_hash.value != STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
        ):
            raise ValueError("bounded Stage 5D requires the exact approved Stage 5A rules")
    if not isinstance(capability, ApprovedRuleCapability):
        raise TypeError("stage5d_capability must be ApprovedRuleCapability")
    actual = (
        capability.approval_id,
        capability.strategy_id,
        capability.bundle_id,
        capability.bundle_version,
        capability.bundle_hash.value,
        capability.approval_record_hash.value,
        capability.approval_scope,
        capability.rule_status,
    )
    expected = (
        STAGE5_5D_RULE_APPROVAL_ID,
        STAGE5_STRATEGY_ID,
        STAGE5_5D_RULE_BUNDLE_ID,
        STAGE5_5D_RULE_BUNDLE_VERSION,
        STAGE5_5D_RULE_BUNDLE_SHA256,
        STAGE5_5D_RULE_APPROVAL_RECORD_SHA256,
        STAGE5_5D_APPROVAL_SCOPE,
        RuleStatus.APPROVED,
    )
    if actual != expected:
        raise ValueError("bounded Stage 5D requires the exact approved Stage 5D capability")


def _source_failure(source: Stage5DSourceDrivenSliceResult) -> str | None:
    if (
        source.status is not Stage5DSourceDrivenSliceStatus.BUY_RECONCILED
        or source.v2_replay is None
        or source.v2_replay.status is not Stage5DV2ReplayStatus.RECONCILED
        or canonical_sha256(source.stage5c_result) != STAGE5D_FIRST_REPLAY_STAGE5C_RESULT_SHA256
        or canonical_sha256(source) != STAGE5D_FIRST_REPLAY_SOURCE_SLICE_SHA256
    ):
        return "STAGE5D_PREREGISTERED_SOURCE_RECOMPUTATION_MISMATCH"
    constrained = source.stage5c_result.constrained_market_projection
    if constrained is None or constrained.market_execution_result.fill is None:
        return "STAGE5D_PREREGISTERED_FILL_MISSING"
    fill = constrained.market_execution_result.fill
    if (
        fill.side is not TradeSide.BUY
        or fill.fill_id != "synthetic_fill_b11033004c59d2aaef7256e0"
        or fill.quantity != 200
        or fill.benchmark_vwap != "8"
        or fill.fill_price != "8.04"
        or fill.gross_notional != "1608"
        or fill.costs.total != "5.23"
        or fill.costs.tax != "0"
        or fill.cash_effect != "-1613.23"
    ):
        return "STAGE5D_PREREGISTERED_FILL_ECONOMICS_MISMATCH"
    return None


def _rematerialize_events(
    source: Stage5DSourceDrivenSliceResult,
    beginning_at: datetime,
) -> tuple[Stage5DV2Event, ...]:
    if source.v2_replay is None:
        raise ValueError("source V2 replay is required")
    source_events = source.v2_replay.projected_events
    if tuple(item.event_type for item in source_events) != _EVENT_INVENTORY:
        raise ValueError("source event inventory does not match the preregistration")
    result: list[Stage5DV2Event] = []
    prior: tuple[HashDigest, ...] = ()
    for event in source_events:
        rebound = bind_stage5d_v2_event(
            replace(
                event,
                effective_at=(
                    beginning_at
                    if event.event_type is Stage5DV2EventType.OPENING_BALANCE
                    else event.effective_at
                ),
                prior_event_hashes=prior,
                declared_canonical_hash=_ZERO_HASH,
            )
        )
        result.append(rebound)
        prior += (rebound.declared_canonical_hash,)
    return tuple(result)


def _balance(
    state: Stage5DV2DerivedState,
    account: Stage5DV2Account,
    *,
    unit: str = "CNY",
    security_id: str | None = None,
) -> Decimal:
    return sum(
        (
            Decimal(item.debit_less_credit)
            for item in state.balances
            if item.account is account and item.unit == unit and item.security_id == security_id
        ),
        Decimal(0),
    )


def _valuation(
    state: Stage5DV2DerivedState,
    *,
    as_of: datetime,
    security_id: str,
    mark_price: Decimal | None,
) -> Stage5DBoundedValuation:
    quantity = state.actual_quantity(security_id)
    if quantity > 0 and mark_price is None:
        raise ValueError("a positive position requires an eligible mark")
    market_value = Decimal(quantity) * (mark_price or Decimal(0))
    available = Decimal(state.available_cash)
    receivable = _balance(state, Stage5DV2Account.CASH_RECEIVABLE)
    payable = Decimal(state.cash_payable)
    settled_unavailable = _balance(state, Stage5DV2Account.CASH_SETTLED_UNAVAILABLE)
    nav = available + settled_unavailable + receivable - payable + market_value
    return _bind_valuation(
        Stage5DBoundedValuation(
            as_of=as_of,
            security_id=security_id,
            available_cash=_decimal_text(available),
            trade_cash_receivable=_decimal_text(receivable),
            trade_cash_payable=_decimal_text(payable),
            actual_quantity=quantity,
            sellable_quantity=state.sellable_quantity(security_id),
            mark_price=_decimal_text(mark_price) if mark_price is not None else None,
            market_value=_decimal_text(market_value),
            nav=_decimal_text(nav),
            journal_head_hash=state.journal_head_hash,
            valuation_hash=_ZERO_HASH,
        )
    )


def _all_cells(
    values: dict[tuple[Stage5DPnlRealization, Stage5DPnlDriver], Decimal],
) -> tuple[Stage5DPnlCell, ...]:
    return tuple(
        Stage5DPnlCell(
            realization=row,
            driver=driver,
            amount=_decimal_text(values.get((row, driver), Decimal(0))),
        )
        for row in Stage5DPnlRealization
        for driver in Stage5DPnlDriver
    )


def _pnl(
    beginning: Stage5DBoundedValuation,
    ending: Stage5DBoundedValuation,
    ending_state: Stage5DV2DerivedState,
    mark: Stage5DBoundedMark,
    events: tuple[Stage5DV2Event, ...],
) -> Stage5DBoundedPnl:
    buy_event = next(item for item in events if item.event_type is Stage5DV2EventType.BUY_TRADE)
    if len(ending_state.lots) != 1:
        raise ValueError("the bounded P&L slice requires exactly one remaining lot")
    lot = ending_state.lots[0]
    mv = Decimal(ending.market_value)
    principal = Decimal(lot.cost_components.principal)
    slippage = Decimal(lot.cost_components.slippage)
    fee = Decimal(lot.cost_components.fee)
    tax = Decimal(lot.cost_components.tax)
    basis = Decimal(lot.cost_components.basis_adjustment)
    ending_values = {
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.PRICE): mv - principal - basis,
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.SLIPPAGE): -slippage,
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.FEE): -fee,
        (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.TAX): -tax,
    }
    beginning_cells = _all_cells({})
    ending_cells = _all_cells(ending_values)
    period_cells = _all_cells(ending_values)
    contributions = (
        Stage5DPnlContribution(
            as_of=ending.as_of,
            realization=Stage5DPnlRealization.UNREALIZED,
            driver=Stage5DPnlDriver.PRICE,
            formula_term="MV",
            source_event_id=mark.mark_id,
            source_lot_id=lot.lot_id,
            signed_amount=_decimal_text(mv),
        ),
        Stage5DPnlContribution(
            as_of=ending.as_of,
            realization=Stage5DPnlRealization.UNREALIZED,
            driver=Stage5DPnlDriver.PRICE,
            formula_term="RB",
            source_event_id=buy_event.event_id,
            source_lot_id=lot.lot_id,
            signed_amount=_decimal_text(-principal),
        ),
        Stage5DPnlContribution(
            as_of=ending.as_of,
            realization=Stage5DPnlRealization.UNREALIZED,
            driver=Stage5DPnlDriver.SLIPPAGE,
            formula_term="RS",
            source_event_id=buy_event.event_id,
            source_lot_id=lot.lot_id,
            signed_amount=_decimal_text(-slippage),
        ),
        Stage5DPnlContribution(
            as_of=ending.as_of,
            realization=Stage5DPnlRealization.UNREALIZED,
            driver=Stage5DPnlDriver.FEE,
            formula_term="RF",
            source_event_id=buy_event.event_id,
            source_lot_id=lot.lot_id,
            signed_amount=_decimal_text(-fee),
        ),
    )
    period_total = sum((Decimal(item.amount) for item in period_cells), Decimal(0))
    nav_pnl = Decimal(ending.nav) - Decimal(beginning.nav)
    if period_total != nav_pnl:
        raise ValueError("P&L cells do not reconcile to the period NAV identity")
    cell_totals: dict[tuple[Stage5DPnlRealization, Stage5DPnlDriver], Decimal] = {}
    for contribution in contributions:
        key = (contribution.realization, contribution.driver)
        cell_totals[key] = cell_totals.get(key, Decimal(0)) + Decimal(contribution.signed_amount)
    if any(
        cell_totals.get((cell.realization, cell.driver), Decimal(0)) != Decimal(cell.amount)
        for cell in period_cells
    ):
        raise ValueError("P&L contributions do not reconcile to the atomic cells")
    return _bind_pnl(
        Stage5DBoundedPnl(
            formula_map_hash=HashDigest(algorithm="sha256", value=STAGE5D_PNL_FORMULA_MAP_SHA256),
            beginning_matrix=Stage5DPnlMatrix(
                as_of=beginning.as_of,
                cells=beginning_cells,
                total="0",
            ),
            ending_matrix=Stage5DPnlMatrix(
                as_of=ending.as_of,
                cells=ending_cells,
                total=_decimal_text(period_total),
            ),
            period_cells=period_cells,
            ending_contributions=contributions,
            net_external_cash_inflow="0",
            period_total_pnl=_decimal_text(period_total),
            pnl_hash=_ZERO_HASH,
        )
    )


@with_stage5_decimal_context
def evaluate_stage5d_bounded_complete_replay(
    case: Stage5DBoundedReplayCase,
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
    stage5d_capability: ApprovedRuleCapability,
) -> Stage5DBoundedReplayResult:
    """Evaluate the preregistered BUY case without widening Stage 5D scope."""

    if not isinstance(case, Stage5DBoundedReplayCase):
        raise TypeError("case must be Stage5DBoundedReplayCase")
    _require_exact_governance(market_rules, portfolio_rules, stage5d_capability)
    input_failure = _preregistered_input_failure(case)
    if input_failure is not None:
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.PRECHECK_BLOCKED,
            reason_codes=(input_failure,),
        )
    source = evaluate_stage5d_source_driven_ledger_slice(
        case.stage5c_case,
        market_rules,
        portfolio_rules,
        stage5d_capability,
    )
    source_failure = _source_failure(source)
    if source_failure is not None:
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.RECONCILIATION_BLOCKED,
            reason_codes=(source_failure,),
            source=source,
        )
    try:
        events = _rematerialize_events(source, case.beginning_at)
        beginning_replay = replay_stage5d_v2_slice(events, as_of=case.beginning_at)
        ending_replay = replay_stage5d_v2_slice(events, as_of=case.ending_at)
    except (TypeError, ValueError):
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.RECONCILIATION_BLOCKED,
            reason_codes=("STAGE5D_OPENING_REMATERIALIZATION_FAILED",),
            source=source,
        )
    if (
        beginning_replay.status is not Stage5DV2ReplayStatus.RECONCILED
        or ending_replay.status is not Stage5DV2ReplayStatus.RECONCILED
        or beginning_replay.derived_state is None
        or ending_replay.derived_state is None
        or tuple(item.event_type for item in beginning_replay.accepted_events)
        != (Stage5DV2EventType.OPENING_BALANCE,)
        or tuple(item.event_type for item in ending_replay.accepted_events) != _EVENT_INVENTORY
        or ending_replay.future_events
    ):
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.RECONCILIATION_BLOCKED,
            reason_codes=("STAGE5D_BOUNDED_PREFIX_REPLAY_FAILED",),
            source=source,
            replay=ending_replay,
        )
    if case.ending_mark is None:
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.ABSTAIN_INCOMPLETE_PNL,
            reason_codes=("STAGE5D_COMPLETE_COVERAGE_HAS_NO_ELIGIBLE_ENDING_MARK",),
            source=source,
            replay=ending_replay,
        )
    try:
        beginning = _valuation(
            beginning_replay.derived_state,
            as_of=case.beginning_at,
            security_id="600000.SH",
            mark_price=None,
        )
        ending = _valuation(
            ending_replay.derived_state,
            as_of=case.ending_at,
            security_id="600000.SH",
            mark_price=Decimal(case.ending_mark.price),
        )
        pnl = _pnl(beginning, ending, ending_replay.derived_state, case.ending_mark, events)
    except (InvalidOperation, TypeError, ValueError):
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.RECONCILIATION_BLOCKED,
            reason_codes=("STAGE5D_BOUNDED_VALUATION_OR_PNL_DID_NOT_RECONCILE",),
            source=source,
            replay=ending_replay,
        )
    research_case = replace(
        case,
        purpose=Stage5DBoundedReplayPurpose.RESEARCH_VALIDATION,
        source_complete_replay_hash=None,
    )
    research_result = _result(
        research_case,
        status=Stage5DBoundedReplayStatus.COMPLETE,
        reason_codes=("STAGE5D_FIRST_ORDER_CONTRACT_REPLAY_COMPLETE",),
        source=source,
        replay=ending_replay,
        beginning=beginning,
        ending=ending,
        pnl=pnl,
    )
    if case.purpose is Stage5DBoundedReplayPurpose.AUDIT_REPLAY:
        if case.source_complete_replay_hash != research_result.complete_replay_hash:
            return _result(
                case,
                status=Stage5DBoundedReplayStatus.PRECHECK_BLOCKED,
                reason_codes=("STAGE5D_AUDIT_SOURCE_REPLAY_HASH_MISMATCH",),
                source=source,
            )
        return _result(
            case,
            status=Stage5DBoundedReplayStatus.COMPLETE,
            reason_codes=("STAGE5D_FIRST_ORDER_CONTRACT_AUDIT_REPLAY_COMPLETE",),
            source=source,
            replay=ending_replay,
            beginning=beginning,
            ending=ending,
            pnl=pnl,
        )
    return research_result


__all__ = [
    "STAGE5D_BOUNDED_REPLAY_SCHEMA_VERSION",
    "STAGE5D_EVENT_SEMANTIC_MAP_SHA256",
    "STAGE5D_FIRST_REPLAY_PREREGISTRATION_SHA256",
    "STAGE5D_PNL_FORMULA_MAP_SHA256",
    "Stage5DBoundedMark",
    "Stage5DBoundedPnl",
    "Stage5DBoundedReplayCase",
    "Stage5DBoundedReplayPurpose",
    "Stage5DBoundedReplayResult",
    "Stage5DBoundedReplayStatus",
    "Stage5DBoundedValuation",
    "Stage5DPnlCell",
    "Stage5DPnlContribution",
    "Stage5DPnlDriver",
    "Stage5DPnlMatrix",
    "Stage5DPnlRealization",
    "evaluate_stage5d_bounded_complete_replay",
    "stage5d_bounded_complete_replay_sha256",
]
