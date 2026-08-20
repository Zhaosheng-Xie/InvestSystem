from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path

import pytest

from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.strategies.industrial_event import (
    Stage6CCandidateInventory,
    Stage6CComparisonId,
    Stage6CCoverageAuditResult,
    Stage6CDailyNavPoint,
    Stage6CFoldPlanSet,
    Stage6CHolmStatus,
    Stage6CInferenceCase,
    Stage6CInferenceResult,
    Stage6CInferenceStatus,
    Stage6CPairedContribution,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    evaluate_stage6c_holm_family,
    evaluate_stage6c_synthetic_coverage,
    evaluate_stage6c_synthetic_inference,
    evaluate_stage6c_synthetic_twr_kernel,
    plan_stage6c_synthetic_folds,
)

_COVERAGE_SUPPORT = import_module("tests.unit.test_stage6c_candidate_coverage")
_TWR_SUPPORT = import_module("tests.unit.test_stage6c_synthetic_kernel")
_capability = _COVERAGE_SUPPORT._capability
_inventory = _COVERAGE_SUPPORT._inventory
_base_twr_case = _TWR_SUPPORT._case


def _constant_factor_nav_points(
    *,
    factor: int = 2,
) -> tuple[Stage6CDailyNavPoint, ...]:
    start = date(2020, 1, 1)
    points: list[Stage6CDailyNavPoint] = []
    strategy_nav = 100000
    for index in range(127):
        if index:
            strategy_nav *= factor
        points.append(
            Stage6CDailyNavPoint(
                session_index=index,
                session_date=(start + timedelta(days=index)).isoformat(),
                strategy_nav=str(strategy_nav),
                benchmark_nav="100000",
            )
        )
    return tuple(points)


def _sources(
    repository_root: Path, *, factor: int = 2
) -> tuple[
    ApprovedRuleCapability,
    Stage6CCandidateInventory,
    Stage6CFoldPlanSet,
    Stage6CCoverageAuditResult,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
]:
    capability = _capability(repository_root)
    inventory = _inventory()
    folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    coverage = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)
    twr_case = _base_twr_case(nav_points=_constant_factor_nav_points(factor=factor))
    twr_result = evaluate_stage6c_synthetic_twr_kernel(twr_case, capability=capability)
    return capability, inventory, folds, coverage, twr_case, twr_result


def _contributions(
    inventory: Stage6CCandidateInventory,
) -> tuple[Stage6CPairedContribution, ...]:
    values: list[Stage6CPairedContribution] = []
    for index, candidate in enumerate(inventory.candidates):
        contribution = "100" if candidate.disposition.value == "TRADE_READY" else "0"
        values.append(
            Stage6CPairedContribution(
                candidate_id=candidate.candidate_id,
                listed_company_id=candidate.listed_company_id,
                risk_cluster_id=f"risk_cluster_{index % 4}",
                full_net_contribution=contribution,
                comparator_net_contribution="0",
            )
        )
    return tuple(values)


def _inference_case(
    comparison_id: Stage6CComparisonId,
    *,
    inventory: Stage6CCandidateInventory,
    folds: Stage6CFoldPlanSet,
    coverage: Stage6CCoverageAuditResult,
    twr_case: Stage6CSyntheticKernelCase,
    twr_result: Stage6CSyntheticKernelResult,
    contributions: tuple[Stage6CPairedContribution, ...] | None = None,
    full_ending_pnl: str = "3200",
) -> Stage6CInferenceCase:
    return Stage6CInferenceCase.create(
        inference_case_id=f"stage6c_inference_{comparison_id.value}",
        comparison_id=comparison_id,
        inventory_hash=inventory.inventory_hash,
        fold_plan_set_hash=folds.plan_set_hash,
        coverage_replay_hash=coverage.replay_hash,
        twr_case_hash=twr_case.case_hash,
        twr_replay_hash=twr_result.replay_hash,
        fold_beginning_nav="100000",
        full_ending_pnl=full_ending_pnl,
        comparator_ending_pnl="0",
        contributions=contributions or _contributions(inventory),
    )


