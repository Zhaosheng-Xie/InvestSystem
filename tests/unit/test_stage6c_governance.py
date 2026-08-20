from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system import RuleApprovalRegistry, RuleApprovalScope
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    RuleBundleDocument,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import RuleStatus
from invest_system.strategies.industrial_event import (
    STAGE6_6C_APPROVAL_DOCUMENT_SHA256,
    STAGE6_6C_APPROVAL_SCOPE,
    STAGE6_6C_DRAFT_BUNDLE_SHA256,
    STAGE6_6C_DRAFT_OWNER_ITEMS_SHA256,
    STAGE6_6C_DRAFT_RAW_SHA256,
    STAGE6_6C_DRAFT_RULES_SHA256,
    STAGE6_6C_OWNER_APPROVAL_ITEM_IDS,
    STAGE6_6C_OWNER_APPROVAL_ITEMS_SHA256,
    STAGE6_6C_RULE_APPROVAL_ID,
    STAGE6_6C_RULE_APPROVAL_RECORD_SHA256,
    STAGE6_6C_RULE_BUNDLE_ID,
    STAGE6_6C_RULE_BUNDLE_RAW_SHA256,
    STAGE6_6C_RULE_BUNDLE_SHA256,
    STAGE6_6C_RULE_BUNDLE_VERSION,
    STAGE6_6C_RULES_SHA256,
    STAGE6_6C_SPECIFICATION_SHA256,
    Stage6CApprovalCompatibilityError,
    require_stage6c_kernel_validation_capability,
)

RULE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格")
MACHINE_DIRECTORY = RULE_DIRECTORY / "机器制品"
SPECIFICATION_PATH = RULE_DIRECTORY / ("Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md")
APPROVAL_DOCUMENT_PATH = RULE_DIRECTORY / ("Stage6_6C开发样本WalkForward与冠军挑战批准记录_v0.2.md")
DRAFT_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
    "v0.2.0-draft.rule-bundle.json"
)
APPROVED_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.rule-bundle.json"
)
APPROVAL_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.approval.json"
)
APPROVAL_RAW_SHA256 = "7fd3756f005f20e3c345d06549340cba9abd5a974d6cd9977121eab98d08a2a0"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _artifacts(repository_root: Path) -> tuple[RuleBundleDocument, Any]:
    document = rule_bundle_document_from_json_value(_json(repository_root / APPROVED_PATH))
    approval = rule_approval_record_from_json_value(_json(repository_root / APPROVAL_PATH))
    return document, approval


def _changed(document: RuleBundleDocument, mutate: Any) -> RuleBundleDocument:
    value = deepcopy(document.to_json_value())
    mutate(value["rules"])
    return rule_bundle_document_from_json_value(value)


def test_stage6c_v02_checked_in_approval_lineage_is_exact(repository_root: Path) -> None:
    document, approval = _artifacts(repository_root)

    assert document.declared_status is RuleStatus.APPROVED
    assert document.bundle_id == STAGE6_6C_RULE_BUNDLE_ID
    assert document.bundle_version == STAGE6_6C_RULE_BUNDLE_VERSION
    assert sha256((repository_root / APPROVED_PATH).read_bytes()).hexdigest() == (
        STAGE6_6C_RULE_BUNDLE_RAW_SHA256
    )
    assert document.bundle_hash().value == STAGE6_6C_RULE_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE6_6C_RULES_SHA256
    assert approval.approval_id == STAGE6_6C_RULE_APPROVAL_ID
    assert approval.bundle_hash == document.bundle_hash()
    assert approval.approval_scope is STAGE6_6C_APPROVAL_SCOPE
    assert approval.canonical_sha256() == STAGE6_6C_RULE_APPROVAL_RECORD_SHA256
    assert sha256((repository_root / APPROVAL_PATH).read_bytes()).hexdigest() == (
        APPROVAL_RAW_SHA256
    )
    assert sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest() == (
        STAGE6_6C_SPECIFICATION_SHA256
    )
    assert sha256((repository_root / APPROVAL_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        STAGE6_6C_APPROVAL_DOCUMENT_SHA256
    )

    draft_path = repository_root / DRAFT_PATH
    draft = rule_bundle_document_from_json_value(_json(draft_path))
    assert sha256(draft_path.read_bytes()).hexdigest() == STAGE6_6C_DRAFT_RAW_SHA256
    assert draft.bundle_hash().value == STAGE6_6C_DRAFT_BUNDLE_SHA256
    assert canonical_sha256(draft.rules) == STAGE6_6C_DRAFT_RULES_SHA256
    assert canonical_sha256(draft.rules["owner_approval_items"]) == (
        STAGE6_6C_DRAFT_OWNER_ITEMS_SHA256
    )

    draft_items = [
        line
        for line in (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8").splitlines()
        if line.startswith("- [ ] `6C-")
    ]
    approved_items = [
        line
        for line in (repository_root / APPROVAL_DOCUMENT_PATH)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("- [x] `6C-")
    ]
    assert len(draft_items) == len(approved_items) == 40
    assert [line.replace("- [ ]", "- [x]", 1) for line in draft_items] == approved_items


def test_stage6c_v02_capability_is_anonymous_synthetic_kernel_only(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)
    capability = require_stage6c_kernel_validation_capability(
        document, registry=RuleApprovalRegistry((approval,))
    )
    boundary = _json(repository_root / APPROVED_PATH)["rules"]["authorization_boundary"]

    assert capability.approval_scope is (
        RuleApprovalScope.STAGE6_DEVELOPMENT_WALK_FORWARD_VALIDATION
    )
    assert capability.approval_id == STAGE6_6C_RULE_APPROVAL_ID
    assert boundary["allowed_run_modes"] == []
    assert boundary["validation_capability_issued"] is True
    assert boundary["authorizes_implementation"] is True
    assert boundary["authorizes_synthetic_kernel_validation"] is True
    assert boundary["authority_eligible"] is False
    assert all(
        boundary[field] is False
        for field in (
            "authorizes_formal_historical_admission",
            "authorizes_formal_development_run",
            "authorizes_walk_forward_run",
            "authorizes_holdout_commitment_read",
            "authorizes_holdout_artifact_read",
            "authorizes_holdout_open",
            "authorizes_stage6_final_pass",
            "authorizes_formal_state_migration",
            "authorizes_backtest",
            "authorizes_paper",
            "authorizes_shadow",
            "authorizes_live",
            "authorizes_positions",
            "authorizes_orders",
            "authorizes_broker_connection",
            "authorizes_kb_internal_reads",
            "authorizes_kb_writes",
            "authorizes_funds_deployment",
        )
    )


def test_stage6c_v02_default_registry_and_other_scope_fail_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)
    with pytest.raises(ValueError, match="RULE_BUNDLE_IDENTITY_NOT_APPROVED"):
        require_stage6c_kernel_validation_capability(document)

    wrong_scope = replace(
        approval, approval_scope=RuleApprovalScope.STAGE6_HISTORICAL_ADMISSION_VALIDATION
    )
    with pytest.raises(Stage6CApprovalCompatibilityError) as exc_info:
        require_stage6c_kernel_validation_capability(
            document, registry=RuleApprovalRegistry((wrong_scope,))
        )
    assert exc_info.value.code == "STAGE6C_APPROVAL_SCOPE_MISMATCH"


def test_stage6c_v02_formal_execution_holdout_or_trading_expansion_fails_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)
    fields = (
        "authorizes_formal_historical_admission",
        "authorizes_formal_development_run",
        "authorizes_walk_forward_run",
        "authorizes_holdout_commitment_read",
        "authorizes_holdout_artifact_read",
        "authorizes_holdout_open",
        "authorizes_stage6_final_pass",
        "authorizes_formal_state_migration",
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
        "authorizes_broker_connection",
        "authorizes_kb_internal_reads",
        "authorizes_kb_writes",
        "authorizes_funds_deployment",
        "authority_eligible",
    )
    for field in fields:
        changed = _changed(
            document,
            lambda rules, field=field: rules["authorization_boundary"].update({field: True}),
        )
        matching = replace(approval, bundle_hash=changed.bundle_hash())
        with pytest.raises(Stage6CApprovalCompatibilityError) as exc_info:
            require_stage6c_kernel_validation_capability(
                changed, registry=RuleApprovalRegistry((matching,))
            )
        assert exc_info.value.code == "STAGE6C_RULE_IDENTITY_MISMATCH"


