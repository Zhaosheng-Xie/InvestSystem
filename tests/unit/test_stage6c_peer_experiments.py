from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from importlib import import_module
from pathlib import Path

import pytest

from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event import (
    STAGE6C_MINIMUM_PEERS,
    STAGE6C_REQUIRED_ABLATION_IDS,
    STAGE6C_REQUIRED_STRESS_IDS,
    Stage6CCandidateInventory,
    Stage6CExperimentKind,
    Stage6CExperimentOutcome,
    Stage6CExperimentOutcomeStatus,
    Stage6CExperimentRegistration,
    Stage6CFoldPlanSet,
    Stage6CPeerBasketStatus,
    Stage6CPeerFallbackLevel,
    Stage6CPeerMember,
    Stage6CPeerSnapshot,
    Stage6CSyntheticCandidate,
    build_stage6c_experiment_ledger,
    build_stage6c_peer_basket,
    build_stage6c_peer_basket_set,
    plan_stage6c_synthetic_folds,
)

_COVERAGE_SUPPORT = import_module("tests.unit.test_stage6c_candidate_coverage")
_CHAMPION_SUPPORT = import_module("tests.unit.test_stage6c_champion")
_capability = _COVERAGE_SUPPORT._capability
_champion_inventory = _CHAMPION_SUPPORT._champion_inventory


def _digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _member(
    security_id: str,
    *,
    candidate: Stage6CSyntheticCandidate,
    industry: str | None = None,
    size_quintile: int = 3,
    beta_quintile: int = 2,
    eligible: bool = True,
    supported: bool = True,
) -> Stage6CPeerMember:
    return Stage6CPeerMember(
        security_id=security_id,
        level_1_industry=industry or candidate.level_1_industry,
        float_market_cap_quintile=size_quintile,
        prior_120_session_beta_quintile=beta_quintile,
        available_at=candidate.decision_time,
        eligible=eligible,
        stage5d_supported=supported,
        synthetic=True,
        validation_only=True,
        outcome_fields_present=False,
    )


def _snapshot(
    candidate: Stage6CSyntheticCandidate,
    members: tuple[Stage6CPeerMember, ...],
) -> Stage6CPeerSnapshot:
    return Stage6CPeerSnapshot.create(
        snapshot_id=f"peer_snapshot_{candidate.candidate_id}",
        candidate=candidate,
        target_float_market_cap_quintile=3,
        target_prior_120_session_beta_quintile=2,
        members=members,
    )


def test_stage6c_peer_basket_uses_exact_level_and_excludes_target(
    repository_root: Path,
) -> None:
    candidate = next(
        value for value in _champion_inventory().candidates if value.calendar_year == 2022
    )
    members = tuple(
        [_member(candidate.listed_company_id, candidate=candidate)]
        + [_member(f"peer_exact_{index}", candidate=candidate) for index in range(6)]
    )
    result = build_stage6c_peer_basket(
        candidate, _snapshot(candidate, members), capability=_capability(repository_root)
    )

    assert result.status is Stage6CPeerBasketStatus.READY
    assert result.fallback_level is Stage6CPeerFallbackLevel.SAME_INDUSTRY_SIZE_BETA
    assert result.peer_count == 6
    assert candidate.listed_company_id not in tuple(
        value.security_id for value in result.peer_weights
    )
    assert all(value.numerator == 1 and value.denominator == 6 for value in result.peer_weights)
    assert result.holdout_artifact_read is False
    assert result.authority_eligible is False


def test_stage6c_peer_basket_uses_first_fallback_with_at_least_five(
    repository_root: Path,
) -> None:
    candidate = next(
        value for value in _champion_inventory().candidates if value.calendar_year == 2022
    )
    members = tuple(
        [_member(f"peer_industry_{index}", candidate=candidate) for index in range(4)]
        + [
            _member(
                f"peer_cross_industry_{index}",
                candidate=candidate,
                industry="other_industry",
            )
            for index in range(3)
        ]
    )
    result = build_stage6c_peer_basket(
        candidate, _snapshot(candidate, members), capability=_capability(repository_root)
    )

    assert result.status is Stage6CPeerBasketStatus.READY
    assert result.fallback_level is Stage6CPeerFallbackLevel.SAME_SIZE_BETA_ALL_A_SHARE
    assert result.peer_count == 7


