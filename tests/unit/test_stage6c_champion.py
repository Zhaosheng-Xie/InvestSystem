from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from invest_system.models import HashDigest
from invest_system.strategies.industrial_event import (
    Stage6CCandidateInventory,
    Stage6CComparisonId,
    Stage6CDailyNavPoint,
    Stage6CFoldTwrBinding,
    Stage6CSyntheticAuditAttestation,
    Stage6CSyntheticChampionCase,
    Stage6CSyntheticChampionResult,
    Stage6CSyntheticChampionStatus,
    Stage6CSyntheticCompletionAttestation,
    Stage6CSyntheticFrictionAttestation,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    evaluate_stage6c_synthetic_champion_gate,
    evaluate_stage6c_synthetic_coverage,
    evaluate_stage6c_synthetic_twr_kernel,
    plan_stage6c_synthetic_folds,
)

_COVERAGE_SUPPORT = import_module("tests.unit.test_stage6c_candidate_coverage")
_INFERENCE_SUPPORT = import_module("tests.unit.test_stage6c_inference")
_TWR_SUPPORT = import_module("tests.unit.test_stage6c_synthetic_kernel")
_capability = _COVERAGE_SUPPORT._capability
_candidate = _COVERAGE_SUPPORT._candidate
_balanced_candidates = _COVERAGE_SUPPORT._balanced_candidates
_default_inventory = _COVERAGE_SUPPORT._inventory
_inference_case = _INFERENCE_SUPPORT._inference_case
_comparison_twr_sources = _INFERENCE_SUPPORT._comparison_twr_sources
_base_twr_case = _TWR_SUPPORT._case


def _digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _champion_inventory() -> Stage6CCandidateInventory:
    candidates = []
    for index, original in enumerate(_balanced_candidates(), start=1):
        supported = original.calendar_year != 2019
        candidates.append(
            _candidate(
                candidate_number=index,
                year=original.calendar_year,
                offset=(index - 1) % 8,
                supported=supported,
                scale=1 if index % 2 else 2,
            )
        )
    return Stage6CCandidateInventory.create(
        inventory_id="stage6c_champion_inventory",
        projection_hash=_digest("1"),
        candidates=tuple(candidates),
    )


def _fold_nav_points(gross_factor: str) -> tuple[Stage6CDailyNavPoint, ...]:
    start = date(2020, 1, 1)
    ending = Decimal("100000") * Decimal(gross_factor)
    return tuple(
        Stage6CDailyNavPoint(
            session_index=index,
            session_date=(start + timedelta(days=index)).isoformat(),
            strategy_nav=str(ending) if index == 252 else "100000",
            benchmark_nav="100000",
        )
        for index in range(253)
    )


def _twr_source(
    case_id: str,
    gross_factor: str,
    *,
    capability: Any,
) -> tuple[Stage6CSyntheticKernelCase, Stage6CSyntheticKernelResult]:
    base = _base_twr_case(nav_points=_fold_nav_points(gross_factor))
    case = Stage6CSyntheticKernelCase.create(
        case_id=case_id,
        projection=base.projection,
        holdout_commitment=base.holdout_commitment,
        isolation_evidence=base.isolation_evidence,
        nav_points=base.nav_points,
    )
    return case, evaluate_stage6c_synthetic_twr_kernel(case, capability=capability)


