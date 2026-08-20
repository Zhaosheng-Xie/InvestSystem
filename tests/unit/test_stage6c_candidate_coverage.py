from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_UP, getcontext
from pathlib import Path
from typing import Any

import pytest

from invest_system import RuleApprovalRegistry
from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event import (
    STAGE6C_EMBARGO_SESSIONS,
    STAGE6C_HOLDOUT_START_SESSION_INDEX,
    STAGE6C_MAX_LABEL_SESSIONS,
    Stage6CCandidateDisposition,
    Stage6CCandidateInventory,
    Stage6CCoverageAuditStatus,
    Stage6CFoldPlanSet,
    Stage6CSecurityState,
    Stage6CSyntheticCandidate,
    evaluate_stage6c_synthetic_coverage,
    plan_stage6c_synthetic_folds,
    require_stage6c_kernel_validation_capability,
)

MACHINE_DIRECTORY = Path("产业卡点及事件驱动系统/03_规则与规格/机器制品")
STAGE6C_BUNDLE = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.rule-bundle.json"
)
STAGE6C_APPROVAL = MACHINE_DIRECTORY / (
    "industrial_event_stage6_6c_development_walk_forward_champion_challenge_v0.2.0.approval.json"
)
_YEAR_START_INDEX = {2019: 0, 2022: 756, 2023: 1008, 2024: 1260, 2025: 1512}


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _capability(repository_root: Path) -> Any:
    document = rule_bundle_document_from_json_value(_json(repository_root / STAGE6C_BUNDLE))
    approval = rule_approval_record_from_json_value(_json(repository_root / STAGE6C_APPROVAL))
    return require_stage6c_kernel_validation_capability(
        document, registry=RuleApprovalRegistry((approval,))
    )


def _candidate(
    *,
    candidate_number: int,
    year: int,
    offset: int,
    supported: bool,
    scale: int,
    industry: str | None = None,
) -> Stage6CSyntheticCandidate:
    session_index = _YEAR_START_INDEX[year] + 10 + offset
    return Stage6CSyntheticCandidate.create(
        candidate_id=f"candidate_{candidate_number:03d}",
        economic_event_id=f"economic_event_{candidate_number:03d}",
        listed_company_id=f"company_{candidate_number:03d}",
        decision_time=datetime(year, 1, 5 + offset, 2, tzinfo=UTC),
        decision_session_index=session_index,
        label_end_session_index=session_index + 60,
        level_1_industry=industry or ("industry_a" if scale == 1 else "industry_b"),
        event_type="event_a" if scale == 1 else "event_b",
        e4_state="E4_PUBLIC",
        float_market_cap=str(100 * scale),
        prior_20_session_adv=str(10 * scale),
        prior_120_session_beta=str(scale),
        security_state=Stage6CSecurityState.NORMAL,
        disposition=(
            Stage6CCandidateDisposition.TRADE_READY
            if supported
            else Stage6CCandidateDisposition.BLOCKED
        ),
        supported=supported,
        support_failure_category=None if supported else "UNSUPPORTED_EXIT",
    )


def _balanced_candidates() -> tuple[Stage6CSyntheticCandidate, ...]:
    values: list[Stage6CSyntheticCandidate] = []
    candidate_number = 1
    for offset in range(8):
        values.append(
            _candidate(
                candidate_number=candidate_number,
                year=2019,
                offset=offset,
                supported=True,
                scale=1 if offset % 2 == 0 else 2,
            )
        )
        candidate_number += 1
    for year in (2022, 2023, 2024, 2025):
        for offset in range(8):
            values.append(
                _candidate(
                    candidate_number=candidate_number,
                    year=year,
                    offset=offset,
                    supported=offset < 6,
                    scale=1 if offset % 2 == 0 else 2,
                )
            )
            candidate_number += 1
    return tuple(values)


def _inventory(
    candidates: tuple[Stage6CSyntheticCandidate, ...] | None = None,
) -> Stage6CCandidateInventory:
    return Stage6CCandidateInventory.create(
        inventory_id="stage6c_candidate_inventory_fixture_001",
        projection_hash=_digest("1"),
        candidates=candidates or _balanced_candidates(),
    )


def test_stage6c_candidate_inventory_and_fold_plan_are_deterministic(
    repository_root: Path,
) -> None:
    capability = _capability(repository_root)
    ordered = _inventory()
    reversed_inventory = _inventory(tuple(reversed(_balanced_candidates())))
    first = plan_stage6c_synthetic_folds(ordered, capability=capability)
    second = plan_stage6c_synthetic_folds(reversed_inventory, capability=capability)

    assert ordered == reversed_inventory
    assert first == second
    assert first.holdout_fold_present is False
    assert tuple(fold.fold_id for fold in first.folds) == (
        "WF-2022",
        "WF-2023",
        "WF-2024",
        "WF-2025",
    )
    assert tuple(len(fold.evaluation_candidate_ids) for fold in first.folds) == (8, 8, 8, 8)
    assert tuple(len(fold.training_candidate_ids) for fold in first.folds) == (8, 16, 24, 32)
    assert all(fold.embargo_sessions == STAGE6C_EMBARGO_SESSIONS for fold in first.folds)
    assert all(fold.maximum_label_sessions == STAGE6C_MAX_LABEL_SESSIONS for fold in first.folds)


