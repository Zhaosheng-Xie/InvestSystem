"""Exact Stage 5D approval lineage without Stage 5D business logic.

This boundary may issue only the owner-approved anonymous synthetic research
capability.  It deliberately implements no Ledger V2 event, corporate action,
mark, valuation, P&L, replay evaluator, SQLite migration, or durable write.
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

from .stage5_governance import (
    STAGE5_5A_APPROVAL_DOCUMENT_SHA256,
    STAGE5_5A_RULE_APPROVAL_ID,
    STAGE5_5A_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5A_RULE_BUNDLE_ID,
    STAGE5_5A_RULE_BUNDLE_SHA256,
    STAGE5_5A_RULE_BUNDLE_VERSION,
    STAGE5_5A_RULES_SHA256,
    STAGE5_5A_SPECIFICATION_SHA256,
    STAGE5_APPROVAL_SCOPE,
    STAGE5_STRATEGY_ID,
)

STAGE5_5D_RULE_BUNDLE_ID = "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence"
STAGE5_5D_RULE_BUNDLE_VERSION = "0.1.0"
STAGE5_5D_RULE_BUNDLE_RAW_SHA256 = (
    "8f65be5d4817c915faaa74608508bc4e27e7a063126cb8d1239f7b2241f745ef"
)
STAGE5_5D_RULE_BUNDLE_SHA256 = "0202d8a15e85851e58af06e9e7c62903efd51f87c7222cbb0172d9e59648be63"
STAGE5_5D_RULES_SHA256 = "22c84398b52dd20f09fe9c7c18edeccfd0f132cc3892b670d21a945b28665dcb"
STAGE5_5D_RULE_APPROVAL_ID = (
    "rule_approval_stage5_5d_corporate_action_pnl_replay_persistence_v0_1_0"
)
STAGE5_5D_RULE_APPROVAL_RECORD_SHA256 = (
    "9f2e3a08dc209d276b4ed82eed416719e9fcf83f86dd6f571afd70d82ab7ea05"
)
STAGE5_5D_SPECIFICATION_SHA256 = "db09ab438836167e0736aaa459d82fc24c6a22de6868ef7b0952e6546b410f46"
STAGE5_5D_DRAFT_RULE_BUNDLE_RAW_SHA256 = (
    "a17de440604be1bd3bd1d981af3bbf0dd458e0db97251830053b4aaf711f29d2"
)
STAGE5_5D_DRAFT_RULE_BUNDLE_SHA256 = (
    "88189304fa4a68262c2ee72a0ca74f3d6235f995ffb4858bece32087ce579d22"
)
STAGE5_5D_DRAFT_RULES_SHA256 = "04b693c343fd85e07284bbf1b15eef09fa5b00b9a3dfc01ad82cf4597e3606ac"
STAGE5_5D_DRAFT_OWNER_APPROVAL_ITEMS_SHA256 = (
    "38bfe202d8583c531a4ce17a08d5ce3c2d02fe55db9bddf70850de4e0ab7e337"
)
STAGE5_5D_OWNER_APPROVAL_ITEMS_SHA256 = (
    "06b28ba6ffaaa5b8afa6bbfbbd2b496930d63478e410b08cd71e616be7eefcf4"
)
STAGE5_5D_APPROVAL_DOCUMENT_SHA256 = (
    "bde155cc3d03d038f2a182ba6ec1c1fd5d4f2ccafba5ff75c1979db728422436"
)
STAGE5_5D_OWNER_APPROVAL_ITEM_IDS = tuple(f"5D-{number:02d}" for number in range(1, 49))
STAGE5_5D_STAGE5C_BASELINE_COMMIT = "7f64c584c5c7be5e2385a177fab9e5d31e3f665b"
STAGE5_5D_APPROVAL_SCOPE = STAGE5_APPROVAL_SCOPE

_SPECIFICATION_PATH = (
    "产业卡点及事件驱动系统/03_规则与规格/"
    "Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md"
)
_DRAFT_BUNDLE_PATH = (
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_"
    "v0.1.0-draft.rule-bundle.json"
)
_APPROVAL_DOCUMENT_PATH = (
    "产业卡点及事件驱动系统/03_规则与规格/"
    "Stage5_5D公司行动估值P&L完整回放与原子持久化批准记录_v0.1.md"
)


class Stage5DApprovalCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 5D approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _hash_value(value: Any, *, field_name: str) -> str:
    item = _mapping(value, field_name=field_name)
    if set(item) != {"algorithm", "value"} or item.get("algorithm") != "sha256":
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an exact SHA-256 identity",
        )
    digest = item.get("value")
    if not isinstance(digest, str) or len(digest) != 64:
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVED_CONTRACT_INVALID",
            f"{field_name}.value must be a 64-character digest",
        )
    return digest


def _require_exact_authority(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="authorization_boundary")
    expected = {
        "approval_scope": RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION.value,
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
        "authorizes_durable_persistence": False,
        "authorizes_kb_write": False,
        "authorizes_real_data": False,
        "authorizes_strategy_performance_claim": False,
        "authorizes_stage6": False,
        "authorizes_cross_strategy_ledger_or_pnl": False,
        "future_capability_may_not_be_inherited_from_stage2b_stage4_stage5b_or_stage5c": True,
    }
    if dict(boundary) != expected:
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_AUTHORIZATION_BOUNDARY_MISMATCH",
            "Stage 5D must remain anonymous synthetic research validation only",
        )


def _require_exact_batch_and_sequence(rules: Mapping[str, Any]) -> None:
    batch = _mapping(rules.get("batch"), field_name="batch")
    if (
        batch.get("stage") != "Stage 5"
        or batch.get("batch_id") != "5D"
        or batch.get("purpose") != "approved_rule_governance"
        or batch.get("owner_approval_required") is not True
        or batch.get("approval_items_required") != 48
        or batch.get("approved_items") != 48
        or batch.get("approved_machine_bundle_exists") is not True
        or batch.get("approval_record_exists") is not True
        or batch.get("governance_capability_verifier_exists") is not True
        or batch.get("business_rule_evaluator_exists") is not False
        or batch.get("persistence_exists") is not False
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_IMPLEMENTATION_BOUNDARY_MISMATCH",
            "approval lineage must not claim a Stage 5D evaluator or persistence",
        )

    sequence = _mapping(rules.get("implementation_sequence"), field_name="implementation_sequence")
    phase_5d1 = _mapping(sequence.get("5D-1"), field_name="implementation_sequence.5D-1")
    phase_5d2 = _mapping(sequence.get("5D-2"), field_name="implementation_sequence.5D-2")
    if (
        sequence.get("status") != "approved"
        or tuple(sequence.get("phase_order", ())) != ("5D-1", "5D-2")
        or phase_5d1.get("io_or_external_side_effects") is not False
        or phase_5d1.get("persists_state") is not False
        or phase_5d1.get("must_complete_before_5d_2") is not True
        or phase_5d2.get("requires_exact_accepted_5d_1_result") is not True
        or phase_5d2.get("may_not_recompute_or_backfill_5d_1_inside_sql_transaction") is not True
        or phase_5d2.get("currently_authorized") is not False
        or phase_5d2.get("currently_implemented") is not False
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_IMPLEMENTATION_SEQUENCE_MISMATCH",
            "5D-1 must remain pure and precede the separately gated 5D-2 phase",
        )

    modules = _mapping(rules.get("rule_modules"), field_name="rule_modules")
    if not modules or any(
        _mapping(module, field_name="rule_modules[]").get("status") != "approved"
        for module in modules.values()
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVED_MODULE_STATUS_MISMATCH",
            "all and only the exact approved Stage 5D rule modules are required",
        )


def _require_exact_approval_items(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_ITEMS_INVALID",
            "owner_approval_items must be an immutable sequence",
        )
    identities: list[str] = []
    for raw_item in raw_items:
        item = _mapping(raw_item, field_name="owner_approval_items[]")
        if set(item) != {
            "approval_item_id",
            "status",
            "decision_text_sha256",
            "rule_paths",
        }:
            raise Stage5DApprovalCompatibilityError(
                "STAGE5D_APPROVAL_ITEMS_INVALID",
                "each approved decision must keep its exact identity, text hash, and rule paths",
            )
        item_id = item.get("approval_item_id")
        decision_hash = item.get("decision_text_sha256")
        rule_paths = item.get("rule_paths")
        if (
            not isinstance(item_id, str)
            or item.get("status") != "approved"
            or not isinstance(decision_hash, str)
            or len(decision_hash) != 64
            or not isinstance(rule_paths, tuple)
            or not rule_paths
            or not all(isinstance(path, str) and path.startswith("/") for path in rule_paths)
        ):
            raise Stage5DApprovalCompatibilityError(
                "STAGE5D_APPROVAL_ITEMS_INVALID",
                "all and only the forty-eight complete owner decisions must be approved",
            )
        identities.append(item_id)
    if tuple(identities) != STAGE5_5D_OWNER_APPROVAL_ITEM_IDS or (
        canonical_sha256(raw_items) != STAGE5_5D_OWNER_APPROVAL_ITEMS_SHA256
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_ITEMS_INVALID",
            "the approved decisions differ from exact 5D-01 through 5D-48",
        )

    atomicity = _mapping(rules.get("owner_approval_atomicity"), field_name="atomicity")
    if (
        atomicity.get("authorization_predicate") != "all(5D-01..5D-48==approved)"
        or atomicity.get("all_48_required") is not True
        or atomicity.get("same_exact_bundle_document_and_approval_record_required") is not True
        or atomicity.get("partial_capability_forbidden") is not True
        or atomicity.get("partial_implementation_authority_forbidden") is not True
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_ATOMICITY_MISMATCH",
            "the forty-eight decisions may authorize only as one atomic set",
        )


def _require_exact_upstream(rules: Mapping[str, Any]) -> None:
    dependencies = _mapping(
        rules.get("exact_upstream_dependencies"),
        field_name="exact_upstream_dependencies",
    )
    stage5a = _mapping(dependencies.get("stage5a_rule_governance"), field_name="stage5a")
    expected_stage5a = {
        "batch_id": "5A",
        "bundle_id": STAGE5_5A_RULE_BUNDLE_ID,
        "bundle_version": STAGE5_5A_RULE_BUNDLE_VERSION,
        "bundle_hash": STAGE5_5A_RULE_BUNDLE_SHA256,
        "rules_hash": STAGE5_5A_RULES_SHA256,
        "approval_record_hash": STAGE5_5A_RULE_APPROVAL_RECORD_SHA256,
        "approval_id": STAGE5_5A_RULE_APPROVAL_ID,
        "specification_hash": STAGE5_5A_SPECIFICATION_SHA256,
        "approval_document_hash": STAGE5_5A_APPROVAL_DOCUMENT_SHA256,
    }
    for field_name in ("batch_id", "bundle_id", "bundle_version", "approval_id"):
        if stage5a.get(field_name) != expected_stage5a[field_name]:
            raise Stage5DApprovalCompatibilityError(
                "STAGE5D_STAGE5A_IDENTITY_MISMATCH",
                f"Stage 5A {field_name} differs from the approved dependency",
            )
    for field_name in (
        "bundle_hash",
        "rules_hash",
        "approval_record_hash",
        "specification_hash",
        "approval_document_hash",
    ):
        if (
            _hash_value(stage5a.get(field_name), field_name=field_name)
            != expected_stage5a[field_name]
        ):
            raise Stage5DApprovalCompatibilityError(
                "STAGE5D_STAGE5A_IDENTITY_MISMATCH",
                f"Stage 5A {field_name} differs from the approved dependency",
            )
    if (
        stage5a.get("existing_stage5a_artifact_bytes_must_remain_unchanged") is not True
        or stage5a.get("dependency_is_approved_rule_authority") is not True
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_STAGE5A_IDENTITY_MISMATCH",
            "Stage 5A lineage must remain immutable approved rule authority",
        )

    stage5c = _mapping(
        dependencies.get("stage5c_implementation_baseline"),
        field_name="stage5c_implementation_baseline",
    )
    if (
        stage5c.get("commit_algorithm") != "git-sha1"
        or stage5c.get("commit") != STAGE5_5D_STAGE5C_BASELINE_COMMIT
        or stage5c.get("commit_is_implementation_baseline_not_runtime_capability") is not True
        or stage5c.get("ledger_v2_changes_require_stage5c_schema_version_increment") is not True
        or stage5c.get("stage5a_through_stage5c_regression_must_be_rerun") is not True
        or stage5c.get("stage5d_must_not_backfill_or_overwrite_historical_stage5c_artifacts")
        is not True
        or dependencies.get("dependency_identity_drift") != "PRECHECK_BLOCKED"
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_STAGE5C_BASELINE_MISMATCH",
            "Stage 5D requires the exact accepted Stage 5C implementation baseline",
        )


def _require_exact_approval_lineage(rules: Mapping[str, Any]) -> None:
    source = _mapping(rules.get("approval_source_binding"), field_name="approval_source_binding")
    if (
        source.get("specification_path") != _SPECIFICATION_PATH
        or source.get("draft_proposal_path") != _DRAFT_BUNDLE_PATH
        or source.get("traceability_only") is not True
        or _hash_value(source.get("specification_hash"), field_name="specification_hash")
        != STAGE5_5D_SPECIFICATION_SHA256
        or _hash_value(source.get("draft_raw_hash"), field_name="draft_raw_hash")
        != STAGE5_5D_DRAFT_RULE_BUNDLE_RAW_SHA256
        or _hash_value(source.get("draft_bundle_hash"), field_name="draft_bundle_hash")
        != STAGE5_5D_DRAFT_RULE_BUNDLE_SHA256
        or _hash_value(source.get("draft_rules_hash"), field_name="draft_rules_hash")
        != STAGE5_5D_DRAFT_RULES_SHA256
        or _hash_value(
            source.get("draft_owner_approval_items_hash"),
            field_name="draft_owner_approval_items_hash",
        )
        != STAGE5_5D_DRAFT_OWNER_APPROVAL_ITEMS_SHA256
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_SOURCE_MISMATCH",
            "the approved bundle is not bound to the exact owner-reviewed draft",
        )

    document = _mapping(rules.get("document_binding"), field_name="document_binding")
    if (
        document.get("path") != _APPROVAL_DOCUMENT_PATH
        or document.get("traceability_only") is not True
        or _hash_value(document.get("hash"), field_name="document_binding.hash")
        != STAGE5_5D_APPROVAL_DOCUMENT_SHA256
        or rules.get("runtime_must_not_parse_markdown") is not True
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_DOCUMENT_MISMATCH",
            "the approved bundle is not bound to the exact owner approval document",
        )


def require_stage5d_rule_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact Stage 5D synthetic research-validation capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    expected_identity = (
        STAGE5_STRATEGY_ID,
        STAGE5_5D_RULE_BUNDLE_ID,
        STAGE5_5D_RULE_BUNDLE_VERSION,
    )
    if (document.strategy_id, document.bundle_id, document.bundle_version) != expected_identity:
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_RULE_IDENTITY_UNSUPPORTED",
            "only the exact owner-approved Stage 5D bundle may issue capability",
        )
    _require_exact_authority(document.rules)
    _require_exact_batch_and_sequence(document.rules)
    _require_exact_approval_items(document.rules)
    _require_exact_upstream(document.rules)
    _require_exact_approval_lineage(document.rules)
    if canonical_sha256(document.rules) != STAGE5_5D_RULES_SHA256 or (
        document.bundle_hash().value != STAGE5_5D_RULE_BUNDLE_SHA256
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_RULE_HASH_UNSUPPORTED",
            "the Stage 5D machine semantics differ from the owner-approved version",
        )
    capability = registry.require(document)
    if capability.approval_scope is not STAGE5_5D_APPROVAL_SCOPE:
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 5D",
        )
    if capability.approval_id != STAGE5_5D_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE5_5D_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage5DApprovalCompatibilityError(
            "STAGE5D_APPROVAL_RECORD_UNSUPPORTED",
            "the capability requires the exact Stage 5D owner approval record",
        )
    return capability
