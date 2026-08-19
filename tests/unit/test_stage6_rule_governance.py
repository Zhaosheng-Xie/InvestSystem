from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system import RuleApprovalRecord, RuleApprovalRegistry, RuleApprovalScope
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import rule_bundle_document_from_json_value
from invest_system.models import RuleStatus

SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage6_6A历史验证预注册与准入精确规则包_v0.1.md"
)
DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage6_6a_historical_validation_preregistration_"
    "v0.1.0-draft.rule-bundle.json"
)

SPECIFICATION_SHA256 = "7ef1126261ddbead37c016fe472a8d518cddb553fe3c3d1214f5c378a9b964df"
DRAFT_RAW_SHA256 = "a071e2509bcf86361836cdd5e5d0748748b607e1129edc4f47c308de7073cdca"
DRAFT_BUNDLE_SHA256 = "41759cb4e4db282d98bc70b3a599f632283d2cf79330adab910b1bc9a308eb92"
DRAFT_RULES_SHA256 = "c1d0298488317318b8d9dedde9f1ff719aa83d08af7196d255482e11522dc097"
OWNER_ITEMS_SHA256 = "ea2b4b9d232884d3cd12b4a8003562261fc8e6c8e8f299b88f1df1fb16e3fcfe"


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
    section = specification.split("## 13. Owner 逐项批准清单", 1)[1].split(
        "## 14. 批准后的唯一顺序", 1
    )[0]
    return tuple(
        match.group(1)
        for line in section.splitlines()
        if (match := re.fullmatch(r"- \[ \] `(6A-\d{2})`：.+", line)) is not None
    )


def test_stage6a_draft_has_strict_identity_and_exact_source_bindings(
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
        "industrial_event_stage6_6a_historical_validation_preregistration"
    )
    assert document.bundle_version == "0.1.0-draft"
    assert document.declared_status is RuleStatus.DRAFT
    assert document.bundle_hash().value == DRAFT_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == DRAFT_RULES_SHA256

    rules = raw["rules"]
    binding = rules["document_binding"]
    assert binding == {
        "path": SPECIFICATION_PATH.as_posix(),
        "hash": {"algorithm": "sha256", "value": SPECIFICATION_SHA256},
        "traceability_only": True,
    }
    assert sha256((repository_root / SPECIFICATION_PATH).read_bytes()).hexdigest() == (
        SPECIFICATION_SHA256
    )

    dependencies = rules["exact_upstream_dependencies"]
    assert dependencies["plan"] == {
        "path": "PLAN.md",
        "version": "3.6",
        "sha256": "2e5a2f7e757e68705024d235db03a5b41c45e1ef9bcaa79f43900d4ee253da9f",
    }
    for dependency in (
        "industrial_prd",
        "stage3d_acceptance",
        "stage5d_preregistration",
        "stage5d_acceptance",
    ):
        item = dependencies[dependency]
        path = repository_root / item["path"]
        assert path.is_file()
        assert sha256(path.read_bytes()).hexdigest() == item["sha256"]
    assert dependencies["stage5d_implementation_baseline"] == {
        "commit_algorithm": "git-sha1",
        "commit": "caf1e6702e2653e61c668508d32eb4f7c8f27783",
        "scope_limited": True,
    }


