from __future__ import annotations

import copy
import re
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import pytest

from invest_system.canonical import canonical_sha256, to_json_value
from invest_system.domain.replay import ReplayEnvelope, compute_replay_hash
from invest_system.domain.synthetic_fixture import SyntheticFixtureAuthorizationError
from invest_system.models import (
    GateEvaluationState,
    HashDigest,
    PositionState,
    RunMode,
)
from invest_system.strategies.industrial_event import (
    CASE_MATERIAL_HASH_PREDICATE,
    COMPLETE_CASE_PAYLOAD_PREDICATE,
    IndustrialEventDecision,
    decimal_to_display_text,
    evaluate_industrial_event,
)
from stage2b_support import (
    STAGE2B_BOUNDARY_PATH,
    STAGE2B_GOLDEN_PATH,
    STAGE2B_REPLAY_PATH,
    ApprovedStage2BArtifacts,
    JsonObject,
    MaterializedStage2BCase,
    find_case,
    fixture_capability_for,
    load_approved_stage2b_artifacts,
    load_json_object,
    materialize_stage2b_case,
    matrix_cases,
    parse_utc,
    replace_json_pointer,
    replay_envelope_for_decision,
)

_GOLDEN_MATRIX, _GOLDEN_CASES = matrix_cases(STAGE2B_GOLDEN_PATH)
_BOUNDARY_MATRIX, _BOUNDARY_CASES = matrix_cases(STAGE2B_BOUNDARY_PATH)
_HEX_64 = re.compile(r"[0-9a-f]{64}")


@pytest.fixture(scope="module")
def approved_artifacts() -> ApprovedStage2BArtifacts:
    return load_approved_stage2b_artifacts()


def _evaluate(
    vector: JsonObject,
    approved: ApprovedStage2BArtifacts,
) -> tuple[MaterializedStage2BCase, IndustrialEventDecision]:
    materialized = materialize_stage2b_case(
        vector,
        artifacts=approved,
    )
    fixture_capability = fixture_capability_for(materialized)
    decision = evaluate_industrial_event(
        materialized.case,
        rule_document=approved.document,
        approval_capability=approved.capability,
        fixture_capability=fixture_capability,
    )
    return materialized, decision


def _fixture_identity_hashes(materialized: MaterializedStage2BCase) -> dict[str, Any]:
    case = materialized.case
    strategy_input = case.strategy_input
    verified = strategy_input.verified_knowledge_input
    return {
        "strategy_id": materialized.manifest.strategy_id,
        "case_id": case.case_id,
        "fixture_id": strategy_input.fixture_id,
        "fixture_version": strategy_input.fixture_version,
        "dataset_release_id": verified.strategy_input_ref.dataset_release_id,
        "input_id": verified.input_id,
        "input_envelope_hash": HashDigest(
            algorithm="sha256",
            value=strategy_input.canonical_sha256(),
        ),
        "verified_input_hash": strategy_input.fixture_payload_hash,
        "strategy_case_input_hash": case.semantic_input_hash(),
        "strategy_case_envelope_hash": HashDigest(
            algorithm="sha256",
            value=case.canonical_sha256(),
        ),
    }


def _assert_registered_capability_rejects_dynamic_case(
    registered: MaterializedStage2BCase,
    changed: MaterializedStage2BCase,
) -> None:
    capability = fixture_capability_for(registered)
    with pytest.raises(SyntheticFixtureAuthorizationError):
        capability.require_exact(**_fixture_identity_hashes(changed))
    with pytest.raises(SyntheticFixtureAuthorizationError):
        fixture_capability_for(changed)


def _replay_identity_variant_for_unregistered_input(
    baseline: ReplayEnvelope,
    changed: MaterializedStage2BCase,
) -> ReplayEnvelope:
    """Project changed hashes without issuing capability or invoking the engine."""

    hashes = _fixture_identity_hashes(changed)
    return replace(
        baseline,
        input_envelope_hash=cast(HashDigest, hashes["input_envelope_hash"]),
        verified_input_hash=cast(HashDigest, hashes["verified_input_hash"]),
        strategy_case_input_hash=cast(HashDigest, hashes["strategy_case_input_hash"]),
        strategy_case_envelope_hash=cast(
            HashDigest,
            hashes["strategy_case_envelope_hash"],
        ),
    )