def _evaluate_one(
    repository_root: Path,
) -> tuple[
    ApprovedRuleCapability,
    Stage6CCandidateInventory,
    Stage6CFoldPlanSet,
    Stage6CCoverageAuditResult,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    Stage6CInferenceCase,
    Stage6CInferenceResult,
]:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(repository_root)
    case = _inference_case(
        Stage6CComparisonId.FULL_VS_MARKET_OR_INDUSTRY_MATCHED,
        inventory=inventory,
        folds=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
    )
    result = evaluate_stage6c_synthetic_inference(
        case,
        inventory=inventory,
        fold_plans=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        capability=capability,
    )
    return (capability, inventory, folds, coverage, twr_case, twr_result, case, result)


def test_stage6c_inference_three_paths_pass_and_are_deterministic(
    repository_root: Path,
) -> None:
    sources = _evaluate_one(repository_root)
    result = sources[-1]
    repeated = evaluate_stage6c_synthetic_inference(
        sources[-2],
        inventory=sources[1],
        fold_plans=sources[2],
        coverage=sources[3],
        twr_case=sources[4],
        twr_result=sources[5],
        capability=sources[0],
    )

    assert result == repeated
    assert result.status is Stage6CInferenceStatus.INFERENCE_PASSED
    assert result.failure_reasons == ()
    assert result.calendar_path is not None
    assert result.company_path is not None
    assert result.risk_path is not None
    assert result.calendar_path.passes_positive_lower_bound is True
    assert result.company_path.passes_positive_lower_bound is True
    assert result.risk_path.passes_positive_lower_bound is True
    assert Decimal(result.calendar_path.raw_p_value) <= Decimal("0.001")
    assert Decimal(result.company_path.ci_lower) > 0
    assert Decimal(result.risk_path.ci_lower) > 0
    assert result.not_a_complete_stage6c_walk_forward is True
    assert result.holdout_artifact_read is False
    assert result.persists_state is False
    assert result.authority_eligible is False


def test_stage6c_inference_blocks_contribution_reconciliation_drift(
    repository_root: Path,
) -> None:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(repository_root)
    case = _inference_case(
        Stage6CComparisonId.FULL_VS_NO_TRADE,
        inventory=inventory,
        folds=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        full_ending_pnl="3199",
    )
    result = evaluate_stage6c_synthetic_inference(
        case,
        inventory=inventory,
        fold_plans=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        capability=capability,
    )

    assert result.status is Stage6CInferenceStatus.RECONCILIATION_BLOCKED
    assert result.failure_reasons == ("CONTRIBUTION_PNL_RECONCILIATION_MISMATCH",)
    assert result.calendar_path is None
    assert result.company_path is None
    assert result.risk_path is None


def test_stage6c_inference_blocks_nontrading_candidate_contribution(
    repository_root: Path,
) -> None:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(repository_root)
    contributions = list(_contributions(inventory))
    blocked_index = next(
        index
        for index, candidate in enumerate(inventory.candidates)
        if candidate.disposition.value != "TRADE_READY"
    )
    contributions[blocked_index] = replace(contributions[blocked_index], full_net_contribution="1")
    case = _inference_case(
        Stage6CComparisonId.FULL_VS_SIMPLE_E4_ONLY,
        inventory=inventory,
        folds=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        contributions=tuple(contributions),
        full_ending_pnl="3201",
    )
    result = evaluate_stage6c_synthetic_inference(
        case,
        inventory=inventory,
        fold_plans=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        capability=capability,
    )

    assert result.status is Stage6CInferenceStatus.RECONCILIATION_BLOCKED
    assert result.failure_reasons == ("NON_TRADING_CANDIDATE_CONTRIBUTION_NONZERO",)


