from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from invest_system import (
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
    RuleStatus,
)
from invest_system.strategies.industrial_event import (
    STAGE4_APPROVAL_SCOPE,
    STAGE4_REQUIRED_RULE_IDS,
    STAGE4_RULE_INVENTORY_SCHEMA_VERSION,
    STAGE4_STRATEGY_ID,
    Stage4RuleInventory,
    Stage4RuleInventoryItem,
    Stage4RuleReadinessError,
    require_stage4_rule_capability,
    stage4_rule_inventory_from_json_value,
)

INVENTORY_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json"
)


def _approved_item(requirement_id: str) -> Stage4RuleInventoryItem:
    return Stage4RuleInventoryItem(
        requirement_id=requirement_id,
        status=RuleStatus.APPROVED,
        specification_ref=f"spec:{requirement_id}",
        approval_id=f"approval:{requirement_id}",
        machine_rule_ref=f"machine:{requirement_id}",
        positive_test_refs=(f"test:positive:{requirement_id}",),
        negative_test_refs=(f"test:negative:{requirement_id}",),
        boundary_test_refs=(f"test:boundary:{requirement_id}",),
        abstain_test_refs=(f"test:abstain:{requirement_id}",),
    )


def _approved_inventory() -> Stage4RuleInventory:
    return Stage4RuleInventory(
        items=tuple(_approved_item(requirement_id) for requirement_id in STAGE4_REQUIRED_RULE_IDS)
    )


def _authorization_boundary(**overrides: Any) -> dict[str, Any]:
    boundary: dict[str, Any] = {
        "approval_scope": STAGE4_APPROVAL_SCOPE.value,
        "allowed_run_modes": ["research"],
        "synthetic_only": True,
        "validation_only": True,
        "not_a_published_release": True,
        "authorizes_backtest": False,
        "authorizes_paper": False,
        "authorizes_shadow": False,
        "authorizes_live": False,
        "authorizes_positions": False,
        "authorizes_orders": False,
    }
    boundary.update(overrides)
    return boundary


def _document(
    inventory: Stage4RuleInventory,
    *,
    boundary_overrides: dict[str, Any] | None = None,
    inventory_hash: dict[str, str] | None = None,
) -> RuleBundleDocument:
    return RuleBundleDocument(
        schema_version="0.1.0-draft",
        strategy_id=STAGE4_STRATEGY_ID,
        bundle_id="synthetic_stage4_governance_test_bundle",
        bundle_version="0.1.0",
        declared_status=RuleStatus.APPROVED,
        rules={
            "authorization_boundary": _authorization_boundary(**(boundary_overrides or {})),
            "stage4_rule_inventory": {
                "schema_version": STAGE4_RULE_INVENTORY_SCHEMA_VERSION,
                "inventory_hash": inventory_hash or inventory.inventory_hash().to_json_value(),
                "requirement_ids": STAGE4_REQUIRED_RULE_IDS,
            },
            "rule_modules": {
                requirement_id: {
                    "requirement_id": requirement_id,
                    "machine_rule_ref": f"machine:{requirement_id}",
                    "synthetic_test_semantics_only": True,
                }
                for requirement_id in STAGE4_REQUIRED_RULE_IDS
            },
        },
    )


def _registry(
    document: RuleBundleDocument,
    *,
    scope: RuleApprovalScope = STAGE4_APPROVAL_SCOPE,
) -> RuleApprovalRegistry:
    approval = RuleApprovalRecord(
        approval_id="synthetic_stage4_governance_test_approval",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 3, 8, tzinfo=UTC),
        approval_scope=scope,
        approval_source_ref="synthetic_stage4_governance_test_source",
    )
    return RuleApprovalRegistry((approval,))


def test_checked_in_stage4_inventory_has_approved_4a1_4a2_and_six_unapproved_rules(
    repository_root: Path,
) -> None:
    value = json.loads((repository_root / INVENTORY_PATH).read_text(encoding="utf-8"))
    inventory = stage4_rule_inventory_from_json_value(value)

    assert inventory.to_json_value() == value
    assert inventory.unapproved_requirement_ids == STAGE4_REQUIRED_RULE_IDS[8:]
    assert inventory.approval_scope is RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION
    assert inventory.authorizes_backtest is False
    assert inventory.authorizes_paper is False
    assert inventory.authorizes_shadow is False
    assert inventory.authorizes_live is False
    assert inventory.authorizes_positions is False
    assert inventory.authorizes_orders is False
    for rule_item in inventory.items:
        relative_path, anchor = rule_item.specification_ref.split("#", maxsplit=1)
        specification_path = repository_root / relative_path
        assert specification_path.is_file()
        assert anchor == rule_item.requirement_id.lower()
        assert f"### {rule_item.requirement_id}" in specification_path.read_text(encoding="utf-8")
    for rule_item in inventory.items[:4]:
        assert rule_item.status is RuleStatus.APPROVED
        assert rule_item.approval_id == "rule_approval_stage4_4a1_context_industry_v0_1_0"
        assert rule_item.machine_rule_ref is not None
    for rule_item in inventory.items[4:8]:
        assert rule_item.status is RuleStatus.APPROVED
        assert rule_item.approval_id == "rule_approval_stage4_4a2_event_semantics_v0_1_0"
        assert rule_item.machine_rule_ref is not None
    for rule_item in inventory.items[8:]:
        assert rule_item.status is RuleStatus.DRAFT
        assert rule_item.approval_id is None
        assert rule_item.machine_rule_ref is None
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        inventory.require_complete()
    assert exc_info.value.code == "STAGE4_RULES_NOT_FULLY_APPROVED"