def _sources(
    repository_root: Path,
    *,
    inventory: Stage6CCandidateInventory | None = None,
    fold_factors: tuple[str, str, str, str] = ("1.05", "1.04", "1.03", "0.95"),
    friction_factor: str = "1.01",
) -> dict[str, Any]:
    capability = _capability(repository_root)
    inventory = inventory or _champion_inventory()
    folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    coverage = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)
    fold_sources = tuple(
        _twr_source(f"fold_twr_{index}", factor, capability=capability)
        for index, factor in enumerate(fold_factors, start=1)
    )
    fold_cases = tuple(value[0] for value in fold_sources)
    fold_results = tuple(value[1] for value in fold_sources)
    inference_twr_cases, inference_twr_results = _comparison_twr_sources(capability)
    inference_cases = tuple(
        _inference_case(
            comparison_id,
            inventory=inventory,
            folds=folds,
            coverage=coverage,
            twr_case=inference_twr_cases[index],
            twr_result=inference_twr_results[index],
        )
        for index, comparison_id in enumerate(Stage6CComparisonId)
    )
    friction_case, friction_result = _twr_source(
        "friction_1_5_twr", friction_factor, capability=capability
    )
    audit = Stage6CSyntheticAuditAttestation.create(
        attestation_id="stage6c_synthetic_audit_attestation",
        source_test_report_hash=_digest("8"),
        p0_bias_failure_count=0,
        reconciliation_failure_count=0,
    )
    evaluation_ids = {
        candidate_id for fold in folds.folds for candidate_id in fold.evaluation_candidate_ids
    }
    completed_ids = tuple(
        sorted(
            candidate.candidate_id
            for candidate in inventory.candidates
            if candidate.candidate_id in evaluation_ids
            and candidate.supported
            and candidate.disposition.value == "TRADE_READY"
        )
    )
    completion = Stage6CSyntheticCompletionAttestation.create(
        attestation_id="stage6c_synthetic_completion_attestation",
        completed_candidate_ids=completed_ids,
        source_test_report_hash=_digest("9"),
    )
    friction_attestation = Stage6CSyntheticFrictionAttestation.create(
        attestation_id="stage6c_synthetic_friction_attestation",
        twr_case_hash=friction_case.case_hash,
        twr_replay_hash=friction_result.replay_hash,
        source_test_report_hash=_digest("5"),
    )
    champion_case = Stage6CSyntheticChampionCase.create(
        champion_case_id="stage6c_synthetic_champion_case",
        inventory_hash=inventory.inventory_hash,
        fold_plan_set_hash=folds.plan_set_hash,
        coverage_replay_hash=coverage.replay_hash,
        fold_twr_bindings=tuple(
            Stage6CFoldTwrBinding(
                fold_id=fold.fold_id,
                twr_case_hash=twr_case.case_hash,
                twr_replay_hash=twr_result.replay_hash,
            )
            for fold, twr_case, twr_result in zip(
                folds.folds, fold_cases, fold_results, strict=True
            )
        ),
        inference_case_hashes=tuple(value.case_hash for value in inference_cases),
        inference_twr_case_hashes=tuple(value.case_hash for value in inference_twr_cases),
        inference_twr_replay_hashes=tuple(value.replay_hash for value in inference_twr_results),
        friction_attestation_hash=friction_attestation.attestation_hash,
        completion_attestation_hash=completion.attestation_hash,
        audit_attestation_hash=audit.attestation_hash,
    )
    return {
        "capability": capability,
        "inventory": inventory,
        "folds": folds,
        "coverage": coverage,
        "fold_cases": fold_cases,
        "fold_results": fold_results,
        "inference_cases": inference_cases,
        "inference_twr_cases": inference_twr_cases,
        "inference_twr_results": inference_twr_results,
        "friction_case": friction_case,
        "friction_result": friction_result,
        "friction_attestation": friction_attestation,
        "audit": audit,
        "completion": completion,
        "champion_case": champion_case,
    }


def _evaluate(values: dict[str, Any]) -> Stage6CSyntheticChampionResult:
    return evaluate_stage6c_synthetic_champion_gate(
        values["champion_case"],
        inventory=values["inventory"],
        fold_plans=values["folds"],
        coverage=values["coverage"],
        fold_twr_cases=values["fold_cases"],
        fold_twr_results=values["fold_results"],
        inference_cases=values["inference_cases"],
        inference_twr_cases=values["inference_twr_cases"],
        inference_twr_results=values["inference_twr_results"],
        friction_twr_case=values["friction_case"],
        friction_twr_result=values["friction_result"],
        friction_attestation=values["friction_attestation"],
        completion_attestation=values["completion"],
        audit_attestation=values["audit"],
        capability=values["capability"],
    )


