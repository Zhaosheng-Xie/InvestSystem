"""Pure Stage 5C target sizing and portfolio-risk validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_FLOOR, Decimal

from invest_system.models import CanonicalModel, HashDigest

from .stage5_decimal import with_stage5_decimal_context
from .stage5_execution_contracts import (
    MarketRegime,
    MarketRegimeSnapshot,
    PortfolioSizingInputs,
    PortfolioTarget,
    RecoveryApprovalDecision,
    RiskClusterSnapshot,
    RiskConstraintValue,
    Stage5CArtifact,
    StressScenarioInput,
    SyntheticAccountSnapshot,
    SyntheticRecoveryRecord,
    bind_stage5c_artifact,
    stage5c_artifact_content_sha256,
)
from .stage5_governance import STAGE5_STRATEGY_ID, ApprovedStage5PortfolioLedgerRules
from .stage5_market_execution import (
    Stage5ActionIntent,
    Stage5ExecutionStatus,
    Stage5MarketExecutionCase,
    stage5_artifact_content_sha256,
)


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _number(value: Decimal) -> str:
    if value == 0:
        return "0"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


@dataclass(frozen=True, slots=True)
class PortfolioRiskEvaluation(CanonicalModel):
    status: Stage5ExecutionStatus
    reason_codes: tuple[str, ...]
    target: PortfolioTarget | None
    account_snapshot_hash: HashDigest
    risk_cluster_hash: HashDigest
    market_regime_hash: HashDigest
    stress_scenario_hash: HashDigest
    sizing_inputs_hash: HashDigest
    selected_rounding_market_rule_hash: HashDigest | None
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    drawdown_band: str
    survival_limit_breach: bool
    run_mode: str = field(default="research", init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)


def _artifact_ok(value: Stage5CArtifact) -> bool:
    return value.identity.declared_content_hash.value == stage5c_artifact_content_sha256(value)


def _recovery_record_failure(
    case: Stage5MarketExecutionCase,
    account: SyntheticAccountSnapshot,
    record: SyntheticRecoveryRecord,
) -> str | None:
    if not _artifact_ok(record):
        return "RECOVERY_RECORD_HASH_DRIFT"
    if account.ledger_head_hash is None:
        return "STOPPED_STATE_LEDGER_HEAD_MISSING"
    if (
        record.strategy_id != case.strategy_id
        or record.strategy_id != account.strategy_id
        or record.account_fixture_id != case.account_fixture_id
        or record.account_fixture_id != account.account_fixture_id
        or record.account_ledger_head_hash != account.ledger_head_hash
    ):
        return "RECOVERY_RECORD_SCOPE_OR_LEDGER_HEAD_MISMATCH"
    if (
        record.identity.as_of != record.effective_at
        or record.identity.knowledge_cutoff > record.effective_at
        or record.effective_at > account.identity.as_of
        or record.effective_at > case.synthetic_approval_fixture.approved_at
        or record.owner_approval_at > record.effective_at
        or record.prior_stopped_at >= record.owner_approval_at
    ):
        return "RECOVERY_RECORD_FROM_FUTURE_OR_TIME_SCOPE_INVALID"
    return None


def _failure(
    status: Stage5ExecutionStatus,
    reason: str,
    *,
    account: SyntheticAccountSnapshot,
    clusters: RiskClusterSnapshot,
    regime: MarketRegimeSnapshot,
    stress: StressScenarioInput,
    sizing: PortfolioSizingInputs,
    rules: ApprovedStage5PortfolioLedgerRules,
    drawdown_band: str = "UNVERIFIED",
    survival: bool = False,
    selected_rounding_market_rule_hash: HashDigest | None = None,
) -> PortfolioRiskEvaluation:
    return PortfolioRiskEvaluation(
        status=status,
        reason_codes=(reason,),
        target=None,
        account_snapshot_hash=account.identity.declared_content_hash,
        risk_cluster_hash=clusters.identity.declared_content_hash,
        market_regime_hash=regime.identity.declared_content_hash,
        stress_scenario_hash=stress.identity.declared_content_hash,
        sizing_inputs_hash=sizing.identity.declared_content_hash,
        selected_rounding_market_rule_hash=selected_rounding_market_rule_hash,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
        drawdown_band=drawdown_band,
        survival_limit_breach=survival,
    )


def _drawdown_band(drawdown: Decimal, rules: ApprovedStage5PortfolioLedgerRules) -> str:
    if drawdown >= rules.drawdown_survival_breach:
        return "SURVIVAL_LIMIT_BREACH"
    if drawdown >= rules.drawdown_stopped:
        return "STOPPED"
    if drawdown >= rules.drawdown_derisk_only:
        return "DERISK_ONLY"
    if drawdown >= rules.drawdown_caution:
        return "CAUTION_NO_ADDITIONS"
    return "NORMAL"


@with_stage5_decimal_context
def evaluate_stage5_portfolio_target(
    case: Stage5MarketExecutionCase,
    account: SyntheticAccountSnapshot,
    clusters: RiskClusterSnapshot,
    regime: MarketRegimeSnapshot,
    stress: StressScenarioInput,
    sizing: PortfolioSizingInputs,
    target_identity: object,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> PortfolioRiskEvaluation:
    """Compute the approved Stage 5C target without accepting partial results."""

    from .stage4_expectation_valuation_exit import VersionedArtifactIdentity

    if not isinstance(case, Stage5MarketExecutionCase):
        raise TypeError("case must be Stage5MarketExecutionCase")
    if not isinstance(rules, ApprovedStage5PortfolioLedgerRules):
        raise TypeError("rules must be ApprovedStage5PortfolioLedgerRules")
    if not isinstance(target_identity, VersionedArtifactIdentity):
        raise TypeError("target_identity must be VersionedArtifactIdentity")
    approval_at = case.synthetic_approval_fixture.approved_at
    if any(not _artifact_ok(value) for value in (account, clusters, regime, stress, sizing)):
        return _failure(
            Stage5ExecutionStatus.PRECHECK_BLOCKED,
            "STAGE5C_ARTIFACT_HASH_DRIFT",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
        )
    if (
        case.strategy_id != STAGE5_STRATEGY_ID
        or account.strategy_id != case.strategy_id
        or clusters.strategy_id != case.strategy_id
        or account.account_fixture_id != case.account_fixture_id
        or clusters.security_id != case.security_id
        or sizing.proposal_reference_price_hash
        != case.proposal_reference_price.identity.declared_content_hash
    ):
        return _failure(
            Stage5ExecutionStatus.PRECHECK_BLOCKED,
            "STAGE5C_SCOPE_MISMATCH",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
        )
    if (
        any(
            value.identity.as_of > approval_at or value.identity.knowledge_cutoff > approval_at
            for value in (account, clusters, regime, stress, sizing)
        )
        or target_identity.as_of > approval_at
        or target_identity.knowledge_cutoff > approval_at
        or case.proposal_reference_price.identity.as_of > case.proposal_reference_price.observed_at
        or case.proposal_reference_price.identity.knowledge_cutoff
        > case.proposal_reference_price.observed_at
        or case.synthetic_approval_fixture.identity.as_of != approval_at
        or case.synthetic_approval_fixture.identity.knowledge_cutoff > approval_at
    ):
        return _failure(
            Stage5ExecutionStatus.PRECHECK_BLOCKED,
            "STAGE5C_INPUT_FROM_FUTURE",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
        )

    nav = Decimal(account.net_asset_value)
    drawdown = Decimal(account.declared_drawdown)
    band = _drawdown_band(drawdown, rules)
    survival = drawdown >= rules.drawdown_survival_breach
    is_new_risk = case.action_intent in (Stage5ActionIntent.ENTER, Stage5ActionIntent.ADD)

    if not is_new_risk:
        position = account.position(case.security_id)
        target_quantity = min(case.proposed_quantity, position.quantity if position else 0)
        price = Decimal(case.proposal_reference_price.price)
        target_value = price * target_quantity
        constraint_values = (
            RiskConstraintValue("requested_derisk_value", _number(target_value)),
            RiskConstraintValue(
                "current_position_value",
                _number(Decimal(position.market_value) if position else Decimal(0)),
            ),
        )
        reason = "DERISK_TARGET_READY" if target_quantity > 0 else "NO_POSITION_TO_DERISK"
        target = bind_stage5c_artifact(
            PortfolioTarget(
                identity=target_identity,
                case_id=case.case_id,
                security_id=case.security_id,
                account_fixture_id=case.account_fixture_id,
                action_intent=case.action_intent,
                proposal_reference_price_hash=case.proposal_reference_price.identity.declared_content_hash,
                account_snapshot_hash=account.identity.declared_content_hash,
                risk_cluster_hash=clusters.identity.declared_content_hash,
                market_regime_hash=regime.identity.declared_content_hash,
                stress_scenario_hash=stress.identity.declared_content_hash,
                sizing_inputs_hash=sizing.identity.declared_content_hash,
                selected_rounding_market_rule_hash=None,
                rule_bundle_hash=rules.bundle_hash,
                rule_approval_id=rules.approval_id,
                rule_approval_record_hash=rules.approval_record_hash,
                stress_loss_rate="0.10",
                planned_account_loss_rate="0",
                constraint_values=constraint_values,
                target_value=_number(target_value),
                target_quantity=target_quantity,
                rounded_target_value=_number(target_value),
                binding_constraint_ids=("requested_derisk_value",),
                reason_codes=(reason,),
            )
        )
        return PortfolioRiskEvaluation(
            status=(
                Stage5ExecutionStatus.TARGET_READY
                if target_quantity > 0
                else Stage5ExecutionStatus.SYNTHETIC_REJECTED
            ),
            reason_codes=(reason,),
            target=target,
            account_snapshot_hash=account.identity.declared_content_hash,
            risk_cluster_hash=clusters.identity.declared_content_hash,
            market_regime_hash=regime.identity.declared_content_hash,
            stress_scenario_hash=stress.identity.declared_content_hash,
            sizing_inputs_hash=sizing.identity.declared_content_hash,
            selected_rounding_market_rule_hash=None,
            rule_bundle_hash=rules.bundle_hash,
            rule_approval_id=rules.approval_id,
            rule_approval_record_hash=rules.approval_record_hash,
            drawdown_band=band,
            survival_limit_breach=survival,
        )

    recovery_record = account.synthetic_recovery_record
    if recovery_record is not None:
        recovery_failure = _recovery_record_failure(case, account, recovery_record)
        if recovery_failure is not None:
            return _failure(
                Stage5ExecutionStatus.PRECHECK_BLOCKED,
                recovery_failure,
                account=account,
                clusters=clusters,
                regime=regime,
                stress=stress,
                sizing=sizing,
                rules=rules,
                drawdown_band=band,
                survival=survival,
            )

    if regime.regime is None:
        return _failure(
            Stage5ExecutionStatus.ABSTAIN,
            "MARKET_REGIME_UNKNOWN",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
            drawdown_band=band,
            survival=survival,
        )
    if stress.scenario_return is None or not stress.comparable_to_account_nav:
        return _failure(
            Stage5ExecutionStatus.ABSTAIN,
            "STRESS_SCENARIO_MISSING_OR_INCOMPARABLE",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
            drawdown_band=band,
            survival=survival,
        )
    exposure_by_id = {
        (item.cluster_type, item.cluster_id): item for item in account.risk_cluster_exposures
    }
    if any(
        (assignment.cluster_type, assignment.cluster_id) not in exposure_by_id
        for assignment in clusters.assignments
    ):
        return _failure(
            Stage5ExecutionStatus.ABSTAIN,
            "REQUIRED_RISK_CLUSTER_EXPOSURE_MISSING",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
            drawdown_band=band,
            survival=survival,
        )

    stress_return = Decimal(stress.scenario_return)
    stress_loss_rate = max(abs(min(Decimal(0), stress_return)), Decimal("0.10"))
    planned_loss_rate = (
        rules.normal_planned_loss_rate
        if regime.regime is MarketRegime.NORMAL
        else rules.defensive_planned_loss_rate
        if regime.regime is MarketRegime.DEFENSIVE
        else rules.crisis_new_risk_rate
    )
    zero_reason: str | None = None
    if drawdown >= rules.drawdown_stopped:
        planned_loss_rate = Decimal(0)
        zero_reason = "DRAWDOWN_STOPPED_NEW_RISK_FORBIDDEN"
    elif drawdown >= rules.drawdown_derisk_only:
        planned_loss_rate = Decimal(0)
        zero_reason = "DRAWDOWN_DERISK_ONLY"
    elif drawdown >= rules.drawdown_caution:
        planned_loss_rate = min(planned_loss_rate, rules.defensive_planned_loss_rate)
        if case.action_intent is Stage5ActionIntent.ADD:
            planned_loss_rate = Decimal(0)
            zero_reason = "DRAWDOWN_ADDITION_FORBIDDEN"
    if account.prior_stopped and drawdown < rules.drawdown_stopped:
        if recovery_record is None:
            planned_loss_rate = Decimal(0)
            zero_reason = "STOPPED_STATE_RECOVERY_RECORD_MISSING"
        elif recovery_record.owner_approval_decision is not RecoveryApprovalDecision.APPROVED:
            planned_loss_rate = Decimal(0)
            zero_reason = "STOPPED_STATE_OWNER_RECOVERY_APPROVAL_MISSING"
    if regime.regime is MarketRegime.CRISIS:
        zero_reason = "CRISIS_NEW_RISK_FORBIDDEN"

    price = Decimal(case.proposal_reference_price.price)
    current_company_value = sum(
        Decimal(position.market_value)
        for position in account.positions
        if position.company_id == clusters.company_id
    )
    company_remaining = max(nav * rules.company_weight_cap - current_company_value, Decimal(0))
    aggregate_remaining = (
        max(
            nav * rules.aggregate_planned_loss_cap - Decimal(account.aggregate_open_planned_loss),
            Decimal(0),
        )
        / stress_loss_rate
    )
    cluster_values: list[RiskConstraintValue] = []
    cluster_remaining_values: list[Decimal] = []
    for assignment in sorted(
        clusters.assignments,
        key=lambda item: (item.cluster_type.value, item.cluster_id),
    ):
        exposure = exposure_by_id[(assignment.cluster_type, assignment.cluster_id)]
        market_remaining = max(
            nav * rules.cluster_market_value_cap - Decimal(exposure.market_value),
            Decimal(0),
        )
        loss_remaining = (
            max(
                nav * rules.cluster_planned_loss_cap - Decimal(exposure.planned_loss),
                Decimal(0),
            )
            / stress_loss_rate
        )
        remaining = min(market_remaining, loss_remaining)
        cluster_id = f"cluster:{assignment.cluster_type.value}:{assignment.cluster_id}"
        cluster_values.append(RiskConstraintValue(cluster_id, _number(remaining)))
        cluster_remaining_values.append(remaining)
    available_after_reserve = max(
        Decimal(account.available_cash) - Decimal(sizing.worst_applicable_cost_reserve),
        Decimal(0),
    )
    values = [
        RiskConstraintValue(
            "planned_loss_budget",
            _number(nav * planned_loss_rate / stress_loss_rate),
        ),
        RiskConstraintValue("initial_e4_weight", _number(nav * rules.initial_weight_cap)),
        RiskConstraintValue("liquidity_capacity", sizing.liquidity_capacity_value),
        RiskConstraintValue("company_remaining", _number(company_remaining)),
        *cluster_values,
        RiskConstraintValue("aggregate_risk_remaining", _number(aggregate_remaining)),
        RiskConstraintValue("cash_after_cost_reserve", _number(available_after_reserve)),
    ]
    minimum = min(Decimal(item.value_cny) for item in values)
    binding = tuple(item.constraint_id for item in values if Decimal(item.value_cny) == minimum)

    selected_rules = tuple(
        item
        for item in case.market_rule_sets
        if item.effective_from <= case.proposal_reference_price.observed_at
        and (
            item.effective_to is None
            or case.proposal_reference_price.observed_at < item.effective_to
        )
        and item.venue == case.venue
        and item.board == case.board
        and item.security_type == case.security_type
        and item.risk_label_scope in (case.risk_label, "ALL")
        and item.published_at <= case.proposal_reference_price.observed_at
        and item.identity.as_of <= case.proposal_reference_price.observed_at
        and item.identity.knowledge_cutoff <= case.proposal_reference_price.observed_at
        and item.identity.declared_content_hash.value == stage5_artifact_content_sha256(item)
    )
    if len(selected_rules) != 1:
        return _failure(
            Stage5ExecutionStatus.ABSTAIN,
            "EXACT_MARKET_RULE_REQUIRED_FOR_TARGET_ROUNDING",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
            drawdown_band=band,
            survival=survival,
        )
    lot_size = selected_rules[0].buy_lot_size
    selected_rounding_rule_hash = selected_rules[0].identity.declared_content_hash
    target_quantity = int((minimum / price).to_integral_value(rounding=ROUND_FLOOR))
    target_quantity = (target_quantity // lot_size) * lot_size
    rounded_value = price * target_quantity
    if rounded_value > minimum:
        return _failure(
            Stage5ExecutionStatus.PRECHECK_BLOCKED,
            "ROUNDED_TARGET_EXCEEDS_BINDING_LIMIT",
            account=account,
            clusters=clusters,
            regime=regime,
            stress=stress,
            sizing=sizing,
            rules=rules,
            drawdown_band=band,
            survival=survival,
        )
    reason = zero_reason or (
        "TARGET_BELOW_MINIMUM_LEGAL_LOT" if target_quantity == 0 else "PORTFOLIO_TARGET_READY"
    )
    target = bind_stage5c_artifact(
        PortfolioTarget(
            identity=target_identity,
            case_id=case.case_id,
            security_id=case.security_id,
            account_fixture_id=case.account_fixture_id,
            action_intent=case.action_intent,
            proposal_reference_price_hash=case.proposal_reference_price.identity.declared_content_hash,
            account_snapshot_hash=account.identity.declared_content_hash,
            risk_cluster_hash=clusters.identity.declared_content_hash,
            market_regime_hash=regime.identity.declared_content_hash,
            stress_scenario_hash=stress.identity.declared_content_hash,
            sizing_inputs_hash=sizing.identity.declared_content_hash,
            selected_rounding_market_rule_hash=selected_rounding_rule_hash,
            rule_bundle_hash=rules.bundle_hash,
            rule_approval_id=rules.approval_id,
            rule_approval_record_hash=rules.approval_record_hash,
            stress_loss_rate=_number(stress_loss_rate),
            planned_account_loss_rate=_number(planned_loss_rate),
            constraint_values=tuple(values),
            target_value=_number(minimum),
            target_quantity=target_quantity,
            rounded_target_value=_number(rounded_value),
            binding_constraint_ids=binding,
            reason_codes=(reason,),
        )
    )
    return PortfolioRiskEvaluation(
        status=(
            Stage5ExecutionStatus.TARGET_READY
            if target_quantity > 0
            else Stage5ExecutionStatus.SYNTHETIC_REJECTED
        ),
        reason_codes=(reason,),
        target=target,
        account_snapshot_hash=account.identity.declared_content_hash,
        risk_cluster_hash=clusters.identity.declared_content_hash,
        market_regime_hash=regime.identity.declared_content_hash,
        stress_scenario_hash=stress.identity.declared_content_hash,
        sizing_inputs_hash=sizing.identity.declared_content_hash,
        selected_rounding_market_rule_hash=selected_rounding_rule_hash,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
        drawdown_band=band,
        survival_limit_breach=survival,
    )
