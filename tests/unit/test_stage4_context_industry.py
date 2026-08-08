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
from invest_system.models import GateOutcome
from invest_system.strategies.industrial_event import (
    STAGE4_4A1_RULE_APPROVAL_ID,
    STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256,
    STAGE4_4A1_RULE_BUNDLE_SHA256,
    STAGE4_4A1_RULES_SHA256,
    ApprovedStage4ContextIndustryRules,
    BeneficiaryMappingInput,
    BeneficiaryTier,
    ContextCoverage,
    ContextCoverageArea,
    ContextDisposition,
    ContextTemporalBinding,
    ContextTemporalBindingKind,
    EvidenceClaim,
    EvidenceConclusion,
    IndustryBottleneckInput,
    IndustryContextView,
    Stage4ContextIndustryCase,
    Stage4ContextIndustryCompatibilityError,
    Stage4RuleEvaluationState,
    evaluate_beneficiary_mapping,
    evaluate_context_admission,
    evaluate_historical_context,
    evaluate_industry_bottleneck,
    evaluate_stage4_context_industry,
)

RULE_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_4a1_context_industry_v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_4a1_context_industry_v0.1.0.approval.json"
)
SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A1上下文与产业映射规则包_v0.1.md"
)

AS_OF = datetime(2025, 1, 15, 0, tzinfo=UTC)
CUTOFF = datetime(2025, 1, 16, 0, tzinfo=UTC)
DECISION_AT = datetime(2025, 1, 17, 0, tzinfo=UTC)


def _claim(
    conclusion: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    *,
    name: str = "claim",
    groups: tuple[str, ...] = ("evidence_group_a",),
) -> EvidenceClaim:
    if conclusion is EvidenceConclusion.UNKNOWN:
        return EvidenceClaim(conclusion=conclusion)
    if conclusion is EvidenceConclusion.CONFLICTED:
        return EvidenceClaim(
            conclusion=conclusion,
            supporting_fact_ids=(f"fact_{name}_support",),
            conflicting_fact_ids=(f"fact_{name}_conflict",),
            independence_group_ids=groups,
        )
    return EvidenceClaim(
        conclusion=conclusion,
        supporting_fact_ids=(f"fact_{name}",),
        independence_group_ids=groups,
    )


def _coverage() -> tuple[ContextCoverage, ...]:
    return tuple(
        ContextCoverage(
            area=area,
            assessment=_claim(name=f"coverage_{index}"),
        )
        for index, area in enumerate(ContextCoverageArea)
    )


def _temporal_bindings() -> tuple[ContextTemporalBinding, ...]:
    return tuple(
        ContextTemporalBinding(
            kind=kind,
            semantic_id=f"historical_semantic_{index}",
            assessment=_claim(name=f"temporal_{index}"),
            available_at=AS_OF - timedelta(days=2),
            valid_from=AS_OF - timedelta(days=10),
            valid_to=AS_OF + timedelta(days=10),
        )
        for index, kind in enumerate(ContextTemporalBindingKind)
    )


def _context() -> IndustryContextView:
    return IndustryContextView(
        context_view_id="context_view_001",
        company_id="company_001",
        context_pack_ref="synthetic_context_pack_001",
        context_pack_version="0.1.0",
        input_id="synthetic_input_001",
        as_of=AS_OF,
        knowledge_cutoff=CUTOFF,
        decision_at=DECISION_AT,
        context_pack_available_at=AS_OF - timedelta(days=1),
        preregistered=True,
        coverage=_coverage(),
        temporal_bindings=_temporal_bindings(),
    )


def _bottleneck(
    *,
    demand: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    supply: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    substitute: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    persistence: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    dissolution: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    groups: tuple[str, ...] = ("evidence_group_a", "evidence_group_b"),
) -> IndustryBottleneckInput:
    first_group = (groups[0],)
    second_group = (groups[-1],)
    return IndustryBottleneckInput(
        node_id="industry_node_001",
        verifiable_demand=_claim(demand, name="demand", groups=first_group),
        slow_supply_response=_claim(supply, name="supply", groups=second_group),
        constrained_substitution=_claim(substitute, name="substitute", groups=first_group),
        persistence_to_next_window=_claim(
            persistence,
            name="persistence",
            groups=second_group,
        ),
        dissolution_signals_identified=_claim(
            dissolution,
            name="dissolution",
            groups=first_group,
        ),
    )