def test_stage6c_synthetic_champion_gate_passes_all_approved_formulas(
    repository_root: Path,
) -> None:
    result = _evaluate(_sources(repository_root))

    assert result.status is Stage6CSyntheticChampionStatus.GATE_FORMULA_PASSED
    assert result.failure_reasons == ()
    assert result.completed_trade_count == 32
    assert result.fold_completed_trade_counts == (8, 8, 8, 8)
    assert result.fold_net_excess_percentage_points == ("5", "4", "3", "-5")
    assert result.positive_fold_count == 3
    assert result.worst_fold_net_excess_percentage_points == "-5"
    assert Decimal(result.full_net_benchmark_excess_percentage_points or "0") > 0
    assert Decimal(result.full_vs_best_simple_increment_percentage_points or "0") >= 2
    assert result.maximum_drawdown == "0.05"
    assert result.total_net_profit == "3200"
    assert result.largest_winner_share == "0.03125"
    assert result.friction_one_point_five_net_excess_percentage_points == "1"
    assert result.holm_replay_hash is not None
    assert result.not_a_real_6d_request is True
    assert result.not_a_complete_stage6c_walk_forward is True
    assert result.formal_historical_run is False
    assert result.holdout_artifact_read is False
    assert result.persists_state is False
    assert result.authority_eligible is False


def test_stage6c_synthetic_champion_precheck_blocks_source_hash_drift(
    repository_root: Path,
) -> None:
    values = _sources(repository_root)
    original = values["champion_case"]
    values["champion_case"] = Stage6CSyntheticChampionCase.create(
        champion_case_id="stage6c_synthetic_champion_case_drifted",
        inventory_hash=_digest("9"),
        fold_plan_set_hash=original.fold_plan_set_hash,
        coverage_replay_hash=original.coverage_replay_hash,
        fold_twr_bindings=original.fold_twr_bindings,
        inference_case_hashes=original.inference_case_hashes,
        inference_twr_case_hashes=original.inference_twr_case_hashes,
        inference_twr_replay_hashes=original.inference_twr_replay_hashes,
        friction_attestation_hash=original.friction_attestation_hash,
        completion_attestation_hash=original.completion_attestation_hash,
        audit_attestation_hash=original.audit_attestation_hash,
    )
    result = _evaluate(values)

    assert result.status is Stage6CSyntheticChampionStatus.PRECHECK_BLOCKED
    assert result.failure_reasons == ("INVENTORY_SOURCE_MISMATCH",)
    assert result.holm_replay_hash is None


def test_stage6c_synthetic_champion_rejects_nonzero_audit_failures(
    repository_root: Path,
) -> None:
    values = _sources(repository_root)
    audit = Stage6CSyntheticAuditAttestation.create(
        attestation_id="stage6c_synthetic_audit_failed",
        source_test_report_hash=_digest("7"),
        p0_bias_failure_count=1,
        reconciliation_failure_count=1,
    )
    original = values["champion_case"]
    values["audit"] = audit
    values["champion_case"] = Stage6CSyntheticChampionCase.create(
        champion_case_id="stage6c_synthetic_champion_case_audit_failed",
        inventory_hash=original.inventory_hash,
        fold_plan_set_hash=original.fold_plan_set_hash,
        coverage_replay_hash=original.coverage_replay_hash,
        fold_twr_bindings=original.fold_twr_bindings,
        inference_case_hashes=original.inference_case_hashes,
        inference_twr_case_hashes=original.inference_twr_case_hashes,
        inference_twr_replay_hashes=original.inference_twr_replay_hashes,
        friction_attestation_hash=original.friction_attestation_hash,
        completion_attestation_hash=original.completion_attestation_hash,
        audit_attestation_hash=audit.attestation_hash,
    )
    result = _evaluate(values)

    assert result.status is Stage6CSyntheticChampionStatus.REVISE_REQUIRED
    assert result.failure_reasons == (
        "P0_BIAS_FAILURES_NONZERO",
        "RECONCILIATION_FAILURES_NONZERO",
    )


