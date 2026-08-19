from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system import RuleApprovalRecord, RuleApprovalRegistry, RuleApprovalScope
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    RuleBundleDocument,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import RuleStatus
from invest_system.strategies.industrial_event import (
    STAGE6_6A_APPROVAL_DOCUMENT_SHA256,
    STAGE6_6A_APPROVAL_SCOPE,
    STAGE6_6A_DRAFT_BUNDLE_SHA256,
    STAGE6_6A_DRAFT_OWNER_ITEMS_SHA256,
    STAGE6_6A_DRAFT_RAW_SHA256,
    STAGE6_6A_DRAFT_RULES_SHA256,
    STAGE6_6A_OWNER_APPROVAL_ITEM_IDS,
    STAGE6_6A_OWNER_APPROVAL_ITEMS_SHA256,
    STAGE6_6A_RULE_APPROVAL_ID,
    STAGE6_6A_RULE_APPROVAL_RECORD_SHA256,
    STAGE6_6A_RULE_BUNDLE_ID,
    STAGE6_6A_RULE_BUNDLE_RAW_SHA256,
    STAGE6_6A_RULE_BUNDLE_SHA256,
    STAGE6_6A_RULE_BUNDLE_VERSION,
    STAGE6_6A_RULES_SHA256,
    STAGE6_6A_SPECIFICATION_SHA256,
    Stage6ApprovalCompatibilityError,
    require_stage6a_governance_capability,
)

RULE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格")
MACHINE_DIRECTORY = RULE_DIRECTORY / "机器制品"
SPECIFICATION_PATH = RULE_DIRECTORY / "Stage6_6A历史验证预注册与准入精确规则包_v0.1.md"
APPROVAL_DOCUMENT_PATH = RULE_DIRECTORY / "Stage6_6A历史验证预注册与准入批准记录_v0.1.md"
DRAFT_PATH = (
    MACHINE_DIRECTORY / "industrial_event_stage6_6a_historical_validation_preregistration_"
    "v0.1.0-draft.rule-bundle.json"
)
APPROVED_PATH = (
    MACHINE_DIRECTORY / "industrial_event_stage6_6a_historical_validation_preregistration_"
    "v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = (
    MACHINE_DIRECTORY / "industrial_event_stage6_6a_historical_validation_preregistration_"
    "v0.1.0.approval.json"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _artifacts(
    repository_root: Path,
) -> tuple[RuleBundleDocument, RuleApprovalRecord]:
    document = rule_bundle_document_from_json_value(_json(repository_root / APPROVED_PATH))
    approval = rule_approval_record_from_json_value(_json(repository_root / APPROVAL_PATH))
    return document, approval


def _changed_document(document: RuleBundleDocument, mutate: Any) -> RuleBundleDocument:
    value = document.to_json_value()
    mutate(value["rules"])
    return rule_bundle_document_from_json_value(value)


def test_checked_in_stage6a_approval_lineage_is_exact(repository_root: Path) -> None:
    document, approval = _artifacts(repository_root)

    assert document.declared_status is RuleStatus.APPROVED
    assert document.bundle_id == STAGE6_6A_RULE_BUNDLE_ID
    assert document.bundle_version == STAGE6_6A_RULE_BUNDLE_VERSION
    assert sha256((repository_root / APPROVED_PATH).read_bytes()).hexdigest() == (
        STAGE6_6A_RULE_BUNDLE_RAW_SHA256
    )
    assert document.bundle_hash().value == STAGE6_6A_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE6_6A_RULES_SHA256
    assert approval.approval_id == STAGE6_6A_RULE_APPROVAL_ID
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_scope is STAGE6_6A_APPROVAL_SCOPE
    assert approval.canonical_sha256() == STAGE6_6A_RULE_APPROVAL_RECORD_SHA256

    assert sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest() == (
        STAGE6_6A_SPECIFICATION_SHA256
    )
    assert sha256((repository_root / APPROVAL_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        STAGE6_6A_APPROVAL_DOCUMENT_SHA256
    )
    specification_items = [
        line
        for line in (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8").splitlines()
        if line.startswith("- [ ] `6A-")
    ]
    approval_items = [
        line
        for line in (repository_root / APPROVAL_DOCUMENT_PATH)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("- [x] `6A-")
    ]
    assert len(specification_items) == len(approval_items) == 35
    assert [line.replace("- [ ]", "- [x]", 1) for line in specification_items] == (approval_items)
    draft_path = repository_root / DRAFT_PATH
    draft = rule_bundle_document_from_json_value(_json(draft_path))
    assert sha256(draft_path.read_bytes()).hexdigest() == STAGE6_6A_DRAFT_RAW_SHA256
    assert draft.bundle_hash().value == STAGE6_6A_DRAFT_BUNDLE_SHA256
    assert canonical_sha256(draft.rules) == STAGE6_6A_DRAFT_RULES_SHA256
    assert canonical_sha256(draft.rules["owner_approval_items"]) == (
        STAGE6_6A_DRAFT_OWNER_ITEMS_SHA256
    )


def test_stage6a_capability_is_independent_and_zero_run_authority(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)
    capability = require_stage6a_governance_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )
    approved_rules = _json(repository_root / APPROVED_PATH)["rules"]
    boundary = approved_rules["authorization_boundary"]

    assert capability.approval_scope is (RuleApprovalScope.STAGE6_HISTORICAL_VALIDATION_GOVERNANCE)
    assert capability.approval_id == STAGE6_6A_RULE_APPROVAL_ID
    assert boundary["allowed_run_modes"] == []
    assert boundary["governance_capability_issued"] is True
    assert boundary["authorizes_forming_stage6b_draft"] is True
    assert all(
        value is False
        for key, value in boundary.items()
        if key.startswith("authorizes_") and key != "authorizes_forming_stage6b_draft"
    )
    assert approved_rules["phase_authority"] == {
        "6A": "approved_governance_only",
        "6B": "not_authorized",
        "6C": "not_authorized",
        "6D": "not_authorized",
        "approval_or_completion_is_not_transitive": True,
        "next_allowed_action": "form_exact_stage6b_draft_for_owner_review",
    }


def test_stage6a_default_registry_and_other_stage_scope_fail_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)
    with pytest.raises(ValueError, match="RULE_BUNDLE_IDENTITY_NOT_APPROVED"):
        require_stage6a_governance_capability(document)

    wrong_scope = replace(
        approval,
        approval_scope=RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION,
    )
    with pytest.raises(Stage6ApprovalCompatibilityError) as exc_info:
        require_stage6a_governance_capability(
            document,
            registry=RuleApprovalRegistry((wrong_scope,)),
        )
    assert exc_info.value.code == "STAGE6A_APPROVAL_SCOPE_MISMATCH"


def test_stage6a_partial_owner_approval_or_phase_expansion_fails_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)

    changed_items = _changed_document(
        document,
        lambda rules: rules["owner_approval_items"].pop(),
    )
    matching_items = replace(approval, bundle_hash=changed_items.bundle_hash())
    with pytest.raises(Stage6ApprovalCompatibilityError) as items_exc:
        require_stage6a_governance_capability(
            changed_items,
            registry=RuleApprovalRegistry((matching_items,)),
        )
    assert items_exc.value.code == "STAGE6A_APPROVAL_ITEMS_INVALID"

    changed_phase = _changed_document(
        document,
        lambda rules: rules["phase_authority"].update({"6B": "authorized"}),
    )
    matching_phase = replace(approval, bundle_hash=changed_phase.bundle_hash())
    with pytest.raises(Stage6ApprovalCompatibilityError) as phase_exc:
        require_stage6a_governance_capability(
            changed_phase,
            registry=RuleApprovalRegistry((matching_phase,)),
        )
    assert phase_exc.value.code == "STAGE6A_PHASE_AUTHORITY_MISMATCH"


