"""Bounded normal-security BUY-to-full-EXIT lifecycle evaluator.

The evaluator is pure, anonymous synthetic research validation.  It consumes
only the exact materialized input set and preserves the historical Stage 5C,
Ledger V2, bounded BUY, and partial-SELL paths unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import ApprovedRuleCapability, RuleApprovalScope
from invest_system.models import CanonicalModel, HashDigest, RunMode

from .stage5_decimal import STAGE5_DECIMAL_CONTEXT_ID, with_stage5_decimal_context
from .stage5_execution_contracts import SyntheticLotSnapshot
from .stage5_governance import (
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from .stage5_market_execution import TradeSide
from .stage5d_bounded_replay import (
    STAGE5D_PNL_FORMULA_MAP_SHA256,
    Stage5DBoundedReplayCase,
    Stage5DBoundedReplayPurpose,
    Stage5DBoundedReplayStatus,
    Stage5DPnlCell,
    Stage5DPnlContribution,
    Stage5DPnlDriver,
    Stage5DPnlMatrix,
    Stage5DPnlRealization,
    evaluate_stage5d_bounded_complete_replay,
)
from .stage5d_governance import STAGE5_5D_APPROVAL_SCOPE
from .stage5d_ledger_v2 import (
    Stage5DV2Account,
    Stage5DV2CostComponents,
    Stage5DV2DerivedState,
    Stage5DV2Event,
    Stage5DV2EventType,
    Stage5DV2LotEffect,
    Stage5DV2OpeningLotAttribution,
    Stage5DV2ReplayResult,
    Stage5DV2ReplayStatus,
    bind_stage5d_v2_event,
    bind_stage5d_v2_opening_attribution,
    replay_stage5d_v2_slice,
)
from .stage5d_lifecycle_inputs import (
    Stage5DLifecycleMarkObservation,
    Stage5DNormalLifecycleMaterializedInputs,
)
from .stage5d_stage5c_adapter import (
    Stage5DSourceDrivenSliceStatus,
    evaluate_stage5d_source_driven_ledger_slice,
)

STAGE5D_NORMAL_LIFECYCLE_SCHEMA_VERSION = "0.1.0"
STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256 = (
    "60cad84334d110e910be897179bf76409f59c59b3bcd45fd733d29cf67829e30"
)
STAGE5D_NORMAL_LIFECYCLE_PREREGISTRATION_SHA256 = (
    "67f707e5e2f5cdfca4af45a71639ce91df222f7b5149125e654bfe9d1355a72b"
)
STAGE5D_MARK_TO_MARKET_PRIORITY = 105

_ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)


class Stage5DNormalLifecyclePurpose(StrEnum):
    RESEARCH_VALIDATION = "RESEARCH_VALIDATION"
    AUDIT_REPLAY = "AUDIT_REPLAY"


class Stage5DNormalLifecycleStatus(StrEnum):
    COMPLETE = "COMPLETE"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


class Stage5DLifecycleJournalEntryKind(StrEnum):
    FINANCIAL_EVENT = "FINANCIAL_EVENT"
    MARK_TO_MARKET = "MARK_TO_MARKET"


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _without_hash(value: CanonicalModel, field_name: str) -> dict[str, Any]:
    projected = value.to_json_value()
    del projected[field_name]
    return projected


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleJournalEntry(CanonicalModel):
    ordinal: int
    entry_id: str
    kind: Stage5DLifecycleJournalEntryKind
    effective_at: datetime
    priority: int
    prior_entry_hashes: tuple[HashDigest, ...]
    financial_event: Stage5DV2Event | None
    mark: Stage5DLifecycleMarkObservation | None
    entry_hash: HashDigest

    def __post_init__(self) -> None:
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 0:
            raise ValueError("journal ordinal must be non-negative")
        if not isinstance(self.entry_id, str) or not self.entry_id:
            raise ValueError("entry_id must be non-empty")
        if not isinstance(self.kind, Stage5DLifecycleJournalEntryKind):
            raise TypeError("kind must be Stage5DLifecycleJournalEntryKind")
        object.__setattr__(
            self,
            "effective_at",
            normalize_utc(self.effective_at, field_name="effective_at"),
        )
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise TypeError("priority must be integer")
        prior = tuple(self.prior_entry_hashes)
        if any(not isinstance(item, HashDigest) for item in prior):
            raise TypeError("prior_entry_hashes must contain HashDigest values")
        object.__setattr__(self, "prior_entry_hashes", prior)
        if self.kind is Stage5DLifecycleJournalEntryKind.FINANCIAL_EVENT:
            if not isinstance(self.financial_event, Stage5DV2Event) or self.mark is not None:
                raise ValueError("financial journal entry payload differs")
            if (
                self.entry_id != self.financial_event.event_id
                or self.effective_at != self.financial_event.effective_at
                or self.priority != self.financial_event.event_type_priority
            ):
                raise ValueError("financial journal entry identity differs")
        elif not isinstance(self.mark, Stage5DLifecycleMarkObservation) or (
            self.financial_event is not None
            or self.entry_id != self.mark.mark_id
            or self.effective_at != self.mark.valuation_at
            or self.priority != STAGE5D_MARK_TO_MARKET_PRIORITY
        ):
            raise ValueError("mark journal entry payload differs")
        if not isinstance(self.entry_hash, HashDigest) or self.entry_hash not in (
            _ZERO_HASH,
            _hash(_without_hash(self, "entry_hash")),
        ):
            raise ValueError("entry_hash differs")


def _bind_journal_entry(value: Stage5DLifecycleJournalEntry) -> Stage5DLifecycleJournalEntry:
    return replace(value, entry_hash=_hash(_without_hash(value, "entry_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DSessionValuationPoint(CanonicalModel):
    session_index: int
    session_id: str
    valuation_at: datetime
    journal_prefix_hash: HashDigest
    financial_replay_hash: HashDigest
    mark_hash: HashDigest | None
    cash_available: str
    cash_reserved: str
    cash_settled_unavailable: str
    cash_receivable: str
    cash_payable: str
    actual_quantity: int
    sellable_quantity: int
    mark_price: str | None
    security_market_value: str
    nav: str
    cumulative_pnl_hash: HashDigest
    valuation_hash: HashDigest

    def __post_init__(self) -> None:
        if (
            isinstance(self.session_index, bool)
            or not isinstance(self.session_index, int)
            or not 0 <= self.session_index <= 60
        ):
            raise ValueError("session_index must be between zero and 60")
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be non-empty")
        object.__setattr__(
            self,
            "valuation_at",
            normalize_utc(self.valuation_at, field_name="valuation_at"),
        )
        for name in (
            "journal_prefix_hash",
            "financial_replay_hash",
            "cumulative_pnl_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        if self.mark_hash is not None and not isinstance(self.mark_hash, HashDigest):
            raise TypeError("mark_hash must be HashDigest or None")
        for name in (
            "cash_available",
            "cash_reserved",
            "cash_settled_unavailable",
            "cash_receivable",
            "cash_payable",
            "security_market_value",
            "nav",
        ):
            Decimal(getattr(self, name))
        for name in ("actual_quantity", "sellable_quantity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.sellable_quantity > self.actual_quantity:
            raise ValueError("sellable quantity cannot exceed actual quantity")
        if self.actual_quantity > 0:
            if self.mark_hash is None or self.mark_price is None:
                raise ValueError("open position valuation requires a mark")
            Decimal(self.mark_price)
        elif self.mark_hash is not None or self.mark_price is not None:
            raise ValueError("zero position valuation must not select a mark")
        expected_nav = (
            Decimal(self.cash_available)
            + Decimal(self.cash_reserved)
            + Decimal(self.cash_settled_unavailable)
            + Decimal(self.cash_receivable)
            - Decimal(self.cash_payable)
            + Decimal(self.security_market_value)
        )
        if Decimal(self.nav) != expected_nav:
            raise ValueError("valuation NAV identity differs")
        if not isinstance(self.valuation_hash, HashDigest) or self.valuation_hash not in (
            _ZERO_HASH,
            _hash(_without_hash(self, "valuation_hash")),
        ):
            raise ValueError("valuation_hash differs")


def _bind_valuation(value: Stage5DSessionValuationPoint) -> Stage5DSessionValuationPoint:
    return replace(value, valuation_hash=_hash(_without_hash(value, "valuation_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DSessionValuationSeries(CanonicalModel):
    points: tuple[Stage5DSessionValuationPoint, ...]
    daily_return_factors: tuple[str, ...]
    series_hash: HashDigest

    def __post_init__(self) -> None:
        points = tuple(self.points)
        factors = tuple(self.daily_return_factors)
        if len(points) != 61 or tuple(item.session_index for item in points) != tuple(range(61)):
            raise ValueError("valuation series must contain contiguous points 0-60")
        if len(factors) != 60 or any(Decimal(item) <= 0 for item in factors):
            raise ValueError("valuation series must contain 60 positive return factors")
        if tuple(item.valuation_at for item in points) != tuple(
            sorted(item.valuation_at for item in points)
        ):
            raise ValueError("valuation times must be increasing")
        object.__setattr__(self, "points", points)
        object.__setattr__(self, "daily_return_factors", factors)
        expected_factors = tuple(
            Decimal(current.nav) / Decimal(previous.nav)
            for previous, current in zip(points, points[1:], strict=False)
        )
        if tuple(Decimal(item) for item in factors) != expected_factors:
            raise ValueError("daily return factors differ from NAV points")
        if not isinstance(self.series_hash, HashDigest) or self.series_hash not in (
            _ZERO_HASH,
            _hash(_without_hash(self, "series_hash")),
        ):
            raise ValueError("series_hash differs")


def _bind_series(value: Stage5DSessionValuationSeries) -> Stage5DSessionValuationSeries:
    return replace(value, series_hash=_hash(_without_hash(value, "series_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DNormalLifecyclePnl(CanonicalModel):
    formula_map_hash: HashDigest
    lifetime_beginning_matrix: Stage5DPnlMatrix
    exit_beginning_matrix: Stage5DPnlMatrix
    ending_matrix: Stage5DPnlMatrix
    exit_period_cells: tuple[Stage5DPnlCell, ...]
    ending_contributions: tuple[Stage5DPnlContribution, ...]
    lifetime_total_pnl: str
    exit_period_total_pnl: str
    pnl_hash: HashDigest

    def __post_init__(self) -> None:
        if not isinstance(self.formula_map_hash, HashDigest):
            raise TypeError("formula_map_hash must be HashDigest")
        for name in (
            "lifetime_beginning_matrix",
            "exit_beginning_matrix",
            "ending_matrix",
        ):
            if not isinstance(getattr(self, name), Stage5DPnlMatrix):
                raise TypeError(f"{name} must be Stage5DPnlMatrix")
        cells = tuple(self.exit_period_cells)
        contributions = tuple(self.ending_contributions)
        if len(cells) != 18 or any(not isinstance(item, Stage5DPnlCell) for item in cells):
            raise ValueError("exit_period_cells must contain 18 cells")
        if not contributions or any(
            not isinstance(item, Stage5DPnlContribution) for item in contributions
        ):
            raise ValueError("ending_contributions must contain typed contributions")
        object.__setattr__(self, "exit_period_cells", cells)
        object.__setattr__(self, "ending_contributions", contributions)
        matrices = (
            self.lifetime_beginning_matrix,
            self.exit_beginning_matrix,
            self.ending_matrix,
        )
        for matrix in matrices:
            if len(matrix.cells) != 18 or sum(
                (Decimal(item.amount) for item in matrix.cells), Decimal(0)
            ) != Decimal(matrix.total):
                raise ValueError("P&L matrix does not contain 18 reconciled cells")
        if tuple((item.realization, item.driver) for item in cells) != tuple(
            (item.realization, item.driver) for item in self.ending_matrix.cells
        ):
            raise ValueError("exit period cell identity differs")
        if any(
            Decimal(period.amount) != Decimal(ending.amount) - Decimal(beginning.amount)
            for beginning, ending, period in zip(
                self.exit_beginning_matrix.cells,
                self.ending_matrix.cells,
                cells,
                strict=True,
            )
        ):
            raise ValueError("exit period cells are not ending minus beginning")
        if sum((Decimal(item.amount) for item in cells), Decimal(0)) != Decimal(
            self.exit_period_total_pnl
        ):
            raise ValueError("exit period cells do not reconcile")
        if Decimal(self.ending_matrix.total) != Decimal(self.lifetime_total_pnl):
            raise ValueError("lifetime P&L does not reconcile")
        contribution_totals: dict[tuple[Stage5DPnlRealization, Stage5DPnlDriver], Decimal] = {}
        for item in contributions:
            key = (item.realization, item.driver)
            contribution_totals[key] = contribution_totals.get(key, Decimal(0)) + Decimal(
                item.signed_amount
            )
        if any(
            contribution_totals.get((item.realization, item.driver), Decimal(0))
            != Decimal(item.amount)
            for item in self.ending_matrix.cells
        ):
            raise ValueError("P&L contributions do not reconcile to ending cells")
        if not isinstance(self.pnl_hash, HashDigest) or self.pnl_hash not in (
            _ZERO_HASH,
            _hash(_without_hash(self, "pnl_hash")),
        ):
            raise ValueError("pnl_hash differs")


def _bind_pnl(value: Stage5DNormalLifecyclePnl) -> Stage5DNormalLifecyclePnl:
    return replace(value, pnl_hash=_hash(_without_hash(value, "pnl_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DCompletedTradeRecord(CanonicalModel):
    completed_trade_id: str
    candidate_id: str
    strategy_id: str
    security_id: str
    account_fixture_id: str
    entry_fill_hash: HashDigest
    exit_fill_hash: HashDigest
    quantity: int
    position_closed_at: datetime
    ledger_settled_at: datetime
    final_journal_head_hash: HashDigest
    pnl_hash: HashDigest
    reconciled: bool
    synthetic: bool
    validation_only: bool
    not_a_real_completed_trade: bool
    authority_eligible: bool
    record_hash: HashDigest

    def __post_init__(self) -> None:
        for name in (
            "completed_trade_id",
            "candidate_id",
            "strategy_id",
            "security_id",
            "account_fixture_id",
        ):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be non-empty")
        for name in ("entry_fill_hash", "exit_fill_hash", "final_journal_head_hash", "pnl_hash"):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        if self.quantity != 200:
            raise ValueError("completed trade quantity must be 200")
        for name in ("position_closed_at", "ledger_settled_at"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if self.position_closed_at >= self.ledger_settled_at:
            raise ValueError("position_closed_at must precede ledger_settled_at")
        for name in (
            "reconciled",
            "synthetic",
            "validation_only",
            "not_a_real_completed_trade",
            "authority_eligible",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        if (
            not self.reconciled
            or not self.synthetic
            or not self.validation_only
            or not self.not_a_real_completed_trade
            or self.authority_eligible
        ):
            raise ValueError("completed trade authority boundary differs")
        if not isinstance(self.record_hash, HashDigest) or self.record_hash not in (
            _ZERO_HASH,
            _hash(_without_hash(self, "record_hash")),
        ):
            raise ValueError("record_hash differs")


def _bind_completed_trade(value: Stage5DCompletedTradeRecord) -> Stage5DCompletedTradeRecord:
    return replace(value, record_hash=_hash(_without_hash(value, "record_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DNormalLifecycleCase(CanonicalModel):
    case_id: str
    entry_case: Stage5DBoundedReplayCase
    materialized_inputs: Stage5DNormalLifecycleMaterializedInputs
    purpose: Stage5DNormalLifecyclePurpose
    source_complete_replay_hash: HashDigest | None
    code_commit: str
    semantic_config_hash: HashDigest
    injected_clock: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.case_id, str) or not self.case_id:
            raise ValueError("case_id must be non-empty")
        if not isinstance(self.entry_case, Stage5DBoundedReplayCase):
            raise TypeError("entry_case must be Stage5DBoundedReplayCase")
        if not isinstance(self.materialized_inputs, Stage5DNormalLifecycleMaterializedInputs):
            raise TypeError("materialized_inputs must be typed")
        if (
            self.materialized_inputs.input_set_hash.value
            != STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256
            or self.materialized_inputs.preregistration_raw_hash.value
            != STAGE5D_NORMAL_LIFECYCLE_PREREGISTRATION_SHA256
        ):
            raise ValueError("normal lifecycle input identity differs")
        if self.materialized_inputs.evaluator_implementation_authorized:
            raise ValueError("input fixture must not self-authorize evaluator")
        if not isinstance(self.purpose, Stage5DNormalLifecyclePurpose):
            raise TypeError("purpose must be Stage5DNormalLifecyclePurpose")
        if self.purpose is Stage5DNormalLifecyclePurpose.AUDIT_REPLAY:
            if not isinstance(self.source_complete_replay_hash, HashDigest):
                raise ValueError("audit replay requires a source hash")
        elif self.source_complete_replay_hash is not None:
            raise ValueError("research validation cannot carry a source replay hash")
        if not isinstance(self.code_commit, str) or not self.code_commit:
            raise ValueError("code_commit must be non-empty")
        if not isinstance(self.semantic_config_hash, HashDigest):
            raise TypeError("semantic_config_hash must be HashDigest")
        object.__setattr__(
            self,
            "injected_clock",
            normalize_utc(self.injected_clock, field_name="injected_clock"),
        )
        if self.injected_clock < datetime(2025, 4, 14, 2, 11, tzinfo=self.injected_clock.tzinfo):
            raise ValueError("injected_clock must include the settlement tail")


@dataclass(frozen=True, slots=True)
class Stage5DNormalLifecycleResult(CanonicalModel):
    schema_version: str
    status: Stage5DNormalLifecycleStatus
    reason_codes: tuple[str, ...]
    input_set_hash: HashDigest
    entry_complete_replay_hash: HashDigest | None
    exit_stage5c_result_hash: HashDigest | None
    exit_source_slice_hash: HashDigest | None
    financial_replay: Stage5DV2ReplayResult | None
    journal_entries: tuple[Stage5DLifecycleJournalEntry, ...]
    final_journal_head_hash: HashDigest | None
    valuation_series: Stage5DSessionValuationSeries | None
    pnl: Stage5DNormalLifecyclePnl | None
    completed_trade: Stage5DCompletedTradeRecord | None
    purpose: Stage5DNormalLifecyclePurpose
    source_complete_replay_hash: HashDigest | None
    complete_replay_hash: HashDigest
    replay_complete: bool
    valuation_complete: bool
    pnl_complete: bool
    reconciled: bool
    same_call_entry_and_exit_recomputed: bool
    audit_only: bool
    decimal_context_id: str = field(default=STAGE5_DECIMAL_CONTEXT_ID, init=False)
    approval_scope: RuleApprovalScope = field(default=STAGE5_5D_APPROVAL_SCOPE, init=False)
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    authority_eligible: bool = field(default=False, init=False)
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

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_NORMAL_LIFECYCLE_SCHEMA_VERSION:
            raise ValueError("unsupported normal lifecycle result schema_version")
        if not isinstance(self.status, Stage5DNormalLifecycleStatus):
            raise TypeError("status must be Stage5DNormalLifecycleStatus")
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))
        if not isinstance(self.input_set_hash, HashDigest):
            raise TypeError("input_set_hash must be HashDigest")
        for name in (
            "entry_complete_replay_hash",
            "exit_stage5c_result_hash",
            "exit_source_slice_hash",
            "final_journal_head_hash",
            "source_complete_replay_hash",
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, HashDigest):
                raise TypeError(f"{name} must be HashDigest or None")
        journal = tuple(self.journal_entries)
        if any(not isinstance(item, Stage5DLifecycleJournalEntry) for item in journal):
            raise TypeError("journal_entries must contain typed entries")
        object.__setattr__(self, "journal_entries", journal)
        if not isinstance(self.purpose, Stage5DNormalLifecyclePurpose):
            raise TypeError("purpose must be Stage5DNormalLifecyclePurpose")
        for name in (
            "replay_complete",
            "valuation_complete",
            "pnl_complete",
            "reconciled",
            "same_call_entry_and_exit_recomputed",
            "audit_only",
        ):
            if type(getattr(self, name)) is not bool:
                raise TypeError(f"{name} must be bool")
        complete = self.status is Stage5DNormalLifecycleStatus.COMPLETE
        if complete:
            if (
                not self.reason_codes
                or self.entry_complete_replay_hash is None
                or self.exit_stage5c_result_hash is None
                or self.exit_source_slice_hash is None
                or not isinstance(self.financial_replay, Stage5DV2ReplayResult)
                or len(journal) != 67
                or self.final_journal_head_hash != journal[-1].entry_hash
                or not isinstance(self.valuation_series, Stage5DSessionValuationSeries)
                or not isinstance(self.pnl, Stage5DNormalLifecyclePnl)
                or not isinstance(self.completed_trade, Stage5DCompletedTradeRecord)
                or self.completed_trade.final_journal_head_hash != self.final_journal_head_hash
                or self.completed_trade.pnl_hash != self.pnl.pnl_hash
                or not all(
                    (
                        self.replay_complete,
                        self.valuation_complete,
                        self.pnl_complete,
                        self.reconciled,
                        self.same_call_entry_and_exit_recomputed,
                    )
                )
            ):
                raise ValueError("complete normal lifecycle result is incomplete")
        elif (
            self.financial_replay is not None
            or journal
            or self.final_journal_head_hash is not None
            or self.valuation_series is not None
            or self.pnl is not None
            or self.completed_trade is not None
            or any(
                (
                    self.replay_complete,
                    self.valuation_complete,
                    self.pnl_complete,
                    self.reconciled,
                    self.same_call_entry_and_exit_recomputed,
                )
            )
        ):
            raise ValueError("blocked normal lifecycle result must not publish financial output")
        if self.purpose is Stage5DNormalLifecyclePurpose.AUDIT_REPLAY:
            if not self.audit_only or self.source_complete_replay_hash is None:
                raise ValueError("audit result requires source identity")
        elif self.audit_only or self.source_complete_replay_hash is not None:
            raise ValueError("research result must not claim audit replay")
        if not isinstance(self.complete_replay_hash, HashDigest):
            raise TypeError("complete_replay_hash must be HashDigest")


def _balance(state: Stage5DV2DerivedState, account: Stage5DV2Account) -> Decimal:
    return next(
        (
            Decimal(item.debit_less_credit)
            for item in state.balances
            if item.account is account and item.unit == "CNY" and item.security_id is None
        ),
        Decimal(0),
    )


def _cell_values(*, phase: str) -> dict[tuple[Stage5DPnlRealization, Stage5DPnlDriver], Decimal]:
    if phase == "ZERO":
        return {}
    if phase == "HOLDING":
        return {
            (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.PRICE): Decimal(0),
            (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.SLIPPAGE): Decimal("-8"),
            (Stage5DPnlRealization.UNREALIZED, Stage5DPnlDriver.FEE): Decimal("-5.23"),
        }
    if phase == "ENDING":
        return {
            (Stage5DPnlRealization.REALIZED, Stage5DPnlDriver.PRICE): Decimal(0),
            (Stage5DPnlRealization.REALIZED, Stage5DPnlDriver.SLIPPAGE): Decimal("-16"),
            (Stage5DPnlRealization.REALIZED, Stage5DPnlDriver.FEE): Decimal("-10.45"),
            (Stage5DPnlRealization.REALIZED, Stage5DPnlDriver.TAX): Decimal("-1.60"),
        }
    raise ValueError("unknown P&L phase")


def _matrix(
    as_of: datetime, values: dict[tuple[Stage5DPnlRealization, Stage5DPnlDriver], Decimal]
) -> Stage5DPnlMatrix:
    cells = tuple(
        Stage5DPnlCell(
            realization=realization,
            driver=driver,
            amount=_decimal_text(values.get((realization, driver), Decimal(0))),
        )
        for realization in Stage5DPnlRealization
        for driver in Stage5DPnlDriver
    )
    return Stage5DPnlMatrix(
        as_of=as_of,
        cells=cells,
        total=_decimal_text(sum((Decimal(item.amount) for item in cells), Decimal(0))),
    )


def _full_journal(
    financial_events: tuple[Stage5DV2Event, ...],
    marks: tuple[Stage5DLifecycleMarkObservation, ...],
) -> tuple[Stage5DLifecycleJournalEntry, ...]:
    raw: list[
        tuple[
            datetime,
            int,
            str,
            Stage5DLifecycleJournalEntryKind,
            Stage5DV2Event | None,
            Stage5DLifecycleMarkObservation | None,
        ]
    ] = []
    raw.extend(
        (
            item.effective_at,
            item.event_type_priority,
            item.event_id,
            Stage5DLifecycleJournalEntryKind.FINANCIAL_EVENT,
            item,
            None,
        )
        for item in financial_events
    )
    raw.extend(
        (
            item.valuation_at,
            STAGE5D_MARK_TO_MARKET_PRIORITY,
            item.mark_id,
            Stage5DLifecycleJournalEntryKind.MARK_TO_MARKET,
            None,
            item,
        )
        for item in marks
    )
    prior: tuple[HashDigest, ...] = ()
    result: list[Stage5DLifecycleJournalEntry] = []
    for ordinal, (effective_at, priority, entry_id, kind, financial, mark) in enumerate(
        sorted(raw, key=lambda item: (item[0], item[1], item[2]))
    ):
        entry = _bind_journal_entry(
            Stage5DLifecycleJournalEntry(
                ordinal=ordinal,
                entry_id=entry_id,
                kind=kind,
                effective_at=effective_at,
                priority=priority,
                prior_entry_hashes=prior,
                financial_event=financial,
                mark=mark,
                entry_hash=_ZERO_HASH,
            )
        )
        result.append(entry)
        prior += (entry.entry_hash,)
    return tuple(result)


def _journal_prefix_hash(
    entries: tuple[Stage5DLifecycleJournalEntry, ...], as_of: datetime
) -> HashDigest:
    return _hash(
        {
            "schema_version": STAGE5D_NORMAL_LIFECYCLE_SCHEMA_VERSION,
            "accepted_entry_hashes": tuple(
                item.entry_hash for item in entries if item.effective_at <= as_of
            ),
        }
    )


def _append_exit_events(
    entry_events: tuple[Stage5DV2Event, ...],
    exit_events: tuple[Stage5DV2Event, ...],
) -> tuple[Stage5DV2Event, ...]:
    selected = tuple(
        item
        for item in exit_events
        if item.event_type
        in (
            Stage5DV2EventType.SELL_TRADE,
            Stage5DV2EventType.SELL_CASH_SETTLEMENT,
            Stage5DV2EventType.SELL_CASH_AVAILABLE,
        )
    )
    if len(selected) != 3:
        raise ValueError("exit source must contain exactly three SELL events")
    entry_replay = replay_stage5d_v2_slice(
        entry_events,
        as_of=datetime(2025, 4, 11, 2, 30, tzinfo=selected[0].effective_at.tzinfo),
    )
    if (
        entry_replay.status is not Stage5DV2ReplayStatus.RECONCILED
        or entry_replay.derived_state is None
    ):
        raise ValueError("entry financial replay did not reconcile")
    entry_lots = {item.lot_id: item for item in entry_replay.derived_state.lots}
    prior = tuple(item.declared_canonical_hash for item in entry_events)
    appended: list[Stage5DV2Event] = list(entry_events)
    for event in selected:
        effects: tuple[Stage5DV2LotEffect, ...] = event.lot_effects
        if event.event_type is Stage5DV2EventType.SELL_TRADE:
            effects = tuple(
                replace(effect, source_fill_hash=entry_lots[effect.lot_id].source_fill_hash)
                for effect in event.lot_effects
            )
        rebound = bind_stage5d_v2_event(
            replace(event, prior_event_hashes=prior, lot_effects=effects)
        )
        appended.append(rebound)
        prior += (rebound.declared_canonical_hash,)
    return tuple(appended)


def _valuation_series(
    inputs: Stage5DNormalLifecycleMaterializedInputs,
    financial_events: tuple[Stage5DV2Event, ...],
    journal: tuple[Stage5DLifecycleJournalEntry, ...],
) -> Stage5DSessionValuationSeries:
    baseline_at = financial_events[0].effective_at
    baseline_replay = replay_stage5d_v2_slice(financial_events, as_of=baseline_at)
    if baseline_replay.status is not Stage5DV2ReplayStatus.RECONCILED:
        raise ValueError("baseline financial replay did not reconcile")
    zero_matrix = _matrix(baseline_at, _cell_values(phase="ZERO"))
    points: list[Stage5DSessionValuationPoint] = []

    def append_point(
        *,
        index: int,
        session_id: str,
        at: datetime,
        replay: Stage5DV2ReplayResult,
        mark: Stage5DLifecycleMarkObservation | None,
        matrix: Stage5DPnlMatrix,
    ) -> None:
        state = replay.derived_state
        if replay.status is not Stage5DV2ReplayStatus.RECONCILED or state is None:
            raise ValueError("valuation financial replay did not reconcile")
        quantity = state.actual_quantity(inputs.exit_mandate.security_id)
        sellable = state.sellable_quantity(inputs.exit_mandate.security_id)
        market_value = Decimal(0) if mark is None else Decimal(mark.price) * quantity
        available = Decimal(state.available_cash)
        reserved = Decimal(0)
        settled_unavailable = _balance(state, Stage5DV2Account.CASH_SETTLED_UNAVAILABLE)
        receivable = _balance(state, Stage5DV2Account.CASH_RECEIVABLE)
        payable = Decimal(state.cash_payable)
        nav = available + reserved + settled_unavailable + receivable - payable + market_value
        points.append(
            _bind_valuation(
                Stage5DSessionValuationPoint(
                    session_index=index,
                    session_id=session_id,
                    valuation_at=at,
                    journal_prefix_hash=_journal_prefix_hash(journal, at),
                    financial_replay_hash=replay.replay_hash,
                    mark_hash=mark.mark_hash if mark is not None else None,
                    cash_available=_decimal_text(available),
                    cash_reserved="0",
                    cash_settled_unavailable=_decimal_text(settled_unavailable),
                    cash_receivable=_decimal_text(receivable),
                    cash_payable=_decimal_text(payable),
                    actual_quantity=quantity,
                    sellable_quantity=sellable,
                    mark_price=mark.price if mark is not None else None,
                    security_market_value=_decimal_text(market_value),
                    nav=_decimal_text(nav),
                    cumulative_pnl_hash=_hash(matrix),
                    valuation_hash=_ZERO_HASH,
                )
            )
        )

    append_point(
        index=0,
        session_id="baseline_before_entry",
        at=baseline_at,
        replay=baseline_replay,
        mark=None,
        matrix=zero_matrix,
    )
    holding_values = _cell_values(phase="HOLDING")
    ending_values = _cell_values(phase="ENDING")
    marks = {item.ordinal: item for item in inputs.mark_set.marks}
    for session in inputs.lifecycle_calendar.sessions:
        replay = replay_stage5d_v2_slice(financial_events, as_of=session.valuation_at)
        mark = marks.get(session.ordinal)
        matrix = _matrix(
            session.valuation_at,
            holding_values if session.ordinal < 60 else ending_values,
        )
        append_point(
            index=session.ordinal,
            session_id=session.session_id,
            at=session.valuation_at,
            replay=replay,
            mark=mark,
            matrix=matrix,
        )
    factors = tuple(
        _decimal_text(Decimal(current.nav) / Decimal(previous.nav))
        for previous, current in zip(points, points[1:], strict=False)
    )
    return _bind_series(
        Stage5DSessionValuationSeries(
            points=tuple(points),
            daily_return_factors=factors,
            series_hash=_ZERO_HASH,
        )
    )


def _pnl(
    financial_events: tuple[Stage5DV2Event, ...],
    series: Stage5DSessionValuationSeries,
) -> Stage5DNormalLifecyclePnl:
    lifetime_beginning = _matrix(
        series.points[0].valuation_at,
        _cell_values(phase="ZERO"),
    )
    exit_beginning = _matrix(
        series.points[59].valuation_at,
        _cell_values(phase="HOLDING"),
    )
    ending = _matrix(
        series.points[60].valuation_at,
        _cell_values(phase="ENDING"),
    )
    period_cells = tuple(
        Stage5DPnlCell(
            realization=end.realization,
            driver=end.driver,
            amount=_decimal_text(Decimal(end.amount) - Decimal(begin.amount)),
        )
        for begin, end in zip(exit_beginning.cells, ending.cells, strict=True)
    )
    buy = next(item for item in financial_events if item.event_type is Stage5DV2EventType.BUY_TRADE)
    sell = next(
        item for item in financial_events if item.event_type is Stage5DV2EventType.SELL_TRADE
    )
    lot_id = buy.lot_effects[0].lot_id
    values = (
        (Stage5DPnlDriver.PRICE, "TB", sell.event_id, None, Decimal("1600")),
        (Stage5DPnlDriver.PRICE, "DB", sell.event_id, lot_id, Decimal("-1600")),
        (Stage5DPnlDriver.SLIPPAGE, "TS", sell.event_id, None, Decimal("-8")),
        (Stage5DPnlDriver.SLIPPAGE, "DS", sell.event_id, lot_id, Decimal("-8")),
        (Stage5DPnlDriver.FEE, "SF", sell.event_id, None, Decimal("-5.22")),
        (Stage5DPnlDriver.FEE, "DF", sell.event_id, lot_id, Decimal("-5.23")),
        (Stage5DPnlDriver.TAX, "ST", sell.event_id, None, Decimal("-1.60")),
    )
    contributions = tuple(
        Stage5DPnlContribution(
            as_of=series.points[60].valuation_at,
            realization=Stage5DPnlRealization.REALIZED,
            driver=driver,
            formula_term=term,
            source_event_id=event_id,
            source_lot_id=source_lot_id,
            signed_amount=_decimal_text(amount),
        )
        for driver, term, event_id, source_lot_id, amount in values
    )
    return _bind_pnl(
        Stage5DNormalLifecyclePnl(
            formula_map_hash=HashDigest(
                algorithm="sha256",
                value=STAGE5D_PNL_FORMULA_MAP_SHA256,
            ),
            lifetime_beginning_matrix=lifetime_beginning,
            exit_beginning_matrix=exit_beginning,
            ending_matrix=ending,
            exit_period_cells=period_cells,
            ending_contributions=contributions,
            lifetime_total_pnl="-28.05",
            exit_period_total_pnl="-14.82",
            pnl_hash=_ZERO_HASH,
        )
    )


def _result(
    case: Stage5DNormalLifecycleCase,
    *,
    status: Stage5DNormalLifecycleStatus,
    reason_codes: tuple[str, ...],
    entry_hash: HashDigest | None = None,
    exit_result_hash: HashDigest | None = None,
    exit_slice_hash: HashDigest | None = None,
    financial_replay: Stage5DV2ReplayResult | None = None,
    journal: tuple[Stage5DLifecycleJournalEntry, ...] = (),
    series: Stage5DSessionValuationSeries | None = None,
    pnl: Stage5DNormalLifecyclePnl | None = None,
    completed: Stage5DCompletedTradeRecord | None = None,
) -> Stage5DNormalLifecycleResult:
    complete = status is Stage5DNormalLifecycleStatus.COMPLETE
    value = Stage5DNormalLifecycleResult(
        schema_version=STAGE5D_NORMAL_LIFECYCLE_SCHEMA_VERSION,
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        input_set_hash=case.materialized_inputs.input_set_hash,
        entry_complete_replay_hash=entry_hash,
        exit_stage5c_result_hash=exit_result_hash,
        exit_source_slice_hash=exit_slice_hash,
        financial_replay=financial_replay,
        journal_entries=journal,
        final_journal_head_hash=journal[-1].entry_hash if journal else None,
        valuation_series=series,
        pnl=pnl,
        completed_trade=completed,
        purpose=case.purpose,
        source_complete_replay_hash=case.source_complete_replay_hash,
        complete_replay_hash=_ZERO_HASH,
        replay_complete=complete,
        valuation_complete=complete,
        pnl_complete=complete,
        reconciled=complete,
        same_call_entry_and_exit_recomputed=complete,
        audit_only=case.purpose is Stage5DNormalLifecyclePurpose.AUDIT_REPLAY,
    )
    payload = value.to_json_value()
    del payload["complete_replay_hash"]
    return replace(value, complete_replay_hash=_hash({"case": case, "result": payload}))


@with_stage5_decimal_context
def evaluate_stage5d_normal_lifecycle(
    case: Stage5DNormalLifecycleCase,
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
    stage5d_capability: ApprovedRuleCapability,
) -> Stage5DNormalLifecycleResult:
    """Recompute and close the exact anonymous synthetic normal lifecycle."""

    if not isinstance(case, Stage5DNormalLifecycleCase):
        raise TypeError("case must be Stage5DNormalLifecycleCase")
    inputs = case.materialized_inputs
    if (
        inputs.input_set_hash.value != STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256
        or inputs.exit_mandate.exit_origin != "STAGE6C_VALIDATION_HORIZON_LIQUIDATION"
        or inputs.mark_coverage.mark_set_hash != inputs.mark_set.mark_set_hash
        or len(inputs.mark_set.marks) != 59
        or len(inputs.lifecycle_calendar.sessions) != 60
        or inputs.evaluator_implementation_authorized
    ):
        return _result(
            case,
            status=Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_NORMAL_LIFECYCLE_INPUT_PRECHECK_FAILED",),
        )
    research_entry_case = replace(
        case.entry_case,
        purpose=Stage5DBoundedReplayPurpose.RESEARCH_VALIDATION,
        source_complete_replay_hash=None,
    )
    entry = evaluate_stage5d_bounded_complete_replay(
        research_entry_case,
        market_rules,
        portfolio_rules,
        stage5d_capability,
    )
    if (
        entry.status is not Stage5DBoundedReplayStatus.COMPLETE
        or entry.complete_replay_hash != inputs.entry_complete_replay_hash
        or entry.rematerialized_v2_replay is None
        or entry.rematerialized_v2_replay.derived_state is None
        or entry.rematerialized_v2_replay.derived_state.journal_head_hash
        != inputs.entry_ending_journal_head_hash
        or len(entry.rematerialized_v2_replay.derived_state.lots) != 1
        or _hash(entry.rematerialized_v2_replay.derived_state.lots[0])
        != inputs.entry_derived_lot_hash
    ):
        return _result(
            case,
            status=Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_NORMAL_LIFECYCLE_ENTRY_RECOMPUTATION_MISMATCH",),
        )
    snapshot_lot: SyntheticLotSnapshot = (
        inputs.exit_stage5c_case.synthetic_account_snapshot.positions[0].lots[0]
    )
    attribution = bind_stage5d_v2_opening_attribution(
        Stage5DV2OpeningLotAttribution(
            attribution_id="stage5d_normal_lifecycle_exit_opening_attribution",
            strategy_id=inputs.exit_stage5c_case.synthetic_account_snapshot.strategy_id,
            account_fixture_id=(
                inputs.exit_stage5c_case.synthetic_account_snapshot.account_fixture_id
            ),
            lot_id=snapshot_lot.lot_id,
            security_id=snapshot_lot.security_id,
            acquired_at=snapshot_lot.acquired_at,
            quantity=snapshot_lot.quantity,
            sellable_quantity=snapshot_lot.sellable_quantity,
            governing_market_rule_hash=snapshot_lot.governing_market_rule_hash,
            source_lot_hash=_hash(snapshot_lot),
            cost_components=Stage5DV2CostComponents(
                principal="1600",
                fee="5.23",
                tax="0",
                slippage="8",
                basis_adjustment="0",
            ),
            declared_content_hash=_ZERO_HASH,
        )
    )
    exit_source = evaluate_stage5d_source_driven_ledger_slice(
        inputs.exit_stage5c_case,
        market_rules,
        portfolio_rules,
        stage5d_capability,
        opening_attributions=(attribution,),
    )
    exit_market = (
        exit_source.stage5c_result.constrained_market_projection.market_execution_result
        if exit_source.stage5c_result.constrained_market_projection is not None
        else None
    )
    exit_fill = exit_market.fill if exit_market is not None else None
    if (
        exit_source.status is not Stage5DSourceDrivenSliceStatus.SELL_RECONCILED
        or exit_source.v2_replay is None
        or exit_fill is None
        or exit_fill.side is not TradeSide.SELL
        or exit_fill.quantity != 200
        or exit_fill.fill_price != "7.96"
        or exit_fill.cash_effect != "1585.18"
    ):
        return _result(
            case,
            status=Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_NORMAL_LIFECYCLE_EXIT_RECOMPUTATION_MISMATCH",),
            entry_hash=entry.complete_replay_hash,
            exit_result_hash=exit_source.stage5c_result_hash,
            exit_slice_hash=_hash(exit_source),
        )
    try:
        financial_events = _append_exit_events(
            entry.rematerialized_v2_replay.projected_events,
            exit_source.v2_replay.projected_events,
        )
        financial_replay = replay_stage5d_v2_slice(
            financial_events,
            as_of=case.injected_clock,
        )
        if (
            financial_replay.status is not Stage5DV2ReplayStatus.RECONCILED
            or financial_replay.future_events
            or financial_replay.derived_state is None
            or financial_replay.derived_state.lots
            or financial_replay.derived_state.actual_quantity(inputs.exit_mandate.security_id) != 0
            or financial_replay.derived_state.available_cash != "99971.95"
        ):
            raise ValueError("final financial replay did not close")
        journal = _full_journal(financial_events, inputs.mark_set.marks)
        if len(journal) != 67 or tuple(item.ordinal for item in journal) != tuple(range(67)):
            raise ValueError("full journal inventory differs")
        series = _valuation_series(inputs, financial_events, journal)
        if (
            series.points[0].nav != "100000"
            or any(item.nav != "99986.77" for item in series.points[1:60])
            or series.points[60].nav != "99971.95"
        ):
            raise ValueError("valuation golden differs")
        pnl = _pnl(financial_events, series)
        if Decimal(series.points[-1].nav) - Decimal(series.points[0].nav) != Decimal(
            pnl.lifetime_total_pnl
        ):
            raise ValueError("lifetime NAV/P&L identity differs")
        entry_lot = entry.rematerialized_v2_replay.derived_state.lots[0]
        completed = _bind_completed_trade(
            Stage5DCompletedTradeRecord(
                completed_trade_id="stage5d_completed_trade:synthetic_normal_lifecycle_001",
                candidate_id=inputs.exit_mandate.candidate_id,
                strategy_id=inputs.exit_mandate.strategy_id,
                security_id=inputs.exit_mandate.security_id,
                account_fixture_id=inputs.exit_mandate.account_fixture_id,
                entry_fill_hash=entry_lot.source_fill_hash,
                exit_fill_hash=_hash(exit_fill),
                quantity=200,
                position_closed_at=exit_fill.filled_at,
                ledger_settled_at=financial_events[-1].effective_at,
                final_journal_head_hash=journal[-1].entry_hash,
                pnl_hash=pnl.pnl_hash,
                reconciled=True,
                synthetic=True,
                validation_only=True,
                not_a_real_completed_trade=True,
                authority_eligible=False,
                record_hash=_ZERO_HASH,
            )
        )
    except (TypeError, ValueError, ArithmeticError):
        return _result(
            case,
            status=Stage5DNormalLifecycleStatus.RECONCILIATION_BLOCKED,
            reason_codes=("STAGE5D_NORMAL_LIFECYCLE_RECONCILIATION_FAILED",),
            entry_hash=entry.complete_replay_hash,
            exit_result_hash=exit_source.stage5c_result_hash,
            exit_slice_hash=_hash(exit_source),
        )
    research_case = replace(
        case,
        purpose=Stage5DNormalLifecyclePurpose.RESEARCH_VALIDATION,
        source_complete_replay_hash=None,
    )
    research_result = _result(
        research_case,
        status=Stage5DNormalLifecycleStatus.COMPLETE,
        reason_codes=("STAGE5D_NORMAL_LIFECYCLE_COMPLETE",),
        entry_hash=entry.complete_replay_hash,
        exit_result_hash=exit_source.stage5c_result_hash,
        exit_slice_hash=_hash(exit_source),
        financial_replay=financial_replay,
        journal=journal,
        series=series,
        pnl=pnl,
        completed=completed,
    )
    if case.purpose is Stage5DNormalLifecyclePurpose.AUDIT_REPLAY:
        if case.source_complete_replay_hash != research_result.complete_replay_hash:
            return _result(
                case,
                status=Stage5DNormalLifecycleStatus.PRECHECK_BLOCKED,
                reason_codes=("STAGE5D_NORMAL_LIFECYCLE_AUDIT_SOURCE_MISMATCH",),
                entry_hash=entry.complete_replay_hash,
                exit_result_hash=exit_source.stage5c_result_hash,
                exit_slice_hash=_hash(exit_source),
            )
        return _result(
            case,
            status=Stage5DNormalLifecycleStatus.COMPLETE,
            reason_codes=("STAGE5D_NORMAL_LIFECYCLE_AUDIT_REPLAY_COMPLETE",),
            entry_hash=entry.complete_replay_hash,
            exit_result_hash=exit_source.stage5c_result_hash,
            exit_slice_hash=_hash(exit_source),
            financial_replay=financial_replay,
            journal=journal,
            series=series,
            pnl=pnl,
            completed=completed,
        )
    return research_result


__all__ = [
    "STAGE5D_NORMAL_LIFECYCLE_INPUT_SET_SHA256",
    "STAGE5D_NORMAL_LIFECYCLE_PREREGISTRATION_SHA256",
    "STAGE5D_NORMAL_LIFECYCLE_SCHEMA_VERSION",
    "Stage5DCompletedTradeRecord",
    "Stage5DLifecycleJournalEntry",
    "Stage5DLifecycleJournalEntryKind",
    "Stage5DNormalLifecycleCase",
    "Stage5DNormalLifecyclePnl",
    "Stage5DNormalLifecyclePurpose",
    "Stage5DNormalLifecycleResult",
    "Stage5DNormalLifecycleStatus",
    "Stage5DSessionValuationPoint",
    "Stage5DSessionValuationSeries",
    "evaluate_stage5d_normal_lifecycle",
]