def test_stage6c_synthetic_champion_requires_30_completed_walk_forward_trades(
    repository_root: Path,
) -> None:
    result = _evaluate(_sources(repository_root, inventory=_default_inventory()))

    assert result.status is Stage6CSyntheticChampionStatus.INSUFFICIENT_EVIDENCE
    assert result.completed_trade_count == 24
    assert result.fold_completed_trade_counts == (6, 6, 6, 6)
    assert result.failure_reasons == ("COMPLETED_TRADES_BELOW_30",)


def test_stage6c_synthetic_champion_revises_on_fold_drawdown_and_friction_failures(
    repository_root: Path,
) -> None:
    result = _evaluate(
        _sources(
            repository_root,
            fold_factors=("1.05", "0.8", "0.7", "0.6"),
            friction_factor="0.99",
        )
    )

    assert result.status is Stage6CSyntheticChampionStatus.REVISE_REQUIRED
    assert result.positive_fold_count == 1
    assert result.worst_fold_net_excess_percentage_points == "-40"
    assert result.maximum_drawdown == "0.4"
    assert result.friction_one_point_five_net_excess_percentage_points == "-1"
    assert result.failure_reasons == (
        "FRICTION_1_5_NET_EXCESS_NEGATIVE",
        "MAXIMUM_DRAWDOWN_ABOVE_0_15",
        "POSITIVE_FOLDS_BELOW_3_OF_4",
        "WORST_FOLD_BELOW_MINUS_10",
    )


def test_stage6c_synthetic_champion_attestation_never_claims_real_audit() -> None:
    audit = Stage6CSyntheticAuditAttestation.create(
        attestation_id="stage6c_synthetic_audit_boundary",
        source_test_report_hash=_digest("6"),
        p0_bias_failure_count=0,
        reconciliation_failure_count=0,
    )
    assert audit.synthetic is True
    assert audit.validation_only is True
    assert audit.not_a_real_bias_audit is True
    assert audit.authority_eligible is False
    with pytest.raises(ValueError, match="anonymous synthetic"):
        Stage6CSyntheticAuditAttestation(
            schema_version=audit.schema_version,
            attestation_id=audit.attestation_id,
            source_test_report_hash=audit.source_test_report_hash,
            p0_bias_failure_count=0,
            reconciliation_failure_count=0,
            synthetic=True,
            validation_only=True,
            not_a_real_bias_audit=False,
            authority_eligible=False,
            attestation_hash=audit.attestation_hash,
        )
    friction = Stage6CSyntheticFrictionAttestation.create(
        attestation_id="stage6c_synthetic_friction_boundary",
        twr_case_hash=_digest("1"),
        twr_replay_hash=_digest("2"),
        source_test_report_hash=_digest("3"),
    )
    assert friction.friction_multiplier == "1.5"
    assert friction.not_a_real_friction_replay is True
    with pytest.raises(ValueError, match="must be 1.5"):
        replace(
            friction,
            friction_multiplier="1.0",
            attestation_hash=friction.attestation_hash,
        )


def test_stage6c_synthetic_champion_rejects_reordered_fold_bindings(
    repository_root: Path,
) -> None:
    original = _sources(repository_root)["champion_case"]
    with pytest.raises(ValueError, match="approved fold closed world"):
        Stage6CSyntheticChampionCase.create(
            champion_case_id="stage6c_reordered_fold_binding",
            inventory_hash=original.inventory_hash,
            fold_plan_set_hash=original.fold_plan_set_hash,
            coverage_replay_hash=original.coverage_replay_hash,
            fold_twr_bindings=tuple(reversed(original.fold_twr_bindings)),
            inference_case_hashes=original.inference_case_hashes,
            inference_twr_case_hashes=original.inference_twr_case_hashes,
            inference_twr_replay_hashes=original.inference_twr_replay_hashes,
            friction_attestation_hash=original.friction_attestation_hash,
            completion_attestation_hash=original.completion_attestation_hash,
            audit_attestation_hash=original.audit_attestation_hash,
        )
