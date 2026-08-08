from __future__ import annotations

import json
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
from invest_system.strategies.industrial_event import (
    STAGE5_5A_APPROVAL_DOCUMENT_SHA256,
    STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256,
    STAGE5_5A_DRAFT_RULES_SHA256,
    STAGE5_5A_OWNER_APPROVAL_ITEM_IDS,
    STAGE5_5A_RULE_APPROVAL_ID,
    STAGE5_5A_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5A_RULE_BUNDLE_ID,
    STAGE5_5A_RULE_BUNDLE_SHA256,
    STAGE5_5A_RULE_BUNDLE_VERSION,
    STAGE5_5A_RULES_SHA256,
    STAGE5_5A_SPECIFICATION_SHA256,
    STAGE5_APPROVAL_SCOPE,
    Stage5RuleCompatibilityError,
    require_stage5_rule_capability,
)

APPROVED_BUNDLE_FILENAME = (
    "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.rule-bundle.json"
)
DRAFT_BUNDLE_FILENAME = (
    "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0-draft.rule-bundle.json"
)
APPROVAL_FILENAME = (
    "industrial_event_stage5_5a_execution_portfolio_ledger_replay_v0.1.0.approval.json"
)
SPECIFICATION_FILENAME = "Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md"
APPROVAL_DOCUMENT_FILENAME = "Stage5_5A成交组合账本与确定性回放批准记录_v0.1.md"


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


def _changed_document(
    document: RuleBundleDocument,
    mutate: Any,
) -> RuleBundleDocument:
    value = document.to_json_value()
    mutate(value["rules"])
    return rule_bundle_document_from_json_value(value)


def test_checked_in_stage5a_approval_lineage_is_exact(repository_root: Path) -> None:
    document, approval = _approved_artifacts(repository_root)
    draft_value = _json(repository_root, DRAFT_BUNDLE_FILENAME)
    draft = rule_bundle_document_from_json_value(draft_value)

    assert document.bundle_id == STAGE5_5A_RULE_BUNDLE_ID
    assert document.bundle_version == STAGE5_5A_RULE_BUNDLE_VERSION
    assert document.bundle_hash().value == STAGE5_5A_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE5_5A_RULES_SHA256
    assert draft.bundle_hash().value == STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256
    assert canonical_sha256(draft.rules) == STAGE5_5A_DRAFT_RULES_SHA256
    assert approval.approval_id == STAGE5_5A_RULE_APPROVAL_ID
    assert approval.approval_scope is STAGE5_APPROVAL_SCOPE
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.canonical_sha256() == STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
    assert (
        sha256(_one(repository_root, SPECIFICATION_FILENAME).read_bytes()).hexdigest()
        == STAGE5_5A_SPECIFICATION_SHA256
    )
    assert (
        sha256(_one(repository_root, APPROVAL_DOCUMENT_FILENAME).read_bytes()).hexdigest()
        == STAGE5_5A_APPROVAL_DOCUMENT_SHA256
    )


def test_checked_in_stage5a_bundle_has_exact_zero_real_authority(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)
    rules = _json(repository_root, APPROVED_BUNDLE_FILENAME)["rules"]
    boundary = rules["authorization_boundary"]
    batch = rules["batch"]
    items = rules["owner_approval_items"]

    assert boundary["approval_scope"] == STAGE5_APPROVAL_SCOPE.value
    assert boundary["allowed_run_modes"] == ["research"]
    assert boundary["synthetic_only"] is True
    assert boundary["validation_only"] is True
    assert boundary["runtime_capability_issued"] is True
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert batch["approved_items"] == 40
    assert batch["governance_capability_verifier_exists"] is True
    assert batch["business_rule_evaluator_exists"] is False
    assert tuple(item["approval_item_id"] for item in items) == (STAGE5_5A_OWNER_APPROVAL_ITEM_IDS)
    assert all(item["status"] == "approved" for item in items)
    assert (
        rules["rule_modules"]["replay_and_atomicity"][
            "sqlite_schema_migration_or_persistence_implemented_by_this_bundle"
        ]
        is False
    )

    capability = require_stage5_rule_capability(
        document,
        registry=RuleApprovalRegistry((approval,)),
    )
    assert capability.approval_scope is RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION
    assert capability.approval_record_hash.value == STAGE5_5A_RULE_APPROVAL_RECORD_SHA256


