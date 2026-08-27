from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256

BASE_PRD_PATH = Path("产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.3.md")
DRAFT_DOCUMENT_PATH = Path(
    "产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订补充.md"
)
DRAFT_MACHINE_PATH = Path(
    "docs/validation/machine/industrial-event-prd-v0.4-boundary-addendum-draft.json"
)
APPROVAL_DOCUMENT_PATH = Path(
    "产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订批准记录.md"
)
APPROVAL_MACHINE_PATH = Path(
    "docs/validation/machine/industrial-event-prd-v0.4-boundary-addendum-approval.json"
)

BASE_PRD_RAW_SHA256 = "0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03"
DRAFT_DOCUMENT_RAW_SHA256 = "3587f49786cd3425f5a9dc5dd9df1af364963a7369cb38b8c40511ce00501d36"
DRAFT_MACHINE_RAW_SHA256 = "f6dcef60682a2eaf7824fc9039e048e5f1730c0ffd27db55ebaf3a72fc77b79b"
DRAFT_ADDENDUM_HASH = "da32630be2b2ca9d44a68b7dba5a23fcc92ed4223adc00b7e448e7f541a092c4"
DRAFT_ITEMS_HASH = "72d79dd91c26129b1acdfa74371373522e164351833645b499e93b8995b46f03"
APPROVAL_DOCUMENT_RAW_SHA256 = "ec575435f91e56c271d38f1cf0219537633504faaae1a6ac55f0aee390ef93fa"
APPROVAL_MACHINE_RAW_SHA256 = "697736a5a50f9efc64b2961947d0d50f2845b774a974685e4cb9bd0abe1cc234"
APPROVAL_RECORD_HASH = "f2afa2d4199fd80e81906242a2a021b1f3e2fdb04186419551421ef8bd7c0465"
APPROVED_DECISIONS_HASH = "497e915cb09330fbb1fa7dd5a1c25a1b33e115239020bc7c709d2def9003f1fa"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_approval_preserves_exact_base_and_pending_draft_bytes(repository_root: Path) -> None:
    assert sha256((repository_root / BASE_PRD_PATH).read_bytes()).hexdigest() == (
        BASE_PRD_RAW_SHA256
    )
    assert sha256((repository_root / DRAFT_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        DRAFT_DOCUMENT_RAW_SHA256
    )
    assert sha256((repository_root / DRAFT_MACHINE_PATH).read_bytes()).hexdigest() == (
        DRAFT_MACHINE_RAW_SHA256
    )
    draft = _json(repository_root / DRAFT_MACHINE_PATH)
    assert draft["addendum_hash"] == DRAFT_ADDENDUM_HASH
    assert {item["status"] for item in draft["owner_confirmation_items"]} == {"pending"}


def test_approval_document_and_machine_record_have_exact_identity(
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


def test_owner_conditional_risk_authority_is_explicit_and_satisfied(
    repository_root: Path,
) -> None:
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)

    assert approval["owner_source"]["text"] == "如果没有特别值得我注意的风险就批准"
    assert approval["approved_by"] == "repository_owner_via_conditional_risk_delegation"
    assert approval["risk_assessment"] == {
        "blocking_p0_or_p1_found": False,
        "base_prd_bytes_preserved": True,
        "legacy_compatibility_preserved": True,
        "strategy_or_numeric_rules_changed": False,
        "data_runtime_or_trading_authority_added": False,
        "condition_satisfied": True,
    }


def test_all_eight_decisions_are_atomically_approved_without_drift(
    repository_root: Path,
) -> None:
    draft = _json(repository_root / DRAFT_MACHINE_PATH)
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)
    pending = draft["owner_confirmation_items"]
    approved = approval["approved_decisions"]

    assert [item["id"] for item in approved] == [
        f"PRD04-BND-{number:02d}" for number in range(1, 9)
    ]
    assert {item["status"] for item in approved} == {"approved"}
    assert [item["decision"] for item in approved] == [item["decision"] for item in pending]
    assert canonical_sha256(pending) == DRAFT_ITEMS_HASH
    assert canonical_sha256(approved) == APPROVED_DECISIONS_HASH
    assert approval["approved_decisions_sha256"] == APPROVED_DECISIONS_HASH
    assert approval["approved_atomically"] is True


def test_effective_prd_is_v03_plus_narrow_v04_addendum(repository_root: Path) -> None:
    effective = _json(repository_root / APPROVAL_MACHINE_PATH)["effective_prd"]

    assert effective == {
        "base": "PRD_V0_3",
        "boundary_addendum": "PRD_V0_4_BOUNDARY_ADDENDUM",
        "addendum_precedence_only_for_listed_conflicts": True,
        "unlisted_v0_3_requirements_remain_effective": True,
    }


def test_approval_grants_no_refactor_data_runtime_or_trading_authority(
    repository_root: Path,
) -> None:
    approval = _json(repository_root / APPROVAL_MACHINE_PATH)

    assert all(value is False for value in approval["authorization_boundary"].values())
    assert approval["next_gate"] == (
        "WAIT_FOR_KB_DATA_SOURCE_LICENSE_PIT_AUDIT_AND_SEPARATE_OWNER_AUTHORIZATION"
    )
