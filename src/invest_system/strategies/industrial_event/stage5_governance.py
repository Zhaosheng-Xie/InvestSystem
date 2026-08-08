"""Exact Stage 5A approval boundary without execution business logic.

The owner-approved bundle may issue only an anonymous synthetic execution-
validation capability.  This module deliberately implements no market-rule
table, fill model, portfolio state, ledger, P&L, replay engine, persistence,
broker adapter, or real-account integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    CURRENT_RULE_APPROVAL_REGISTRY,
    ApprovedRuleCapability,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
)

STAGE5_STRATEGY_ID = "industrial_bottleneck_event"
STAGE5_APPROVAL_SCOPE = RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION
STAGE5_5A_RULE_BUNDLE_ID = "industrial_event_stage5_5a_execution_portfolio_ledger_replay"
STAGE5_5A_RULE_BUNDLE_VERSION = "0.1.0"
STAGE5_5A_RULE_BUNDLE_SHA256 = "c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7"
STAGE5_5A_RULES_SHA256 = "bb7ef84b1287be1111fe95571efa58cd268a65d862b7d235508fc31ccbaf0c69"
STAGE5_5A_RULE_APPROVAL_ID = "rule_approval_stage5_5a_execution_portfolio_ledger_replay_v0_1_0"
STAGE5_5A_RULE_APPROVAL_RECORD_SHA256 = (
    "5b9536f546337ba38408d255b3fbad68fbbdf6d9ccba9af79b10b6e04ca8cd78"
)
STAGE5_5A_SPECIFICATION_SHA256 = "df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740"
STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256 = (
    "d0664b6b371ad042218f5d3c6caac9b9f1d1edd3ff475a5f7b36e401ca3d02db"
)
STAGE5_5A_DRAFT_RULES_SHA256 = "ecc61a4ee3eb3a7e4dea7238c027aca2ac3c2ce145eb40f0fa80bb34085463f5"
STAGE5_5A_APPROVAL_DOCUMENT_SHA256 = (
    "4862d0c8add5d28db8f24432d4d3958c9de6f73bf74ae7d4754e0290916cbf02"
)
STAGE5_5A_OWNER_APPROVAL_ITEM_IDS = tuple(f"5A-{number:02d}" for number in range(1, 41))

_EXPECTED_UPSTREAM = {
    "batch_id": "4B",
    "bundle_id": "industrial_event_stage4_4b_complete_engine_integration",
    "bundle_version": "0.1.0",
    "bundle_hash": "ba8886cf85beef084c2a2d3b83446b499c7786fbc3f0e56066fb8cedc8e27e77",
    "rules_hash": "3477d237523ce84239ca1363ad1c8d2e467528ec90acb0034193aeb320740019",
    "approval_record_hash": ("d809394ef00beab2053795779878025fb1b3b0cd2a49da76302e500ef7f4b2fe"),
    "stage4_inventory_hash": ("fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53"),
}


class Stage5RuleCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 5A approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _hash_value(value: Any, *, field_name: str) -> str:
    item = _mapping(value, field_name=field_name)
    if set(item) != {"algorithm", "value"} or item.get("algorithm") != "sha256":
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an exact SHA-256 identity",
        )
    digest = item.get("value")
    if not isinstance(digest, str):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name}.value must be text",
        )
    return digest


def _require_exact_authority(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="authorization_boundary")
    expected = {
        "approval_scope": STAGE5_APPROVAL_SCOPE.value,
        "allowed_run_modes": ("research",),
        "synthetic_only": True,
        "validation_only": True,
        "runtime_capability_issued": True,
        "authorizes_backtest": False,
        "authorizes_paper": False,
        "authorizes_shadow": False,
        "authorizes_live": False,
        "authorizes_real_positions": False,
        "authorizes_real_accounts": False,
        "authorizes_real_orders": False,
        "authorizes_broker_connectivity": False,
        "authorizes_kb_write": False,
    }
    if dict(boundary) != expected:
        raise Stage5RuleCompatibilityError(
            "STAGE5_AUTHORIZATION_BOUNDARY_MISMATCH",
            "the approved Stage 5A capability must remain synthetic research validation only",
        )


def _require_exact_approval_items(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_ITEMS_INVALID",
            "owner_approval_items must be an immutable sequence",
        )
    identities: list[str] = []
    for raw_item in raw_items:
        item = _mapping(raw_item, field_name="owner_approval_items[]")
        if set(item) != {"approval_item_id", "status"} or item.get("status") != "approved":
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_ITEMS_INVALID",
                "all and only the forty owner decisions must be approved",
            )
        item_id = item.get("approval_item_id")
        if not isinstance(item_id, str):
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_ITEMS_INVALID",
                "approval_item_id must be text",
            )
        identities.append(item_id)
    if tuple(identities) != STAGE5_5A_OWNER_APPROVAL_ITEM_IDS:
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_ITEMS_INVALID",
            "the approved decision identity sequence differs from 5A-01 through 5A-40",
        )


def _require_exact_lineage(rules: Mapping[str, Any]) -> None:
    upstream = _mapping(rules.get("exact_upstream_dependency"), field_name="upstream")
    for field_name in ("batch_id", "bundle_id", "bundle_version"):
        if upstream.get(field_name) != _EXPECTED_UPSTREAM[field_name]:
            raise Stage5RuleCompatibilityError(
                "STAGE5_UPSTREAM_IDENTITY_MISMATCH",
                f"{field_name} differs from the approved Stage 4B identity",
            )
    for field_name in (
        "bundle_hash",
        "rules_hash",
        "approval_record_hash",
        "stage4_inventory_hash",
    ):
        if (
            _hash_value(upstream.get(field_name), field_name=field_name)
            != _EXPECTED_UPSTREAM[field_name]
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_UPSTREAM_IDENTITY_MISMATCH",
                f"{field_name} differs from the approved Stage 4B identity",
            )

    source = _mapping(rules.get("approval_source_binding"), field_name="approval_source_binding")
    if (
        _hash_value(source.get("specification_hash"), field_name="specification_hash")
        != STAGE5_5A_SPECIFICATION_SHA256
        or _hash_value(source.get("draft_bundle_hash"), field_name="draft_bundle_hash")
        != STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256
        or _hash_value(source.get("draft_rules_hash"), field_name="draft_rules_hash")
        != STAGE5_5A_DRAFT_RULES_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SOURCE_MISMATCH",
            "the approved bundle is not bound to the exact owner-reviewed draft lineage",
        )
    document_binding = _mapping(rules.get("document_binding"), field_name="document_binding")
    if (
        _hash_value(document_binding.get("hash"), field_name="document_binding.hash")
        != STAGE5_5A_APPROVAL_DOCUMENT_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SOURCE_MISMATCH",
            "the approved bundle is not bound to the exact owner approval document",
        )


def require_stage5_rule_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact Stage 5A synthetic execution-validation capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    expected_identity = (
        STAGE5_STRATEGY_ID,
        STAGE5_5A_RULE_BUNDLE_ID,
        STAGE5_5A_RULE_BUNDLE_VERSION,
    )
    if (document.strategy_id, document.bundle_id, document.bundle_version) != expected_identity:
        raise Stage5RuleCompatibilityError(
            "STAGE5_RULE_IDENTITY_UNSUPPORTED",
            "only the exact approved Stage 5A bundle may issue capability",
        )
    _require_exact_authority(document.rules)
    _require_exact_approval_items(document.rules)
    _require_exact_lineage(document.rules)
    if canonical_sha256(document.rules) != STAGE5_5A_RULES_SHA256 or (
        document.bundle_hash().value != STAGE5_5A_RULE_BUNDLE_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_RULE_HASH_UNSUPPORTED",
            "the Stage 5A machine semantics differ from the owner-approved version",
        )
    capability = registry.require(document)
    if capability.approval_scope is not STAGE5_APPROVAL_SCOPE:
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 5A",
        )
    if capability.approval_id != STAGE5_5A_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_RECORD_UNSUPPORTED",
            "the capability requires the exact owner approval record",
        )
    return capability
