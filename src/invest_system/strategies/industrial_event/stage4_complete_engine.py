"""Approved complete Stage 4 synthetic research-validation orchestration.

The engine composes the four independently approved Stage 4 evaluators from
their raw typed cases.  It performs no I/O, accepts no caller-supplied partial
results, issues no KB authority, and grants no trading capability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import (
    CanonicalModel,
    DecisionState,
    ExpectationClass,
    GateOutcome,
    HashDigest,
    PositionState,
    RuleStatus,
    RunMode,
)

from .stage4_context_industry import (
    STAGE4_4A1_RULE_APPROVAL_ID,
    STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A1_RULE_BUNDLE_ID,
    STAGE4_4A1_RULE_BUNDLE_SHA256,
    STAGE4_4A1_RULE_BUNDLE_VERSION,
    STAGE4_4A1_RULES_SHA256,
    ApprovedStage4ContextIndustryRules,
    Stage4ContextIndustryCase,
    Stage4ContextIndustryResult,
    Stage4RuleEvaluationState,
    evaluate_stage4_context_industry,
)
from .stage4_event_semantics import (
    STAGE4_4A2_RULE_APPROVAL_ID,
    STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A2_RULE_BUNDLE_ID,
    STAGE4_4A2_RULE_BUNDLE_SHA256,
    STAGE4_4A2_RULE_BUNDLE_VERSION,
    STAGE4_4A2_RULES_SHA256,
    ApprovedStage4EventRules,
    PartyLinkApplicability,
    PartyRole,
    Stage4EventCase,
    Stage4EventResult,
    evaluate_stage4_event,
)
from .stage4_expectation_valuation_exit import (
    STAGE4_4A4_RULE_APPROVAL_ID,
    STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A4_RULE_BUNDLE_ID,
    STAGE4_4A4_RULE_BUNDLE_SHA256,
    STAGE4_4A4_RULE_BUNDLE_VERSION,
    STAGE4_4A4_RULES_SHA256,
    ApprovedStage4ExpectationValuationExitRules,
    EconomicBasis,
    ExitDisposition,
    ExpectationSnapshot,
    MarketPricingState,
    PreE4MarketContext,
    ProofPlan,
    Stage4A4GateAssessment,
    Stage4ExitInput,
    Stage4ExpectationValuationExitCase,
    Stage4ExpectationValuationExitResult,
    Stage4ValuationSet,
    SyntheticResearchPriceAssumption,
    evaluate_stage4_expectation_valuation_exit,
)
from .stage4_gate_profit_scenarios import (
    STAGE4_4A3_RULE_APPROVAL_ID,
    STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A3_RULE_BUNDLE_ID,
    STAGE4_4A3_RULE_BUNDLE_SHA256,
    STAGE4_4A3_RULE_BUNDLE_VERSION,
    STAGE4_4A3_RULES_SHA256,
    ApprovedStage4GateRules,
    CounterfactualProfitBridge,
    DecimalInterval,
    ProfitTrack,
    ScenarioSet,
    Stage4GateCase,
    Stage4GateResult,
    Stage4GateRuleAssessment,
    evaluate_stage4_gates,
)
from .stage4_governance import (
    STAGE4_APPROVAL_SCOPE,
    STAGE4_COMPLETE_INVENTORY_SHA256,
    STAGE4_COMPLETE_RULE_APPROVAL_ID,
    STAGE4_COMPLETE_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_COMPLETE_RULE_BUNDLE_ID,
    STAGE4_COMPLETE_RULE_BUNDLE_SHA256,
    STAGE4_COMPLETE_RULE_BUNDLE_VERSION,
    STAGE4_COMPLETE_RULES_SHA256,
    STAGE4_STRATEGY_ID,
    Stage4RuleInventory,
)


def _hash(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _freeze_reason_codes(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError("reason_codes must be a non-empty tuple")
    result = tuple(_require_text("reason_code", value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError("reason_codes must not contain duplicates")
    return result


class CompleteStage4EvaluationState(StrEnum):
    COMPLETED = "completed"
    BLOCKED_BEFORE_EVALUATION = "blocked_before_evaluation"
    BLOCKED_DURING_COMPOSITION = "blocked_during_composition"


@dataclass(frozen=True, slots=True)
class Stage4CapabilityIdentity(CanonicalModel):
    batch_id: str
    bundle_id: str
    bundle_version: str
    bundle_hash: HashDigest
    rules_hash: HashDigest
    approval_id: str
    approval_record_hash: HashDigest

    def __post_init__(self) -> None:
        for field_name in ("batch_id", "bundle_id", "bundle_version"):
            _require_text(field_name, getattr(self, field_name))
        _require_text("approval_id", self.approval_id)
        for field_name in ("bundle_hash", "rules_hash", "approval_record_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")


def _expected_local_capability_identities() -> tuple[Stage4CapabilityIdentity, ...]:
    return (
        Stage4CapabilityIdentity(
            batch_id="4A-1",
            bundle_id=STAGE4_4A1_RULE_BUNDLE_ID,
            bundle_version=STAGE4_4A1_RULE_BUNDLE_VERSION,
            bundle_hash=_hash(STAGE4_4A1_RULE_BUNDLE_SHA256),
            rules_hash=_hash(STAGE4_4A1_RULES_SHA256),
            approval_id=STAGE4_4A1_RULE_APPROVAL_ID,
            approval_record_hash=_hash(STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256),
        ),
        Stage4CapabilityIdentity(
            batch_id="4A-2",
            bundle_id=STAGE4_4A2_RULE_BUNDLE_ID,
            bundle_version=STAGE4_4A2_RULE_BUNDLE_VERSION,
            bundle_hash=_hash(STAGE4_4A2_RULE_BUNDLE_SHA256),
            rules_hash=_hash(STAGE4_4A2_RULES_SHA256),
            approval_id=STAGE4_4A2_RULE_APPROVAL_ID,
            approval_record_hash=_hash(STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256),
        ),
        Stage4CapabilityIdentity(
            batch_id="4A-3",
            bundle_id=STAGE4_4A3_RULE_BUNDLE_ID,
            bundle_version=STAGE4_4A3_RULE_BUNDLE_VERSION,
            bundle_hash=_hash(STAGE4_4A3_RULE_BUNDLE_SHA256),
            rules_hash=_hash(STAGE4_4A3_RULES_SHA256),
            approval_id=STAGE4_4A3_RULE_APPROVAL_ID,
            approval_record_hash=_hash(STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256),
        ),
        Stage4CapabilityIdentity(
            batch_id="4A-4",
            bundle_id=STAGE4_4A4_RULE_BUNDLE_ID,
            bundle_version=STAGE4_4A4_RULE_BUNDLE_VERSION,
            bundle_hash=_hash(STAGE4_4A4_RULE_BUNDLE_SHA256),
            rules_hash=_hash(STAGE4_4A4_RULES_SHA256),
            approval_id=STAGE4_4A4_RULE_APPROVAL_ID,
            approval_record_hash=_hash(STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256),
        ),
    )


def _expected_complete_capability_identity() -> Stage4CapabilityIdentity:
    return Stage4CapabilityIdentity(
        batch_id="4B",
        bundle_id=STAGE4_COMPLETE_RULE_BUNDLE_ID,
        bundle_version=STAGE4_COMPLETE_RULE_BUNDLE_VERSION,
        bundle_hash=_hash(STAGE4_COMPLETE_RULE_BUNDLE_SHA256),
        rules_hash=_hash(STAGE4_COMPLETE_RULES_SHA256),
        approval_id=STAGE4_COMPLETE_RULE_APPROVAL_ID,
        approval_record_hash=_hash(STAGE4_COMPLETE_RULE_APPROVAL_RECORD_SHA256),
    )


@dataclass(frozen=True, slots=True)
class Stage4LocalResultHash(CanonicalModel):
    batch_id: str
    result_hash: HashDigest

    def __post_init__(self) -> None:
        _require_text("batch_id", self.batch_id)
        if not isinstance(self.result_hash, HashDigest):
            raise TypeError("result_hash must be HashDigest")


@dataclass(frozen=True, slots=True)
class UnifiedStage4Assessment(CanonicalModel):
    rule_id: str
    source_batch_id: str
    evaluation_state: Stage4RuleEvaluationState
    outcome: GateOutcome | None
    reason_codes: tuple[str, ...]
    source_rule_hash: HashDigest

    def __post_init__(self) -> None:
        _require_text("rule_id", self.rule_id)
        _require_text("source_batch_id", self.source_batch_id)
        if not isinstance(self.evaluation_state, Stage4RuleEvaluationState):
            raise TypeError("evaluation_state must be Stage4RuleEvaluationState")
        if self.outcome is not None and not isinstance(self.outcome, GateOutcome):
            raise TypeError("outcome must be GateOutcome or None")
        object.__setattr__(self, "reason_codes", _freeze_reason_codes(self.reason_codes))
        if not isinstance(self.source_rule_hash, HashDigest):
            raise TypeError("source_rule_hash must be HashDigest")
        if self.evaluation_state is Stage4RuleEvaluationState.EVALUATED:
            if self.outcome is None:
                raise ValueError("evaluated assessment requires outcome")
        elif self.outcome is not None:
            raise ValueError("not_evaluated assessment cannot carry outcome")


@dataclass(frozen=True, slots=True)
class UnifiedStage4GateView(CanonicalModel):
    gate_1: UnifiedStage4Assessment
    scenario_validation: UnifiedStage4Assessment
    gate_2: UnifiedStage4Assessment
    gate_3: UnifiedStage4Assessment
    gate_4: UnifiedStage4Assessment

    def __post_init__(self) -> None:
        if any(
            not isinstance(getattr(self, field_name), UnifiedStage4Assessment)
            for field_name in ("gate_1", "scenario_validation", "gate_2", "gate_3", "gate_4")
        ):
            raise TypeError("all unified gate fields must be UnifiedStage4Assessment")


@dataclass(frozen=True, slots=True)
class Stage4CompleteSyntheticCase(CanonicalModel):
    case_id: str
    company_id: str
    industry_node_id: str
    logical_event_id: str
    knowledge_cutoff: datetime
    e4_first_public_at: datetime
    context_case: Stage4ContextIndustryCase
    event_case: Stage4EventCase
    base_counterfactual_bridge: CounterfactualProfitBridge
    downside_counterfactual_bridge: CounterfactualProfitBridge
    scenario_set: ScenarioSet
    e4_basis: EconomicBasis
    e4_binding_obligation_interval: DecimalInterval
    e4_incremental_profit_interval: DecimalInterval
    e4_incremental_fcf_interval: DecimalInterval
    expectation_snapshot: ExpectationSnapshot
    pre_e4_market_context: PreE4MarketContext
    valuation_set: Stage4ValuationSet
    price_assumption: SyntheticResearchPriceAssumption
    proof_plan: ProofPlan
    exit_input: Stage4ExitInput
    run_mode: RunMode = RunMode.RESEARCH
    anonymous_synthetic_fixture: bool = True
    validation_only: bool = True
    not_a_published_release: bool = True
    reads_kb_internal_state: bool = False
    carries_kb_current_status_authority: bool = False

    def __post_init__(self) -> None:
        for field_name in ("case_id", "company_id", "industry_node_id", "logical_event_id"):
            _require_text(field_name, getattr(self, field_name))
        for field_name in ("knowledge_cutoff", "e4_first_public_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        expected_types = (
            ("context_case", Stage4ContextIndustryCase),
            ("event_case", Stage4EventCase),
            ("base_counterfactual_bridge", CounterfactualProfitBridge),
            ("downside_counterfactual_bridge", CounterfactualProfitBridge),
            ("scenario_set", ScenarioSet),
            ("e4_basis", EconomicBasis),
            ("e4_binding_obligation_interval", DecimalInterval),
            ("e4_incremental_profit_interval", DecimalInterval),
            ("e4_incremental_fcf_interval", DecimalInterval),
            ("expectation_snapshot", ExpectationSnapshot),
            ("pre_e4_market_context", PreE4MarketContext),
            ("valuation_set", Stage4ValuationSet),
            ("price_assumption", SyntheticResearchPriceAssumption),
            ("proof_plan", ProofPlan),
            ("exit_input", Stage4ExitInput),
        )
        for field_name, expected_type in expected_types:
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} must be {expected_type.__name__}")
        if not isinstance(self.run_mode, RunMode):
            raise TypeError("run_mode must be RunMode")
        for field_name in (
            "anonymous_synthetic_fixture",
            "validation_only",
            "not_a_published_release",
            "reads_kb_internal_state",
            "carries_kb_current_status_authority",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be boolean")

    def input_hash(self) -> HashDigest:
        return _hash(canonical_sha256(self))


class Stage4CompleteCompatibilityError(ValueError):
    """Stable rejection for a forged or drifted complete Stage 4 capability."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


