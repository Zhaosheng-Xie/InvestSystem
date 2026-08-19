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
    "产业卡点及事件驱动系统/03_规则与规格/Stage6_6B历史准入状态确认与原子留存精确规则包_v0.1.md"
)
DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage6_6b_historical_admission_atomic_retention_"
    "v0.1.0-draft.rule-bundle.json"
)

SPECIFICATION_SHA256 = "96ec47da0eb356f726db3ce1be8015366ad3a804cc3f93d63c5b1c3fc65e3f5a"
DRAFT_RAW_SHA256 = "4a5ed454e6ab152e03dc83b9723f035eacd020ff4bfe16d742427b4aaff827e4"
DRAFT_BUNDLE_SHA256 = "0ef8808f8de5e44991bbdecb5bb6a63f1b408d0650fd395c958af454adb262d4"
DRAFT_RULES_SHA256 = "4cd66370471d22169f1308ad4cc9f16852b5b6ebe1f20832ca3de6e30598a73b"
OWNER_ITEMS_SHA256 = "17d1d3dabb4d68e8917ce008f6494d644c006c7a4d57f27a81a2e89260a2a3d8"
AUTHORITY_PROFILE_SHA256 = "07d3e6a03aa45f38604ecd3728b2ad64b34c075dfc94032431a4486911692238"


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
    section = specification.split("## 14. Owner 逐项批准清单", 1)[1].split(
        "## 15. 批准后的唯一实施顺序", 1
    )[0]
    return tuple(
        match.group(1)
        for line in section.splitlines()
        if (match := re.fullmatch(r"- \[ \] `(6B-\d{2})`：.+", line)) is not None
    )


