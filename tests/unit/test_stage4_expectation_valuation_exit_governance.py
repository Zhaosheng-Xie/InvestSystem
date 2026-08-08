from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system import RuleApprovalRecord, RuleApprovalRegistry, RuleApprovalScope
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    RuleBundleDocument,
    rule_bundle_document_from_json_value,
)
from invest_system.models import RuleStatus
from invest_system.strategies.industrial_event import (
    STAGE4_4A4_DRAFT_RULE_BUNDLE_SHA256,
    STAGE4_4A4_DRAFT_RULES_SHA256,
    STAGE4_4A4_DRAFT_SPECIFICATION_PATH,
    STAGE4_4A4_DRAFT_SPECIFICATION_SHA256,
    STAGE4_4A4_OWNER_APPROVAL_ITEM_IDS,
    STAGE4_4A4_REQUIREMENT_IDS,
    Stage4ExpectationValuationExitRuleProposalError,
    stage4_expectation_valuation_exit_rule_proposal_from_document,
    stage4_rule_inventory_from_json_value,
)

DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_4a4_expectation_valuation_exit_"
    "v0.1.0-draft.rule-bundle.json"
)
INVENTORY_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json"
)
EXPECTED_INVENTORY_SHA256 = "fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53"


def _document(repository_root: Path) -> RuleBundleDocument:
    value = json.loads((repository_root / DRAFT_BUNDLE_PATH).read_text(encoding="utf-8"))
    return rule_bundle_document_from_json_value(value)


def test_4a4_draft_artifacts_bind_exact_review_proposal(repository_root: Path) -> None:
    document = _document(repository_root)
    proposal = stage4_expectation_valuation_exit_rule_proposal_from_document(document)
    specification_path = repository_root / STAGE4_4A4_DRAFT_SPECIFICATION_PATH

    assert document.declared_status is RuleStatus.DRAFT
    assert document.bundle_hash().value == STAGE4_4A4_DRAFT_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE4_4A4_DRAFT_RULES_SHA256
    assert sha256(specification_path.read_bytes()).hexdigest() == (
        STAGE4_4A4_DRAFT_SPECIFICATION_SHA256
    )
    assert proposal.requirement_ids == STAGE4_4A4_REQUIREMENT_IDS
    assert proposal.pending_owner_approval_item_ids == STAGE4_4A4_OWNER_APPROVAL_ITEM_IDS


def test_4a4_draft_has_zero_runtime_or_trading_authority(repository_root: Path) -> None:
    proposal = stage4_expectation_valuation_exit_rule_proposal_from_document(
        _document(repository_root)
    )

    assert proposal.allowed_run_modes == ()
    assert proposal.runtime_capability_issued is False
    assert proposal.full_stage4_capability is False
    assert proposal.authorizes_backtest is False
    assert proposal.authorizes_paper is False
    assert proposal.authorizes_shadow is False
    assert proposal.authorizes_live is False
    assert proposal.authorizes_positions is False
    assert proposal.authorizes_orders is False


def test_4a4_rules_are_approved_in_stage4_inventory(repository_root: Path) -> None:
    value = json.loads((repository_root / INVENTORY_PATH).read_text(encoding="utf-8"))
    inventory = stage4_rule_inventory_from_json_value(value)
    by_id = {item.requirement_id: item for item in inventory.items}

    assert canonical_sha256(value) == EXPECTED_INVENTORY_SHA256
    assert inventory.unapproved_requirement_ids == ()
    for requirement_id in STAGE4_4A4_REQUIREMENT_IDS:
        item = by_id[requirement_id]
        assert item.status is RuleStatus.APPROVED
        assert item.approval_id == ("rule_approval_stage4_4a4_expectation_valuation_exit_v0_1_0")
        assert item.machine_rule_ref is not None
        assert item.positive_test_refs
        assert item.negative_test_refs
        assert item.boundary_test_refs
        assert item.abstain_test_refs


def test_4a4_draft_cannot_issue_capability_from_default_registry(
    repository_root: Path,
) -> None:
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry().require(_document(repository_root))


def test_4a4_draft_cannot_issue_capability_with_forged_matching_record(
    repository_root: Path,
) -> None:
    document = _document(repository_root)
    forged_approval = RuleApprovalRecord(
        approval_id="forged_4a4_draft_approval",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="test_only",
        approved_at=datetime(2026, 8, 8, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION,
        approval_source_ref="test_only",
    )

    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry((forged_approval,)).require(document)


def test_4a4_semantic_drift_fails_exact_hash_boundary(repository_root: Path) -> None:
    original = _document(repository_root)
    value = original.to_json_value()
    value["rules"]["rule_modules"]["FR-GATE-005"]["semantics"]["gate_4_calculation"][
        "minimum_net_base_remaining_return"
    ] = "0.14"
    drifted = rule_bundle_document_from_json_value(value)

    with pytest.raises(Stage4ExpectationValuationExitRuleProposalError) as exc_info:
        stage4_expectation_valuation_exit_rule_proposal_from_document(drifted)
    assert exc_info.value.code == "STAGE4_4A4_DRAFT_BUNDLE_HASH_DRIFT"


def test_4a4_cannot_self_declare_approved(repository_root: Path) -> None:
    original = _document(repository_root)
    drifted = RuleBundleDocument(
        schema_version=original.schema_version,
        strategy_id=original.strategy_id,
        bundle_id=original.bundle_id,
        bundle_version=original.bundle_version,
        declared_status=RuleStatus.APPROVED,
        rules=original.rules,
    )

    with pytest.raises(Stage4ExpectationValuationExitRuleProposalError) as exc_info:
        stage4_expectation_valuation_exit_rule_proposal_from_document(drifted)
    assert exc_info.value.code == "STAGE4_4A4_DRAFT_STATUS_UNSUPPORTED"


def test_4a4_draft_has_no_draft_approval_but_approved_version_is_separate(
    repository_root: Path,
) -> None:
    machine_directory = (repository_root / DRAFT_BUNDLE_PATH).parent

    assert not (
        machine_directory
        / "industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0-draft.approval.json"
    ).exists()
    assert [
        path.name for path in machine_directory.glob("industrial_event_stage4_4a4*.approval.json")
    ] == ["industrial_event_stage4_4a4_expectation_valuation_exit_v0.1.0.approval.json"]

    from invest_system.strategies import industrial_event

    assert hasattr(industrial_event, "evaluate_stage4_expectation_valuation_exit")
    assert not hasattr(industrial_event, "evaluate_complete_stage4")


def test_4a4_draft_contains_only_stage4_owned_rule_modules(repository_root: Path) -> None:
    document = _document(repository_root)
    modules = document.rules["rule_modules"]

    assert isinstance(modules, Mapping)
    assert set(modules) == set(STAGE4_4A4_REQUIREMENT_IDS)
    serialized = json.dumps(document.to_json_value(), ensure_ascii=False)
    assert "FR-GATE-006" not in serialized
    assert "FR-RISK" not in serialized
    assert "FR-EXEC" not in serialized


def test_4a4_draft_binds_all_three_approved_upstream_batches(
    repository_root: Path,
) -> None:
    dependencies = _document(repository_root).rules["approved_upstream_dependencies"]

    assert isinstance(dependencies, Mapping)
    assert set(dependencies) == {"4A-1", "4A-2", "4A-3"}
    stage4_4a3 = dependencies["4A-3"]
    assert isinstance(stage4_4a3, Mapping)
    assert stage4_4a3["bundle_hash"] == (
        "e6936e9c236fd7ed3a67eb8c5e01cb02d23d8fa20c8fcd7a3ccbd615220619b2"
    )
