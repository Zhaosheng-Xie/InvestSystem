from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

DOCUMENT_PATH = Path(
    "docs/validation/stage6-minimum-public-data-consumption-contract-draft-v0.1.md"
)
MACHINE_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.1-draft.json"
)
DOCUMENT_SHA256 = "205a0c7d403d9fbadd988f2c3081882cb61594a5e4c36a6d4cc6db559e253182"
MACHINE_SHA256 = "65b9288b7bf2279b061174869181b6e92c85f76db567c6297ff67996e49a1359"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_stage6_minimum_data_contract_has_exact_draft_identity(repository_root: Path) -> None:
    document = repository_root / DOCUMENT_PATH
    machine = repository_root / MACHINE_PATH
    value = _json(machine)

    assert sha256(document.read_bytes()).hexdigest() == DOCUMENT_SHA256
    assert sha256(machine.read_bytes()).hexdigest() == MACHINE_SHA256
    assert value["schema_version"] == "1.0.0-draft"
    assert value["status"] == "DRAFT_FOR_OWNER_CONFIRMATION_ZERO_RUNTIME_AUTHORITY"
    assert value["baseline_commit"] == "7e294f2d48498d94c4c5063e23a144c606fe106f"
    assert value["document_binding"] == {
        "path": DOCUMENT_PATH.as_posix(),
        "sha256": DOCUMENT_SHA256,
    }


