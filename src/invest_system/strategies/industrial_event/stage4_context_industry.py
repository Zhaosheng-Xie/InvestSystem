"""Approved Stage 4 / 4A-1 context and industry mapping semantics.

The batch is deliberately narrower than the complete Stage 4 capability.  It
accepts only synthetic research-validation inputs, performs no I/O, and emits
no event, gate, valuation, position, or order authority.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import CanonicalModel, GateOutcome, HashDigest, RuleStatus

STAGE4_4A1_RULE_BUNDLE_ID = "industrial_event_stage4_4a1_context_industry"
STAGE4_4A1_RULE_BUNDLE_VERSION = "0.1.0"
STAGE4_4A1_RULE_APPROVAL_ID = "rule_approval_stage4_4a1_context_industry_v0_1_0"
STAGE4_4A1_RULE_BUNDLE_SHA256 = "5224e8e6d600b8f613d6dfaf4dd486d6caafdcf5fe3d8d3db29af2f25462a32d"
STAGE4_4A1_RULES_SHA256 = "2e16e87585bccc1df735e33feed4b72e3160d7bb1c415320bed31ee01c1d264a"
STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256 = (
    "84d47caa4b8226dd4e9c4dee31645214938e7321e25e93f368bf1ecc167b5e1a"
)
STAGE4_4A1_RULE_VERSION = "0.1.0"

STAGE4_4A1_REQUIREMENT_IDS = (
    "FR-CTX-001",
    "FR-CTX-002",
    "FR-IND-001",
    "FR-IND-002",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _freeze_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    result = tuple(_require_id(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result))


def _coerce_enum[EnumT: StrEnum](
    field_name: str,
    enum_type: type[EnumT],
    value: Any,
) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _claim_fact_ids(claims: Iterable[EvidenceClaim]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    supporting = sorted({fact_id for claim in claims for fact_id in claim.supporting_fact_ids})
    conflicting = sorted({fact_id for claim in claims for fact_id in claim.conflicting_fact_ids})
    return tuple(supporting), tuple(conflicting)


def _evidence_group_count(claims: Iterable[EvidenceClaim]) -> int:
    return len({group_id for claim in claims for group_id in claim.independence_group_ids})


class EvidenceConclusion(StrEnum):
    CONFIRMED = "confirmed"
    REFUTED = "refuted"
    UNKNOWN = "unknown"
    CONFLICTED = "conflicted"


class ContextCoverageArea(StrEnum):
    PRODUCT_TECHNOLOGY_TERMS = "product_technology_terms"
    VALUE_CHAIN_RELATIONS = "value_chain_relations"
    DEMAND_PROCUREMENT_DEPLOYMENT = "demand_procurement_deployment"
    COMMERCIALIZATION_CYCLES = "commercialization_cycles"
    CAPACITY_YIELD_LEADTIME_PRICE_COST_INVENTORY = "capacity_yield_leadtime_price_cost_inventory"
    COMPETITION_SWITCHING_NEW_SUPPLY = "competition_switching_new_supply"
    PROFIT_POOL_OWNERSHIP_PATH = "profit_pool_ownership_path"
    HISTORICAL_STAGE_COUNTEREXAMPLES_CONFLICTS = "historical_stage_counterexamples_conflicts"
    SOURCE_TIME_VERSION_CONFIDENCE_REVIEW = "source_time_version_confidence_review"
    COMPANY_IDENTITY_EXCLUSION_REVIEW_TRIGGER = "company_identity_exclusion_review_trigger"


class ContextTemporalBindingKind(StrEnum):
    INDUSTRY_STAGE = "industry_stage"
    COMPANY_LABEL = "company_label"
    SUPPLY_CHAIN_RELATION = "supply_chain_relation"


class ContextDisposition(StrEnum):
    DECISION_POOL = "decision_pool"
    RESEARCH_QUARANTINE = "research_quarantine"


class BeneficiaryTier(StrEnum):
    NONE = "none"
    TECHNICAL_LINK = "technical_link"
    QUALIFIED_SUPPLIER = "qualified_supplier"
    PROFIT_BENEFICIARY = "profit_beneficiary"


class Stage4RuleEvaluationState(StrEnum):
    EVALUATED = "evaluated"
    NOT_EVALUATED = "not_evaluated"


class Stage4ContextIndustryCompatibilityError(ValueError):
    """Stable fail-closed rejection for a non-approved 4A-1 rule capability."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class EvidenceClaim(CanonicalModel):
    """One explicit four-state strategy claim over fixed provider-neutral facts."""

    conclusion: EvidenceConclusion
    supporting_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()
    independence_group_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "conclusion",
            _coerce_enum("conclusion", EvidenceConclusion, self.conclusion),
        )
        for field_name in (
            "supporting_fact_ids",
            "conflicting_fact_ids",
            "independence_group_ids",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_ids(field_name, getattr(self, field_name)),
            )
        if self.conclusion in (EvidenceConclusion.CONFIRMED, EvidenceConclusion.REFUTED):
            if not self.supporting_fact_ids or not self.independence_group_ids:
                raise ValueError("confirmed/refuted claims require facts and evidence groups")
            if self.conflicting_fact_ids:
                raise ValueError("confirmed/refuted claims cannot carry conflicting facts")
        elif self.conclusion is EvidenceConclusion.CONFLICTED:
            if (
                not self.supporting_fact_ids
                or not self.conflicting_fact_ids
                or not self.independence_group_ids
            ):
                raise ValueError("conflicted claims require both fact sides and evidence groups")
        elif self.conflicting_fact_ids:
            raise ValueError("unknown claims cannot claim a resolved conflict side")
        if self.independence_group_ids and not self.supporting_fact_ids:
            raise ValueError("evidence groups require supporting facts")