def _beneficiary(
    *,
    technical: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    qualified: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    market_share: EvidenceConclusion = EvidenceConclusion.CONFIRMED,
    groups: tuple[str, ...] = ("evidence_group_a", "evidence_group_b"),
) -> BeneficiaryMappingInput:
    first_group = (groups[0],)
    second_group = (groups[-1],)
    return BeneficiaryMappingInput(
        company_id="company_001",
        node_id="industry_node_001",
        technical_link=_claim(technical, name="technical", groups=first_group),
        qualified_supplier=_claim(qualified, name="qualified", groups=first_group),
        market_share=_claim(market_share, name="share", groups=first_group),
        realized_price=_claim(name="price", groups=second_group),
        incremental_gross_profit=_claim(name="gross_profit", groups=first_group),
        cash_collection=_claim(name="cash", groups=second_group),
        ownership_path=_claim(name="ownership", groups=first_group),
    )


def _case() -> Stage4ContextIndustryCase:
    return Stage4ContextIndustryCase(
        case_id="stage4_4a1_case_001",
        context=_context(),
        bottleneck=_bottleneck(),
        beneficiary=_beneficiary(),
    )


def _approved_rules(repository_root: Path) -> ApprovedStage4ContextIndustryRules:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    capability = RuleApprovalRegistry((approval,)).require(document)
    return ApprovedStage4ContextIndustryRules.from_approved_bundle(document, capability)


def test_4a1_rule_artifacts_bind_exact_owner_approval(repository_root: Path) -> None:
    document = rule_bundle_document_from_json_value(
        json.loads((repository_root / RULE_BUNDLE_PATH).read_text(encoding="utf-8"))
    )
    approval = rule_approval_record_from_json_value(
        json.loads((repository_root / APPROVAL_PATH).read_text(encoding="utf-8"))
    )
    specification_hash = sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest()

    assert document.bundle_hash().value == STAGE4_4A1_RULE_BUNDLE_SHA256
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_id == STAGE4_4A1_RULE_APPROVAL_ID
    assert approval.canonical_sha256() == STAGE4_4A1_RULE_APPROVAL_RECORD_SHA256
    document_binding = document.rules["document_binding"]
    assert isinstance(document_binding, Mapping)
    document_hash = document_binding["hash"]
    assert isinstance(document_hash, Mapping)
    assert document_hash["value"] == specification_hash
    from invest_system.canonical import canonical_sha256

    assert canonical_sha256(document.rules) == STAGE4_4A1_RULES_SHA256
    rules = _approved_rules(repository_root)
    assert rules.minimum_independent_evidence_groups == 2


def test_fr_ctx_001_complete_context_enters_decision_pool() -> None:
    assessment = evaluate_context_admission(_context())

    assert assessment.outcome is GateOutcome.PASS
    assert assessment.reason_codes == ("CTX_DECISION_POOL_ADMITTED",)


def test_fr_ctx_001_non_preregistered_company_is_rejected() -> None:
    assessment = evaluate_context_admission(replace(_context(), preregistered=False))

    assert assessment.outcome is GateOutcome.REJECT


def test_fr_ctx_001_requires_exactly_all_ten_coverage_areas() -> None:
    complete = evaluate_context_admission(_context())
    incomplete = evaluate_context_admission(replace(_context(), coverage=_coverage()[:-1]))

    assert len(_coverage()) == 10
    assert complete.outcome is GateOutcome.PASS
    assert incomplete.outcome is GateOutcome.BLOCKED


def test_fr_ctx_001_missing_context_pack_identity_blocks() -> None:
    assessment = evaluate_context_admission(replace(_context(), context_pack_ref=""))

    assert assessment.outcome is GateOutcome.BLOCKED
    assert assessment.reason_codes == ("CTX_CONTEXT_PACK_IDENTITY_MISSING",)


def test_fr_ctx_001_unknown_coverage_abstains() -> None:
    coverage = list(_coverage())
    coverage[0] = replace(coverage[0], assessment=_claim(EvidenceConclusion.UNKNOWN))

    assessment = evaluate_context_admission(replace(_context(), coverage=tuple(coverage)))

    assert assessment.outcome is GateOutcome.ABSTAIN


