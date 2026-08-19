"""Exact Stage 6A governance approval without historical-run authority.

The issued capability proves only that the owner approved the exact 6A
preregistration design.  It cannot confirm a KB Release, persist a historical
run, open a holdout, execute a backtest, or authorize any trading mode.
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

STAGE6_STRATEGY_ID = "industrial_bottleneck_event"
STAGE6_6A_RULE_BUNDLE_ID = "industrial_event_stage6_6a_historical_validation_preregistration"
STAGE6_6A_RULE_BUNDLE_VERSION = "0.1.0"
STAGE6_6A_RULE_BUNDLE_RAW_SHA256 = (
    "4d933c04b341e454009f49ed9e912d22d4b62878473e02e47ebf51e956cdabee"
)
STAGE6_6A_RULE_BUNDLE_SHA256 = "9a3f663936b0ad83795c7338c6b93fc9617d1f9ed6f4ccca6f92dd2fd06f6505"
STAGE6_6A_RULES_SHA256 = "f1f42898fd61f21724d8bfe22158d2a22f6499b52c670d27e7c2f69800cbea80"
STAGE6_6A_OWNER_APPROVAL_ITEMS_SHA256 = (
    "03a4fdde65cc5d4d567eb71b46cdd57e95348e90a552330cf6958cbd409e8dbb"
)
STAGE6_6A_RULE_APPROVAL_ID = "rule_approval_stage6_6a_historical_validation_preregistration_v0_1_0"
STAGE6_6A_RULE_APPROVAL_RECORD_SHA256 = (
    "c81fca2c42a160b91a4ebbb2f2144b8e12ada28a270cb1f810104695bb0a3076"
)
STAGE6_6A_SPECIFICATION_SHA256 = "7ef1126261ddbead37c016fe472a8d518cddb553fe3c3d1214f5c378a9b964df"
STAGE6_6A_DRAFT_RAW_SHA256 = "a071e2509bcf86361836cdd5e5d0748748b607e1129edc4f47c308de7073cdca"
STAGE6_6A_DRAFT_BUNDLE_SHA256 = "41759cb4e4db282d98bc70b3a599f632283d2cf79330adab910b1bc9a308eb92"
STAGE6_6A_DRAFT_RULES_SHA256 = "c1d0298488317318b8d9dedde9f1ff719aa83d08af7196d255482e11522dc097"
STAGE6_6A_DRAFT_OWNER_ITEMS_SHA256 = (
    "ea2b4b9d232884d3cd12b4a8003562261fc8e6c8e8f299b88f1df1fb16e3fcfe"
)
STAGE6_6A_APPROVAL_DOCUMENT_SHA256 = (
    "392eb5461c3e1c0e2ff3654fe0eea729de2671adb0bc5207854b98f8fbe79b9f"
)
STAGE6_6A_APPROVAL_SCOPE = RuleApprovalScope.STAGE6_HISTORICAL_VALIDATION_GOVERNANCE
STAGE6_6A_OWNER_APPROVAL_ITEM_IDS = tuple(f"6A-{number:02d}" for number in range(1, 36))


class Stage6ApprovalCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 6A approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _require_exact_boundary(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="boundary")
    expected = {
        "approval_scope": STAGE6_6A_APPROVAL_SCOPE.value,
        "allowed_run_modes": (),
        "governance_capability_issued": True,
        "authorizes_forming_stage6b_draft": True,
        "authorizes_stage6b_implementation": False,
        "authorizes_stage6c_execution": False,
        "authorizes_stage6d_holdout": False,
        "authorizes_historical_run": False,
        "authorizes_release_status_confirmation": False,
        "authorizes_state_persistence": False,
        "authorizes_holdout_open": False,
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
    }
    if dict(boundary) != expected:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_AUTHORIZATION_BOUNDARY_MISMATCH",
            "6A may authorize governance and formation of a 6B draft only",
        )


def _require_exact_batch_and_phases(rules: Mapping[str, Any]) -> None:
    batch = _mapping(rules.get("batch"), field_name="batch")
    if dict(batch) != {
        "stage": "Stage 6",
        "batch_id": "6A",
        "purpose": "approved_historical_validation_preregistration_governance",
        "owner_approval_required": True,
        "approval_items_required": 35,
        "approved_items": 35,
        "approved_machine_bundle_exists": True,
        "approval_record_exists": True,
        "governance_capability_verifier_exists": True,
        "historical_evaluator_exists": False,
        "release_confirmation_issuer_exists": False,
        "state_persistence_exists": False,
        "holdout_has_been_opened": False,
    }:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_IMPLEMENTATION_BOUNDARY_MISMATCH",
            "approved governance must not claim historical execution",
        )
    phases = _mapping(rules.get("phase_authority"), field_name="phase_authority")
    if dict(phases) != {
        "6A": "approved_governance_only",
        "6B": "not_authorized",
        "6C": "not_authorized",
        "6D": "not_authorized",
        "approval_or_completion_is_not_transitive": True,
        "next_allowed_action": "form_exact_stage6b_draft_for_owner_review",
    }:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_PHASE_AUTHORITY_MISMATCH",
            "6B through 6D must remain separately gated",
        )


def _require_exact_source_lineage(rules: Mapping[str, Any]) -> None:
    source = _mapping(rules.get("approval_source_binding"), field_name="source")
    expected = {
        "specification_path": (
            "产业卡点及事件驱动系统/03_规则与规格/Stage6_6A历史验证预注册与准入精确规则包_v0.1.md"
        ),
        "specification_raw_sha256": STAGE6_6A_SPECIFICATION_SHA256,
        "draft_proposal_path": (
            "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
            "industrial_event_stage6_6a_historical_validation_preregistration_"
            "v0.1.0-draft.rule-bundle.json"
        ),
        "draft_raw_sha256": STAGE6_6A_DRAFT_RAW_SHA256,
        "draft_bundle_sha256": STAGE6_6A_DRAFT_BUNDLE_SHA256,
        "draft_rules_sha256": STAGE6_6A_DRAFT_RULES_SHA256,
        "draft_owner_items_sha256": STAGE6_6A_DRAFT_OWNER_ITEMS_SHA256,
        "accepted_rule_source": "exact_draft_rules_by_canonical_sha256",
        "semantic_mutation_during_approval": False,
        "source_files_remain_immutable": True,
    }
    if dict(source) != expected:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_SOURCE_MISMATCH",
            "approved governance must bind the exact owner-reviewed draft",
        )
    document = _mapping(rules.get("document_binding"), field_name="document_binding")
    if dict(document) != {
        "path": (
            "产业卡点及事件驱动系统/03_规则与规格/Stage6_6A历史验证预注册与准入批准记录_v0.1.md"
        ),
        "hash": {
            "algorithm": "sha256",
            "value": STAGE6_6A_APPROVAL_DOCUMENT_SHA256,
        },
        "traceability_only": True,
    }:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_DOCUMENT_MISMATCH",
            "approved governance must bind the exact owner approval record",
        )


def _require_exact_items_and_guards(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_ITEMS_INVALID",
            "owner approval items must be immutable",
        )
    identities: list[str] = []
    for raw_item in raw_items:
        item = _mapping(raw_item, field_name="owner_approval_items[]")
        if set(item) != {"approval_item_id", "status"} or item.get("status") != "approved":
            raise Stage6ApprovalCompatibilityError(
                "STAGE6A_APPROVAL_ITEMS_INVALID",
                "all exact owner decisions must be approved",
            )
        item_id = item.get("approval_item_id")
        if not isinstance(item_id, str):
            raise Stage6ApprovalCompatibilityError(
                "STAGE6A_APPROVAL_ITEMS_INVALID",
                "approval item IDs must be strings",
            )
        identities.append(item_id)
    if tuple(identities) != STAGE6_6A_OWNER_APPROVAL_ITEM_IDS or (
        canonical_sha256(raw_items) != STAGE6_6A_OWNER_APPROVAL_ITEMS_SHA256
    ):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_ITEMS_INVALID",
            "approved decisions differ from exact 6A-01 through 6A-35",
        )
    atomicity = _mapping(rules.get("owner_approval_atomicity"), field_name="atomicity")
    if dict(atomicity) != {
        "all_35_required": True,
        "authorization_predicate": "all(6A-01..6A-35==approved)",
        "same_exact_bundle_and_approval_record_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
    }:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_ATOMICITY_MISMATCH",
            "the thirty-five decisions may authorize only as one atomic set",
        )
    guards = _mapping(rules.get("approved_semantic_guards"), field_name="guards")
    if dict(guards) != {
        "preregistration_frozen_before_performance": True,
        "historical_admission_requires_separate_stage6b_approval": True,
        "unsupported_stage5d_input_remains_blocked_or_abstain": True,
        "coverage_failure_is_insufficient_evidence": True,
        "holdout_tuning_forbidden": True,
        "full_system_must_beat_best_simple_competitor": True,
        "prd_numeric_thresholds_remain_hypothesis": True,
        "historical_result_is_not_forward_or_live_evidence": True,
    }:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_SEMANTIC_GUARD_MISMATCH",
            "the approved preregistration safety guards must remain exact",
        )


def require_stage6a_governance_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact owner-approved, zero-run-authority 6A capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    if (
        document.strategy_id,
        document.bundle_id,
        document.bundle_version,
    ) != (STAGE6_STRATEGY_ID, STAGE6_6A_RULE_BUNDLE_ID, STAGE6_6A_RULE_BUNDLE_VERSION):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_RULE_IDENTITY_UNSUPPORTED",
            "only the exact owner-approved Stage 6A bundle may issue capability",
        )
    _require_exact_boundary(document.rules)
    _require_exact_batch_and_phases(document.rules)
    _require_exact_source_lineage(document.rules)
    _require_exact_items_and_guards(document.rules)
    if document.rules.get("runtime_must_not_parse_markdown") is not True or (
        canonical_sha256(document.rules) != STAGE6_6A_RULES_SHA256
        or document.bundle_hash().value != STAGE6_6A_RULE_BUNDLE_SHA256
    ):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_RULE_HASH_UNSUPPORTED",
            "the Stage 6A machine governance differs from the owner-approved version",
        )
    capability = registry.require(document)
    if capability.approval_scope is not STAGE6_6A_APPROVAL_SCOPE:
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 6A governance",
        )
    if capability.approval_id != STAGE6_6A_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE6_6A_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage6ApprovalCompatibilityError(
            "STAGE6A_APPROVAL_RECORD_UNSUPPORTED",
            "the capability requires the exact Stage 6A owner approval record",
        )
    return capability
