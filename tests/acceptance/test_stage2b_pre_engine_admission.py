from __future__ import annotations

import copy
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from invest_system.domain.synthetic_fixture import (
    SyntheticFixtureAuthorizationError,
    SyntheticFixtureRegistry,
)
from invest_system.strategies.industrial_event.admission import (
    Stage2BFailureInjectionRequest,
    Stage2BPreEngineAdmissionError,
    Stage2BRunFailureAudit,
    orchestrate_stage2b_failure_injection,
)
from stage2b_support import (
    STAGE2B_BLOCKED_PATH,
    ApprovedStage2BArtifacts,
    JsonObject,
    load_approved_stage2b_artifacts,
    load_json_object,
    load_stage2b_fixture_registry,
)

_BLOCKED_MATRIX = load_json_object(STAGE2B_BLOCKED_PATH)


def _load_blocked_cases() -> tuple[JsonObject, ...]:
    value = _BLOCKED_MATRIX["cases"]
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError("blocked cases must be an array of objects")
    return tuple(value)


_BLOCKED_CASES = _load_blocked_cases()
_FIXTURE_VERSION = "0.1.0"
_OBSERVED_AT = datetime(2026, 1, 6, 1, 40, tzinfo=UTC)


def _failure_payload(vector: Mapping[str, Any]) -> JsonObject:
    payload = vector["failure_input"]
    if not isinstance(payload, dict):
        raise TypeError("failure_input must be an object")
    return copy.deepcopy(cast(JsonObject, payload))


@pytest.fixture(scope="module")
def approved_artifacts() -> ApprovedStage2BArtifacts:
    return load_approved_stage2b_artifacts()


@pytest.fixture(scope="module")
def failure_registry() -> SyntheticFixtureRegistry:
    return load_stage2b_fixture_registry()


@pytest.mark.parametrize(
    "vector",
    _BLOCKED_CASES,
    ids=lambda vector: cast(dict[str, Any], vector)["case_id"],
)
def test_stage2b_registered_failure_is_audited_before_strategy_execution(
    vector: JsonObject,
    approved_artifacts: ApprovedStage2BArtifacts,
    failure_registry: SyntheticFixtureRegistry,
) -> None:
    evaluator_calls = 0
    persisted: list[Stage2BRunFailureAudit] = []

    def forbidden_strategy_evaluator() -> object:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("pre-engine failure must not invoke the strategy evaluator")

    request = Stage2BFailureInjectionRequest(
        failure_audit_id=f"audit_{str(vector['case_id']).lower()}",
        case_id=cast(str, vector["case_id"]),
        fixture_version=_FIXTURE_VERSION,
        observed_at=_OBSERVED_AT,
        failure_payload=_failure_payload(vector),
    )
    result = orchestrate_stage2b_failure_injection(
        request,
        registry=failure_registry,
        rule_document=approved_artifacts.document,
        approval_capability=approved_artifacts.capability,
        strategy_evaluator=forbidden_strategy_evaluator,
        failure_audit_sink=persisted.append,
    )
    audit = result.failure_audit

    assert evaluator_calls == result.strategy_evaluator_calls == 0
    assert result.strategy_run_manifest is None
    assert result.decision_record is None
    assert persisted == [audit]
    assert audit.case_id == vector["case_id"]
    assert audit.blocker_code.value == vector["expected_blocker_code"]
    assert audit.failure_layer.value == vector["failure_layer"]
    assert audit.decision_state.value == "BLOCKED"
    assert audit.strategy_evaluator_calls == 0
    assert audit.normal_strategy_run_manifest_created is False
    assert audit.decision_record_created is False
    assert audit.synthetic is True
    assert audit.validation_only is True
    assert audit.not_a_published_release is True
    assert audit.not_strategy_evidence is True
    assert audit.authorizes_positions is False
    assert audit.authorizes_orders is False
    assert audit.fixture_registry_snapshot_hash == failure_registry.snapshot_hash


def test_stage2b_tampered_failure_payload_has_no_strategy_capability(
    approved_artifacts: ApprovedStage2BArtifacts,
    failure_registry: SyntheticFixtureRegistry,
) -> None:
    vector = copy.deepcopy(_BLOCKED_CASES[0])
    payload = _failure_payload(vector)
    payload["actual_manifest_hash"] = "f" * 64
    evaluator_calls = 0

    def forbidden_strategy_evaluator() -> object:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("unregistered bytes must not invoke the strategy evaluator")

    request = Stage2BFailureInjectionRequest(
        failure_audit_id="audit_tampered_failure_payload_001",
        case_id=cast(str, vector["case_id"]),
        fixture_version=_FIXTURE_VERSION,
        observed_at=_OBSERVED_AT,
        failure_payload=payload,
    )

    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="FAILURE_INJECTION_FIXTURE_HASH_MISMATCH",
    ):
        orchestrate_stage2b_failure_injection(
            request,
            registry=failure_registry,
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            strategy_evaluator=forbidden_strategy_evaluator,
        )
    assert evaluator_calls == 0


def test_stage2b_unapproved_registry_snapshot_is_rejected_before_strategy_execution(
    approved_artifacts: ApprovedStage2BArtifacts,
) -> None:
    vector = _BLOCKED_CASES[0]
    evaluator_calls = 0

    def forbidden_strategy_evaluator() -> object:
        nonlocal evaluator_calls
        evaluator_calls += 1
        raise AssertionError("unapproved registry must not invoke the strategy evaluator")

    request = Stage2BFailureInjectionRequest(
        failure_audit_id="audit_unapproved_fixture_registry_001",
        case_id=cast(str, vector["case_id"]),
        fixture_version=_FIXTURE_VERSION,
        observed_at=_OBSERVED_AT,
        failure_payload=_failure_payload(vector),
    )

    with pytest.raises(
        Stage2BPreEngineAdmissionError,
        match="SYNTHETIC_FIXTURE_REGISTRY_NOT_APPROVED",
    ):
        orchestrate_stage2b_failure_injection(
            request,
            registry=SyntheticFixtureRegistry(),
            rule_document=approved_artifacts.document,
            approval_capability=approved_artifacts.capability,
            strategy_evaluator=forbidden_strategy_evaluator,
        )
    assert evaluator_calls == 0