def test_stage6c_holm_recomputes_exact_five_case_family_and_passes(
    repository_root: Path,
) -> None:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(repository_root)
    cases = tuple(
        _inference_case(
            comparison_id,
            inventory=inventory,
            folds=folds,
            coverage=coverage,
            twr_case=twr_case,
            twr_result=twr_result,
        )
        for comparison_id in Stage6CComparisonId
    )
    result = evaluate_stage6c_holm_family(
        cases,
        inventory=inventory,
        fold_plans=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        capability=capability,
    )

    assert result.status is Stage6CHolmStatus.ADJUSTED_INFERENCE_READY
    assert result.failure_reasons == ()
    assert len(result.items) == 5
    assert tuple(item.rank for item in result.items) == (1, 2, 3, 4, 5)
    assert all(item.rejected for item in result.items)
    assert all(Decimal(item.adjusted_p_value) <= Decimal("0.05") for item in result.items)
    assert result.holdout_artifact_read is False
    assert result.authority_eligible is False


def test_stage6c_holm_rejects_incomplete_or_duplicate_family(repository_root: Path) -> None:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(repository_root)
    one = _inference_case(
        Stage6CComparisonId.FULL_VS_NO_TRADE,
        inventory=inventory,
        folds=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
    )
    with pytest.raises(ValueError, match="every comparison exactly once"):
        evaluate_stage6c_holm_family(
            (one, one, one, one, one),
            inventory=inventory,
            fold_plans=folds,
            coverage=coverage,
            twr_case=twr_case,
            twr_result=twr_result,
            capability=capability,
        )


def test_stage6c_holm_fails_when_calendar_path_has_no_positive_evidence(
    repository_root: Path,
) -> None:
    capability, inventory, folds, coverage, twr_case, twr_result = _sources(
        repository_root, factor=1
    )
    contributions = tuple(
        replace(value, full_net_contribution="0") for value in _contributions(inventory)
    )
    cases = tuple(
        _inference_case(
            comparison_id,
            inventory=inventory,
            folds=folds,
            coverage=coverage,
            twr_case=twr_case,
            twr_result=twr_result,
            contributions=contributions,
            full_ending_pnl="0",
        )
        for comparison_id in Stage6CComparisonId
    )
    result = evaluate_stage6c_holm_family(
        cases,
        inventory=inventory,
        fold_plans=folds,
        coverage=coverage,
        twr_case=twr_case,
        twr_result=twr_result,
        capability=capability,
    )

    assert result.status is Stage6CHolmStatus.ADJUSTED_INFERENCE_FAILED
    assert "HOLM_ADJUSTED_FAMILY_NOT_ALL_REJECTED" in result.failure_reasons
    assert "PRIMARY_COMPARISON_THREE_PATH_GATE_FAILED" in result.failure_reasons
    assert all(not item.rejected for item in result.items)


def test_stage6c_inference_input_drift_changes_replay_identity(
    repository_root: Path,
) -> None:
    sources = _evaluate_one(repository_root)
    baseline = sources[-1]
    contributions = list(_contributions(sources[1]))
    contributions[0] = replace(contributions[0], full_net_contribution="101")
    changed_case = _inference_case(
        Stage6CComparisonId.FULL_VS_MARKET_OR_INDUSTRY_MATCHED,
        inventory=sources[1],
        folds=sources[2],
        coverage=sources[3],
        twr_case=sources[4],
        twr_result=sources[5],
        contributions=tuple(contributions),
        full_ending_pnl="3201",
    )
    changed = evaluate_stage6c_synthetic_inference(
        changed_case,
        inventory=sources[1],
        fold_plans=sources[2],
        coverage=sources[3],
        twr_case=sources[4],
        twr_result=sources[5],
        capability=sources[0],
    )

    assert changed.status is Stage6CInferenceStatus.INFERENCE_PASSED
    assert changed.replay_hash != baseline.replay_hash


def test_stage6c_inference_contract_rejects_noncanonical_numeric_input() -> None:
    with pytest.raises(ValueError, match="canonical fixed-point"):
        Stage6CPairedContribution(
            candidate_id="candidate_001",
            listed_company_id="company_001",
            risk_cluster_id="risk_cluster_001",
            full_net_contribution="NaN",
            comparator_net_contribution="0",
        )
