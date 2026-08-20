from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import rule_bundle_document_from_json_value
from invest_system.models import RuleStatus

SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md"
)
DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
    "v0.2.0-draft.rule-bundle.json"
)

SPECIFICATION_SHA256 = "3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368"
DRAFT_RAW_SHA256 = "6f2663feb8b8cef5fd969d2791d2505b82e31ff42071872df0350c2196007afd"
DRAFT_BUNDLE_SHA256 = "a45396cde1e23ab6c05ea03111cf9f72044031a57d6a91dce554e15d6979a72c"
DRAFT_RULES_SHA256 = "c64f2b6057355c5e0bca9d597c01ed9f39ae0fd483ee469de86f7c964d8879c8"
OWNER_ITEMS_SHA256 = "7e3eee1c02a8d16e27ec3180379d221302ff3ca1741bb43300f145063f910bd6"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resolve_json_pointer(root: dict[str, Any], pointer: str) -> Any:
    assert pointer.startswith("/")
    current: Any = root
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict)
        assert token in current
        current = current[token]
    return current


def _decision_ids(specification: str) -> tuple[str, ...]:
    section = specification.split("## 6. v0.2 完整 Owner 批准清单", 1)[1].split(
        "## 7. 批准后的唯一顺序", 1
    )[0]
    return tuple(
        match.group(1)
        for line in section.splitlines()
        if (match := re.fullmatch(r"- \[ \] `(6C-\d{2})`：.+", line)) is not None
    )


def test_stage6c_v02_draft_has_strict_identity_and_supersedes_exact_v01(
    repository_root: Path,
) -> None:
    draft_path = repository_root / DRAFT_BUNDLE_PATH
    raw = _json(draft_path)
    document = rule_bundle_document_from_json_value(raw)

    assert sha256(draft_path.read_bytes()).hexdigest() == DRAFT_RAW_SHA256
    assert document.to_json_value() == raw
    assert document.schema_version == "0.1.0-draft"
    assert document.bundle_version == "0.2.0-draft"
    assert document.declared_status is RuleStatus.DRAFT
    assert document.bundle_hash().value == DRAFT_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == DRAFT_RULES_SHA256
    assert sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest() == (
        SPECIFICATION_SHA256
    )
    assert raw["rules"]["document_binding"]["hash"]["value"] == SPECIFICATION_SHA256

    base = raw["rules"]["supersession_and_base_binding"]
    base_spec = repository_root / base["supersedes_specification"]["path"]
    base_draft = repository_root / base["supersedes_draft_machine_proposal"]["path"]
    base_acceptance = repository_root / base["v0_1_draft_acceptance"]["path"]
    assert (
        sha256(base_spec.read_bytes()).hexdigest() == (base["supersedes_specification"]["sha256"])
    )
    assert (
        sha256(base_draft.read_bytes()).hexdigest()
        == (base["supersedes_draft_machine_proposal"]["raw_sha256"])
    )
    assert (
        sha256(base_acceptance.read_bytes()).hexdigest()
        == (base["v0_1_draft_acceptance"]["sha256"])
    )
    assert base["future_approved_bundle_must_materialize_complete_rules"] is True
    assert base["runtime_delta_or_markdown_merge_forbidden"] is True
    assert raw["rules"]["exact_upstream_dependencies"]["plan_at_revision_formation"] == {
        "path": "PLAN.md",
        "version": "3.12",
        "sha256": "dfd09b833bcd2eecf89eb93c5d02558a86f6ba56f8e38c7e675172c0f399775d",
    }
    assert (
        raw["rules"]["effective_rule_materialization"][
            "future_approved_bundle_contains_no_delta_reference"
        ]
        is True
    )


