from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from stage2b_support import (
    STAGE2B_BASE_PATH,
    STAGE2B_BLOCKED_PATH,
    STAGE2B_BOUNDARY_PATH,
    STAGE2B_GOLDEN_PATH,
    STAGE2B_REGISTRY_PATH,
    STAGE2B_REPLAY_PATH,
    apply_mutations,
    build_stage2b_fixture_registry,
    find_case,
    load_approved_stage2b_artifacts,
    load_json_object,
    load_stage2b_fixture_registry,
    materialize_stage2b_case,
    matrix_cases,
    verify_canonical_lock,
)

_FIXTURE_PATHS = (
    STAGE2B_BASE_PATH,
    STAGE2B_GOLDEN_PATH,
    STAGE2B_BOUNDARY_PATH,
    STAGE2B_BLOCKED_PATH,
    STAGE2B_REPLAY_PATH,
    STAGE2B_REGISTRY_PATH,
)
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


def _classified_objects(
    value: Any,
    *,
    path: str = "$",
) -> list[tuple[str, dict[str, Any]]]:
    result: list[tuple[str, dict[str, Any]]] = []
    if isinstance(value, dict):
        if "classification" in value:
            result.append((path, value))
        for key, item in value.items():
            result.extend(_classified_objects(item, path=f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            result.extend(_classified_objects(item, path=f"{path}[{index}]"))
    return result


@pytest.mark.parametrize("path", _FIXTURE_PATHS, ids=lambda path: cast(Path, path).name)
def test_stage2b_fixture_has_a_valid_canonical_lock(path: Path) -> None:
    digest = verify_canonical_lock(path)

    assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_stage2b_normal_matrices_pin_identity_but_resolve_hash_from_registry() -> None:
    approved = load_approved_stage2b_artifacts()
    actual_bundle_hash = approved.capability.bundle_hash.value

    for path in (STAGE2B_GOLDEN_PATH, STAGE2B_BOUNDARY_PATH):
        matrix = load_json_object(path)
        reference = cast(dict[str, Any], matrix["rule_bundle_reference"])

        assert reference == {
            "approval_id": "rule_approval_stage2b_minimum_order_contract_v0_1_0",
            "approval_scope": "stage2b_synthetic_validation",
            "bundle_id": "industrial_event_minimum_order_contract_slice",
            "bundle_version": "0.1.0",
            "canonical_hash_resolution": "trusted_approval_registry_at_test_time",
            "rule_status_required": "approved",
            "strategy_id": "industrial_bottleneck_event",
        }
        assert actual_bundle_hash not in path.read_text(encoding="utf-8")


def test_stage2b_every_normal_case_is_unique_and_uses_replace_only_mutations() -> None:
    all_cases: list[dict[str, Any]] = []
    for path in (STAGE2B_GOLDEN_PATH, STAGE2B_BOUNDARY_PATH):
        _matrix, cases = matrix_cases(path)
        all_cases.extend(cases)

    case_ids = [case["case_id"] for case in all_cases]
    assert len(case_ids) == len(set(case_ids)) == 24

    base = load_json_object(STAGE2B_BASE_PATH)
    for case in all_cases:
        mutations = cast(list[dict[str, Any]], case["mutations"])
        assert all(set(mutation) == {"op", "path", "value"} for mutation in mutations)
        assert all(mutation["op"] == "replace" for mutation in mutations)
        # The adapter rejects missing targets; the test makes this fixture contract explicit.
        assert apply_mutations(base, mutations) is not base


def test_stage2b_trade_case_preserves_the_approved_baseline_identity_only() -> None:
    base = load_json_object(STAGE2B_BASE_PATH)
    base_identity = cast(dict[str, Any], base["fixture_identity"])
    _golden_matrix, golden_cases = matrix_cases(STAGE2B_GOLDEN_PATH)
    _boundary_matrix, boundary_cases = matrix_cases(STAGE2B_BOUNDARY_PATH)
    trade = next(case for case in golden_cases if case["case_id"] == "SYN-TRADE-001")
    trade_identity = cast(dict[str, Any], trade["materialized_identity"])
    identity_fields = ("dataset_release_id", "fixture_id", "input_id")
    approved = load_approved_stage2b_artifacts()
    bundle_rules = cast(dict[str, Any], approved.bundle_json["rules"])
    approved_fixture_identity = cast(dict[str, Any], bundle_rules["fixture_identity"])
    materialized = materialize_stage2b_case(
        find_case(golden_cases, "SYN-TRADE-001"),
        artifacts=approved,
    )
    strategy_input = materialized.case.strategy_input
    verified = strategy_input.verified_knowledge_input

    assert trade["mutations"] == []
    assert {field: trade_identity[field] for field in identity_fields} == {
        field: base_identity[field] for field in identity_fields
    }
    assert strategy_input.fixture_id == base_identity["fixture_id"]
    assert verified.input_id == base_identity["input_id"]
    assert verified.strategy_input_ref.dataset_release_id == base_identity["dataset_release_id"]
    assert approved_fixture_identity["fixture_id"] == strategy_input.fixture_id

    registry = load_stage2b_fixture_registry()
    trade_registration = next(
        record for record in registry.strategy_records if record.case_id == "SYN-TRADE-001"
    )
    assert trade_registration.fixture_id == strategy_input.fixture_id
    assert len({record.fixture_id for record in registry.strategy_records}) == 24
    for case in (*golden_cases, *boundary_cases):
        if case["case_id"] == "SYN-TRADE-001":
            continue
        explicit_identity = case.get("materialized_identity")
        if explicit_identity is not None:
            assert cast(dict[str, Any], explicit_identity) != trade_identity


def test_stage2b_base_uses_independent_public_evidence_chains() -> None:
    base = load_json_object(STAGE2B_BASE_PATH)
    chains = cast(list[dict[str, Any]], base["evidence_chains"])

    assert len(chains) == 2
    for field in (
        "source_document_id",
        "publisher_responsibility_id",
        "acquisition_chain_id",
    ):
        values = [chain[field] for chain in chains]
        assert len(values) == len(set(values))
    hashes = [cast(dict[str, str], chain["content_hash"])["value"] for chain in chains]
    assert len(hashes) == len(set(hashes))
    assert sum(chain["authoritative_original"] is True for chain in chains) >= 1
    assert all(chain["derived_from_source_document_id"] is None for chain in chains)
    assert all(chain["fact_ids"] and chain["evidence_ids"] for chain in chains)


def test_stage2b_business_decimals_are_exact_strings_not_json_numbers() -> None:
    base = load_json_object(STAGE2B_BASE_PATH)
    decimal_values: list[str] = []

    commercial = cast(dict[str, Any], base["commercial_event"])
    decimal_values.extend(
        cast(str, commercial[field])
        for field in (
            "profit_attribution_ratio",
            "seller_to_listed_company_ownership_ratio",
        )
    )
    minimum = cast(dict[str, Any], commercial["binding_minimum_contract_amount"])
    decimal_values.append(cast(str, minimum["amount"]))

    for section_name in ("profit_bridge_input", "valuation_input"):
        section = cast(dict[str, Any], base[section_name])
        for item in section.values():
            if not isinstance(item, dict):
                continue
            for field in ("amount", "value"):
                if field in item:
                    decimal_values.append(cast(str, item[field]))

    expectation = cast(dict[str, Any], base["expectation_snapshot"])
    decimal_values.append(cast(str, expectation["prior_expected_binding_minimum_amount"]))

    assert decimal_values
    assert all(isinstance(value, str) and _DECIMAL_RE.fullmatch(value) for value in decimal_values)


def test_stage2b_every_assumption_has_complete_point_in_time_audit_metadata() -> None:
    base = load_json_object(STAGE2B_BASE_PATH)
    clock = cast(dict[str, str], base["clock"])
    knowledge_cutoff = datetime.fromisoformat(clock["knowledge_cutoff"].replace("Z", "+00:00"))
    decision_at = datetime.fromisoformat(clock["decision_at"].replace("Z", "+00:00"))
    assumptions: list[tuple[str, dict[str, Any]]] = []

    for path, item in _classified_objects(base):
        classification = item["classification"]
        assert classification in {"Assumption", "Derived", "Fact", "Judgment"}
        if classification != "Assumption":
            assert "assumption_id" not in item, path
            continue
        assumptions.append((path, item))
        for field in ("assumption_id", "as_of", "scenario", "source_reason", "falsifier"):
            assert isinstance(item.get(field), str) and cast(str, item[field]).strip(), (
                path,
                field,
            )
        as_of = datetime.fromisoformat(cast(str, item["as_of"]).replace("Z", "+00:00"))
        assert as_of == knowledge_cutoff
        assert as_of <= decision_at
        assert item["scenario"] in {"base", "downside"}
        expected_section = (
            "§7.2_profit_bridge" if ".profit_bridge_input." in path else "§7.4_valuation"
        )
        assert cast(str, item["source_reason"]) == (
            f"approved_stage2b_synthetic_baseline:{expected_section}"
        )

    assert len(assumptions) == 13


def test_stage2b_blocked_vectors_are_physically_and_semantically_pre_admission() -> None:
    blocked = load_json_object(STAGE2B_BLOCKED_PATH)
    common = cast(dict[str, Any], blocked["expected_common"])
    cases = cast(list[dict[str, Any]], blocked["cases"])
    _golden_matrix, golden_cases = matrix_cases(STAGE2B_GOLDEN_PATH)
    _boundary_matrix, boundary_cases = matrix_cases(STAGE2B_BOUNDARY_PATH)

    assert common == {
        "decision_record_created": False,
        "decision_state": "BLOCKED",
        "normal_strategy_run_manifest_created": False,
        "run_failure_audit_required": True,
        "strategy_evaluator_calls": 0,
    }
    assert len(cases) == 10
    assert blocked["must_not_reuse_normal_fixture_identity"] is True
    assert STAGE2B_BLOCKED_PATH.parent.name == "failure-injection"
    assert STAGE2B_GOLDEN_PATH.parent.name == STAGE2B_BOUNDARY_PATH.parent.name == "normal"

    normal_text = json.dumps((*golden_cases, *boundary_cases), ensure_ascii=False)
    failure_identities: set[str] = set()
    for case in cases:
        failure_input = cast(dict[str, Any], case["failure_input"])
        assert case["expected_blocker_code"]
        assert case["failure_layer"]
        for field in ("dataset_release_id", "fixture_id", "input_id"):
            value = cast(str, failure_input[field])
            failure_identities.add(value)
            assert value not in normal_text
    assert len(failure_identities) == 3 * len(cases)


def test_stage2b_registry_artifact_exactly_matches_every_checked_in_vector() -> None:
    rebuilt = build_stage2b_fixture_registry()
    loaded = load_stage2b_fixture_registry()

    assert len(loaded.strategy_records) == 24
    assert len(loaded.failure_records) == 10
    assert loaded.snapshot_hash == rebuilt.snapshot_hash
    assert loaded.to_artifact_payload() == rebuilt.to_artifact_payload()


def test_stage2b_replay_matrix_names_the_complete_self_excluding_contract() -> None:
    replay = load_json_object(STAGE2B_REPLAY_PATH)
    relations = cast(list[dict[str, Any]], replay["relations"])

    assert replay["hash_contract"] == {
        "algorithm": "sha256",
        "canonical_profile": "investsystem-replay-v1",
        "digest_format": "64_lowercase_hex",
        "rule_bundle_hash_resolution": "trusted_approval_registry_at_test_time",
        "self_excluding": True,
    }
    assert set(cast(list[str], replay["required_components"])) == {
        "canonical_input_envelope_hash",
        "verified_input_hash",
        "approved_rule_bundle_hash",
        "rule_bundle_id",
        "rule_bundle_version",
        "rule_status",
        "strategy_id",
        "strategy_version",
        "code_commit",
        "config_hash",
        "runtime_environment_lock_hash",
        "run_mode",
        "random_seed",
        "evaluated_at",
        "synthetic_fixture_registration_id",
        "synthetic_fixture_registration_hash",
        "synthetic_fixture_registry_snapshot_hash",
        "deterministic_semantic_output",
    }
    assert len(relations) == 16
    assert {relation["expected_relation"] for relation in relations} == {
        "equal",
        "different",
        "rejected",
    }
    excluded = set(cast(list[str], replay["excluded_components"]))
    assert {"replay_hash", "run_id", "decision_id", "endpoint", "wall_clock"} <= excluded
