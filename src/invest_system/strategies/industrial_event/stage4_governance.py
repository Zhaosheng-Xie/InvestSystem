"""Fail-closed Stage 4 rule inventory and approval boundary.

Stage 4 may start before Stage 3 because its strategy rules consume only
provider-neutral inputs.  Starting the stage does not approve the unresolved
business semantics in the PRD, however.  This module therefore models the
complete Stage-4-owned P0 inventory and rejects runtime capability issuance
until every item has an exact specification, approval, machine rule, and test
evidence.  It defines no event, gate, valuation, exit, position, or execution
semantics.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from invest_system.canonical import JsonValue, freeze_json
from invest_system.domain.rule_approval import (
    CURRENT_RULE_APPROVAL_REGISTRY,
    ApprovedRuleCapability,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import CanonicalModel, HashDigest, RuleStatus

STAGE4_RULE_INVENTORY_SCHEMA_VERSION = "0.1.0-draft"
STAGE4_STRATEGY_ID = "industrial_bottleneck_event"
STAGE4_APPROVAL_SCOPE = RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION

# Stage 4 owns strategy semantics.  Transport belongs to Stage 3, while
# executable-price mechanics, risk budgets, portfolio, orders, and P&L belong
# to Stage 5.  Those requirements must not be smuggled into this inventory.
STAGE4_REQUIRED_RULE_IDS = (
    "FR-CTX-001",
    "FR-CTX-002",
    "FR-IND-001",
    "FR-IND-002",
    "FR-EVT-001",
    "FR-EVT-002",
    "FR-EVT-003",
    "FR-EVT-004",
    "FR-GATE-001",
    "FR-GATE-002",
    "FR-GATE-003",
    "FR-GATE-004",
    "FR-GATE-005",
    "FR-EXIT-001",
)

_ITEM_KEYS = frozenset(
    {
        "requirement_id",
        "status",
        "specification_ref",
        "approval_id",
        "machine_rule_ref",
        "positive_test_refs",
        "negative_test_refs",
        "boundary_test_refs",
        "abstain_test_refs",
    }
)
_INVENTORY_KEYS = frozenset(
    {
        "schema_version",
        "strategy_id",
        "approval_scope",
        "items",
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
    }
)
_AUTHORIZATION_KEYS = frozenset(
    {
        "approval_scope",
        "allowed_run_modes",
        "synthetic_only",
        "validation_only",
        "not_a_published_release",
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
    }
)
_INVENTORY_BINDING_KEYS = frozenset({"schema_version", "inventory_hash", "requirement_ids"})
_RULE_DOCUMENT_KEYS = frozenset({"authorization_boundary", "stage4_rule_inventory", "rule_modules"})


def _strict_mapping(
    value: Any,
    *,
    keys: frozenset[str],
    field_name: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ValueError(f"{field_name} fields differ; missing={missing}, extra={extra}")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _freeze_refs(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    result = tuple(_require_text(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicates")
    return tuple(sorted(result))


def _coerce_status(value: RuleStatus | str) -> RuleStatus:
    try:
        return value if isinstance(value, RuleStatus) else RuleStatus(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("status is not a supported RuleStatus") from exc


class Stage4RuleReadinessError(ValueError):
    """Stable fail-closed rejection from the Stage 4 rule boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Stage4RuleInventoryItem(CanonicalModel):
    """Readiness evidence for one Stage-4-owned P0 requirement."""

    requirement_id: str
    status: RuleStatus
    specification_ref: str
    approval_id: str | None = None
    machine_rule_ref: str | None = None
    positive_test_refs: tuple[str, ...] = ()
    negative_test_refs: tuple[str, ...] = ()
    boundary_test_refs: tuple[str, ...] = ()
    abstain_test_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.requirement_id not in STAGE4_REQUIRED_RULE_IDS:
            raise ValueError("requirement_id is not owned by Stage 4")
        object.__setattr__(self, "status", _coerce_status(self.status))
        _require_text("specification_ref", self.specification_ref)
        for field_name in (
            "positive_test_refs",
            "negative_test_refs",
            "boundary_test_refs",
            "abstain_test_refs",
        ):
            object.__setattr__(
                self,
                field_name,
                _freeze_refs(field_name, getattr(self, field_name)),
            )

        if self.status is RuleStatus.APPROVED:
            if self.approval_id is None or self.machine_rule_ref is None:
                raise ValueError("approved items require approval_id and machine_rule_ref")
            _require_text("approval_id", self.approval_id)
            _require_text("machine_rule_ref", self.machine_rule_ref)
            if any(
                not getattr(self, field_name)
                for field_name in (
                    "positive_test_refs",
                    "negative_test_refs",
                    "boundary_test_refs",
                    "abstain_test_refs",
                )
            ):
                raise ValueError(
                    "approved items require positive, negative, boundary, and ABSTAIN tests"
                )
        elif self.approval_id is not None or self.machine_rule_ref is not None:
            raise ValueError("unapproved items cannot claim approval or runtime machine rules")