def test_stage5a_draft_cannot_issue_approved_capability(repository_root: Path) -> None:
    _, approval = _approved_artifacts(repository_root)
    draft = rule_bundle_document_from_json_value(_json(repository_root, DRAFT_BUNDLE_FILENAME))

    with pytest.raises(Stage5RuleCompatibilityError) as exc_info:
        require_stage5_rule_capability(
            draft,
            registry=RuleApprovalRegistry((approval,)),
        )

    assert exc_info.value.code == "STAGE5_RULE_IDENTITY_UNSUPPORTED"


def test_stage5a_authority_expansion_fails_even_with_matching_registry(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate(rules: dict[str, Any]) -> None:
        rules["authorization_boundary"]["authorizes_paper"] = True

    changed = _changed_document(document, mutate)
    matching_approval = replace(approval, bundle_hash=changed.bundle_hash())

    with pytest.raises(Stage5RuleCompatibilityError) as exc_info:
        require_stage5_rule_capability(
            changed,
            registry=RuleApprovalRegistry((matching_approval,)),
        )

    assert exc_info.value.code == "STAGE5_AUTHORIZATION_BOUNDARY_MISMATCH"


def test_stage5a_semantic_drift_fails_even_with_matching_registry(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate(rules: dict[str, Any]) -> None:
        rules["rule_modules"]["capacity_cost_and_fill"]["synthetic_maximum_participation_rate"] = (
            "0.06"
        )

    changed = _changed_document(document, mutate)
    matching_approval = replace(approval, bundle_hash=changed.bundle_hash())

    with pytest.raises(Stage5RuleCompatibilityError) as exc_info:
        require_stage5_rule_capability(
            changed,
            registry=RuleApprovalRegistry((matching_approval,)),
        )

    assert exc_info.value.code == "STAGE5_RULE_HASH_UNSUPPORTED"


def test_stage5a_upstream_drift_fails_even_with_matching_registry(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)

    def mutate(rules: dict[str, Any]) -> None:
        rules["exact_upstream_dependency"]["bundle_hash"]["value"] = "0" * 64

    changed = _changed_document(document, mutate)
    matching_approval = replace(approval, bundle_hash=changed.bundle_hash())

    with pytest.raises(Stage5RuleCompatibilityError) as exc_info:
        require_stage5_rule_capability(
            changed,
            registry=RuleApprovalRegistry((matching_approval,)),
        )

    assert exc_info.value.code == "STAGE5_UPSTREAM_IDENTITY_MISMATCH"


def test_stage5a_wrong_scope_or_approval_record_cannot_authorize(
    repository_root: Path,
) -> None:
    document, approval = _approved_artifacts(repository_root)
    wrong_scope = replace(
        approval,
        approval_scope=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION,
    )
    with pytest.raises(Stage5RuleCompatibilityError) as scope_exc:
        require_stage5_rule_capability(
            document,
            registry=RuleApprovalRegistry((wrong_scope,)),
        )
    assert scope_exc.value.code == "STAGE5_APPROVAL_SCOPE_MISMATCH"

    drifted_record = replace(approval, approval_source_ref="approval_source_drift")
    with pytest.raises(Stage5RuleCompatibilityError) as record_exc:
        require_stage5_rule_capability(
            document,
            registry=RuleApprovalRegistry((drifted_record,)),
        )
    assert record_exc.value.code == "STAGE5_APPROVAL_RECORD_UNSUPPORTED"