@dataclass(frozen=True, slots=True)
class ContextCoverage(CanonicalModel):
    area: ContextCoverageArea
    assessment: EvidenceClaim

    def __post_init__(self) -> None:
        object.__setattr__(self, "area", _coerce_enum("area", ContextCoverageArea, self.area))
        if not isinstance(self.assessment, EvidenceClaim):
            raise TypeError("assessment must be an EvidenceClaim")
        if self.assessment.conclusion is EvidenceConclusion.REFUTED:
            raise ValueError("context coverage cannot use refuted; use unknown or conflicted")


@dataclass(frozen=True, slots=True)
class ContextTemporalBinding(CanonicalModel):
    kind: ContextTemporalBindingKind
    semantic_id: str
    assessment: EvidenceClaim
    available_at: datetime | None
    valid_from: datetime | None
    valid_to: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "kind",
            _coerce_enum("kind", ContextTemporalBindingKind, self.kind),
        )
        _require_id("semantic_id", self.semantic_id)
        if not isinstance(self.assessment, EvidenceClaim):
            raise TypeError("assessment must be an EvidenceClaim")
        if self.assessment.conclusion is EvidenceConclusion.REFUTED:
            raise ValueError("temporal binding cannot use refuted; use unknown or conflicted")
        for field_name in ("available_at", "valid_from", "valid_to"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(
                    self,
                    field_name,
                    normalize_utc(value, field_name=field_name),
                )
        if self.valid_to is not None and (
            self.valid_from is None or self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be strictly later than valid_from")


@dataclass(frozen=True, slots=True)
class IndustryContextView(CanonicalModel):
    context_view_id: str
    company_id: str
    context_pack_ref: str
    context_pack_version: str
    input_id: str
    as_of: datetime
    knowledge_cutoff: datetime
    decision_at: datetime
    context_pack_available_at: datetime
    preregistered: bool
    coverage: tuple[ContextCoverage, ...]
    temporal_bindings: tuple[ContextTemporalBinding, ...]

    def __post_init__(self) -> None:
        for field_name in ("context_view_id", "company_id", "input_id"):
            _require_id(field_name, getattr(self, field_name))
        for field_name in ("context_pack_ref", "context_pack_version"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        for field_name in (
            "as_of",
            "knowledge_cutoff",
            "decision_at",
            "context_pack_available_at",
        ):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.preregistered, bool):
            raise TypeError("preregistered must be a boolean")
        if not isinstance(self.coverage, (list, tuple)) or any(
            not isinstance(item, ContextCoverage) for item in self.coverage
        ):
            raise TypeError("coverage must contain only ContextCoverage values")
        coverage_by_area = {item.area: item for item in self.coverage}
        if len(coverage_by_area) != len(self.coverage):
            raise ValueError("coverage must not repeat an area")
        object.__setattr__(
            self,
            "coverage",
            tuple(
                coverage_by_area[area] for area in ContextCoverageArea if area in coverage_by_area
            ),
        )
        if not isinstance(self.temporal_bindings, (list, tuple)) or any(
            not isinstance(item, ContextTemporalBinding) for item in self.temporal_bindings
        ):
            raise TypeError("temporal_bindings must contain only ContextTemporalBinding values")
        binding_by_kind = {item.kind: item for item in self.temporal_bindings}
        if len(binding_by_kind) != len(self.temporal_bindings):
            raise ValueError("temporal_bindings must not repeat a kind")
        object.__setattr__(
            self,
            "temporal_bindings",
            tuple(
                binding_by_kind[kind]
                for kind in ContextTemporalBindingKind
                if kind in binding_by_kind
            ),
        )


@dataclass(frozen=True, slots=True)
class IndustryBottleneckInput(CanonicalModel):
    node_id: str
    verifiable_demand: EvidenceClaim
    slow_supply_response: EvidenceClaim
    constrained_substitution: EvidenceClaim
    persistence_to_next_window: EvidenceClaim
    dissolution_signals_identified: EvidenceClaim

    def __post_init__(self) -> None:
        _require_id("node_id", self.node_id)
        for field_name in (
            "verifiable_demand",
            "slow_supply_response",
            "constrained_substitution",
            "persistence_to_next_window",
            "dissolution_signals_identified",
        ):
            if not isinstance(getattr(self, field_name), EvidenceClaim):
                raise TypeError(f"{field_name} must be an EvidenceClaim")

    @property
    def claims(self) -> tuple[EvidenceClaim, ...]:
        return (
            self.verifiable_demand,
            self.slow_supply_response,
            self.constrained_substitution,
            self.persistence_to_next_window,
            self.dissolution_signals_identified,
        )


@dataclass(frozen=True, slots=True)
class BeneficiaryMappingInput(CanonicalModel):
    company_id: str
    node_id: str
    technical_link: EvidenceClaim
    qualified_supplier: EvidenceClaim
    market_share: EvidenceClaim
    realized_price: EvidenceClaim
    incremental_gross_profit: EvidenceClaim
    cash_collection: EvidenceClaim
    ownership_path: EvidenceClaim

    def __post_init__(self) -> None:
        _require_id("company_id", self.company_id)
        _require_id("node_id", self.node_id)
        for field_name in (
            "technical_link",
            "qualified_supplier",
            "market_share",
            "realized_price",
            "incremental_gross_profit",
            "cash_collection",
            "ownership_path",
        ):
            if not isinstance(getattr(self, field_name), EvidenceClaim):
                raise TypeError(f"{field_name} must be an EvidenceClaim")

    @property
    def profit_claims(self) -> tuple[EvidenceClaim, ...]:
        return (
            self.market_share,
            self.realized_price,
            self.incremental_gross_profit,
            self.cash_collection,
            self.ownership_path,
        )

    @property
    def claims(self) -> tuple[EvidenceClaim, ...]:
        return (self.technical_link, self.qualified_supplier, *self.profit_claims)


@dataclass(frozen=True, slots=True)
class Stage4ContextIndustryCase(CanonicalModel):
    case_id: str
    context: IndustryContextView
    bottleneck: IndustryBottleneckInput
    beneficiary: BeneficiaryMappingInput
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        if not isinstance(self.context, IndustryContextView):
            raise TypeError("context must be an IndustryContextView")
        if not isinstance(self.bottleneck, IndustryBottleneckInput):
            raise TypeError("bottleneck must be an IndustryBottleneckInput")
        if not isinstance(self.beneficiary, BeneficiaryMappingInput):
            raise TypeError("beneficiary must be a BeneficiaryMappingInput")
        if self.context.company_id != self.beneficiary.company_id:
            raise ValueError("context and beneficiary company_id must match")
        if self.bottleneck.node_id != self.beneficiary.node_id:
            raise ValueError("bottleneck and beneficiary node_id must match")


@dataclass(frozen=True, slots=True)
class Stage4RuleAssessment(CanonicalModel):
    rule_id: str
    evaluation_state: Stage4RuleEvaluationState
    outcome: GateOutcome | None
    reason_codes: tuple[str, ...]
    supporting_fact_ids: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...]
    rule_version: str = field(default=STAGE4_4A1_RULE_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.rule_id not in STAGE4_4A1_REQUIREMENT_IDS:
            raise ValueError("rule_id is not part of Stage 4 / 4A-1")
        object.__setattr__(
            self,
            "evaluation_state",
            _coerce_enum(
                "evaluation_state",
                Stage4RuleEvaluationState,
                self.evaluation_state,
            ),
        )
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        for field_name in ("reason_codes", "supporting_fact_ids", "conflicting_fact_ids"):
            object.__setattr__(
                self,
                field_name,
                _freeze_ids(field_name, getattr(self, field_name)),
            )
        if self.evaluation_state is Stage4RuleEvaluationState.EVALUATED:
            if self.outcome is None or not self.reason_codes:
                raise ValueError("evaluated rules require outcome and reason codes")
        elif self.outcome is not None or len(self.reason_codes) != 1:
            raise ValueError("not_evaluated rules require outcome=None and one reason code")


@dataclass(frozen=True, slots=True)
class Stage4ContextIndustryResult(CanonicalModel):
    case_id: str
    context_admission: Stage4RuleAssessment
    historical_context: Stage4RuleAssessment
    bottleneck_assessment: Stage4RuleAssessment
    beneficiary_assessment: Stage4RuleAssessment
    context_disposition: ContextDisposition
    bottleneck_qualified: bool
    beneficiary_tier: BeneficiaryTier
    four_gate_eligible: bool
    rule_bundle_hash: HashDigest
    rule_approval_id: str
    rule_approval_record_hash: HashDigest
    approval_scope: RuleApprovalScope = field(
        default=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION,
        init=False,
    )
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        _require_id("case_id", self.case_id)
        for field_name in (
            "context_admission",
            "historical_context",
            "bottleneck_assessment",
            "beneficiary_assessment",
        ):
            if not isinstance(getattr(self, field_name), Stage4RuleAssessment):
                raise TypeError(f"{field_name} must be a Stage4RuleAssessment")
        object.__setattr__(
            self,
            "context_disposition",
            _coerce_enum("context_disposition", ContextDisposition, self.context_disposition),
        )
        object.__setattr__(
            self,
            "beneficiary_tier",
            _coerce_enum("beneficiary_tier", BeneficiaryTier, self.beneficiary_tier),
        )
        for field_name in ("bottleneck_qualified", "four_gate_eligible"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        if not isinstance(self.rule_bundle_hash, HashDigest):
            raise TypeError("rule_bundle_hash must be a HashDigest")
        if not isinstance(self.rule_approval_record_hash, HashDigest):
            raise TypeError("rule_approval_record_hash must be a HashDigest")
        _require_id("rule_approval_id", self.rule_approval_id)
        if self.four_gate_eligible and (
            self.beneficiary_tier is not BeneficiaryTier.PROFIT_BENEFICIARY
            or self.beneficiary_assessment.outcome is not GateOutcome.PASS
        ):
            raise ValueError("four_gate_eligible requires a passing profit beneficiary")


_STAGE4_4A1_RULE_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4ContextIndustryRules:
    """Exact approved 4A-1 semantics backed by an opaque registry capability."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    minimum_independent_evidence_groups: int

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        minimum_independent_evidence_groups: int,
    ) -> None:
        if _issuer is not _STAGE4_4A1_RULE_ISSUER:
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_RULE_ISSUER_INVALID",
                "4A-1 typed rules can only be issued from an approved capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(
            self,
            "minimum_independent_evidence_groups",
            minimum_independent_evidence_groups,
        )

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage4ContextIndustryRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be a RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be an ApprovedRuleCapability")
        expected_identity = (
            "industrial_bottleneck_event",
            STAGE4_4A1_RULE_BUNDLE_ID,
            STAGE4_4A1_RULE_BUNDLE_VERSION,
        )
        if (document.strategy_id, document.bundle_id, document.bundle_version) != (
            expected_identity
        ) or (capability.strategy_id, capability.bundle_id, capability.bundle_version) != (
            expected_identity
        ):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_RULE_IDENTITY_UNSUPPORTED",
                "strategy, bundle, and version must match the approved 4A-1 profile",
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_RULE_DOCUMENT_NOT_APPROVED",
                "the rule document must declare approved",
            )
        if capability.approval_scope is not (
            RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION
        ):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_RULE_SCOPE_UNSUPPORTED",
                "4A-1 requires the exact Stage 4 synthetic research scope",
            )
        if capability.bundle_hash != document.bundle_hash() or (
            document.bundle_hash().value != STAGE4_4A1_RULE_BUNDLE_SHA256
        ):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_RULE_HASH_UNSUPPORTED",
                "the capability must bind the pinned 4A-1 rule document",
            )
        if capability.approval_id != STAGE4_4A1_RULE_APPROVAL_ID:
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_APPROVAL_ID_UNSUPPORTED",
                "the capability must carry the pinned owner approval ID",
            )
        if capability.approval_record_hash.value != (STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_APPROVAL_RECORD_UNSUPPORTED",
                "the capability must carry the pinned owner approval record",
            )
        if canonical_sha256(document.rules) != STAGE4_4A1_RULES_SHA256:
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_MACHINE_SEMANTICS_UNSUPPORTED",
                "the machine rule semantics differ from the approved profile",
            )
        rules = document.rules
        shared = rules.get("shared_semantics")
        if not isinstance(shared, Mapping):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_MACHINE_SEMANTICS_INVALID",
                "shared_semantics must be an object",
            )
        minimum_groups = shared.get("minimum_independent_evidence_groups")
        if (
            isinstance(minimum_groups, bool)
            or not isinstance(minimum_groups, int)
            or minimum_groups != 2
        ):
            raise Stage4ContextIndustryCompatibilityError(
                "STAGE4_4A1_EVIDENCE_POLICY_UNSUPPORTED",
                "the approved minimum independent evidence groups is exactly 2",
            )
        return cls(
            _issuer=_STAGE4_4A1_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            minimum_independent_evidence_groups=minimum_groups,
        )


def _assessment(
    rule_id: str,
    outcome: GateOutcome,
    reason_code: str,
    claims: Iterable[EvidenceClaim] = (),
) -> Stage4RuleAssessment:
    supporting, conflicting = _claim_fact_ids(claims)
    return Stage4RuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(reason_code,),
        supporting_fact_ids=supporting,
        conflicting_fact_ids=conflicting,
    )


def _not_evaluated(rule_id: str, reason_code: str) -> Stage4RuleAssessment:
    return Stage4RuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
        outcome=None,
        reason_codes=(reason_code,),
        supporting_fact_ids=(),
        conflicting_fact_ids=(),
    )


def evaluate_historical_context(context: IndustryContextView) -> Stage4RuleAssessment:
    """Evaluate FR-CTX-002 before any strategy semantic can run."""

    if not isinstance(context, IndustryContextView):
        raise TypeError("context must be an IndustryContextView")
    claims = tuple(binding.assessment for binding in context.temporal_bindings)
    actual_kinds = {binding.kind for binding in context.temporal_bindings}
    if actual_kinds != set(ContextTemporalBindingKind):
        return _assessment(
            "FR-CTX-002", GateOutcome.BLOCKED, "CTX_TEMPORAL_BINDING_SET_INCOMPLETE", claims
        )
    if (
        context.context_pack_available_at > context.knowledge_cutoff
        or context.as_of > context.knowledge_cutoff
        or context.knowledge_cutoff > context.decision_at
    ):
        return _assessment("FR-CTX-002", GateOutcome.BLOCKED, "CTX_PIT_RELATION_INVALID", claims)
    for binding in context.temporal_bindings:
        if binding.assessment.conclusion is EvidenceConclusion.CONFIRMED:
            if binding.available_at is None or binding.valid_from is None:
                return _assessment(
                    "FR-CTX-002",
                    GateOutcome.BLOCKED,
                    "CTX_CONFIRMED_BINDING_TIME_MISSING",
                    claims,
                )
            if binding.available_at > context.knowledge_cutoff:
                return _assessment(
                    "FR-CTX-002", GateOutcome.BLOCKED, "CTX_BINDING_AVAILABLE_AFTER_CUTOFF", claims
                )
            if context.as_of < binding.valid_from or (
                binding.valid_to is not None and context.as_of >= binding.valid_to
            ):
                return _assessment(
                    "FR-CTX-002", GateOutcome.BLOCKED, "CTX_BINDING_NOT_VALID_AT_AS_OF", claims
                )
    if any(
        claim.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for claim in claims
    ):
        return _assessment(
            "FR-CTX-002", GateOutcome.ABSTAIN, "CTX_HISTORICAL_SEMANTICS_UNRESOLVED", claims
        )
    return _assessment("FR-CTX-002", GateOutcome.PASS, "CTX_HISTORICAL_BINDINGS_VALID", claims)


def evaluate_context_admission(context: IndustryContextView) -> Stage4RuleAssessment:
    """Evaluate FR-CTX-001 after the historical/PIT precondition passes."""

    if not isinstance(context, IndustryContextView):
        raise TypeError("context must be an IndustryContextView")
    claims = tuple(item.assessment for item in context.coverage)
    if not context.context_pack_ref.strip() or not context.context_pack_version.strip():
        return _assessment(
            "FR-CTX-001",
            GateOutcome.BLOCKED,
            "CTX_CONTEXT_PACK_IDENTITY_MISSING",
            claims,
        )
    actual_areas = {item.area for item in context.coverage}
    if actual_areas != set(ContextCoverageArea):
        return _assessment(
            "FR-CTX-001", GateOutcome.BLOCKED, "CTX_REQUIRED_COVERAGE_SET_INCOMPLETE", claims
        )
    if not context.preregistered:
        return _assessment(
            "FR-CTX-001", GateOutcome.REJECT, "CTX_COMPANY_NOT_PREREGISTERED", claims
        )
    if any(
        claim.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for claim in claims
    ):
        return _assessment("FR-CTX-001", GateOutcome.ABSTAIN, "CTX_COVERAGE_UNRESOLVED", claims)
    return _assessment("FR-CTX-001", GateOutcome.PASS, "CTX_DECISION_POOL_ADMITTED", claims)


def evaluate_industry_bottleneck(
    bottleneck: IndustryBottleneckInput,
    *,
    minimum_independent_evidence_groups: int = 2,
) -> Stage4RuleAssessment:
    """Evaluate FR-IND-001 as a strict, non-compensating bottleneck predicate."""

    if not isinstance(bottleneck, IndustryBottleneckInput):
        raise TypeError("bottleneck must be an IndustryBottleneckInput")
    if minimum_independent_evidence_groups != 2:
        raise ValueError("minimum_independent_evidence_groups must be exactly 2")
    core = bottleneck.claims[:4]
    if any(claim.conclusion is EvidenceConclusion.REFUTED for claim in core):
        return _assessment(
            "FR-IND-001", GateOutcome.REJECT, "IND_BOTTLENECK_CORE_CLAIM_REFUTED", bottleneck.claims
        )
    if any(
        claim.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for claim in bottleneck.claims
    ):
        return _assessment(
            "FR-IND-001", GateOutcome.ABSTAIN, "IND_BOTTLENECK_CLAIM_UNRESOLVED", bottleneck.claims
        )
    if bottleneck.dissolution_signals_identified.conclusion is EvidenceConclusion.REFUTED:
        return _assessment(
            "FR-IND-001",
            GateOutcome.ABSTAIN,
            "IND_DISSOLUTION_SIGNAL_NOT_IDENTIFIED",
            bottleneck.claims,
        )
    if _evidence_group_count(bottleneck.claims) < minimum_independent_evidence_groups:
        return _assessment(
            "FR-IND-001",
            GateOutcome.ABSTAIN,
            "IND_EVIDENCE_INDEPENDENCE_INSUFFICIENT",
            bottleneck.claims,
        )
    return _assessment(
        "FR-IND-001", GateOutcome.PASS, "IND_BOTTLENECK_QUALIFIED", bottleneck.claims
    )


def evaluate_beneficiary_mapping(
    beneficiary: BeneficiaryMappingInput,
    *,
    minimum_independent_evidence_groups: int = 2,
) -> tuple[Stage4RuleAssessment, BeneficiaryTier]:
    """Evaluate FR-IND-002 and return the highest safely established tier."""

    if not isinstance(beneficiary, BeneficiaryMappingInput):
        raise TypeError("beneficiary must be a BeneficiaryMappingInput")
    if minimum_independent_evidence_groups != 2:
        raise ValueError("minimum_independent_evidence_groups must be exactly 2")
    technical = beneficiary.technical_link.conclusion
    qualified = beneficiary.qualified_supplier.conclusion
    profit_complete = all(
        claim.conclusion is EvidenceConclusion.CONFIRMED for claim in beneficiary.profit_claims
    )
    if qualified is EvidenceConclusion.CONFIRMED and technical is not EvidenceConclusion.CONFIRMED:
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.BLOCKED,
                "IND_MAPPING_QUALIFIED_WITHOUT_TECHNICAL_LINK",
                beneficiary.claims,
            ),
            BeneficiaryTier.NONE,
        )
    if profit_complete and qualified is not EvidenceConclusion.CONFIRMED:
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.BLOCKED,
                "IND_MAPPING_PROFIT_WITHOUT_SUPPLIER_QUALIFICATION",
                beneficiary.claims,
            ),
            BeneficiaryTier.NONE,
        )
    if technical is EvidenceConclusion.REFUTED:
        return (
            _assessment(
                "FR-IND-002", GateOutcome.REJECT, "IND_TECHNICAL_LINK_REFUTED", beneficiary.claims
            ),
            BeneficiaryTier.NONE,
        )
    if technical in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.ABSTAIN,
                "IND_TECHNICAL_LINK_UNRESOLVED",
                beneficiary.claims,
            ),
            BeneficiaryTier.NONE,
        )
    if qualified is EvidenceConclusion.REFUTED:
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.REJECT,
                "IND_SUPPLIER_QUALIFICATION_REFUTED",
                beneficiary.claims,
            ),
            BeneficiaryTier.TECHNICAL_LINK,
        )
    if qualified in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.ABSTAIN,
                "IND_SUPPLIER_QUALIFICATION_UNRESOLVED",
                beneficiary.claims,
            ),
            BeneficiaryTier.TECHNICAL_LINK,
        )
    if any(claim.conclusion is EvidenceConclusion.REFUTED for claim in beneficiary.profit_claims):
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.REJECT,
                "IND_PROFIT_ATTRIBUTION_CLAIM_REFUTED",
                beneficiary.claims,
            ),
            BeneficiaryTier.QUALIFIED_SUPPLIER,
        )
    if any(
        claim.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for claim in beneficiary.profit_claims
    ):
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.ABSTAIN,
                "IND_PROFIT_ATTRIBUTION_UNRESOLVED",
                beneficiary.claims,
            ),
            BeneficiaryTier.QUALIFIED_SUPPLIER,
        )
    if _evidence_group_count(beneficiary.profit_claims) < minimum_independent_evidence_groups:
        return (
            _assessment(
                "FR-IND-002",
                GateOutcome.ABSTAIN,
                "IND_PROFIT_EVIDENCE_INDEPENDENCE_INSUFFICIENT",
                beneficiary.claims,
            ),
            BeneficiaryTier.QUALIFIED_SUPPLIER,
        )
    return (
        _assessment(
            "FR-IND-002", GateOutcome.PASS, "IND_PROFIT_BENEFICIARY_QUALIFIED", beneficiary.claims
        ),
        BeneficiaryTier.PROFIT_BENEFICIARY,
    )


def evaluate_stage4_context_industry(
    case: Stage4ContextIndustryCase,
    rules: ApprovedStage4ContextIndustryRules,
) -> Stage4ContextIndustryResult:
    """Run the approved 4A-1 slice with deterministic fail-closed short circuiting."""

    if not isinstance(case, Stage4ContextIndustryCase):
        raise TypeError("case must be a Stage4ContextIndustryCase")
    if not isinstance(rules, ApprovedStage4ContextIndustryRules):
        raise TypeError("rules must be ApprovedStage4ContextIndustryRules")

    historical = evaluate_historical_context(case.context)
    if historical.outcome is not GateOutcome.PASS:
        context_admission = _not_evaluated("FR-CTX-001", "CTX_HISTORICAL_CONTEXT_TERMINAL")
        bottleneck = _not_evaluated("FR-IND-001", "CTX_HISTORICAL_CONTEXT_TERMINAL")
        beneficiary = _not_evaluated("FR-IND-002", "CTX_HISTORICAL_CONTEXT_TERMINAL")
        tier = BeneficiaryTier.NONE
    else:
        context_admission = evaluate_context_admission(case.context)
        if context_admission.outcome is not GateOutcome.PASS:
            bottleneck = _not_evaluated("FR-IND-001", "CTX_ADMISSION_TERMINAL")
            beneficiary = _not_evaluated("FR-IND-002", "CTX_ADMISSION_TERMINAL")
            tier = BeneficiaryTier.NONE
        else:
            bottleneck = evaluate_industry_bottleneck(
                case.bottleneck,
                minimum_independent_evidence_groups=(rules.minimum_independent_evidence_groups),
            )
            if bottleneck.outcome is not GateOutcome.PASS:
                beneficiary = _not_evaluated("FR-IND-002", "IND_BOTTLENECK_TERMINAL")
                tier = BeneficiaryTier.NONE
            else:
                beneficiary, tier = evaluate_beneficiary_mapping(
                    case.beneficiary,
                    minimum_independent_evidence_groups=(rules.minimum_independent_evidence_groups),
                )

    context_passed = historical.outcome is GateOutcome.PASS and (
        context_admission.outcome is GateOutcome.PASS
    )
    bottleneck_passed = bottleneck.outcome is GateOutcome.PASS
    four_gate_eligible = beneficiary.outcome is GateOutcome.PASS and (
        tier is BeneficiaryTier.PROFIT_BENEFICIARY
    )
    return Stage4ContextIndustryResult(
        case_id=case.case_id,
        context_admission=context_admission,
        historical_context=historical,
        bottleneck_assessment=bottleneck,
        beneficiary_assessment=beneficiary,
        context_disposition=(
            ContextDisposition.DECISION_POOL
            if context_passed
            else ContextDisposition.RESEARCH_QUARANTINE
        ),
        bottleneck_qualified=bottleneck_passed,
        beneficiary_tier=tier,
        four_gate_eligible=four_gate_eligible,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
    )