def test_stage6c_coverage_ready_is_outcome_blind_balanced_and_replayable(
    repository_root: Path,
) -> None:
    capability = _capability(repository_root)
    inventory = _inventory()
    folds = plan_stage6c_synthetic_folds(inventory, capability=capability)

    first = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)
    second = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)

    assert first == second
    assert first.status is Stage6CCoverageAuditStatus.COVERAGE_READY
    assert first.failure_reasons == ()
    assert first.caveats == ("UNSUPPORTED_COUNT_LT_15_NO_PROOF_OF_NO_SELECTION_BIAS",)
    assert first.candidate_count == 40
    assert first.supported_count == 32
    assert first.unsupported_count == 8
    assert first.aggregate_coverage == "0.8"
    assert tuple(item.coverage for item in first.year_coverage) == ("0.75",) * 4
    assert all(item.passes for item in first.year_coverage)
    assert tuple(
        item.absolute_standardized_mean_difference for item in first.continuous_balance
    ) == (
        "0",
        "0",
        "0",
    )
    assert all(item.passes for item in first.continuous_balance)
    material = tuple(item for item in first.categorical_balance if item.material)
    assert material
    assert all(item.coverage == "0.8" for item in material)
    assert all(item.absolute_proportion_difference == "0" for item in material)
    assert all(item.passes for item in material)
    assert first.outcome_fields_read is False
    assert first.not_a_complete_stage6c_walk_forward is True
    assert first.holdout_artifact_read is False
    assert first.persists_state is False
    assert first.authority_eligible is False


def test_stage6c_coverage_is_independent_of_ambient_decimal_context(
    repository_root: Path,
) -> None:
    capability = _capability(repository_root)
    inventory = _inventory()
    folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    baseline = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)
    original_precision = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        getcontext().prec = 6
        getcontext().rounding = ROUND_UP
        changed = evaluate_stage6c_synthetic_coverage(inventory, folds, capability=capability)
    finally:
        getcontext().prec = original_precision
        getcontext().rounding = original_rounding
    assert changed == baseline


def test_stage6c_coverage_quantity_gate_fails_without_dropping_candidates(
    repository_root: Path,
) -> None:
    candidates = list(_balanced_candidates())
    target = candidates[0]
    candidates[0] = _candidate(
        candidate_number=1,
        year=2019,
        offset=0,
        supported=False,
        scale=1,
    )
    assert candidates[0].candidate_id == target.candidate_id
    inventory = _inventory(tuple(candidates))
    capability = _capability(repository_root)
    result = evaluate_stage6c_synthetic_coverage(
        inventory,
        plan_stage6c_synthetic_folds(inventory, capability=capability),
        capability=capability,
    )

    assert result.status is Stage6CCoverageAuditStatus.INSUFFICIENT_EVIDENCE
    assert "AGGREGATE_COVERAGE_BELOW_0_80" in result.failure_reasons
    assert result.candidate_count == 40
    assert result.aggregate_coverage == "0.775"


def test_stage6c_coverage_year_gate_can_fail_while_aggregate_passes(
    repository_root: Path,
) -> None:
    candidates: list[Stage6CSyntheticCandidate] = []
    number = 1
    for offset in range(8):
        candidates.append(
            _candidate(
                candidate_number=number,
                year=2019,
                offset=offset,
                supported=True,
                scale=1 if offset % 2 == 0 else 2,
            )
        )
        number += 1
    for year in (2022, 2023, 2024, 2025):
        for offset in range(8):
            supported = offset < (5 if year == 2022 else 7)
            candidates.append(
                _candidate(
                    candidate_number=number,
                    year=year,
                    offset=offset,
                    supported=supported,
                    scale=1 if offset % 2 == 0 else 2,
                )
            )
            number += 1
    inventory = _inventory(tuple(candidates))
    capability = _capability(repository_root)
    result = evaluate_stage6c_synthetic_coverage(
        inventory,
        plan_stage6c_synthetic_folds(inventory, capability=capability),
        capability=capability,
    )

    assert result.aggregate_coverage == "0.85"
    assert result.status is Stage6CCoverageAuditStatus.INSUFFICIENT_EVIDENCE
    assert "YEAR_COVERAGE_BELOW_0_70" in result.failure_reasons
    assert result.year_coverage[0].coverage == "0.625"