def test_contract_accepts_kb_not_ready_without_laundering_it_into_handoff(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    context = value["declared_kb_census_context"]

    assert context == {
        "branch": "codex/stage6-historical-census",
        "commit": "857c86787ed46d34e4f4f17eefa4bbde78089d15",
        "commit_pushed": False,
        "census_conclusion": "NOT_READY",
        "scope_eligible_release_count": 0,
        "scope_eligible_artifact_count": 0,
        "handoff_json_exists": False,
        "token_exists": False,
        "new_release_exists": False,
        "independently_verified_by_is": False,
    }
    assert value["observed_inputs"]
    assert all(item is False for item in value["observed_inputs"].values())
    assert all(item is False for item in value["authorization_boundary"].values())


def test_contract_requires_one_root_and_reduces_four_families_to_three(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    root = value["single_root_release"]
    families = value["recommended_source_families"]
    decision = value["release_architecture_decision"]

    assert root == {
        "required": True,
        "release_family": "historical-stage6-public-input-2019-2025.v1",
        "reason": "ADR-0001 permits exactly one strategy_input_ref per run",
        "source_family_count": 3,
    }
    assert [item["family"] for item in families] == [
        "historical-public-evidence-2019-2025.v1",
        "historical-security-market-reference-2019-2025.v1",
        "historical-public-financials-2019-2025.v1",
    ]
    assert decision["merge_common_reference_factors_into_market_reference"] == (
        "RECOMMENDED_PENDING_OWNER"
    )
    assert decision["multiple_strategy_input_refs_forbidden"] is True


def test_contract_p0_domains_universe_and_hard_delivery_gates_are_closed_world(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    domains = set(value["p0_required_domains"])
    universe = value["universe_recommendation"]
    hard = value["hard_data_delivery_gates"]

    assert {
        "public_evidence_and_historical_pit",
        "listing_delisting_st_code_change_history",
        "complete_exchange_calendar",
        "effective_dated_market_rule_sets",
        "security_session_states",
        "unadjusted_daily_marks_volume_turnover",
        "corporate_actions_and_total_return_basis",
        "pit_financial_statements_and_metrics",
        "pit_primary_industry",
        "pit_float_market_cap",
        "benchmark_daily_total_return_basis",
        "adv20_raw_basis_and_versioned_factor",
        "beta120_raw_basis_and_versioned_factor",
    } <= domains
    assert universe["exchanges"] == ["SSE", "SZSE"]
    assert universe["bse"] == "DEFERRED_PENDING_OWNER"
    assert universe["retain_st_star_st"] is True
    assert universe["retain_delisted_failed"] is True
    assert universe["strategy_ineligible_securities_remain_in_denominator"] is True
    assert hard["release_manifest_schema_dependency_identity"] == "100_PERCENT"
    assert hard["calendar_market_rule_session_intervals"] == "100_PERCENT"
    assert hard["security_entity_lifecycle_identified"] == "100_PERCENT"
    assert hard["survivor_only_forbidden"] is True


def test_adv20_and_beta120_are_versioned_generic_factors_with_raw_basis(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    adv = value["adv20_recommendation"]
    beta = value["beta120_recommendation"]

    assert adv["measure"] == "CNY_TURNOVER"
    assert adv["window"] == "PREVIOUS_EXACTLY_20_EXCHANGE_SESSIONS"
    assert adv["denominator_sessions"] == 20
    assert adv["proven_full_day_suspension_turnover"] == "ZERO_INCLUDED"
    assert adv["missing_or_unknown_state"] == "INCOMPLETE_NOT_ZERO"
    assert adv["basis_hashes_required"] is True
    assert beta["benchmark"] == "BROAD_MARKET_TOTAL_RETURN_ID_PENDING_OWNER"
    assert beta["window"] == "PREVIOUS_EXACTLY_120_EXCHANGE_SESSIONS"
    assert beta["estimator"] == "OLS_SLOPE_WITH_INTERCEPT"
    assert beta["return_basis"] == "PIT_ONE_SESSION_TOTAL_RETURN"
    assert beta["future_backward_adjustment_forbidden"] is True
    assert beta["short_listing_history"] == "INCOMPLETE_NO_SHORTENED_WINDOW"
    assert beta["paired_basis_hashes_required"] is True


def test_contract_preserves_approved_candidate_gates_without_counting_synthetic(
    repository_root: Path,
) -> None:
    gates = _json(repository_root / MACHINE_PATH)["later_is_candidate_gates"]

    assert gates == {
        "aggregate_support_minimum": "0.80",
        "annual_fold_support_minimum": "0.70",
        "material_category_support_minimum": "0.60",
        "selected_peer_count_minimum": 5,
        "target_and_all_selected_peers_must_be_supported": True,
        "real_completed_trades_minimum": 30,
        "real_completed_trades_per_fold_minimum": 5,
        "synthetic_completed_trades_count": 0,
    }


def test_schema_transport_and_repin_do_not_silently_expand_protocol(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    schemas = value["proposed_artifact_schemas"]
    transport = value["transport_version_recommendation"]
    repin = value["is_repin_gate_order"]

    assert len(schemas) == len(set(schemas)) == 11
    assert all(item.endswith("@1.0.0") for item in schemas)
    assert transport["existing_transport_source_commit"] == (
        "aab36fe229104779b50ec71e2dc37a9fad81d285"
    )
    assert (
        transport[
            "keep_existing_transport_protocol_v1_if_envelope_endpoints_headers_auth_unchanged"
        ]
        is True
    )
    assert transport["transport_v2_only_if_transport_semantics_change"] is True
    assert repin[-2:] == [
        "IS_REBUILDS_VENDOR_SNAPSHOT_AND_CATALOG_LOCK",
        "REAL_HTTPS_HANDOFF_ONLY_AFTER_REPIN",
    ]


def test_blockers_and_owner_decisions_are_ordered_pending_and_non_authoritative(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    blockers = value["blockers"]
    decisions = value["owner_decisions"]

    assert [item["priority"] for item in blockers] == list(range(1, 11))
    assert [item["id"] for item in blockers[:7]] == [
        "P0-ROOT-RELEASE",
        "P0-PIT-LINEAGE",
        "P0-MARK-STATE-RULE",
        "P0-SECURITY-LIFECYCLE",
        "P0-CORPORATE-ACTION",
        "P0-FINANCIAL-PIT",
        "P0-REFERENCE-FACTOR",
    ]
    assert [item["id"] for item in decisions] == [f"S6DATA-{number:02d}" for number in range(1, 11)]
    assert {item["status"] for item in decisions} == {"pending"}
    assert value["next_gate"] == (
        "OWNER_CONFIRMS_S6DATA_01_THROUGH_S6DATA_10_BEFORE_KB_BACKFILL_CONTRACT_FREEZE"
    )