def test_stage6c_peer_basket_fails_closed_below_minimum(repository_root: Path) -> None:
    candidate = next(
        value for value in _champion_inventory().candidates if value.calendar_year == 2022
    )
    members = tuple(
        _member(f"peer_too_few_{index}", candidate=candidate)
        for index in range(STAGE6C_MINIMUM_PEERS - 1)
    )
    result = build_stage6c_peer_basket(
        candidate, _snapshot(candidate, members), capability=_capability(repository_root)
    )

    assert result.status is Stage6CPeerBasketStatus.INSUFFICIENT_EVIDENCE
    assert result.fallback_level is Stage6CPeerFallbackLevel.INSUFFICIENT_PEERS
    assert result.peer_count == 0
    assert result.peer_weights == ()
    assert result.failure_reasons == ("PEER_COUNT_BELOW_5",)


def test_stage6c_peer_basket_uses_size_only_third_fallback(repository_root: Path) -> None:
    candidate = next(
        value for value in _champion_inventory().candidates if value.calendar_year == 2022
    )
    members = tuple(
        _member(
            f"peer_size_only_{index}",
            candidate=candidate,
            industry="other_industry",
            beta_quintile=4,
        )
        for index in range(5)
    )
    result = build_stage6c_peer_basket(
        candidate, _snapshot(candidate, members), capability=_capability(repository_root)
    )

    assert result.status is Stage6CPeerBasketStatus.READY
    assert result.fallback_level is Stage6CPeerFallbackLevel.SAME_SIZE_ALL_A_SHARE
    assert result.peer_count == 5


def test_stage6c_peer_snapshot_rejects_future_or_outcome_bearing_member() -> None:
    candidate = next(
        value for value in _champion_inventory().candidates if value.calendar_year == 2022
    )
    future = replace(
        _member("peer_future", candidate=candidate),
        available_at=candidate.decision_time + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="available_at exceeds"):
        _snapshot(candidate, (future,))
    with pytest.raises(ValueError, match="outcome-blind"):
        replace(_member("peer_outcome", candidate=candidate), outcome_fields_present=True)


def _basket_set_sources(
    repository_root: Path,
) -> tuple[
    ApprovedRuleCapability,
    Stage6CCandidateInventory,
    Stage6CFoldPlanSet,
    tuple[Stage6CPeerSnapshot, ...],
]:
    capability = _capability(repository_root)
    inventory = _champion_inventory()
    folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    evaluation_ids = {
        candidate_id for fold in folds.folds for candidate_id in fold.evaluation_candidate_ids
    }
    snapshots = tuple(
        _snapshot(
            candidate,
            tuple(
                _member(f"peer_{candidate.candidate_id}_{index}", candidate=candidate)
                for index in range(5)
            ),
        )
        for candidate in inventory.candidates
        if candidate.candidate_id in evaluation_ids
    )
    return capability, inventory, folds, snapshots


def test_stage6c_peer_basket_set_preserves_every_evaluation_candidate(
    repository_root: Path,
) -> None:
    capability, inventory, folds, snapshots = _basket_set_sources(repository_root)
    first = build_stage6c_peer_basket_set(inventory, folds, snapshots, capability=capability)
    second = build_stage6c_peer_basket_set(
        inventory, folds, tuple(reversed(snapshots)), capability=capability
    )

    assert first == second
    assert len(first.baskets) == 32
    assert first.ready_count == 32
    assert first.insufficient_count == 0
    assert first.all_evaluation_candidates_covered is True

    with pytest.raises(ValueError, match="every evaluation candidate exactly once"):
        build_stage6c_peer_basket_set(inventory, folds, snapshots[:-1], capability=capability)


