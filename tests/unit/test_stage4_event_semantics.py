from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system import RuleApprovalRecord, RuleApprovalRegistry, RuleApprovalScope
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import EventState, GateOutcome, HashDigest
from invest_system.strategies.industrial_event.stage4_context_industry import (
    EvidenceClaim,
    EvidenceConclusion,
    Stage4RuleEvaluationState,
)
from invest_system.strategies.industrial_event.stage4_event_semantics import (
    STAGE4_4A2_RULE_APPROVAL_ID,
    STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A2_RULE_BUNDLE_SHA256,
    STAGE4_4A2_RULES_SHA256,
    ApprovedStage4EventRules,
    AssumptionKnowledge,
    AuditKnowledgeGraph,
    AuthoritativeOriginal,
    DerivedKnowledge,
    E4ClosureClaim,
    E4PublicInput,
    EconomicQuantification,
    EventPassportClaim,
    EventPassportInput,
    EventRevisionInput,
    EventSnapshotRef,
    FactKnowledge,
    JudgmentKnowledge,
    PartyLink,
    PartyLinkApplicability,
    PartyLinkKind,
    PartyRole,
    PassportClaimKind,
    PublicEvidenceChain,
    RuleMigrationReplay,
    Stage4EventCase,
    Stage4EventCompatibilityError,
    TerminalEventClaim,
    TerminalEventType,
    evaluate_stage4_event,
)

RULE_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_4a2_event_semantics_v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_4a2_event_semantics_v0.1.0.approval.json"
)
APPROVAL_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层批准记录_v0.1.md"
)
DRAFT_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层规则包_v0.1.md"
)

AS_OF = datetime(2025, 1, 10, tzinfo=UTC)
CUTOFF = datetime(2025, 1, 15, tzinfo=UTC)
DECISION_AT = datetime(2025, 1, 16, tzinfo=UTC)
INPUT_REF = "synthetic_stage4_4a2_input"

FACT_NAMES = (
    "party_listed",
    "party_economic",
    "party_seller",
    "party_buyer",
    "party_procurement",
    "e4_authorized",
    "e4_ownership",
    "e4_signed",
    "e4_effective",
    "e4_binding",
    "e4_zeroable",
    "contract_original",
    "buyer_chain",
    "narrative",
    "e1",
    "e2",
    "e3",
    "strong",
    "e5",
    "revenue",
    "profit",
    "cash",
    "terminal",
    "earliest_a",
    "earliest_b",
    "refutation",
    "conflict_support",
    "conflict_against",
)


def _hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _claim(
    name: str,
    conclusion: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    *,
    group: str | None = None,
) -> EvidenceClaim:
    if conclusion is EvidenceConclusion.UNKNOWN:
        return EvidenceClaim(conclusion=conclusion)
    evidence_group = group or f"group_{name}"
    if conclusion is EvidenceConclusion.CONFLICTED:
        return EvidenceClaim(
            conclusion=conclusion,
            supporting_fact_ids=("fact_conflict_support",),
            conflicting_fact_ids=("fact_conflict_against",),
            independence_group_ids=(evidence_group,),
        )
    return EvidenceClaim(
        conclusion=conclusion,
        supporting_fact_ids=(f"fact_{name}",),
        independence_group_ids=(evidence_group,),
    )


def _fact(name: str, *, available_at: datetime | None = AS_OF) -> FactKnowledge:
    return FactKnowledge(
        provider_fact_id=f"fact_{name}",
        subject=f"subject {name}",
        predicate=f"predicate {name}",
        value_ref=f"value {name}",
        available_at=available_at,
        evidence_ids=(f"evidence_{name}",),
        input_ref=INPUT_REF,
        lineage_group_id=f"lineage_{name}",
    )


