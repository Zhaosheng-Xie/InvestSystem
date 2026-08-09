"""Complete Stage 5C synthetic portfolio, constrained fill and ledger engine."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import RuleApprovalScope
from invest_system.models import CanonicalModel, HashDigest, RunMode

from .stage4_expectation_valuation_exit import VersionedArtifactIdentity
from .stage5_decimal import STAGE5_DECIMAL_CONTEXT_ID, with_stage5_decimal_context
from .stage5_execution_contracts import (
    InitialLedgerSnapshot,
    MarketRegimeSnapshot,
    PortfolioApprovalDecision,
    PortfolioSizingInputs,
    RiskClusterSnapshot,
    SettlementAvailabilityTerms,
    Stage5CArtifact,
    StressScenarioInput,
    SyntheticAccountSnapshot,
    SyntheticCorporateActionSet,
    SyntheticPortfolioApproval,
    stage5c_artifact_content_sha256,
)
from .stage5_fill_projection import (
    Stage5FillLedgerProjection,
    Stage5FillProjectionError,
    project_stage5_fill_to_ledger,
    project_stage5_opening_to_ledger,
)
from .stage5_governance import (
    STAGE5_APPROVAL_SCOPE,
    STAGE5_STRATEGY_ID,
    ApprovedStage5MarketExecutionRules,
    ApprovedStage5PortfolioLedgerRules,
)
from .stage5_ledger import LedgerReplayResult, LedgerReplayStatus, replay_stage5c_ledger
from .stage5_market_execution import (
    Stage5ActionIntent,
    Stage5ConstrainedMarketExecutionProjection,
    Stage5ExecutionStatus,
    Stage5MarketCandidate,
    Stage5MarketExecutionCase,
    Stage5SubmissionReductionConstraint,
    bind_stage5_artifact,
    bind_stage5_submission_constraint_candidate,
    evaluate_stage5_market_execution_constrained,
    plan_stage5_market_candidate,
    stage5_constrained_market_execution_replay_sha256,
)
from .stage5_portfolio_risk import PortfolioRiskEvaluation, evaluate_stage5_portfolio_target

STAGE5C_ENGINE_SCHEMA_VERSION = "0.1.0"


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _decimal_text(value: Decimal) -> str:
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


@dataclass(frozen=True, slots=True)
class Stage5PortfolioLedgerCase(CanonicalModel):
    case_id: str
    market_execution_case: Stage5MarketExecutionCase
    synthetic_account_snapshot: SyntheticAccountSnapshot
    risk_cluster_snapshot: RiskClusterSnapshot
    market_regime_snapshot: MarketRegimeSnapshot
    stress_scenario_input: StressScenarioInput
    portfolio_sizing_inputs: PortfolioSizingInputs
    synthetic_portfolio_approval: SyntheticPortfolioApproval
    initial_ledger_snapshot: InitialLedgerSnapshot
    settlement_terms: tuple[SettlementAvailabilityTerms, ...]
    corporate_action_set: SyntheticCorporateActionSet
    target_identity: VersionedArtifactIdentity
    constraint_identity: VersionedArtifactIdentity
    code_commit: str
    config_hash: HashDigest
    injected_clock: datetime
    run_mode: RunMode = RunMode.RESEARCH
    anonymous_synthetic_fixture: bool = True
    validation_only: bool = True
    reads_kb_internal_state: bool = False
    connects_broker: bool = False
    persists_state: bool = False

    def __post_init__(self) -> None:
        if self.case_id != self.market_execution_case.case_id:
            raise ValueError("case_id must match the raw Stage 5B case")
        for name, expected in (
            ("synthetic_account_snapshot", SyntheticAccountSnapshot),
            ("risk_cluster_snapshot", RiskClusterSnapshot),
            ("market_regime_snapshot", MarketRegimeSnapshot),
            ("stress_scenario_input", StressScenarioInput),
            ("portfolio_sizing_inputs", PortfolioSizingInputs),
            ("synthetic_portfolio_approval", SyntheticPortfolioApproval),
            ("initial_ledger_snapshot", InitialLedgerSnapshot),
            ("corporate_action_set", SyntheticCorporateActionSet),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"{name} has the wrong type")
        terms = tuple(self.settlement_terms)
        if not terms or any(not isinstance(item, SettlementAvailabilityTerms) for item in terms):
            raise ValueError("settlement_terms must contain typed historical terms")
        object.__setattr__(self, "settlement_terms", terms)
        if not isinstance(self.target_identity, VersionedArtifactIdentity):
            raise TypeError("target_identity must be VersionedArtifactIdentity")
        if not isinstance(self.constraint_identity, VersionedArtifactIdentity):
            raise TypeError("constraint_identity must be VersionedArtifactIdentity")
        if not isinstance(self.code_commit, str) or not self.code_commit:
            raise ValueError("code_commit must be non-empty")
        if not isinstance(self.config_hash, HashDigest):
            raise TypeError("config_hash must be HashDigest")
        object.__setattr__(
            self,
            "injected_clock",
            normalize_utc(self.injected_clock, field_name="injected_clock"),
        )
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be RunMode")


@dataclass(frozen=True, slots=True)
class Stage5PositionLayers(CanonicalModel):
    target_quantity: int
    approved_quantity: int
    submitted_quantity: int
    filled_quantity: int
    actual_quantity: int
    unsubmitted_approved_quantity: int
    unfilled_cancelled_quantity: int
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        values = (
            self.target_quantity,
            self.approved_quantity,
            self.submitted_quantity,
            self.filled_quantity,
            self.actual_quantity,
            self.unsubmitted_approved_quantity,
            self.unfilled_cancelled_quantity,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in values
        ):
            raise ValueError("all position-layer quantities must be non-negative integers")
        if not (
            self.target_quantity
            >= self.approved_quantity
            >= self.submitted_quantity
            >= self.filled_quantity
        ):
            raise ValueError("target >= approved >= submitted >= filled must hold")


@dataclass(frozen=True, slots=True)
class Stage5PortfolioLedgerResult(CanonicalModel):
    schema_version: str
    case_id: str
    status: Stage5ExecutionStatus
    reason_codes: tuple[str, ...]
    input_hash: HashDigest
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    portfolio_risk_evaluation: PortfolioRiskEvaluation | None
    portfolio_approval_hash: HashDigest
    market_candidate: Stage5MarketCandidate | None
    submission_constraint: Stage5SubmissionReductionConstraint | None
    constrained_market_projection: Stage5ConstrainedMarketExecutionProjection | None
    fill_ledger_projection: Stage5FillLedgerProjection | None
    ledger_replay: LedgerReplayResult | None
    position_layers: Stage5PositionLayers | None
    ledger_replay_as_of: datetime
    projection_replay_hash: HashDigest
    decimal_context_id: str = field(default=STAGE5_DECIMAL_CONTEXT_ID, init=False)
    approval_scope: RuleApprovalScope = field(default=STAGE5_APPROVAL_SCOPE, init=False)
    run_mode: RunMode = field(default=RunMode.RESEARCH, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_complete_stage5_replay: bool = field(default=True, init=False)
    persists_state: bool = field(default=False, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_real_accounts: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)
    connects_broker: bool = field(default=False, init=False)


def stage5c_portfolio_ledger_projection_sha256(
    case: Stage5PortfolioLedgerCase,
    result: Stage5PortfolioLedgerResult,
) -> str:
    projected = result.to_json_value()
    del projected["projection_replay_hash"]
    return canonical_sha256({"case": case, "result": projected})


def _result(
    case: Stage5PortfolioLedgerCase,
    rules: ApprovedStage5PortfolioLedgerRules,
    *,
    status: Stage5ExecutionStatus,
    reason_codes: tuple[str, ...],
    risk: PortfolioRiskEvaluation | None = None,
    candidate: Stage5MarketCandidate | None = None,
    constraint: Stage5SubmissionReductionConstraint | None = None,
    constrained: Stage5ConstrainedMarketExecutionProjection | None = None,
    fill_projection: Stage5FillLedgerProjection | None = None,
    ledger: LedgerReplayResult | None = None,
    layers: Stage5PositionLayers | None = None,
) -> Stage5PortfolioLedgerResult:
    value = Stage5PortfolioLedgerResult(
        schema_version=STAGE5C_ENGINE_SCHEMA_VERSION,
        case_id=case.case_id,
        status=status,
        reason_codes=tuple(dict.fromkeys(reason_codes)),
        input_hash=_hash(canonical_sha256(case)),
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
        portfolio_risk_evaluation=risk,
        portfolio_approval_hash=case.synthetic_portfolio_approval.identity.declared_content_hash,
        market_candidate=candidate,
        submission_constraint=constraint,
        constrained_market_projection=constrained,
        fill_ledger_projection=fill_projection,
        ledger_replay=ledger,
        position_layers=layers,
        ledger_replay_as_of=case.injected_clock,
        projection_replay_hash=_hash("0" * 64),
    )
    return replace(
        value,
        projection_replay_hash=_hash(stage5c_portfolio_ledger_projection_sha256(case, value)),
    )


def _artifacts_valid(case: Stage5PortfolioLedgerCase) -> bool:
    artifacts: tuple[Stage5CArtifact, ...] = (
        case.synthetic_account_snapshot,
        case.risk_cluster_snapshot,
        case.market_regime_snapshot,
        case.stress_scenario_input,
        case.portfolio_sizing_inputs,
        case.synthetic_portfolio_approval,
        case.initial_ledger_snapshot,
        *case.settlement_terms,
        case.corporate_action_set,
    )
    return all(
        item.identity.declared_content_hash.value == stage5c_artifact_content_sha256(item)
        for item in artifacts
    )


def _scope_failure(case: Stage5PortfolioLedgerCase) -> str | None:
    raw = case.market_execution_case
    account = case.synthetic_account_snapshot
    approval = case.synthetic_portfolio_approval
    stage5c_artifacts: tuple[Stage5CArtifact, ...] = (
        case.synthetic_account_snapshot,
        case.risk_cluster_snapshot,
        case.market_regime_snapshot,
        case.stress_scenario_input,
        case.portfolio_sizing_inputs,
        case.synthetic_portfolio_approval,
        case.initial_ledger_snapshot,
        *case.settlement_terms,
        case.corporate_action_set,
    )
    if (
        raw.strategy_id != STAGE5_STRATEGY_ID
        or case.run_mode is not RunMode.RESEARCH
        or not case.anonymous_synthetic_fixture
        or not case.validation_only
        or case.reads_kb_internal_state
        or case.connects_broker
        or case.persists_state
    ):
        return "STAGE5C_AUTHORITY_BOUNDARY_VIOLATION"
    if (
        account.strategy_id != raw.strategy_id
        or account.account_fixture_id != raw.account_fixture_id
        or case.risk_cluster_snapshot.strategy_id != raw.strategy_id
        or case.risk_cluster_snapshot.security_id != raw.security_id
        or case.corporate_action_set.security_id != raw.security_id
        or case.initial_ledger_snapshot.strategy_id != raw.strategy_id
        or case.initial_ledger_snapshot.account_fixture_id != raw.account_fixture_id
    ):
        return "STAGE5C_SCOPE_MISMATCH"
    if (
        approval.case_id != raw.case_id
        or approval.security_id != raw.security_id
        or approval.account_fixture_id != raw.account_fixture_id
        or approval.action_intent is not raw.action_intent
        or approval.market_approval_hash
        != raw.synthetic_approval_fixture.identity.declared_content_hash
    ):
        return "PORTFOLIO_APPROVAL_SCOPE_MISMATCH"
    if (
        approval.approved_at != raw.synthetic_approval_fixture.approved_at
        or approval.expires_at > raw.synthetic_approval_fixture.expires_at
    ):
        return "PORTFOLIO_AND_MARKET_APPROVAL_WINDOW_MISMATCH"
    if case.injected_clock < approval.approved_at:
        return "INJECTED_CLOCK_PRECEDES_APPROVAL"
    if case.injected_clock != raw.injected_clock:
        return "STAGE5B_AND_STAGE5C_CLOCK_MISMATCH"
    approval_at = raw.synthetic_approval_fixture.approved_at
    target_inputs: tuple[Stage5CArtifact, ...] = (
        case.synthetic_account_snapshot,
        case.risk_cluster_snapshot,
        case.market_regime_snapshot,
        case.stress_scenario_input,
        case.portfolio_sizing_inputs,
    )
    if (
        any(
            item.identity.as_of > approval_at or item.identity.knowledge_cutoff > approval_at
            for item in target_inputs
        )
        or case.target_identity.as_of > approval_at
        or case.target_identity.knowledge_cutoff > approval_at
        or raw.proposal_reference_price.identity.as_of > raw.proposal_reference_price.observed_at
        or raw.proposal_reference_price.identity.knowledge_cutoff
        > raw.proposal_reference_price.observed_at
        or raw.synthetic_approval_fixture.identity.as_of != approval_at
        or raw.synthetic_approval_fixture.identity.knowledge_cutoff > approval_at
    ):
        return "STAGE5C_TARGET_INPUT_NOT_PIT_AT_APPROVAL"
    if any(
        artifact.identity.as_of > case.injected_clock
        or artifact.identity.knowledge_cutoff > case.injected_clock
        for artifact in stage5c_artifacts
    ) or any(
        identity.as_of > case.injected_clock or identity.knowledge_cutoff > case.injected_clock
        for identity in (case.target_identity, case.constraint_identity)
    ):
        return "STAGE5C_INPUT_NOT_PIT_AVAILABLE"
    return None


def _opening_replay(
    case: Stage5PortfolioLedgerCase,
    rules: ApprovedStage5PortfolioLedgerRules,
) -> LedgerReplayResult:
    events = project_stage5_opening_to_ledger(
        case.market_execution_case,
        case.synthetic_account_snapshot,
        case.initial_ledger_snapshot,
        rules,
    )
    return replay_stage5c_ledger(events)


def _opening_matches_account(
    account: SyntheticAccountSnapshot,
    ledger: LedgerReplayResult,
) -> bool:
    state = ledger.derived_state
    if ledger.status is not LedgerReplayStatus.RECONCILED or state is None:
        return False
    if (
        Decimal(state.available_cash) != Decimal(account.available_cash)
        or Decimal(state.reserved_cash) != Decimal(account.reserved_cash)
        or Decimal(state.unsettled_cash_receivable) != Decimal(account.unsettled_cash_receivable)
        or Decimal(state.unsettled_cash_payable) != Decimal(account.unsettled_cash_payable)
    ):
        return False
    for position in account.positions:
        if (
            state.actual_quantity(position.security_id) != position.quantity
            or state.sellable_quantity(position.security_id) != position.sellable_quantity
        ):
            return False
    return True


def _layers(
    target_quantity: int,
    approved_quantity: int,
    ledger: LedgerReplayResult,
    security_id: str,
    *,
    submitted: int = 0,
    filled: int = 0,
    unsubmitted: int | None = None,
    reason: str,
) -> Stage5PositionLayers:
    actual = (
        ledger.derived_state.actual_quantity(security_id) if ledger.derived_state is not None else 0
    )
    return Stage5PositionLayers(
        target_quantity=target_quantity,
        approved_quantity=approved_quantity,
        submitted_quantity=submitted,
        filled_quantity=filled,
        actual_quantity=actual,
        unsubmitted_approved_quantity=(
            approved_quantity - submitted if unsubmitted is None else unsubmitted
        ),
        unfilled_cancelled_quantity=0,
        reason_codes=(reason,),
    )


@with_stage5_decimal_context
def evaluate_stage5_portfolio_ledger(
    case: Stage5PortfolioLedgerCase,
    market_rules: ApprovedStage5MarketExecutionRules,
    portfolio_rules: ApprovedStage5PortfolioLedgerRules,
) -> Stage5PortfolioLedgerResult:
    """Recompute target → candidate → constraint → fill → in-memory journal."""

    if not isinstance(case, Stage5PortfolioLedgerCase):
        raise TypeError("case must be Stage5PortfolioLedgerCase")
    if not isinstance(market_rules, ApprovedStage5MarketExecutionRules):
        raise TypeError("market_rules must be ApprovedStage5MarketExecutionRules")
    if not isinstance(portfolio_rules, ApprovedStage5PortfolioLedgerRules):
        raise TypeError("portfolio_rules must be ApprovedStage5PortfolioLedgerRules")
    if not _artifacts_valid(case):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("STAGE5C_ARTIFACT_HASH_DRIFT",),
        )
    failure = _scope_failure(case)
    if failure is not None:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=(failure,),
        )
    risk = evaluate_stage5_portfolio_target(
        case.market_execution_case,
        case.synthetic_account_snapshot,
        case.risk_cluster_snapshot,
        case.market_regime_snapshot,
        case.stress_scenario_input,
        case.portfolio_sizing_inputs,
        case.target_identity,
        portfolio_rules,
    )
    if risk.target is None:
        return _result(
            case,
            portfolio_rules,
            status=risk.status,
            reason_codes=risk.reason_codes,
            risk=risk,
        )
    target = risk.target
    approval = case.synthetic_portfolio_approval
    risk_evaluation_hash = _hash(canonical_sha256(risk))
    if (
        approval.target_hash != target.identity.declared_content_hash
        or approval.portfolio_risk_evaluation_hash != risk_evaluation_hash
        or target.account_snapshot_hash
        != case.synthetic_account_snapshot.identity.declared_content_hash
        or target.risk_cluster_hash != case.risk_cluster_snapshot.identity.declared_content_hash
        or target.market_regime_hash != case.market_regime_snapshot.identity.declared_content_hash
        or target.stress_scenario_hash != case.stress_scenario_input.identity.declared_content_hash
        or target.sizing_inputs_hash != case.portfolio_sizing_inputs.identity.declared_content_hash
        or target.selected_rounding_market_rule_hash != risk.selected_rounding_market_rule_hash
        or target.rule_bundle_hash != portfolio_rules.bundle_hash
        or target.rule_approval_id != portfolio_rules.approval_id
        or target.rule_approval_record_hash != portfolio_rules.approval_record_hash
        or approval.approved_quantity > target.target_quantity
        or approval.approved_quantity
        > case.market_execution_case.synthetic_approval_fixture.approved_quantity
        or Decimal(approval.approved_notional_cap) > Decimal(target.rounded_target_value)
        or Decimal(approval.approved_planned_loss_cap)
        > Decimal(target.rounded_target_value) * Decimal(target.stress_loss_rate)
        or target.identity.as_of > approval.approved_at
    ):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("PORTFOLIO_APPROVAL_INCREASE_OR_TARGET_BINDING_MISMATCH",),
            risk=risk,
        )
    try:
        opening = _opening_replay(case, portfolio_rules)
    except Stage5FillProjectionError as error:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=(error.code,),
            risk=risk,
        )
    if not _opening_matches_account(case.synthetic_account_snapshot, opening):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("OPENING_JOURNAL_DOES_NOT_RECONCILE_ACCOUNT_SNAPSHOT",),
            risk=risk,
            ledger=opening,
        )
    if approval.decision is PortfolioApprovalDecision.REJECTED:
        layers = _layers(
            target.target_quantity,
            0,
            opening,
            case.market_execution_case.security_id,
            reason="PORTFOLIO_APPROVAL_REJECTED",
        )
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.SYNTHETIC_REJECTED,
            reason_codes=("PORTFOLIO_APPROVAL_REJECTED",),
            risk=risk,
            ledger=opening,
            layers=layers,
        )
    if risk.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("ZERO_TARGET_REQUIRES_EXPLICIT_REJECTED_APPROVAL",),
            risk=risk,
            ledger=opening,
        )

    position = case.synthetic_account_snapshot.position(case.market_execution_case.security_id)
    is_buy = case.market_execution_case.action_intent in (
        Stage5ActionIntent.ENTER,
        Stage5ActionIntent.ADD,
    )
    if is_buy:
        maximum_quantity = min(target.target_quantity, approval.approved_quantity)
        planned_loss_notional_cap = Decimal(approval.approved_planned_loss_cap) / Decimal(
            target.stress_loss_rate
        )
        maximum_gross = min(
            Decimal(target.rounded_target_value),
            Decimal(approval.approved_notional_cap),
            Decimal(case.market_execution_case.synthetic_approval_fixture.approved_notional_cap),
            planned_loss_notional_cap,
        )
        maximum_cash = Decimal(case.synthetic_account_snapshot.available_cash)
        maximum_cost_reserve: Decimal | None = Decimal(
            case.portfolio_sizing_inputs.worst_applicable_cost_reserve
        )
        maximum_sellable: int | None = None
    else:
        sellable = position.sellable_quantity if position is not None else 0
        maximum_quantity = min(target.target_quantity, approval.approved_quantity, sellable)
        maximum_gross = min(
            Decimal(target.rounded_target_value),
            Decimal(approval.approved_notional_cap),
            Decimal(case.market_execution_case.synthetic_approval_fixture.approved_notional_cap),
        )
        maximum_cash = None
        maximum_cost_reserve = None
        maximum_sellable = sellable

    provisional_identity = replace(
        case.constraint_identity,
        as_of=case.initial_ledger_snapshot.head_observed_at,
        declared_content_hash=_hash("0" * 64),
    )
    provisional_constraint = bind_stage5_artifact(
        Stage5SubmissionReductionConstraint(
            identity=provisional_identity,
            case_id=case.case_id,
            strategy_id=case.market_execution_case.strategy_id,
            security_id=case.market_execution_case.security_id,
            account_fixture_id=case.market_execution_case.account_fixture_id,
            action_intent=case.market_execution_case.action_intent,
            as_of=case.initial_ledger_snapshot.head_observed_at,
            effective_approved_quantity=approval.approved_quantity,
            maximum_quantity=maximum_quantity,
            maximum_gross_notional=(
                _decimal_text(maximum_gross) if maximum_gross is not None else None
            ),
            maximum_cash_outflow=(
                _decimal_text(maximum_cash) if maximum_cash is not None else None
            ),
            maximum_transaction_cost_reserve=(
                _decimal_text(maximum_cost_reserve) if maximum_cost_reserve is not None else None
            ),
            maximum_sellable_quantity=maximum_sellable,
            candidate_hash=_hash("0" * 64),
            candidate_session_id=None,
            candidate_observation_id=None,
            candidate_at=None,
            candidate_market_rule_hash=None,
            candidate_cost_schedule_hash=None,
            candidate_impact_curve_hash=None,
            target_hash=target.identity.declared_content_hash,
            portfolio_approval_hash=approval.identity.declared_content_hash,
            market_approval_hash=case.market_execution_case.synthetic_approval_fixture.identity.declared_content_hash,
            source_account_snapshot_hash=case.synthetic_account_snapshot.identity.declared_content_hash,
            source_initial_ledger_hash=case.initial_ledger_snapshot.identity.declared_content_hash,
            source_risk_cluster_hash=case.risk_cluster_snapshot.identity.declared_content_hash,
            source_market_regime_hash=case.market_regime_snapshot.identity.declared_content_hash,
            expected_ledger_head_hash=case.initial_ledger_snapshot.expected_head_hash,
            reason_codes=("STAGE5C_RISK_CASH_SELLABLE_REDUCTION_ONLY",),
        )
    )
    candidate = plan_stage5_market_candidate(
        case.market_execution_case,
        market_rules,
        provisional_constraint,
    )
    preview = candidate.market_execution_preview
    candidate_at = candidate.candidate_at
    if candidate_at is None:
        layers = _layers(
            target.target_quantity,
            approval.approved_quantity,
            opening,
            case.market_execution_case.security_id,
            reason="NO_EXECUTABLE_MARKET_CANDIDATE",
        )
        return _result(
            case,
            portfolio_rules,
            status=preview.status,
            reason_codes=preview.reason_codes,
            risk=risk,
            candidate=candidate,
            ledger=opening,
            layers=layers,
        )
    if candidate_at > approval.expires_at:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.CANCELLED,
            reason_codes=("PORTFOLIO_APPROVAL_EXPIRED_BEFORE_CANDIDATE",),
            risk=risk,
            candidate=candidate,
            ledger=opening,
        )
    selected_observation = next(
        (
            item
            for item in case.market_execution_case.market_observation_set.observations
            if item.observation_id == candidate.candidate_observation_id
        ),
        None,
    )
    if (
        selected_observation is None
        or candidate_at > case.injected_clock
        or selected_observation.available_at > case.injected_clock
    ):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("MARKET_CANDIDATE_NOT_AVAILABLE_AT_INJECTED_CLOCK",),
            risk=risk,
            candidate=candidate,
            ledger=opening,
        )
    if any(
        identity.as_of > candidate_at or identity.knowledge_cutoff > candidate_at
        for identity in (
            case.initial_ledger_snapshot.identity,
            case.corporate_action_set.identity,
            case.constraint_identity,
        )
    ):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("STAGE5C_CANDIDATE_INPUT_NOT_PIT_AVAILABLE",),
            risk=risk,
            candidate=candidate,
            ledger=opening,
        )
    if case.initial_ledger_snapshot.head_observed_at != candidate_at:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("CURRENT_LEDGER_HEAD_NOT_AT_MARKET_CANDIDATE",),
            risk=risk,
            candidate=candidate,
            ledger=opening,
        )
    constraint = bind_stage5_submission_constraint_candidate(
        provisional_constraint,
        candidate,
    )
    constrained = evaluate_stage5_market_execution_constrained(
        case.market_execution_case,
        market_rules,
        constraint,
    )
    if constrained.replay_hash.value != stage5_constrained_market_execution_replay_sha256(
        case.market_execution_case,
        constrained.market_candidate,
        constraint,
        constrained.market_execution_result,
    ):
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.PRECHECK_BLOCKED,
            reason_codes=("CONSTRAINED_MARKET_REPLAY_MISMATCH",),
            risk=risk,
            candidate=candidate,
            constraint=constraint,
        )
    constrained_result = constrained.market_execution_result
    if constrained_result.fill is None:
        layers = _layers(
            target.target_quantity,
            approval.approved_quantity,
            opening,
            case.market_execution_case.security_id,
            reason="CONSTRAINT_REDUCED_SUBMISSION_TO_ZERO",
        )
        return _result(
            case,
            portfolio_rules,
            status=constrained_result.status,
            reason_codes=constrained_result.reason_codes,
            risk=risk,
            candidate=candidate,
            constraint=constraint,
            constrained=constrained,
            ledger=opening,
            layers=layers,
        )
    attempt = next(
        item
        for item in constrained_result.attempts
        if item.observation_id == constrained_result.fill.observation_id
    )
    matching_terms = tuple(
        item
        for item in case.settlement_terms
        if item.trade_local_date == attempt.local_trade_date
        and item.market_rule_hash == attempt.market_rule_hash
    )
    if len(matching_terms) != 1:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.ABSTAIN,
            reason_codes=("EXACT_SETTLEMENT_TERMS_MISSING_OR_AMBIGUOUS",),
            risk=risk,
            candidate=candidate,
            constraint=constraint,
            constrained=constrained,
            ledger=opening,
        )
    try:
        fill_projection = project_stage5_fill_to_ledger(
            case.market_execution_case,
            constrained,
            case.synthetic_account_snapshot,
            case.initial_ledger_snapshot,
            matching_terms[0],
            case.portfolio_sizing_inputs,
            portfolio_rules,
        )
    except Stage5FillProjectionError as error:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.RECONCILIATION_BLOCKED,
            reason_codes=(error.code,),
            risk=risk,
            candidate=candidate,
            constraint=constraint,
            constrained=constrained,
            ledger=opening,
        )
    ledger = replay_stage5c_ledger(
        tuple(
            event for event in fill_projection.events if event.effective_at <= case.injected_clock
        )
    )
    if ledger.status is not LedgerReplayStatus.RECONCILED or ledger.derived_state is None:
        return _result(
            case,
            portfolio_rules,
            status=Stage5ExecutionStatus.RECONCILIATION_BLOCKED,
            reason_codes=ledger.reason_codes,
            risk=risk,
            candidate=candidate,
            constraint=constraint,
            constrained=constrained,
            fill_projection=fill_projection,
            ledger=ledger,
        )
    order = constrained_result.order_intent
    fill = constrained_result.fill
    assert order is not None and fill is not None
    layers = _layers(
        target.target_quantity,
        approval.approved_quantity,
        ledger,
        case.market_execution_case.security_id,
        submitted=order.quantity,
        filled=fill.quantity,
        unsubmitted=approval.approved_quantity - order.quantity,
        reason="FIVE_POSITION_LAYERS_RECONCILED",
    )
    return _result(
        case,
        portfolio_rules,
        status=constrained_result.status,
        reason_codes=("STAGE5C_SYNTHETIC_PORTFOLIO_LEDGER_RECONCILED",),
        risk=risk,
        candidate=candidate,
        constraint=constraint,
        constrained=constrained,
        fill_projection=fill_projection,
        ledger=ledger,
        layers=layers,
    )
