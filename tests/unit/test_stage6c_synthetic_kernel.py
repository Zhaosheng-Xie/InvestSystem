from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, getcontext
from pathlib import Path
from typing import Any, cast

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event import (
    STAGE6C_DECIMAL_CONTEXT_ID,
    STAGE6C_HOLDOUT_END_EXCLUSIVE,
    STAGE6C_HOLDOUT_START,
    STAGE6C_KNOWLEDGE_CUTOFF_CAP,
    Stage6CDailyNavPoint,
    Stage6CDevelopmentProjection,
    Stage6CHoldoutIsolationEvidence,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelStatus,
    Stage6DHoldoutCommitment,
    evaluate_stage6c_synthetic_twr_kernel,
    require_stage6b_admission_validation_capability,
    require_stage6c_kernel_validation_capability,
)

MACHINE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
STAGE6C_BUNDLE = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.rule-bundle.json"
)
STAGE6C_APPROVAL = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.approval.json"
)
STAGE6B_BUNDLE = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.rule-bundle.json"
)
STAGE6B_APPROVAL = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6b_historical_admission_atomic_retention_v0.1.0.approval.json"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value * 64)


def _capability(repository_root: Path) -> Any:
    document = rule_bundle_document_from_json_value(_json(repository_root / STAGE6C_BUNDLE))
    approval = rule_approval_record_from_json_value(_json(repository_root / STAGE6C_APPROVAL))
    return require_stage6c_kernel_validation_capability(
        document, registry=RuleApprovalRegistry((approval,))
    )


def _nav_points() -> tuple[Stage6CDailyNavPoint, ...]:
    start = date(2020, 1, 1)
    points: list[Stage6CDailyNavPoint] = []
    for index in range(253):
        points.append(
            Stage6CDailyNavPoint(
                session_index=index,
                session_date=(start + timedelta(days=index)).isoformat(),
                strategy_nav="200000" if index == 252 else "100000",
                benchmark_nav="100000",
            )
        )
    return tuple(points)


