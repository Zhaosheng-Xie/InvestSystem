"""Draft-only governance for Stage 4 / 4A-2 event semantics.

The checked-in 4A-2 bundle is an owner-review proposal, not executable strategy
authority.  This module pins its exact identity and verifies that every runtime
and trading capability remains closed.  It deliberately exposes no event
evaluator and cannot issue an :class:`ApprovedRuleCapability`.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from invest_system.canonical import canonical_sha256, freeze_json
from invest_system.domain.rule_approval import RuleApprovalScope, RuleBundleDocument
from invest_system.models import CanonicalModel, HashDigest, RuleStatus

STAGE4_4A2_DRAFT_RULE_BUNDLE_ID = "industrial_event_stage4_4a2_event_semantics"
STAGE4_4A2_DRAFT_RULE_BUNDLE_VERSION = "0.1.0-draft"
STAGE4_4A2_DRAFT_RULE_BUNDLE_SHA256 = (
    "972a30f88d33e46fe85ad63a88b4e4cf145a95c98a5d2a0d67c741394f5b5f41"
)
STAGE4_4A2_DRAFT_RULES_SHA256 = "cb883d48e7caaa5bf8f70534f1d61c314bd6e605e1bae3dc7fd6e3f09be0680e"
STAGE4_4A2_DRAFT_SPECIFICATION_SHA256 = (
    "673e7b65425cfda19561b3e3ac97ffd624e9d9770fa2d8dc80f458a4fd23468f"
)
STAGE4_4A2_DRAFT_SPECIFICATION_PATH = (
    "产业卡点及事件驱动系统/03_规则与规格/Stage4_4A2事件状态与审计分层规则包_v0.1.md"
)
STAGE4_4A2_REQUIREMENT_IDS = (
    "FR-EVT-001",
    "FR-EVT-002",
    "FR-EVT-003",
    "FR-EVT-004",
)
STAGE4_4A2_OWNER_APPROVAL_ITEM_IDS = tuple(f"4A2-APPROVAL-{index:03d}" for index in range(1, 17))

_RULE_KEYS = frozenset(
    {
        "authorization_boundary",
        "batch",
        "shared_semantics",
        "rule_modules",
        "owner_approval_items",
        "document_binding",
        "runtime_must_not_parse_markdown",
    }
)
_MODULE_KEYS = frozenset({"requirement_id", "proposal_rule_ref", "status", "semantics"})
_APPROVAL_ITEM_KEYS = frozenset({"approval_item_id", "status"})


class Stage4EventRuleProposalError(ValueError):
    """Stable fail-closed rejection for a 4A-2 draft proposal."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


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
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_STRUCTURE_DRIFT",
            f"{field_name} fields differ; missing={missing}, extra={extra}",
        )
    return value