def _assert_provenance_closure(materialized: MaterializedStage2BCase) -> None:
    strategy_input = materialized.case.strategy_input
    verified = strategy_input.verified_knowledge_input
    facts = {fact.fact_id: fact for fact in verified.facts}
    payload_fact = facts[materialized.primary_payload_fact_id]
    material_hash_fact = facts[materialized.material_hash_fact_id]

    assert payload_fact.predicate == COMPLETE_CASE_PAYLOAD_PREDICATE
    assert to_json_value(payload_fact.value) == materialized.complete_payload
    assert payload_fact.metadata["complete_case_payload_hash"] == canonical_sha256(
        materialized.complete_payload
    )
    assert materialized.complete_payload["case_input_schema_version"] == "0.1.0"
    assert materialized.complete_payload["raw_semantic_source"] == {
        key: materialized.source_document[key]
        for key in (
            "clock",
            "commercial_event",
            "evidence_chains",
            "expectation_snapshot",
            "profit_bridge_input",
            "valuation_input",
        )
    }
    assert materialized.complete_payload["strategy_case_payload"] == (materialized.semantic_payload)
    assert (
        canonical_sha256(materialized.complete_payload["strategy_case_payload"])
        == materialized.case.semantic_input_hash().value
    )
    assert material_hash_fact.predicate == CASE_MATERIAL_HASH_PREDICATE
    assert material_hash_fact.subject_id == materialized.case.case_id
    assert material_hash_fact.value == materialized.case.semantic_input_hash().value
    assert sum(fact.predicate == CASE_MATERIAL_HASH_PREDICATE for fact in facts.values()) == 1

    assert set(materialized.referenced_fact_ids) <= set(facts)
    all_bound_evidence = {
        evidence_id for fact in verified.facts for evidence_id in fact.evidence_ids
    }
    assert set(materialized.referenced_evidence_ids) <= all_bound_evidence
    for chain in materialized.case.commercial_event.evidence_chains:
        chain_bound_evidence = {
            evidence_id for fact_id in chain.fact_ids for evidence_id in facts[fact_id].evidence_ids
        }
        assert set(chain.evidence_ids) <= chain_bound_evidence

    assert strategy_input.synthetic is True
    assert strategy_input.validation_only is True
    assert strategy_input.not_a_published_release is True
    assert strategy_input.not_strategy_evidence is True
    assert strategy_input.authorizes_positions is False
    assert strategy_input.authorizes_orders is False
    assert all(fact.metadata["synthetic"] is True for fact in verified.facts)
    assert all(fact.metadata["not_a_published_release"] is True for fact in verified.facts)


def _assert_zero_authority(
    materialized: MaterializedStage2BCase,
    decision: IndustrialEventDecision,
    approved: ApprovedStage2BArtifacts,
) -> None:
    manifest = materialized.manifest

    assert decision.position_state is PositionState.FLAT
    assert decision.target_weight == decision.approved_weight == decision.actual_weight == "0"
    assert decision.approver is None
    assert decision.authorizes_positions is False
    assert decision.authorizes_orders is False
    assert decision.run_mode is RunMode.RESEARCH
    assert decision.validation_only is True

    assert manifest.synthetic is True
    assert manifest.validation_only is True
    assert manifest.input_path == "synthetic_validation"
    assert manifest.run_mode is RunMode.RESEARCH
    assert manifest.authorizes_positions is False
    assert manifest.authorizes_orders is False
    assert manifest.rule_bundle_hash == decision.rule_bundle_hash == approved.capability.bundle_hash
    assert manifest.rule_approval_id == decision.approval_id == approved.capability.approval_id
    assert manifest.rule_approval_record_hash == approved.capability.approval_record_hash
    assert manifest.rule_approval_scope == approved.capability.approval_scope.value
    assert manifest.strategy_case_input_hash == materialized.case.semantic_input_hash()
    assert manifest.input_envelope_hash == HashDigest(
        algorithm="sha256",
        value=materialized.case.strategy_input.canonical_sha256(),
    )
    assert manifest.strategy_case_envelope_hash == decision.strategy_case_envelope_hash
    assert decision.strategy_case_envelope_hash == HashDigest(
        algorithm="sha256",
        value=materialized.case.canonical_sha256(),
    )
    assert (
        manifest.synthetic_fixture_payload_hash
        == materialized.case.strategy_input.fixture_payload_hash
    )


