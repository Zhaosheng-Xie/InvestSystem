from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system import (
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.storage import STORAGE_SCHEMA_VERSION
from invest_system.strategies.industrial_event import (
    STAGE5_5D_APPROVAL_DOCUMENT_SHA256,
    STAGE5_5D_APPROVAL_SCOPE,
    STAGE5_5D_DRAFT_OWNER_APPROVAL_ITEMS_SHA256,
    STAGE5_5D_DRAFT_RULE_BUNDLE_RAW_SHA256,
    STAGE5_5D_DRAFT_RULE_BUNDLE_SHA256,
    STAGE5_5D_DRAFT_RULES_SHA256,
    STAGE5_5D_OWNER_APPROVAL_ITEM_IDS,
    STAGE5_5D_OWNER_APPROVAL_ITEMS_SHA256,
    STAGE5_5D_RULE_APPROVAL_ID,
    STAGE5_5D_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5D_RULE_BUNDLE_ID,
    STAGE5_5D_RULE_BUNDLE_RAW_SHA256,
    STAGE5_5D_RULE_BUNDLE_SHA256,
    STAGE5_5D_RULE_BUNDLE_VERSION,
    STAGE5_5D_RULES_SHA256,
    STAGE5_5D_SPECIFICATION_SHA256,
    STAGE5_5D_STAGE5C_BASELINE_COMMIT,
    Stage5DApprovalCompatibilityError,
    require_stage5d_rule_capability,
)

APPROVED_BUNDLE_FILENAME = (
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.rule-bundle.json"
)
DRAFT_BUNDLE_FILENAME = (
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_"
    "v0.1.0-draft.rule-bundle.json"
)
APPROVAL_FILENAME = (
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_v0.1.0.approval.json"
)
SPECIFICATION_FILENAME = "Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md"
APPROVAL_DOCUMENT_FILENAME = "Stage5_5D公司行动估值P&L完整回放与原子持久化批准记录_v0.1.md"


def _one(repository_root: Path, filename: str) -> Path:
    matches = tuple(repository_root.rglob(filename))
    assert len(matches) == 1
    return matches[0]


def _json(repository_root: Path, filename: str) -> dict[str, Any]:
    value = json.loads(_one(repository_root, filename).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _approved_artifacts(
    repository_root: Path,
) -> tuple[RuleBundleDocument, RuleApprovalRecord]:
    document = rule_bundle_document_from_json_value(
        _json(repository_root, APPROVED_BUNDLE_FILENAME)
    )
    approval = rule_approval_record_from_json_value(_json(repository_root, APPROVAL_FILENAME))
    return document, approval


def _changed_document(document: RuleBundleDocument, mutate: Any) -> RuleBundleDocument:
    value = document.to_json_value()
    mutate(value["rules"])
    return rule_bundle_document_from_json_value(value)


def test_checked_in_stage5d_approval_lineage_is_exact(repository_root: Path) -> None:
    document, approval = _approved_artifacts(repository_root)
    approved_path = _one(repository_root, APPROVED_BUNDLE_FILENAME)
    draft_path = _one(repository_root, DRAFT_BUNDLE_FILENAME)
    draft = rule_bundle_document_from_json_value(_json(repository_root, DRAFT_BUNDLE_FILENAME))

    assert document.bundle_id == STAGE5_5D_RULE_BUNDLE_ID
    assert document.bundle_version == STAGE5_5D_RULE_BUNDLE_VERSION
    assert sha256(approved_path.read_bytes()).hexdigest() == STAGE5_5D_RULE_BUNDLE_RAW_SHA256
    assert document.bundle_hash().value == STAGE5_5D_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE5_5D_RULES_SHA256
    assert sha256(draft_path.read_bytes()).hexdigest() == STAGE5_5D_DRAFT_RULE_BUNDLE_RAW_SHA256
    assert draft.bundle_hash().value == STAGE5_5D_DRAFT_RULE_BUNDLE_SHA256
    assert canonical_sha256(draft.rules) == STAGE5_5D_DRAFT_RULES_SHA256
    assert approval.approval_id == STAGE5_5D_RULE_APPROVAL_ID
    assert approval.approval_scope is STAGE5_5D_APPROVAL_SCOPE
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.canonical_sha256() == STAGE5_5D_RULE_APPROVAL_RECORD_SHA256
    assert (
        sha256(_one(repository_root, SPECIFICATION_FILENAME).read_bytes()).hexdigest()
        == STAGE5_5D_SPECIFICATION_SHA256
    )
    assert (
        sha256(_one(repository_root, APPROVAL_DOCUMENT_FILENAME).read_bytes()).hexdigest()
        == STAGE5_5D_APPROVAL_DOCUMENT_SHA256
    )

    approved_items = document.to_json_value()["rules"]["owner_approval_items"]
    draft_items = draft.to_json_value()["rules"]["owner_approval_items"]
    assert canonical_sha256(approved_items) == STAGE5_5D_OWNER_APPROVAL_ITEMS_SHA256
    assert canonical_sha256(draft_items) == STAGE5_5D_DRAFT_OWNER_APPROVAL_ITEMS_SHA256
    assert tuple(item["approval_item_id"] for item in approved_items) == (
        STAGE5_5D_OWNER_APPROVAL_ITEM_IDS
    )
    assert all(item["status"] == "approved" for item in approved_items)
    for approved_item, draft_item in zip(approved_items, draft_items, strict=True):
        assert approved_item["approval_item_id"] == draft_item["approval_item_id"]
        assert approved_item["decision_text_sha256"] == draft_item["decision_text_sha256"]
        assert approved_item["rule_paths"] == draft_item["rule_paths"]


def test_stage5d_approved_bundle_changes_only_governance_surface(
    repository_root: Path,
) -> None:
    approved = _json(repository_root, APPROVED_BUNDLE_FILENAME)
    draft = _json(repository_root, DRAFT_BUNDLE_FILENAME)
    normalized = deepcopy(approved)

    normalized["bundle_version"] = draft["bundle_version"]
    normalized["declared_status"] = draft["declared_status"]
    normalized_rules = normalized["rules"]
    draft_rules = draft["rules"]
    normalized_rules["authorization_boundary"] = draft_rules["authorization_boundary"]
    normalized_rules["batch"] = draft_rules["batch"]
    normalized_rules["implementation_sequence"]["status"] = draft_rules["implementation_sequence"][
        "status"
    ]
    for module_name, module in normalized_rules["rule_modules"].items():
        module["status"] = draft_rules["rule_modules"][module_name]["status"]
    for item, draft_item in zip(
        normalized_rules["owner_approval_items"],
        draft_rules["owner_approval_items"],
        strict=True,
    ):
        item["status"] = draft_item["status"]
    normalized_rules.pop("approval_source_binding")
    normalized_rules["document_binding"] = draft_rules["document_binding"]

    assert normalized == draft


def test_stage5d_capability_has_exact_zero_real_or_persistence_authority(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)
    rules = document.to_json_value()["rules"]
    boundary = rules["authorization_boundary"]
    batch = rules["batch"]

    assert boundary["approval_scope"] == "stage5_synthetic_execution_validation"
    assert boundary["allowed_run_modes"] == ["research"]
    assert boundary["synthetic_only"] is True
    assert boundary["validation_only"] is True
    assert boundary["runtime_capability_issued"] is True
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert batch["approved_items"] == 48
    assert batch["governance_capability_verifier_exists"] is True
    assert batch["business_rule_evaluator_exists"] is False
    assert batch["persistence_exists"] is False
    assert rules["implementation_sequence"]["5D-1"]["persists_state"] is False
    assert rules["implementation_sequence"]["5D-2"]["currently_authorized"] is False
    assert rules["implementation_sequence"]["5D-2"]["currently_implemented"] is False
    assert STORAGE_SCHEMA_VERSION == 3

    capability = require_stage5d_rule_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )
    assert capability.approval_scope is RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION
    assert capability.approval_record_hash.value == STAGE5_5D_RULE_APPROVAL_RECORD_SHA256


def test_stage5d_draft_or_partial_approval_cannot_issue_capability(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)
    draft = rule_bundle_document_from_json_value(_json(repository_root, DRAFT_BUNDLE_FILENAME))
    with pytest.raises(Stage5DApprovalCompatibilityError) as draft_exc:
        require_stage5d_rule_capability(draft, registry=RuleApprovalRegistry((approval,)))
    assert draft_exc.value.code == "STAGE5D_RULE_IDENTITY_UNSUPPORTED"

    def mutate(rules: dict[str, Any]) -> None:
        rules["owner_approval_items"][17]["status"] = "pending"

    partial = _changed_document(document, mutate)
    matching = replace(approval, bundle_hash=partial.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as partial_exc:
        require_stage5d_rule_capability(partial, registry=RuleApprovalRegistry((matching,)))
    assert partial_exc.value.code == "STAGE5D_APPROVAL_ITEMS_INVALID"


@pytest.mark.parametrize(
    "authority", ["authorizes_paper", "authorizes_live", "authorizes_durable_persistence"]
)
def test_stage5d_authority_expansion_fails_even_with_matching_registry(
    repository_root: Path,
    authority: str,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate(rules: dict[str, Any]) -> None:
        rules["authorization_boundary"][authority] = True

    changed = _changed_document(document, mutate)
    matching = replace(approval, bundle_hash=changed.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as exc_info:
        require_stage5d_rule_capability(changed, registry=RuleApprovalRegistry((matching,)))
    assert exc_info.value.code == "STAGE5D_AUTHORIZATION_BOUNDARY_MISMATCH"


def test_stage5d_semantic_drift_fails_even_with_matching_registry(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate(rules: dict[str, Any]) -> None:
        rules["rule_modules"]["two_dimensional_pnl"]["period_total_pnl_formula"] = "0"

    changed = _changed_document(document, mutate)
    matching = replace(approval, bundle_hash=changed.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as exc_info:
        require_stage5d_rule_capability(changed, registry=RuleApprovalRegistry((matching,)))
    assert exc_info.value.code == "STAGE5D_RULE_HASH_UNSUPPORTED"


def test_stage5d_stage5a_or_stage5c_drift_fails_closed(repository_root: Path) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate_stage5a(rules: dict[str, Any]) -> None:
        rules["exact_upstream_dependencies"]["stage5a_rule_governance"]["bundle_hash"]["value"] = (
            "0" * 64
        )

    changed_stage5a = _changed_document(document, mutate_stage5a)
    matching_stage5a = replace(approval, bundle_hash=changed_stage5a.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as stage5a_exc:
        require_stage5d_rule_capability(
            changed_stage5a,
            registry=RuleApprovalRegistry((matching_stage5a,)),
        )
    assert stage5a_exc.value.code == "STAGE5D_STAGE5A_IDENTITY_MISMATCH"

    def mutate_stage5c(rules: dict[str, Any]) -> None:
        rules["exact_upstream_dependencies"]["stage5c_implementation_baseline"]["commit"] = "0" * 40

    changed_stage5c = _changed_document(document, mutate_stage5c)
    matching_stage5c = replace(approval, bundle_hash=changed_stage5c.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as stage5c_exc:
        require_stage5d_rule_capability(
            changed_stage5c,
            registry=RuleApprovalRegistry((matching_stage5c,)),
        )
    assert stage5c_exc.value.code == "STAGE5D_STAGE5C_BASELINE_MISMATCH"
    assert STAGE5_5D_STAGE5C_BASELINE_COMMIT == "7f64c584c5c7be5e2385a177fab9e5d31e3f665b"


def test_stage5d_source_document_scope_and_record_drift_fail_closed(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate_source(rules: dict[str, Any]) -> None:
        rules["approval_source_binding"]["draft_raw_hash"]["value"] = "0" * 64

    changed_source = _changed_document(document, mutate_source)
    matching_source = replace(approval, bundle_hash=changed_source.bundle_hash())
    with pytest.raises(Stage5DApprovalCompatibilityError) as source_exc:
        require_stage5d_rule_capability(
            changed_source,
            registry=RuleApprovalRegistry((matching_source,)),
        )
    assert source_exc.value.code == "STAGE5D_APPROVAL_SOURCE_MISMATCH"

    wrong_scope = replace(
        approval,
        approval_scope=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION,
    )
    with pytest.raises(Stage5DApprovalCompatibilityError) as scope_exc:
        require_stage5d_rule_capability(
            document,
            registry=RuleApprovalRegistry((wrong_scope,)),
        )
    assert scope_exc.value.code == "STAGE5D_APPROVAL_SCOPE_MISMATCH"

    drifted_record = replace(approval, approval_source_ref="approval_source_drift")
    with pytest.raises(Stage5DApprovalCompatibilityError) as record_exc:
        require_stage5d_rule_capability(
            document,
            registry=RuleApprovalRegistry((drifted_record,)),
        )
    assert record_exc.value.code == "STAGE5D_APPROVAL_RECORD_UNSUPPORTED"