def test_stage6c_v02_all_40_items_pending_atomic_resolvable_and_zero_authority(
    repository_root: Path,
) -> None:
    raw = _json(repository_root / DRAFT_BUNDLE_PATH)
    rules = raw["rules"]
    boundary = rules["authorization_boundary"]
    items = rules["owner_approval_items"]
    expected_ids = tuple(f"6C-{number:02d}" for number in range(1, 41))

    assert tuple(item["approval_item_id"] for item in items) == expected_ids
    assert {item["status"] for item in items} == {"pending"}
    assert canonical_sha256(items) == OWNER_ITEMS_SHA256
    for item in items:
        for pointer in item["rule_paths"]:
            _resolve_json_pointer(rules, pointer)
    specification = (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8")
    assert _decision_ids(specification) == expected_ids
    assert re.search(r"^- \[[xX]\] `6C-", specification, flags=re.MULTILINE) is None

    assert boundary["allowed_run_modes"] == []
    assert boundary["runtime_capability_issued"] is False
    assert boundary["authority_eligible"] is False
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert rules["batch"]["approved_items"] == 0
    assert rules["batch"]["runtime_code_exists"] is False
    assert rules["batch"]["holdout_has_been_opened"] is False
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry().require(rule_bundle_document_from_json_value(raw))


def test_stage6c_v02_holdout_is_technically_inaccessible_to_6c(
    repository_root: Path,
) -> None:
    holdout = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["holdout_technical_isolation"]
    projection = holdout["development_projection"]
    commitment = holdout["holdout_commitment"]
    access = holdout["access_control"]

    assert projection["decision_time_strictly_before"] == "2025-12-31T16:00:00.000000Z"
    assert projection["contains_holdout_records"] is False
    assert (
        projection["contains_holdout_count_summary_schema_cardinality_or_performance_proxy"]
        is False
    )
    assert commitment["allows_6c_artifact_read"] is False
    assert (
        commitment[
            "record_count_candidate_ids_returns_status_distribution_coverage_or_size_forbidden"
        ]
        is True
    )
    assert (
        access["six_c_process_user_container_workdir_cache_and_token_have_no_read_access"] is True
    )
    assert access["holdout_mount_copy_symlink_or_junction_into_6c_forbidden"] is True
    assert access["mixed_pre_2026_and_holdout_artifact_requires_custodian_projection"] is True
    assert access["non_sensitive_holdout_canary_read_must_be_denied"] is True
    assert access["holdout_audit_read_count"] == 0
    assert access["any_failure_evaluator_calls"] == 0
    assert holdout["evidence_label"] == ("LOCKED_HISTORICAL_HOLDOUT_NOT_STRICTLY_UNKNOWN_SAMPLE")


def test_stage6c_v02_adjusted_and_cluster_sensitive_inference_is_one_gate(
    repository_root: Path,
) -> None:
    gate = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["adjusted_inference_entry_gate"]

    assert gate["comparisons_requiring_three_inference_paths"] == [
        "full_vs_market_or_industry_matched",
        "full_vs_frozen_best_simple",
    ]
    assert gate["required_inference_paths"] == [
        "calendar_block_portfolio",
        "company_cluster_sensitivity",
        "risk_cluster_sensitivity",
    ]
    assert gate["each_path_two_sided_95_ci_lower_gt"] == "0"
    assert len(gate["confirmatory_family"]) == 5
    assert gate["every_adjusted_p_value_lte"] == "0.05"
    assert gate["raw_ci_without_adjusted_and_sensitivity_pass_cannot_enter_6d"] is True
    assert gate["required_inference_trail"] == [
        "raw_ci",
        "raw_p_value",
        "holm_sort_order",
        "holm_threshold",
        "adjusted_p_value",
        "reject_or_not_reject",
    ]


def test_stage6c_v02_bootstrap_uses_canonical_portfolio_fact_without_row_summing(
    repository_root: Path,
) -> None:
    bootstrap = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["portfolio_fact_and_bootstrap"]
    fact = bootstrap["canonical_source_driven_portfolio_fact"]
    primary = bootstrap["primary_calendar_block_bootstrap"]

    assert fact["recompute_from_raw_candidates_rules_execution_risk_ledger_and_marks"] is True
    assert fact["caller_supplied_return_nav_contribution_or_pass_trusted"] is False
    assert fact["external_flow_required"] == "0"
    assert primary["input"] == "canonical_daily_excess_return"
    assert primary["preserve_within_block_order"] is True
    assert (
        primary["concatenate_until_original_session_count_and_deterministically_truncate_last"]
        is True
    )
    assert primary["opportunity_contributions_resampled_or_summed_as_portfolio_nav"] is False
    assert primary["creates_new_ledger_or_historical_fact"] is False
    assert primary["resamples"] == 10000
    assert primary["seed"] == 20260820
    company = bootstrap["company_cluster_sensitivity"]
    risk = bootstrap["risk_cluster_sensitivity"]
    assert company["paired_delta_rate"] == (
        "(full_net_contribution_i-comparator_net_contribution_i)/fold_beginning_nav"
    )
    assert company["non_trading_model_contribution"] == "0_candidate_retained"
    assert company["residual"] == "paired_delta_rate_i-mean_paired_delta_rate"
    assert company["ci"] == "two_sided_percentile_95"
    assert company["seed"] == 20260821
    assert risk["paired_delta_rate"] == company["paired_delta_rate"]
    assert risk["draw"] == company["draw"]
    assert risk["seed"] == 20260822


def test_stage6c_v02_coverage_requires_outcome_blind_selection_balance(
    repository_root: Path,
) -> None:
    audit = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["coverage_selection_audit"]

    assert audit["frozen_before_any_return_label_or_performance_summary_read"] is True
    assert audit["support_flag_outcome_blind"] is True
    assert audit["inherited_quantity_gates"] == {
        "aggregate_coverage_gte": "0.80",
        "each_walk_forward_year_coverage_gte": "0.70",
    }
    assert set(audit["continuous_absolute_standardized_mean_difference_lte"].values()) == {"0.10"}
    assert audit["categorical_material_category_absolute_proportion_difference_lte"] == "0.10"
    assert audit["material_category"] == {
        "population_share_gte": "0.05",
        "candidate_count_gte": 15,
    }
    assert audit["each_material_category_coverage_gte"] == "0.60"
    assert audit["unsupported_count_lt_15"] == ("MANDATORY_CAVEAT_NOT_PROOF_OF_NO_SELECTION_BIAS")
    assert audit["failure_result"] == "INSUFFICIENT_EVIDENCE"
    assert audit["audit_cannot_prove_unobserved_missingness_absent"] is True


def test_stage6c_v02_primary_estimator_and_benchmark_formula_are_exact(
    repository_root: Path,
) -> None:
    estimator = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"][
        "exact_primary_estimator_and_benchmark"
    ]

    assert estimator["external_cash_flow"] == "0"
    assert estimator["daily_strategy_return"] == "NAV_t/NAV_t_minus_1-1"
    assert estimator["daily_benchmark_return"] == ("benchmark_NAV_t/benchmark_NAV_t_minus_1-1")
    assert estimator["daily_excess_factor"] == ("(1+strategy_return_t)/(1+benchmark_return_t)")
    assert estimator["annualized_net_excess_percentage_points"] == (
        "(gross_excess_factor**(252/N)-1)*100"
    )
    assert estimator["annualization_sessions"] == 252
    assert estimator["minimum_fold_sessions_for_confirmatory_entry"] == 126
    assert estimator["cash_only_days_retained"] is True
    assert estimator["full_precision_determines_gates"] is True
    benchmark = estimator["benchmark_nav"]
    assert benchmark["same_entry_time_cash_occupancy_risk_budget_and_exit_clock"] is True
    assert benchmark["same_fee_tax_slippage_impact_capacity_and_unexecutable_constraints"] is True
    assert benchmark["benchmark_security_stage5d_support_required"] is True
    assert benchmark["unsupported_benchmark_candidate_remains_in_coverage_denominator"] is True
    assert benchmark["frictionless_index_substitution_forbidden"] is True
