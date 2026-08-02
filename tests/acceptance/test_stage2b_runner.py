from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, cast

import pytest

import invest_system.strategies.industrial_event.runner as runner_module
from invest_system.canonical import canonical_sha256
from invest_system.domain.replay import compute_replay_hash
from invest_system.models import HashDigest, PositionState, RunMode
from invest_system.strategies.industrial_event import (
    CASE_MATERIAL_HASH_PREDICATE,
    COMPLETE_CASE_PAYLOAD_PREDICATE,
    INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256,
    STAGE2B_NON_TRADE_DECLARATION,
    Stage2BResearchValidationError,
    Stage2BResearchValidationResult,
    run_stage2b_research_validation,
)
from stage2b_support import (
    STAGE2B_BOUNDARY_PATH,
    STAGE2B_GOLDEN_PATH,
    ApprovedStage2BArtifacts,
    JsonObject,
    MaterializedStage2BCase,
    fixture_capability_for,
    load_approved_stage2b_artifacts,
    materialize_stage2b_case,
    matrix_cases,
)

_GOLDEN_MATRIX, _GOLDEN_CASES = matrix_cases(STAGE2B_GOLDEN_PATH)
_BOUNDARY_MATRIX, _BOUNDARY_CASES = matrix_cases(STAGE2B_BOUNDARY_PATH)
_ALL_NORMAL_CASES = (*_GOLDEN_CASES, *_BOUNDARY_CASES)


@pytest.fixture(scope="module")
def approved_artifacts() -> ApprovedStage2BArtifacts:
    return load_approved_stage2b_artifacts()


def _decision_id(materialized: MaterializedStage2BCase) -> str:
    run_identity = cast(dict[str, Any], materialized.source_document["run_identity"])
    audit_ids = cast(dict[str, Any], run_identity["audit_only_ids"])
    return cast(str, audit_ids["decision_id"])