def _knowledge_graph() -> AuditKnowledgeGraph:
    facts = tuple(_fact(name) for name in FACT_NAMES)
    assumption = AssumptionKnowledge(
        assumption_id="assumption_base",
        as_of=AS_OF + timedelta(hours=1),
        scenario_id="scenario_base",
        rationale="Synthetic falsifiable assumption",
        dependency_ids=("fact_narrative",),
        observable_falsification_conditions=("observable_condition_1",),
        created_by="strategy_research",
        version="0.1.0",
        input_ref=INPUT_REF,
    )
    derived = DerivedKnowledge(
        derived_id="derived_base",
        formula_id="formula_base",
        formula_version="0.1.0",
        dependency_ids=("assumption_base", "fact_e4_binding"),
        scenario_id="scenario_base",
        calculation_input_hash=_hash("1"),
        result_hash=_hash("2"),
        as_of=AS_OF + timedelta(hours=2),
        created_by="strategy_research",
        version="0.1.0",
        input_ref=INPUT_REF,
    )
    judgment = JudgmentKnowledge(
        judgment_id="judgment_base",
        rule_id="FR-EVT-002",
        rule_version="0.1.0",
        rule_hash=_hash("3"),
        outcome=GateOutcome.PASS,
        reason_codes=("judgment_supported",),
        dependency_ids=("derived_base", "fact_contract_original"),
        supporting_dependency_ids=("fact_contract_original",),
        conflicting_dependency_ids=(),
        pending_question_ids=("question_1",),
        as_of=AS_OF + timedelta(hours=3),
        created_by="strategy_research",
        version="0.1.0",
        input_ref=INPUT_REF,
    )
    return AuditKnowledgeGraph(
        facts=facts,
        assumptions=(assumption,),
        derived=(derived,),
        judgments=(judgment,),
    )


def _party_links() -> tuple[PartyLink, ...]:
    return tuple(
        PartyLink(
            role=role,
            applicability=PartyLinkApplicability.APPLICABLE,
            assessment=_claim(name),
            legal_entity_id=f"entity_{name}",
            link_kind=PartyLinkKind.DIRECT,
            relation=f"verified {name} relation",
            lineage_group_ids=(f"party_lineage_{name}",),
            valid_from=AS_OF - timedelta(days=5),
        )
        for role, name in (
            (PartyRole.LISTED_COMPANY, "party_listed"),
            (PartyRole.ECONOMIC_BENEFICIARY, "party_economic"),
            (PartyRole.SELLER_SUPPLIER, "party_seller"),
            (PartyRole.CUSTOMER_BUYER, "party_buyer"),
            (PartyRole.PROCUREMENT_ACTOR, "party_procurement"),
        )
    )


def _e4(
    *,
    binding: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    quantification: EconomicQuantification = EconomicQuantification.KNOWN,
    chains: tuple[PublicEvidenceChain, ...] | None = None,
    originals: tuple[AuthoritativeOriginal, ...] | None = None,
) -> E4PublicInput:
    authoritative = AuthoritativeOriginal(
        fact_id="fact_contract_original",
        responsible_publisher_id="publisher_authority",
        acquisition_lineage_id="acquisition_authority",
        directly_supports=(
            E4ClosureClaim.SIGNED_OR_FORMALLY_ORDERED,
            E4ClosureClaim.EFFECTIVE_OR_CONDITIONS_SATISFIED,
            E4ClosureClaim.BINDING_MINIMUM_OBLIGATION,
        ),
    )
    default_chains = (
        PublicEvidenceChain(
            chain_id="chain_authority",
            fact_ids=("fact_contract_original",),
            responsible_publisher_id="publisher_authority",
            acquisition_lineage_id="acquisition_authority",
            contains_authoritative_original=True,
        ),
        PublicEvidenceChain(
            chain_id="chain_buyer",
            fact_ids=("fact_buyer_chain",),
            responsible_publisher_id="publisher_buyer",
            acquisition_lineage_id="acquisition_buyer",
            contains_authoritative_original=False,
        ),
    )
    return E4PublicInput(
        authorized_public_evidence=_claim("e4_authorized"),
        listed_company_ownership_path=_claim("e4_ownership"),
        signed_or_formally_ordered=_claim("e4_signed"),
        effective_or_conditions_satisfied=_claim("e4_effective"),
        binding_minimum_obligation=_claim("e4_binding", binding),
        minimum_not_zeroable=_claim("e4_zeroable"),
        authoritative_originals=originals if originals is not None else (authoritative,),
        public_evidence_chains=chains if chains is not None else default_chains,
        economic_quantification=quantification,
    )