@dataclass(frozen=True, slots=True)
class Stage4EventRuleProposal(CanonicalModel):
    """Verified identity of the non-executable 4A-2 owner-review proposal."""

    bundle_hash: HashDigest
    rules_hash: HashDigest
    specification_hash: HashDigest
    requirement_ids: tuple[str, ...] = field(default=STAGE4_4A2_REQUIREMENT_IDS, init=False)
    pending_owner_approval_item_ids: tuple[str, ...] = field(
        default=STAGE4_4A2_OWNER_APPROVAL_ITEM_IDS,
        init=False,
    )
    proposed_approval_scope: RuleApprovalScope = field(
        default=RuleApprovalScope.STAGE4_SYNTHETIC_RESEARCH_VALIDATION,
        init=False,
    )
    declared_status: RuleStatus = field(default=RuleStatus.DRAFT, init=False)
    allowed_run_modes: tuple[str, ...] = field(default=(), init=False)
    runtime_capability_issued: bool = field(default=False, init=False)
    full_stage4_capability: bool = field(default=False, init=False)
    authorizes_backtest: bool = field(default=False, init=False)
    authorizes_paper: bool = field(default=False, init=False)
    authorizes_shadow: bool = field(default=False, init=False)
    authorizes_live: bool = field(default=False, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        for field_name in ("bundle_hash", "rules_hash", "specification_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")


def stage4_event_rule_proposal_from_document(
    document: RuleBundleDocument,
) -> Stage4EventRuleProposal:
    """Verify the exact draft proposal without granting runtime authority."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    expected_identity = (
        "industrial_bottleneck_event",
        STAGE4_4A2_DRAFT_RULE_BUNDLE_ID,
        STAGE4_4A2_DRAFT_RULE_BUNDLE_VERSION,
    )
    if (document.strategy_id, document.bundle_id, document.bundle_version) != expected_identity:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_IDENTITY_UNSUPPORTED",
            "the document is not the pinned 4A-2 owner-review proposal",
        )
    if document.declared_status is not RuleStatus.DRAFT:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_STATUS_UNSUPPORTED",
            "4A-2 remains draft until all owner decisions are explicitly approved",
        )
    if document.bundle_hash().value != STAGE4_4A2_DRAFT_RULE_BUNDLE_SHA256:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_BUNDLE_HASH_DRIFT",
            "the complete draft bundle differs from the reviewed proposal",
        )
    if canonical_sha256(document.rules) != STAGE4_4A2_DRAFT_RULES_SHA256:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_RULES_HASH_DRIFT",
            "the draft machine semantics differ from the pinned proposal",
        )

    rules = _strict_mapping(document.rules, keys=_RULE_KEYS, field_name="4A-2 rules")
    expected_boundary = freeze_json(
        {
            "proposed_approval_scope": "stage4_synthetic_research_validation",
            "allowed_run_modes": [],
            "specification_validation_only": True,
            "runtime_capability_issued": False,
            "full_stage4_capability": False,
            "authorizes_backtest": False,
            "authorizes_paper": False,
            "authorizes_shadow": False,
            "authorizes_live": False,
            "authorizes_positions": False,
            "authorizes_orders": False,
        }
    )
    if rules["authorization_boundary"] != expected_boundary:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_AUTHORITY_DRIFT",
            "a draft proposal must have zero runtime and trading authority",
        )

    expected_batch = freeze_json(
        {
            "batch_id": "4A-2",
            "requirement_ids": list(STAGE4_4A2_REQUIREMENT_IDS),
            "owner_approval_required": True,
            "approval_items_required": 16,
            "approved_items": 0,
        }
    )
    if rules["batch"] != expected_batch:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_APPROVAL_STATE_DRIFT",
            "the proposal must retain all sixteen pending owner decisions",
        )

    modules = rules["rule_modules"]
    if not isinstance(modules, Mapping) or set(modules) != set(STAGE4_4A2_REQUIREMENT_IDS):
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_RULE_SET_DRIFT",
            "the proposal must contain exactly FR-EVT-001 through FR-EVT-004",
        )
    for requirement_id in STAGE4_4A2_REQUIREMENT_IDS:
        module = _strict_mapping(
            modules[requirement_id],
            keys=_MODULE_KEYS,
            field_name=f"4A-2 module {requirement_id}",
        )
        if module["requirement_id"] != requirement_id or module["status"] != "draft":
            raise Stage4EventRuleProposalError(
                "STAGE4_4A2_DRAFT_MODULE_STATUS_DRIFT",
                f"{requirement_id} must remain an identity-bound draft",
            )
        if not isinstance(module["semantics"], Mapping) or not module["semantics"]:
            raise Stage4EventRuleProposalError(
                "STAGE4_4A2_DRAFT_MODULE_EMPTY",
                f"{requirement_id} must contain reviewable proposed semantics",
            )

    raw_approval_items = rules["owner_approval_items"]
    if not isinstance(raw_approval_items, tuple) or len(raw_approval_items) != 16:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_APPROVAL_ITEMS_DRIFT",
            "the proposal must contain exactly sixteen pending approval items",
        )
    actual_approval_ids: list[str] = []
    for index, raw_item in enumerate(raw_approval_items):
        item = _strict_mapping(
            raw_item,
            keys=_APPROVAL_ITEM_KEYS,
            field_name=f"4A-2 owner approval item {index}",
        )
        if item["status"] != "pending":
            raise Stage4EventRuleProposalError(
                "STAGE4_4A2_DRAFT_APPROVAL_ITEM_PREAPPROVED",
                "a draft artifact cannot record owner approval",
            )
        approval_id = item["approval_item_id"]
        if not isinstance(approval_id, str):
            raise TypeError("approval_item_id must be a string")
        actual_approval_ids.append(approval_id)
    if tuple(actual_approval_ids) != STAGE4_4A2_OWNER_APPROVAL_ITEM_IDS:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_APPROVAL_ITEMS_DRIFT",
            "owner approval item identities or ordering differ",
        )

    expected_binding = freeze_json(
        {
            "path": STAGE4_4A2_DRAFT_SPECIFICATION_PATH,
            "hash": {
                "algorithm": "sha256",
                "value": STAGE4_4A2_DRAFT_SPECIFICATION_SHA256,
            },
            "traceability_only": True,
        }
    )
    if rules["document_binding"] != expected_binding:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_SPECIFICATION_BINDING_DRIFT",
            "the machine proposal does not bind the exact owner-review document",
        )
    if rules["runtime_must_not_parse_markdown"] is not True:
        raise Stage4EventRuleProposalError(
            "STAGE4_4A2_DRAFT_MARKDOWN_RUNTIME_BOUNDARY_DRIFT",
            "runtime code must never parse Markdown as strategy semantics",
        )

    return Stage4EventRuleProposal(
        bundle_hash=document.bundle_hash(),
        rules_hash=HashDigest(algorithm="sha256", value=STAGE4_4A2_DRAFT_RULES_SHA256),
        specification_hash=HashDigest(
            algorithm="sha256",
            value=STAGE4_4A2_DRAFT_SPECIFICATION_SHA256,
        ),
    )