def test_stage6a_all_35_owner_items_are_pending_and_resolvable(
    repository_root: Path,
) -> None:
    raw = _json(repository_root / DRAFT_BUNDLE_PATH)
    rules = raw["rules"]
    items = rules["owner_approval_items"]
    expected_ids = tuple(f"6A-{number:02d}" for number in range(1, 36))

    assert tuple(item["approval_item_id"] for item in items) == expected_ids
    assert len(items) == 35
    assert {item["status"] for item in items} == {"pending"}
    assert canonical_sha256(items) == OWNER_ITEMS_SHA256
    for item in items:
        assert item["rule_paths"]
        for pointer in item["rule_paths"]:
            _resolve_json_pointer(rules, pointer)

    specification = (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8")
    assert _decision_ids(specification) == expected_ids
    assert re.search(r"^- \[[xX]\] `6A-", specification, flags=re.MULTILINE) is None
    assert rules["batch"]["approval_items_required"] == 35
    assert rules["batch"]["approved_items"] == 0
    assert rules["owner_approval_atomicity"] == {
        "all_35_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
        "authorization_predicate": "all(6A-01..6A-35==approved)",
        "pending_rejected_missing_or_identity_drift_result": ("draft_zero_runtime_authority"),
    }


def test_stage6a_draft_has_zero_runtime_data_or_trading_authority(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    boundary = rules["authorization_boundary"]
    batch = rules["batch"]

    assert boundary["proposed_approval_scope"] == ("stage6_historical_validation_governance")
    assert boundary["allowed_run_modes"] == []
    assert boundary["specification_validation_only"] is True
    assert boundary["runtime_capability_issued"] is False
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert batch["approved_machine_bundle_exists"] is False
    assert batch["approval_record_exists"] is False
    assert batch["runtime_code_exists"] is False
    assert batch["historical_evaluator_exists"] is False
    assert batch["release_confirmation_issuer_exists"] is False
    assert batch["holdout_has_been_opened"] is False

    document = rule_bundle_document_from_json_value(_json(repository_root / DRAFT_BUNDLE_PATH))
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry().require(document)

    forged = RuleApprovalRecord(
        approval_id="forged_stage6a_draft_approval",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="test_only",
        approved_at=datetime(2026, 8, 19, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION,
        approval_source_ref="test_only",
    )
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry((forged,)).require(document)


def test_stage6a_phase_order_does_not_grant_transitive_authority(
    repository_root: Path,
) -> None:
    phase_model = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["phase_model"]

    assert tuple(
        key for key in phase_model if key != "approval_or_completion_is_not_transitive"
    ) == (
        "6A",
        "6B",
        "6C",
        "6D",
    )
    assert phase_model["6A"]["status"] == "draft_governance_only"
    assert {phase_model[phase]["status"] for phase in ("6B", "6C", "6D")} == {"not_authorized"}
    assert phase_model["6D"]["purpose"] == (
        "single_open_frozen_holdout_champion_challenge_and_report"
    )
    assert phase_model["approval_or_completion_is_not_transitive"] is True


def test_stage6a_preregistration_and_admission_fail_closed_before_history(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    preregistration = rules["preregistration_contract"]
    sample = rules["sample_and_pit"]
    admission = rules["historical_admission"]

    assert preregistration["content_addressed"] is True
    assert preregistration["freeze_before_any_candidate_performance_is_read"] is True
    assert preregistration["performance_visible_change_requires_new_version"] is True
    assert preregistration["missing_required_field_outcome"] == "PRECHECK_BLOCKED"
    assert sample["split_order"] == ["development", "walk_forward", "frozen_holdout"]
    assert sample["random_time_mixing_forbidden"] is True
    assert sample["owner_required_unset_fields"]
    assert sample["unset_field_outcome"] == "PRECHECK_BLOCKED"
    assert admission["implementation_phase"] == "6B"
    assert admission["stage3d_validation_object_reuse_forbidden"] is True
    assert admission["stage7_authority_reuse_forbidden"] is True
    assert admission["any_failure_evaluator_calls"] == 0
    assert admission["any_failure_state_writes"] == 0
    assert admission["withdrawn_or_unconfirmable_blocks_new_run"] is True
    assert admission["historical_material_after_withdrawal"] == "audit_replay_only"


def test_stage6a_support_matrix_and_prd_thresholds_cannot_be_laundered_into_rules(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    support = rules["accounting_support_gate"]
    metrics = rules["metrics_and_statistics"]

    assert support["current_stage5d_baseline"] == "single_enter_buy_bounded_replay_only"
    assert support["current_baseline_is_sufficient_for_formal_historical_population"] is False
    assert support["unsupported_input_outcome"] == ["BLOCKED", "ABSTAIN"]
    assert support["partial_nav_or_pnl_forbidden"] is True
    assert support["silent_exclusion_forbidden"] is True
    assert support["coverage_below_preregistered_threshold"] == "INSUFFICIENT_EVIDENCE"

    hypotheses = metrics["prd_hypothesis_thresholds"]
    assert hypotheses == {
        "minimum_independent_trades": 30,
        "net_mean_expectation": ">0",
        "cluster_resampled_confidence_level": "95%",
        "cluster_resampled_ci_lower_bound": ">0",
        "maximum_out_of_sample_drawdown": "<=15%",
        "largest_winner_share_of_total_net_profit": "<=25%",
        "status": "hypothesis_not_runtime_rule",
    }
    assert metrics["primary_estimand"]["exact_horizon"] == "OWNER_DECISION_REQUIRED"
    assert metrics["multiple_testing"]["adjustment_method"] == "OWNER_DECISION_REQUIRED"
    assert metrics["additional_owner_decisions_required"]


def test_stage6a_champion_challenge_bias_audit_and_replay_are_closed_world(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    champion = rules["champion_challenge"]
    audit = rules["parameter_and_bias_audit"]
    result = rules["result_and_replay"]
    isolation = rules["cross_repository_and_strategy_isolation"]

    assert champion["hypothesis_closed_world"] == [
        "H0_no_independent_alpha",
        "no_trade",
        "market_or_industry_matched",
        "simple_e4_only",
        "simple_valuation_threshold",
        "full_system",
    ]
    assert champion["index_only_comparison_is_sufficient"] is False
    assert champion["winner_selected_after_holdout_forbidden"] is True
    assert audit["holdout_tuning_forbidden"] is True
    assert audit["required_ablations"] == [
        "E0_E7",
        "four_gates",
        "profit_bridge",
        "valuation",
        "exit",
        "risk",
        "execution",
    ]
    assert result["result_status_closed_world"] == [
        "PASS",
        "FAIL",
        "INSUFFICIENT_EVIDENCE",
        "PRECHECK_BLOCKED",
        "AUDIT_REPLAY_ONLY",
    ]
    assert result["successful_rerun_must_not_overwrite_failure"] is True
    assert result["historical_result_is_forward_or_live_evidence"] is False
    assert isolation["kb_public_contracts_and_published_releases_only"] is True
    assert isolation["industrial_and_theme_strategy_signal_interchange"] is False
    assert rules["runtime_must_not_parse_markdown"] is True