@dataclass(frozen=True, slots=True)
class Stage4RuleInventory(CanonicalModel):
    """Complete inventory; completeness is necessary but not sufficient authority."""

    items: tuple[Stage4RuleInventoryItem, ...]
    schema_version: str = field(default=STAGE4_RULE_INVENTORY_SCHEMA_VERSION, init=False)
    strategy_id: str = field(default=STAGE4_STRATEGY_ID, init=False)
    approval_scope: RuleApprovalScope = field(default=STAGE4_APPROVAL_SCOPE, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.items, (list, tuple)) or any(
            not isinstance(item, Stage4RuleInventoryItem) for item in self.items
        ):
            raise TypeError("items must contain only Stage4RuleInventoryItem values")
        by_id = {item.requirement_id: item for item in self.items}
        if len(by_id) != len(self.items):
            raise ValueError("items must not repeat requirement_id")
        actual = set(by_id)
        required = set(STAGE4_REQUIRED_RULE_IDS)
        if actual != required:
            missing = sorted(required - actual)
            extra = sorted(actual - required)
            raise ValueError(f"Stage 4 inventory differs; missing={missing}, extra={extra}")
        object.__setattr__(
            self,
            "items",
            tuple(by_id[requirement_id] for requirement_id in STAGE4_REQUIRED_RULE_IDS),
        )

    @property
    def unapproved_requirement_ids(self) -> tuple[str, ...]:
        return tuple(
            item.requirement_id for item in self.items if item.status is not RuleStatus.APPROVED
        )

    def inventory_hash(self) -> HashDigest:
        return HashDigest(algorithm="sha256", value=self.canonical_sha256())

    def require_complete(self) -> None:
        unapproved = self.unapproved_requirement_ids
        if unapproved:
            raise Stage4RuleReadinessError(
                "STAGE4_RULES_NOT_FULLY_APPROVED",
                f"unapproved P0 requirements: {list(unapproved)}",
            )


def stage4_rule_inventory_from_json_value(value: Any) -> Stage4RuleInventory:
    """Strictly reconstruct the checked-in Stage 4 inventory."""

    item = _strict_mapping(value, keys=_INVENTORY_KEYS, field_name="Stage 4 rule inventory")
    if item["schema_version"] != STAGE4_RULE_INVENTORY_SCHEMA_VERSION:
        raise ValueError("Stage 4 rule inventory schema_version is not supported")
    if item["strategy_id"] != STAGE4_STRATEGY_ID:
        raise ValueError("Stage 4 rule inventory strategy_id is not supported")
    if item["approval_scope"] != STAGE4_APPROVAL_SCOPE.value:
        raise ValueError("Stage 4 rule inventory approval_scope is not supported")
    for field_name in (
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
    ):
        if item[field_name] is not False:
            raise ValueError(f"{field_name} must be false")
    raw_items = item["items"]
    if not isinstance(raw_items, (list, tuple)):
        raise TypeError("Stage 4 rule inventory items must be a JSON array")
    parsed_items: list[Stage4RuleInventoryItem] = []
    for index, raw_item in enumerate(raw_items):
        parsed = _strict_mapping(
            raw_item,
            keys=_ITEM_KEYS,
            field_name=f"Stage 4 rule inventory item {index}",
        )
        parsed_items.append(
            Stage4RuleInventoryItem(
                requirement_id=parsed["requirement_id"],
                status=parsed["status"],
                specification_ref=parsed["specification_ref"],
                approval_id=parsed["approval_id"],
                machine_rule_ref=parsed["machine_rule_ref"],
                positive_test_refs=parsed["positive_test_refs"],
                negative_test_refs=parsed["negative_test_refs"],
                boundary_test_refs=parsed["boundary_test_refs"],
                abstain_test_refs=parsed["abstain_test_refs"],
            )
        )
    return Stage4RuleInventory(items=tuple(parsed_items))