def test_stage6c_coverage_smd_gate_detects_observable_selection_bias(
    repository_root: Path,
) -> None:
    candidates: list[Stage6CSyntheticCandidate] = []
    for index, original in enumerate(_balanced_candidates(), start=1):
        scale = 1 if original.supported else 20
        candidates.append(
            _candidate(
                candidate_number=index,
                year=original.calendar_year,
                offset=(index - 1) % 8,
                supported=original.supported,
                scale=scale,
                industry="industry_shared",
            )
        )
    inventory = _inventory(tuple(candidates))
    capability = _capability(repository_root)
    result = evaluate_stage6c_synthetic_coverage(
        inventory,
        plan_stage6c_synthetic_folds(inventory, capability=capability),
        capability=capability,
    )

    assert result.aggregate_coverage == "0.8"
    assert result.status is Stage6CCoverageAuditStatus.INSUFFICIENT_EVIDENCE
    assert "CONTINUOUS_SMD_ABOVE_0_10" in result.failure_reasons
    assert any(not item.passes for item in result.continuous_balance)


def test_stage6c_coverage_categorical_balance_gate_detects_selection_bias(
    repository_root: Path,
) -> None:
    candidates: list[Stage6CSyntheticCandidate] = []
    supported_seen = 0
    unsupported_seen = 0
    for index, original in enumerate(_balanced_candidates(), start=1):
        if original.supported:
            industry = "industry_a" if supported_seen < 14 else "industry_b"
            supported_seen += 1
        else:
            industry = "industry_a" if unsupported_seen < 6 else "industry_b"
            unsupported_seen += 1
        candidates.append(
            _candidate(
                candidate_number=index,
                year=original.calendar_year,
                offset=(index - 1) % 8,
                supported=original.supported,
                scale=1 if index % 2 else 2,
                industry=industry,
            )
        )
    inventory = _inventory(tuple(candidates))
    capability = _capability(repository_root)
    result = evaluate_stage6c_synthetic_coverage(
        inventory,
        plan_stage6c_synthetic_folds(inventory, capability=capability),
        capability=capability,
    )

    assert result.aggregate_coverage == "0.8"
    assert result.status is Stage6CCoverageAuditStatus.INSUFFICIENT_EVIDENCE
    assert "CATEGORY_PROPORTION_DIFFERENCE_ABOVE_0_10" in result.failure_reasons
    industry_stats = tuple(
        item for item in result.categorical_balance if item.dimension == "level_1_industry"
    )
    assert len(industry_stats) == 2
    assert all(item.material for item in industry_stats)
    assert all(not item.passes for item in industry_stats)


def test_stage6c_fold_planner_enforces_purge_and_embargo_boundary(
    repository_root: Path,
) -> None:
    base = list(_balanced_candidates())
    near_boundary = Stage6CSyntheticCandidate.create(
        candidate_id="candidate_near_boundary",
        economic_event_id="economic_event_near_boundary",
        listed_company_id="company_near_boundary",
        decision_time=datetime(2021, 12, 1, 2, tzinfo=UTC),
        decision_session_index=700,
        label_end_session_index=736,
        level_1_industry="industry_a",
        event_type="event_a",
        e4_state="E4_PUBLIC",
        float_market_cap="100",
        prior_20_session_adv="10",
        prior_120_session_beta="1",
        security_state=Stage6CSecurityState.NORMAL,
        disposition=Stage6CCandidateDisposition.TRADE_READY,
        supported=True,
        support_failure_category=None,
    )
    base.append(near_boundary)
    inventory = _inventory(tuple(base))
    folds = plan_stage6c_synthetic_folds(inventory, capability=_capability(repository_root))

    assert "candidate_near_boundary" not in folds.folds[0].training_candidate_ids
    assert folds.folds[0].evaluation_start_session_index - STAGE6C_EMBARGO_SESSIONS == 736


def test_stage6c_fold_planner_never_uses_label_that_enters_holdout(
    repository_root: Path,
) -> None:
    candidates = list(_balanced_candidates())
    late = Stage6CSyntheticCandidate.create(
        candidate_id="candidate_late_2025",
        economic_event_id="economic_event_late_2025",
        listed_company_id="company_late_2025",
        decision_time=datetime(2025, 12, 1, 2, tzinfo=UTC),
        decision_session_index=1720,
        label_end_session_index=1780,
        level_1_industry="industry_a",
        event_type="event_a",
        e4_state="E4_PUBLIC",
        float_market_cap="100",
        prior_20_session_adv="10",
        prior_120_session_beta="1",
        security_state=Stage6CSecurityState.NORMAL,
        disposition=Stage6CCandidateDisposition.BLOCKED,
        supported=False,
        support_failure_category="HOLDOUT_LABEL_UNAVAILABLE",
    )
    candidates.append(late)
    inventory = _inventory(tuple(candidates))
    folds = plan_stage6c_synthetic_folds(inventory, capability=_capability(repository_root))

    assert late.candidate_id in tuple(item.candidate_id for item in inventory.candidates)
    assert late.candidate_id not in folds.folds[-1].evaluation_candidate_ids
    assert late.label_end_session_index >= STAGE6C_HOLDOUT_START_SESSION_INDEX