def _passports(
    *,
    e2: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    strong: EvidenceConclusion = EvidenceConclusion.REFUTED,
    e5: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    revenue: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    profit: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    cash: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    terminal_claims: tuple[TerminalEventClaim, ...] = (),
) -> EventPassportInput:
    return EventPassportInput(
        narrative=_claim("narrative"),
        e1_claims=(
            EventPassportClaim(
                PassportClaimKind.RESEARCH_AND_DEVELOPMENT,
                _claim("e1"),
            ),
        ),
        e2_claims=(EventPassportClaim(PassportClaimKind.CUSTOMER_TEST, _claim("e2", e2)),),
        e3_claims=(EventPassportClaim(PassportClaimKind.PROCUREMENT_INTENT, _claim("e3")),),
        strong_commercial_clue=_claim("strong", strong),
        e5_claims=(EventPassportClaim(PassportClaimKind.DELIVERY, _claim("e5", e5)),),
        revenue_validation=_claim("revenue", revenue),
        incremental_profit_validation=_claim("profit", profit),
        cash_collection_validation=_claim("cash", cash),
        terminal_claims=terminal_claims,
    )


def _revision(
    *,
    previous: EventSnapshotRef | None = None,
    content: str = "4",
    duplicate: bool = False,
    refutation: EvidenceClaim | None = None,
    migration: RuleMigrationReplay | None = None,
) -> EventRevisionInput:
    if previous is None:
        return EventRevisionInput(
            logical_event_id="logical_event_001",
            event_snapshot_id="event_snapshot_001",
            revision=1,
            content_hash=_hash(content),
            supersedes_event_snapshot_id=None,
        )
    if duplicate:
        return EventRevisionInput(
            logical_event_id=previous.logical_event_id,
            event_snapshot_id=previous.event_snapshot_id,
            revision=previous.revision,
            content_hash=previous.content_hash,
            supersedes_event_snapshot_id=None,
            previous_snapshot=previous,
            duplicate_observation=True,
        )
    return EventRevisionInput(
        logical_event_id=previous.logical_event_id,
        event_snapshot_id="event_snapshot_002",
        revision=previous.revision + 1,
        content_hash=_hash(content),
        supersedes_event_snapshot_id=previous.event_snapshot_id,
        previous_snapshot=previous,
        explicit_superseding_refutation=refutation,
        migration_replay=migration,
    )


def _case(
    *,
    graph: AuditKnowledgeGraph | None = None,
    parties: tuple[PartyLink, ...] | None = None,
    e4: E4PublicInput | None = None,
    passports: EventPassportInput | None = None,
    revision: EventRevisionInput | None = None,
    earliest_id: str = "fact_earliest_a",
) -> Stage4EventCase:
    return Stage4EventCase(
        case_id="stage4_4a2_case_001",
        input_ref=INPUT_REF,
        knowledge_cutoff=CUTOFF,
        decision_at=DECISION_AT,
        knowledge_graph=graph or _knowledge_graph(),
        earliest_fact_candidate_ids=("fact_earliest_a", "fact_earliest_b"),
        declared_earliest_legal_public_fact_id=earliest_id,
        party_links=parties or _party_links(),
        e4_public=e4 or _e4(),
        passports=passports or _passports(),
        revision=revision or _revision(),
    )


def _approved_rules(repository_root: Path) -> ApprovedStage4EventRules:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    capability = RuleApprovalRegistry((approval,)).require(document)
    return ApprovedStage4EventRules.from_approved_bundle(document, capability)


