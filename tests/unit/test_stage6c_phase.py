from __future__ import annotations

from dataclasses import replace
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from invest_system.strategies.industrial_event import (
    Stage6CExperimentOutcome,
    Stage6CExperimentOutcomeStatus,
    Stage6CExperimentRegistration,
    Stage6CPeerSnapshot,
    Stage6CSyntheticPhaseSourceBundle,
    Stage6CSyntheticPhaseStatus,
    evaluate_stage6c_synthetic_phase,
)

_CHAMPION_SUPPORT = import_module("tests.unit.test_stage6c_champion")
_PEER_SUPPORT = import_module("tests.unit.test_stage6c_peer_experiments")
_champion_sources = _CHAMPION_SUPPORT._sources
_peer_sources = _PEER_SUPPORT._basket_set_sources
_experiment_sources = _PEER_SUPPORT._experiment_sources
_member = _PEER_SUPPORT._member
_snapshot = _PEER_SUPPORT._snapshot


def _source_bundle(
    repository_root: Path,
) -> tuple[dict[str, Any], Stage6CSyntheticPhaseSourceBundle]:
    values = _champion_sources(repository_root)
    _, peer_inventory, peer_folds, snapshots = _peer_sources(repository_root)
    assert peer_inventory == values["inventory"]
    assert peer_folds == values["folds"]
    parent, started, registrations, outcomes = _experiment_sources()
    source = Stage6CSyntheticPhaseSourceBundle.create(
        source_bundle_id="stage6c_synthetic_phase_source",
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
        champion_case=values["champion_case"],
        peer_snapshots=snapshots,
        parent_preregistration_hash=parent,
        experiment_execution_started_at=started,
        experiment_registrations=registrations,
        experiment_outcomes=outcomes,
    )
    values.update(
        {
            "peer_snapshots": snapshots,
            "parent": parent,
            "started": started,
            "registrations": registrations,
            "outcomes": outcomes,
        }
    )
    return values, source


def _replace_source(
    values: dict[str, Any],
    *,
    source_bundle_id: str,
    peer_snapshots: tuple[Stage6CPeerSnapshot, ...] | None = None,
    registrations: tuple[Stage6CExperimentRegistration, ...] | None = None,
    outcomes: tuple[Stage6CExperimentOutcome, ...] | None = None,
) -> Stage6CSyntheticPhaseSourceBundle:
    return Stage6CSyntheticPhaseSourceBundle.create(
        source_bundle_id=source_bundle_id,
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
        champion_case=values["champion_case"],
        peer_snapshots=peer_snapshots or values["peer_snapshots"],
        parent_preregistration_hash=values["parent"],
        experiment_execution_started_at=values["started"],
        experiment_registrations=registrations or values["registrations"],
        experiment_outcomes=outcomes or values["outcomes"],
    )


def test_stage6c_synthetic_phase_recomputes_all_sources_and_seals(
    repository_root: Path,
) -> None:
    values, source = _source_bundle(repository_root)
    result = evaluate_stage6c_synthetic_phase(source, capability=values["capability"])

    assert result.status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_SEALED
    assert result.failure_reasons == ()
    assert result.champion_replay_hash is not None
    assert result.peer_basket_set_hash is not None
    assert result.experiment_ledger_hash is not None
    assert result.synthetic_phase_kernel_complete is True
    assert result.not_ready_for_6d_freeze is True
    assert result.not_a_real_6d_request is True
    assert result.real_holdout_commitment_read is False
    assert result.holdout_artifact_read is False
    assert result.formal_historical_run is False
    assert result.persists_state is False
    assert result.authority_eligible is False
    with pytest.raises(ValueError, match="phase seal scope differs"):
        replace(
            result,
            not_ready_for_6d_freeze=False,
            seal_hash=result.seal_hash,
        )


def test_stage6c_synthetic_phase_stops_before_champion_when_peers_insufficient(
    repository_root: Path,
) -> None:
    values, _ = _source_bundle(repository_root)
    snapshots = list(values["peer_snapshots"])
    candidate = next(
        value
        for value in values["inventory"].candidates
        if value.candidate_id == snapshots[0].candidate_id
    )
    snapshots[0] = _snapshot(
        candidate,
        tuple(_member(f"insufficient_peer_{index}", candidate=candidate) for index in range(4)),
    )
    source = _replace_source(
        values,
        source_bundle_id="stage6c_phase_peer_insufficient",
        peer_snapshots=tuple(snapshots),
    )
    result = evaluate_stage6c_synthetic_phase(source, capability=values["capability"])

    assert result.status is (Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE)
    assert result.failure_reasons == ("PEER_BASKET_INSUFFICIENT",)
    assert result.champion_replay_hash is None
    assert result.peer_basket_set_hash is not None
    assert result.experiment_ledger_hash is None


def test_stage6c_synthetic_phase_maps_failed_experiment_to_revise(
    repository_root: Path,
) -> None:
    values, _ = _source_bundle(repository_root)
    outcomes = list(values["outcomes"])
    original = outcomes[0]
    outcomes[0] = Stage6CExperimentOutcome.create(
        experiment_id=original.experiment_id,
        registration_hash=original.registration_hash,
        source_replay_hash=original.source_replay_hash,
        status=Stage6CExperimentOutcomeStatus.FAILED,
        result_summary_hash=original.result_summary_hash,
    )
    source = _replace_source(
        values,
        source_bundle_id="stage6c_phase_experiment_failed",
        outcomes=tuple(outcomes),
    )
    result = evaluate_stage6c_synthetic_phase(source, capability=values["capability"])

    assert result.status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_REVISE_REQUIRED
    assert result.failure_reasons == ("EXPERIMENT_OUTCOME_NOT_COMPLETED",)
    assert result.champion_replay_hash is None
    assert result.peer_basket_set_hash is not None
    assert result.experiment_ledger_hash is not None


def test_stage6c_synthetic_phase_blocks_incomplete_experiment_sources(
    repository_root: Path,
) -> None:
    values, _ = _source_bundle(repository_root)
    source = _replace_source(
        values,
        source_bundle_id="stage6c_phase_experiment_incomplete",
        registrations=values["registrations"][:-1],
        outcomes=values["outcomes"][:-1],
    )
    result = evaluate_stage6c_synthetic_phase(source, capability=values["capability"])

    assert result.status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_PRECHECK_BLOCKED
    assert result.failure_reasons == ("EXPERIMENT_SOURCE_INVALID",)
    assert result.champion_replay_hash is None


def test_stage6c_synthetic_phase_contract_rejects_real_holdout_or_authority_claim() -> None:
    values, source = _source_bundle(Path(__file__).resolve().parents[2])
    with pytest.raises(ValueError, match="exceeded authority"):
        replace(
            source,
            real_holdout_commitment_read=True,
            source_bundle_hash=source.source_bundle_hash,
        )
    reordered = _replace_source(
        values,
        source_bundle_id=source.source_bundle_id,
        peer_snapshots=tuple(reversed(values["peer_snapshots"])),
        registrations=tuple(reversed(values["registrations"])),
        outcomes=tuple(reversed(values["outcomes"])),
    )
    assert reordered == source
