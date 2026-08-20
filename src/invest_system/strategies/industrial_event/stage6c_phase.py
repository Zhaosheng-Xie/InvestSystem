"""Unified anonymous synthetic Stage 6C phase seal orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.models import CanonicalModel, HashDigest

from .stage6c_candidate_coverage import (
    Stage6CCandidateInventory,
    Stage6CCoverageAuditResult,
    Stage6CFoldPlanSet,
)
from .stage6c_champion import (
    Stage6CSyntheticAuditAttestation,
    Stage6CSyntheticChampionCase,
    Stage6CSyntheticChampionStatus,
    Stage6CSyntheticCompletionAttestation,
    Stage6CSyntheticFrictionAttestation,
    evaluate_stage6c_synthetic_champion_gate,
)
from .stage6c_inference import Stage6CInferenceCase
from .stage6c_peer_experiments import (
    Stage6CExperimentOutcome,
    Stage6CExperimentOutcomeStatus,
    Stage6CExperimentRegistration,
    Stage6CPeerSnapshot,
    build_stage6c_experiment_ledger,
    build_stage6c_peer_basket_set,
)
from .stage6c_synthetic_kernel import (
    STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    require_stage6c_synthetic_capability,
)


class Stage6CSyntheticPhaseStatus(StrEnum):
    SYNTHETIC_PHASE_SEALED = "SYNTHETIC_PHASE_SEALED"
    SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE = "SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE"
    SYNTHETIC_PHASE_REVISE_REQUIRED = "SYNTHETIC_PHASE_REVISE_REQUIRED"
    SYNTHETIC_PHASE_PRECHECK_BLOCKED = "SYNTHETIC_PHASE_PRECHECK_BLOCKED"


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticPhaseSourceBundle(CanonicalModel):
    schema_version: str
    source_bundle_id: str
    inventory: Stage6CCandidateInventory
    fold_plans: Stage6CFoldPlanSet
    coverage: Stage6CCoverageAuditResult
    fold_twr_cases: tuple[Stage6CSyntheticKernelCase, ...]
    fold_twr_results: tuple[Stage6CSyntheticKernelResult, ...]
    inference_cases: tuple[Stage6CInferenceCase, ...]
    inference_twr_cases: tuple[Stage6CSyntheticKernelCase, ...]
    inference_twr_results: tuple[Stage6CSyntheticKernelResult, ...]
    friction_twr_case: Stage6CSyntheticKernelCase
    friction_twr_result: Stage6CSyntheticKernelResult
    friction_attestation: Stage6CSyntheticFrictionAttestation
    completion_attestation: Stage6CSyntheticCompletionAttestation
    audit_attestation: Stage6CSyntheticAuditAttestation
    champion_case: Stage6CSyntheticChampionCase
    peer_snapshots: tuple[Stage6CPeerSnapshot, ...]
    parent_preregistration_hash: HashDigest
    experiment_execution_started_at: datetime
    experiment_registrations: tuple[Stage6CExperimentRegistration, ...]
    experiment_outcomes: tuple[Stage6CExperimentOutcome, ...]
    synthetic: bool
    validation_only: bool
    real_holdout_commitment_read: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    source_bundle_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported phase source schema_version")
        if not isinstance(self.source_bundle_id, str) or not self.source_bundle_id:
            raise ValueError("source_bundle_id must be non-empty")
        if not isinstance(self.inventory, Stage6CCandidateInventory):
            raise TypeError("inventory must be Stage6CCandidateInventory")
        if not isinstance(self.fold_plans, Stage6CFoldPlanSet):
            raise TypeError("fold_plans must be Stage6CFoldPlanSet")
        if not isinstance(self.coverage, Stage6CCoverageAuditResult):
            raise TypeError("coverage must be Stage6CCoverageAuditResult")
        for field_name, expected_count, expected_type in (
            ("fold_twr_cases", 4, Stage6CSyntheticKernelCase),
            ("fold_twr_results", 4, Stage6CSyntheticKernelResult),
            ("inference_cases", 5, Stage6CInferenceCase),
            ("inference_twr_cases", 5, Stage6CSyntheticKernelCase),
            ("inference_twr_results", 5, Stage6CSyntheticKernelResult),
        ):
            values = tuple(getattr(self, field_name))
            if len(values) != expected_count or any(
                not isinstance(value, expected_type) for value in values
            ):
                raise ValueError(f"{field_name} shape differs")
            object.__setattr__(self, field_name, values)
        single_source_types: tuple[tuple[str, type[Any]], ...] = (
            ("friction_twr_case", Stage6CSyntheticKernelCase),
            ("friction_twr_result", Stage6CSyntheticKernelResult),
            ("friction_attestation", Stage6CSyntheticFrictionAttestation),
            ("completion_attestation", Stage6CSyntheticCompletionAttestation),
            ("audit_attestation", Stage6CSyntheticAuditAttestation),
            ("champion_case", Stage6CSyntheticChampionCase),
        )
        for field_name, expected_type in single_source_types:
            if not isinstance(getattr(self, field_name), expected_type):
                raise TypeError(f"{field_name} type differs")
        snapshots = tuple(sorted(self.peer_snapshots, key=lambda value: value.candidate_id))
        if not snapshots or any(not isinstance(value, Stage6CPeerSnapshot) for value in snapshots):
            raise ValueError("peer_snapshots must contain typed values")
        object.__setattr__(self, "peer_snapshots", snapshots)
        if not isinstance(self.parent_preregistration_hash, HashDigest):
            raise TypeError("parent_preregistration_hash must be HashDigest")
        object.__setattr__(
            self,
            "experiment_execution_started_at",
            normalize_utc(
                self.experiment_execution_started_at,
                field_name="experiment_execution_started_at",
            ),
        )
        registrations = tuple(
            sorted(self.experiment_registrations, key=lambda value: value.experiment_id)
        )
        outcomes = tuple(sorted(self.experiment_outcomes, key=lambda value: value.experiment_id))
        if not registrations or any(
            not isinstance(value, Stage6CExperimentRegistration) for value in registrations
        ):
            raise ValueError("experiment_registrations must contain typed values")
        if not outcomes or any(
            not isinstance(value, Stage6CExperimentOutcome) for value in outcomes
        ):
            raise ValueError("experiment_outcomes must contain typed values")
        object.__setattr__(self, "experiment_registrations", registrations)
        object.__setattr__(self, "experiment_outcomes", outcomes)
        for field_name in (
            "synthetic",
            "validation_only",
            "real_holdout_commitment_read",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if not self.synthetic or not self.validation_only:
            raise ValueError("phase source must remain anonymous synthetic validation")
        if (
            self.real_holdout_commitment_read
            or self.holdout_artifact_read
            or self.persists_state
            or self.authority_eligible
        ):
            raise ValueError("phase source exceeded authority boundary")
        if not isinstance(self.source_bundle_hash, HashDigest) or self.source_bundle_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("source_bundle_hash differs")

    @classmethod
    def create(
        cls,
        *,
        source_bundle_id: str,
        inventory: Stage6CCandidateInventory,
        fold_plans: Stage6CFoldPlanSet,
        coverage: Stage6CCoverageAuditResult,
        fold_twr_cases: tuple[Stage6CSyntheticKernelCase, ...],
        fold_twr_results: tuple[Stage6CSyntheticKernelResult, ...],
        inference_cases: tuple[Stage6CInferenceCase, ...],
        inference_twr_cases: tuple[Stage6CSyntheticKernelCase, ...],
        inference_twr_results: tuple[Stage6CSyntheticKernelResult, ...],
        friction_twr_case: Stage6CSyntheticKernelCase,
        friction_twr_result: Stage6CSyntheticKernelResult,
        friction_attestation: Stage6CSyntheticFrictionAttestation,
        completion_attestation: Stage6CSyntheticCompletionAttestation,
        audit_attestation: Stage6CSyntheticAuditAttestation,
        champion_case: Stage6CSyntheticChampionCase,
        peer_snapshots: tuple[Stage6CPeerSnapshot, ...],
        parent_preregistration_hash: HashDigest,
        experiment_execution_started_at: datetime,
        experiment_registrations: tuple[Stage6CExperimentRegistration, ...],
        experiment_outcomes: tuple[Stage6CExperimentOutcome, ...],
    ) -> Stage6CSyntheticPhaseSourceBundle:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "source_bundle_id": source_bundle_id,
            "inventory": inventory,
            "fold_plans": fold_plans,
            "coverage": coverage,
            "fold_twr_cases": fold_twr_cases,
            "fold_twr_results": fold_twr_results,
            "inference_cases": inference_cases,
            "inference_twr_cases": inference_twr_cases,
            "inference_twr_results": inference_twr_results,
            "friction_twr_case": friction_twr_case,
            "friction_twr_result": friction_twr_result,
            "friction_attestation": friction_attestation,
            "completion_attestation": completion_attestation,
            "audit_attestation": audit_attestation,
            "champion_case": champion_case,
            "peer_snapshots": tuple(sorted(peer_snapshots, key=lambda value: value.candidate_id)),
            "parent_preregistration_hash": parent_preregistration_hash,
            "experiment_execution_started_at": normalize_utc(
                experiment_execution_started_at,
                field_name="experiment_execution_started_at",
            ),
            "experiment_registrations": tuple(
                sorted(experiment_registrations, key=lambda value: value.experiment_id)
            ),
            "experiment_outcomes": tuple(
                sorted(experiment_outcomes, key=lambda value: value.experiment_id)
            ),
            "synthetic": True,
            "validation_only": True,
            "real_holdout_commitment_read": False,
            "holdout_artifact_read": False,
            "persists_state": False,
            "authority_eligible": False,
        }
        return cls(**payload, source_bundle_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "source_bundle_id",
                "inventory",
                "fold_plans",
                "coverage",
                "fold_twr_cases",
                "fold_twr_results",
                "inference_cases",
                "inference_twr_cases",
                "inference_twr_results",
                "friction_twr_case",
                "friction_twr_result",
                "friction_attestation",
                "completion_attestation",
                "audit_attestation",
                "champion_case",
                "peer_snapshots",
                "parent_preregistration_hash",
                "experiment_execution_started_at",
                "experiment_registrations",
                "experiment_outcomes",
                "synthetic",
                "validation_only",
                "real_holdout_commitment_read",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticPhaseSeal(CanonicalModel):
    schema_version: str
    source_bundle_hash: HashDigest
    status: Stage6CSyntheticPhaseStatus
    failure_reasons: tuple[str, ...]
    champion_replay_hash: HashDigest | None
    peer_basket_set_hash: HashDigest | None
    experiment_ledger_hash: HashDigest | None
    synthetic: bool
    validation_only: bool
    synthetic_phase_kernel_complete: bool
    not_ready_for_6d_freeze: bool
    not_a_real_6d_request: bool
    real_holdout_commitment_read: bool
    holdout_artifact_read: bool
    formal_historical_run: bool
    persists_state: bool
    authority_eligible: bool
    seal_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported phase seal schema_version")
        if not isinstance(self.source_bundle_hash, HashDigest):
            raise TypeError("source_bundle_hash must be HashDigest")
        object.__setattr__(self, "status", Stage6CSyntheticPhaseStatus(self.status))
        reasons = tuple(sorted(set(self.failure_reasons)))
        if tuple(self.failure_reasons) != reasons:
            raise ValueError("failure_reasons must be sorted and unique")
        object.__setattr__(self, "failure_reasons", reasons)
        if self.status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_SEALED:
            if reasons or any(
                value is None
                for value in (
                    self.champion_replay_hash,
                    self.peer_basket_set_hash,
                    self.experiment_ledger_hash,
                )
            ):
                raise ValueError("sealed synthetic phase requires all child hashes")
        elif not reasons:
            raise ValueError("non-sealed synthetic phase requires failure reasons")
        for field_name in (
            "synthetic",
            "validation_only",
            "synthetic_phase_kernel_complete",
            "not_ready_for_6d_freeze",
            "not_a_real_6d_request",
            "real_holdout_commitment_read",
            "holdout_artifact_read",
            "formal_historical_run",
            "persists_state",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if (
            not self.synthetic
            or not self.validation_only
            or not self.not_ready_for_6d_freeze
            or (not self.not_a_real_6d_request)
        ):
            raise ValueError("phase seal scope differs")
        if (
            self.real_holdout_commitment_read
            or self.holdout_artifact_read
            or self.formal_historical_run
            or self.persists_state
            or self.authority_eligible
        ):
            raise ValueError("phase seal exceeded authority boundary")
        expected_complete = self.status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_SEALED
        if self.synthetic_phase_kernel_complete != expected_complete:
            raise ValueError("synthetic_phase_kernel_complete differs from status")
        if not isinstance(self.seal_hash, HashDigest) or self.seal_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("phase seal_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "source_bundle_hash",
                "status",
                "failure_reasons",
                "champion_replay_hash",
                "peer_basket_set_hash",
                "experiment_ledger_hash",
                "synthetic",
                "validation_only",
                "synthetic_phase_kernel_complete",
                "not_ready_for_6d_freeze",
                "not_a_real_6d_request",
                "real_holdout_commitment_read",
                "holdout_artifact_read",
                "formal_historical_run",
                "persists_state",
                "authority_eligible",
            )
        }


def _seal(
    source: Stage6CSyntheticPhaseSourceBundle,
    *,
    status: Stage6CSyntheticPhaseStatus,
    reasons: tuple[str, ...],
    champion_hash: HashDigest | None = None,
    peer_hash: HashDigest | None = None,
    experiment_hash: HashDigest | None = None,
) -> Stage6CSyntheticPhaseSeal:
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "source_bundle_hash": source.source_bundle_hash,
        "status": status,
        "failure_reasons": tuple(sorted(set(reasons))),
        "champion_replay_hash": champion_hash,
        "peer_basket_set_hash": peer_hash,
        "experiment_ledger_hash": experiment_hash,
        "synthetic": True,
        "validation_only": True,
        "synthetic_phase_kernel_complete": (
            status is Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_SEALED
        ),
        "not_ready_for_6d_freeze": True,
        "not_a_real_6d_request": True,
        "real_holdout_commitment_read": False,
        "holdout_artifact_read": False,
        "formal_historical_run": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CSyntheticPhaseSeal(**payload, seal_hash=_hash(payload))


def evaluate_stage6c_synthetic_phase(
    source: Stage6CSyntheticPhaseSourceBundle,
    *,
    capability: ApprovedRuleCapability,
) -> Stage6CSyntheticPhaseSeal:
    """Recompute all raw synthetic slices and issue a non-authoritative seal."""

    if not isinstance(source, Stage6CSyntheticPhaseSourceBundle):
        raise TypeError("source must be Stage6CSyntheticPhaseSourceBundle")
    require_stage6c_synthetic_capability(capability)
    try:
        peer_set = build_stage6c_peer_basket_set(
            source.inventory,
            source.fold_plans,
            source.peer_snapshots,
            capability=capability,
        )
    except (TypeError, ValueError):
        return _seal(
            source,
            status=Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_PRECHECK_BLOCKED,
            reasons=("PEER_SOURCE_INVALID",),
        )
    if peer_set.insufficient_count:
        return _seal(
            source,
            status=Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE,
            reasons=("PEER_BASKET_INSUFFICIENT",),
            peer_hash=peer_set.basket_set_hash,
        )
    try:
        experiment_ledger = build_stage6c_experiment_ledger(
            source.experiment_registrations,
            source.experiment_outcomes,
            parent_preregistration_hash=source.parent_preregistration_hash,
            execution_started_at=source.experiment_execution_started_at,
            capability=capability,
        )
    except (TypeError, ValueError):
        return _seal(
            source,
            status=Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_PRECHECK_BLOCKED,
            reasons=("EXPERIMENT_SOURCE_INVALID",),
            peer_hash=peer_set.basket_set_hash,
        )
    if any(
        value.status is not Stage6CExperimentOutcomeStatus.COMPLETED
        for value in experiment_ledger.outcomes
    ):
        return _seal(
            source,
            status=Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_REVISE_REQUIRED,
            reasons=("EXPERIMENT_OUTCOME_NOT_COMPLETED",),
            peer_hash=peer_set.basket_set_hash,
            experiment_hash=experiment_ledger.ledger_hash,
        )
    champion = evaluate_stage6c_synthetic_champion_gate(
        source.champion_case,
        inventory=source.inventory,
        fold_plans=source.fold_plans,
        coverage=source.coverage,
        fold_twr_cases=source.fold_twr_cases,
        fold_twr_results=source.fold_twr_results,
        inference_cases=source.inference_cases,
        inference_twr_cases=source.inference_twr_cases,
        inference_twr_results=source.inference_twr_results,
        friction_twr_case=source.friction_twr_case,
        friction_twr_result=source.friction_twr_result,
        friction_attestation=source.friction_attestation,
        completion_attestation=source.completion_attestation,
        audit_attestation=source.audit_attestation,
        capability=capability,
    )
    mapping = {
        Stage6CSyntheticChampionStatus.GATE_FORMULA_PASSED: (
            Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_SEALED,
            (),
        ),
        Stage6CSyntheticChampionStatus.INSUFFICIENT_EVIDENCE: (
            Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_INSUFFICIENT_EVIDENCE,
            tuple(f"CHAMPION_{value}" for value in champion.failure_reasons),
        ),
        Stage6CSyntheticChampionStatus.REVISE_REQUIRED: (
            Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_REVISE_REQUIRED,
            tuple(f"CHAMPION_{value}" for value in champion.failure_reasons),
        ),
        Stage6CSyntheticChampionStatus.PRECHECK_BLOCKED: (
            Stage6CSyntheticPhaseStatus.SYNTHETIC_PHASE_PRECHECK_BLOCKED,
            tuple(f"CHAMPION_{value}" for value in champion.failure_reasons),
        ),
    }
    status, reasons = mapping[champion.status]
    return _seal(
        source,
        status=status,
        reasons=reasons,
        champion_hash=champion.replay_hash,
        peer_hash=peer_set.basket_set_hash,
        experiment_hash=experiment_ledger.ledger_hash,
    )


__all__ = [
    "Stage6CSyntheticPhaseSeal",
    "Stage6CSyntheticPhaseSourceBundle",
    "Stage6CSyntheticPhaseStatus",
    "evaluate_stage6c_synthetic_phase",
]
