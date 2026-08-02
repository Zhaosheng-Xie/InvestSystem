from __future__ import annotations

import json
from dataclasses import fields
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from invest_system import (
    FixedClock,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
    read_clock,
)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def make_digest(value: dict[str, Any]) -> HashDigest:
    return HashDigest(algorithm=value["algorithm"], value=value["value"])


def build_manifest_from_complete_identity(
    identity: dict[str, Any],
) -> StrategyRunManifest:
    expected_fields = {field.name for field in fields(StrategyRunManifest)}
    assert set(identity) == expected_fields

    raw_reference = cast(dict[str, Any], identity["strategy_input_ref"])
    reference = StrategyInputRef(
        schema_version=raw_reference["schema_version"],
        dataset_release_id=raw_reference["dataset_release_id"],
        knowledge_cutoff=parse_utc(raw_reference["knowledge_cutoff"]),
        release_manifest_schema_version=raw_reference["release_manifest_schema_version"],
        manifest_hash=make_digest(raw_reference["manifest_hash"]),
    )
    clock = FixedClock(parse_utc(identity["created_at"]))

    return StrategyRunManifest(
        strategy_run_manifest_schema_version=identity["strategy_run_manifest_schema_version"],
        run_id=identity["run_id"],
        created_at=read_clock(clock, field_name="created_at"),
        strategy_id=identity["strategy_id"],
        strategy_version=identity["strategy_version"],
        code_commit=identity["code_commit"],
        rule_bundle_id=identity["rule_bundle_id"],
        rule_bundle_version=identity["rule_bundle_version"],
        rule_bundle_hash=make_digest(identity["rule_bundle_hash"]),
        rule_status=RuleStatus(identity["rule_status"]),
        rule_approval_id=identity["rule_approval_id"],
        rule_approval_record_hash=(
            make_digest(identity["rule_approval_record_hash"])
            if identity["rule_approval_record_hash"] is not None
            else None
        ),
        rule_approval_scope=identity["rule_approval_scope"],
        config_hash=make_digest(identity["config_hash"]),
        strategy_input_ref=reference,
        input_envelope_hash=make_digest(identity["input_envelope_hash"]),
        strategy_case_envelope_hash=(
            make_digest(identity["strategy_case_envelope_hash"])
            if identity["strategy_case_envelope_hash"] is not None
            else None
        ),
        strategy_case_input_hash=(
            make_digest(identity["strategy_case_input_hash"])
            if identity["strategy_case_input_hash"] is not None
            else None
        ),
        synthetic_fixture_id=identity["synthetic_fixture_id"],
        synthetic_fixture_version=identity["synthetic_fixture_version"],
        synthetic_fixture_payload_hash=(
            make_digest(identity["synthetic_fixture_payload_hash"])
            if identity["synthetic_fixture_payload_hash"] is not None
            else None
        ),
        input_path=identity["input_path"],
        synthetic=identity["synthetic"],
        validation_only=identity["validation_only"],
        not_a_published_release=identity["not_a_published_release"],
        not_strategy_evidence=identity["not_strategy_evidence"],
        authorizes_positions=identity["authorizes_positions"],
        authorizes_orders=identity["authorizes_orders"],
        artifact_consumption_receipt_hash=make_digest(
            identity["artifact_consumption_receipt_hash"]
        ),
        artifact_fetch_observation_id=identity["artifact_fetch_observation_id"],
        release_status_observation_id=identity["release_status_observation_id"],
        release_admission_observation_id=identity["release_admission_observation_id"],
        random_seed=identity["random_seed"],
        run_mode=RunMode(identity["run_mode"]),
        runtime_environment_lock_hash=make_digest(identity["runtime_environment_lock_hash"]),
    )


def test_complete_fixed_identity_rebuilds_the_same_manifest_bytes_and_hash(
    repository_root: Path,
) -> None:
    fixture_root = repository_root / "tests" / "fixtures" / "synthetic"
    json_path = fixture_root / "strategy_run_manifest_v0.2.0-draft.json"
    hash_path = fixture_root / "strategy_run_manifest_v0.2.0-draft.sha256"
    checked_in_bytes = json_path.read_bytes()
    expected_bytes = checked_in_bytes[:-1] if checked_in_bytes.endswith(b"\n") else checked_in_bytes
    expected_json = expected_bytes.decode("utf-8")
    expected_hash = hash_path.read_text(encoding="ascii").strip()

    first_identity = cast(dict[str, Any], json.loads(expected_json))
    second_identity = cast(dict[str, Any], json.loads(expected_json))
    first = build_manifest_from_complete_identity(first_identity)
    second = build_manifest_from_complete_identity(second_identity)

    assert first is not second
    assert first.strategy_input_ref is not second.strategy_input_ref
    assert first.to_canonical_json() == expected_json
    assert second.to_canonical_json() == expected_json
    assert first.to_canonical_bytes() == second.to_canonical_bytes() == expected_bytes
    assert first.canonical_sha256() == expected_hash
    assert second.canonical_sha256() == expected_hash
