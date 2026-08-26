from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256

DRAFT_ADR_PATH = Path("docs/adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md")
DRAFT_DOCUMENT_PATH = Path(
    "docs/validation/stage6-historical-public-data-consumer-profile-v0.3-draft.md"
)
DRAFT_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-historical-public-data-consumer-profile-v0.3.0-draft.json"
)
APPROVAL_DOCUMENT_PATH = Path("docs/validation/stage6-provider-consumer-boundary-approval-v0.1.md")
APPROVAL_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-provider-consumer-boundary-approval-v0.1.json"
)

DRAFT_ADR_RAW_SHA256 = "e18e91423066589b636edd0ca793e6949f45dcf272ce0f81661aa33c3982f22e"
DRAFT_DOCUMENT_RAW_SHA256 = "79abfe814577dd2da644f5a59310021e6151e1c3a585cc6fa69aa69424e6bbad"
DRAFT_MACHINE_RAW_SHA256 = "2ea49cf7cd2cd100ecf6fde345b431a75a3f03c226d79fa4689cb0799fce8f6d"
DRAFT_PROFILE_HASH = "76c8d8eceab4c012dc957ac40edfd7d013a7d2a27a8b4edb997815ce81e3ebc0"
DRAFT_OWNER_ITEMS_HASH = "dd003f2688fa459bce537e7d1c560152494c7ffad120cdb383cc1e4f5e8d0a27"
APPROVAL_DOCUMENT_RAW_SHA256 = "85e837261b7d57b0c59e9683eced367c2ba55e50a7434c221efa8f5377606fcb"
APPROVAL_MACHINE_RAW_SHA256 = "83d8053fa5dc0593a4c5ab7205560512f89eb39a7dbd61eb4157badb0a0046af"
APPROVAL_RECORD_HASH = "28e856cbc38ec42d40176ca06c654c469249b023fbcd75d39db6c8c165075d56"
APPROVED_DECISIONS_HASH = "feb9235b1c1f1379de6d100fd7f8fc5292b4448a7b443709a7766728160c0b92"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_approval_binds_exact_unchanged_pending_drafts(repository_root: Path) -> None:
    assert sha256((repository_root / DRAFT_ADR_PATH).read_bytes()).hexdigest() == (
        DRAFT_ADR_RAW_SHA256
    )
    assert sha256((repository_root / DRAFT_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        DRAFT_DOCUMENT_RAW_SHA256
    )
    assert sha256((repository_root / DRAFT_MACHINE_PATH).read_bytes()).hexdigest() == (
        DRAFT_MACHINE_RAW_SHA256
    )
    draft = _json(repository_root / DRAFT_MACHINE_PATH)
    assert draft["profile_hash"] == DRAFT_PROFILE_HASH
    assert {item["status"] for item in draft["owner_confirmation_items"]} == {"pending"}


def test_approval_document_and_record_have_exact_content_identity(
    repository_root: Path,
) -> None:
    assert sha256((repository_root / APPROVAL_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        APPROVAL_DOCUMENT_RAW_SHA256
    )
    assert sha256((repository_root / APPROVAL_MACHINE_PATH).read_bytes()).hexdigest() == (
        APPROVAL_MACHINE_RAW_SHA256
    )
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)
    assert approval["approval_record_hash"] == APPROVAL_RECORD_HASH
    assert (
        canonical_sha256(
            {key: value for key, value in approval.items() if key != "approval_record_hash"}
        )
        == APPROVAL_RECORD_HASH
    )


def test_conditional_owner_authority_and_preconditions_are_explicit(
    repository_root: Path,
) -> None:
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)
    assert [source["text"] for source in approval["owner_sources"]] == [
        "这两份待批准的文件可能会有很大的风险吗？如果风险不大，就可以帮我看着批准。",
        "KB那边修复完了，IS这边继续",
    ]
    assert approval["approved_by"] == "repository_owner_via_conditional_delegation"
    preconditions = approval["preconditions"]
    assert preconditions["is_and_kb_architecture_audits_aligned"] is True
    assert preconditions["major_architecture_risk_found"] is False
    assert preconditions["kb_stage7_fix_main_commit"] == (
        "6ae6c4c3c8ec9433ff63fddcb2bbb207a39e8cbe"
    )
    assert preconditions["kb_post_merge_main_ci_all_green"] is True
    assert preconditions["is_draft_formation_commit"] == "29f83eb"


def test_all_ten_boundary_decisions_are_atomically_approved_without_drift(
    repository_root: Path,
) -> None:
    draft = _json(repository_root / DRAFT_MACHINE_PATH)
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)
    approved = approval["approved_decisions"]
    pending = draft["owner_confirmation_items"]

    assert [item["id"] for item in approved] == [f"S6BOUND-{number:02d}" for number in range(1, 11)]
    assert {item["status"] for item in approved} == {"approved"}
    assert [item["decision"] for item in approved] == [item["decision"] for item in pending]
    assert canonical_sha256(pending) == DRAFT_OWNER_ITEMS_HASH
    assert canonical_sha256(approved) == APPROVED_DECISIONS_HASH
    assert approval["approved_decisions_sha256"] == APPROVED_DECISIONS_HASH
    assert approval["approved_atomically"] is True


def test_approval_keeps_cross_repository_and_runtime_authority_closed(
    repository_root: Path,
) -> None:
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)
    counterpart = approval["kb_counterpart"]

    assert counterpart["same_decision_id_required"] is True
    assert counterpart["same_approved_decisions_sha256_required"] is True
    assert counterpart["kb_schema_implementation_approved_by_this_record"] is False
    assert counterpart["cross_repository_runtime_dependency_created"] is False
    assert all(value is False for value in approval["authorization_boundary"].values())
    assert approval["next_gate"] == (
        "KB_FORMS_GENERIC_DRAFT_SCHEMA_REGISTRY_CATALOG_FIXTURE_UNDER_ITS_OWN_GOVERNANCE"
    )