def test_fr_ctx_002_historical_bindings_pass_without_hindsight() -> None:
    assessment = evaluate_historical_context(_context())

    assert assessment.outcome is GateOutcome.PASS
    assert assessment.reason_codes == ("CTX_HISTORICAL_BINDINGS_VALID",)


def test_fr_ctx_002_right_boundary_or_future_fact_blocks() -> None:
    bindings = list(_temporal_bindings())
    bindings[0] = replace(bindings[0], valid_to=AS_OF)
    right_boundary = evaluate_historical_context(
        replace(_context(), temporal_bindings=tuple(bindings))
    )
    future_binding = replace(
        _temporal_bindings()[0],
        available_at=CUTOFF + timedelta(microseconds=1),
    )
    future = evaluate_historical_context(
        replace(
            _context(),
            temporal_bindings=(future_binding, *_temporal_bindings()[1:]),
        )
    )

    assert right_boundary.outcome is GateOutcome.BLOCKED
    assert future.outcome is GateOutcome.BLOCKED


def test_fr_ctx_002_left_closed_boundary_passes() -> None:
    bindings = tuple(replace(binding, valid_from=AS_OF) for binding in _temporal_bindings())

    assessment = evaluate_historical_context(replace(_context(), temporal_bindings=bindings))

    assert assessment.outcome is GateOutcome.PASS


def test_fr_ctx_002_unrecoverable_historical_binding_abstains() -> None:
    bindings = list(_temporal_bindings())
    bindings[1] = ContextTemporalBinding(
        kind=bindings[1].kind,
        semantic_id="historical_semantic_unrecoverable",
        assessment=_claim(EvidenceConclusion.UNKNOWN),
        available_at=None,
        valid_from=None,
    )

    assessment = evaluate_historical_context(replace(_context(), temporal_bindings=tuple(bindings)))

    assert assessment.outcome is GateOutcome.ABSTAIN


def test_fr_ctx_002_confirmed_binding_without_time_blocks() -> None:
    bindings = list(_temporal_bindings())
    bindings[0] = replace(bindings[0], available_at=None, valid_from=None, valid_to=None)

    assessment = evaluate_historical_context(replace(_context(), temporal_bindings=tuple(bindings)))

    assert assessment.outcome is GateOutcome.BLOCKED
    assert assessment.reason_codes == ("CTX_CONFIRMED_BINDING_TIME_MISSING",)


def test_fr_ind_001_all_five_claims_confirm_bottleneck() -> None:
    assessment = evaluate_industry_bottleneck(_bottleneck())

    assert assessment.outcome is GateOutcome.PASS
    assert assessment.reason_codes == ("IND_BOTTLENECK_QUALIFIED",)


def test_fr_ind_001_refuted_core_claim_rejects() -> None:
    assessment = evaluate_industry_bottleneck(_bottleneck(supply=EvidenceConclusion.REFUTED))

    assert assessment.outcome is GateOutcome.REJECT


def test_fr_ind_001_exactly_two_independent_groups_pass() -> None:
    assessment = evaluate_industry_bottleneck(
        _bottleneck(groups=("evidence_group_a", "evidence_group_b"))
    )

    assert assessment.outcome is GateOutcome.PASS


@pytest.mark.parametrize(
    "bottleneck",
    [
        _bottleneck(demand=EvidenceConclusion.UNKNOWN),
        _bottleneck(groups=("evidence_group_a",)),
    ],
)
def test_fr_ind_001_unknown_or_single_source_abstains(
    bottleneck: IndustryBottleneckInput,
) -> None:
    assessment = evaluate_industry_bottleneck(bottleneck)

    assert assessment.outcome is GateOutcome.ABSTAIN


def test_fr_ind_002_profit_beneficiary_enters_four_gate_queue() -> None:
    assessment, tier = evaluate_beneficiary_mapping(_beneficiary())

    assert assessment.outcome is GateOutcome.PASS
    assert tier is BeneficiaryTier.PROFIT_BENEFICIARY


