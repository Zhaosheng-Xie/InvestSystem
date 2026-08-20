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
    "产业卡点及事件驱动系统/03_规则与规格/Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.1.md"
)
DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
    "v0.1.0-draft.rule-bundle.json"
)

SPECIFICATION_SHA256 = "bcf77c5608eb09fd3e591f0bd92a3e0e71a27c42c18123e26e98080db9609383"
DRAFT_RAW_SHA256 = "03e6717ab0de1b2c595e46b7a2a25c5cd3947ba9942a6e939f21636ce114e881"
DRAFT_BUNDLE_SHA256 = "6f3924d218fbb26f214e42f50776458784656a6104b7e3e6cf56aa812ce1eef9"
DRAFT_RULES_SHA256 = "e28982ac9989c7aee174581d181a44f339ae0fc696deac18b10c01501bff9086"
OWNER_ITEMS_SHA256 = "918df9a47b5041475d2a6b06347d864a61d2b256f60b5a56af3b8a16d5a7b0c2"


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
    section = specification.split("## 16. Owner 逐项批准清单", 1)[1].split(
        "## 17. 批准后的唯一实施顺序", 1
    )[0]
    return tuple(
        match.group(1)
        for line in section.splitlines()
        if (match := re.fullmatch(r"- \[ \] `(6C-\d{2})`：.+", line)) is not None
    )


def test_stage6c_draft_has_strict_identity_and_exact_source_bindings(
    repository_root: Path,
) -> None:
    draft_path = repository_root / DRAFT_BUNDLE_PATH
    raw = _json(draft_path)
    document = rule_bundle_document_from_json_value(raw)

    assert sha256(draft_path.read_bytes()).hexdigest() == DRAFT_RAW_SHA256
    assert document.to_json_value() == raw
    assert document.schema_version == "0.1.0-draft"
    assert document.strategy_id == "industrial_bottleneck_event"
    assert document.bundle_id == (
        "industrial_event_stage6_6c_development_walk_forward_champion_challenge"
    )
    assert document.bundle_version == "0.1.0-draft"
    assert document.declared_status is RuleStatus.DRAFT
    assert document.bundle_hash().value == DRAFT_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == DRAFT_RULES_SHA256

    binding = raw["rules"]["document_binding"]
    assert binding == {
        "path": SPECIFICATION_PATH.as_posix(),
        "hash": {"algorithm": "sha256", "value": SPECIFICATION_SHA256},
        "traceability_only": True,
    }
    assert sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest() == (
        SPECIFICATION_SHA256
    )

    dependencies = raw["rules"]["exact_upstream_dependencies"]
    for name, dependency in dependencies.items():
        if name in {"plan_at_draft_formation", "stage5d_implementation_baseline"}:
            continue
        path = repository_root / dependency["path"]
        assert path.is_file()
        expected = dependency.get("sha256", dependency.get("raw_sha256"))
        assert sha256(path.read_bytes()).hexdigest() == expected
    assert dependencies["plan_at_draft_formation"] == {
        "path": "PLAN.md",
        "version": "3.11",
        "sha256": "b2b330494a90fc3930f26194b976c651af2f2dd738fd4701cb80c35d4193058e",
    }
    assert dependencies["stage5d_implementation_baseline"]["commit"] == (
        "caf1e6702e2653e61c668508d32eb4f7c8f27783"
    )