def _validate_stage4_rule_document(
    document: RuleBundleDocument,
    inventory: Stage4RuleInventory,
) -> None:
    if document.strategy_id != STAGE4_STRATEGY_ID:
        raise Stage4RuleReadinessError(
            "STAGE4_STRATEGY_ID_MISMATCH",
            "the rule bundle is not for the industrial-event strategy",
        )
    rules = _strict_mapping(
        document.rules,
        keys=_RULE_DOCUMENT_KEYS,
        field_name="Stage 4 rule bundle rules",
    )
    boundary = _strict_mapping(
        rules["authorization_boundary"],
        keys=_AUTHORIZATION_KEYS,
        field_name="Stage 4 authorization boundary",
    )
    expected_boundary_value = freeze_json(
        {
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
        },
        path="$.stage4_authorization_boundary",
    )
    if not isinstance(expected_boundary_value, Mapping):
        raise TypeError("Stage 4 authorization boundary must freeze to a mapping")
    expected_boundary: Mapping[str, JsonValue] = expected_boundary_value
    if boundary != expected_boundary:
        raise Stage4RuleReadinessError(
            "STAGE4_AUTHORIZATION_BOUNDARY_DRIFT",
            "Stage 4 remains synthetic research validation with zero trading authority",
        )

    binding = _strict_mapping(
        rules["stage4_rule_inventory"],
        keys=_INVENTORY_BINDING_KEYS,
        field_name="Stage 4 rule inventory binding",
    )
    if binding["schema_version"] != STAGE4_RULE_INVENTORY_SCHEMA_VERSION:
        raise Stage4RuleReadinessError(
            "STAGE4_INVENTORY_SCHEMA_MISMATCH",
            "the rule bundle binds an unsupported inventory schema",
        )
    expected_hash = inventory.inventory_hash().to_json_value()
    if binding["inventory_hash"] != expected_hash:
        raise Stage4RuleReadinessError(
            "STAGE4_INVENTORY_HASH_MISMATCH",
            "the rule bundle does not bind the exact approved inventory",
        )
    requirement_ids = binding["requirement_ids"]
    if not isinstance(requirement_ids, (list, tuple)) or tuple(requirement_ids) != (
        STAGE4_REQUIRED_RULE_IDS
    ):
        raise Stage4RuleReadinessError(
            "STAGE4_REQUIREMENT_SET_MISMATCH",
            "the rule bundle must bind the complete ordered Stage 4 P0 requirement set",
        )

    modules = rules["rule_modules"]
    if not isinstance(modules, Mapping):
        raise TypeError("Stage 4 rule_modules must be a JSON object")
    if set(modules) != set(STAGE4_REQUIRED_RULE_IDS):
        raise Stage4RuleReadinessError(
            "STAGE4_RULE_MODULE_SET_MISMATCH",
            "rule_modules must contain every and only Stage-4-owned P0 requirement",
        )
    if any(not isinstance(module, Mapping) or not module for module in modules.values()):
        raise Stage4RuleReadinessError(
            "STAGE4_RULE_MODULE_EMPTY",
            "every approved P0 requirement needs non-empty machine semantics",
        )
    inventory_by_id = {item.requirement_id: item for item in inventory.items}
    for requirement_id in STAGE4_REQUIRED_RULE_IDS:
        module = modules[requirement_id]
        if not isinstance(module, Mapping):  # narrowed after the aggregate check above
            raise TypeError("Stage 4 rule module must be a JSON object")
        if module.get("requirement_id") != requirement_id:
            raise Stage4RuleReadinessError(
                "STAGE4_RULE_MODULE_ID_MISMATCH",
                f"rule module {requirement_id} does not bind its own requirement ID",
            )
        if module.get("machine_rule_ref") != inventory_by_id[requirement_id].machine_rule_ref:
            raise Stage4RuleReadinessError(
                "STAGE4_MACHINE_RULE_REF_MISMATCH",
                f"rule module {requirement_id} does not bind the inventory machine rule",
            )


def require_stage4_rule_capability(
    document: RuleBundleDocument,
    inventory: Stage4RuleInventory,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue Stage 4 capability only after both completeness and exact approval."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(inventory, Stage4RuleInventory):
        raise TypeError("inventory must be a Stage4RuleInventory")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    inventory.require_complete()
    capability = registry.require(document)
    if capability.approval_scope is not STAGE4_APPROVAL_SCOPE:
        raise Stage4RuleReadinessError(
            "STAGE4_APPROVAL_SCOPE_MISMATCH",
            "Stage 2B or another scope cannot authorize Stage 4",
        )
    _validate_stage4_rule_document(document, inventory)
    return capability
