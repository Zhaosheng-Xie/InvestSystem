"""Anonymous synthetic Stage 6C champion-gate orchestration kernel."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from typing import Any

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import ApprovedRuleCapability
from invest_system.models import CanonicalModel, HashDigest

from .stage6c_candidate_coverage import (
    Stage6CCandidateDisposition,
    Stage6CCandidateInventory,
    Stage6CCoverageAuditResult,
    Stage6CCoverageAuditStatus,
    Stage6CFoldPlanSet,
    evaluate_stage6c_synthetic_coverage,
    plan_stage6c_synthetic_folds,
)
from .stage6c_inference import (
    Stage6CComparisonId,
    Stage6CHolmStatus,
    Stage6CInferenceCase,
    Stage6CInferenceResult,
    _evaluate_stage6c_holm_family_details,
)
from .stage6c_synthetic_kernel import (
    STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    Stage6CSyntheticKernelStatus,
    evaluate_stage6c_synthetic_twr_kernel,
    require_stage6c_synthetic_capability,
)

_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)


class Stage6CSyntheticChampionStatus(StrEnum):
    GATE_FORMULA_PASSED = "GATE_FORMULA_PASSED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    REVISE_REQUIRED = "REVISE_REQUIRED"
    PRECHECK_BLOCKED = "PRECHECK_BLOCKED"


@dataclass(frozen=True, slots=True)
class Stage6CFoldTwrBinding(CanonicalModel):
    fold_id: str
    twr_case_hash: HashDigest
    twr_replay_hash: HashDigest

    def __post_init__(self) -> None:
        if not isinstance(self.fold_id, str) or not self.fold_id:
            raise ValueError("fold_id must be non-empty")
        if not isinstance(self.twr_case_hash, HashDigest) or not isinstance(
            self.twr_replay_hash, HashDigest
        ):
            raise TypeError("fold TWR hashes must be HashDigest")


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticCompletionAttestation(CanonicalModel):
    schema_version: str
    attestation_id: str
    completed_candidate_ids: tuple[str, ...]
    source_test_report_hash: HashDigest
    synthetic: bool
    validation_only: bool
    not_a_real_trade_completion_record: bool
    authority_eligible: bool
    attestation_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported completion attestation schema_version")
        if not isinstance(self.attestation_id, str) or not self.attestation_id:
            raise ValueError("attestation_id must be non-empty")
        ids = tuple(self.completed_candidate_ids)
        if ids != tuple(sorted(ids)) or len(ids) != len(set(ids)):
            raise ValueError("completed_candidate_ids must be sorted and unique")
        object.__setattr__(self, "completed_candidate_ids", ids)
        if not isinstance(self.source_test_report_hash, HashDigest):
            raise TypeError("source_test_report_hash must be HashDigest")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_real_trade_completion_record",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if (
            not self.synthetic
            or not self.validation_only
            or (not self.not_a_real_trade_completion_record)
        ):
            raise ValueError("completion attestation must remain anonymous synthetic")
        if self.authority_eligible:
            raise ValueError("completion attestation must remain authority-ineligible")
        if not isinstance(self.attestation_hash, HashDigest) or self.attestation_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("completion attestation_hash differs")

    @classmethod
    def create(
        cls,
        *,
        attestation_id: str,
        completed_candidate_ids: tuple[str, ...],
        source_test_report_hash: HashDigest,
    ) -> Stage6CSyntheticCompletionAttestation:
        ordered = tuple(sorted(completed_candidate_ids))
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "attestation_id": attestation_id,
            "completed_candidate_ids": ordered,
            "source_test_report_hash": source_test_report_hash,
            "synthetic": True,
            "validation_only": True,
            "not_a_real_trade_completion_record": True,
            "authority_eligible": False,
        }
        return cls(**payload, attestation_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "attestation_id",
                "completed_candidate_ids",
                "source_test_report_hash",
                "synthetic",
                "validation_only",
                "not_a_real_trade_completion_record",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticFrictionAttestation(CanonicalModel):
    schema_version: str
    attestation_id: str
    friction_multiplier: str
    twr_case_hash: HashDigest
    twr_replay_hash: HashDigest
    source_test_report_hash: HashDigest
    synthetic: bool
    validation_only: bool
    not_a_real_friction_replay: bool
    authority_eligible: bool
    attestation_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported friction attestation schema_version")
        if not isinstance(self.attestation_id, str) or not self.attestation_id:
            raise ValueError("attestation_id must be non-empty")
        if self.friction_multiplier != "1.5":
            raise ValueError("friction_multiplier must be 1.5")
        for field_name in ("twr_case_hash", "twr_replay_hash", "source_test_report_hash"):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_real_friction_replay",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if not self.synthetic or not self.validation_only or not self.not_a_real_friction_replay:
            raise ValueError("friction attestation must remain anonymous synthetic")
        if self.authority_eligible:
            raise ValueError("friction attestation must remain authority-ineligible")
        if not isinstance(self.attestation_hash, HashDigest) or self.attestation_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("friction attestation_hash differs")

    @classmethod
    def create(
        cls,
        *,
        attestation_id: str,
        twr_case_hash: HashDigest,
        twr_replay_hash: HashDigest,
        source_test_report_hash: HashDigest,
    ) -> Stage6CSyntheticFrictionAttestation:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "attestation_id": attestation_id,
            "friction_multiplier": "1.5",
            "twr_case_hash": twr_case_hash,
            "twr_replay_hash": twr_replay_hash,
            "source_test_report_hash": source_test_report_hash,
            "synthetic": True,
            "validation_only": True,
            "not_a_real_friction_replay": True,
            "authority_eligible": False,
        }
        return cls(**payload, attestation_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "attestation_id",
                "friction_multiplier",
                "twr_case_hash",
                "twr_replay_hash",
                "source_test_report_hash",
                "synthetic",
                "validation_only",
                "not_a_real_friction_replay",
                "authority_eligible",
            )
        }


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except Exception as exc:  # pragma: no cover - inputs are already canonical
        raise ValueError("invalid decimal") from exc


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticAuditAttestation(CanonicalModel):
    schema_version: str
    attestation_id: str
    source_test_report_hash: HashDigest
    p0_bias_failure_count: int
    reconciliation_failure_count: int
    synthetic: bool
    validation_only: bool
    not_a_real_bias_audit: bool
    authority_eligible: bool
    attestation_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported audit attestation schema_version")
        if not isinstance(self.attestation_id, str) or not self.attestation_id:
            raise ValueError("attestation_id must be non-empty")
        if not isinstance(self.source_test_report_hash, HashDigest):
            raise TypeError("source_test_report_hash must be HashDigest")
        for field_name in ("p0_bias_failure_count", "reconciliation_failure_count"):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{field_name} must be non-negative integer")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_real_bias_audit",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if not self.synthetic or not self.validation_only or not self.not_a_real_bias_audit:
            raise ValueError("audit attestation must remain anonymous synthetic validation")
        if self.authority_eligible:
            raise ValueError("audit attestation must remain authority-ineligible")
        if not isinstance(self.attestation_hash, HashDigest) or self.attestation_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("attestation_hash differs")

    @classmethod
    def create(
        cls,
        *,
        attestation_id: str,
        source_test_report_hash: HashDigest,
        p0_bias_failure_count: int,
        reconciliation_failure_count: int,
    ) -> Stage6CSyntheticAuditAttestation:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "attestation_id": attestation_id,
            "source_test_report_hash": source_test_report_hash,
            "p0_bias_failure_count": p0_bias_failure_count,
            "reconciliation_failure_count": reconciliation_failure_count,
            "synthetic": True,
            "validation_only": True,
            "not_a_real_bias_audit": True,
            "authority_eligible": False,
        }
        return cls(**payload, attestation_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "attestation_id",
                "source_test_report_hash",
                "p0_bias_failure_count",
                "reconciliation_failure_count",
                "synthetic",
                "validation_only",
                "not_a_real_bias_audit",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticChampionCase(CanonicalModel):
    schema_version: str
    champion_case_id: str
    inventory_hash: HashDigest
    fold_plan_set_hash: HashDigest
    coverage_replay_hash: HashDigest
    fold_twr_bindings: tuple[Stage6CFoldTwrBinding, ...]
    inference_case_hashes: tuple[HashDigest, ...]
    inference_twr_case_hashes: tuple[HashDigest, ...]
    inference_twr_replay_hashes: tuple[HashDigest, ...]
    friction_attestation_hash: HashDigest
    completion_attestation_hash: HashDigest
    audit_attestation_hash: HashDigest
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    case_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported champion case schema_version")
        if not isinstance(self.champion_case_id, str) or not self.champion_case_id:
            raise ValueError("champion_case_id must be non-empty")
        for field_name in (
            "inventory_hash",
            "fold_plan_set_hash",
            "coverage_replay_hash",
            "friction_attestation_hash",
            "completion_attestation_hash",
            "audit_attestation_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        for field_name, expected_count in (
            ("inference_case_hashes", 5),
            ("inference_twr_case_hashes", 5),
            ("inference_twr_replay_hashes", 5),
        ):
            values = tuple(getattr(self, field_name))
            if (
                len(values) != expected_count
                or len(set(values)) != expected_count
                or any(not isinstance(value, HashDigest) for value in values)
            ):
                raise ValueError(f"{field_name} identity set differs")
            object.__setattr__(self, field_name, values)
        bindings = tuple(self.fold_twr_bindings)
        if (
            tuple(value.fold_id for value in bindings)
            != ("WF-2022", "WF-2023", "WF-2024", "WF-2025")
            or any(not isinstance(value, Stage6CFoldTwrBinding) for value in bindings)
            or len({value.twr_case_hash for value in bindings}) != 4
            or len({value.twr_replay_hash for value in bindings}) != 4
        ):
            raise ValueError("fold_twr_bindings differ from approved fold closed world")
        object.__setattr__(self, "fold_twr_bindings", bindings)
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if not self.synthetic or not self.validation_only:
            raise ValueError("champion case must be anonymous synthetic validation")
        if self.holdout_artifact_read or self.authority_eligible:
            raise ValueError("champion case exceeded authority boundary")
        if not isinstance(self.case_hash, HashDigest) or self.case_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("champion case_hash differs")

    @classmethod
    def create(
        cls,
        *,
        champion_case_id: str,
        inventory_hash: HashDigest,
        fold_plan_set_hash: HashDigest,
        coverage_replay_hash: HashDigest,
        fold_twr_bindings: tuple[Stage6CFoldTwrBinding, ...],
        inference_case_hashes: tuple[HashDigest, ...],
        inference_twr_case_hashes: tuple[HashDigest, ...],
        inference_twr_replay_hashes: tuple[HashDigest, ...],
        friction_attestation_hash: HashDigest,
        completion_attestation_hash: HashDigest,
        audit_attestation_hash: HashDigest,
    ) -> Stage6CSyntheticChampionCase:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "champion_case_id": champion_case_id,
            "inventory_hash": inventory_hash,
            "fold_plan_set_hash": fold_plan_set_hash,
            "coverage_replay_hash": coverage_replay_hash,
            "fold_twr_bindings": fold_twr_bindings,
            "inference_case_hashes": inference_case_hashes,
            "inference_twr_case_hashes": inference_twr_case_hashes,
            "inference_twr_replay_hashes": inference_twr_replay_hashes,
            "friction_attestation_hash": friction_attestation_hash,
            "completion_attestation_hash": completion_attestation_hash,
            "audit_attestation_hash": audit_attestation_hash,
            "synthetic": True,
            "validation_only": True,
            "holdout_artifact_read": False,
            "authority_eligible": False,
        }
        return cls(**payload, case_hash=_hash(payload))

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "champion_case_id",
                "inventory_hash",
                "fold_plan_set_hash",
                "coverage_replay_hash",
                "fold_twr_bindings",
                "inference_case_hashes",
                "inference_twr_case_hashes",
                "inference_twr_replay_hashes",
                "friction_attestation_hash",
                "completion_attestation_hash",
                "audit_attestation_hash",
                "synthetic",
                "validation_only",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CSyntheticChampionResult(CanonicalModel):
    schema_version: str
    case_hash: HashDigest
    status: Stage6CSyntheticChampionStatus
    failure_reasons: tuple[str, ...]
    completed_trade_count: int
    fold_completed_trade_counts: tuple[int, ...]
    fold_net_excess_percentage_points: tuple[str, ...]
    positive_fold_count: int
    worst_fold_net_excess_percentage_points: str | None
    full_net_benchmark_excess_percentage_points: str | None
    full_vs_best_simple_increment_percentage_points: str | None
    maximum_drawdown: str | None
    total_net_profit: str | None
    largest_winner_share: str | None
    friction_one_point_five_net_excess_percentage_points: str | None
    holm_replay_hash: HashDigest | None
    synthetic: bool
    validation_only: bool
    not_a_real_6d_request: bool
    not_a_complete_stage6c_walk_forward: bool
    formal_historical_run: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    replay_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported champion result schema_version")
        if not isinstance(self.case_hash, HashDigest):
            raise TypeError("case_hash must be HashDigest")
        object.__setattr__(self, "status", Stage6CSyntheticChampionStatus(self.status))
        reasons = tuple(sorted(set(self.failure_reasons)))
        if tuple(self.failure_reasons) != reasons:
            raise ValueError("failure_reasons must be sorted and unique")
        object.__setattr__(self, "failure_reasons", reasons)
        if self.status is Stage6CSyntheticChampionStatus.GATE_FORMULA_PASSED and reasons:
            raise ValueError("passed champion result cannot have failures")
        if self.status is not Stage6CSyntheticChampionStatus.GATE_FORMULA_PASSED and not reasons:
            raise ValueError("non-passed champion result requires failures")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_real_6d_request",
            "not_a_complete_stage6c_walk_forward",
            "formal_historical_run",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if (
            not self.synthetic
            or not self.validation_only
            or not self.not_a_real_6d_request
            or (not self.not_a_complete_stage6c_walk_forward)
        ):
            raise ValueError("champion result scope differs")
        if (
            self.formal_historical_run
            or self.holdout_artifact_read
            or self.persists_state
            or (self.authority_eligible)
        ):
            raise ValueError("champion result exceeded authority boundary")
        if not isinstance(self.replay_hash, HashDigest) or self.replay_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("champion replay_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "case_hash",
                "status",
                "failure_reasons",
                "completed_trade_count",
                "fold_completed_trade_counts",
                "fold_net_excess_percentage_points",
                "positive_fold_count",
                "worst_fold_net_excess_percentage_points",
                "full_net_benchmark_excess_percentage_points",
                "full_vs_best_simple_increment_percentage_points",
                "maximum_drawdown",
                "total_net_profit",
                "largest_winner_share",
                "friction_one_point_five_net_excess_percentage_points",
                "holm_replay_hash",
                "synthetic",
                "validation_only",
                "not_a_real_6d_request",
                "not_a_complete_stage6c_walk_forward",
                "formal_historical_run",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


def _maximum_drawdown(cases: tuple[Stage6CSyntheticKernelCase, ...]) -> Decimal:
    maximum = Decimal(0)
    for case in cases:
        high = Decimal(0)
        for point in case.nav_points:
            nav = _decimal(point.strategy_nav)
            high = max(high, nav)
            maximum = max(maximum, (high - nav) / high)
    return maximum


def _result(
    case: Stage6CSyntheticChampionCase,
    *,
    status: Stage6CSyntheticChampionStatus,
    reasons: tuple[str, ...],
    completed_trade_count: int = 0,
    fold_counts: tuple[int, ...] = (),
    fold_excess: tuple[str, ...] = (),
    full_excess: str | None = None,
    increment: str | None = None,
    drawdown: str | None = None,
    total_profit: str | None = None,
    winner_share: str | None = None,
    friction: str | None = None,
    holm_hash: HashDigest | None = None,
) -> Stage6CSyntheticChampionResult:
    values = tuple(_decimal(value) for value in fold_excess)
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "case_hash": case.case_hash,
        "status": status,
        "failure_reasons": tuple(sorted(set(reasons))),
        "completed_trade_count": completed_trade_count,
        "fold_completed_trade_counts": fold_counts,
        "fold_net_excess_percentage_points": fold_excess,
        "positive_fold_count": sum(value > 0 for value in values),
        "worst_fold_net_excess_percentage_points": (_decimal_text(min(values)) if values else None),
        "full_net_benchmark_excess_percentage_points": full_excess,
        "full_vs_best_simple_increment_percentage_points": increment,
        "maximum_drawdown": drawdown,
        "total_net_profit": total_profit,
        "largest_winner_share": winner_share,
        "friction_one_point_five_net_excess_percentage_points": friction,
        "holm_replay_hash": holm_hash,
        "synthetic": True,
        "validation_only": True,
        "not_a_real_6d_request": True,
        "not_a_complete_stage6c_walk_forward": True,
        "formal_historical_run": False,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CSyntheticChampionResult(**payload, replay_hash=_hash(payload))


def evaluate_stage6c_synthetic_champion_gate(
    case: Stage6CSyntheticChampionCase,
    *,
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
    capability: ApprovedRuleCapability,
) -> Stage6CSyntheticChampionResult:
    """Recompute every synthetic source and apply the approved champion formula."""

    if not isinstance(case, Stage6CSyntheticChampionCase):
        raise TypeError("case must be Stage6CSyntheticChampionCase")
    require_stage6c_synthetic_capability(capability)
    precheck: list[str] = []
    recomputed_folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    recomputed_coverage = evaluate_stage6c_synthetic_coverage(
        inventory, recomputed_folds, capability=capability
    )
    if fold_plans != recomputed_folds or case.fold_plan_set_hash != fold_plans.plan_set_hash:
        precheck.append("FOLD_SOURCE_MISMATCH")
    if coverage != recomputed_coverage or case.coverage_replay_hash != coverage.replay_hash:
        precheck.append("COVERAGE_SOURCE_MISMATCH")
    if case.inventory_hash != inventory.inventory_hash:
        precheck.append("INVENTORY_SOURCE_MISMATCH")
    if coverage.status is not Stage6CCoverageAuditStatus.COVERAGE_READY:
        precheck.append("COVERAGE_NOT_READY")
    if len(fold_twr_cases) != 4 or len(fold_twr_results) != 4:
        precheck.append("FOLD_TWR_COUNT_MISMATCH")
    recomputed_fold_results = tuple(
        evaluate_stage6c_synthetic_twr_kernel(source, capability=capability)
        for source in fold_twr_cases
    )
    expected_fold_bindings = (
        tuple(
            Stage6CFoldTwrBinding(
                fold_id=fold.fold_id,
                twr_case_hash=twr_case.case_hash,
                twr_replay_hash=twr_result.replay_hash,
            )
            for fold, twr_case, twr_result in zip(
                fold_plans.folds, fold_twr_cases, fold_twr_results, strict=True
            )
        )
        if len(fold_twr_cases) == len(fold_twr_results) == 4
        else ()
    )
    if tuple(fold_twr_results) != recomputed_fold_results or (
        case.fold_twr_bindings != expected_fold_bindings
    ):
        precheck.append("FOLD_TWR_SOURCE_MISMATCH")
    if any(
        value.status is not Stage6CSyntheticKernelStatus.TWR_RECONCILED
        for value in recomputed_fold_results
    ):
        precheck.append("FOLD_TWR_NOT_RECONCILED")
    recomputed_inference_twr = tuple(
        evaluate_stage6c_synthetic_twr_kernel(source, capability=capability)
        for source in inference_twr_cases
    )
    if (
        len(inference_twr_cases) != 5
        or len(inference_twr_results) != 5
        or tuple(inference_twr_results) != recomputed_inference_twr
        or case.inference_twr_case_hashes != tuple(value.case_hash for value in inference_twr_cases)
        or case.inference_twr_replay_hashes
        != tuple(value.replay_hash for value in inference_twr_results)
    ):
        precheck.append("INFERENCE_TWR_SOURCE_MISMATCH")
    if case.inference_case_hashes != tuple(value.case_hash for value in inference_cases):
        precheck.append("INFERENCE_CASE_SOURCE_MISMATCH")
    recomputed_friction = evaluate_stage6c_synthetic_twr_kernel(
        friction_twr_case, capability=capability
    )
    if friction_twr_result != recomputed_friction or (
        not isinstance(friction_attestation, Stage6CSyntheticFrictionAttestation)
        or case.friction_attestation_hash != friction_attestation.attestation_hash
        or friction_attestation.twr_case_hash != friction_twr_case.case_hash
        or friction_attestation.twr_replay_hash != friction_twr_result.replay_hash
    ):
        precheck.append("FRICTION_TWR_SOURCE_MISMATCH")
    if audit_attestation.attestation_hash != case.audit_attestation_hash:
        precheck.append("AUDIT_ATTESTATION_SOURCE_MISMATCH")
    if not isinstance(completion_attestation, Stage6CSyntheticCompletionAttestation) or (
        completion_attestation.attestation_hash != case.completion_attestation_hash
    ):
        precheck.append("COMPLETION_ATTESTATION_SOURCE_MISMATCH")
    evaluation_ids_by_fold = tuple(set(plan.evaluation_candidate_ids) for plan in fold_plans.folds)
    eligible_completed_ids = {
        candidate.candidate_id
        for candidate in inventory.candidates
        if candidate.supported
        and candidate.disposition is Stage6CCandidateDisposition.TRADE_READY
        and any(candidate.candidate_id in values for values in evaluation_ids_by_fold)
    }
    completed_ids = set(completion_attestation.completed_candidate_ids)
    if not completed_ids <= eligible_completed_ids:
        precheck.append("COMPLETION_ATTESTATION_CONTAINS_INELIGIBLE_CANDIDATE")
    no_trade_case = next(
        (
            value
            for value in inference_cases
            if value.comparison_id is Stage6CComparisonId.FULL_VS_NO_TRADE
        ),
        None,
    )
    if no_trade_case is None:
        precheck.append("NO_TRADE_INFERENCE_CASE_MISSING")
    elif any(
        contribution.candidate_id not in completed_ids
        and (
            _decimal(contribution.full_net_contribution) != 0
            or _decimal(contribution.comparator_net_contribution) != 0
        )
        for contribution in no_trade_case.contributions
    ):
        precheck.append("NONCOMPLETED_CANDIDATE_CONTRIBUTION_NONZERO")
    if precheck:
        return _result(
            case,
            status=Stage6CSyntheticChampionStatus.PRECHECK_BLOCKED,
            reasons=tuple(precheck),
        )

    inference_results, holm = _evaluate_stage6c_holm_family_details(
        inference_cases,
        inventory=inventory,
        fold_plans=fold_plans,
        coverage=coverage,
        twr_cases=inference_twr_cases,
        twr_results=inference_twr_results,
        capability=capability,
    )
    inference_by_id: dict[Stage6CComparisonId, Stage6CInferenceResult] = {
        result.comparison_id: result for result in inference_results
    }
    fold_counts = tuple(len(completed_ids & values) for values in evaluation_ids_by_fold)
    fold_excess = tuple(
        value.annualized_net_excess_percentage_points or "0" for value in recomputed_fold_results
    )
    with localcontext(_CONTEXT):
        fold_values = tuple(_decimal(value) for value in fold_excess)
        benchmark_result = inference_by_id[Stage6CComparisonId.FULL_VS_MARKET_OR_INDUSTRY_MATCHED]
        best_result = inference_by_id[
            Stage6CComparisonId.FULL_VS_FROZEN_BEST_SIMPLE_MATERIAL_INCREMENT
        ]
        assert benchmark_result.calendar_path is not None
        assert best_result.calendar_path is not None
        full_excess = _decimal(benchmark_result.calendar_path.estimate)
        increment = _decimal(best_result.calendar_path.estimate)
        drawdown = _maximum_drawdown(tuple(fold_twr_cases))
        assert no_trade_case is not None
        profits = tuple(
            _decimal(value.full_net_contribution) for value in no_trade_case.contributions
        )
        total_profit = sum(profits, Decimal(0))
        largest_winner = max(profits)
        winner_share = largest_winner / total_profit if total_profit > 0 else None
        friction = _decimal(friction_twr_result.annualized_net_excess_percentage_points or "0")
        insufficient: list[str] = []
        revise: list[str] = []
        if len(completed_ids) < 30:
            insufficient.append("COMPLETED_TRADES_BELOW_30")
        if any(value < 5 for value in fold_counts):
            insufficient.append("FOLD_COMPLETED_TRADES_BELOW_5")
        if sum(value > 0 for value in fold_values) < 3:
            revise.append("POSITIVE_FOLDS_BELOW_3_OF_4")
        if min(fold_values) < Decimal("-10"):
            revise.append("WORST_FOLD_BELOW_MINUS_10")
        if full_excess <= 0:
            revise.append("FULL_NET_BENCHMARK_EXCESS_NOT_POSITIVE")
        if increment < Decimal("2"):
            revise.append("FULL_VS_BEST_SIMPLE_INCREMENT_BELOW_2")
        if drawdown > Decimal("0.15"):
            revise.append("MAXIMUM_DRAWDOWN_ABOVE_0_15")
        if total_profit <= 0:
            revise.append("TOTAL_NET_PROFIT_NOT_POSITIVE")
        elif winner_share is not None and winner_share > Decimal("0.25"):
            revise.append("LARGEST_WINNER_SHARE_ABOVE_0_25")
        if friction < 0:
            revise.append("FRICTION_1_5_NET_EXCESS_NEGATIVE")
        if holm.status is not Stage6CHolmStatus.ADJUSTED_INFERENCE_READY:
            revise.append("HOLM_ADJUSTED_INFERENCE_NOT_READY")
        if audit_attestation.p0_bias_failure_count != 0:
            revise.append("P0_BIAS_FAILURES_NONZERO")
        if audit_attestation.reconciliation_failure_count != 0:
            revise.append("RECONCILIATION_FAILURES_NONZERO")
    status = (
        Stage6CSyntheticChampionStatus.INSUFFICIENT_EVIDENCE
        if insufficient
        else (
            Stage6CSyntheticChampionStatus.REVISE_REQUIRED
            if revise
            else Stage6CSyntheticChampionStatus.GATE_FORMULA_PASSED
        )
    )
    return _result(
        case,
        status=status,
        reasons=tuple(insufficient + revise),
        completed_trade_count=len(completed_ids),
        fold_counts=fold_counts,
        fold_excess=fold_excess,
        full_excess=_decimal_text(full_excess),
        increment=_decimal_text(increment),
        drawdown=_decimal_text(drawdown),
        total_profit=_decimal_text(total_profit),
        winner_share=(_decimal_text(winner_share) if winner_share is not None else None),
        friction=_decimal_text(friction),
        holm_hash=holm.replay_hash,
    )


__all__ = [
    "Stage6CFoldTwrBinding",
    "Stage6CSyntheticAuditAttestation",
    "Stage6CSyntheticChampionCase",
    "Stage6CSyntheticChampionResult",
    "Stage6CSyntheticChampionStatus",
    "Stage6CSyntheticCompletionAttestation",
    "Stage6CSyntheticFrictionAttestation",
    "evaluate_stage6c_synthetic_champion_gate",
]