def test_stage6c_v02_partial_items_source_or_critical_method_drift_fail_closed(
    repository_root: Path,
) -> None:
    document, approval = _artifacts(repository_root)

    changed_items = _changed(document, lambda rules: rules["owner_approval_items"].pop())
    matching_items = replace(approval, bundle_hash=changed_items.bundle_hash())
    with pytest.raises(Stage6CApprovalCompatibilityError) as items_exc:
        require_stage6c_kernel_validation_capability(
            changed_items, registry=RuleApprovalRegistry((matching_items,))
        )
    assert items_exc.value.code == "STAGE6C_RULE_IDENTITY_MISMATCH"

    changed_source = _changed(
        document,
        lambda rules: rules["approval_source_binding"].update({"draft_rules_sha256": "0" * 64}),
    )
    matching_source = replace(approval, bundle_hash=changed_source.bundle_hash())
    with pytest.raises(Stage6CApprovalCompatibilityError) as source_exc:
        require_stage6c_kernel_validation_capability(
            changed_source, registry=RuleApprovalRegistry((matching_source,))
        )
    assert source_exc.value.code == "STAGE6C_RULE_IDENTITY_MISMATCH"

    changed_holdout = _changed(
        document,
        lambda rules: rules["holdout_technical_isolation"]["access_control"].update(
            {"holdout_audit_read_count": 1}
        ),
    )
    matching_holdout = replace(approval, bundle_hash=changed_holdout.bundle_hash())
    with pytest.raises(Stage6CApprovalCompatibilityError) as holdout_exc:
        require_stage6c_kernel_validation_capability(
            changed_holdout, registry=RuleApprovalRegistry((matching_holdout,))
        )
    assert holdout_exc.value.code == "STAGE6C_RULE_IDENTITY_MISMATCH"


def test_stage6c_v02_approved_bundle_is_fully_materialized(repository_root: Path) -> None:
    rules = _json(repository_root / APPROVED_PATH)["rules"]

    assert "supersession_and_base_binding" not in rules
    assert "effective_rule_materialization" not in rules
    assert rules["approval_source_binding"]["complete_rules_materialized"] is True
    assert rules["runtime_must_not_parse_markdown_or_delta_bundle"] is True
    assert rules["holdout_technical_isolation"]["access_control"]["holdout_audit_read_count"] == 0
    assert (
        rules["inference_and_multiple_testing"]["adjusted_entry_gate"]["every_adjusted_p_value_lte"]
        == "0.05"
    )
    assert rules["data_readiness_and_support"]["coverage_selection_audit_required"] is True
    assert rules["metrics_and_entry_gates"]["primary_estimator"]["annualization_sessions"] == 252
    assert canonical_sha256(rules["owner_approval_items"]) == (
        STAGE6_6C_OWNER_APPROVAL_ITEMS_SHA256
    )
    assert tuple(item["approval_item_id"] for item in rules["owner_approval_items"]) == (
        STAGE6_6C_OWNER_APPROVAL_ITEM_IDS
    )
