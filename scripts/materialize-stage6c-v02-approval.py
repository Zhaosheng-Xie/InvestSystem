"""Materialize the complete approved Stage 6C v0.2 governance artifacts.

This is a generation-time audit utility. Runtime code must consume the fully
materialized approved bundle and must never merge draft or Markdown sources.
"""

from __future__ import annotations

import json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.domain.rule_approval import rule_bundle_document_from_json_value

ROOT = Path(__file__).resolve().parents[1]
RULE_DIRECTORY = ROOT / "产业卡点及事件驱动系统" / "03_规则与规格"
MACHINE_DIRECTORY = RULE_DIRECTORY / "机器制品"
BASE_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
    "v0.1.0-draft.rule-bundle.json"
)
REVISION_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
    "v0.2.0-draft.rule-bundle.json"
)
APPROVAL_DOCUMENT_PATH = RULE_DIRECTORY / ("Stage6_6C开发样本WalkForward与冠军挑战批准记录_v0.2.md")
APPROVED_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.rule-bundle.json"
)
APPROVAL_PATH = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.approval.json"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain one JSON object")
    return value


def _write(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    base = _json(BASE_PATH)
    revision = _json(REVISION_PATH)
    rules = deepcopy(base["rules"])
    revision_rules = revision["rules"]

    for replaced in (
        "authorization_boundary",
        "batch",
        "document_binding",
        "owner_approval_items",
        "owner_approval_atomicity",
        "minimum_validation_matrix",
        "runtime_must_not_parse_markdown",
    ):
        rules.pop(replaced, None)

    rules["authorization_boundary"] = {
        "approval_scope": "stage6_development_walk_forward_validation",
        "allowed_run_modes": [],
        "validation_capability_issued": True,
        "authorizes_implementation": True,
        "authorizes_synthetic_kernel_validation": True,
        "authorizes_formal_historical_admission": False,
        "authorizes_formal_development_run": False,
        "authorizes_walk_forward_run": False,
        "authorizes_holdout_commitment_read": False,
        "authorizes_holdout_artifact_read": False,
        "authorizes_holdout_open": False,
        "authorizes_stage6_final_pass": False,
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
    rules["batch"] = {
        "stage": "Stage 6",
        "batch_id": "6C-v0.2",
        "purpose": "approved_anonymous_synthetic_walk_forward_kernel_validation",
        "owner_approval_required": True,
        "approval_items_required": 40,
        "approved_items": 40,
        "approved_machine_bundle_exists": True,
        "approval_record_exists": True,
        "validation_capability_verifier_exists": True,
        "runtime_code_exists": False,
        "formal_historical_run_exists": False,
        "walk_forward_results_exist": False,
        "holdout_has_been_opened": False,
    }
    rules["approval_source_binding"] = {
        "specification_path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6C开发样本WalkForward与冠军挑战精确规则包_v0.2.md"
        ),
        "specification_raw_sha256": "3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368",
        "draft_proposal_path": (
            "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
            "industrial_event_stage6_6c_development_walk_forward_champion_challenge_"
            "v0.2.0-draft.rule-bundle.json"
        ),
        "draft_raw_sha256": "6f2663feb8b8cef5fd969d2791d2505b82e31ff42071872df0350c2196007afd",
        "draft_bundle_sha256": "a45396cde1e23ab6c05ea03111cf9f72044031a57d6a91dce554e15d6979a72c",
        "draft_rules_sha256": "c64f2b6057355c5e0bca9d597c01ed9f39ae0fd483ee469de86f7c964d8879c8",
        "draft_owner_items_sha256": "7e3eee1c02a8d16e27ec3180379d221302ff3ca1741bb43300f145063f910bd6",
        "v0_1_specification_sha256": "bcf77c5608eb09fd3e591f0bd92a3e0e71a27c42c18123e26e98080db9609383",
        "v0_1_draft_raw_sha256": "03e6717ab0de1b2c595e46b7a2a25c5cd3947ba9942a6e939f21636ce114e881",
        "accepted_rule_source": "exact_v0_1_rules_plus_exact_v0_2_replacements",
        "complete_rules_materialized": True,
        "runtime_delta_or_markdown_merge_forbidden": True,
        "source_files_remain_immutable": True,
    }
    approval_document_hash = sha256(APPROVAL_DOCUMENT_PATH.read_bytes()).hexdigest()
    rules["document_binding"] = {
        "path": (
            "产业卡点及事件驱动系统/03_规则与规格/"
            "Stage6_6C开发样本WalkForward与冠军挑战批准记录_v0.2.md"
        ),
        "hash": {"algorithm": "sha256", "value": approval_document_hash},
        "traceability_only": True,
    }
    rules["phase_authority"] = {
        "6A": "approved_governance_only",
        "6B": "completed_with_scope_limits_validation_only",
        "6C_rules": "approved",
        "6C_synthetic_kernel": "authorized_for_implementation_and_validation",
        "6C_formal_execution": "not_authorized",
        "6D": "not_authorized",
        "formal_state_migration": "not_authorized",
        "approval_or_completion_is_not_transitive": True,
        "next_allowed_action": "implement_and_accept_anonymous_synthetic_stage6c_kernel",
    }

    rules["holdout_technical_isolation"] = deepcopy(revision_rules["holdout_technical_isolation"])
    rules["coverage_selection_audit"] = deepcopy(revision_rules["coverage_selection_audit"])
    rules["exact_primary_estimator_and_benchmark"] = deepcopy(
        revision_rules["exact_primary_estimator_and_benchmark"]
    )
    rules["inference_and_multiple_testing"] = {
        "adjusted_entry_gate": deepcopy(revision_rules["adjusted_inference_entry_gate"]),
        "portfolio_fact_and_bootstrap": deepcopy(revision_rules["portfolio_fact_and_bootstrap"]),
    }
    rules["data_readiness_and_support"]["coverage_selection_audit_required"] = True
    rules["temporal_preregistration"]["frozen_holdout"]["technical_isolation_profile"] = (
        "Stage6DHoldoutCommitment_v0.2"
    )
    rules["metrics_and_entry_gates"]["primary_estimator"] = deepcopy(
        revision_rules["exact_primary_estimator_and_benchmark"]
    )
    rules["metrics_and_entry_gates"]["ready_for_6d_all_required"][
        "v0_2_adjusted_and_three_path_inference_gate"
    ] = True
    base_matrix = base["rules"]["minimum_validation_matrix"]
    revision_matrix = revision_rules["minimum_validation_matrix"]
    rules["minimum_validation_matrix"] = {
        "required": sorted(set(base_matrix["required"] + revision_matrix["required"])),
        "formal_historical_run": False,
        "holdout_artifact_read": False,
        "kb_modification": False,
    }
    rules["owner_approval_items"] = [
        {"approval_item_id": f"6C-{number:02d}", "status": "approved"} for number in range(1, 41)
    ]
    rules["owner_approval_atomicity"] = {
        "all_40_required": True,
        "authorization_predicate": "all(v0.2_6C-01..6C-40==approved)",
        "same_exact_bundle_and_approval_record_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
    }
    rules["approved_semantic_guards"] = {
        "complete_v0_1_plus_v0_2_rules_materialized": True,
        "holdout_artifact_inaccessible_to_6c": True,
        "holdout_commitment_contains_no_performance_proxy": True,
        "adjusted_and_three_path_inference_required": True,
        "canonical_source_driven_portfolio_fact_required": True,
        "contribution_rows_cannot_be_summed_as_portfolio_bootstrap": True,
        "outcome_blind_coverage_selection_audit_required": True,
        "exact_252_session_twr_and_benchmark_required": True,
        "current_stage5d_profile_does_not_satisfy_formal_6c": True,
        "stage6b_validation_seal_is_not_formal_run_authority": True,
        "formal_execution_and_holdout_require_separate_owner_approval": True,
        "all_outputs_authority_eligible_false": True,
    }
    rules["runtime_must_not_parse_markdown_or_delta_bundle"] = True

    approved = {
        "schema_version": "0.1.0-draft",
        "strategy_id": "industrial_bottleneck_event",
        "bundle_id": ("industrial_event_stage6_6c_development_walk_forward_champion_challenge"),
        "bundle_version": "0.2.0",
        "declared_status": "approved",
        "rules": rules,
    }
    document = rule_bundle_document_from_json_value(approved)
    _write(APPROVED_PATH, approved)
    approval = {
        "approval_id": "rule_approval_stage6_6c_development_walk_forward_v0_2_0",
        "strategy_id": document.strategy_id,
        "bundle_id": document.bundle_id,
        "bundle_version": document.bundle_version,
        "bundle_hash": {"algorithm": "sha256", "value": document.bundle_hash().value},
        "approved_by": "repository_owner",
        "approved_at": "2026-08-20T13:13:12.270950Z",
        "approval_scope": "stage6_development_walk_forward_validation",
        "approval_source_ref": "codex_task_owner_unified_approval_stage6c_v02_20260820",
        "schema_version": "0.1.0-draft",
    }
    _write(APPROVAL_PATH, approval)


if __name__ == "__main__":
    main()