def _classification_count(value: Any, classification: str) -> int:
    if isinstance(value, Mapping):
        return int(value.get("classification") == classification) + sum(
            _classification_count(item, classification) for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return sum(_classification_count(item, classification) for item in value)
    return 0


def _run(
    vector: JsonObject,
    approved: ApprovedStage2BArtifacts,
) -> tuple[MaterializedStage2BCase, Stage2BResearchValidationResult]:
    materialized = materialize_stage2b_case(vector, artifacts=approved)
    result = run_stage2b_research_validation(
        decision_id=_decision_id(materialized),
        manifest=materialized.manifest,
        case=materialized.case,
        rule_document=approved.document,
        approval_capability=approved.capability,
        fixture_capability=fixture_capability_for(materialized),
    )
    return materialized, result


@pytest.mark.parametrize(
    "vector",
    _ALL_NORMAL_CASES,
    ids=lambda vector: cast(dict[str, Any], vector)["case_id"],
)
def test_stage2b_runner_closes_every_registered_normal_case_end_to_end(
    vector: JsonObject,
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evaluator_calls = 0
    evaluator = runner_module.evaluate_industrial_event

    def counting_evaluator(*args: Any, **kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        return evaluator(*args, **kwargs)

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", counting_evaluator)
    materialized, result = _run(vector, approved_artifacts)
    decision = result.strategy_decision
    replay = result.replay_envelope
    record = result.decision_record
    fixture_capability = fixture_capability_for(materialized)

    assert evaluator_calls == result.strategy_evaluator_calls == 1
    assert record.run_id == materialized.manifest.run_id
    assert record.decision_at == decision.decision_at == materialized.case.decision_at
    assert record.event_state is decision.event_state
    assert record.decision_state is decision.decision_state
    assert record.gate_results == decision.gate_results
    assert record.replay_hash == compute_replay_hash(replay)
    assert canonical_sha256(replay.semantic_output) == canonical_sha256(decision.to_json_value())
    assert replay.input_envelope_hash == materialized.manifest.input_envelope_hash
    assert replay.strategy_case_input_hash == materialized.manifest.strategy_case_input_hash
    assert (
        replay.strategy_case_envelope_hash
        == materialized.manifest.strategy_case_envelope_hash
        == decision.strategy_case_envelope_hash
    )
    assert replay.synthetic_fixture_registration_id == fixture_capability.registration_id
    assert replay.synthetic_fixture_registration_hash == fixture_capability.registration_hash
    assert replay.synthetic_fixture_registry_snapshot_hash.value == (
        INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256
    )

    binding_predicates = {
        fact.fact_id: fact.predicate
        for fact in materialized.case.strategy_input.verified_knowledge_input.facts
        if fact.predicate in {COMPLETE_CASE_PAYLOAD_PREDICATE, CASE_MATERIAL_HASH_PREDICATE}
    }
    assert set(binding_predicates) <= set(record.facts_used)
    assert len(record.assumptions) == _classification_count(
        materialized.source_document,
        "Assumption",
    )
    if materialized.case.case_id == "SYN-TRADE-001":
        assert len(record.assumptions) == 13
    assumption_ids: set[str] = set()
    for item in record.assumptions:
        assert isinstance(item, Mapping)
        assumption = item["value"]
        assert isinstance(assumption, Mapping)
        assert assumption["classification"] == "Assumption"
        for field_name in (
            "assumption_id",
            "as_of",
            "scenario",
            "source_reason",
            "falsifier",
        ):
            assert isinstance(assumption[field_name], str)
            assert cast(str, assumption[field_name]).strip()
        assumption_ids.add(cast(str, assumption["assumption_id"]))
    assert len(assumption_ids) == len(record.assumptions)

    rule_judgment = cast(Mapping[str, Any], record.judgments[-1])
    assert rule_judgment["classification"] == "Judgment"
    gate_outcomes = cast(tuple[Mapping[str, Any], ...], rule_judgment["gate_outcomes"])
    assert len(gate_outcomes) == 4
    assert all(
        set(gate_outcome)
        == {
            "gate_id",
            "evaluation_state",
            "outcome",
            "rule_id",
            "rule_version",
            "reason_codes",
            "short_circuit_reason_code",
        }
        for gate_outcome in gate_outcomes
    )
    assert record.derived_values["synthetic_fixture_registration_id"] == (
        fixture_capability.registration_id
    )
    assert record.derived_values["synthetic_fixture_registry_snapshot_hash"] == (
        fixture_capability.registry_snapshot_hash.to_json_value()
    )


def test_stage2b_runner_accepts_assumption_as_of_equal_to_knowledge_cutoff(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    materialized, result = _run(_GOLDEN_CASES[0], approved_artifacts)
    cutoff = materialized.case.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff

    for item in result.decision_record.assumptions:
        assumption = cast(Mapping[str, Any], cast(Mapping[str, Any], item)["value"])
        assert assumption["as_of"] == cutoff.isoformat(timespec="microseconds").replace(
            "+00:00", "Z"
        )


@pytest.mark.parametrize(
    "vector",
    _ALL_NORMAL_CASES,
    ids=lambda vector: cast(dict[str, Any], vector)["case_id"],
)
def test_stage2b_runner_never_crosses_the_research_non_trade_boundary(
    vector: JsonObject,
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    _materialized, result = _run(vector, approved_artifacts)

    for artifact in (result.strategy_decision, result.decision_record):
        assert artifact.synthetic is True
        assert artifact.validation_only is True
        assert artifact.run_mode is RunMode.RESEARCH
        assert artifact.position_state is PositionState.FLAT
        assert artifact.target_weight == "0"
        assert artifact.approved_weight == "0"
        assert artifact.actual_weight == "0"
        assert artifact.approver is None
        assert artifact.authorizes_positions is False
        assert artifact.authorizes_orders is False
    assert result.decision_record.not_a_published_release is True
    assert result.decision_record.not_strategy_evidence is True
    assert result.decision_record.non_trade_declaration == STAGE2B_NON_TRADE_DECLARATION
    assert "stage2b_synthetic_research_validation_only" in (result.decision_record.block_reasons)


def test_stage2b_runner_rejects_a_manifest_with_any_case_identity_drift(
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialized = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    mismatched_manifest = replace(
        materialized.manifest,
        input_envelope_hash=HashDigest(algorithm="sha256", value="f" * 64),
    )

    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(
        Stage2BResearchValidationError,
        match="MANIFEST_FIXTURE_IDENTITY_MISMATCH",
    ):
        run_stage2b_research_validation(
            decision_id=_decision_id(materialized),
            manifest=mismatched_manifest,
            case=materialized.case,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(materialized),
        )
    assert evaluator_calls == 0


@pytest.mark.parametrize(
    ("field_name", "value", "expected_code"),
    (
        (
            "artifact_consumption_receipt_hash",
            HashDigest(algorithm="sha256", value="e" * 64),
            "MANIFEST_SYNTHETIC_RECEIPT_MISMATCH",
        ),
        (
            "artifact_fetch_observation_id",
            "published_fetch_observation_001",
            "MANIFEST_SYNTHETIC_AUDIT_IDENTITY_INVALID",
        ),
        (
            "release_status_observation_id",
            "published_status_observation_001",
            "MANIFEST_SYNTHETIC_AUDIT_IDENTITY_INVALID",
        ),
        (
            "release_admission_observation_id",
            "published_admission_observation_001",
            "MANIFEST_SYNTHETIC_AUDIT_IDENTITY_INVALID",
        ),
    ),
)
def test_stage2b_runner_rejects_synthetic_manifest_audit_drift_before_evaluation(
    field_name: str,
    value: Any,
    expected_code: str,
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialized = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    manifest = replace(materialized.manifest, **{field_name: value})
    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(Stage2BResearchValidationError, match=expected_code):
        run_stage2b_research_validation(
            decision_id=_decision_id(materialized),
            manifest=manifest,
            case=materialized.case,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(materialized),
        )
    assert evaluator_calls == 0


def test_stage2b_runner_rejects_invalid_decision_id_before_evaluation(
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialized = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(Stage2BResearchValidationError, match="DECISION_ID_INVALID"):
        run_stage2b_research_validation(
            decision_id="invalid decision id",
            manifest=materialized.manifest,
            case=materialized.case,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(materialized),
        )
    assert evaluator_calls == 0


def test_stage2b_runner_rejects_a_capability_from_another_case_before_evaluation(
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialized = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    other = materialize_stage2b_case(_GOLDEN_CASES[1], artifacts=approved_artifacts)
    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(
        Stage2BResearchValidationError,
        match="SYNTHETIC_FIXTURE_IDENTITY_MISMATCH",
    ):
        run_stage2b_research_validation(
            decision_id=_decision_id(materialized),
            manifest=materialized.manifest,
            case=materialized.case,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(other),
        )
    assert evaluator_calls == 0


def test_stage2b_runner_rejects_rule_semantic_drift_before_evaluation(
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    materialized = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    changed_rules = dict(approved_artifacts.document.rules)
    changed_rules["approval_items"] = ()
    changed_document = replace(approved_artifacts.document, rules=changed_rules)
    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(Stage2BResearchValidationError, match="RULE_HASH_MISMATCH"):
        run_stage2b_research_validation(
            decision_id=_decision_id(materialized),
            manifest=materialized.manifest,
            case=materialized.case,
            rule_document=changed_document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(materialized),
        )
    assert evaluator_calls == 0


@pytest.mark.parametrize(
    ("path", "value", "expected_code"),
    (
        (
            "/profit_bridge_input/incremental_gross_margin_rate/as_of",
            "2026-01-06T01:35:00.000001Z",
            "ASSUMPTION_AS_OF_AFTER_KNOWLEDGE_CUTOFF",
        ),
        (
            "/profit_bridge_input/incremental_gross_margin_rate/as_of",
            "2026-02-30T01:35:00.000000Z",
            "ASSUMPTION_AS_OF_INVALID",
        ),
        (
            "/profit_bridge_input/incremental_gross_margin_rate/classification",
            None,
            "AUDIT_CLASSIFICATION_INVALID",
        ),
    ),
)
def test_stage2b_runner_rejects_invalid_assumption_audit_before_evaluation(
    path: str,
    value: Any,
    expected_code: str,
    approved_artifacts: ApprovedStage2BArtifacts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approved_case = materialize_stage2b_case(
        _GOLDEN_CASES[0],
        artifacts=approved_artifacts,
    )
    changed = materialize_stage2b_case(
        _GOLDEN_CASES[0],
        artifacts=approved_artifacts,
        additional_mutations=(
            {
                "op": "replace",
                "path": path,
                "value": value,
            },
        ),
    )
    evaluator_calls = 0

    def forbidden_evaluator(*_args: Any, **_kwargs: Any) -> Any:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine rejection must not invoke the evaluator")

    monkeypatch.setattr(runner_module, "evaluate_industrial_event", forbidden_evaluator)
    with pytest.raises(Stage2BResearchValidationError, match=expected_code):
        run_stage2b_research_validation(
            decision_id=_decision_id(changed),
            manifest=changed.manifest,
            case=changed.case,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            fixture_capability=fixture_capability_for(approved_case),
        )
    assert evaluator_calls == 0


def test_stage2b_runner_replay_excludes_audit_only_manifest_identities(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    first = materialize_stage2b_case(_GOLDEN_CASES[0], artifacts=approved_artifacts)
    second = materialize_stage2b_case(
        _GOLDEN_CASES[0],
        artifacts=approved_artifacts,
        audit_identity_overrides={
            "run_id": "synthetic_run_stage2b_retry_999",
            "decision_id": "synthetic_decision_stage2b_retry_999",
            "artifact_fetch_observation_id": "synthetic_fetch_stage2b_retry_999",
            "release_status_observation_id": "synthetic_status_stage2b_retry_999",
            "release_admission_observation_id": "synthetic_admission_stage2b_retry_999",
        },
    )
    first_result = run_stage2b_research_validation(
        decision_id=_decision_id(first),
        manifest=first.manifest,
        case=first.case,
        rule_document=approved_artifacts.document,
        approval_capability=approved_artifacts.capability,
        fixture_capability=fixture_capability_for(first),
    )
    second_result = run_stage2b_research_validation(
        decision_id=_decision_id(second),
        manifest=second.manifest,
        case=second.case,
        rule_document=approved_artifacts.document,
        approval_capability=approved_artifacts.capability,
        fixture_capability=fixture_capability_for(second),
    )

    assert first.manifest.run_id != second.manifest.run_id
    assert _decision_id(first) != _decision_id(second)
    assert first_result.replay_envelope == second_result.replay_envelope
    assert first_result.decision_record.replay_hash == second_result.decision_record.replay_hash
    assert first_result.decision_record.run_id == first.manifest.run_id
    assert second_result.decision_record.run_id == second.manifest.run_id