def _experiment_sources() -> tuple[
    HashDigest,
    datetime,
    tuple[Stage6CExperimentRegistration, ...],
    tuple[Stage6CExperimentOutcome, ...],
]:
    parent = _digest("1")
    registered_at = datetime(2026, 8, 20, tzinfo=UTC)
    registrations: list[Stage6CExperimentRegistration] = []
    for scenario_id in STAGE6C_REQUIRED_ABLATION_IDS:
        registrations.append(
            Stage6CExperimentRegistration.create(
                experiment_id=scenario_id,
                kind=Stage6CExperimentKind.ABLATION,
                scenario_id=scenario_id,
                parent_preregistration_hash=parent,
                registered_at=registered_at,
            )
        )
    for scenario_id in STAGE6C_REQUIRED_STRESS_IDS:
        registrations.append(
            Stage6CExperimentRegistration.create(
                experiment_id=scenario_id,
                kind=Stage6CExperimentKind.STRESS,
                scenario_id=scenario_id,
                parent_preregistration_hash=parent,
                registered_at=registered_at,
            )
        )
    outcomes = tuple(
        Stage6CExperimentOutcome.create(
            experiment_id=value.experiment_id,
            registration_hash=value.registration_hash,
            source_replay_hash=_digest("2"),
            status=Stage6CExperimentOutcomeStatus.COMPLETED,
            result_summary_hash=_digest("3"),
        )
        for value in registrations
    )
    return parent, registered_at + timedelta(hours=1), tuple(registrations), outcomes


def test_stage6c_experiment_ledger_is_complete_pre_registered_and_deterministic(
    repository_root: Path,
) -> None:
    parent, started, registrations, outcomes = _experiment_sources()
    capability = _capability(repository_root)
    first = build_stage6c_experiment_ledger(
        registrations,
        outcomes,
        parent_preregistration_hash=parent,
        execution_started_at=started,
        capability=capability,
    )
    second = build_stage6c_experiment_ledger(
        tuple(reversed(registrations)),
        tuple(reversed(outcomes)),
        parent_preregistration_hash=parent,
        execution_started_at=started,
        capability=capability,
    )

    assert first == second
    assert first.required_ablation_complete is True
    assert first.required_stress_complete is True
    assert first.exploratory_count == 0
    assert len(first.registrations) == 24
    assert len(first.outcomes) == 24
    assert first.holdout_artifact_read is False
    assert first.persists_state is False
    assert first.authority_eligible is False


def test_stage6c_experiment_ledger_rejects_missing_or_posthoc_registration(
    repository_root: Path,
) -> None:
    parent, started, registrations, outcomes = _experiment_sources()
    capability = _capability(repository_root)
    with pytest.raises(ValueError, match="required stress closed world differs"):
        build_stage6c_experiment_ledger(
            registrations[:-1],
            outcomes[:-1],
            parent_preregistration_hash=parent,
            execution_started_at=started,
            capability=capability,
        )
    late = Stage6CExperimentRegistration.create(
        experiment_id=registrations[0].experiment_id,
        kind=registrations[0].kind,
        scenario_id=registrations[0].scenario_id,
        parent_preregistration_hash=parent,
        registered_at=started,
    )
    with pytest.raises(ValueError, match="registered before execution"):
        build_stage6c_experiment_ledger(
            (late, *registrations[1:]),
            outcomes,
            parent_preregistration_hash=parent,
            execution_started_at=started,
            capability=capability,
        )


def test_stage6c_exploratory_registration_can_never_enter_current_champion() -> None:
    registration = Stage6CExperimentRegistration.create(
        experiment_id="exploratory_fixture",
        kind=Stage6CExperimentKind.EXPLORATORY,
        scenario_id="exploratory_fixture",
        parent_preregistration_hash=_digest("4"),
        registered_at=datetime(2026, 8, 20, tzinfo=UTC),
    )
    assert registration.performance_visible_at_registration is False
    assert registration.may_enter_current_champion is False
    with pytest.raises(ValueError, match="pre-performance diagnostic"):
        replace(
            registration,
            may_enter_current_champion=True,
            registration_hash=registration.registration_hash,
        )
