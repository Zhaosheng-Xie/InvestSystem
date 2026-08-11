"""Stage 5C recomputation boundary for the first source-driven Ledger V2 slice."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleStatus,
)
from invest_system.models import CanonicalModel, HashDigest, RunMode

from .stage5_decimal import STAGE5_DECIMAL_CONTEXT_ID, with_stage5_decimal_context
from .stage5_execution_contracts import (
    SettlementAvailabilityTerms,
    SettlementMomentKind,
    stage5c_artifact_content_sha256,
)
from .stage5_governance import (
    STAGE5_5A_RULE_APPROVAL_ID,
    STAGE5_5A_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5A_RULE_BUNDLE_SHA256,
    STAGE5_STRATEGY_ID,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from .stage5_ledger import LedgerReplayStatus
from .stage5_market_execution import (
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    TradeSide,
    stage5_artifact_content_sha256,
)
from .stage5_portfolio_ledger_engine import (
    Stage5PortfolioLedgerCase,
    Stage5PortfolioLedgerResult,
    evaluate_stage5_portfolio_ledger,
    stage5c_portfolio_ledger_projection_sha256,
)
from .stage5d_governance import (
    STAGE5_5D_APPROVAL_SCOPE,
    STAGE5_5D_RULE_APPROVAL_ID,
    STAGE5_5D_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5D_RULE_BUNDLE_ID,
    STAGE5_5D_RULE_BUNDLE_SHA256,
    STAGE5_5D_RULE_BUNDLE_VERSION,
)
from .stage5d_ledger_v2 import (
    STAGE5D_V2_EVENT_PRIORITY,
    STAGE5D_V2_SLICE_SCHEMA_VERSION,
    Stage5DV2Account,
    Stage5DV2CostComponents,
    Stage5DV2Event,
    Stage5DV2EventType,
    Stage5DV2LotEffect,
    Stage5DV2Posting,
    Stage5DV2ReplayResult,
    Stage5DV2ReplayStatus,
    Stage5DV2SourceRef,
    Stage5DV2SourceRole,
    bind_stage5d_v2_event,
    replay_stage5d_v2_slice,
)


class Stage5DSourceDrivenSliceStatus(StrEnum):
    BUY_RECONCILED = "BUY_RECONCILED"
    NO_FILL_RECONCILED = "NO_FILL_RECONCILED"
    SOURCE_PRECHECK_BLOCKED = "SOURCE_PRECHECK_BLOCKED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"
    UNSUPPORTED_SLICE = "UNSUPPORTED_SLICE"


_ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)


def _hash(value: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(value))


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@dataclass(frozen=True, slots=True)
class Stage5DSourceDrivenSliceResult(CanonicalModel):
    schema_version: str
    case_id: str
    status: Stage5DSourceDrivenSliceStatus
    reason_codes: tuple[str, ...]
    input_hash: HashDigest
    stage5c_result: Stage5PortfolioLedgerResult
    stage5c_result_hash: HashDigest
    stage5c_projection_replay_hash: HashDigest
    stage5d_rule_bundle_hash: HashDigest
    stage5d_rule_approval_id: str
    stage5d_rule_approval_record_hash: HashDigest
    v2_replay: Stage5DV2ReplayResult | None
    slice_replay_hash: HashDigest
    decimal_context_id: str = field(default=STAGE5_DECIMAL_CONTEXT_ID, init=False)
    approval_scope: RuleApprovalScope = field(default=STAGE5_5D_APPROVAL_SCOPE, init=False)
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    source_driven: bool = field(default=True, init=False)
    same_call_stage5c_recomputed: bool = field(default=True, init=False)
    not_stage5d1_complete: bool = field(default=True, init=False)
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


def stage5d_source_driven_slice_sha256(
    case: Stage5PortfolioLedgerCase,
    result: Stage5DSourceDrivenSliceResult,
) -> str:
    projected = result.to_json_value()
    del projected["slice_replay_hash"]
    return canonical_sha256({"case": case, "result": projected})


def _result(
    case: Stage5PortfolioLedgerCase,
    source: Stage5PortfolioLedgerResult,
    capability: ApprovedRuleCapability,
    *,
    status: Stage5DSourceDrivenSliceStatus,
    reason_codes: tuple[str, ...],
    replay: Stage5DV2ReplayResult | None = None,
) -> Stage5DSourceDrivenSliceResult:
    value = Stage5DSourceDrivenSliceResult(
        schema_version=STAGE5D_V2_SLICE_SCHEMA_VERSION,
        case_id=case.case_id,
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        input_hash=_hash(case),
        stage5c_result=source,
        stage5c_result_hash=_hash(source),
        stage5c_projection_replay_hash=source.projection_replay_hash,
        stage5d_rule_bundle_hash=capability.bundle_hash,
        stage5d_rule_approval_id=capability.approval_id,
        stage5d_rule_approval_record_hash=capability.approval_record_hash,
        v2_replay=replay,
        slice_replay_hash=_ZERO_HASH,
    )
    return replace(
        value,
        slice_replay_hash=HashDigest(
            algorithm="sha256",
            value=stage5d_source_driven_slice_sha256(case, value),
        ),
    )


def _require_exact_capability(capability: ApprovedRuleCapability) -> None:
    if not isinstance(capability, ApprovedRuleCapability):
        raise TypeError("stage5d_capability must be ApprovedRuleCapability")
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
    if actual != expected:
        raise ValueError("the first Ledger V2 slice requires the exact Stage 5D capability")


def _require_exact_stage5_rules(
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
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
            raise ValueError("Stage 5D must recompute from the exact approved Stage 5A rules")


def _stage5c_source_is_exact(
    case: Stage5PortfolioLedgerCase,
    result: Stage5PortfolioLedgerResult,
) -> bool:
    if result.input_hash != _hash(case):
        return False
    if result.projection_replay_hash.value != stage5c_portfolio_ledger_projection_sha256(
        case, result
    ):
        return False
    if (
        result.run_mode is not RunMode.RESEARCH
        or not result.synthetic
        or not result.validation_only
        or result.persists_state
        or result.authorizes_backtest
        or result.authorizes_paper
        or result.authorizes_shadow
        or result.authorizes_live
        or result.authorizes_real_accounts
        or result.authorizes_positions
        or result.authorizes_orders
        or result.connects_broker
    ):
        return False
    constrained = result.constrained_market_projection
    if constrained is None:
        return True
    market = constrained.market_execution_result
    if (
        not constrained.synthetic
        or not constrained.validation_only
        or constrained.persists_state
        or constrained.authorizes_orders
        or not market.synthetic
        or not market.validation_only
        or market.persists_state
        or market.authorizes_backtest
        or market.authorizes_paper
        or market.authorizes_shadow
        or market.authorizes_live
        or market.authorizes_real_accounts
        or market.authorizes_positions
        or market.authorizes_orders
        or market.connects_broker
    ):
        return False
    order = market.order_intent
    fill = market.fill
    return not (
        order is not None
        and (not order.synthetic or not order.validation_only or order.broker_route is not None)
        or fill is not None
        and (not fill.synthetic or not fill.validation_only)
    )


def _empty_opening_supported(case: Stage5PortfolioLedgerCase) -> bool:
    account = case.synthetic_account_snapshot
    initial = case.initial_ledger_snapshot
    return (
        account.base_currency == "CNY"
        and Decimal(account.reserved_cash) == 0
        and Decimal(account.unsettled_cash_receivable) == 0
        and Decimal(account.unsettled_cash_payable) == 0
        and Decimal(account.available_cash) == Decimal(account.settled_cash)
        and not account.positions
        and account.ledger_head_hash is None
        and not initial.prior_event_hashes
        and initial.empty_stage5c_opening_projection
        and case.corporate_action_set.explicitly_empty_for_stage5c
        and not case.corporate_action_set.applicable_action_ids
    )


def _posting(
    account: Stage5DV2Account,
    unit: str,
    security_id: str | None,
    amount: Decimal,
    *,
    debit: bool,
) -> Stage5DV2Posting:
    return Stage5DV2Posting(
        account=account,
        unit=unit,
        security_id=security_id,
        debit=_decimal_text(amount if debit else Decimal(0)),
        credit=_decimal_text(Decimal(0) if debit else amount),
    )


def _source(
    role: Stage5DV2SourceRole,
    object_id: str,
    content_hash: HashDigest,
) -> Stage5DV2SourceRef:
    return Stage5DV2SourceRef(role=role, object_id=object_id, content_hash=content_hash)


@dataclass(frozen=True, slots=True)
class _EventSpec:
    event_id: str
    event_type: Stage5DV2EventType
    security_id: str | None
    effective_at: datetime
    source_refs: tuple[Stage5DV2SourceRef, ...]
    postings: tuple[Stage5DV2Posting, ...]
    lot_effects: tuple[Stage5DV2LotEffect, ...]


def _bind_ordered_events(
    case: Stage5PortfolioLedgerCase,
    specs: tuple[_EventSpec, ...],
) -> tuple[Stage5DV2Event, ...]:
    ordered = sorted(
        specs,
        key=lambda item: (
            item.effective_at,
            STAGE5D_V2_EVENT_PRIORITY[item.event_type],
            item.event_id,
        ),
    )
    prior: tuple[HashDigest, ...] = ()
    result: list[Stage5DV2Event] = []
    for spec in ordered:
        event = bind_stage5d_v2_event(
            Stage5DV2Event(
                event_id=spec.event_id,
                event_type=spec.event_type,
                strategy_id=case.market_execution_case.strategy_id,
                account_fixture_id=case.market_execution_case.account_fixture_id,
                security_id=spec.security_id,
                effective_at=spec.effective_at,
                source_refs=spec.source_refs,
                prior_event_hashes=prior,
                postings=spec.postings,
                lot_effects=spec.lot_effects,
                declared_canonical_hash=_ZERO_HASH,
            )
        )
        result.append(event)
        prior += (event.declared_canonical_hash,)
    return tuple(result)


def _opening_spec(case: Stage5PortfolioLedgerCase) -> _EventSpec:
    account = case.synthetic_account_snapshot
    cash = Decimal(account.available_cash)
    return _EventSpec(
        event_id=f"stage5d_v2:{case.case_id}:opening",
        event_type=Stage5DV2EventType.OPENING_BALANCE,
        security_id=None,
        effective_at=case.initial_ledger_snapshot.head_observed_at,
        source_refs=(
            _source(Stage5DV2SourceRole.STAGE5C_CASE, case.case_id, _hash(case)),
            _source(
                Stage5DV2SourceRole.ACCOUNT_SNAPSHOT,
                account.identity.artifact_id,
                account.identity.declared_content_hash,
            ),
            _source(
                Stage5DV2SourceRole.INITIAL_LEDGER,
                case.initial_ledger_snapshot.identity.artifact_id,
                case.initial_ledger_snapshot.identity.declared_content_hash,
            ),
        ),
        postings=(
            _posting(Stage5DV2Account.CASH_AVAILABLE, "CNY", None, cash, debit=True),
            _posting(Stage5DV2Account.OPENING_CONTROL, "CNY", None, cash, debit=False),
        ),
        lot_effects=(),
    )


def _matching_terms(
    case: Stage5PortfolioLedgerCase,
    local_trade_date: str,
    market_rule_hash: HashDigest,
) -> SettlementAvailabilityTerms | None:
    matches = tuple(
        item
        for item in case.settlement_terms
        if item.trade_local_date == local_trade_date
        and item.market_rule_hash == market_rule_hash
        and item.identity.declared_content_hash.value == stage5c_artifact_content_sha256(item)
    )
    return matches[0] if len(matches) == 1 else None


def _buy_specs(
    case: Stage5PortfolioLedgerCase,
    result: Stage5PortfolioLedgerResult,
) -> tuple[_EventSpec, ...] | None:
    constrained = result.constrained_market_projection
    if constrained is None:
        return None
    market = constrained.market_execution_result
    order = market.order_intent
    fill = market.fill
    if order is None or fill is None or fill.side is not TradeSide.BUY:
        return None
    attempt = next(
        (item for item in market.attempts if item.observation_id == fill.observation_id), None
    )
    observation = next(
        (
            item
            for item in case.market_execution_case.market_observation_set.observations
            if item.observation_id == fill.observation_id
        ),
        None,
    )
    if attempt is None or observation is None:
        return None
    if (
        attempt.market_rule_hash is None
        or attempt.cost_schedule_hash is None
        or attempt.impact_curve_hash is None
    ):
        return None
    raw = case.market_execution_case
    market_rule = next(
        (
            item
            for item in raw.market_rule_sets
            if item.identity.declared_content_hash == attempt.market_rule_hash
        ),
        None,
    )
    cost = next(
        (
            item
            for item in raw.cost_schedules
            if item.identity.declared_content_hash == attempt.cost_schedule_hash
        ),
        None,
    )
    impact = next(
        (
            item
            for item in raw.impact_curves
            if item.identity.declared_content_hash == attempt.impact_curve_hash
        ),
        None,
    )
    terms = _matching_terms(case, attempt.local_trade_date, attempt.market_rule_hash)
    if market_rule is None or cost is None or impact is None or terms is None:
        return None
    if (
        market_rule.identity.declared_content_hash.value
        != stage5_artifact_content_sha256(market_rule)
        or cost.identity.declared_content_hash.value != stage5_artifact_content_sha256(cost)
        or impact.identity.declared_content_hash.value != stage5_artifact_content_sha256(impact)
        or terms.special_exception_id is not None
        or order.quantity != fill.quantity
        or order.security_id != fill.security_id
        or order.market_rule_hash != attempt.market_rule_hash
        or order.cost_schedule_hash != attempt.cost_schedule_hash
        or order.impact_curve_hash != attempt.impact_curve_hash
        or fill.order_intent_id != order.order_intent_id
        or fill.filled_at != order.submitted_at
    ):
        return None

    quantity = fill.quantity
    principal = Decimal(fill.benchmark_vwap) * quantity
    gross = Decimal(fill.gross_notional)
    slippage = gross - principal
    fee = sum(
        (
            Decimal(fill.costs.exchange_fee),
            Decimal(fill.costs.regulatory_fee),
            Decimal(fill.costs.transfer_fee),
            Decimal(fill.costs.broker_commission),
        ),
        Decimal(0),
    )
    tax = Decimal(fill.costs.tax)
    components = Stage5DV2CostComponents(
        principal=_decimal_text(principal),
        fee=_decimal_text(fee),
        tax=_decimal_text(tax),
        slippage=_decimal_text(slippage),
        basis_adjustment="0",
    )
    all_in = components.total()
    if (
        slippage < 0
        or gross != principal + slippage
        or Decimal(fill.costs.total) != fee + tax
        or Decimal(fill.cash_effect) != -all_in
    ):
        return None
    case_hash = _hash(case)
    result_hash = _hash(result)
    order_hash = _hash(order)
    fill_hash = _hash(fill)
    observation_hash = _hash(observation)
    lot_id = f"stage5d_v2_lot:{fill.fill_id}"
    zero_components = Stage5DV2CostComponents("0", "0", "0", "0", "0")

    trade_postings = [
        _posting(
            Stage5DV2Account.SECURITY_COST_PRINCIPAL,
            "CNY",
            fill.security_id,
            principal,
            debit=True,
        ),
        _posting(
            Stage5DV2Account.SECURITY_COST_SLIPPAGE,
            "CNY",
            fill.security_id,
            slippage,
            debit=True,
        ),
        _posting(
            Stage5DV2Account.SECURITY_COST_FEE,
            "CNY",
            fill.security_id,
            fee,
            debit=True,
        ),
    ]
    if tax > 0:
        trade_postings.append(
            _posting(
                Stage5DV2Account.SECURITY_COST_TAX,
                "CNY",
                fill.security_id,
                tax,
                debit=True,
            )
        )
    trade_postings.extend(
        (
            _posting(Stage5DV2Account.CASH_PAYABLE, "CNY", None, all_in, debit=False),
            _posting(
                Stage5DV2Account.SECURITY_UNSETTLED,
                fill.security_id,
                fill.security_id,
                Decimal(quantity),
                debit=True,
            ),
            _posting(
                Stage5DV2Account.SECURITY_CONTROL,
                fill.security_id,
                fill.security_id,
                Decimal(quantity),
                debit=False,
            ),
        )
    )
    trade_sources = (
        _source(Stage5DV2SourceRole.STAGE5C_CASE, case.case_id, case_hash),
        _source(Stage5DV2SourceRole.STAGE5C_RESULT, result.case_id, result_hash),
        _source(Stage5DV2SourceRole.ORDER_INTENT, order.order_intent_id, order_hash),
        _source(Stage5DV2SourceRole.FILL, fill.fill_id, fill_hash),
        _source(
            Stage5DV2SourceRole.MARKET_OBSERVATION,
            observation.observation_id,
            observation_hash,
        ),
        _source(
            Stage5DV2SourceRole.MARKET_RULE,
            market_rule.identity.artifact_id,
            attempt.market_rule_hash,
        ),
        _source(
            Stage5DV2SourceRole.COST_SCHEDULE, cost.identity.artifact_id, attempt.cost_schedule_hash
        ),
        _source(
            Stage5DV2SourceRole.IMPACT_CURVE, impact.identity.artifact_id, attempt.impact_curve_hash
        ),
    )
    settlement_sources = (
        _source(Stage5DV2SourceRole.FILL, fill.fill_id, fill_hash),
        _source(
            Stage5DV2SourceRole.SETTLEMENT_TERMS,
            terms.identity.artifact_id,
            terms.identity.declared_content_hash,
        ),
        _source(
            Stage5DV2SourceRole.MARKET_RULE,
            market_rule.identity.artifact_id,
            attempt.market_rule_hash,
        ),
    )
    acquired_at = fill.filled_at
    buy_payable = terms.moment(SettlementMomentKind.BUY_CASH_PAYABLE)
    security_settlement = terms.moment(SettlementMomentKind.SECURITY_SETTLEMENT)
    security_sellable = terms.moment(SettlementMomentKind.SECURITY_SELLABLE)
    return (
        _opening_spec(case),
        _EventSpec(
            event_id=f"stage5d_v2:{case.case_id}:buy_trade",
            event_type=Stage5DV2EventType.BUY_TRADE,
            security_id=fill.security_id,
            effective_at=fill.filled_at,
            source_refs=trade_sources,
            postings=tuple(trade_postings),
            lot_effects=(
                Stage5DV2LotEffect(
                    lot_id=lot_id,
                    security_id=fill.security_id,
                    acquired_at=acquired_at,
                    source_fill_hash=fill_hash,
                    quantity_delta=quantity,
                    unsettled_quantity_delta=quantity,
                    unsellable_quantity_delta=0,
                    sellable_quantity_delta=0,
                    cost_components_delta=components,
                ),
            ),
        ),
        _EventSpec(
            event_id=f"stage5d_v2:{case.case_id}:buy_cash_settlement",
            event_type=Stage5DV2EventType.BUY_CASH_SETTLEMENT,
            security_id=fill.security_id,
            effective_at=buy_payable.effective_at,
            source_refs=settlement_sources,
            postings=(
                _posting(Stage5DV2Account.CASH_PAYABLE, "CNY", None, all_in, debit=True),
                _posting(Stage5DV2Account.CASH_AVAILABLE, "CNY", None, all_in, debit=False),
            ),
            lot_effects=(),
        ),
        _EventSpec(
            event_id=f"stage5d_v2:{case.case_id}:security_settlement",
            event_type=Stage5DV2EventType.SECURITY_SETTLEMENT,
            security_id=fill.security_id,
            effective_at=security_settlement.effective_at,
            source_refs=settlement_sources,
            postings=(
                _posting(
                    Stage5DV2Account.SECURITY_UNSELLABLE,
                    fill.security_id,
                    fill.security_id,
                    Decimal(quantity),
                    debit=True,
                ),
                _posting(
                    Stage5DV2Account.SECURITY_UNSETTLED,
                    fill.security_id,
                    fill.security_id,
                    Decimal(quantity),
                    debit=False,
                ),
            ),
            lot_effects=(
                Stage5DV2LotEffect(
                    lot_id=lot_id,
                    security_id=fill.security_id,
                    acquired_at=acquired_at,
                    source_fill_hash=fill_hash,
                    quantity_delta=0,
                    unsettled_quantity_delta=-quantity,
                    unsellable_quantity_delta=quantity,
                    sellable_quantity_delta=0,
                    cost_components_delta=zero_components,
                ),
            ),
        ),
        _EventSpec(
            event_id=f"stage5d_v2:{case.case_id}:security_sellable",
            event_type=Stage5DV2EventType.SECURITY_SELLABLE,
            security_id=fill.security_id,
            effective_at=security_sellable.effective_at,
            source_refs=settlement_sources,
            postings=(
                _posting(
                    Stage5DV2Account.SECURITY_SELLABLE,
                    fill.security_id,
                    fill.security_id,
                    Decimal(quantity),
                    debit=True,
                ),
                _posting(
                    Stage5DV2Account.SECURITY_UNSELLABLE,
                    fill.security_id,
                    fill.security_id,
                    Decimal(quantity),
                    debit=False,
                ),
            ),
            lot_effects=(
                Stage5DV2LotEffect(
                    lot_id=lot_id,
                    security_id=fill.security_id,
                    acquired_at=acquired_at,
                    source_fill_hash=fill_hash,
                    quantity_delta=0,
                    unsettled_quantity_delta=0,
                    unsellable_quantity_delta=-quantity,
                    sellable_quantity_delta=quantity,
                    cost_components_delta=zero_components,
                ),
            ),
        ),
    )


@with_stage5_decimal_context
def evaluate_stage5d_source_driven_ledger_slice(
    case: Stage5PortfolioLedgerCase,
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
    stage5d_capability: ApprovedRuleCapability,
) -> Stage5DSourceDrivenSliceResult:
    """Recompute Stage 5C and project the first source-driven V2 BUY/no-fill slice."""

    if not isinstance(case, Stage5PortfolioLedgerCase):
        raise TypeError("case must be Stage5PortfolioLedgerCase")
    _require_exact_capability(stage5d_capability)
    _require_exact_stage5_rules(market_rules, portfolio_rules)
    source = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    if not _stage5c_source_is_exact(case, source):
        return _result(
            case,
            source,
            stage5d_capability,
            status=Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_STAGE5C_RECOMPUTATION_OR_AUTHORITY_MISMATCH",),
        )
    if not _empty_opening_supported(case):
        return _result(
            case,
            source,
            stage5d_capability,
            status=Stage5DSourceDrivenSliceStatus.UNSUPPORTED_SLICE,
            reason_codes=("STAGE5D_V2_SLICE_REQUIRES_EMPTY_SYNTHETIC_OPENING",),
        )
    if source.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED:
        if (
            source.constrained_market_projection is not None
            or source.fill_ledger_projection is not None
            or source.ledger_replay is None
            or source.ledger_replay.status is not LedgerReplayStatus.RECONCILED
        ):
            return _result(
                case,
                source,
                stage5d_capability,
                status=Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED,
                reason_codes=("STAGE5D_NO_FILL_SOURCE_SHAPE_INVALID",),
            )
        events = _bind_ordered_events(case, (_opening_spec(case),))
        replay = replay_stage5d_v2_slice(events, as_of=case.injected_clock)
        status = (
            Stage5DSourceDrivenSliceStatus.NO_FILL_RECONCILED
            if replay.status is Stage5DV2ReplayStatus.RECONCILED
            else Stage5DSourceDrivenSliceStatus.RECONCILIATION_BLOCKED
        )
        return _result(
            case,
            source,
            stage5d_capability,
            status=status,
            reason_codes=replay.reason_codes,
            replay=replay,
        )
    if source.status in (
        Stage5ExecutionStatus.PRECHECK_BLOCKED,
        Stage5ExecutionStatus.RECONCILIATION_BLOCKED,
    ):
        return _result(
            case,
            source,
            stage5d_capability,
            status=Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_EXACT_STAGE5C_SOURCE_DID_NOT_RECONCILE", *source.reason_codes),
        )
    if (
        source.status is not Stage5ExecutionStatus.FILLED
        or case.market_execution_case.action_intent
        not in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD)
    ):
        return _result(
            case,
            source,
            stage5d_capability,
            status=Stage5DSourceDrivenSliceStatus.UNSUPPORTED_SLICE,
            reason_codes=("STAGE5D_V2_SLICE_SUPPORTS_ONLY_BUY_OR_EXPLICIT_REJECTED_NO_FILL",),
        )
    specs = _buy_specs(case, source)
    if specs is None:
        return _result(
            case,
            source,
            stage5d_capability,
            status=Stage5DSourceDrivenSliceStatus.SOURCE_PRECHECK_BLOCKED,
            reason_codes=("STAGE5D_BUY_SOURCE_CLOSURE_FAILED",),
        )
    events = _bind_ordered_events(case, specs)
    replay = replay_stage5d_v2_slice(events, as_of=case.injected_clock)
    status = (
        Stage5DSourceDrivenSliceStatus.BUY_RECONCILED
        if replay.status is Stage5DV2ReplayStatus.RECONCILED
        else Stage5DSourceDrivenSliceStatus.RECONCILIATION_BLOCKED
    )
    return _result(
        case,
        source,
        stage5d_capability,
        status=status,
        reason_codes=replay.reason_codes,
        replay=replay,
    )


__all__ = [
    "Stage5DSourceDrivenSliceResult",
    "Stage5DSourceDrivenSliceStatus",
    "evaluate_stage5d_source_driven_ledger_slice",
    "stage5d_source_driven_slice_sha256",
]