_COMPLETE_RULE_ISSUER = object()
_COMPLETE_CAPABILITY_SET_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4CompleteRules:
    bundle_hash: HashDigest
    rules_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    inventory_hash: HashDigest

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        rules_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        inventory_hash: HashDigest,
    ) -> None:
        if _issuer is not _COMPLETE_RULE_ISSUER:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_ISSUER_INVALID",
                "complete rules require the exact owner-approved 4B capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "rules_hash", rules_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(self, "inventory_hash", inventory_hash)

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
        inventory: Stage4RuleInventory,
    ) -> ApprovedStage4CompleteRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be ApprovedRuleCapability")
        if not isinstance(inventory, Stage4RuleInventory):
            raise TypeError("inventory must be Stage4RuleInventory")
        inventory.require_complete()
        identity = (
            STAGE4_STRATEGY_ID,
            STAGE4_COMPLETE_RULE_BUNDLE_ID,
            STAGE4_COMPLETE_RULE_BUNDLE_VERSION,
        )
        if (document.strategy_id, document.bundle_id, document.bundle_version) != identity or (
            capability.strategy_id,
            capability.bundle_id,
            capability.bundle_version,
        ) != identity:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_IDENTITY_UNSUPPORTED",
                "complete rule identity differs from the approved 4B bundle",
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_DOCUMENT_NOT_APPROVED",
                "complete rule document must declare approved",
            )
        if capability.approval_scope is not STAGE4_APPROVAL_SCOPE:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_SCOPE_UNSUPPORTED",
                "only Stage 4 synthetic research validation is approved",
            )
        if capability.bundle_hash != document.bundle_hash() or (
            document.bundle_hash().value != STAGE4_COMPLETE_RULE_BUNDLE_SHA256
        ):
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_HASH_UNSUPPORTED",
                "complete capability must bind the pinned 4B bundle",
            )
        if capability.approval_id != STAGE4_COMPLETE_RULE_APPROVAL_ID or (
            capability.approval_record_hash.value != STAGE4_COMPLETE_RULE_APPROVAL_RECORD_SHA256
        ):
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_RULE_APPROVAL_UNSUPPORTED",
                "complete capability must bind the exact owner approval",
            )
        if canonical_sha256(document.rules) != STAGE4_COMPLETE_RULES_SHA256:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_MACHINE_SEMANTICS_UNSUPPORTED",
                "complete machine semantics differ from the approved version",
            )
        inventory_hash = inventory.inventory_hash()
        if inventory_hash.value != STAGE4_COMPLETE_INVENTORY_SHA256:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_INVENTORY_UNSUPPORTED",
                "complete capability requires the exact all-approved inventory",
            )
        integration = document.rules.get("complete_engine_integration")
        if not isinstance(integration, Mapping) or integration.get("batch_id") != "4B":
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_INTEGRATION_CONTRACT_INVALID",
                "approved 4B integration contract is missing",
            )
        return cls(
            _issuer=_COMPLETE_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            rules_hash=_hash(STAGE4_COMPLETE_RULES_SHA256),
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            inventory_hash=inventory_hash,
        )


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4CompleteCapabilities:
    complete: ApprovedStage4CompleteRules
    context_industry: ApprovedStage4ContextIndustryRules
    event: ApprovedStage4EventRules
    gate_profit_scenarios: ApprovedStage4GateRules
    expectation_valuation_exit: ApprovedStage4ExpectationValuationExitRules
    local_identities: tuple[Stage4CapabilityIdentity, ...]

    def __init__(
        self,
        *,
        _issuer: object,
        complete: ApprovedStage4CompleteRules,
        context_industry: ApprovedStage4ContextIndustryRules,
        event: ApprovedStage4EventRules,
        gate_profit_scenarios: ApprovedStage4GateRules,
        expectation_valuation_exit: ApprovedStage4ExpectationValuationExitRules,
        local_identities: tuple[Stage4CapabilityIdentity, ...],
    ) -> None:
        if _issuer is not _COMPLETE_CAPABILITY_SET_ISSUER:
            raise Stage4CompleteCompatibilityError(
                "STAGE4_COMPLETE_CAPABILITY_SET_ISSUER_INVALID",
                "the complete engine requires all five exact approved capabilities",
            )
        object.__setattr__(self, "complete", complete)
        object.__setattr__(self, "context_industry", context_industry)
        object.__setattr__(self, "event", event)
        object.__setattr__(self, "gate_profit_scenarios", gate_profit_scenarios)
        object.__setattr__(self, "expectation_valuation_exit", expectation_valuation_exit)
        object.__setattr__(self, "local_identities", local_identities)

    @classmethod
    def compose(
        cls,
        *,
        complete: ApprovedStage4CompleteRules,
        context_industry: ApprovedStage4ContextIndustryRules,
        event: ApprovedStage4EventRules,
        gate_profit_scenarios: ApprovedStage4GateRules,
        expectation_valuation_exit: ApprovedStage4ExpectationValuationExitRules,
    ) -> ApprovedStage4CompleteCapabilities:
        expected_types = (
            (complete, ApprovedStage4CompleteRules),
            (context_industry, ApprovedStage4ContextIndustryRules),
            (event, ApprovedStage4EventRules),
            (gate_profit_scenarios, ApprovedStage4GateRules),
            (expectation_valuation_exit, ApprovedStage4ExpectationValuationExitRules),
        )
        if any(not isinstance(value, expected) for value, expected in expected_types):
            raise TypeError("complete capability set contains an unsupported typed capability")
        expected_local = (
            (
                "4A-1",
                context_industry,
                STAGE4_4A1_RULE_BUNDLE_ID,
                STAGE4_4A1_RULE_BUNDLE_VERSION,
                STAGE4_4A1_RULE_BUNDLE_SHA256,
                STAGE4_4A1_RULES_SHA256,
                STAGE4_4A1_RULE_APPROVAL_ID,
                STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256,
            ),
            (
                "4A-2",
                event,
                STAGE4_4A2_RULE_BUNDLE_ID,
                STAGE4_4A2_RULE_BUNDLE_VERSION,
                STAGE4_4A2_RULE_BUNDLE_SHA256,
                STAGE4_4A2_RULES_SHA256,
                STAGE4_4A2_RULE_APPROVAL_ID,
                STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256,
            ),
            (
                "4A-3",
                gate_profit_scenarios,
                STAGE4_4A3_RULE_BUNDLE_ID,
                STAGE4_4A3_RULE_BUNDLE_VERSION,
                STAGE4_4A3_RULE_BUNDLE_SHA256,
                STAGE4_4A3_RULES_SHA256,
                STAGE4_4A3_RULE_APPROVAL_ID,
                STAGE4_4A3_RULE_APPROVAL_RECORD_SHA256,
            ),
            (
                "4A-4",
                expectation_valuation_exit,
                STAGE4_4A4_RULE_BUNDLE_ID,
                STAGE4_4A4_RULE_BUNDLE_VERSION,
                STAGE4_4A4_RULE_BUNDLE_SHA256,
                STAGE4_4A4_RULES_SHA256,
                STAGE4_4A4_RULE_APPROVAL_ID,
                STAGE4_4A4_RULE_APPROVAL_RECORD_SHA256,
            ),
        )
        identities: list[Stage4CapabilityIdentity] = []
        for (
            batch_id,
            rules,
            bundle_id,
            bundle_version,
            bundle_hash,
            rules_hash,
            approval_id,
            approval_hash,
        ) in expected_local:
            if (
                rules.bundle_hash.value != bundle_hash
                or rules.approval_id != approval_id
                or rules.approval_record_hash.value != approval_hash
            ):
                raise Stage4CompleteCompatibilityError(
                    "STAGE4_COMPLETE_LOCAL_CAPABILITY_DRIFT",
                    f"{batch_id} capability differs from the exact approved dependency",
                )
            identities.append(
                Stage4CapabilityIdentity(
                    batch_id=batch_id,
                    bundle_id=bundle_id,
                    bundle_version=bundle_version,
                    bundle_hash=rules.bundle_hash,
                    rules_hash=_hash(rules_hash),
                    approval_id=rules.approval_id,
                    approval_record_hash=rules.approval_record_hash,
                )
            )
        return cls(
            _issuer=_COMPLETE_CAPABILITY_SET_ISSUER,
            complete=complete,
            context_industry=context_industry,
            event=event,
            gate_profit_scenarios=gate_profit_scenarios,
            expectation_valuation_exit=expectation_valuation_exit,
            local_identities=tuple(identities),
        )