def _assert_expected_gates(decision: IndustrialEventDecision, expected: JsonObject) -> None:
    expected_gates = cast(list[dict[str, Any]], expected["gate_results"])
    assert len(expected_gates) == len(decision.gate_results) == 4
    for actual, wanted in zip(decision.gate_results, expected_gates, strict=True):
        assert actual.gate_id.value == wanted["gate_id"]
        assert actual.evaluation_state.value == wanted["evaluation_state"]
        assert (actual.outcome.value if actual.outcome is not None else None) == wanted["outcome"]
        assert actual.rule_id == wanted["rule_id"]
        assert actual.rule_version == wanted["rule_version"]
        if "reason_codes" in wanted:
            assert actual.reason_codes == tuple(wanted["reason_codes"])
        if "short_circuit_reason_code" in wanted:
            assert actual.short_circuit_reason_code == wanted["short_circuit_reason_code"]


def _derived_value(decision: IndustrialEventDecision, field_name: str) -> str | None:
    if decision.profit_bridge is not None and hasattr(decision.profit_bridge, field_name):
        return cast(str | None, getattr(decision.profit_bridge, field_name))
    if decision.scenario_valuation is not None and hasattr(decision.scenario_valuation, field_name):
        return cast(str | None, getattr(decision.scenario_valuation, field_name))
    raise AssertionError(f"decision does not contain derived field {field_name!r}")


def _assert_decimal_equal(actual: str | None, expected: str | None) -> None:
    if expected is None:
        assert actual is None
    else:
        assert actual is not None
        assert Decimal(actual) == Decimal(expected)


def _assert_golden_derived(decision: IndustrialEventDecision, expected: JsonObject) -> None:
    derived = cast(dict[str, dict[str, Any]], expected["derived"])
    for field_name, wanted in derived.items():
        actual = _derived_value(decision, field_name)
        expected_raw = cast(str, wanted.get("raw", wanted.get("amount")))
        _assert_decimal_equal(actual, expected_raw)
        if "currency" in wanted:
            currency = (
                decision.profit_bridge.currency
                if decision.profit_bridge is not None
                and hasattr(decision.profit_bridge, field_name)
                else decision.scenario_valuation.currency
                if decision.scenario_valuation is not None
                else None
            )
            assert currency == wanted["currency"]
        if "display_6dp" in wanted:
            assert actual is not None
            assert decimal_to_display_text(Decimal(actual)) == wanted["display_6dp"]