def test_stage6c_all_40_owner_items_are_pending_atomic_and_resolvable(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    items = rules["owner_approval_items"]
    expected_ids = tuple(f"6C-{number:02d}" for number in range(1, 41))

    assert tuple(item["approval_item_id"] for item in items) == expected_ids
    assert len(items) == 40
    assert {item["status"] for item in items} == {"pending"}
    assert canonical_sha256(items) == OWNER_ITEMS_SHA256
    for item in items:
        assert item["rule_paths"]
        for pointer in item["rule_paths"]:
            _resolve_json_pointer(rules, pointer)

    specification = (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8")
    assert _decision_ids(specification) == expected_ids
    assert re.search(r"^- \[[xX]\] `6C-", specification, flags=re.MULTILINE) is None
    assert rules["owner_approval_atomicity"] == {
        "all_40_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
        "authorization_predicate": "all(6C-01..6C-40==approved)",
        "pending_rejected_missing_or_identity_drift_result": ("draft_zero_runtime_authority"),
    }


def test_stage6c_draft_has_zero_runtime_historical_holdout_or_trading_authority(
    repository_root: Path,
) -> None:
    raw = _json(repository_root / DRAFT_BUNDLE_PATH)
    rules = raw["rules"]
    boundary = rules["authorization_boundary"]
    batch = rules["batch"]

    assert boundary["proposed_approval_scope"] == ("stage6_development_walk_forward_validation")
    assert boundary["allowed_run_modes"] == []
    assert boundary["specification_validation_only"] is True
    assert boundary["runtime_capability_issued"] is False
    assert boundary["authority_eligible"] is False
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert batch["approved_items"] == 0
    assert batch["runtime_code_exists"] is False
    assert batch["formal_historical_run_exists"] is False
    assert batch["walk_forward_results_exist"] is False
    assert batch["holdout_has_been_opened"] is False

    document = rule_bundle_document_from_json_value(raw)
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry().require(document)


def test_stage6c_temporal_folds_purge_embargo_and_holdout_are_exact(
    repository_root: Path,
) -> None:
    temporal = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["temporal_preregistration"]

    assert temporal["timezone"] == "Asia/Shanghai"
    assert temporal["interval_semantics"] == "LEFT_CLOSED_RIGHT_OPEN"
    assert temporal["population"]["knowledge_cutoff_inclusive_cap"] == (
        "2026-07-28T14:13:31.303929Z"
    )
    assert temporal["development"] == {
        "start_inclusive_local_date": "2019-01-01",
        "end_exclusive_local_date": "2022-01-01",
    }
    assert [fold["fold_id"] for fold in temporal["walk_forward_evaluation_folds"]] == [
        "WF-2022",
        "WF-2023",
        "WF-2024",
        "WF-2025",
    ]
    assert temporal["primary_horizon_trading_sessions"] == 60
    assert temporal["secondary_exploratory_horizons_trading_sessions"] == [20, 120]
    assert temporal["maximum_purge_trading_sessions"] == 120
    assert temporal["embargo_trading_sessions"] == 20
    assert temporal["training_label_end_before_evaluation_start_required"] is True
    assert temporal["frozen_holdout"]["identity_only_in_6c"] is True
    assert temporal["frozen_holdout"]["result_count_summary_or_performance_read_forbidden"] is True


def test_stage6c_readiness_support_and_sample_gates_fail_closed(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    preconditions = rules["formal_execution_preconditions"]
    readiness = rules["data_readiness_and_support"]
    samples = rules["sample_sufficiency"]

    assert preconditions["formal_historical_run_admission_seal_required"] is True
    assert preconditions["stage6b_validation_only_seal_is_not_formal_run_authority"] is True
    assert preconditions["missing_precondition_strategy_evaluator_calls"] == 0
    assert readiness["current_bounded_stage5d_profile_satisfies_formal_6c"] is False
    assert readiness["partial_nav_or_pnl_forbidden"] is True
    assert readiness["unsupported_in_coverage_denominator"] is True
    assert readiness["aggregate_coverage_gte"] == "0.80"
    assert readiness["each_walk_forward_year_coverage_gte"] == "0.70"
    assert samples["minimum_independent_executable_completed_reconciled_trades"] == 30
    assert samples["minimum_per_walk_forward_fold"] == 5
    assert samples["subgroup_confirmatory_minimum"] == 15
    assert samples["abstain_blocked_and_no_fill_are_not_zero_return_trades"] is True


def test_stage6c_competition_metrics_and_inference_are_closed_world(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    models = rules["competition_models"]
    metrics = rules["metrics_and_entry_gates"]
    inference = rules["inference_and_multiple_testing"]

    assert models["closed_world"] == [
        "no_trade",
        "market_or_industry_matched",
        "simple_e4_only",
        "simple_valuation_threshold",
        "full_system",
    ]
    assert models["shared_candidate_pit_horizon_execution_cost_capacity_risk_and_clock"] is True
    assert models["stage6c_business_rule_threshold_search_forbidden"] is True
    assert models["exact_model_semantics"]["market_or_industry_matched"]["minimum_peers"] == 5
    assert models["best_simple_selection"] == {
        "selection_data": "development_2019_2021_only",
        "selection_metric": "primary_estimator",
        "frozen_before_any_walk_forward_summary_read": True,
        "tie_break_low_to_high_complexity": [
            "market_or_industry_matched",
            "simple_e4_only",
            "simple_valuation_threshold",
        ],
        "same_frozen_identity_for_all_walk_forward_folds": True,
        "per_fold_or_post_hoc_reselection_forbidden": True,
    }
    gates = metrics["ready_for_6d_all_required"]
    assert gates["full_system_annualized_net_benchmark_excess_gt"] == "0"
    assert gates["full_vs_best_simple_annualized_net_increment_gte_percentage_points"] == "2.0"
    assert gates["positive_walk_forward_folds_gte"] == 3
    assert gates["maximum_drawdown_lte"] == "0.15"
    assert gates["largest_winner_share_of_total_net_profit_lte"] == "0.25"
    assert gates["one_point_five_x_friction_net_benchmark_excess_gte"] == "0"
    assert inference["bootstrap_resamples"] == 10000
    assert inference["random_seed"] == 20260820
    assert len(inference["confirmatory_family"]) == 5
    assert inference["family_wise_alpha"] == "0.05"
    assert inference["adjustment"] == "HOLM_BONFERRONI"


def test_stage6c_stress_retention_and_phase_handoff_do_not_open_6d(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    stress = rules["ablation_and_stress"]
    retention = rules["retention_and_replay"]
    outcome = rules["phase_outcome_and_handoff"]
    matrix = rules["minimum_validation_matrix"]

    assert len(stress["ablation_layers"]) == 8
    assert stress["friction_multipliers"] == ["1.0", "1.5", "2.0"]
    assert stress["delay_trading_sessions"] == [0, 1, 2]
    assert stress["starting_nav_cny_primary"] == "100000"
    assert stress["starting_nav_cny_capacity_stress"] == "300000"
    assert retention["append_only"] is True
    assert retention["failed_run_cannot_be_overwritten_by_success"] is True
    assert retention["unregistered_parameter_search_forbidden"] is True
    assert retention["exploratory_result_may_enter_current_champion"] is False
    assert outcome["closed_world"] == [
        "READY_FOR_6D_FREEZE",
        "REVISE_NEW_PREREGISTRATION",
        "INSUFFICIENT_EVIDENCE",
        "PRECHECK_BLOCKED",
        "AUDIT_REPLAY_ONLY",
    ]
    assert outcome["ready_for_6d_is_not_stage6_final_pass"] is True
    assert outcome["six_d_requires_unopened_holdout_identity"] is True
    assert matrix["formal_historical_run_in_draft_tests"] is False
    assert matrix["holdout_access_in_draft_tests"] is False
    assert matrix["kb_modification"] is False