@dataclass(frozen=True, slots=True)
class Stage4CompleteResult(CanonicalModel):
    case_id: str
    evaluation_state: CompleteStage4EvaluationState
    input_hash: HashDigest
    local_capabilities: tuple[Stage4CapabilityIdentity, ...]
    context_result: Stage4ContextIndustryResult | None
    event_result: Stage4EventResult | None
    gate_profit_result: Stage4GateResult | None
    expectation_valuation_exit_result: Stage4ExpectationValuationExitResult | None
    local_result_hashes: tuple[Stage4LocalResultHash, ...]
    unified_gate_view: UnifiedStage4GateView
    overall_outcome: GateOutcome
    research_decision_label: DecisionState
    reason_codes: tuple[str, ...]
    profit_track: ProfitTrack | None
    public_expectation_class: ExpectationClass | None
    market_pricing_state: MarketPricingState | None
    net_base_remaining_return: str | None
    reward_to_downside: str | None
    exit_disposition: ExitDisposition | None
    complete_capability: Stage4CapabilityIdentity
    stage4_inventory_hash: HashDigest
    replay_hash: HashDigest
    approval_scope: RuleApprovalScope = field(default=STAGE4_APPROVAL_SCOPE, init=False)
    complete_stage4_synthetic_capability: bool = field(default=True, init=False)
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    kb_current_status_authority: bool = field(default=False, init=False)
    formal_strategy_run_manifest: None = field(default=None, init=False)
    position_state: PositionState = field(default=PositionState.FLAT, init=False)
    target_weight: None = field(default=None, init=False)
    approved_weight: None = field(default=None, init=False)
    actual_weight: None = field(default=None, init=False)
    approver: None = field(default=None, init=False)
    order_intent: None = field(default=None, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_portfolio: bool = field(default=False, init=False)
    authorizes_execution: bool = field(default=False, init=False)
    authorizes_pnl: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_text("case_id", self.case_id)
        if not isinstance(self.evaluation_state, CompleteStage4EvaluationState):
            raise TypeError("evaluation_state must be CompleteStage4EvaluationState")
        for field_name in (
            "input_hash",
            "stage4_inventory_hash",
            "replay_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        if not isinstance(self.complete_capability, Stage4CapabilityIdentity):
            raise TypeError("complete_capability must be Stage4CapabilityIdentity")
        if self.complete_capability != _expected_complete_capability_identity():
            raise ValueError("complete_capability must identify the exact approved 4B capability")
        if self.stage4_inventory_hash.value != STAGE4_COMPLETE_INVENTORY_SHA256:
            raise ValueError("stage4_inventory_hash must identify the exact approved inventory")
        object.__setattr__(self, "reason_codes", _freeze_reason_codes(self.reason_codes))
        if not isinstance(self.unified_gate_view, UnifiedStage4GateView):
            raise TypeError("unified_gate_view must be UnifiedStage4GateView")
        for field_name, expected_type in (
            ("context_result", Stage4ContextIndustryResult),
            ("event_result", Stage4EventResult),
            ("gate_profit_result", Stage4GateResult),
            ("expectation_valuation_exit_result", Stage4ExpectationValuationExitResult),
        ):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"{field_name} must be {expected_type.__name__} or None")
        if len(self.local_capabilities) != 4 or any(
            not isinstance(item, Stage4CapabilityIdentity) for item in self.local_capabilities
        ):
            raise ValueError("local_capabilities must contain exactly four identities")
        if self.local_capabilities != _expected_local_capability_identities():
            raise ValueError("local_capabilities must contain the exact approved dependencies")
        if any(not isinstance(item, Stage4LocalResultHash) for item in self.local_result_hashes):
            raise TypeError("local_result_hashes must contain Stage4LocalResultHash values")
        if self.local_result_hashes != _result_hashes(
            self.context_result,
            self.event_result,
            self.gate_profit_result,
            self.expectation_valuation_exit_result,
        ):
            raise ValueError("local_result_hashes differ from the immutable local results")
        result_presence = (
            self.context_result is not None,
            self.event_result is not None,
            self.gate_profit_result is not None,
            self.expectation_valuation_exit_result is not None,
        )
        expected_presence = {
            CompleteStage4EvaluationState.BLOCKED_BEFORE_EVALUATION: (
                False,
                False,
                False,
                False,
            ),
            CompleteStage4EvaluationState.BLOCKED_DURING_COMPOSITION: (
                True,
                True,
                True,
                False,
            ),
            CompleteStage4EvaluationState.COMPLETED: (True, True, True, True),
        }[self.evaluation_state]
        if result_presence != expected_presence:
            raise ValueError("local result presence differs from the evaluation state")
        expected_outcome = (
            _aggregate_gate_outcome(self.unified_gate_view)
            if self.evaluation_state is CompleteStage4EvaluationState.COMPLETED
            else GateOutcome.BLOCKED
        )
        if self.overall_outcome is not expected_outcome:
            raise ValueError("overall_outcome differs from the deterministic gate aggregation")
        if self.research_decision_label is not _decision(expected_outcome):
            raise ValueError("research_decision_label differs from the aggregate outcome")
        a4_gate = (
            self.expectation_valuation_exit_result.gate_result
            if self.expectation_valuation_exit_result is not None
            else None
        )
        exit_result = (
            self.expectation_valuation_exit_result.exit_result
            if self.expectation_valuation_exit_result is not None
            else None
        )
        derived_values = (
            self.gate_profit_result.profit_track if self.gate_profit_result is not None else None,
            a4_gate.public_expectation_class if a4_gate is not None else None,
            a4_gate.market_pricing_state if a4_gate is not None else None,
            a4_gate.net_base_remaining_return if a4_gate is not None else None,
            a4_gate.reward_to_downside if a4_gate is not None else None,
            exit_result.disposition if exit_result is not None else None,
        )
        if derived_values != (
            self.profit_track,
            self.public_expectation_class,
            self.market_pricing_state,
            self.net_base_remaining_return,
            self.reward_to_downside,
            self.exit_disposition,
        ):
            raise ValueError("summary fields differ from the immutable local results")


def complete_stage4_replay_sha256(value: Stage4CompleteResult) -> str:
    if not isinstance(value, Stage4CompleteResult):
        raise TypeError("value must be Stage4CompleteResult")
    projected = value.to_json_value()
    del projected["replay_hash"]
    return canonical_sha256(projected)


def _not_evaluated(
    rule_id: str,
    source_batch_id: str,
    source_rule_hash: str,
    reason: str,
) -> UnifiedStage4Assessment:
    return UnifiedStage4Assessment(
        rule_id=rule_id,
        source_batch_id=source_batch_id,
        evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
        outcome=None,
        reason_codes=(reason,),
        source_rule_hash=_hash(source_rule_hash),
    )


def _preflight_gate_view(reason: str) -> UnifiedStage4GateView:
    return UnifiedStage4GateView(
        gate_1=_not_evaluated("FR-GATE-001", "4A-3", STAGE4_4A3_RULES_SHA256, reason),
        scenario_validation=_not_evaluated(
            "FR-GATE-003",
            "4A-3",
            STAGE4_4A3_RULES_SHA256,
            reason,
        ),
        gate_2=_not_evaluated("FR-GATE-002", "4A-3", STAGE4_4A3_RULES_SHA256, reason),
        gate_3=_not_evaluated("FR-GATE-004", "4A-4", STAGE4_4A4_RULES_SHA256, reason),
        gate_4=_not_evaluated("FR-GATE-005", "4A-4", STAGE4_4A4_RULES_SHA256, reason),
    )


def _preflight_failure(case: Stage4CompleteSyntheticCase) -> str | None:
    if (
        case.run_mode is not RunMode.RESEARCH
        or not case.anonymous_synthetic_fixture
        or not case.validation_only
        or not case.not_a_published_release
        or case.reads_kb_internal_state
        or case.carries_kb_current_status_authority
    ):
        return "STAGE4_COMPLETE_SCOPE_OR_CROSS_REPOSITORY_VIOLATION"
    if (
        not case.price_assumption.synthetic
        or not case.price_assumption.not_first_actual_executable_price
    ):
        return "STAGE4_COMPLETE_REAL_OR_EXECUTABLE_PRICE_FORBIDDEN"
    holding = case.exit_input.holding_snapshot
    if holding is not None and (not holding.synthetic or holding.authorizes_execution):
        return "STAGE4_COMPLETE_REAL_HOLDING_OR_EXECUTION_AUTHORITY_FORBIDDEN"
    if case.context_case.case_id != case.case_id or case.event_case.case_id != case.case_id:
        return "STAGE4_COMPLETE_CASE_ID_MISMATCH"
    context = case.context_case.context
    event = case.event_case
    if context.knowledge_cutoff != case.knowledge_cutoff or event.knowledge_cutoff != (
        case.knowledge_cutoff
    ):
        return "STAGE4_COMPLETE_KNOWLEDGE_CUTOFF_MISMATCH"
    versioned_artifacts = (
        case.expectation_snapshot.identity,
        case.pre_e4_market_context.identity,
        case.valuation_set.identity,
        case.price_assumption.identity,
        case.proof_plan.identity,
    )
    if any(
        identity.knowledge_cutoff != case.knowledge_cutoff for identity in versioned_artifacts
    ) or (holding is not None and holding.identity.knowledge_cutoff != case.knowledge_cutoff):
        return "STAGE4_COMPLETE_KNOWLEDGE_CUTOFF_MISMATCH"
    if case.scenario_set.knowledge_cutoff != case.knowledge_cutoff:
        return "STAGE4_COMPLETE_KNOWLEDGE_CUTOFF_MISMATCH"
    if context.decision_at != event.decision_at:
        return "STAGE4_COMPLETE_DECISION_TIME_MISMATCH"
    if context.input_id != event.input_ref:
        return "STAGE4_COMPLETE_INPUT_VERSION_CHAIN_MISMATCH"
    if (
        case.company_id != context.company_id
        or case.company_id != case.context_case.beneficiary.company_id
    ):
        return "STAGE4_COMPLETE_COMPANY_IDENTITY_MISMATCH"
    if (
        case.industry_node_id != case.context_case.bottleneck.node_id
        or case.industry_node_id != case.context_case.beneficiary.node_id
    ):
        return "STAGE4_COMPLETE_INDUSTRY_NODE_IDENTITY_MISMATCH"
    if (
        case.logical_event_id != event.revision.logical_event_id
        or case.logical_event_id != case.e4_basis.event_identity
    ):
        return "STAGE4_COMPLETE_EVENT_IDENTITY_MISMATCH"
    if case.e4_basis.subject_scope != case.company_id:
        return "STAGE4_COMPLETE_SUBJECT_SCOPE_MISMATCH"
    listed_entities = {
        link.legal_entity_id
        for link in event.party_links
        if link.role is PartyRole.LISTED_COMPANY
        and link.applicability is PartyLinkApplicability.APPLICABLE
        and link.legal_entity_id is not None
    }
    if listed_entities and listed_entities != {case.company_id}:
        return "STAGE4_COMPLETE_LISTED_ENTITY_MISMATCH"
    if (
        case.expectation_snapshot.basis != case.e4_basis
        or case.valuation_set.basis != case.e4_basis
        or case.price_assumption.currency != case.e4_basis.currency
        or case.price_assumption.unit != case.e4_basis.unit
        or case.scenario_set.presentation_currency != case.e4_basis.currency
        or case.scenario_set.contract_currency != case.e4_basis.currency
        or (
            f"{case.scenario_set.ntm_start_date}/"
            f"{case.scenario_set.ntm_end_date_exclusive}" != case.e4_basis.effective_period
        )
    ):
        return "STAGE4_COMPLETE_ECONOMIC_BASIS_MISMATCH"
    if case.e4_first_public_at > case.knowledge_cutoff or (
        case.expectation_snapshot.e4_first_public_at != case.e4_first_public_at
        or case.scenario_set.e4_first_public_at != case.e4_first_public_at
    ):
        return "STAGE4_COMPLETE_E4_PUBLIC_TIME_MISMATCH"
    if holding is not None and holding.case_id != case.case_id:
        return "STAGE4_COMPLETE_CASE_ID_MISMATCH"
    if event.e4_public.authoritative_originals:
        facts = {fact.provider_fact_id: fact for fact in event.knowledge_graph.facts}
        public_times: list[datetime] = []
        for original in event.e4_public.authoritative_originals:
            fact = facts.get(original.fact_id)
            if fact is None or fact.available_at is None:
                return "STAGE4_COMPLETE_E4_ORIGINAL_TIME_UNAVAILABLE"
            public_times.append(fact.available_at)
        if min(public_times) != case.e4_first_public_at:
            return "STAGE4_COMPLETE_E4_PUBLIC_TIME_MISMATCH"
    return None


def _unified_assessment(
    assessment: Stage4GateRuleAssessment | Stage4A4GateAssessment,
    *,
    rule_id: str,
    source_batch_id: str,
    source_rule_hash: str,
) -> UnifiedStage4Assessment:
    evaluation_state = assessment.evaluation_state
    outcome = assessment.outcome
    reason_codes = assessment.reason_codes
    if not isinstance(evaluation_state, Stage4RuleEvaluationState):
        raise TypeError("local assessment evaluation_state differs")
    if outcome is not None and not isinstance(outcome, GateOutcome):
        raise TypeError("local assessment outcome differs")
    if not isinstance(reason_codes, tuple):
        raise TypeError("local assessment reason_codes differs")
    return UnifiedStage4Assessment(
        rule_id=rule_id,
        source_batch_id=source_batch_id,
        evaluation_state=evaluation_state,
        outcome=outcome,
        reason_codes=reason_codes,
        source_rule_hash=_hash(source_rule_hash),
    )


def _gate_view(
    gate_result: Stage4GateResult,
    expectation_result: Stage4ExpectationValuationExitResult | None,
    *,
    later_reason: str = "PRIOR_GATE_NOT_PASS",
) -> UnifiedStage4GateView:
    if expectation_result is None:
        gate_3 = _not_evaluated("FR-GATE-004", "4A-4", STAGE4_4A4_RULES_SHA256, later_reason)
        gate_4 = _not_evaluated("FR-GATE-005", "4A-4", STAGE4_4A4_RULES_SHA256, later_reason)
    else:
        gate_3 = _unified_assessment(
            expectation_result.gate_result.gate_3,
            rule_id="FR-GATE-004",
            source_batch_id="4A-4",
            source_rule_hash=STAGE4_4A4_RULES_SHA256,
        )
        gate_4 = _unified_assessment(
            expectation_result.gate_result.gate_4,
            rule_id="FR-GATE-005",
            source_batch_id="4A-4",
            source_rule_hash=STAGE4_4A4_RULES_SHA256,
        )
    return UnifiedStage4GateView(
        gate_1=_unified_assessment(
            gate_result.gate_1,
            rule_id="FR-GATE-001",
            source_batch_id="4A-3",
            source_rule_hash=STAGE4_4A3_RULES_SHA256,
        ),
        scenario_validation=_unified_assessment(
            gate_result.scenario_validation,
            rule_id="FR-GATE-003",
            source_batch_id="4A-3",
            source_rule_hash=STAGE4_4A3_RULES_SHA256,
        ),
        gate_2=_unified_assessment(
            gate_result.gate_2,
            rule_id="FR-GATE-002",
            source_batch_id="4A-3",
            source_rule_hash=STAGE4_4A3_RULES_SHA256,
        ),
        gate_3=gate_3,
        gate_4=gate_4,
    )


def _aggregate_gate_outcome(view: UnifiedStage4GateView) -> GateOutcome:
    assessments = (
        view.gate_1,
        view.scenario_validation,
        view.gate_2,
        view.gate_3,
        view.gate_4,
    )
    outcomes = tuple(
        assessment.outcome for assessment in assessments if assessment.outcome is not None
    )
    for outcome in (
        GateOutcome.BLOCKED,
        GateOutcome.REJECT,
        GateOutcome.ABSTAIN,
        GateOutcome.SHADOW_ONLY,
    ):
        if outcome in outcomes:
            return outcome
    four_gates = (view.gate_1, view.gate_2, view.gate_3, view.gate_4)
    if all(item.outcome is GateOutcome.PASS for item in four_gates) and (
        view.scenario_validation.outcome is GateOutcome.PASS
    ):
        return GateOutcome.PASS
    return GateOutcome.BLOCKED


def _decision(outcome: GateOutcome) -> DecisionState:
    return {
        GateOutcome.PASS: DecisionState.TRADE_READY,
        GateOutcome.REJECT: DecisionState.REJECT,
        GateOutcome.ABSTAIN: DecisionState.ABSTAIN,
        GateOutcome.BLOCKED: DecisionState.BLOCKED,
        GateOutcome.SHADOW_ONLY: DecisionState.SHADOW_ONLY,
    }[outcome]


def _result_hashes(
    context_result: Stage4ContextIndustryResult | None,
    event_result: Stage4EventResult | None,
    gate_result: Stage4GateResult | None,
    expectation_result: Stage4ExpectationValuationExitResult | None,
) -> tuple[Stage4LocalResultHash, ...]:
    values = (
        ("4A-1", context_result),
        ("4A-2", event_result),
        ("4A-3", gate_result),
        ("4A-4", expectation_result),
    )
    return tuple(
        Stage4LocalResultHash(batch_id=batch_id, result_hash=_hash(canonical_sha256(result)))
        for batch_id, result in values
        if result is not None
    )


def _finalize_result(value: Stage4CompleteResult) -> Stage4CompleteResult:
    replay_hash = _hash(complete_stage4_replay_sha256(value))
    return replace(value, replay_hash=replay_hash)


def _base_result(
    *,
    case: Stage4CompleteSyntheticCase,
    capabilities: ApprovedStage4CompleteCapabilities,
    evaluation_state: CompleteStage4EvaluationState,
    context_result: Stage4ContextIndustryResult | None,
    event_result: Stage4EventResult | None,
    gate_result: Stage4GateResult | None,
    expectation_result: Stage4ExpectationValuationExitResult | None,
    view: UnifiedStage4GateView,
    overall_outcome: GateOutcome,
    reason_codes: tuple[str, ...],
) -> Stage4CompleteResult:
    a4_gate = expectation_result.gate_result if expectation_result is not None else None
    exit_result = expectation_result.exit_result if expectation_result is not None else None
    value = Stage4CompleteResult(
        case_id=case.case_id,
        evaluation_state=evaluation_state,
        input_hash=case.input_hash(),
        local_capabilities=capabilities.local_identities,
        context_result=context_result,
        event_result=event_result,
        gate_profit_result=gate_result,
        expectation_valuation_exit_result=expectation_result,
        local_result_hashes=_result_hashes(
            context_result, event_result, gate_result, expectation_result
        ),
        unified_gate_view=view,
        overall_outcome=overall_outcome,
        research_decision_label=_decision(overall_outcome),
        reason_codes=reason_codes,
        profit_track=(gate_result.profit_track if gate_result is not None else None),
        public_expectation_class=(
            a4_gate.public_expectation_class if a4_gate is not None else None
        ),
        market_pricing_state=(a4_gate.market_pricing_state if a4_gate is not None else None),
        net_base_remaining_return=(
            a4_gate.net_base_remaining_return if a4_gate is not None else None
        ),
        reward_to_downside=(a4_gate.reward_to_downside if a4_gate is not None else None),
        exit_disposition=(exit_result.disposition if exit_result is not None else None),
        complete_capability=Stage4CapabilityIdentity(
            batch_id="4B",
            bundle_id=STAGE4_COMPLETE_RULE_BUNDLE_ID,
            bundle_version=STAGE4_COMPLETE_RULE_BUNDLE_VERSION,
            bundle_hash=capabilities.complete.bundle_hash,
            rules_hash=capabilities.complete.rules_hash,
            approval_id=capabilities.complete.approval_id,
            approval_record_hash=capabilities.complete.approval_record_hash,
        ),
        stage4_inventory_hash=capabilities.complete.inventory_hash,
        replay_hash=_hash("0" * 64),
    )
    return _finalize_result(value)


def evaluate_complete_stage4(
    case: Stage4CompleteSyntheticCase,
    capabilities: ApprovedStage4CompleteCapabilities,
) -> Stage4CompleteResult:
    """Run all four approved Stage 4 batches from raw synthetic inputs."""

    if not isinstance(case, Stage4CompleteSyntheticCase):
        raise TypeError("case must be Stage4CompleteSyntheticCase")
    if not isinstance(capabilities, ApprovedStage4CompleteCapabilities):
        raise TypeError("capabilities must be ApprovedStage4CompleteCapabilities")
    preflight_failure = _preflight_failure(case)
    if preflight_failure is not None:
        return _base_result(
            case=case,
            capabilities=capabilities,
            evaluation_state=CompleteStage4EvaluationState.BLOCKED_BEFORE_EVALUATION,
            context_result=None,
            event_result=None,
            gate_result=None,
            expectation_result=None,
            view=_preflight_gate_view(preflight_failure),
            overall_outcome=GateOutcome.BLOCKED,
            reason_codes=(preflight_failure,),
        )

    context_result = evaluate_stage4_context_industry(
        case.context_case, capabilities.context_industry
    )
    event_result = evaluate_stage4_event(case.event_case, capabilities.event)
    gate_case = Stage4GateCase(
        case_id=case.case_id,
        context_result=context_result,
        event_result=event_result,
        knowledge_graph=case.event_case.knowledge_graph,
        base_counterfactual_bridge=case.base_counterfactual_bridge,
        downside_counterfactual_bridge=case.downside_counterfactual_bridge,
        scenario_set=case.scenario_set,
    )
    gate_result = evaluate_stage4_gates(gate_case, capabilities.gate_profit_scenarios)

    if gate_result.base_incremental_profit is not None and (
        gate_result.base_incremental_profit != case.e4_incremental_profit_interval.lower
    ):
        reason = "STAGE4_COMPLETE_INCREMENTAL_PROFIT_BINDING_MISMATCH"
        return _base_result(
            case=case,
            capabilities=capabilities,
            evaluation_state=CompleteStage4EvaluationState.BLOCKED_DURING_COMPOSITION,
            context_result=context_result,
            event_result=event_result,
            gate_result=gate_result,
            expectation_result=None,
            view=_gate_view(gate_result, None, later_reason=reason),
            overall_outcome=GateOutcome.BLOCKED,
            reason_codes=(reason,),
        )
    if gate_result.base_incremental_fcf is not None and (
        gate_result.base_incremental_fcf != case.e4_incremental_fcf_interval.lower
    ):
        reason = "STAGE4_COMPLETE_INCREMENTAL_FCF_BINDING_MISMATCH"
        return _base_result(
            case=case,
            capabilities=capabilities,
            evaluation_state=CompleteStage4EvaluationState.BLOCKED_DURING_COMPOSITION,
            context_result=context_result,
            event_result=event_result,
            gate_result=gate_result,
            expectation_result=None,
            view=_gate_view(gate_result, None, later_reason=reason),
            overall_outcome=GateOutcome.BLOCKED,
            reason_codes=(reason,),
        )

    expectation_case = Stage4ExpectationValuationExitCase(
        case_id=case.case_id,
        knowledge_cutoff=case.knowledge_cutoff,
        e4_first_public_at=case.e4_first_public_at,
        upstream_gate_result=gate_result,
        e4_basis=case.e4_basis,
        e4_binding_obligation_interval=case.e4_binding_obligation_interval,
        e4_incremental_profit_interval=case.e4_incremental_profit_interval,
        e4_incremental_fcf_interval=case.e4_incremental_fcf_interval,
        expectation_snapshot=case.expectation_snapshot,
        pre_e4_market_context=case.pre_e4_market_context,
        valuation_set=case.valuation_set,
        price_assumption=case.price_assumption,
        proof_plan=case.proof_plan,
        exit_input=case.exit_input,
        anonymous_synthetic_fixture=case.anonymous_synthetic_fixture,
        reads_kb_internal_state=case.reads_kb_internal_state,
    )
    expectation_result = evaluate_stage4_expectation_valuation_exit(
        expectation_case,
        capabilities.expectation_valuation_exit,
    )
    view = _gate_view(gate_result, expectation_result)
    overall_outcome = _aggregate_gate_outcome(view)
    reason_codes = tuple(
        dict.fromkeys(
            reason
            for assessment in (
                view.gate_1,
                view.scenario_validation,
                view.gate_2,
                view.gate_3,
                view.gate_4,
            )
            for reason in assessment.reason_codes
        )
    )
    return _base_result(
        case=case,
        capabilities=capabilities,
        evaluation_state=CompleteStage4EvaluationState.COMPLETED,
        context_result=context_result,
        event_result=event_result,
        gate_result=gate_result,
        expectation_result=expectation_result,
        view=view,
        overall_outcome=overall_outcome,
        reason_codes=reason_codes,
    )