def test_stage6b_draft_has_strict_identity_and_exact_source_bindings(
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
        "industrial_event_stage6_6b_historical_admission_atomic_retention"
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
    assert dependencies["plan_at_draft_formation"] == {
        "path": "PLAN.md",
        "version": "3.7",
        "sha256": "da5fab0050c809e41ba43b1a041e595b3ad0d9a22ca54745999dda10c73300b8",
    }
    path_keys = (
        "industrial_prd",
        "stage6a_approved_bundle",
        "stage6a_approval_record",
        "stage6a_acceptance",
        "kb_transport_snapshot",
        "kb_transport_support_matrix",
    )
    for dependency_name in path_keys:
        dependency = dependencies[dependency_name]
        path = repository_root / dependency["path"]
        assert path.is_file()
        expected = dependency.get("sha256", dependency.get("raw_sha256"))
        assert sha256(path.read_bytes()).hexdigest() == expected

    for dependency in dependencies["is_contracts"].values():
        path = repository_root / dependency["path"]
        assert path.is_file()
        assert sha256(path.read_bytes()).hexdigest() == dependency["sha256"]
    assert dependencies["implementation_entry_baseline"]["commit"] == (
        "59e1edd80765dbd67635d1497b2fc008d08b21d9"
    )
    assert dependencies["is_implementation_sources"]["storage_schema_version"] == 3


def test_stage6b_all_32_owner_items_are_pending_and_resolvable(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    items = rules["owner_approval_items"]
    expected_ids = tuple(f"6B-{number:02d}" for number in range(1, 33))

    assert tuple(item["approval_item_id"] for item in items) == expected_ids
    assert len(items) == 32
    assert {item["status"] for item in items} == {"pending"}
    assert canonical_sha256(items) == OWNER_ITEMS_SHA256
    for item in items:
        assert item["rule_paths"]
        for pointer in item["rule_paths"]:
            _resolve_json_pointer(rules, pointer)

    specification = (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8")
    assert _decision_ids(specification) == expected_ids
    assert re.search(r"^- \[[xX]\] `6B-", specification, flags=re.MULTILINE) is None
    assert rules["owner_approval_atomicity"] == {
        "all_32_required": True,
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
        "authorization_predicate": "all(6B-01..6B-32==approved)",
        "pending_rejected_missing_or_identity_drift_result": ("draft_zero_runtime_authority"),
    }


def test_stage6b_draft_has_zero_runtime_historical_or_trading_authority(
    repository_root: Path,
) -> None:
    raw = _json(repository_root / DRAFT_BUNDLE_PATH)
    rules = raw["rules"]
    boundary = rules["authorization_boundary"]
    batch = rules["batch"]

    assert boundary["proposed_approval_scope"] == ("stage6_historical_admission_validation")
    assert boundary["allowed_run_modes"] == []
    assert boundary["specification_validation_only"] is True
    assert boundary["runtime_capability_issued"] is False
    assert boundary["authority_eligible"] is False
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert batch["approved_items"] == 0
    assert batch["runtime_code_exists"] is False
    assert batch["formal_storage_migration_exists"] is False
    assert batch["historical_evaluator_exists"] is False
    assert batch["formal_historical_run_exists"] is False
    assert batch["holdout_has_been_opened"] is False

    document = rule_bundle_document_from_json_value(raw)
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry().require(document)
    forged = RuleApprovalRecord(
        approval_id="forged_stage6b_draft_approval",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="test_only",
        approved_at=datetime(2026, 8, 19, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE6_HISTORICAL_VALIDATION_GOVERNANCE,
        approval_source_ref="test_only",
    )
    with pytest.raises(ValueError, match="RULE_BUNDLE_STATUS_NOT_APPROVED"):
        RuleApprovalRegistry((forged,)).require(document)


def test_stage6b_authority_profile_is_exact_and_secret_free(repository_root: Path) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    authority = rules["authority_contract"]
    profile = authority["profile"]

    assert canonical_sha256(profile) == AUTHORITY_PROFILE_SHA256
    assert authority["profile_canonical_sha256"] == AUTHORITY_PROFILE_SHA256
    assert profile == {
        "authority_id": "kb_public_https_status_v1",
        "endpoint_origin": "https://82.157.112.120",
        "status_path_template": "/api/v1/dataset-releases/{release_id}/status",
        "transport_snapshot_sha256": (
            "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169"
        ),
        "provider_snapshot_max_age_seconds": 300,
        "max_clock_skew_seconds": 30,
        "confirmation_ttl_seconds": 300,
        "redirect_policy": "forbidden",
        "tls_certificate_verification_required": True,
        "credential_policy": "short_lived_read_only_process_memory_only",
    }
    credential = rules["credential_boundary"]
    assert credential["token_in_process_memory_only"] is True
    assert (
        credential[
            "token_or_authorization_header_in_canonical_bytes_logs_db_cache_or_git_forbidden"
        ]
        is True
    )
    raw_text = (repository_root / DRAFT_BUNDLE_PATH).read_text(encoding="utf-8")
    assert "Bearer " not in raw_text


def test_stage6b_closure_confirmation_and_seal_are_closed_world(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    request = rules["historical_admission_request"]
    closure = rules["release_closure"]
    confirmation = rules["run_release_status_confirmation"]
    envelope = rules["admission_envelope_and_seal"]

    assert request["strategy_input_ref_count"] == 1
    assert request["latest_forbidden"] is True
    assert closure["source_releases_are_not_additional_strategy_input_refs"] is True
    assert closure["confirmation_items_pin_releases_and_closure_release_set_exactly_equal"] is True
    assert confirmation["existing_contract_status"] == ("0.1.0-draft_not_runtime_authority")
    assert confirmation["stage6b_requires_new_versioned_approved_contract"] is True
    assert confirmation["caller_supplied_pass_forbidden"] is True
    assert envelope["seal_is_only_admission_completion_marker"] is True
    assert envelope["evaluator_must_reload_and_reverify_seal"] is True
    assert "seal_hash" in envelope["seal_required_fields"]


def test_stage6b_atomic_commit_failure_and_recovery_are_fail_closed(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    atomic = rules["atomic_commit"]
    recovery = rules["idempotency_concurrency_and_recovery"]

    assert atomic["transaction"] == "BEGIN IMMEDIATE"
    assert atomic["network_io_and_candidate_cas_before_database_write_transaction"] is True
    assert atomic["network_io_while_holding_database_write_lock_forbidden"] is True
    assert atomic["atomic_write_or_link_order"][-1] == ("historical_run_admission_seal_last")
    assert atomic["any_failure_authoritative_state_rows"] == 0
    assert atomic["any_failure_evaluator_calls"] == 0
    assert atomic["partial_pin_manifest_confirmation_or_seal_forbidden"] is True
    assert recovery["same_run_request_envelope_seal_same_bytes"] == "RETURN_EXISTING"
    assert recovery["same_identity_or_idempotency_key_different_bytes"] == (
        "IMMUTABLE_IDENTITY_CONFLICT"
    )
    assert recovery["wal_ioerr_full_busy_or_crash_visible_outcome"] == ("COMPLETE_SEAL_OR_NO_SEAL")
    assert recovery["sqlite_v2_quarantine"] == "PERMANENT_AUDIT_REPLAY_ONLY"
    assert recovery["stage5d_reserved_sqlite_v4_semantics_must_not_be_reused"] is True
    assert recovery["stage6b_formal_migration_version_and_table_prefix"] == (
        "OWNER_DECISION_REQUIRED_BEFORE_FORMAL_STATE_MIGRATION"
    )


def test_stage6b_status_withdrawal_audit_and_result_states_are_closed_world(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    status = rules["status_evidence"]
    freshness = rules["freshness_and_pit"]
    audit = rules["withdrawal_read_and_audit"]
    result = rules["admission_result"]

    assert status["one_complete_history_per_closure_release"] is True
    assert status["required_current_status"] == "published"
    assert status["withdrawn_is_terminal"] is True
    assert freshness["provider_snapshot_may_lead_consumer_by_at_most_seconds"] == 30
    assert freshness["provider_snapshot_age_at_pin_lte_seconds"] == 300
    assert freshness["confirmation_consumed_by_confirmed_at_plus_seconds"] == 300
    assert freshness["equal_boundaries_pass"] is True
    assert audit["any_unconfirmable_or_withdrawn_closure_release_blocks_new_seal"] is True
    assert audit["historical_material_after_withdrawal"] == "AUDIT_REPLAY_ONLY"
    assert audit["audit_state_writes"] == 0
    assert result["status_closed_world"] == [
        "SEALED_VALIDATION_ONLY",
        "PRECHECK_BLOCKED",
        "STATUS_UNCONFIRMED",
        "RECONCILIATION_BLOCKED",
        "IMMUTABLE_IDENTITY_CONFLICT",
        "ATOMIC_COMMIT_BLOCKED",
        "AUDIT_REPLAY_ONLY",
    ]
    assert result["formal_historical_authority_status"] == "NOT_AUTHORIZED"
    assert result["strategy_evaluator_calls"] == 0
    assert result["authority_eligible"] is False


def test_stage6b_validation_matrix_and_repository_isolation_are_explicit(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    matrix = rules["minimum_validation_matrix"]
    isolation = rules["cross_repository_and_strategy_isolation"]

    assert len(matrix["required"]) == 18
    assert "failure_at_every_atomic_step" in matrix["required"]
    assert "withdrawal_audit_replay" in matrix["required"]
    assert "zero_strategy_evaluator_calls" in matrix["required"]
    assert matrix["validation_store"] == ("independent_temporary_investsystem_state_and_cache")
    assert matrix["production_state_database_modification"] is False
    assert matrix["kb_modification"] is False
    assert isolation["kb_public_contracts_and_published_release_surfaces_only"] is True
    assert (
        isolation["kb_sqlite_raw_staging_published_worktree_or_internal_package_reads_forbidden"]
        is True
    )
    assert isolation["kb_mutation_forbidden"] is True
    assert isolation["industrial_and_theme_strategy_signal_interchange"] is False
    assert rules["runtime_must_not_parse_markdown"] is True
