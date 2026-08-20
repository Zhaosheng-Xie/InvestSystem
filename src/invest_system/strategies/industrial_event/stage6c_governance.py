"""Exact Stage 6C v0.2 anonymous synthetic-kernel approval boundary.

The capability permits implementation and validation of pure holdout-isolation,
candidate/fold, statistics, and replay contracts using anonymous synthetic
fixtures. It never authorizes a formal historical run, holdout access, state
migration, strategy conclusion, or trading.
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

STAGE6_6C_RULE_BUNDLE_ID = "industrial_event_stage6_6c_development_walk_forward_champion_challenge"
STAGE6_6C_RULE_BUNDLE_VERSION = "0.2.0"
STAGE6_6C_RULE_BUNDLE_RAW_SHA256 = (
    "77e76205b2d4de2163b914bcab2fffb0baa2087e6b89c543dfb538ac366e863a"
)
STAGE6_6C_RULE_BUNDLE_SHA256 = "6ce5a6bd3cc892540be8f3ed5cec900388dbaa6f8ccbe0b7be7eb801d530e11a"
STAGE6_6C_RULES_SHA256 = "cd1581d11c2aa75564329197f0cf7d6d353683f371caf0a0dc65179abeaef323"
STAGE6_6C_OWNER_APPROVAL_ITEMS_SHA256 = (
    "82e7911106d46d876956bddf73d718c18a6fdf5d9d7b50e4b13e1c750ddc1582"
)
STAGE6_6C_RULE_APPROVAL_ID = "rule_approval_stage6_6c_development_walk_forward_v0_2_0"
STAGE6_6C_RULE_APPROVAL_RECORD_SHA256 = (
    "afabd62f918361565eb9f0a15357d6cade39ed445957c92039f5efee1e66414e"
)
STAGE6_6C_APPROVAL_DOCUMENT_SHA256 = (
    "d68c6dca0963469e1a0f06e030f3400a534653b372b5a78c229170577c5d653f"
)
STAGE6_6C_SPECIFICATION_SHA256 = "3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368"
STAGE6_6C_DRAFT_RAW_SHA256 = "6f2663feb8b8cef5fd969d2791d2505b82e31ff42071872df0350c2196007afd"
STAGE6_6C_DRAFT_BUNDLE_SHA256 = "a45396cde1e23ab6c05ea03111cf9f72044031a57d6a91dce554e15d6979a72c"
STAGE6_6C_DRAFT_RULES_SHA256 = "c64f2b6057355c5e0bca9d597c01ed9f39ae0fd483ee469de86f7c964d8879c8"
STAGE6_6C_DRAFT_OWNER_ITEMS_SHA256 = (
    "7e3eee1c02a8d16e27ec3180379d221302ff3ca1741bb43300f145063f910bd6"
)
STAGE6_6C_APPROVAL_SCOPE = RuleApprovalScope.STAGE6_DEVELOPMENT_WALK_FORWARD_VALIDATION
STAGE6_6C_OWNER_APPROVAL_ITEM_IDS = tuple(f"6C-{number:02d}" for number in range(1, 41))

_CRITICAL_MODULE_HASHES = {
    "holdout_technical_isolation": (
        "209406d9155d4855fb5e4249e3ff45e2bebea256db4777cdda40dd17f724e9ce"
    ),
    "inference_and_multiple_testing": (
        "2b6a34b084e713c21db330cc20fc3ec5b0b7e59715179fa6e12a7908a1a1422a"
    ),
    "coverage_selection_audit": (
        "856fafd224b384db0f8950ca269e5a94c3ff6db23962661540c5caed55d23e54"
    ),
    "exact_primary_estimator_and_benchmark": (
        "e87fbaefefb34c37ceb6fdfee4d0e41df578ff3e87e87e60d19e6646de006a4f"
    ),
    "approved_semantic_guards": (
        "8b032dbde11c3c3ee33451c63da914ad35cf3c3da877c870869a21b6da866c36"
    ),
}


class Stage6CApprovalCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 6C approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVED_CONTRACT_INVALID", f"{field_name} must be an object"
        )
    return value


def _require_boundary_and_batch(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="boundary")
    expected_boundary = {
        "approval_scope": STAGE6_6C_APPROVAL_SCOPE.value,
        "allowed_run_modes": (),
        "validation_capability_issued": True,
        "authorizes_implementation": True,
        "authorizes_synthetic_kernel_validation": True,
        "authorizes_formal_historical_admission": False,
        "authorizes_formal_development_run": False,
        "authorizes_walk_forward_run": False,
        "authorizes_holdout_commitment_read": False,
        "authorizes_holdout_artifact_read": False,
        "authorizes_holdout_open": False,
        "authorizes_stage6_final_pass": False,
        "authorizes_formal_state_migration": False,
        "authorizes_backtest": False,
        "authorizes_paper": False,
        "authorizes_shadow": False,
        "authorizes_live": False,
        "authorizes_positions": False,
        "authorizes_orders": False,
        "authorizes_broker_connection": False,
        "authorizes_kb_internal_reads": False,
        "authorizes_kb_writes": False,
        "authorizes_funds_deployment": False,
        "authority_eligible": False,
    }
    if dict(boundary) != expected_boundary:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_AUTHORIZATION_BOUNDARY_MISMATCH",
            "6C approval permits anonymous synthetic kernel validation only",
        )
    batch = _mapping(rules.get("batch"), field_name="batch")
    expected_batch = {
        "stage": "Stage 6",
        "batch_id": "6C-v0.2",
        "purpose": "approved_anonymous_synthetic_walk_forward_kernel_validation",
        "owner_approval_required": True,
        "approval_items_required": 40,
        "approved_items": 40,
        "approved_machine_bundle_exists": True,
        "approval_record_exists": True,
        "validation_capability_verifier_exists": True,
        "runtime_code_exists": False,
        "formal_historical_run_exists": False,
        "walk_forward_results_exist": False,
        "holdout_has_been_opened": False,
    }
    if dict(batch) != expected_batch:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_IMPLEMENTATION_BOUNDARY_MISMATCH",
            "approval lineage must not claim a completed 6C runtime",
        )


def _require_source_and_document(rules: Mapping[str, Any]) -> None:
    source = _mapping(rules.get("approval_source_binding"), field_name="source")
    expected_source = {
        "specification_path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md"
        ),
        "specification_raw_sha256": STAGE6_6C_SPECIFICATION_SHA256,
        "draft_proposal_path": (
            "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
            "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
            "v0.2.0-draft.rule-bundle.json"
        ),
        "draft_raw_sha256": STAGE6_6C_DRAFT_RAW_SHA256,
        "draft_bundle_sha256": STAGE6_6C_DRAFT_BUNDLE_SHA256,
        "draft_rules_sha256": STAGE6_6C_DRAFT_RULES_SHA256,
        "draft_owner_items_sha256": STAGE6_6C_DRAFT_OWNER_ITEMS_SHA256,
        "v0_1_specification_sha256": (
            "bcf77c5608eb09fd3e591f0bd92a3e0e71a27c42c18123e26e98080db9609383"
        ),
        "v0_1_draft_raw_sha256": (
            "03e6717ab0de1b2c595e46b7a2a25c5cd3947ba9942a6e939f21636ce114e881"
        ),
        "accepted_rule_source": "exact_v0_1_rules_plus_exact_v0_2_replacements",
        "complete_rules_materialized": True,
        "runtime_delta_or_markdown_merge_forbidden": True,
        "source_files_remain_immutable": True,
    }
    if dict(source) != expected_source:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_SOURCE_MISMATCH",
            "approved governance must bind and materialize exact v0.1 plus v0.2",
        )
    document = _mapping(rules.get("document_binding"), field_name="document")
    if dict(document) != {
        "path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6C开发样本WalkForward与冠军挑战批准记录_v0.2.md"
        ),
        "hash": {
            "algorithm": "sha256",
            "value": STAGE6_6C_APPROVAL_DOCUMENT_SHA256,
        },
        "traceability_only": True,
    }:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_DOCUMENT_MISMATCH",
            "approved governance must bind the exact owner approval record",
        )


def _require_items_and_modules(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_ITEMS_INVALID", "approval items must be immutable"
        )
    identities: list[str] = []
    for raw in raw_items:
        item = _mapping(raw, field_name="owner_approval_items[]")
        if set(item) != {"approval_item_id", "status"} or item.get("status") != "approved":
            raise Stage6CApprovalCompatibilityError(
                "STAGE6C_APPROVAL_ITEMS_INVALID", "all forty decisions must be approved"
            )
        item_id = item.get("approval_item_id")
        if not isinstance(item_id, str):
            raise Stage6CApprovalCompatibilityError(
                "STAGE6C_APPROVAL_ITEMS_INVALID", "approval item IDs must be strings"
            )
        identities.append(item_id)
    if tuple(identities) != STAGE6_6C_OWNER_APPROVAL_ITEM_IDS or (
        canonical_sha256(raw_items) != STAGE6_6C_OWNER_APPROVAL_ITEMS_SHA256
    ):
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_ITEMS_INVALID", "approved item identity differs"
        )
    atomicity = _mapping(rules.get("owner_approval_atomicity"), field_name="atomicity")
    if dict(atomicity) != {
        "all_40_required": True,
        "authorization_predicate": "all(v0.2_6C-01..6C-40==approved)",
        "same_exact_bundle_and_approval_record_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
    }:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_ATOMICITY_MISMATCH", "forty decisions must remain atomic"
        )
    for field_name, expected_hash in _CRITICAL_MODULE_HASHES.items():
        if canonical_sha256(rules.get(field_name)) != expected_hash:
            raise Stage6CApprovalCompatibilityError(
                "STAGE6C_CRITICAL_RULE_DRIFT",
                f"approved critical rule differs: {field_name}",
            )


def require_stage6c_kernel_validation_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact approved anonymous synthetic Stage 6C capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if (
        document.strategy_id != "industrial_bottleneck_event"
        or document.bundle_id != STAGE6_6C_RULE_BUNDLE_ID
        or document.bundle_version != STAGE6_6C_RULE_BUNDLE_VERSION
        or document.bundle_hash().value != STAGE6_6C_RULE_BUNDLE_SHA256
        or canonical_sha256(document.rules) != STAGE6_6C_RULES_SHA256
    ):
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_RULE_IDENTITY_MISMATCH",
            "Stage 6C machine governance differs from the owner-approved version",
        )
    _require_boundary_and_batch(document.rules)
    _require_source_and_document(document.rules)
    _require_items_and_modules(document.rules)
    capability = registry.require(document)
    if capability.approval_scope is not STAGE6_6C_APPROVAL_SCOPE:
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 6C",
        )
    if capability.approval_id != STAGE6_6C_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE6_6C_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage6CApprovalCompatibilityError(
            "STAGE6C_APPROVAL_RECORD_MISMATCH",
            "the Stage 6C approval record identity differs",
        )
    return capability


__all__ = [
    "STAGE6_6C_APPROVAL_DOCUMENT_SHA256",
    "STAGE6_6C_APPROVAL_SCOPE",
    "STAGE6_6C_DRAFT_BUNDLE_SHA256",
    "STAGE6_6C_DRAFT_OWNER_ITEMS_SHA256",
    "STAGE6_6C_DRAFT_RAW_SHA256",
    "STAGE6_6C_DRAFT_RULES_SHA256",
    "STAGE6_6C_OWNER_APPROVAL_ITEM_IDS",
    "STAGE6_6C_OWNER_APPROVAL_ITEMS_SHA256",
    "STAGE6_6C_RULE_APPROVAL_ID",
    "STAGE6_6C_RULE_APPROVAL_RECORD_SHA256",
    "STAGE6_6C_RULE_BUNDLE_ID",
    "STAGE6_6C_RULE_BUNDLE_RAW_SHA256",
    "STAGE6_6C_RULE_BUNDLE_SHA256",
    "STAGE6_6C_RULE_BUNDLE_VERSION",
    "STAGE6_6C_RULES_SHA256",
    "STAGE6_6C_SPECIFICATION_SHA256",
    "Stage6CApprovalCompatibilityError",
    "require_stage6c_kernel_validation_capability",
]