@pytest.mark.parametrize(
    "vector",
    _GOLDEN_CASES,
    ids=lambda vector: cast(dict[str, Any], vector)["case_id"],
)
def test_stage2b_golden_matrix_executes_the_real_approved_engine(
    vector: JsonObject,
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    materialized, decision = _evaluate(vector, approved_artifacts)
    expected = cast(JsonObject, vector["expected"])

    _assert_provenance_closure(materialized)
    _assert_zero_authority(materialized, decision, approved_artifacts)
    _assert_expected_gates(decision, expected)
    _assert_golden_derived(decision, expected)

    assert decision.case_id == vector["case_id"]
    assert decision.event_state.value == expected["event_state"]
    assert decision.decision_state.value == expected["decision_state"]
    assert (
        decision.expectation_class.value if decision.expectation_class is not None else None
    ) == expected["expectation_class"]
    if "falsifiers" in expected:
        assert decision.falsifiers == tuple(sorted(cast(list[str], expected["falsifiers"])))

    replay = replay_envelope_for_decision(materialized, decision, approved_artifacts)
    assert replay.input_envelope_hash == materialized.manifest.input_envelope_hash
    assert replay.verified_input_hash == materialized.case.strategy_input.fixture_payload_hash
    assert replay.strategy_case_envelope_hash == decision.strategy_case_envelope_hash
    assert replay.strategy_case_input_hash == materialized.case.semantic_input_hash()
    assert replay.rule_bundle_id == approved_artifacts.document.bundle_id
    assert replay.rule_bundle_hash == approved_artifacts.capability.bundle_hash
    assert replay.rule_approval_id == approved_artifacts.capability.approval_id
    replay_hash = compute_replay_hash(replay)
    assert replay_hash.algorithm == "sha256"
    assert _HEX_64.fullmatch(replay_hash.value)
    assert expected["strategy_evaluator_calls"] == 1
    assert expected["strategy_run_manifest_created"] is True
    assert expected["decision_record_created"] is True


def _assert_boundary_derived(decision: IndustrialEventDecision, expected: JsonObject) -> None:
    derived = cast(dict[str, Any], expected.get("derived", {}))
    for key, wanted in derived.items():
        if key.endswith("_display_6dp"):
            field_name = key.removesuffix("_display_6dp")
            actual = _derived_value(decision, field_name)
            assert actual is not None
            assert decimal_to_display_text(Decimal(actual)) == wanted
        elif key.endswith("_raw"):
            _assert_decimal_equal(_derived_value(decision, key.removesuffix("_raw")), wanted)
        else:
            _assert_decimal_equal(_derived_value(decision, key), wanted)


@pytest.mark.parametrize(
    "vector",
    _BOUNDARY_CASES,
    ids=lambda vector: cast(dict[str, Any], vector)["case_id"],
)
def test_stage2b_boundary_matrix_uses_raw_decimal_and_fail_closed_semantics(
    vector: JsonObject,
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    materialized, decision = _evaluate(vector, approved_artifacts)
    expected = cast(JsonObject, vector["expected"])
    evaluated = tuple(
        gate
        for gate in decision.gate_results
        if gate.evaluation_state is GateEvaluationState.EVALUATED
    )
    terminal = evaluated[-1]

    _assert_provenance_closure(materialized)
    _assert_zero_authority(materialized, decision, approved_artifacts)
    _assert_boundary_derived(decision, expected)

    assert decision.decision_state.value == expected["decision_state"]
    assert terminal.gate_id.value == expected["terminal_gate"]
    assert terminal.outcome is not None
    assert terminal.outcome.value == expected["terminal_outcome"]
    if "event_state" in expected:
        assert decision.event_state.value == expected["event_state"]
    if "expectation_class" in expected:
        actual_class = (
            decision.expectation_class.value if decision.expectation_class is not None else None
        )
        assert actual_class == expected["expectation_class"]
    if "reason_code" in expected:
        assert terminal.reason_codes == (expected["reason_code"],)


def test_stage2b_repeat_run_is_byte_deterministic_and_independently_materialized(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(_GOLDEN_CASES, "SYN-TRADE-001")
    first_materialized, first_decision = _evaluate(vector, approved_artifacts)
    second_materialized, second_decision = _evaluate(vector, approved_artifacts)
    first_envelope = replay_envelope_for_decision(
        first_materialized, first_decision, approved_artifacts
    )
    second_envelope = replay_envelope_for_decision(
        second_materialized, second_decision, approved_artifacts
    )

    assert first_materialized is not second_materialized
    assert first_materialized.case is not second_materialized.case
    assert first_materialized.case.strategy_input is not second_materialized.case.strategy_input
    assert (
        first_materialized.case.strategy_input.verified_knowledge_input
        is not second_materialized.case.strategy_input.verified_knowledge_input
    )
    assert first_decision.to_canonical_bytes() == second_decision.to_canonical_bytes()
    assert first_envelope.to_canonical_bytes() == second_envelope.to_canonical_bytes()
    assert compute_replay_hash(first_envelope) == compute_replay_hash(second_envelope)


@pytest.mark.parametrize(
    ("pointer", "value", "typed_projection_unchanged"),
    (
        ("/commercial_event/seller_legal_entity_id", "SYN-SELLER-CHANGED-999", True),
        ("/commercial_event/security_id", "SYN-A-SHARE-CHANGED-999", True),
        ("/commercial_event/industry_slice", "changed_industry_slice", True),
        ("/commercial_event/profit_attribution_ratio", "0.5", True),
        (
            "/profit_bridge_input/incremental_gross_margin_rate/assumption_id",
            "SYN-ASSUMPTION-GROSS-MARGIN-CHANGED-999",
            True,
        ),
        (
            "/profit_bridge_input/incremental_gross_margin_rate/source_reason",
            "approved_stage2b_synthetic_baseline:changed_reason",
            True,
        ),
        ("/valuation_input/fully_diluted_shares/unit", "synthetic_share", True),
        (
            "/evidence_chains/1/derived_from_source_document_id",
            "SYN-DOCUMENT-UNRELATED-999",
            False,
        ),
    ),
)
def test_stage2b_complete_raw_business_payload_is_hash_material(
    pointer: str,
    value: Any,
    typed_projection_unchanged: bool,
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(_GOLDEN_CASES, "SYN-TRADE-001")
    baseline_materialized, baseline_decision = _evaluate(vector, approved_artifacts)
    changed_materialized = materialize_stage2b_case(
        vector,
        artifacts=approved_artifacts,
        additional_mutations=({"op": "replace", "path": pointer, "value": value},),
    )
    baseline_replay = replay_envelope_for_decision(
        baseline_materialized, baseline_decision, approved_artifacts
    )
    changed_replay_identity = _replay_identity_variant_for_unregistered_input(
        baseline_replay,
        changed_materialized,
    )

    _assert_registered_capability_rejects_dynamic_case(
        baseline_materialized,
        changed_materialized,
    )

    assert (
        baseline_materialized.case.strategy_input.fixture_payload_hash
        != changed_materialized.case.strategy_input.fixture_payload_hash
    )
    assert (
        baseline_materialized.case.strategy_input.canonical_sha256()
        != changed_materialized.case.strategy_input.canonical_sha256()
    )
    assert (
        baseline_materialized.case.canonical_sha256()
        != changed_materialized.case.canonical_sha256()
    )
    assert baseline_decision.strategy_case_envelope_hash != HashDigest(
        algorithm="sha256",
        value=changed_materialized.case.canonical_sha256(),
    )
    assert compute_replay_hash(baseline_replay) != compute_replay_hash(changed_replay_identity)
    assert (
        baseline_materialized.case.semantic_input_hash()
        == changed_materialized.case.semantic_input_hash()
    ) is typed_projection_unchanged


def test_stage2b_audit_only_identity_does_not_change_input_or_replay(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(_GOLDEN_CASES, "SYN-TRADE-001")
    baseline_materialized, baseline_decision = _evaluate(vector, approved_artifacts)
    changed_materialized = materialize_stage2b_case(
        vector,
        artifacts=approved_artifacts,
        audit_identity_overrides={
            "artifact_fetch_observation_id": "synthetic_fetch_stage2b_audit_999",
            "decision_id": "synthetic_decision_stage2b_audit_999",
            "release_admission_observation_id": "synthetic_admission_stage2b_audit_999",
            "release_status_observation_id": "synthetic_status_stage2b_audit_999",
            "run_id": "synthetic_run_stage2b_audit_999",
        },
    )
    changed_decision = evaluate_industrial_event(
        changed_materialized.case,
        rule_document=approved_artifacts.document,
        approval_capability=approved_artifacts.capability,
        fixture_capability=fixture_capability_for(changed_materialized),
    )
    baseline_replay = replay_envelope_for_decision(
        baseline_materialized, baseline_decision, approved_artifacts
    )
    changed_replay = replay_envelope_for_decision(
        changed_materialized, changed_decision, approved_artifacts
    )

    assert baseline_materialized.manifest.run_id != changed_materialized.manifest.run_id
    assert baseline_materialized.complete_payload == changed_materialized.complete_payload
    assert (
        baseline_materialized.case.strategy_input.to_canonical_bytes()
        == changed_materialized.case.strategy_input.to_canonical_bytes()
    )
    assert (
        baseline_materialized.case.to_canonical_bytes()
        == changed_materialized.case.to_canonical_bytes()
    )
    assert baseline_decision.to_canonical_bytes() == changed_decision.to_canonical_bytes()
    assert baseline_replay.to_canonical_bytes() == changed_replay.to_canonical_bytes()
    assert compute_replay_hash(baseline_replay) == compute_replay_hash(changed_replay)


def test_stage2b_gate2_uses_more_than_one_hundred_digits_without_display_rounding(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(
        _BOUNDARY_CASES,
        "SYN-G2-BELOW-DISPLAY-EQUAL-PRECISION-001",
    )
    mutations = cast(list[dict[str, Any]], vector["mutations"])
    operating_expense = cast(str, mutations[0]["value"])
    _materialized, decision = _evaluate(vector, approved_artifacts)
    gate_2 = decision.gate_results[1]

    assert len(Decimal(operating_expense).as_tuple().digits) > 100
    assert decision.decision_state.value == "REJECT"
    assert gate_2.outcome is not None and gate_2.outcome.value == "REJECT"
    assert gate_2.reason_codes == ("profit_materiality_below_threshold",)
    assert decision.profit_bridge is not None
    assert decision.profit_bridge.profit_materiality is not None
    raw = Decimal(decision.profit_bridge.profit_materiality)
    assert raw < Decimal("0.10")
    assert decimal_to_display_text(raw) == "0.100000"


def test_stage2b_gate4_uses_more_than_one_hundred_digits_without_display_rounding(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(
        _BOUNDARY_CASES,
        "SYN-G4-BELOW-DISPLAY-EQUAL-PRECISION-001",
    )
    mutations = cast(list[dict[str, Any]], vector["mutations"])
    base_business_value = cast(str, mutations[0]["value"])
    _materialized, decision = _evaluate(vector, approved_artifacts)
    gate_4 = decision.gate_results[3]

    assert len(Decimal(base_business_value).as_tuple().digits) > 100
    assert decision.decision_state.value == "REJECT"
    assert gate_4.outcome is not None and gate_4.outcome.value == "REJECT"
    assert gate_4.reason_codes == ("executable_return_below_threshold",)
    assert decision.scenario_valuation is not None
    raw = Decimal(decision.scenario_valuation.net_base_remaining_return)
    assert raw < Decimal("0.15")
    assert decimal_to_display_text(raw) == "0.150000"


def _semantic_variant(
    baseline: ReplayEnvelope,
    pointer: str,
    value: Any,
) -> ReplayEnvelope:
    projected = to_json_value(baseline.semantic_output)
    if not isinstance(projected, dict):
        raise TypeError("replay semantic output must project to an object")
    output = copy.deepcopy(cast(dict[str, Any], projected))
    if pointer == "/replay_hash":
        output["replay_hash"] = value
    elif pointer == "/transport/endpoint":
        output["transport"] = {"endpoint": value}
    else:
        replace_json_pointer(output, pointer, value)
    return replace(baseline, semantic_output=output)


def _relation_envelope(
    relation: JsonObject,
    *,
    vector: JsonObject,
    baseline_materialized: MaterializedStage2BCase,
    baseline_decision: IndustrialEventDecision,
    baseline_envelope: ReplayEnvelope,
    approved: ApprovedStage2BArtifacts,
) -> ReplayEnvelope:
    mutations = cast(list[dict[str, Any]], relation["mutations"])
    if not mutations:
        materialized, decision = _evaluate(vector, approved)
        return replay_envelope_for_decision(materialized, decision, approved)

    components = {mutation["component"] for mutation in mutations}
    if components == {"audit_only"}:
        manifest_changes: dict[str, Any] = {}
        audit_field_map = {
            "run_id": "run_id",
            "artifact_fetch_observation_id": "artifact_fetch_observation_id",
            "release_status_observation_id": "release_status_observation_id",
            "release_admission_observation_id": "release_admission_observation_id",
        }
        for mutation in mutations:
            field = cast(str, mutation["field"])
            if field in audit_field_map:
                manifest_changes[audit_field_map[field]] = mutation["value"]
            elif field == "wall_clock":
                manifest_changes["created_at"] = parse_utc(cast(str, mutation["value"]))
            elif field not in {"decision_id", "temporary_path"}:
                raise AssertionError(f"unknown audit-only replay field {field!r}")
        changed_manifest = replace(baseline_materialized.manifest, **manifest_changes)
        return replay_envelope_for_decision(
            baseline_materialized,
            baseline_decision,
            approved,
            manifest=changed_manifest,
        )
    if components == {"canonical_input"}:
        pointer_mutations = tuple(
            {
                "op": "replace",
                "path": mutation["field"],
                "value": mutation["value"],
            }
            for mutation in mutations
        )
        materialized = materialize_stage2b_case(
            vector,
            artifacts=approved,
            additional_mutations=pointer_mutations,
        )
        _assert_registered_capability_rejects_dynamic_case(
            baseline_materialized,
            materialized,
        )
        return _replay_identity_variant_for_unregistered_input(
            baseline_envelope,
            materialized,
        )
    if components == {"rule_identity"}:
        changes: dict[str, Any] = {}
        for mutation in mutations:
            field = cast(str, mutation["field"])
            changes[field] = (
                HashDigest(algorithm="sha256", value=cast(str, mutation["value"]))
                if field == "rule_bundle_hash"
                else mutation["value"]
            )
        return replace(baseline_envelope, **changes)
    if components == {"fixture_authorization"}:
        changes = {}
        fixture_hash_fields = {
            "synthetic_fixture_registration_hash",
            "synthetic_fixture_registry_snapshot_hash",
        }
        for mutation in mutations:
            field = cast(str, mutation["field"])
            value = mutation["value"]
            if field in fixture_hash_fields:
                value = HashDigest(algorithm="sha256", value=cast(str, value))
            changes[field] = value
        return replace(baseline_envelope, **changes)
    if components == {"strategy_identity"}:
        changes = {}
        for mutation in mutations:
            field = cast(str, mutation["field"])
            value = mutation["value"]
            if field in {"config_hash", "runtime_environment_lock_hash"}:
                value = HashDigest(algorithm="sha256", value=cast(str, value))
            elif field == "evaluated_at":
                value = parse_utc(cast(str, value))
            changes[field] = value
        return replace(baseline_envelope, **changes)
    if components == {"semantic_output"} and len(mutations) == 1:
        mutation = mutations[0]
        return _semantic_variant(
            baseline_envelope,
            cast(str, mutation["field"]),
            mutation["value"],
        )
    raise AssertionError(f"unsupported replay relation components: {sorted(components)}")


def test_stage2b_replay_relation_matrix_is_executable(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    replay_matrix = load_json_object(STAGE2B_REPLAY_PATH)
    vector = find_case(_GOLDEN_CASES, cast(str, replay_matrix["baseline_case_ref"]))
    baseline_materialized, baseline_decision = _evaluate(vector, approved_artifacts)
    baseline_envelope = replay_envelope_for_decision(
        baseline_materialized,
        baseline_decision,
        approved_artifacts,
    )
    baseline_hash = compute_replay_hash(baseline_envelope)

    for relation in cast(list[JsonObject], replay_matrix["relations"]):
        expected = relation["expected_relation"]
        if expected == "rejected":
            with pytest.raises(ValueError, match="reserved replay key"):
                _relation_envelope(
                    relation,
                    vector=vector,
                    baseline_materialized=baseline_materialized,
                    baseline_decision=baseline_decision,
                    baseline_envelope=baseline_envelope,
                    approved=approved_artifacts,
                )
            continue

        variant = _relation_envelope(
            relation,
            vector=vector,
            baseline_materialized=baseline_materialized,
            baseline_decision=baseline_decision,
            baseline_envelope=baseline_envelope,
            approved=approved_artifacts,
        )
        variant_hash = compute_replay_hash(variant)
        if expected == "equal":
            assert variant_hash == baseline_hash, relation["relation_id"]
        else:
            assert variant_hash != baseline_hash, relation["relation_id"]


def test_stage2b_explicit_evaluation_clock_is_replay_material(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = find_case(_GOLDEN_CASES, "SYN-TRADE-001")
    materialized, decision = _evaluate(vector, approved_artifacts)
    baseline = replay_envelope_for_decision(materialized, decision, approved_artifacts)
    changed = replay_envelope_for_decision(
        materialized,
        decision,
        approved_artifacts,
        evaluated_at=decision.decision_at + timedelta(microseconds=1),
    )

    assert compute_replay_hash(changed) != compute_replay_hash(baseline)
