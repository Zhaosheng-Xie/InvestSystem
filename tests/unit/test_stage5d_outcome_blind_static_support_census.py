from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.strategies.industrial_event.stage5d_bounded_replay import (
    Stage5DBoundedReplayStatus,
)
from invest_system.strategies.industrial_event.stage5d_ledger_v2 import (
    Stage5DV2EventType,
)
from invest_system.strategies.industrial_event.stage5d_stage5c_adapter import (
    Stage5DSourceDrivenSliceStatus,
)

CENSUS_PATH = Path("docs/validation/stage5d-outcome-blind-static-support-census-v0.1.md")
MACHINE_PATH = Path("docs/validation/machine/stage5d-outcome-blind-static-support-census-v0.1.json")
CENSUS_SHA256 = "546a7c49e840fa3fd4a6a00a043af4bde13e4ff44443aa511919b90f7eb9a8be"
MACHINE_SHA256 = "ce9321834d9a8ac3aee084351868998f03e1b1251f4c09608ce7bcaef86b7c8e"
EXPECTED_COUNTS = {
    "ACCEPTED_BOUNDED_SLICE": 6,
    "ACCEPTED_LEDGER_ONLY": 4,
    "FAILS_CLOSED": 4,
    "NOT_IMPLEMENTED": 4,
    "NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES": 2,
}


def _machine(repository_root: Path) -> dict[str, Any]:
    value = json.loads((repository_root / MACHINE_PATH).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_static_support_census_has_exact_document_and_machine_identity(
    repository_root: Path,
) -> None:
    census = repository_root / CENSUS_PATH
    machine = repository_root / MACHINE_PATH
    value = _machine(repository_root)

    assert sha256(census.read_bytes()).hexdigest() == CENSUS_SHA256
    assert sha256(machine.read_bytes()).hexdigest() == MACHINE_SHA256
    assert value["census_kind"] == "STATIC_CODE_SUPPORT_ONLY"
    assert value["baseline_commit"] == "8ea60895f7ebc42d5e58494711365f6305864889"
    assert value["document_binding"] == {
        "path": CENSUS_PATH.as_posix(),
        "sha256": CENSUS_SHA256,
    }
    assert value["overall_status"] == (
        "STATIC_CODE_SUPPORT_CENSUS_COMPLETE_REAL_CANDIDATE_COVERAGE_PENDING"
    )


def test_static_capability_matrix_is_closed_world_and_matches_markdown(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    items = value["capability_items"]
    expected_ids = [f"S5D-{number:02d}" for number in range(1, 21)]
    counts = Counter(item["status"] for item in items)
    markdown = (repository_root / CENSUS_PATH).read_text(encoding="utf-8")
    markdown_items = re.findall(
        r"^\| `(S5D-\d{2})` \| .+ \| `([A-Z_]+)` \|",
        markdown,
        flags=re.MULTILINE,
    )

    assert [item["id"] for item in items] == expected_ids
    assert counts == EXPECTED_COUNTS
    assert value["status_counts"] == {**EXPECTED_COUNTS, "total": 20}
    assert [item_id for item_id, _ in markdown_items] == expected_ids
    assert Counter(status for _, status in markdown_items) == EXPECTED_COUNTS


def test_every_static_support_claim_binds_existing_exact_evidence(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)

    for binding in value["evidence_bindings"]:
        path = repository_root / binding["path"]
        assert path.is_file()
        assert sha256(path.read_bytes()).hexdigest() == binding["sha256"]
        text = path.read_text(encoding="utf-8")
        assert all(symbol in text for symbol in binding["symbols"])

    event_types = {item.value for item in Stage5DV2EventType}
    assert {
        "BUY_TRADE",
        "SELL_TRADE",
        "BUY_CASH_SETTLEMENT",
        "SELL_CASH_SETTLEMENT",
        "SELL_CASH_AVAILABLE",
        "SECURITY_SETTLEMENT",
        "SECURITY_SELLABLE",
    } <= event_types
    assert Stage5DSourceDrivenSliceStatus.SELL_RECONCILED.value == "SELL_RECONCILED"
    assert Stage5DBoundedReplayStatus.PRECHECK_BLOCKED.value == "PRECHECK_BLOCKED"


def test_real_candidate_metrics_remain_unknown_not_zero_or_inferred(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    metrics = value["real_candidate_metrics"]

    assert metrics
    assert all(metric is None for metric in metrics.values())
    assert value["observed_inputs"] == {
        "candidate_inventory_read": False,
        "outcomes_read": False,
        "labels_read": False,
        "holdout_read": False,
        "network_accessed": False,
        "kb_internal_state_read": False,
        "persists_state": False,
    }
    not_evaluable = {
        item["capability"]
        for item in value["capability_items"]
        if item["status"] == "NOT_EVALUABLE_WITHOUT_HISTORICAL_CANDIDATES"
    }
    assert not_evaluable == {
        "real_candidate_total_and_annual_coverage",
        "real_completed_trade_count",
    }


def test_future_candidate_census_contract_is_outcome_blind_and_fail_closed(
    repository_root: Path,
) -> None:
    contract = _machine(repository_root)["future_candidate_census_contract"]

    assert contract["grain"] == (
        "candidate_id x economic_event_id x listed_company_id x decision_time"
    )
    assert contract["candidate_statuses"] == [
        "SUPPORTED",
        "UNSUPPORTED",
        "INDETERMINATE",
        "PRECHECK_BLOCKED",
    ]
    assert contract["summary_statuses"] == [
        "COVERAGE_READY",
        "INSUFFICIENT_EVIDENCE",
        "PRECHECK_BLOCKED",
    ]
    assert "OUTCOME_FIELD_PRESENT" in contract["precheck_reason_codes"]
    assert "HOLDOUT_CONTENT_PRESENT" in contract["precheck_reason_codes"]
    assert {
        "future_return",
        "nav",
        "pnl",
        "actual_exit_price",
        "completed_trade_flag",
        "holdout_payload",
    } <= set(contract["forbidden_outcome_fields"])
    assert contract["support_flags_freeze_before_outcomes"] is True
    assert contract["reject_abstain_blocked_no_fill_delisted_remain_in_denominator"] is True
    assert contract["indeterminate_counts_as_unsupported"] is True


def test_static_census_is_zero_authority_and_recommends_only_preregistration(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    text = (repository_root / MACHINE_PATH).read_text(encoding="utf-8").lower()

    assert value["authority_eligible"] is False
    assert all(flag is False for flag in value["authorizations"].values())
    assert value["decision"] == "PROCEED_WITH_MINIMAL_SELL_COMPLETE_REPLAY_PREREGISTRATION"
    assert value["recommended_next_slice"]["requires_preregistration"] is True
    assert "bearer" not in text
    assert "investmentresearchkb/tmp" not in text
    assert "investmentresearchkb\\tmp" not in text
