from __future__ import annotations

import json
from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest

from invest_system import (
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleStatus,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)

RULE_ARTIFACT_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
BUNDLE_NAME = "industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json"
APPROVAL_NAME = "industrial_event_minimum_order_contract_slice_v0.1.0.approval.json"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _load_json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(value, dict):
        raise TypeError(f"{path.name} must contain one JSON object")
    return cast(dict[str, Any], value)


@pytest.fixture(scope="module")
def approved_rule_artifacts(repository_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    directory = repository_root / RULE_ARTIFACT_DIRECTORY
    return _load_json_object(directory / BUNDLE_NAME), _load_json_object(directory / APPROVAL_NAME)


def test_stage2b_rule_bundle_and_approval_bind_exact_canonical_identity(
    approved_rule_artifacts: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    bundle_value, approval_value = approved_rule_artifacts
    bundle = rule_bundle_document_from_json_value(bundle_value)
    approval = rule_approval_record_from_json_value(approval_value)
    capability = RuleApprovalRegistry((approval,)).require(bundle)

    assert bundle.to_json_value() == bundle_value
    assert approval.to_json_value() == approval_value
    assert bundle.declared_status is RuleStatus.APPROVED
    assert bundle.bundle_hash() == approval.bundle_hash == capability.bundle_hash
    assert capability.approval_scope is RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION


def test_stage2b_approval_scope_is_research_validation_only_and_fail_closed(
    approved_rule_artifacts: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    bundle_value, _approval_value = approved_rule_artifacts
    rules = bundle_value["rules"]
    assert isinstance(rules, Mapping)
    boundary = rules["authorization_boundary"]
    safety = rules["decision_safety"]
    assert isinstance(boundary, Mapping)
    assert isinstance(safety, Mapping)

    assert boundary["approval_scope"] == "stage2b_synthetic_validation"
    assert boundary["default_policy"] == "deny"
    assert boundary["allowed_run_modes"] == ["research"]
    assert set(boundary["forbidden_run_modes"]) == {
        "backtest",
        "paper",
        "shadow",
        "live",
    }
    assert boundary["scope_expansion_by_inference_is_forbidden"] is True
    assert boundary["new_scope_requires_new_owner_approval"] is True
    assert safety == {
        "position_state": "FLAT",
        "target_weight": "0",
        "approved_weight": "0",
        "actual_weight": "0",
        "approver": None,
        "authorizes_real_trade_ready": False,
        "synthetic_trade_ready_proves_path_reachability_only": True,
    }


def test_stage2b_rule_bundle_records_all_twenty_two_approved_items(
    approved_rule_artifacts: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    bundle_value, _approval_value = approved_rule_artifacts
    approval_items = bundle_value["rules"]["approval_items"]

    assert approval_items == [f"S2B-APPROVAL-{index:03d}" for index in range(1, 23)]


def test_stage2b_document_binding_is_exact_but_traceability_only(
    repository_root: Path,
    approved_rule_artifacts: tuple[dict[str, Any], dict[str, Any]],
) -> None:
    bundle_value, _approval_value = approved_rule_artifacts
    rules = bundle_value["rules"]
    binding = rules["document_binding"]
    target = (repository_root / binding["path"]).resolve()

    assert target.is_relative_to(repository_root.resolve())
    assert sha256(target.read_bytes()).hexdigest() == binding["hash"]["value"]
    assert rules["document_binding_is_traceability_only"] is True
    assert rules["runtime_must_not_parse_markdown"] is True