def test_4a2_rule_artifacts_bind_exact_owner_approval(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )

    assert document.bundle_hash().value == STAGE4_4A2_RULE_BUNDLE_SHA256
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_id == STAGE4_4A2_RULE_APPROVAL_ID
    assert approval.canonical_sha256() == STAGE4_4A2_RULE_APPROVAL_RECORD_SHA256
    from invest_system.canonical import canonical_sha256

    assert canonical_sha256(document.rules) == STAGE4_4A2_RULES_SHA256
    binding = document.rules["document_binding"]
    source_binding = document.rules["approved_source_binding"]
    assert isinstance(binding, Mapping)
    binding_hash = binding["hash"]
    assert isinstance(binding_hash, Mapping)
    binding_hash_value = binding_hash["value"]
    assert isinstance(binding_hash_value, str)
    assert isinstance(source_binding, Mapping)
    source_hash = source_binding["hash"]
    assert isinstance(source_hash, Mapping)
    source_hash_value = source_hash["value"]
    assert isinstance(source_hash_value, str)
    assert (
        sha256((repository_root / APPROVAL_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == binding_hash_value
    )
    assert (
        sha256((repository_root / DRAFT_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == source_hash_value
    )


def test_fr_evt_001_complete_passports_reach_e6(repository_root: Path) -> None:
    result = evaluate_stage4_event(_case(), _approved_rules(repository_root))

    assert result.event_state.assessment.outcome is GateOutcome.PASS
    assert result.event_state.highest_nonterminal_state is EventState.E6
    assert result.event_state.attained_states == (
        EventState.E0,
        EventState.E1,
        EventState.E2,
        EventState.E3,
        EventState.E4,
        EventState.E5,
        EventState.E6,
    )
    assert result.e4_public.independent_gate_evidence_ready is True
    assert result.authorizes_backtest is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False


def test_fr_evt_001_refuted_intermediate_with_later_e4_rejects(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(
        _case(passports=_passports(e2=EvidenceConclusion.REFUTED)),
        _approved_rules(repository_root),
    )

    assert result.event_state.assessment.outcome is GateOutcome.REJECT
    assert result.event_state.highest_nonterminal_state is None
    assert result.event_state.candidate_highest_nonterminal_state is EventState.E1


def test_fr_evt_001_e7_requires_and_accepts_exact_e6_prerequisite(
    repository_root: Path,
) -> None:
    terminal = TerminalEventClaim(TerminalEventType.REPEAT_OR_SCALE, _claim("terminal"))
    result = evaluate_stage4_event(
        _case(passports=_passports(terminal_claims=(terminal,))),
        _approved_rules(repository_root),
    )

    assert result.event_state.assessment.outcome is GateOutcome.PASS
    assert result.event_state.highest_nonterminal_state is EventState.E6
    assert result.event_state.terminal_type is TerminalEventType.REPEAT_OR_SCALE
    assert result.event_state.attained_states[-1] is EventState.E7


def test_fr_evt_001_contract_termination_uses_previous_e4_without_silent_downgrade(
    repository_root: Path,
) -> None:
    rules = _approved_rules(repository_root)
    previous = EventSnapshotRef(
        logical_event_id="logical_event_001",
        event_snapshot_id="event_snapshot_001",
        revision=1,
        content_hash=_hash("4"),
        highest_nonterminal_state=EventState.E4,
        rule_bundle_hash=rules.bundle_hash,
    )
    terminal = TerminalEventClaim(TerminalEventType.CONTRACT_TERMINATED, _claim("terminal"))
    result = evaluate_stage4_event(
        _case(
            e4=_e4(binding=EvidenceConclusion.REFUTED),
            passports=_passports(
                e2=EvidenceConclusion.UNKNOWN,
                terminal_claims=(terminal,),
            ),
            revision=_revision(previous=previous, content="5"),
        ),
        rules,
    )

    assert result.event_state.assessment.outcome is GateOutcome.PASS
    assert result.event_state.highest_nonterminal_state is EventState.E4
    assert result.event_state.terminal_type is TerminalEventType.CONTRACT_TERMINATED
    assert result.event_state.attained_states[-1] is EventState.E7


def test_fr_evt_001_thesis_completion_requires_only_e0_and_explicit_closure(
    repository_root: Path,
) -> None:
    terminal = TerminalEventClaim(TerminalEventType.THESIS_COMPLETED, _claim("terminal"))
    result = evaluate_stage4_event(
        _case(
            passports=_passports(
                e2=EvidenceConclusion.UNKNOWN,
                terminal_claims=(terminal,),
            )
        ),
        _approved_rules(repository_root),
    )

    assert result.event_state.assessment.outcome is GateOutcome.PASS
    assert result.event_state.highest_nonterminal_state is EventState.E0
    assert result.event_state.terminal_type is TerminalEventType.THESIS_COMPLETED


def test_fr_evt_001_missing_intermediate_passport_abstains(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(
        _case(passports=_passports(e2=EvidenceConclusion.UNKNOWN)),
        _approved_rules(repository_root),
    )

    assert result.event_state.assessment.outcome is GateOutcome.ABSTAIN
    assert result.event_state.highest_nonterminal_state is None
    assert result.event_state.candidate_highest_nonterminal_state is EventState.E1


def test_fr_evt_001_duplicate_observation_creates_no_revision(
    repository_root: Path,
) -> None:
    rules = _approved_rules(repository_root)
    previous = EventSnapshotRef(
        logical_event_id="logical_event_001",
        event_snapshot_id="event_snapshot_001",
        revision=1,
        content_hash=_hash("4"),
        highest_nonterminal_state=EventState.E6,
        rule_bundle_hash=rules.bundle_hash,
    )
    result = evaluate_stage4_event(
        _case(revision=_revision(previous=previous, duplicate=True)),
        rules,
    )

    assert result.event_state.duplicate_observation is True
    assert result.event_state.revision_created is False
    assert result.event_state.highest_nonterminal_state is EventState.E6


def test_fr_evt_001_downgrade_requires_explicit_superseding_refutation(
    repository_root: Path,
) -> None:
    rules = _approved_rules(repository_root)
    previous = EventSnapshotRef(
        logical_event_id="logical_event_001",
        event_snapshot_id="event_snapshot_001",
        revision=1,
        content_hash=_hash("4"),
        highest_nonterminal_state=EventState.E6,
        rule_bundle_hash=rules.bundle_hash,
    )
    no_refutation = evaluate_stage4_event(
        _case(
            passports=_passports(e5=EvidenceConclusion.REFUTED),
            revision=_revision(previous=previous, content="5"),
        ),
        rules,
    )
    with_refutation = evaluate_stage4_event(
        _case(
            passports=_passports(e5=EvidenceConclusion.REFUTED),
            revision=_revision(
                previous=previous,
                content="5",
                refutation=_claim("refutation"),
            ),
        ),
        rules,
    )

    assert no_refutation.event_state.assessment.outcome is GateOutcome.ABSTAIN
    assert no_refutation.event_state.highest_nonterminal_state is None
    assert no_refutation.event_state.candidate_highest_nonterminal_state is EventState.E4
    assert no_refutation.event_state.last_confirmed_state is EventState.E6
    assert with_refutation.event_state.assessment.outcome is GateOutcome.PASS
    assert with_refutation.event_state.highest_nonterminal_state is EventState.E4


def test_fr_evt_001_rule_version_change_requires_fixed_input_replay(
    repository_root: Path,
) -> None:
    rules = _approved_rules(repository_root)
    old_hash = _hash("9")
    previous = EventSnapshotRef(
        logical_event_id="logical_event_001",
        event_snapshot_id="event_snapshot_001",
        revision=1,
        content_hash=_hash("4"),
        highest_nonterminal_state=EventState.E4,
        rule_bundle_hash=old_hash,
    )
    blocked = evaluate_stage4_event(
        _case(revision=_revision(previous=previous, content="5")),
        rules,
    )
    replay = RuleMigrationReplay(
        from_rule_bundle_hash=old_hash,
        to_rule_bundle_hash=rules.bundle_hash,
        fixed_input_hash=_hash("5"),
        replay_hash=_hash("8"),
        replayable=True,
    )
    allowed = evaluate_stage4_event(
        _case(revision=_revision(previous=previous, content="5", migration=replay)),
        rules,
    )

    assert blocked.event_state.assessment.outcome is GateOutcome.BLOCKED
    assert allowed.event_state.assessment.outcome is GateOutcome.PASS


def test_fr_evt_002_six_confirmed_claims_and_one_authoritative_original_pass(
    repository_root: Path,
) -> None:
    single_chain = (_e4().public_evidence_chains[0],)
    result = evaluate_stage4_event(
        _case(e4=_e4(chains=single_chain)),
        _approved_rules(repository_root),
    )

    assert result.e4_public.assessment.outcome is GateOutcome.PASS
    assert result.e4_public.independent_gate_evidence_ready is False


def test_fr_evt_002_explicitly_refuted_minimum_obligation_rejects_to_e3_5(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(
        _case(
            e4=_e4(binding=EvidenceConclusion.REFUTED),
            passports=_passports(strong=EvidenceConclusion.CONFIRMED),
        ),
        _approved_rules(repository_root),
    )

    assert result.e4_public.assessment.outcome is GateOutcome.REJECT
    assert result.event_state.assessment.outcome is GateOutcome.PASS
    assert result.event_state.highest_nonterminal_state is EventState.E3_5


def test_fr_evt_002_two_independent_chains_are_gate_readiness_only(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(_case(), _approved_rules(repository_root))

    assert result.e4_public.independent_gate_evidence_ready is True
    assert result.event_state.highest_nonterminal_state is EventState.E6


def test_fr_evt_002_unknown_closure_abstains_but_preserves_e3_5(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(
        _case(
            e4=_e4(binding=EvidenceConclusion.UNKNOWN),
            passports=_passports(strong=EvidenceConclusion.CONFIRMED),
        ),
        _approved_rules(repository_root),
    )

    assert result.e4_public.assessment.outcome is GateOutcome.ABSTAIN
    assert result.event_state.assessment.outcome is GateOutcome.ABSTAIN
    assert result.event_state.highest_nonterminal_state is EventState.E3_5


def test_fr_evt_002_confidential_economic_amount_passes_e4_but_abstains_profit_gate(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(
        _case(e4=_e4(quantification=EconomicQuantification.CONFIDENTIAL_UNKNOWN)),
        _approved_rules(repository_root),
    )

    assert result.e4_public.assessment.outcome is GateOutcome.PASS
    assert result.e4_public.future_profit_gate_must_abstain is True


def test_fr_evt_002_same_lineage_or_publisher_does_not_form_independent_readiness(
    repository_root: Path,
) -> None:
    first, second = _e4().public_evidence_chains
    same_publisher = replace(second, responsible_publisher_id=first.responsible_publisher_id)
    result = evaluate_stage4_event(
        _case(e4=_e4(chains=(first, same_publisher))),
        _approved_rules(repository_root),
    )

    assert result.e4_public.assessment.outcome is GateOutcome.PASS
    assert result.e4_public.independent_gate_evidence_ready is False


def test_fr_evt_003_all_roles_and_deterministic_earliest_fact_pass(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_event(_case(), _approved_rules(repository_root))

    assert result.party_and_pit.assessment.outcome is GateOutcome.PASS
    assert result.party_and_pit.earliest_legal_public_fact_id == "fact_earliest_a"
    assert result.party_and_pit.cross_party_corroboration_ready is True


def test_fr_evt_003_refuted_required_seller_link_rejects(repository_root: Path) -> None:
    links = list(_party_links())
    seller_index = next(i for i, item in enumerate(links) if item.role is PartyRole.SELLER_SUPPLIER)
    links[seller_index] = replace(
        links[seller_index],
        assessment=_claim("party_seller", EvidenceConclusion.REFUTED),
    )
    result = evaluate_stage4_event(
        _case(parties=tuple(links)),
        _approved_rules(repository_root),
    )

    assert result.party_and_pit.assessment.outcome is GateOutcome.REJECT
    assert result.e4_public.assessment.outcome is GateOutcome.REJECT


def test_fr_evt_003_same_timestamp_uses_fact_id_tie_break(repository_root: Path) -> None:
    result = evaluate_stage4_event(_case(), _approved_rules(repository_root))

    assert result.party_and_pit.earliest_legal_public_fact_id == "fact_earliest_a"


def test_fr_evt_003_wrong_declared_earliest_fact_blocks(repository_root: Path) -> None:
    result = evaluate_stage4_event(
        _case(earliest_id="fact_earliest_b"),
        _approved_rules(repository_root),
    )

    assert result.party_and_pit.assessment.outcome is GateOutcome.BLOCKED
    assert result.e4_public.assessment.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED
    assert result.overall_outcome is GateOutcome.BLOCKED


def test_fr_evt_003_legally_confidential_buyer_passes_without_cross_party_readiness(
    repository_root: Path,
) -> None:
    links = list(_party_links())
    buyer_index = next(i for i, item in enumerate(links) if item.role is PartyRole.CUSTOMER_BUYER)
    links[buyer_index] = PartyLink(
        role=PartyRole.CUSTOMER_BUYER,
        applicability=PartyLinkApplicability.APPLICABLE,
        assessment=_claim("buyer_confidential", EvidenceConclusion.UNKNOWN),
        legal_entity_id=None,
        link_kind=None,
        relation=None,
        lineage_group_ids=(),
        valid_from=None,
        legally_confidential=True,
    )
    result = evaluate_stage4_event(
        _case(parties=tuple(links)),
        _approved_rules(repository_root),
    )

    assert result.party_and_pit.assessment.outcome is GateOutcome.PASS
    assert result.party_and_pit.cross_party_corroboration_ready is False
    assert result.e4_public.assessment.outcome is GateOutcome.PASS


def test_fr_evt_003_conflicted_required_party_link_abstains(repository_root: Path) -> None:
    links = list(_party_links())
    seller_index = next(i for i, item in enumerate(links) if item.role is PartyRole.SELLER_SUPPLIER)
    links[seller_index] = replace(
        links[seller_index],
        assessment=_claim("party_seller", EvidenceConclusion.CONFLICTED),
    )
    result = evaluate_stage4_event(
        _case(parties=tuple(links)),
        _approved_rules(repository_root),
    )

    assert result.party_and_pit.assessment.outcome is GateOutcome.ABSTAIN
    assert result.e4_public.assessment.outcome is GateOutcome.ABSTAIN


def test_fr_evt_003_future_earliest_candidate_blocks(repository_root: Path) -> None:
    graph = _knowledge_graph()
    facts = tuple(
        replace(fact, available_at=CUTOFF + timedelta(seconds=1))
        if fact.provider_fact_id == "fact_earliest_a"
        else fact
        for fact in graph.facts
    )
    result = evaluate_stage4_event(
        _case(graph=replace(graph, facts=facts)),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.BLOCKED
    assert result.overall_outcome is GateOutcome.BLOCKED


def test_fr_evt_004_valid_fact_assumption_derived_judgment_graph_passes(
    repository_root: Path,
) -> None:
    case = _case()
    result = evaluate_stage4_event(case, _approved_rules(repository_root))

    assert result.audit_layers.outcome is GateOutcome.PASS
    assert case.knowledge_graph.writeback_to_kb is False
    assert case.knowledge_graph.authorizes_positions is False
    assert case.knowledge_graph.authorizes_orders is False


def test_fr_evt_004_cross_type_id_collision_blocks(repository_root: Path) -> None:
    graph = _knowledge_graph()
    collision = replace(graph.assumptions[0], assumption_id="fact_narrative")
    result = evaluate_stage4_event(
        _case(graph=replace(graph, assumptions=(collision,))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.BLOCKED
    assert result.audit_layers.reason_codes == ("EVT_KNOWLEDGE_ID_COLLISION",)


def test_fr_evt_004_derived_dependency_cycle_blocks(repository_root: Path) -> None:
    graph = _knowledge_graph()
    first = replace(graph.derived[0], dependency_ids=("derived_second",))
    second = replace(
        graph.derived[0],
        derived_id="derived_second",
        dependency_ids=("derived_base",),
        result_hash=_hash("6"),
    )
    result = evaluate_stage4_event(
        _case(graph=replace(graph, derived=(first, second))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.BLOCKED
    assert result.audit_layers.reason_codes == ("EVT_DERIVATION_CYCLE",)


def test_fr_evt_004_as_of_equal_to_latest_dependency_time_passes(
    repository_root: Path,
) -> None:
    graph = _knowledge_graph()
    boundary = replace(
        graph.derived[0],
        as_of=graph.assumptions[0].as_of,
    )
    result = evaluate_stage4_event(
        _case(graph=replace(graph, derived=(boundary,))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.PASS


def test_fr_evt_004_pass_judgment_without_support_abstains(repository_root: Path) -> None:
    graph = _knowledge_graph()
    unsupported = replace(graph.judgments[0], supporting_dependency_ids=())
    result = evaluate_stage4_event(
        _case(graph=replace(graph, judgments=(unsupported,))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.ABSTAIN
    assert result.party_and_pit.assessment.evaluation_state is (
        Stage4RuleEvaluationState.NOT_EVALUATED
    )


def test_fr_evt_004_derived_cannot_depend_on_judgment(repository_root: Path) -> None:
    graph = _knowledge_graph()
    invalid = replace(graph.derived[0], dependency_ids=("judgment_base",))
    result = evaluate_stage4_event(
        _case(graph=replace(graph, derived=(invalid,))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.BLOCKED
    assert result.audit_layers.reason_codes == ("EVT_DEPENDENCY_INVALID",)


def test_fr_evt_004_manual_override_requires_approval_reference(
    repository_root: Path,
) -> None:
    graph = _knowledge_graph()
    override = replace(
        graph.judgments[0],
        judgment_id="judgment_override",
        overrides_judgment_id="judgment_base",
        approval_ref=None,
    )
    result = evaluate_stage4_event(
        _case(graph=replace(graph, judgments=(*graph.judgments, override))),
        _approved_rules(repository_root),
    )

    assert result.audit_layers.outcome is GateOutcome.BLOCKED
    assert result.audit_layers.reason_codes == ("EVT_MANUAL_OVERRIDE_UNAPPROVED",)


def test_stage2b_scope_cannot_authorize_4a2(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approved = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    wrong_scope = RuleApprovalRecord(
        approval_id=approved.approval_id,
        strategy_id=approved.strategy_id,
        bundle_id=approved.bundle_id,
        bundle_version=approved.bundle_version,
        bundle_hash=approved.bundle_hash,
        approved_by=approved.approved_by,
        approved_at=approved.approved_at,
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref=approved.approval_source_ref,
    )
    capability = RuleApprovalRegistry((wrong_scope,)).require(document)

    with pytest.raises(Stage4EventCompatibilityError) as exc_info:
        ApprovedStage4EventRules.from_approved_bundle(document, capability)
    assert exc_info.value.code == "STAGE4_4A2_RULE_SCOPE_UNSUPPORTED"


def test_4a2_typed_rules_cannot_be_forged_without_registry_capability() -> None:
    with pytest.raises(Stage4EventCompatibilityError) as exc_info:
        ApprovedStage4EventRules(
            _issuer=object(),
            bundle_hash=_hash("0"),
            approval_record_hash=_hash("1"),
            approval_id=STAGE4_4A2_RULE_APPROVAL_ID,
            minimum_independent_public_chains=2,
        )
    assert exc_info.value.code == "STAGE4_4A2_RULE_ISSUER_INVALID"
