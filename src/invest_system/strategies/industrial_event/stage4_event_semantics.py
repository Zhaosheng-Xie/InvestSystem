"""Approved Stage 4 / 4A-2 event-state and audit-layer semantics.

The evaluator accepts only an opaque capability for the exact owner-approved
machine bundle.  It performs no I/O, consumes provider-neutral synthetic
objects, never writes back to the KB, and grants no portfolio or order power.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from itertools import combinations
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import CanonicalModel, EventState, GateOutcome, HashDigest, RuleStatus

from .stage4_context_industry import (
    EvidenceClaim,
    EvidenceConclusion,
    Stage4RuleEvaluationState,
)

STAGE4_4A2_RULE_BUNDLE_ID = "industrial_event_stage4_4a2_event_semantics"
STAGE4_4A2_RULE_BUNDLE_VERSION = "0.1.0"
STAGE4_4A2_RULE_APPROVAL_ID = "rule_approval_stage4_4a2_event_semantics_v0_1_0"
STAGE4_4A2_RULE_BUNDLE_SHA256 = "9f9f5cf843347a1918a894be1151c0ef720bd6318daa1077657e97e9324d6560"
STAGE4_4A2_RULES_SHA256 = "574dd4273c60081b099cf2c2427a2f264521f57ff16aa70b5ce1138ea9e8f228"
STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256 = (
    "57c5147ab93c7cf547f72347a7550f951c9ca2ad0cf97cb0755148bfa0d155ac"
)
STAGE4_4A2_RULE_VERSION = "0.1.0"
STAGE4_4A2_REQUIREMENT_IDS = (
    "FR-EVT-001",
    "FR-EVT-002",
    "FR-EVT-003",
    "FR-EVT-004",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_EVENT_STATE_RANK = {
    EventState.E0: 0,
    EventState.E1: 1,
    EventState.E2: 2,
    EventState.E3: 3,
    EventState.E3_5: 4,
    EventState.E4: 5,
    EventState.E5: 6,
    EventState.E6: 7,
}


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
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


def _digest(payload: Any) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _claim_fact_ids(claims: Iterable[EvidenceClaim]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    supporting = sorted({fact_id for claim in claims for fact_id in claim.supporting_fact_ids})
    conflicting = sorted({fact_id for claim in claims for fact_id in claim.conflicting_fact_ids})
    return tuple(supporting), tuple(conflicting)


class E4ClosureClaim(StrEnum):
    AUTHORIZED_PUBLIC_EVIDENCE = "authorized_public_evidence"
    LISTED_COMPANY_OWNERSHIP_PATH = "listed_company_ownership_path"
    SIGNED_OR_FORMALLY_ORDERED = "signed_or_formally_ordered"
    EFFECTIVE_OR_CONDITIONS_SATISFIED = "effective_or_conditions_satisfied"
    BINDING_MINIMUM_OBLIGATION = "binding_minimum_obligation"
    MINIMUM_NOT_ZEROABLE = "minimum_not_zeroable"


class EconomicQuantification(StrEnum):
    KNOWN = "known"
    CONFIDENTIAL_UNKNOWN = "confidential_unknown"
    UNKNOWN = "unknown"


class PartyRole(StrEnum):
    LISTED_COMPANY = "listed_company"
    ECONOMIC_BENEFICIARY = "economic_beneficiary"
    SELLER_SUPPLIER = "seller_supplier"
    CUSTOMER_BUYER = "customer_buyer"
    PROCUREMENT_ACTOR = "procurement_actor"


class PartyLinkKind(StrEnum):
    DIRECT = "direct"
    INDIRECT = "indirect"


class PartyLinkApplicability(StrEnum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"


class PassportClaimKind(StrEnum):
    RESEARCH_AND_DEVELOPMENT = "research_and_development"
    SAMPLE = "sample"
    STANDARD = "standard"
    TECHNICAL_FEASIBILITY = "technical_feasibility"
    CUSTOMER_TEST = "customer_test"
    CERTIFICATION = "certification"
    DESIGN_IN = "design_in"
    SUPPLIER_QUALIFICATION = "supplier_qualification"
    BIDDING = "bidding"
    PROCUREMENT_INTENT = "procurement_intent"
    FRAMEWORK = "framework"
    EXPECTED_SHARE = "expected_share"
    COMMERCIAL_NEGOTIATION = "commercial_negotiation"
    DELIVERY = "delivery"
    ACCEPTANCE = "acceptance"
    VERIFIABLE_PERFORMANCE_PROGRESS = "verifiable_performance_progress"


class TerminalEventType(StrEnum):
    REPEAT_OR_SCALE = "repeat_or_scale"
    CYCLE_MATURED = "cycle_matured"
    CONTRACT_TERMINATED = "contract_terminated"
    THESIS_COMPLETED = "thesis_completed"


class KnowledgeObjectKind(StrEnum):
    FACT = "Fact"
    ASSUMPTION = "Assumption"
    DERIVED = "Derived"
    JUDGMENT = "Judgment"


class Stage4EventCompatibilityError(ValueError):
    """Stable fail-closed rejection for a non-approved 4A-2 capability."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class FactKnowledge(CanonicalModel):
    provider_fact_id: str
    subject: str
    predicate: str
    value_ref: str
    available_at: datetime | None
    evidence_ids: tuple[str, ...]
    input_ref: str
    lineage_group_id: str
    authorized_public: bool = True
    reviewed: bool = True
    is_mnpi: bool = False
    authority_clear: bool = True
    kind: KnowledgeObjectKind = field(default=KnowledgeObjectKind.FACT, init=False)
    content_hash: HashDigest = field(init=False)

    def __post_init__(self) -> None:
        _require_id("provider_fact_id", self.provider_fact_id)
        _require_text("subject", self.subject)
        _require_text("predicate", self.predicate)
        _require_text("value_ref", self.value_ref)
        _require_id("input_ref", self.input_ref)
        _require_id("lineage_group_id", self.lineage_group_id)
        object.__setattr__(self, "evidence_ids", _freeze_ids("evidence_ids", self.evidence_ids))
        if self.available_at is not None:
            object.__setattr__(
                self,
                "available_at",
                normalize_utc(self.available_at, field_name="available_at"),
            )
        for field_name in ("authorized_public", "reviewed", "is_mnpi", "authority_clear"):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a boolean")
        object.__setattr__(
            self,
            "content_hash",
            _digest(
                {
                    "provider_fact_id": self.provider_fact_id,
                    "subject": self.subject,
                    "predicate": self.predicate,
                    "value_ref": self.value_ref,
                    "available_at": self.available_at,
                    "evidence_ids": self.evidence_ids,
                    "input_ref": self.input_ref,
                    "lineage_group_id": self.lineage_group_id,
                    "authorized_public": self.authorized_public,
                    "reviewed": self.reviewed,
                    "is_mnpi": self.is_mnpi,
                    "authority_clear": self.authority_clear,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class AssumptionKnowledge(CanonicalModel):
    assumption_id: str
    as_of: datetime
    scenario_id: str
    rationale: str
    dependency_ids: tuple[str, ...]
    observable_falsification_conditions: tuple[str, ...]
    created_by: str
    version: str
    input_ref: str
    supersedes_id: str | None = None
    kind: KnowledgeObjectKind = field(default=KnowledgeObjectKind.ASSUMPTION, init=False)
    content_hash: HashDigest = field(init=False)

    def __post_init__(self) -> None:
        for field_name in ("assumption_id", "scenario_id", "created_by", "input_ref"):
            _require_id(field_name, getattr(self, field_name))
        _require_text("rationale", self.rationale)
        _require_text("version", self.version)
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        object.__setattr__(
            self,
            "dependency_ids",
            _freeze_ids("dependency_ids", self.dependency_ids),
        )
        if not isinstance(self.observable_falsification_conditions, (list, tuple)):
            raise TypeError("observable_falsification_conditions must be a list or tuple")
        conditions = tuple(
            _require_text("observable_falsification_conditions", item)
            for item in self.observable_falsification_conditions
        )
        if len(conditions) != len(set(conditions)):
            raise ValueError("observable_falsification_conditions must not contain duplicates")
        object.__setattr__(self, "observable_falsification_conditions", tuple(sorted(conditions)))
        if self.supersedes_id is not None:
            _require_id("supersedes_id", self.supersedes_id)
        object.__setattr__(self, "content_hash", _digest(self._content_payload()))

    def _content_payload(self) -> Mapping[str, Any]:
        return {
            "assumption_id": self.assumption_id,
            "as_of": self.as_of,
            "scenario_id": self.scenario_id,
            "rationale": self.rationale,
            "dependency_ids": self.dependency_ids,
            "observable_falsification_conditions": self.observable_falsification_conditions,
            "created_by": self.created_by,
            "version": self.version,
            "input_ref": self.input_ref,
            "supersedes_id": self.supersedes_id,
        }


@dataclass(frozen=True, slots=True)
class DerivedKnowledge(CanonicalModel):
    derived_id: str
    formula_id: str
    formula_version: str
    dependency_ids: tuple[str, ...]
    scenario_id: str
    calculation_input_hash: HashDigest
    result_hash: HashDigest
    as_of: datetime
    created_by: str
    version: str
    input_ref: str
    supersedes_id: str | None = None
    kind: KnowledgeObjectKind = field(default=KnowledgeObjectKind.DERIVED, init=False)
    content_hash: HashDigest = field(init=False)

    def __post_init__(self) -> None:
        for field_name in (
            "derived_id",
            "formula_id",
            "scenario_id",
            "created_by",
            "input_ref",
        ):
            _require_id(field_name, getattr(self, field_name))
        for field_name in ("formula_version", "version"):
            _require_text(field_name, getattr(self, field_name))
        object.__setattr__(
            self,
            "dependency_ids",
            _freeze_ids("dependency_ids", self.dependency_ids),
        )
        for field_name in ("calculation_input_hash", "result_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        if self.supersedes_id is not None:
            _require_id("supersedes_id", self.supersedes_id)
        object.__setattr__(
            self,
            "content_hash",
            _digest(
                {
                    "derived_id": self.derived_id,
                    "formula_id": self.formula_id,
                    "formula_version": self.formula_version,
                    "dependency_ids": self.dependency_ids,
                    "scenario_id": self.scenario_id,
                    "calculation_input_hash": self.calculation_input_hash,
                    "result_hash": self.result_hash,
                    "as_of": self.as_of,
                    "created_by": self.created_by,
                    "version": self.version,
                    "input_ref": self.input_ref,
                    "supersedes_id": self.supersedes_id,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class JudgmentKnowledge(CanonicalModel):
    judgment_id: str
    rule_id: str
    rule_version: str
    rule_hash: HashDigest
    outcome: GateOutcome
    reason_codes: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    supporting_dependency_ids: tuple[str, ...]
    conflicting_dependency_ids: tuple[str, ...]
    pending_question_ids: tuple[str, ...]
    as_of: datetime
    created_by: str
    version: str
    input_ref: str
    supersedes_id: str | None = None
    overrides_judgment_id: str | None = None
    approval_ref: str | None = None
    kind: KnowledgeObjectKind = field(default=KnowledgeObjectKind.JUDGMENT, init=False)
    content_hash: HashDigest = field(init=False)

    def __post_init__(self) -> None:
        for field_name in ("judgment_id", "rule_id", "created_by", "input_ref"):
            _require_id(field_name, getattr(self, field_name))
        for field_name in ("rule_version", "version"):
            _require_text(field_name, getattr(self, field_name))
        if not isinstance(self.rule_hash, HashDigest):
            raise TypeError("rule_hash must be a HashDigest")
        object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        for field_name in (
            "reason_codes",
            "dependency_ids",
            "supporting_dependency_ids",
            "conflicting_dependency_ids",
            "pending_question_ids",
        ):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        object.__setattr__(self, "as_of", normalize_utc(self.as_of, field_name="as_of"))
        for field_name in ("supersedes_id", "overrides_judgment_id", "approval_ref"):
            value = getattr(self, field_name)
            if value is not None:
                _require_id(field_name, value)
        object.__setattr__(
            self,
            "content_hash",
            _digest(
                {
                    "judgment_id": self.judgment_id,
                    "rule_id": self.rule_id,
                    "rule_version": self.rule_version,
                    "rule_hash": self.rule_hash,
                    "outcome": self.outcome,
                    "reason_codes": self.reason_codes,
                    "dependency_ids": self.dependency_ids,
                    "supporting_dependency_ids": self.supporting_dependency_ids,
                    "conflicting_dependency_ids": self.conflicting_dependency_ids,
                    "pending_question_ids": self.pending_question_ids,
                    "as_of": self.as_of,
                    "created_by": self.created_by,
                    "version": self.version,
                    "input_ref": self.input_ref,
                    "supersedes_id": self.supersedes_id,
                    "overrides_judgment_id": self.overrides_judgment_id,
                    "approval_ref": self.approval_ref,
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class AuditKnowledgeGraph(CanonicalModel):
    facts: tuple[FactKnowledge, ...]
    assumptions: tuple[AssumptionKnowledge, ...] = ()
    derived: tuple[DerivedKnowledge, ...] = ()
    judgments: tuple[JudgmentKnowledge, ...] = ()
    writeback_to_kb: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for field_name, item_type in (
            ("facts", FactKnowledge),
            ("assumptions", AssumptionKnowledge),
            ("derived", DerivedKnowledge),
            ("judgments", JudgmentKnowledge),
        ):
            values = getattr(self, field_name)
            if not isinstance(values, (list, tuple)) or any(
                not isinstance(item, item_type) for item in values
            ):
                raise TypeError(f"{field_name} must contain only {item_type.__name__} values")
            object.__setattr__(self, field_name, tuple(values))


@dataclass(frozen=True, slots=True)
class PartyLink(CanonicalModel):
    role: PartyRole
    applicability: PartyLinkApplicability
    assessment: EvidenceClaim | None
    legal_entity_id: str | None
    link_kind: PartyLinkKind | None
    relation: str | None
    lineage_group_ids: tuple[str, ...]
    valid_from: datetime | None
    valid_to: datetime | None = None
    legally_confidential: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "role", _coerce_enum("role", PartyRole, self.role))
        object.__setattr__(
            self,
            "applicability",
            _coerce_enum("applicability", PartyLinkApplicability, self.applicability),
        )
        if self.assessment is not None and not isinstance(self.assessment, EvidenceClaim):
            raise TypeError("assessment must be an EvidenceClaim or None")
        if self.legal_entity_id is not None:
            _require_id("legal_entity_id", self.legal_entity_id)
        if self.link_kind is not None:
            object.__setattr__(
                self,
                "link_kind",
                _coerce_enum("link_kind", PartyLinkKind, self.link_kind),
            )
        if self.relation is not None:
            _require_text("relation", self.relation)
        object.__setattr__(
            self,
            "lineage_group_ids",
            _freeze_ids("lineage_group_ids", self.lineage_group_ids),
        )
        for field_name in ("valid_from", "valid_to"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, normalize_utc(value, field_name=field_name))
        if self.valid_to is not None and (
            self.valid_from is None or self.valid_to <= self.valid_from
        ):
            raise ValueError("valid_to must be strictly later than valid_from")
        if not isinstance(self.legally_confidential, bool):
            raise TypeError("legally_confidential must be a boolean")


@dataclass(frozen=True, slots=True)
class AuthoritativeOriginal(CanonicalModel):
    fact_id: str
    responsible_publisher_id: str
    acquisition_lineage_id: str
    directly_supports: tuple[E4ClosureClaim, ...]

    def __post_init__(self) -> None:
        for field_name in ("fact_id", "responsible_publisher_id", "acquisition_lineage_id"):
            _require_id(field_name, getattr(self, field_name))
        if not isinstance(self.directly_supports, (list, tuple)):
            raise TypeError("directly_supports must be a list or tuple")
        values = tuple(
            _coerce_enum("directly_supports", E4ClosureClaim, value)
            for value in self.directly_supports
        )
        if len(values) != len(set(values)):
            raise ValueError("directly_supports must not contain duplicates")
        object.__setattr__(self, "directly_supports", tuple(sorted(values, key=str)))


@dataclass(frozen=True, slots=True)
class PublicEvidenceChain(CanonicalModel):
    chain_id: str
    fact_ids: tuple[str, ...]
    responsible_publisher_id: str
    acquisition_lineage_id: str
    contains_authoritative_original: bool

    def __post_init__(self) -> None:
        for field_name in ("chain_id", "responsible_publisher_id", "acquisition_lineage_id"):
            _require_id(field_name, getattr(self, field_name))
        object.__setattr__(self, "fact_ids", _freeze_ids("fact_ids", self.fact_ids))
        if not self.fact_ids:
            raise ValueError("fact_ids must not be empty")
        if not isinstance(self.contains_authoritative_original, bool):
            raise TypeError("contains_authoritative_original must be a boolean")


@dataclass(frozen=True, slots=True)
class E4PublicInput(CanonicalModel):
    authorized_public_evidence: EvidenceClaim
    listed_company_ownership_path: EvidenceClaim
    signed_or_formally_ordered: EvidenceClaim
    effective_or_conditions_satisfied: EvidenceClaim
    binding_minimum_obligation: EvidenceClaim
    minimum_not_zeroable: EvidenceClaim
    authoritative_originals: tuple[AuthoritativeOriginal, ...]
    public_evidence_chains: tuple[PublicEvidenceChain, ...]
    economic_quantification: EconomicQuantification

    def __post_init__(self) -> None:
        for field_name in (
            "authorized_public_evidence",
            "listed_company_ownership_path",
            "signed_or_formally_ordered",
            "effective_or_conditions_satisfied",
            "binding_minimum_obligation",
            "minimum_not_zeroable",
        ):
            if not isinstance(getattr(self, field_name), EvidenceClaim):
                raise TypeError(f"{field_name} must be an EvidenceClaim")
        for field_name, item_type in (
            ("authoritative_originals", AuthoritativeOriginal),
            ("public_evidence_chains", PublicEvidenceChain),
        ):
            values = getattr(self, field_name)
            if not isinstance(values, (list, tuple)) or any(
                not isinstance(item, item_type) for item in values
            ):
                raise TypeError(f"{field_name} must contain only {item_type.__name__} values")
            object.__setattr__(self, field_name, tuple(values))
        object.__setattr__(
            self,
            "economic_quantification",
            _coerce_enum(
                "economic_quantification",
                EconomicQuantification,
                self.economic_quantification,
            ),
        )

    @property
    def claims(self) -> tuple[EvidenceClaim, ...]:
        return (
            self.authorized_public_evidence,
            self.listed_company_ownership_path,
            self.signed_or_formally_ordered,
            self.effective_or_conditions_satisfied,
            self.binding_minimum_obligation,
            self.minimum_not_zeroable,
        )


@dataclass(frozen=True, slots=True)
class EventPassportClaim(CanonicalModel):
    kind: PassportClaimKind
    assessment: EvidenceClaim

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", _coerce_enum("kind", PassportClaimKind, self.kind))
        if not isinstance(self.assessment, EvidenceClaim):
            raise TypeError("assessment must be an EvidenceClaim")


@dataclass(frozen=True, slots=True)
class TerminalEventClaim(CanonicalModel):
    terminal_type: TerminalEventType
    assessment: EvidenceClaim

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terminal_type",
            _coerce_enum("terminal_type", TerminalEventType, self.terminal_type),
        )
        if not isinstance(self.assessment, EvidenceClaim):
            raise TypeError("assessment must be an EvidenceClaim")


@dataclass(frozen=True, slots=True)
class EventPassportInput(CanonicalModel):
    narrative: EvidenceClaim
    e1_claims: tuple[EventPassportClaim, ...]
    e2_claims: tuple[EventPassportClaim, ...]
    e3_claims: tuple[EventPassportClaim, ...]
    strong_commercial_clue: EvidenceClaim
    e5_claims: tuple[EventPassportClaim, ...]
    revenue_validation: EvidenceClaim
    incremental_profit_validation: EvidenceClaim
    cash_collection_validation: EvidenceClaim
    terminal_claims: tuple[TerminalEventClaim, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "narrative",
            "strong_commercial_clue",
            "revenue_validation",
            "incremental_profit_validation",
            "cash_collection_validation",
        ):
            if not isinstance(getattr(self, field_name), EvidenceClaim):
                raise TypeError(f"{field_name} must be an EvidenceClaim")
        allowed_by_stage = {
            "e1_claims": {
                PassportClaimKind.RESEARCH_AND_DEVELOPMENT,
                PassportClaimKind.SAMPLE,
                PassportClaimKind.STANDARD,
                PassportClaimKind.TECHNICAL_FEASIBILITY,
            },
            "e2_claims": {
                PassportClaimKind.CUSTOMER_TEST,
                PassportClaimKind.CERTIFICATION,
                PassportClaimKind.DESIGN_IN,
                PassportClaimKind.SUPPLIER_QUALIFICATION,
            },
            "e3_claims": {
                PassportClaimKind.BIDDING,
                PassportClaimKind.PROCUREMENT_INTENT,
                PassportClaimKind.FRAMEWORK,
                PassportClaimKind.EXPECTED_SHARE,
                PassportClaimKind.COMMERCIAL_NEGOTIATION,
            },
            "e5_claims": {
                PassportClaimKind.DELIVERY,
                PassportClaimKind.ACCEPTANCE,
                PassportClaimKind.VERIFIABLE_PERFORMANCE_PROGRESS,
            },
        }
        for field_name, allowed in allowed_by_stage.items():
            values = getattr(self, field_name)
            if not isinstance(values, (list, tuple)) or any(
                not isinstance(item, EventPassportClaim) for item in values
            ):
                raise TypeError(f"{field_name} must contain EventPassportClaim values")
            kinds = [item.kind for item in values]
            if len(kinds) != len(set(kinds)) or any(kind not in allowed for kind in kinds):
                raise ValueError(f"{field_name} contains duplicate or invalid claim kinds")
            object.__setattr__(self, field_name, tuple(sorted(values, key=lambda item: item.kind)))
        if not isinstance(self.terminal_claims, (list, tuple)) or any(
            not isinstance(item, TerminalEventClaim) for item in self.terminal_claims
        ):
            raise TypeError("terminal_claims must contain TerminalEventClaim values")
        terminal_types = [item.terminal_type for item in self.terminal_claims]
        if len(terminal_types) != len(set(terminal_types)):
            raise ValueError("terminal_claims must not repeat terminal_type")
        object.__setattr__(
            self,
            "terminal_claims",
            tuple(sorted(self.terminal_claims, key=lambda item: item.terminal_type)),
        )

    @property
    def claims(self) -> tuple[EvidenceClaim, ...]:
        return (
            self.narrative,
            *(item.assessment for item in self.e1_claims),
            *(item.assessment for item in self.e2_claims),
            *(item.assessment for item in self.e3_claims),
            self.strong_commercial_clue,
            *(item.assessment for item in self.e5_claims),
            self.revenue_validation,
            self.incremental_profit_validation,
            self.cash_collection_validation,
            *(item.assessment for item in self.terminal_claims),
        )


@dataclass(frozen=True, slots=True)
class EventSnapshotRef(CanonicalModel):
    logical_event_id: str
    event_snapshot_id: str
    revision: int
    content_hash: HashDigest
    highest_nonterminal_state: EventState
    rule_bundle_hash: HashDigest

    def __post_init__(self) -> None:
        _require_id("logical_event_id", self.logical_event_id)
        _require_id("event_snapshot_id", self.event_snapshot_id)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("revision must be a positive integer")
        for field_name in ("content_hash", "rule_bundle_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        object.__setattr__(
            self,
            "highest_nonterminal_state",
            EventState(self.highest_nonterminal_state),
        )
        if self.highest_nonterminal_state is EventState.E7:
            raise ValueError("highest_nonterminal_state cannot be E7")


@dataclass(frozen=True, slots=True)
class RuleMigrationReplay(CanonicalModel):
    from_rule_bundle_hash: HashDigest
    to_rule_bundle_hash: HashDigest
    fixed_input_hash: HashDigest
    replay_hash: HashDigest
    replayable: bool

    def __post_init__(self) -> None:
        for field_name in (
            "from_rule_bundle_hash",
            "to_rule_bundle_hash",
            "fixed_input_hash",
            "replay_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        if not isinstance(self.replayable, bool):
            raise TypeError("replayable must be a boolean")


@dataclass(frozen=True, slots=True)
class EventRevisionInput(CanonicalModel):
    logical_event_id: str
    event_snapshot_id: str
    revision: int
    content_hash: HashDigest
    supersedes_event_snapshot_id: str | None
    previous_snapshot: EventSnapshotRef | None = None
    duplicate_observation: bool = False
    explicit_superseding_refutation: EvidenceClaim | None = None
    migration_replay: RuleMigrationReplay | None = None

    def __post_init__(self) -> None:
        _require_id("logical_event_id", self.logical_event_id)
        _require_id("event_snapshot_id", self.event_snapshot_id)
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise ValueError("revision must be a positive integer")
        if not isinstance(self.content_hash, HashDigest):
            raise TypeError("content_hash must be a HashDigest")
        if self.supersedes_event_snapshot_id is not None:
            _require_id("supersedes_event_snapshot_id", self.supersedes_event_snapshot_id)
        if self.previous_snapshot is not None and not isinstance(
            self.previous_snapshot, EventSnapshotRef
        ):
            raise TypeError("previous_snapshot must be an EventSnapshotRef or None")
        if not isinstance(self.duplicate_observation, bool):
            raise TypeError("duplicate_observation must be a boolean")
        if self.explicit_superseding_refutation is not None and not isinstance(
            self.explicit_superseding_refutation, EvidenceClaim
        ):
            raise TypeError("explicit_superseding_refutation must be an EvidenceClaim or None")
        if self.migration_replay is not None and not isinstance(
            self.migration_replay, RuleMigrationReplay
        ):
            raise TypeError("migration_replay must be a RuleMigrationReplay or None")


@dataclass(frozen=True, slots=True)
class Stage4EventCase(CanonicalModel):
    case_id: str
    input_ref: str
    knowledge_cutoff: datetime
    decision_at: datetime
    knowledge_graph: AuditKnowledgeGraph
    earliest_fact_candidate_ids: tuple[str, ...]
    declared_earliest_legal_public_fact_id: str
    party_links: tuple[PartyLink, ...]
    e4_public: E4PublicInput
    passports: EventPassportInput
    revision: EventRevisionInput
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for field_name in ("case_id", "input_ref", "declared_earliest_legal_public_fact_id"):
            _require_id(field_name, getattr(self, field_name))
        for field_name in ("knowledge_cutoff", "decision_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        if not isinstance(self.knowledge_graph, AuditKnowledgeGraph):
            raise TypeError("knowledge_graph must be an AuditKnowledgeGraph")
        object.__setattr__(
            self,
            "earliest_fact_candidate_ids",
            _freeze_ids("earliest_fact_candidate_ids", self.earliest_fact_candidate_ids),
        )
        if not isinstance(self.party_links, (list, tuple)) or any(
            not isinstance(item, PartyLink) for item in self.party_links
        ):
            raise TypeError("party_links must contain PartyLink values")
        object.__setattr__(self, "party_links", tuple(self.party_links))
        if not isinstance(self.e4_public, E4PublicInput):
            raise TypeError("e4_public must be an E4PublicInput")
        if not isinstance(self.passports, EventPassportInput):
            raise TypeError("passports must be an EventPassportInput")
        if not isinstance(self.revision, EventRevisionInput):
            raise TypeError("revision must be an EventRevisionInput")


@dataclass(frozen=True, slots=True)
class Stage4EventRuleAssessment(CanonicalModel):
    rule_id: str
    evaluation_state: Stage4RuleEvaluationState
    outcome: GateOutcome | None
    reason_codes: tuple[str, ...]
    supporting_fact_ids: tuple[str, ...]
    conflicting_fact_ids: tuple[str, ...]
    rule_version: str = field(default=STAGE4_4A2_RULE_VERSION, init=False)

    def __post_init__(self) -> None:
        if self.rule_id not in STAGE4_4A2_REQUIREMENT_IDS:
            raise ValueError("rule_id is not part of Stage 4 / 4A-2")
        object.__setattr__(
            self,
            "evaluation_state",
            _coerce_enum("evaluation_state", Stage4RuleEvaluationState, self.evaluation_state),
        )
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        for field_name in ("reason_codes", "supporting_fact_ids", "conflicting_fact_ids"):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        if self.evaluation_state is Stage4RuleEvaluationState.EVALUATED:
            if self.outcome is None or not self.reason_codes:
                raise ValueError("evaluated rules require outcome and reason codes")
        elif self.outcome is not None or len(self.reason_codes) != 1:
            raise ValueError("not_evaluated rules require outcome=None and one reason code")


@dataclass(frozen=True, slots=True)
class PartyEventAssessment(CanonicalModel):
    assessment: Stage4EventRuleAssessment
    earliest_legal_public_fact_id: str | None
    cross_party_corroboration_ready: bool


@dataclass(frozen=True, slots=True)
class E4PublicAssessment(CanonicalModel):
    assessment: Stage4EventRuleAssessment
    independent_gate_evidence_ready: bool
    economic_quantification: EconomicQuantification
    future_profit_gate_must_abstain: bool


@dataclass(frozen=True, slots=True)
class EventStateAssessment(CanonicalModel):
    assessment: Stage4EventRuleAssessment
    attained_states: tuple[EventState, ...]
    highest_nonterminal_state: EventState | None
    candidate_highest_nonterminal_state: EventState | None
    terminal_type: TerminalEventType | None
    revision_created: bool
    duplicate_observation: bool
    last_confirmed_state: EventState | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attained_states",
            tuple(EventState(state) for state in self.attained_states),
        )
        for field_name in (
            "highest_nonterminal_state",
            "candidate_highest_nonterminal_state",
            "last_confirmed_state",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, EventState(value))
        if self.terminal_type is not None:
            object.__setattr__(
                self,
                "terminal_type",
                _coerce_enum("terminal_type", TerminalEventType, self.terminal_type),
            )


@dataclass(frozen=True, slots=True)
class Stage4EventResult(CanonicalModel):
    case_id: str
    audit_layers: Stage4EventRuleAssessment
    party_and_pit: PartyEventAssessment
    e4_public: E4PublicAssessment
    event_state: EventStateAssessment
    overall_outcome: GateOutcome
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


_STAGE4_4A2_RULE_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage4EventRules:
    """Exact approved 4A-2 semantics backed by an opaque registry capability."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    minimum_independent_public_chains: int

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        minimum_independent_public_chains: int,
    ) -> None:
        if _issuer is not _STAGE4_4A2_RULE_ISSUER:
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_RULE_ISSUER_INVALID",
                "4A-2 typed rules can only be issued from an approved capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(
            self,
            "minimum_independent_public_chains",
            minimum_independent_public_chains,
        )

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage4EventRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be a RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be an ApprovedRuleCapability")
        expected_identity = (
            "industrial_bottleneck_event",
            STAGE4_4A2_RULE_BUNDLE_ID,
            STAGE4_4A2_RULE_BUNDLE_VERSION,
        )
        if (document.strategy_id, document.bundle_id, document.bundle_version) != (
            expected_identity
        ) or (capability.strategy_id, capability.bundle_id, capability.bundle_version) != (
            expected_identity
        ):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_RULE_IDENTITY_UNSUPPORTED",
                "strategy, bundle, and version must match the approved 4A-2 profile",
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_RULE_DOCUMENT_NOT_APPROVED",
                "the rule document must declare approved",
            )
        if capability.approval_scope is not (
            RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION
        ):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_RULE_SCOPE_UNSUPPORTED",
                "4A-2 requires the exact Stage 4 synthetic research scope",
            )
        if capability.bundle_hash != document.bundle_hash() or (
            document.bundle_hash().value != STAGE4_4A2_RULE_BUNDLE_SHA256
        ):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_RULE_HASH_UNSUPPORTED",
                "the capability must bind the pinned 4A-2 rule document",
            )
        if capability.approval_id != STAGE4_4A2_RULE_APPROVAL_ID:
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_APPROVAL_ID_UNSUPPORTED",
                "the capability must carry the pinned owner approval ID",
            )
        if capability.approval_record_hash.value != (STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_APPROVAL_RECORD_UNSUPPORTED",
                "the capability must carry the pinned owner approval record",
            )
        if canonical_sha256(document.rules) != STAGE4_4A2_RULES_SHA256:
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_MACHINE_SEMANTICS_UNSUPPORTED",
                "the machine rule semantics differ from the approved profile",
            )
        shared = document.rules.get("shared_semantics")
        if not isinstance(shared, Mapping):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_MACHINE_SEMANTICS_INVALID",
                "shared_semantics must be an object",
            )
        minimum_chains = shared.get("minimum_independent_public_chains_for_gate_readiness")
        if (
            isinstance(minimum_chains, bool)
            or not isinstance(minimum_chains, int)
            or minimum_chains != 2
        ):
            raise Stage4EventCompatibilityError(
                "STAGE4_4A2_EVIDENCE_POLICY_UNSUPPORTED",
                "the approved gate-readiness minimum is exactly two independent chains",
            )
        return cls(
            _issuer=_STAGE4_4A2_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            minimum_independent_public_chains=minimum_chains,
        )


def _assessment(
    rule_id: str,
    outcome: GateOutcome,
    reason_code: str,
    claims: Iterable[EvidenceClaim] = (),
) -> Stage4EventRuleAssessment:
    supporting, conflicting = _claim_fact_ids(claims)
    return Stage4EventRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.EVALUATED,
        outcome=outcome,
        reason_codes=(reason_code,),
        supporting_fact_ids=supporting,
        conflicting_fact_ids=conflicting,
    )


def _not_evaluated(rule_id: str, reason_code: str) -> Stage4EventRuleAssessment:
    return Stage4EventRuleAssessment(
        rule_id=rule_id,
        evaluation_state=Stage4RuleEvaluationState.NOT_EVALUATED,
        outcome=None,
        reason_codes=(reason_code,),
        supporting_fact_ids=(),
        conflicting_fact_ids=(),
    )


def _all_claims(case: Stage4EventCase) -> tuple[EvidenceClaim, ...]:
    party_claims = tuple(
        link.assessment for link in case.party_links if link.assessment is not None
    )
    refutation = (
        (case.revision.explicit_superseding_refutation,)
        if case.revision.explicit_superseding_refutation is not None
        else ()
    )
    return (*party_claims, *case.e4_public.claims, *case.passports.claims, *refutation)


def _referenced_fact_ids(case: Stage4EventCase) -> set[str]:
    supporting, conflicting = _claim_fact_ids(_all_claims(case))
    result = set(supporting) | set(conflicting) | set(case.earliest_fact_candidate_ids)
    result.update(item.fact_id for item in case.e4_public.authoritative_originals)
    result.update(
        fact_id for chain in case.e4_public.public_evidence_chains for fact_id in chain.fact_ids
    )
    return result


def _node_id(node: AssumptionKnowledge | DerivedKnowledge | JudgmentKnowledge) -> str:
    if isinstance(node, AssumptionKnowledge):
        return node.assumption_id
    if isinstance(node, DerivedKnowledge):
        return node.derived_id
    return node.judgment_id


def evaluate_audit_knowledge_layers(case: Stage4EventCase) -> Stage4EventRuleAssessment:
    """Evaluate FR-EVT-004 global identity, dependency, DAG, time, and PIT rules."""

    if not isinstance(case, Stage4EventCase):
        raise TypeError("case must be a Stage4EventCase")
    graph = case.knowledge_graph
    if case.knowledge_cutoff > case.decision_at:
        return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_KNOWLEDGE_TIME_INVALID")
    facts_by_id = {fact.provider_fact_id: fact for fact in graph.facts}
    assumptions_by_id = {item.assumption_id: item for item in graph.assumptions}
    derived_by_id = {item.derived_id: item for item in graph.derived}
    judgments_by_id = {item.judgment_id: item for item in graph.judgments}
    all_ids = [
        *(fact.provider_fact_id for fact in graph.facts),
        *(item.assumption_id for item in graph.assumptions),
        *(item.derived_id for item in graph.derived),
        *(item.judgment_id for item in graph.judgments),
    ]
    if len(all_ids) != len(set(all_ids)):
        return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_KNOWLEDGE_ID_COLLISION")
    by_id: dict[str, FactKnowledge | AssumptionKnowledge | DerivedKnowledge | JudgmentKnowledge] = {
        **facts_by_id,
        **assumptions_by_id,
        **derived_by_id,
        **judgments_by_id,
    }
    referenced = _referenced_fact_ids(case)
    if not referenced.issubset(facts_by_id):
        return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_REFERENCED_FACT_MISSING")
    for fact in graph.facts:
        if fact.input_ref != case.input_ref:
            return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_CROSS_INPUT_FACT")
        if (
            fact.available_at is None
            or fact.available_at > case.knowledge_cutoff
            or not fact.evidence_ids
            or not fact.authorized_public
            or not fact.reviewed
            or fact.is_mnpi
            or not fact.authority_clear
        ):
            return _assessment(
                "FR-EVT-004", GateOutcome.BLOCKED, "EVT_FACT_PIT_OR_AUTHORITY_INVALID"
            )

    allowed_dependencies = {
        KnowledgeObjectKind.ASSUMPTION: {KnowledgeObjectKind.FACT, KnowledgeObjectKind.ASSUMPTION},
        KnowledgeObjectKind.DERIVED: {
            KnowledgeObjectKind.FACT,
            KnowledgeObjectKind.ASSUMPTION,
            KnowledgeObjectKind.DERIVED,
        },
        KnowledgeObjectKind.JUDGMENT: {
            KnowledgeObjectKind.FACT,
            KnowledgeObjectKind.ASSUMPTION,
            KnowledgeObjectKind.DERIVED,
        },
    }
    nodes: tuple[AssumptionKnowledge | DerivedKnowledge | JudgmentKnowledge, ...] = (
        *graph.assumptions,
        *graph.derived,
        *graph.judgments,
    )
    for node in nodes:
        if node.input_ref != case.input_ref or node.as_of > case.knowledge_cutoff:
            return _assessment(
                "FR-EVT-004", GateOutcome.BLOCKED, "EVT_KNOWLEDGE_INPUT_OR_TIME_INVALID"
            )
        node_id = _node_id(node)
        if node.supersedes_id is not None:
            previous = by_id.get(node.supersedes_id)
            if (
                previous is None
                or previous.kind is not node.kind
                or node.supersedes_id == node_id
                or not hasattr(previous, "as_of")
                or node.as_of <= previous.as_of
            ):
                return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_SUPERSEDES_INVALID")
        if not node.dependency_ids:
            return _assessment(
                "FR-EVT-004", GateOutcome.BLOCKED, "EVT_KNOWLEDGE_DEPENDENCIES_MISSING"
            )
        for dependency_id in node.dependency_ids:
            dependency = by_id.get(dependency_id)
            if dependency is None or dependency.kind not in allowed_dependencies[node.kind]:
                return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_DEPENDENCY_INVALID")
            dependency_time = (
                dependency.available_at
                if isinstance(dependency, FactKnowledge)
                else dependency.as_of
            )
            if dependency_time is None or node.as_of < dependency_time:
                return _assessment(
                    "FR-EVT-004", GateOutcome.BLOCKED, "EVT_DEPENDENCY_TIME_INVERSION"
                )
        if isinstance(node, AssumptionKnowledge) and not (node.observable_falsification_conditions):
            return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_ASSUMPTION_NOT_FALSIFIABLE")
        if isinstance(node, JudgmentKnowledge):
            if not node.reason_codes:
                return _assessment(
                    "FR-EVT-004", GateOutcome.BLOCKED, "EVT_JUDGMENT_REASON_CODES_MISSING"
                )
            dependency_ids = set(node.dependency_ids)
            if not (
                set(node.supporting_dependency_ids) | set(node.conflicting_dependency_ids)
            ).issubset(dependency_ids):
                return _assessment(
                    "FR-EVT-004", GateOutcome.BLOCKED, "EVT_JUDGMENT_AUDIT_REFS_INVALID"
                )
            if node.overrides_judgment_id is not None and (
                node.approval_ref is None or node.overrides_judgment_id not in judgments_by_id
            ):
                return _assessment(
                    "FR-EVT-004", GateOutcome.BLOCKED, "EVT_MANUAL_OVERRIDE_UNAPPROVED"
                )
            if node.outcome is GateOutcome.PASS and not node.supporting_dependency_ids:
                return _assessment(
                    "FR-EVT-004", GateOutcome.ABSTAIN, "EVT_JUDGMENT_SUPPORT_MISSING"
                )

    directed_ids = set(assumptions_by_id) | set(derived_by_id)
    directed_nodes: dict[str, AssumptionKnowledge | DerivedKnowledge] = {
        **assumptions_by_id,
        **derived_by_id,
    }
    edges = {
        node_id: tuple(dep for dep in node.dependency_ids if dep in directed_ids)
        for node_id, node in directed_nodes.items()
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return False
        if node_id in visited:
            return True
        visiting.add(node_id)
        if any(not visit(dependency_id) for dependency_id in edges[node_id]):
            return False
        visiting.remove(node_id)
        visited.add(node_id)
        return True

    if any(not visit(node_id) for node_id in edges):
        return _assessment("FR-EVT-004", GateOutcome.BLOCKED, "EVT_DERIVATION_CYCLE")
    return _assessment(
        "FR-EVT-004",
        GateOutcome.PASS,
        "EVT_AUDIT_KNOWLEDGE_LAYERS_VALID",
        _all_claims(case),
    )


def evaluate_party_links_and_earliest_fact(case: Stage4EventCase) -> PartyEventAssessment:
    """Evaluate FR-EVT-003 party roles and deterministic earliest public fact."""

    if not isinstance(case, Stage4EventCase):
        raise TypeError("case must be a Stage4EventCase")
    claims = tuple(link.assessment for link in case.party_links if link.assessment is not None)
    by_fact = {fact.provider_fact_id: fact for fact in case.knowledge_graph.facts}
    if not case.earliest_fact_candidate_ids:
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.BLOCKED, "EVT_EARLIEST_CANDIDATES_MISSING"),
            None,
            False,
        )
    candidates: list[FactKnowledge] = []
    for fact_id in case.earliest_fact_candidate_ids:
        fact = by_fact.get(fact_id)
        if (
            fact is None
            or fact.available_at is None
            or fact.available_at > case.knowledge_cutoff
            or not fact.authorized_public
            or not fact.reviewed
            or fact.is_mnpi
            or not fact.authority_clear
        ):
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.BLOCKED, "EVT_EARLIEST_CANDIDATE_INVALID", claims
                ),
                None,
                False,
            )
        candidates.append(fact)
    selected = min(candidates, key=lambda fact: (fact.available_at, fact.provider_fact_id))
    if selected.provider_fact_id != case.declared_earliest_legal_public_fact_id:
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.BLOCKED, "EVT_EARLIEST_FACT_MISMATCH", claims),
            selected.provider_fact_id,
            False,
        )

    by_role = {link.role: link for link in case.party_links}
    if len(by_role) != len(case.party_links) or set(by_role) != set(PartyRole):
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.BLOCKED, "EVT_PARTY_ROLE_SET_INVALID", claims),
            selected.provider_fact_id,
            False,
        )
    for link in case.party_links:
        if link.applicability is PartyLinkApplicability.NOT_APPLICABLE:
            if (
                link.role is not PartyRole.PROCUREMENT_ACTOR
                or link.assessment is not None
                or link.legal_entity_id is not None
            ):
                return PartyEventAssessment(
                    _assessment(
                        "FR-EVT-003",
                        GateOutcome.BLOCKED,
                        "EVT_PARTY_NOT_APPLICABLE_INVALID",
                        claims,
                    ),
                    selected.provider_fact_id,
                    False,
                )
            continue
        if link.assessment is None:
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.BLOCKED, "EVT_PARTY_ASSESSMENT_MISSING", claims
                ),
                selected.provider_fact_id,
                False,
            )
        if link.assessment.conclusion is EvidenceConclusion.CONFIRMED and (
            link.legal_entity_id is None
            or link.link_kind is None
            or link.relation is None
            or not link.lineage_group_ids
            or link.valid_from is None
            or link.valid_from > case.knowledge_cutoff
            or (link.valid_to is not None and case.knowledge_cutoff >= link.valid_to)
        ):
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.BLOCKED, "EVT_CONFIRMED_PARTY_LINK_INVALID", claims
                ),
                selected.provider_fact_id,
                False,
            )

    required = (
        by_role[PartyRole.LISTED_COMPANY],
        by_role[PartyRole.ECONOMIC_BENEFICIARY],
        by_role[PartyRole.SELLER_SUPPLIER],
    )
    if any(
        link.assessment is not None and link.assessment.conclusion is EvidenceConclusion.REFUTED
        for link in required
    ):
        return PartyEventAssessment(
            _assessment(
                "FR-EVT-003", GateOutcome.REJECT, "EVT_REQUIRED_PARTY_LINK_REFUTED", claims
            ),
            selected.provider_fact_id,
            False,
        )
    if any(
        link.assessment is None
        or link.assessment.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for link in required
    ):
        return PartyEventAssessment(
            _assessment(
                "FR-EVT-003", GateOutcome.ABSTAIN, "EVT_REQUIRED_PARTY_LINK_UNRESOLVED", claims
            ),
            selected.provider_fact_id,
            False,
        )

    buyer = by_role[PartyRole.CUSTOMER_BUYER]
    if buyer.assessment is None:
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.BLOCKED, "EVT_BUYER_ASSESSMENT_MISSING", claims),
            selected.provider_fact_id,
            False,
        )
    if buyer.assessment.conclusion is EvidenceConclusion.REFUTED:
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.REJECT, "EVT_BUYER_LINK_REFUTED", claims),
            selected.provider_fact_id,
            False,
        )
    if buyer.assessment.conclusion is EvidenceConclusion.CONFLICTED:
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.ABSTAIN, "EVT_BUYER_LINK_CONFLICTED", claims),
            selected.provider_fact_id,
            False,
        )
    if buyer.assessment.conclusion is EvidenceConclusion.UNKNOWN:
        if not buyer.legally_confidential or buyer.legal_entity_id is not None:
            return PartyEventAssessment(
                _assessment("FR-EVT-003", GateOutcome.ABSTAIN, "EVT_BUYER_LINK_UNKNOWN", claims),
                selected.provider_fact_id,
                False,
            )
        return PartyEventAssessment(
            _assessment("FR-EVT-003", GateOutcome.PASS, "EVT_CONFIDENTIAL_BUYER_ACCEPTED", claims),
            selected.provider_fact_id,
            False,
        )

    procurement = by_role[PartyRole.PROCUREMENT_ACTOR]
    if procurement.applicability is PartyLinkApplicability.APPLICABLE:
        if procurement.assessment is None:
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.BLOCKED, "EVT_PROCUREMENT_ASSESSMENT_MISSING", claims
                ),
                selected.provider_fact_id,
                False,
            )
        if procurement.assessment.conclusion is EvidenceConclusion.REFUTED:
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.REJECT, "EVT_PROCUREMENT_LINK_REFUTED", claims
                ),
                selected.provider_fact_id,
                False,
            )
        if procurement.assessment.conclusion in (
            EvidenceConclusion.UNKNOWN,
            EvidenceConclusion.CONFLICTED,
        ):
            return PartyEventAssessment(
                _assessment(
                    "FR-EVT-003", GateOutcome.ABSTAIN, "EVT_PROCUREMENT_LINK_UNRESOLVED", claims
                ),
                selected.provider_fact_id,
                False,
            )
    seller_groups = set(by_role[PartyRole.SELLER_SUPPLIER].lineage_group_ids)
    buyer_groups = set(buyer.lineage_group_ids)
    cross_party_ready = bool(buyer_groups and buyer_groups.isdisjoint(seller_groups))
    return PartyEventAssessment(
        _assessment(
            "FR-EVT-003", GateOutcome.PASS, "EVT_PARTY_LINKS_AND_EARLIEST_FACT_VALID", claims
        ),
        selected.provider_fact_id,
        cross_party_ready,
    )


def _independent_gate_evidence_ready(chains: tuple[PublicEvidenceChain, ...]) -> bool:
    for first, second in combinations(chains, 2):
        if (
            first.responsible_publisher_id != second.responsible_publisher_id
            and first.acquisition_lineage_id != second.acquisition_lineage_id
            and (first.contains_authoritative_original or second.contains_authoritative_original)
        ):
            return True
    return False


def evaluate_e4_public(
    value: E4PublicInput,
    party_assessment: PartyEventAssessment,
) -> E4PublicAssessment:
    """Evaluate FR-EVT-002 strict E4 closure independently from later gates."""

    if not isinstance(value, E4PublicInput):
        raise TypeError("value must be an E4PublicInput")
    if not isinstance(party_assessment, PartyEventAssessment):
        raise TypeError("party_assessment must be a PartyEventAssessment")
    claims = value.claims
    readiness = _independent_gate_evidence_ready(value.public_evidence_chains)
    quantification = value.economic_quantification
    if party_assessment.assessment.outcome is GateOutcome.BLOCKED:
        assessment = _assessment(
            "FR-EVT-002", GateOutcome.BLOCKED, "EVT_E4_PARTY_OR_PIT_BLOCKED", claims
        )
    elif party_assessment.assessment.outcome is GateOutcome.REJECT or any(
        claim.conclusion is EvidenceConclusion.REFUTED for claim in claims
    ):
        assessment = _assessment(
            "FR-EVT-002", GateOutcome.REJECT, "EVT_E4_STRICT_CLAIM_REFUTED", claims
        )
    elif party_assessment.assessment.outcome is GateOutcome.ABSTAIN or any(
        claim.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
        for claim in claims
    ):
        assessment = _assessment(
            "FR-EVT-002", GateOutcome.ABSTAIN, "EVT_E4_STRICT_CLAIM_UNRESOLVED", claims
        )
    else:
        direct_requirements = {
            E4ClosureClaim.SIGNED_OR_FORMALLY_ORDERED,
            E4ClosureClaim.EFFECTIVE_OR_CONDITIONS_SATISFIED,
            E4ClosureClaim.BINDING_MINIMUM_OBLIGATION,
        }
        has_authoritative_original = any(
            direct_requirements.issubset(original.directly_supports)
            for original in value.authoritative_originals
        )
        if not has_authoritative_original:
            assessment = _assessment(
                "FR-EVT-002", GateOutcome.ABSTAIN, "EVT_E4_AUTHORITATIVE_ORIGINAL_MISSING", claims
            )
        elif quantification is EconomicQuantification.UNKNOWN:
            assessment = _assessment(
                "FR-EVT-002",
                GateOutcome.ABSTAIN,
                "EVT_E4_MINIMUM_OBLIGATION_QUANTIFICATION_UNKNOWN",
                claims,
            )
        else:
            assessment = _assessment(
                "FR-EVT-002", GateOutcome.PASS, "EVT_E4_PUBLIC_CONFIRMED", claims
            )
    return E4PublicAssessment(
        assessment=assessment,
        independent_gate_evidence_ready=readiness,
        economic_quantification=quantification,
        future_profit_gate_must_abstain=(
            assessment.outcome is GateOutcome.PASS
            and quantification is EconomicQuantification.CONFIDENTIAL_UNKNOWN
        ),
    )


def _aggregate_or(claims: tuple[EventPassportClaim, ...]) -> EvidenceConclusion:
    conclusions = tuple(item.assessment.conclusion for item in claims)
    if any(value is EvidenceConclusion.CONFIRMED for value in conclusions):
        return EvidenceConclusion.CONFIRMED
    if any(value is EvidenceConclusion.CONFLICTED for value in conclusions):
        return EvidenceConclusion.CONFLICTED
    if any(value is EvidenceConclusion.UNKNOWN for value in conclusions) or not conclusions:
        return EvidenceConclusion.UNKNOWN
    return EvidenceConclusion.REFUTED


def _aggregate_and(claims: tuple[EvidenceClaim, ...]) -> EvidenceConclusion:
    conclusions = tuple(claim.conclusion for claim in claims)
    if any(value is EvidenceConclusion.REFUTED for value in conclusions):
        return EvidenceConclusion.REFUTED
    if any(value is EvidenceConclusion.CONFLICTED for value in conclusions):
        return EvidenceConclusion.CONFLICTED
    if any(value is EvidenceConclusion.UNKNOWN for value in conclusions):
        return EvidenceConclusion.UNKNOWN
    return EvidenceConclusion.CONFIRMED


def _state_result(
    assessment: Stage4EventRuleAssessment,
    attained: Iterable[EventState],
    *,
    highest: EventState | None,
    candidate: EventState | None = None,
    terminal: TerminalEventType | None = None,
    revision_created: bool = True,
    duplicate: bool = False,
    last_confirmed: EventState | None = None,
) -> EventStateAssessment:
    return EventStateAssessment(
        assessment=assessment,
        attained_states=tuple(attained),
        highest_nonterminal_state=highest,
        candidate_highest_nonterminal_state=candidate if candidate is not None else highest,
        terminal_type=terminal,
        revision_created=revision_created,
        duplicate_observation=duplicate,
        last_confirmed_state=last_confirmed,
    )


def _validate_revision(
    revision: EventRevisionInput,
    rules: ApprovedStage4EventRules,
) -> tuple[Stage4EventRuleAssessment | None, bool]:
    previous = revision.previous_snapshot
    if previous is None:
        if (
            revision.revision != 1
            or revision.supersedes_event_snapshot_id is not None
            or revision.duplicate_observation
        ):
            return (
                _assessment("FR-EVT-001", GateOutcome.BLOCKED, "EVT_INITIAL_REVISION_INVALID"),
                False,
            )
        return None, False
    if previous.logical_event_id != revision.logical_event_id:
        return _assessment("FR-EVT-001", GateOutcome.BLOCKED, "EVT_LOGICAL_EVENT_ID_DRIFT"), False
    if revision.duplicate_observation:
        if (
            revision.content_hash != previous.content_hash
            or revision.event_snapshot_id != previous.event_snapshot_id
            or revision.revision != previous.revision
            or revision.supersedes_event_snapshot_id is not None
        ):
            return _assessment(
                "FR-EVT-001", GateOutcome.BLOCKED, "EVT_DUPLICATE_OBSERVATION_INVALID"
            ), False
        return None, True
    if (
        revision.content_hash == previous.content_hash
        or revision.event_snapshot_id == previous.event_snapshot_id
        or revision.revision != previous.revision + 1
        or revision.supersedes_event_snapshot_id != previous.event_snapshot_id
    ):
        return _assessment(
            "FR-EVT-001", GateOutcome.BLOCKED, "EVT_APPEND_ONLY_REVISION_INVALID"
        ), False
    if previous.rule_bundle_hash != rules.bundle_hash:
        replay = revision.migration_replay
        if (
            replay is None
            or not replay.replayable
            or replay.from_rule_bundle_hash != previous.rule_bundle_hash
            or replay.to_rule_bundle_hash != rules.bundle_hash
            or replay.fixed_input_hash != revision.content_hash
        ):
            return _assessment(
                "FR-EVT-001", GateOutcome.BLOCKED, "EVT_RULE_MIGRATION_REPLAY_INVALID"
            ), False
    elif revision.migration_replay is not None:
        return _assessment(
            "FR-EVT-001", GateOutcome.BLOCKED, "EVT_UNNECESSARY_MIGRATION_REPLAY"
        ), False
    return None, False


def evaluate_event_state(
    passports: EventPassportInput,
    e4: E4PublicAssessment,
    revision: EventRevisionInput,
    rules: ApprovedStage4EventRules,
) -> EventStateAssessment:
    """Evaluate FR-EVT-001 passports, terminal state, revision, and migration."""

    revision_error, duplicate = _validate_revision(revision, rules)
    previous = revision.previous_snapshot
    if revision_error is not None:
        return _state_result(
            revision_error,
            (),
            highest=None,
            revision_created=False,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    if duplicate and previous is not None:
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.PASS, "EVT_DUPLICATE_OBSERVATION_REUSED"),
            (),
            highest=previous.highest_nonterminal_state,
            revision_created=False,
            duplicate=True,
            last_confirmed=previous.highest_nonterminal_state,
        )
    claims = passports.claims
    attained: list[EventState] = []
    narrative = passports.narrative.conclusion
    if narrative is EvidenceConclusion.REFUTED:
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.REJECT, "EVT_E0_NARRATIVE_REFUTED", claims),
            attained,
            highest=None,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    if narrative in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.ABSTAIN, "EVT_E0_NARRATIVE_UNRESOLVED", claims),
            attained,
            highest=None,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    attained.append(EventState.E0)
    highest = EventState.E0
    confirmed_terminals = tuple(
        item
        for item in passports.terminal_claims
        if item.assessment.conclusion is EvidenceConclusion.CONFIRMED
    )
    if len(confirmed_terminals) > 1:
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.ABSTAIN, "EVT_TERMINAL_TYPE_AMBIGUOUS", claims),
            attained,
            highest=None,
            candidate=highest,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    if confirmed_terminals:
        early_terminal = confirmed_terminals[0].terminal_type
        previous_rank = (
            _EVENT_STATE_RANK[previous.highest_nonterminal_state] if previous is not None else -1
        )
        if early_terminal is TerminalEventType.THESIS_COMPLETED or (
            early_terminal is TerminalEventType.CONTRACT_TERMINATED
            and previous_rank >= _EVENT_STATE_RANK[EventState.E4]
        ):
            attained.append(EventState.E7)
            historical_highest = (
                previous.highest_nonterminal_state if previous is not None else EventState.E0
            )
            return _state_result(
                _assessment(
                    "FR-EVT-001",
                    GateOutcome.PASS,
                    "EVT_EXPLICIT_TERMINAL_STATE_CLASSIFIED",
                    claims,
                ),
                attained,
                highest=historical_highest,
                terminal=early_terminal,
                last_confirmed=historical_highest,
            )
    later_positive = e4.assessment.outcome is GateOutcome.PASS
    stage_values = (
        (EventState.E1, _aggregate_or(passports.e1_claims)),
        (EventState.E2, _aggregate_or(passports.e2_claims)),
        (EventState.E3, _aggregate_or(passports.e3_claims)),
    )
    for state, conclusion in stage_values:
        if conclusion is EvidenceConclusion.CONFIRMED:
            attained.append(state)
            highest = state
            continue
        if conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
            return _state_result(
                _assessment(
                    "FR-EVT-001",
                    GateOutcome.ABSTAIN,
                    "EVT_INTERMEDIATE_PASSPORT_UNRESOLVED",
                    claims,
                ),
                attained,
                highest=None,
                candidate=highest,
                last_confirmed=(previous.highest_nonterminal_state if previous else None),
            )
        if later_positive:
            return _state_result(
                _assessment(
                    "FR-EVT-001", GateOutcome.REJECT, "EVT_INTERMEDIATE_PASSPORT_REFUTED", claims
                ),
                attained,
                highest=None,
                candidate=highest,
                last_confirmed=(previous.highest_nonterminal_state if previous else None),
            )
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.PASS, "EVT_HIGHEST_PASSPORT_CLASSIFIED", claims),
            attained,
            highest=highest,
            last_confirmed=(previous.highest_nonterminal_state if previous else highest),
        )

    if e4.assessment.outcome is GateOutcome.BLOCKED:
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.BLOCKED, "EVT_E4_BLOCKED_NO_EVENT_STATE", claims),
            (),
            highest=None,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    if e4.assessment.outcome in (GateOutcome.REJECT, GateOutcome.ABSTAIN):
        clue = passports.strong_commercial_clue.conclusion
        if clue is EvidenceConclusion.CONFIRMED:
            attained.append(EventState.E3_5)
            outcome = (
                GateOutcome.PASS
                if e4.assessment.outcome is GateOutcome.REJECT
                else GateOutcome.ABSTAIN
            )
            state_result = _state_result(
                _assessment("FR-EVT-001", outcome, "EVT_E3_5_CLASSIFIED", claims),
                attained,
                highest=EventState.E3_5,
                last_confirmed=(
                    previous.highest_nonterminal_state
                    if previous and outcome is GateOutcome.ABSTAIN
                    else EventState.E3_5
                ),
            )
            return _apply_downgrade_policy(state_result, revision)
        if clue in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
            return _state_result(
                _assessment(
                    "FR-EVT-001",
                    GateOutcome.ABSTAIN,
                    "EVT_STRONG_COMMERCIAL_CLUE_UNRESOLVED",
                    claims,
                ),
                attained,
                highest=None,
                candidate=EventState.E3,
                last_confirmed=(previous.highest_nonterminal_state if previous else None),
            )
        state_result = _state_result(
            _assessment("FR-EVT-001", GateOutcome.PASS, "EVT_HIGHEST_PASSPORT_CLASSIFIED", claims),
            attained,
            highest=EventState.E3,
            last_confirmed=(previous.highest_nonterminal_state if previous else EventState.E3),
        )
        return _apply_downgrade_policy(state_result, revision)

    attained.append(EventState.E4)
    highest = EventState.E4
    e5 = _aggregate_or(passports.e5_claims)
    if e5 in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.ABSTAIN, "EVT_E5_PASSPORT_UNRESOLVED", claims),
            attained,
            highest=None,
            candidate=highest,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    if e5 is EvidenceConclusion.CONFIRMED:
        attained.append(EventState.E5)
        highest = EventState.E5
        e6 = _aggregate_and(
            (
                passports.revenue_validation,
                passports.incremental_profit_validation,
                passports.cash_collection_validation,
            )
        )
        if e6 in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED):
            return _state_result(
                _assessment(
                    "FR-EVT-001", GateOutcome.ABSTAIN, "EVT_E6_PASSPORT_UNRESOLVED", claims
                ),
                attained,
                highest=None,
                candidate=highest,
                last_confirmed=(previous.highest_nonterminal_state if previous else None),
            )
        if e6 is EvidenceConclusion.CONFIRMED:
            attained.append(EventState.E6)
            highest = EventState.E6

    unresolved_terminals = tuple(
        item
        for item in passports.terminal_claims
        if item.assessment.conclusion in (EvidenceConclusion.UNKNOWN, EvidenceConclusion.CONFLICTED)
    )
    terminal_type: TerminalEventType | None = None
    if confirmed_terminals:
        terminal_type = confirmed_terminals[0].terminal_type
        prerequisite = {
            TerminalEventType.REPEAT_OR_SCALE: EventState.E6,
            TerminalEventType.CYCLE_MATURED: EventState.E6,
            TerminalEventType.CONTRACT_TERMINATED: EventState.E4,
            TerminalEventType.THESIS_COMPLETED: EventState.E0,
        }[terminal_type]
        if prerequisite not in attained:
            return _state_result(
                _assessment(
                    "FR-EVT-001", GateOutcome.ABSTAIN, "EVT_TERMINAL_PREREQUISITE_MISSING", claims
                ),
                attained,
                highest=None,
                candidate=highest,
                last_confirmed=(previous.highest_nonterminal_state if previous else None),
            )
        attained.append(EventState.E7)
    elif unresolved_terminals:
        return _state_result(
            _assessment("FR-EVT-001", GateOutcome.ABSTAIN, "EVT_TERMINAL_STATE_UNRESOLVED", claims),
            attained,
            highest=None,
            candidate=highest,
            last_confirmed=(previous.highest_nonterminal_state if previous else None),
        )
    state_result = _state_result(
        _assessment("FR-EVT-001", GateOutcome.PASS, "EVT_STATE_PASSPORTS_CLASSIFIED", claims),
        attained,
        highest=highest,
        terminal=terminal_type,
        last_confirmed=highest,
    )
    return _apply_downgrade_policy(state_result, revision)


def _apply_downgrade_policy(
    result: EventStateAssessment,
    revision: EventRevisionInput,
) -> EventStateAssessment:
    previous = revision.previous_snapshot
    current = result.highest_nonterminal_state
    if previous is None or current is None:
        return result
    if _EVENT_STATE_RANK[current] >= _EVENT_STATE_RANK[previous.highest_nonterminal_state]:
        return result
    refutation = revision.explicit_superseding_refutation
    if refutation is None or refutation.conclusion is not EvidenceConclusion.CONFIRMED:
        return _state_result(
            _assessment(
                "FR-EVT-001",
                GateOutcome.ABSTAIN,
                "EVT_DOWNGRADE_REQUIRES_EXPLICIT_SUPERSEDING_REFUTATION",
                (refutation,) if refutation is not None else (),
            ),
            result.attained_states,
            highest=None,
            candidate=current,
            terminal=result.terminal_type,
            revision_created=result.revision_created,
            last_confirmed=previous.highest_nonterminal_state,
        )
    return _state_result(
        _assessment(
            "FR-EVT-001",
            GateOutcome.PASS,
            "EVT_EXPLICIT_REFUTATION_DOWNGRADE_APPLIED",
            (refutation,),
        ),
        result.attained_states,
        highest=current,
        terminal=result.terminal_type,
        revision_created=result.revision_created,
        last_confirmed=previous.highest_nonterminal_state,
    )


def _empty_party(assessment: Stage4EventRuleAssessment) -> PartyEventAssessment:
    return PartyEventAssessment(assessment, None, False)


def _empty_e4(assessment: Stage4EventRuleAssessment) -> E4PublicAssessment:
    return E4PublicAssessment(
        assessment,
        False,
        EconomicQuantification.UNKNOWN,
        False,
    )


def _empty_state(assessment: Stage4EventRuleAssessment) -> EventStateAssessment:
    return _state_result(assessment, (), highest=None, revision_created=False)


def evaluate_stage4_event(
    case: Stage4EventCase,
    rules: ApprovedStage4EventRules,
) -> Stage4EventResult:
    """Run the approved 4A-2 slice in deterministic fail-closed order."""

    if not isinstance(case, Stage4EventCase):
        raise TypeError("case must be a Stage4EventCase")
    if not isinstance(rules, ApprovedStage4EventRules):
        raise TypeError("rules must be ApprovedStage4EventRules")
    overall: GateOutcome
    audit = evaluate_audit_knowledge_layers(case)
    if audit.outcome is None:
        raise TypeError("evaluated audit layers must have an outcome")
    if audit.outcome is not GateOutcome.PASS:
        party = _empty_party(_not_evaluated("FR-EVT-003", "EVT_AUDIT_LAYERS_NOT_PASS"))
        e4 = _empty_e4(_not_evaluated("FR-EVT-002", "EVT_AUDIT_LAYERS_NOT_PASS"))
        state = _empty_state(_not_evaluated("FR-EVT-001", "EVT_AUDIT_LAYERS_NOT_PASS"))
        overall = audit.outcome
    else:
        party = evaluate_party_links_and_earliest_fact(case)
        if party.assessment.outcome is GateOutcome.BLOCKED:
            e4 = _empty_e4(_not_evaluated("FR-EVT-002", "EVT_PARTY_OR_PIT_BLOCKED"))
            state = _empty_state(_not_evaluated("FR-EVT-001", "EVT_PARTY_OR_PIT_BLOCKED"))
            overall = GateOutcome.BLOCKED
        else:
            e4 = evaluate_e4_public(case.e4_public, party)
            if e4.assessment.outcome is GateOutcome.BLOCKED:
                state = _empty_state(_not_evaluated("FR-EVT-001", "EVT_E4_BLOCKED"))
                overall = GateOutcome.BLOCKED
            else:
                state = evaluate_event_state(case.passports, e4, case.revision, rules)
                if state.assessment.outcome is None:
                    raise TypeError("evaluated event state must have an outcome")
                overall = state.assessment.outcome
    if overall is None:
        raise TypeError("overall outcome cannot be None")
    return Stage4EventResult(
        case_id=case.case_id,
        audit_layers=audit,
        party_and_pit=party,
        e4_public=e4,
        event_state=state,
        overall_outcome=overall,
        rule_bundle_hash=rules.bundle_hash,
        rule_approval_id=rules.approval_id,
        rule_approval_record_hash=rules.approval_record_hash,
    )