def test_fr_ind_002_refuted_profit_claim_stays_qualified_supplier() -> None:
    assessment, tier = evaluate_beneficiary_mapping(
        _beneficiary(market_share=EvidenceConclusion.REFUTED)
    )

    assert assessment.outcome is GateOutcome.REJECT
    assert tier is BeneficiaryTier.QUALIFIED_SUPPLIER


def test_fr_ind_002_prerequisite_inconsistency_blocks() -> None:
    assessment, tier = evaluate_beneficiary_mapping(
        _beneficiary(technical=EvidenceConclusion.UNKNOWN)
    )

    assert assessment.outcome is GateOutcome.BLOCKED
    assert tier is BeneficiaryTier.NONE


def test_fr_ind_002_unknown_profit_claim_abstains_at_qualified_supplier() -> None:
    assessment, tier = evaluate_beneficiary_mapping(
        _beneficiary(market_share=EvidenceConclusion.UNKNOWN)
    )

    assert assessment.outcome is GateOutcome.ABSTAIN
    assert tier is BeneficiaryTier.QUALIFIED_SUPPLIER


def test_approved_4a1_slice_reaches_four_gate_queue_without_trade_authority(
    repository_root: Path,
) -> None:
    result = evaluate_stage4_context_industry(_case(), _approved_rules(repository_root))

    assert result.context_disposition is ContextDisposition.DECISION_POOL
    assert result.bottleneck_qualified is True
    assert result.beneficiary_tier is BeneficiaryTier.PROFIT_BENEFICIARY
    assert result.four_gate_eligible is True
    assert result.synthetic is True
    assert result.validation_only is True
    assert result.authorizes_backtest is False
    assert result.authorizes_paper is False
    assert result.authorizes_shadow is False
    assert result.authorizes_live is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False


def test_historical_context_failure_short_circuits_all_downstream_rules(
    repository_root: Path,
) -> None:
    context = replace(_context(), knowledge_cutoff=DECISION_AT + timedelta(seconds=1))
    result = evaluate_stage4_context_industry(
        replace(_case(), context=context),
        _approved_rules(repository_root),
    )

    assert result.historical_context.outcome is GateOutcome.BLOCKED
    assert result.context_admission.evaluation_state is Stage4RuleEvaluationState.NOT_EVALUATED
    assert result.bottleneck_assessment.evaluation_state is (
        Stage4RuleEvaluationState.NOT_EVALUATED
    )
    assert result.beneficiary_assessment.evaluation_state is (
        Stage4RuleEvaluationState.NOT_EVALUATED
    )
    assert result.context_disposition is ContextDisposition.RESEARCH_QUARANTINE
    assert result.four_gate_eligible is False


def test_stage2b_scope_cannot_authorize_4a1(repository_root: Path) -> None:
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

    with pytest.raises(Stage4ContextIndustryCompatibilityError) as exc_info:
        ApprovedStage4ContextIndustryRules.from_approved_bundle(document, capability)
    assert exc_info.value.code == "STAGE4_4A1_RULE_SCOPE_UNSUPPORTED"


def test_4a1_typed_rules_cannot_be_forged_without_registry_capability() -> None:
    from invest_system.models import HashDigest

    with pytest.raises(Stage4ContextIndustryCompatibilityError) as exc_info:
        ApprovedStage4ContextIndustryRules(
            _issuer=object(),
            bundle_hash=HashDigest(algorithm="sha256", value="0" * 64),
            approval_record_hash=HashDigest(algorithm="sha256", value="1" * 64),
            approval_id=STAGE4_4A1_RULE_APPROVAL_ID,
            minimum_independent_evidence_groups=2,
        )
    assert exc_info.value.code == "STAGE4_4A1_RULE_ISSUER_INVALID"


def test_4a1_approved_items_do_not_issue_complete_stage4_capability(
    repository_root: Path,
) -> None:
    from invest_system.strategies.industrial_event import (
        Stage4RuleReadinessError,
        stage4_rule_inventory_from_json_value,
    )

    inventory_path = repository_root / (
        "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
        "industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json"
    )
    inventory = stage4_rule_inventory_from_json_value(
        json.loads(inventory_path.read_text(encoding="utf-8"))
    )

    assert len(inventory.unapproved_requirement_ids) == 3
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        inventory.require_complete()
    assert exc_info.value.code == "STAGE4_RULES_NOT_FULLY_APPROVED"