def test_stage6c_candidate_contract_rejects_holdout_outcome_and_duplicate_units() -> None:
    with pytest.raises(ValueError, match="outside holdout"):
        Stage6CSyntheticCandidate.create(
            candidate_id="candidate_holdout",
            economic_event_id="event_holdout",
            listed_company_id="company_holdout",
            decision_time=datetime(2026, 1, 2, tzinfo=UTC),
            decision_session_index=1765,
            label_end_session_index=1825,
            level_1_industry="industry_a",
            event_type="event_a",
            e4_state="E4_PUBLIC",
            float_market_cap="100",
            prior_20_session_adv="10",
            prior_120_session_beta="1",
            security_state=Stage6CSecurityState.NORMAL,
            disposition=Stage6CCandidateDisposition.BLOCKED,
            supported=False,
            support_failure_category="HOLDOUT_FORBIDDEN",
        )
    candidate = _balanced_candidates()[0]
    with pytest.raises(ValueError, match="outcome-blind"):
        replace(candidate, outcome_fields_present=True, candidate_hash=candidate.candidate_hash)
    with pytest.raises(ValueError, match="synthetic year range"):
        Stage6CSyntheticCandidate.create(
            candidate_id="candidate_bad_session_year",
            economic_event_id="event_bad_session_year",
            listed_company_id="company_bad_session_year",
            decision_time=datetime(2022, 1, 5, 2, tzinfo=UTC),
            decision_session_index=10,
            label_end_session_index=70,
            level_1_industry="industry_a",
            event_type="event_a",
            e4_state="E4_PUBLIC",
            float_market_cap="100",
            prior_20_session_adv="10",
            prior_120_session_beta="1",
            security_state=Stage6CSecurityState.NORMAL,
            disposition=Stage6CCandidateDisposition.TRADE_READY,
            supported=True,
            support_failure_category=None,
        )
    duplicate = Stage6CSyntheticCandidate.create(
        candidate_id="candidate_duplicate_id",
        economic_event_id=candidate.economic_event_id,
        listed_company_id=candidate.listed_company_id,
        decision_time=candidate.decision_time,
        decision_session_index=candidate.decision_session_index,
        label_end_session_index=candidate.label_end_session_index,
        level_1_industry=candidate.level_1_industry,
        event_type=candidate.event_type,
        e4_state=candidate.e4_state,
        float_market_cap=candidate.float_market_cap,
        prior_20_session_adv=candidate.prior_20_session_adv,
        prior_120_session_beta=candidate.prior_120_session_beta,
        security_state=candidate.security_state,
        disposition=candidate.disposition,
        supported=candidate.supported,
        support_failure_category=candidate.support_failure_category,
    )
    with pytest.raises(ValueError, match="research units must be unique"):
        Stage6CCandidateInventory.create(
            inventory_id="duplicate_inventory",
            projection_hash=_digest("1"),
            candidates=(candidate, duplicate),
        )


def test_stage6c_coverage_rejects_rebound_fold_plan(repository_root: Path) -> None:
    capability = _capability(repository_root)
    inventory = _inventory()
    valid = plan_stage6c_synthetic_folds(inventory, capability=capability)
    payload: dict[str, Any] = {
        "schema_version": valid.schema_version,
        "inventory_hash": _digest("9"),
        "folds": valid.folds,
        "synthetic": valid.synthetic,
        "validation_only": valid.validation_only,
        "holdout_fold_present": valid.holdout_fold_present,
        "authority_eligible": valid.authority_eligible,
    }
    rebound = Stage6CFoldPlanSet(
        schema_version=valid.schema_version,
        inventory_hash=_digest("9"),
        folds=valid.folds,
        synthetic=valid.synthetic,
        validation_only=valid.validation_only,
        holdout_fold_present=valid.holdout_fold_present,
        authority_eligible=valid.authority_eligible,
        plan_set_hash=HashDigest(algorithm="sha256", value=canonical_sha256(payload)),
    )

    result = evaluate_stage6c_synthetic_coverage(inventory, rebound, capability=capability)
    assert result.status is Stage6CCoverageAuditStatus.PRECHECK_BLOCKED
    assert result.failure_reasons == (
        "FOLD_INVENTORY_HASH_MISMATCH",
        "FOLD_PLAN_RECOMPUTATION_MISMATCH",
    )
    assert result.outcome_fields_read is False
    assert result.persists_state is False