def test_inventory_requires_exact_stage4_owned_requirement_set() -> None:
    items = tuple(_approved_item(requirement_id) for requirement_id in STAGE4_REQUIRED_RULE_IDS)
    with pytest.raises(ValueError, match="inventory differs"):
        Stage4RuleInventory(items=items[:-1])
    with pytest.raises(ValueError, match="must not repeat"):
        Stage4RuleInventory(items=items[:-1] + (items[0],))


def test_unapproved_item_cannot_claim_runtime_authority() -> None:
    with pytest.raises(ValueError, match="cannot claim approval"):
        Stage4RuleInventoryItem(
            requirement_id=STAGE4_REQUIRED_RULE_IDS[0],
            status=RuleStatus.DRAFT,
            specification_ref="draft:spec",
            approval_id="false_approval",
            machine_rule_ref="false_machine_rule",
        )


def test_approved_item_requires_all_four_test_classes() -> None:
    with pytest.raises(ValueError, match="ABSTAIN tests"):
        replace(_approved_item(STAGE4_REQUIRED_RULE_IDS[0]), abstain_test_refs=())


def test_exact_complete_inventory_and_exact_stage4_approval_issue_capability() -> None:
    inventory = _approved_inventory()
    document = _document(inventory)
    capability = require_stage4_rule_capability(
        document,
        inventory,
        registry=_registry(document),
    )

    assert capability.approval_scope is STAGE4_APPROVAL_SCOPE
    assert capability.bundle_hash == document.bundle_hash()


def test_stage2b_approval_scope_cannot_authorize_stage4() -> None:
    inventory = _approved_inventory()
    document = _document(inventory)
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        require_stage4_rule_capability(
            document,
            inventory,
            registry=_registry(
                document,
                scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
            ),
        )
    assert exc_info.value.code == "STAGE4_APPROVAL_SCOPE_MISMATCH"


def test_stage4_inventory_hash_drift_fails_closed() -> None:
    inventory = _approved_inventory()
    document = _document(
        inventory,
        inventory_hash={"algorithm": "sha256", "value": "0" * 64},
    )
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        require_stage4_rule_capability(
            document,
            inventory,
            registry=_registry(document),
        )
    assert exc_info.value.code == "STAGE4_INVENTORY_HASH_MISMATCH"


def test_stage4_machine_rule_reference_drift_fails_closed() -> None:
    inventory = _approved_inventory()
    original = _document(inventory)
    value = original.to_json_value()
    first_requirement = STAGE4_REQUIRED_RULE_IDS[0]
    value["rules"]["rule_modules"][first_requirement]["machine_rule_ref"] = "machine:drifted"
    document = RuleBundleDocument(
        schema_version=original.schema_version,
        strategy_id=original.strategy_id,
        bundle_id=original.bundle_id,
        bundle_version=original.bundle_version,
        declared_status=original.declared_status,
        rules=value["rules"],
    )
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        require_stage4_rule_capability(
            document,
            inventory,
            registry=_registry(document),
        )
    assert exc_info.value.code == "STAGE4_MACHINE_RULE_REF_MISMATCH"


@pytest.mark.parametrize(
    "field_name",
    [
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
    ],
)
def test_stage4_trading_authority_drift_fails_closed(field_name: str) -> None:
    inventory = _approved_inventory()
    document = _document(inventory, boundary_overrides={field_name: True})
    with pytest.raises(Stage4RuleReadinessError) as exc_info:
        require_stage4_rule_capability(
            document,
            inventory,
            registry=_registry(document),
        )
    assert exc_info.value.code == "STAGE4_AUTHORIZATION_BOUNDARY_DRIFT"


def test_declared_approved_stage4_bundle_has_no_default_production_authority() -> None:
    inventory = _approved_inventory()
    document = _document(inventory)
    with pytest.raises(ValueError, match="RULE_BUNDLE_IDENTITY_NOT_APPROVED"):
        require_stage4_rule_capability(document, inventory)
