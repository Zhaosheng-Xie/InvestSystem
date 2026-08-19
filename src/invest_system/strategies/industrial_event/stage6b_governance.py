"""Exact Stage 6B validation-only admission approval boundary.

The issued capability permits implementation and isolated validation of the
approved admission contracts, public-HTTPS status confirmation, and temporary
admission seal.  It never authorizes a formal historical run, strategy
evaluation, formal state migration, holdout access, or trading.
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

STAGE6_6B_RULE_BUNDLE_ID = "industrial_event_stage6_6b_historical_admission_atomic_retention"
STAGE6_6B_RULE_BUNDLE_VERSION = "0.1.0"
STAGE6_6B_RULE_BUNDLE_RAW_SHA256 = (
    "c39d06fc822beeec1a78627c67c7ecb82909cf6f3a279786052f74013ebc06a8"
)
STAGE6_6B_RULE_BUNDLE_SHA256 = "c8ee13e82bf3e91f7c5f948c71da5f6af21969caa5ca54792d10e5571c334414"
STAGE6_6B_RULES_SHA256 = "6f3ddba4d510342c9679975576ef2797ddd481034dddef391ec43c3e80b0c20b"
STAGE6_6B_OWNER_APPROVAL_ITEMS_SHA256 = (
    "ad32dfa2db1ec4c8f8b9e2f8f2baf8a604626f9effd15cc049d57d88953827b6"
)
STAGE6_6B_RULE_APPROVAL_ID = "rule_approval_stage6_6b_historical_admission_atomic_retention_v0_1_0"
STAGE6_6B_RULE_APPROVAL_RECORD_SHA256 = (
    "e4ee892f59efea1e29ddb4c8d2ef7adc41711d2a8219e10f4c29f9724214d185"
)
STAGE6_6B_SPECIFICATION_SHA256 = "96ec47da0eb356f726db3ce1be8015366ad3a804cc3f93d63c5b1c3fc65e3f5a"
STAGE6_6B_DRAFT_RAW_SHA256 = "4a5ed454e6ab152e03dc83b9723f035eacd020ff4bfe16d742427b4aaff827e4"
STAGE6_6B_DRAFT_BUNDLE_SHA256 = "0ef8808f8de5e44991bbdecb5bb6a63f1b408d0650fd395c958af454adb262d4"
STAGE6_6B_DRAFT_RULES_SHA256 = "4cd66370471d22169f1308ad4cc9f16852b5b6ebe1f20832ca3de6e30598a73b"
STAGE6_6B_DRAFT_OWNER_ITEMS_SHA256 = (
    "17d1d3dabb4d68e8917ce008f6494d644c006c7a4d57f27a81a2e89260a2a3d8"
)
STAGE6_6B_APPROVAL_DOCUMENT_SHA256 = (
    "040cbe7dc04b0c153d8cd5902486dc4ffb8830c1018bccbfa747678663935aac"
)
STAGE6_6B_AUTHORITY_CONTRACT_SHA256 = (
    "07d3e6a03aa45f38604ecd3728b2ad64b34c075dfc94032431a4486911692238"
)
STAGE6_6B_APPROVAL_SCOPE = RuleApprovalScope.STAGE6_HISTORICAL_ADMISSION_VALIDATION
STAGE6_6B_OWNER_APPROVAL_ITEM_IDS = tuple(f"6B-{number:02d}" for number in range(1, 33))
STAGE6_STRATEGY_ID = "industrial_bottleneck_event"


class Stage6BApprovalCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 6B approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _require_exact_boundary(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="boundary")
    expected = {
        "approval_scope": STAGE6_6B_APPROVAL_SCOPE.value,
        "allowed_run_modes": (),
        "validation_capability_issued": True,
        "authorizes_implementation": True,
        "authorizes_validation_only_public_https_read": True,
        "authorizes_validation_only_confirmation": True,
        "authorizes_validation_only_seal": True,
        "authorizes_formal_historical_run": False,
        "authorizes_strategy_evaluator": False,
        "authorizes_development": False,
        "authorizes_walk_forward": False,
        "authorizes_holdout_open": False,
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
    if dict(boundary) != expected:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_AUTHORIZATION_BOUNDARY_MISMATCH",
            "6B permits isolated admission validation only",
        )


def _require_exact_batch_and_phases(rules: Mapping[str, Any]) -> None:
    batch = _mapping(rules.get("batch"), field_name="batch")
    if dict(batch) != {
        "stage": "Stage 6",
        "batch_id": "6B",
        "purpose": "approved_historical_admission_validation_governance",
        "owner_approval_required": True,
        "approval_items_required": 32,
        "approved_items": 32,
        "approved_machine_bundle_exists": True,
        "approval_record_exists": True,
        "validation_capability_verifier_exists": True,
        "runtime_code_exists": False,
        "formal_storage_migration_exists": False,
        "historical_evaluator_exists": False,
        "formal_historical_run_exists": False,
        "holdout_has_been_opened": False,
    }:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_IMPLEMENTATION_BOUNDARY_MISMATCH",
            "approval lineage must not claim a completed runtime",
        )
    phases = _mapping(rules.get("phase_authority"), field_name="phase_authority")
    if dict(phases) != {
        "6A": "approved_governance_only",
        "6B": "approved_isolated_validation_only_implementation",
        "6C": "not_authorized",
        "6D": "not_authorized",
        "formal_state_migration": "not_authorized",
        "approval_or_completion_is_not_transitive": True,
        "next_allowed_action": "implement_and_accept_isolated_stage6b_admission_validation",
    }:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_PHASE_AUTHORITY_MISMATCH",
            "formal migration and 6C/6D must remain separately gated",
        )


def _require_exact_source_lineage(rules: Mapping[str, Any]) -> None:
    source = _mapping(rules.get("approval_source_binding"), field_name="source")
    expected = {
        "specification_path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6B历史准入状态确认与原子留存精确规则包_v0.1.md"
        ),
        "specification_raw_sha256": STAGE6_6B_SPECIFICATION_SHA256,
        "draft_proposal_path": (
            "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
            "industrial_event_stage6_6b_historical_admission_atomic_retention_"
            "v0.1.0-draft.rule-bundle.json"
        ),
        "draft_raw_sha256": STAGE6_6B_DRAFT_RAW_SHA256,
        "draft_bundle_sha256": STAGE6_6B_DRAFT_BUNDLE_SHA256,
        "draft_rules_sha256": STAGE6_6B_DRAFT_RULES_SHA256,
        "draft_owner_items_sha256": STAGE6_6B_DRAFT_OWNER_ITEMS_SHA256,
        "accepted_rule_source": "exact_draft_rules_by_canonical_sha256",
        "semantic_mutation_during_approval": False,
        "source_files_remain_immutable": True,
    }
    if dict(source) != expected:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_SOURCE_MISMATCH",
            "approved governance must bind the exact owner-reviewed draft",
        )
    document = _mapping(rules.get("document_binding"), field_name="document_binding")
    if dict(document) != {
        "path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6B历史准入状态确认与原子留存批准记录_v0.1.md"
        ),
        "hash": {
            "algorithm": "sha256",
            "value": STAGE6_6B_APPROVAL_DOCUMENT_SHA256,
        },
        "traceability_only": True,
    }:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_DOCUMENT_MISMATCH",
            "approved governance must bind the exact owner approval record",
        )


def _require_exact_items_and_guards(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_ITEMS_INVALID",
            "owner approval items must be immutable",
        )
    identities: list[str] = []
    for raw_item in raw_items:
        item = _mapping(raw_item, field_name="owner_approval_items[]")
        if set(item) != {"approval_item_id", "status"} or item.get("status") != "approved":
            raise Stage6BApprovalCompatibilityError(
                "STAGE6B_APPROVAL_ITEMS_INVALID",
                "all exact owner decisions must be approved",
            )
        item_id = item.get("approval_item_id")
        if not isinstance(item_id, str):
            raise Stage6BApprovalCompatibilityError(
                "STAGE6B_APPROVAL_ITEMS_INVALID",
                "approval item IDs must be strings",
            )
        identities.append(item_id)
    if tuple(identities) != STAGE6_6B_OWNER_APPROVAL_ITEM_IDS or (
        canonical_sha256(raw_items) != STAGE6_6B_OWNER_APPROVAL_ITEMS_SHA256
    ):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_ITEMS_INVALID",
            "approved decisions differ from exact 6B-01 through 6B-32",
        )
    atomicity = _mapping(rules.get("owner_approval_atomicity"), field_name="atomicity")
    if dict(atomicity) != {
        "all_32_required": True,
        "authorization_predicate": "all(6B-01..6B-32==approved)",
        "same_exact_bundle_and_approval_record_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
    }:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_ATOMICITY_MISMATCH",
            "the thirty-two decisions may authorize only as one atomic set",
        )
    guards = _mapping(rules.get("approved_semantic_guards"), field_name="guards")
    if dict(guards) != {
        "one_external_strategy_input_ref": True,
        "complete_transitive_release_closure_required": True,
        "authority_contract_hash": STAGE6_6B_AUTHORITY_CONTRACT_SHA256,
        "fresh_public_https_status_required": True,
        "confirmation_items_equal_complete_closure": True,
        "seal_is_only_admission_completion_marker": True,
        "any_failure_authoritative_rows_and_evaluator_calls_are_zero": True,
        "validation_store_is_temporary_and_isolated": True,
        "stage5d_sqlite_v4_reuse_forbidden": True,
        "formal_state_migration_requires_separate_owner_approval": True,
        "withdrawal_blocks_new_seal_and_preserves_audit_only_history": True,
        "formal_historical_run_and_strategy_evaluator_remain_unauthorized": True,
        "stage6c_and_stage6d_remain_unauthorized": True,
        "all_outputs_authority_eligible_false": True,
    }:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_SEMANTIC_GUARD_MISMATCH",
            "the approved admission safety guards must remain exact",
        )


def require_stage6b_admission_validation_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact owner-approved, validation-only 6B capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    if (
        document.strategy_id,
        document.bundle_id,
        document.bundle_version,
    ) != (STAGE6_STRATEGY_ID, STAGE6_6B_RULE_BUNDLE_ID, STAGE6_6B_RULE_BUNDLE_VERSION):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_RULE_IDENTITY_UNSUPPORTED",
            "only the exact owner-approved Stage 6B bundle may issue capability",
        )
    _require_exact_boundary(document.rules)
    _require_exact_batch_and_phases(document.rules)
    _require_exact_source_lineage(document.rules)
    _require_exact_items_and_guards(document.rules)
    if document.rules.get("runtime_must_not_parse_markdown") is not True or (
        canonical_sha256(document.rules) != STAGE6_6B_RULES_SHA256
        or document.bundle_hash().value != STAGE6_6B_RULE_BUNDLE_SHA256
    ):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_RULE_HASH_UNSUPPORTED",
            "the Stage 6B machine governance differs from the owner-approved version",
        )
    capability = registry.require(document)
    if capability.approval_scope is not STAGE6_6B_APPROVAL_SCOPE:
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 6B validation",
        )
    if capability.approval_id != STAGE6_6B_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE6_6B_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage6BApprovalCompatibilityError(
            "STAGE6B_APPROVAL_RECORD_UNSUPPORTED",
            "the capability requires the exact Stage 6B owner approval record",
        )
    return capability