def _case(
    *,
    source_hash: HashDigest | None = None,
    commitment_source_hash: HashDigest | None = None,
    access: bool = False,
    mounted: bool = False,
    canary_denied: bool = True,
    read_count: int = 0,
    nav_points: tuple[Stage6CDailyNavPoint, ...] | None = None,
    projection_boundary: datetime = STAGE6C_HOLDOUT_START,
    holdout_start: datetime = STAGE6C_HOLDOUT_START,
) -> Stage6CSyntheticKernelCase:
    closure = source_hash or _digest("1")
    commitment_closure = commitment_source_hash or closure
    projection = Stage6CDevelopmentProjection.create(
        projection_id="stage6c_projection_fixture_001",
        source_release_closure_hash=closure,
        projection_rule_hash=_digest("2"),
        generation_code_hash=_digest("3"),
        generation_config_hash=_digest("4"),
        decision_time_exclusive=projection_boundary,
    )
    commitment = Stage6DHoldoutCommitment.create(
        commitment_id="stage6d_holdout_commitment_fixture_001",
        holdout_start_inclusive=holdout_start,
        holdout_end_exclusive=STAGE6C_HOLDOUT_END_EXCLUSIVE,
        knowledge_cutoff_cap=STAGE6C_KNOWLEDGE_CUTOFF_CAP,
        source_release_closure_hash=commitment_closure,
        opaque_holdout_artifact_commitment=_digest("5"),
        custodian_id="stage6c_synthetic_custodian",
        generation_code_hash=_digest("6"),
        generation_config_hash=_digest("7"),
        sealed_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    evidence = Stage6CHoldoutIsolationEvidence.create(
        evidence_id="stage6c_isolation_fixture_001",
        projection_hash=projection.projection_hash,
        commitment_hash=commitment.commitment_hash,
        development_namespace_id="synthetic_development_namespace",
        holdout_namespace_id="synthetic_holdout_namespace",
        process_has_holdout_read_access=access,
        holdout_mounted_or_linked=mounted,
        canary_read_denied=canary_denied,
        holdout_read_count=read_count,
        checked_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    return Stage6CSyntheticKernelCase.create(
        case_id="stage6c_synthetic_twr_case_001",
        projection=projection,
        holdout_commitment=commitment,
        isolation_evidence=evidence,
        nav_points=nav_points or _nav_points(),
    )


def test_stage6c_synthetic_kernel_reconciles_exact_twr_and_is_deterministic(
    repository_root: Path,
) -> None:
    case = _case()
    capability = _capability(repository_root)

    first = evaluate_stage6c_synthetic_twr_kernel(case, capability=capability)
    second = evaluate_stage6c_synthetic_twr_kernel(case, capability=capability)

    assert first == second
    assert first.status is Stage6CSyntheticKernelStatus.TWR_RECONCILED
    assert first.session_count == 252
    assert first.gross_excess_factor == "2"
    assert first.annualized_net_excess_percentage_points == "100"
    assert first.daily_excess_factors.count("1") == 251
    assert first.daily_excess_factors[-1] == "2"
    assert first.failure_reasons == ()
    assert first.decimal_context_id == STAGE6C_DECIMAL_CONTEXT_ID
    assert first.not_a_complete_stage6c_walk_forward is True
    assert first.formal_historical_run is False
    assert first.holdout_artifact_read is False
    assert first.persists_state is False
    assert first.authority_eligible is False


def test_stage6c_synthetic_kernel_is_independent_of_ambient_decimal_context(
    repository_root: Path,
) -> None:
    case = _case()
    capability = _capability(repository_root)
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        getcontext().prec = 6
        getcontext().rounding = ROUND_DOWN
        changed = evaluate_stage6c_synthetic_twr_kernel(case, capability=capability)
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding
    baseline = evaluate_stage6c_synthetic_twr_kernel(case, capability=capability)
    assert changed == baseline


@pytest.mark.parametrize(
    ("overrides", "reason"),
    (
        ({"access": True}, "HOLDOUT_READ_ACCESS_PRESENT"),
        ({"mounted": True}, "HOLDOUT_MOUNTED_OR_LINKED"),
        ({"canary_denied": False}, "HOLDOUT_CANARY_NOT_DENIED"),
        ({"read_count": 1}, "HOLDOUT_READ_COUNT_NONZERO"),
        (
            {"source_hash": _digest("1"), "commitment_source_hash": _digest("8")},
            "SOURCE_CLOSURE_MISMATCH",
        ),
    ),
)
def test_stage6c_synthetic_kernel_blocks_isolation_failures_without_partial_twr(
    repository_root: Path,
    overrides: dict[str, Any],
    reason: str,
) -> None:
    result = evaluate_stage6c_synthetic_twr_kernel(
        _case(**overrides), capability=_capability(repository_root)
    )

    assert result.status is Stage6CSyntheticKernelStatus.PRECHECK_BLOCKED
    assert reason in result.failure_reasons
    assert result.session_count == 0
    assert result.daily_excess_factors == ()
    assert result.gross_excess_factor is None
    assert result.annualized_net_excess_percentage_points is None
    assert result.authority_eligible is False


def test_stage6c_synthetic_kernel_rejects_another_stage_capability(
    repository_root: Path,
) -> None:
    document = rule_bundle_document_from_json_value(_json(repository_root / STAGE6B_BUNDLE))
    approval = rule_approval_record_from_json_value(_json(repository_root / STAGE6B_APPROVAL))
    stage6b = require_stage6b_admission_validation_capability(
        document, registry=RuleApprovalRegistry((approval,))
    )

    with pytest.raises(ValueError, match="exact approved Stage 6C capability"):
        evaluate_stage6c_synthetic_twr_kernel(_case(), capability=stage6b)


def test_stage6c_synthetic_kernel_rejects_mutually_consistent_unapproved_boundary(
    repository_root: Path,
) -> None:
    drifted = datetime(2026, 1, 2, tzinfo=UTC)
    result = evaluate_stage6c_synthetic_twr_kernel(
        _case(projection_boundary=drifted, holdout_start=drifted),
        capability=_capability(repository_root),
    )

    assert result.status is Stage6CSyntheticKernelStatus.PRECHECK_BLOCKED
    assert result.failure_reasons == ("HOLDOUT_BOUNDARY_NOT_APPROVED",)
    assert result.gross_excess_factor is None


def test_stage6c_synthetic_contracts_reject_holdout_or_authority_claims() -> None:
    case = _case()
    with pytest.raises(ValueError, match="holdout information"):
        replace(
            case.projection,
            contains_holdout_records=True,
            projection_hash=case.projection.projection_hash,
        )
    with pytest.raises(ValueError, match="cannot read holdout"):
        replace(case, holdout_artifact_read=True, case_hash=case.case_hash)
    with pytest.raises(TypeError, match="must be bool"):
        replace(
            case.isolation_evidence,
            canary_read_denied=cast(Any, 1),
            evidence_hash=case.isolation_evidence.evidence_hash,
        )


def test_stage6c_synthetic_kernel_input_drift_changes_replay_identity(
    repository_root: Path,
) -> None:
    capability = _capability(repository_root)
    baseline = evaluate_stage6c_synthetic_twr_kernel(_case(), capability=capability)
    points = list(_nav_points())
    points[-1] = replace(points[-1], strategy_nav="199999")
    changed = evaluate_stage6c_synthetic_twr_kernel(
        _case(nav_points=tuple(points)), capability=capability
    )

    assert changed.status is Stage6CSyntheticKernelStatus.TWR_RECONCILED
    assert changed.replay_hash != baseline.replay_hash
    assert changed.annualized_net_excess_percentage_points != (
        baseline.annualized_net_excess_percentage_points
    )
