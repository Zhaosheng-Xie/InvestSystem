from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256

PRD_V03_PATH = Path("产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.3.md")
ADDENDUM_PATH = Path(
    "产业卡点及事件驱动系统/01_需求/产业卡点及事件驱动系统_PRD_v0.4边界修订补充.md"
)
MACHINE_PATH = Path(
    "docs/validation/machine/industrial-event-prd-v0.4-boundary-addendum-draft.json"
)

PRD_V03_RAW_SHA256 = "0f7e6489ee0c5c17d638534337a73c389e70794cf41b821eec7cc92a242c6b03"
ADDENDUM_RAW_SHA256 = "3587f49786cd3425f5a9dc5dd9df1af364963a7369cb38b8c40511ce00501d36"
MACHINE_RAW_SHA256 = "f6dcef60682a2eaf7824fc9039e048e5f1730c0ffd27db55ebaf3a72fc77b79b"
ADDENDUM_HASH = "da32630be2b2ca9d44a68b7dba5a23fcc92ed4223adc00b7e448e7f541a092c4"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_v03_and_v04_draft_have_exact_immutable_identity(repository_root: Path) -> None:
    assert sha256((repository_root / PRD_V03_PATH).read_bytes()).hexdigest() == (PRD_V03_RAW_SHA256)
    assert sha256((repository_root / ADDENDUM_PATH).read_bytes()).hexdigest() == (
        ADDENDUM_RAW_SHA256
    )
    assert sha256((repository_root / MACHINE_PATH).read_bytes()).hexdigest() == (MACHINE_RAW_SHA256)
    machine = _json(repository_root / MACHINE_PATH)
    assert machine["addendum_hash"] == ADDENDUM_HASH
    assert (
        canonical_sha256({key: value for key, value in machine.items() if key != "addendum_hash"})
        == ADDENDUM_HASH
    )
    assert machine["base_prd"]["bytes_unchanged"] is True


def test_addendum_is_narrow_and_does_not_rewrite_unlisted_v03_requirements(
    repository_root: Path,
) -> None:
    machine = _json(repository_root / MACHINE_PATH)
    scope = machine["supersession_scope"]

    assert scope == {
        "mode": "BOUNDARY_CLAUSE_ADDENDUM_ONLY",
        "full_prd_rewrite": False,
        "unlisted_v0_3_requirements_remain_effective": True,
        "listed_boundary_conflicts_use_v0_4_after_approval": True,
    }
    assert [item["replacement_id"] for item in machine["effective_replacements"]] == [
        "PRD-V04-R01",
        "PRD-V04-R02",
        "PRD-V04-R03",
        "PRD-V04-R04",
    ]


def test_strategy_input_ref_ownership_and_construction_are_corrected(
    repository_root: Path,
) -> None:
    machine = _json(repository_root / MACHINE_PATH)
    ownership = machine["object_ownership"]
    construction = machine["strategy_input_ref_construction"]

    assert "release_reference" in ownership["kb"]
    assert "strategy_input_ref" in ownership["investsystem"]
    assert set(ownership["kb"]).isdisjoint(ownership["investsystem"])
    assert construction["source"] == "ONE_VERIFIED_ROOT_RELEASE_REFERENCE"
    assert construction["provider_preconstructed_reference_trusted"] is False
    assert construction["legacy_strategy_input_ref_v1"] == "READ_ONLY_EQUALITY_CHECK_ONLY"
    assert construction["fields"] == {
        "schema_version": "IS_CONTRACT_VERSION",
        "dataset_release_id": "release_reference.release_id",
        "knowledge_cutoff": "release_reference.knowledge_cutoff",
        "release_manifest_schema_version": "release_reference.manifest_schema_version",
        "manifest_hash": "RECOMPUTED_AND_MATCHED_RELEASE_MANIFEST_HASH",
    }


def test_c1a_and_c1b_have_separate_completion_gates(repository_root: Path) -> None:
    stages = _json(repository_root / MACHINE_PATH)["stage_c1"]

    assert stages["c1a"]["status"] == "COMPLETED_WITH_SCOPE_LIMITS_AT_IS_4FC5597"
    assert stages["c1a"]["published_release_required"] is False
    assert stages["c1a"]["runtime_authority"] is False
    assert stages["c1b"]["status"] == "NOT_STARTED"
    assert set(stages["c1b"]["requires"]) == {
        "LEGAL_DATA_SOURCE",
        "HISTORICAL_PIT",
        "RAW_BASIS_RECORDS",
        "IMMUTABLE_RELEASE_CANDIDATE",
        "PRODUCER_VALIDATION",
        "SEPARATE_OWNER_AUTHORIZATION",
    }


def test_valid_v03_strategy_input_ref_semantics_remain_preserved(
    repository_root: Path,
) -> None:
    preserved = set(_json(repository_root / MACHINE_PATH)["preserved_v0_3_semantics"])

    assert preserved == {
        "STRATEGY_RUN_MANIFEST_STORES_STRATEGY_INPUT_REF",
        "RECEIPT_OBSERVATION_DECISION_AND_RETENTION_BIND_STRATEGY_INPUT_REF",
        "AVAILABLE_AT_LTE_KNOWLEDGE_CUTOFF_LTE_DECISION_AT",
        "EXACTLY_ONE_ROOT_STRATEGY_INPUT_REF_PER_RUN",
        "WITHDRAWN_OR_UNCONFIRMABLE_RELEASE_BLOCKS_NEW_RUN",
        "KB_CANDIDATE_EVENT_IS_NOT_IS_EVENT_OR_INVESTMENT_CANDIDATE",
    }


def test_all_eight_owner_items_are_pending_and_not_silently_approved(
    repository_root: Path,
) -> None:
    machine = _json(repository_root / MACHINE_PATH)
    expected_ids = [f"PRD04-BND-{number:02d}" for number in range(1, 9)]
    items = machine["owner_confirmation_items"]

    assert [item["id"] for item in items] == expected_ids
    assert {item["status"] for item in items} == {"pending"}
    assert machine["declared_status"] == "draft_for_owner_confirmation"
    document = (repository_root / ADDENDUM_PATH).read_text(encoding="utf-8")
    unchecked = re.findall(r"^- \[ \] `(PRD04-BND-\d{2})`：", document, flags=re.MULTILINE)
    assert unchecked == expected_ids
    assert re.search(r"^- \[[xX]\] `PRD04-BND-", document, flags=re.MULTILINE) is None


def test_draft_grants_no_refactor_data_runtime_or_trading_authority(
    repository_root: Path,
) -> None:
    machine = _json(repository_root / MACHINE_PATH)

    assert all(value is False for value in machine["observed_inputs"].values())
    assert all(value is False for value in machine["authorization_boundary"].values())
    assert machine["next_gate"] == "OWNER_ATOMICALLY_APPROVES_PRD04_BND_01_THROUGH_08"
    assert (
        "H00985_COMPLETE_HISTORY_PIT_AND_REDISTRIBUTION_PERMISSION" in (machine["current_blockers"])
    )