def test_stage6a_historical_or_trading_authority_expansion_fails_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)

    for field_name in (
        "authorizes_historical_run",
        "authorizes_release_status_confirmation",
        "authorizes_state_persistence",
        "authorizes_holdout_open",
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
    ):
        value = document.to_json_value()
        value["rules"]["authorization_boundary"][field_name] = True
        changed = rule_bundle_document_from_json_value(value)
        matching = replace(approval, bundle_hash=changed.bundle_hash())
        with pytest.raises(Stage6ApprovalCompatibilityError) as exc_info:
            require_stage6a_governance_capability(
                changed,
                registry=RuleApprovalRegistry((matching,)),
            )
        assert exc_info.value.code == "STAGE6A_AUTHORIZATION_BOUNDARY_MISMATCH"


def test_stage6a_draft_source_and_semantic_guard_drift_fail_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)

    value = document.to_json_value()
    value["rules"]["approval_source_binding"]["draft_rules_sha256"] = "0" * 64
    changed_source = rule_bundle_document_from_json_value(value)
    matching_source = replace(approval, bundle_hash=changed_source.bundle_hash())
    with pytest.raises(Stage6ApprovalCompatibilityError) as source_exc:
        require_stage6a_governance_capability(
            changed_source,
            registry=RuleApprovalRegistry((matching_source,)),
        )
    assert source_exc.value.code == "STAGE6A_APPROVAL_SOURCE_MISMATCH"

    value = document.to_json_value()
    value["rules"]["approved_semantic_guards"]["prd_numeric_thresholds_remain_hypothesis"] = False
    changed_guard = rule_bundle_document_from_json_value(value)
    matching_guard = replace(approval, bundle_hash=changed_guard.bundle_hash())
    with pytest.raises(Stage6ApprovalCompatibilityError) as guard_exc:
        require_stage6a_governance_capability(
            changed_guard,
            registry=RuleApprovalRegistry((matching_guard,)),
        )
    assert guard_exc.value.code == "STAGE6A_SEMANTIC_GUARD_MISMATCH"


def test_stage6a_owner_item_sequence_and_approved_hash_are_exact(
    repository_root: Path,
) -> None:
    raw = _json(repository_root / APPROVED_PATH)
    items = raw["rules"]["owner_approval_items"]

    assert tuple(item["approval_item_id"] for item in items) == (STAGE6_6A_OWNER_APPROVAL_ITEM_IDS)
    assert {item["status"] for item in items} == {"approved"}
    assert canonical_sha256(items) == STAGE6_6A_OWNER_APPROVAL_ITEMS_SHA256

    changed = deepcopy(raw)
    changed["rules"]["owner_approval_items"][0]["status"] = "pending"
    drifted = rule_bundle_document_from_json_value(changed)
    _, approval = _artifacts(repository_root)
    matching = replace(approval, bundle_hash=drifted.bundle_hash())
    with pytest.raises(Stage6ApprovalCompatibilityError) as exc_info:
        require_stage6a_governance_capability(
            drifted,
            registry=RuleApprovalRegistry((matching,)),
        )
    assert exc_info.value.code == "STAGE6A_APPROVAL_ITEMS_INVALID"
