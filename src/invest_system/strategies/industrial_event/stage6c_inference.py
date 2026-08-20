"""Anonymous synthetic Stage 6C bootstrap and Holm inference kernel."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, localcontext
from enum import StrEnum
from hashlib import sha256
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
from .stage6c_synthetic_kernel import (
    STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
    Stage6CSyntheticKernelCase,
    Stage6CSyntheticKernelResult,
    Stage6CSyntheticKernelStatus,
    evaluate_stage6c_synthetic_twr_kernel,
    require_stage6c_synthetic_capability,
)

STAGE6C_BOOTSTRAP_RESAMPLES = 10000
STAGE6C_CALENDAR_BOOTSTRAP_SEED = 20260820
STAGE6C_COMPANY_BOOTSTRAP_SEED = 20260821
STAGE6C_RISK_BOOTSTRAP_SEED = 20260822
_CONTEXT = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999)
_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SIGNED_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")


class Stage6CComparisonId(StrEnum):
    FULL_VS_NO_TRADE = "full_vs_no_trade"
    FULL_VS_MARKET_OR_INDUSTRY_MATCHED = "full_vs_market_or_industry_matched"
    FULL_VS_SIMPLE_E4_ONLY = "full_vs_simple_e4_only"
    FULL_VS_SIMPLE_VALUATION_THRESHOLD = "full_vs_simple_valuation_threshold"
    FULL_VS_FROZEN_BEST_SIMPLE_MATERIAL_INCREMENT = "full_vs_frozen_best_simple_material_increment"


class Stage6CInferenceStatus(StrEnum):
    INFERENCE_PASSED = "INFERENCE_PASSED"
    INFERENCE_FAILED = "INFERENCE_FAILED"
    RECONCILIATION_BLOCKED = "RECONCILIATION_BLOCKED"


class Stage6CHolmStatus(StrEnum):
    ADJUSTED_INFERENCE_READY = "ADJUSTED_INFERENCE_READY"
    ADJUSTED_INFERENCE_FAILED = "ADJUSTED_INFERENCE_FAILED"


def _decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return "0" if text in {"", "-0"} else text


def _decimal(value: str) -> Decimal:
    if not isinstance(value, str) or _SIGNED_DECIMAL_RE.fullmatch(value) is None:
        raise ValueError("decimal must use canonical fixed-point text")
    try:
        return Decimal(value)
    except Exception as exc:  # pragma: no cover - dataclass inputs already canonical
        raise ValueError("invalid decimal") from exc


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _hash_int(*parts: object) -> int:
    material = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(sha256(material).digest()[:8], "big")


def _annualized(factors: tuple[Decimal, ...]) -> Decimal:
    if not factors:
        raise ValueError("daily factors must not be empty")
    gross = Decimal(1)
    for factor in factors:
        if factor <= 0:
            raise ValueError("daily factors must be positive")
        gross *= factor
    return (gross ** (Decimal(252) / Decimal(len(factors))) - Decimal(1)) * Decimal(100)


def _percentile(sorted_values: tuple[Decimal, ...], probability: Decimal) -> Decimal:
    if not sorted_values:
        raise ValueError("percentile values must not be empty")
    position = probability * Decimal(len(sorted_values) - 1)
    lower_index = int(position.to_integral_value(rounding=ROUND_FLOOR))
    upper_index = int(position.to_integral_value(rounding=ROUND_CEILING))
    if lower_index == upper_index:
        return sorted_values[lower_index]
    fraction = position - Decimal(lower_index)
    return (
        sorted_values[lower_index]
        + (sorted_values[upper_index] - sorted_values[lower_index]) * fraction
    )


def _two_sided_centered_p_value(centered_draws: tuple[Decimal, ...], observed: Decimal) -> Decimal:
    extreme = sum(abs(value) >= abs(observed) for value in centered_draws)
    return (Decimal(extreme) + Decimal(1)) / (Decimal(len(centered_draws)) + Decimal(1))


@dataclass(frozen=True, slots=True)
class Stage6CPairedContribution(CanonicalModel):
    candidate_id: str
    listed_company_id: str
    risk_cluster_id: str
    full_net_contribution: str
    comparator_net_contribution: str

    def __post_init__(self) -> None:
        for field_name in ("candidate_id", "listed_company_id", "risk_cluster_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be a canonical ID")
        _decimal(self.full_net_contribution)
        _decimal(self.comparator_net_contribution)


@dataclass(frozen=True, slots=True)
class Stage6CInferenceCase(CanonicalModel):
    schema_version: str
    inference_case_id: str
    comparison_id: Stage6CComparisonId
    inventory_hash: HashDigest
    fold_plan_set_hash: HashDigest
    coverage_replay_hash: HashDigest
    twr_case_hash: HashDigest
    twr_replay_hash: HashDigest
    fold_beginning_nav: str
    full_ending_pnl: str
    comparator_ending_pnl: str
    contributions: tuple[Stage6CPairedContribution, ...]
    bootstrap_resamples: int
    calendar_seed: int
    company_seed: int
    risk_seed: int
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    case_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported inference schema_version")
        if not isinstance(self.inference_case_id, str) or not self.inference_case_id:
            raise ValueError("inference_case_id must be non-empty")
        object.__setattr__(self, "comparison_id", Stage6CComparisonId(self.comparison_id))
        for field_name in (
            "inventory_hash",
            "fold_plan_set_hash",
            "coverage_replay_hash",
            "twr_case_hash",
            "twr_replay_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be HashDigest")
        if _decimal(self.fold_beginning_nav) <= 0:
            raise ValueError("fold_beginning_nav must be positive")
        _decimal(self.full_ending_pnl)
        _decimal(self.comparator_ending_pnl)
        contributions = tuple(sorted(self.contributions, key=lambda value: value.candidate_id))
        if not contributions or any(
            not isinstance(value, Stage6CPairedContribution) for value in contributions
        ):
            raise ValueError("contributions must contain typed values")
        ids = tuple(value.candidate_id for value in contributions)
        if len(ids) != len(set(ids)):
            raise ValueError("contribution candidate IDs must be unique")
        object.__setattr__(self, "contributions", contributions)
        if (
            self.bootstrap_resamples != STAGE6C_BOOTSTRAP_RESAMPLES
            or self.calendar_seed != STAGE6C_CALENDAR_BOOTSTRAP_SEED
            or self.company_seed != STAGE6C_COMPANY_BOOTSTRAP_SEED
            or self.risk_seed != STAGE6C_RISK_BOOTSTRAP_SEED
        ):
            raise ValueError("inference resampling profile differs")
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if not self.synthetic or not self.validation_only:
            raise ValueError("inference case must be anonymous synthetic validation")
        if self.holdout_artifact_read or self.authority_eligible:
            raise ValueError("inference case exceeded authority boundary")
        if not isinstance(self.case_hash, HashDigest) or self.case_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("inference case_hash differs")

    @classmethod
    def create(
        cls,
        *,
        inference_case_id: str,
        comparison_id: Stage6CComparisonId,
        inventory_hash: HashDigest,
        fold_plan_set_hash: HashDigest,
        coverage_replay_hash: HashDigest,
        twr_case_hash: HashDigest,
        twr_replay_hash: HashDigest,
        fold_beginning_nav: str,
        full_ending_pnl: str,
        comparator_ending_pnl: str,
        contributions: tuple[Stage6CPairedContribution, ...],
    ) -> Stage6CInferenceCase:
        payload: dict[str, Any] = {
            "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
            "inference_case_id": inference_case_id,
            "comparison_id": comparison_id,
            "inventory_hash": inventory_hash,
            "fold_plan_set_hash": fold_plan_set_hash,
            "coverage_replay_hash": coverage_replay_hash,
            "twr_case_hash": twr_case_hash,
            "twr_replay_hash": twr_replay_hash,
            "fold_beginning_nav": fold_beginning_nav,
            "full_ending_pnl": full_ending_pnl,
            "comparator_ending_pnl": comparator_ending_pnl,
            "contributions": contributions,
            "bootstrap_resamples": STAGE6C_BOOTSTRAP_RESAMPLES,
            "calendar_seed": STAGE6C_CALENDAR_BOOTSTRAP_SEED,
            "company_seed": STAGE6C_COMPANY_BOOTSTRAP_SEED,
            "risk_seed": STAGE6C_RISK_BOOTSTRAP_SEED,
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
                "inference_case_id",
                "comparison_id",
                "inventory_hash",
                "fold_plan_set_hash",
                "coverage_replay_hash",
                "twr_case_hash",
                "twr_replay_hash",
                "fold_beginning_nav",
                "full_ending_pnl",
                "comparator_ending_pnl",
                "contributions",
                "bootstrap_resamples",
                "calendar_seed",
                "company_seed",
                "risk_seed",
                "synthetic",
                "validation_only",
                "holdout_artifact_read",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CInferencePathResult(CanonicalModel):
    path_id: str
    estimate: str
    ci_lower: str
    ci_upper: str
    raw_p_value: str
    passes_positive_lower_bound: bool

    def __post_init__(self) -> None:
        if not isinstance(self.path_id, str) or _ID_RE.fullmatch(self.path_id) is None:
            raise ValueError("path_id must be a canonical ID")
        estimate = _decimal(self.estimate)
        lower = _decimal(self.ci_lower)
        upper = _decimal(self.ci_upper)
        p_value = _decimal(self.raw_p_value)
        if lower > upper or not Decimal(0) <= p_value <= Decimal(1):
            raise ValueError("inference path interval or p-value differs")
        if type(self.passes_positive_lower_bound) is not bool:
            raise TypeError("passes_positive_lower_bound must be bool")
        if self.passes_positive_lower_bound != (lower > 0):
            raise ValueError("passes_positive_lower_bound differs from ci_lower")
        del estimate


@dataclass(frozen=True, slots=True)
class Stage6CInferenceResult(CanonicalModel):
    schema_version: str
    case_hash: HashDigest
    comparison_id: Stage6CComparisonId
    status: Stage6CInferenceStatus
    failure_reasons: tuple[str, ...]
    calendar_path: Stage6CInferencePathResult | None
    company_path: Stage6CInferencePathResult | None
    risk_path: Stage6CInferencePathResult | None
    synthetic: bool
    validation_only: bool
    not_a_complete_stage6c_walk_forward: bool
    holdout_artifact_read: bool
    persists_state: bool
    authority_eligible: bool
    replay_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported inference result schema_version")
        if not isinstance(self.case_hash, HashDigest):
            raise TypeError("case_hash must be HashDigest")
        object.__setattr__(self, "comparison_id", Stage6CComparisonId(self.comparison_id))
        object.__setattr__(self, "status", Stage6CInferenceStatus(self.status))
        reasons = tuple(sorted(set(self.failure_reasons)))
        if tuple(self.failure_reasons) != reasons:
            raise ValueError("failure_reasons must be sorted and unique")
        object.__setattr__(self, "failure_reasons", reasons)
        paths = (self.calendar_path, self.company_path, self.risk_path)
        if self.status is Stage6CInferenceStatus.RECONCILIATION_BLOCKED:
            if not reasons or any(path is not None for path in paths):
                raise ValueError("blocked inference cannot publish partial paths")
        else:
            if reasons or any(not isinstance(path, Stage6CInferencePathResult) for path in paths):
                raise ValueError("completed inference result shape differs")
        for field_name in (
            "synthetic",
            "validation_only",
            "not_a_complete_stage6c_walk_forward",
            "holdout_artifact_read",
            "persists_state",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if (
            not self.synthetic
            or not self.validation_only
            or (not self.not_a_complete_stage6c_walk_forward)
        ):
            raise ValueError("inference result scope differs")
        if self.holdout_artifact_read or self.persists_state or self.authority_eligible:
            raise ValueError("inference result exceeded authority boundary")
        if not isinstance(self.replay_hash, HashDigest) or self.replay_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("inference replay_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            field_name: getattr(self, field_name)
            for field_name in (
                "schema_version",
                "case_hash",
                "comparison_id",
                "status",
                "failure_reasons",
                "calendar_path",
                "company_path",
                "risk_path",
                "synthetic",
                "validation_only",
                "not_a_complete_stage6c_walk_forward",
                "holdout_artifact_read",
                "persists_state",
                "authority_eligible",
            )
        }


@dataclass(frozen=True, slots=True)
class Stage6CHolmItem(CanonicalModel):
    comparison_id: Stage6CComparisonId
    rank: int
    raw_p_value: str
    holm_threshold: str
    adjusted_p_value: str
    rejected: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "comparison_id", Stage6CComparisonId(self.comparison_id))
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or not 1 <= self.rank <= 5:
            raise ValueError("Holm rank must be 1 through 5")
        raw = _decimal(self.raw_p_value)
        threshold = _decimal(self.holm_threshold)
        adjusted = _decimal(self.adjusted_p_value)
        if any(not Decimal(0) <= value <= Decimal(1) for value in (raw, threshold, adjusted)):
            raise ValueError("Holm probabilities must be between zero and one")
        if type(self.rejected) is not bool:
            raise TypeError("rejected must be bool")


@dataclass(frozen=True, slots=True)
class Stage6CHolmResult(CanonicalModel):
    schema_version: str
    inference_replay_hashes: tuple[HashDigest, ...]
    status: Stage6CHolmStatus
    items: tuple[Stage6CHolmItem, ...]
    failure_reasons: tuple[str, ...]
    synthetic: bool
    validation_only: bool
    holdout_artifact_read: bool
    authority_eligible: bool
    replay_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION:
            raise ValueError("unsupported Holm result schema_version")
        object.__setattr__(self, "status", Stage6CHolmStatus(self.status))
        hashes = tuple(self.inference_replay_hashes)
        if (
            len(hashes) != 5
            or len(set(hashes)) != 5
            or any(not isinstance(value, HashDigest) for value in hashes)
        ):
            raise ValueError("Holm requires five inference replay hashes")
        object.__setattr__(self, "inference_replay_hashes", hashes)
        items = tuple(self.items)
        if len(items) != 5 or any(not isinstance(value, Stage6CHolmItem) for value in items):
            raise ValueError("Holm requires five typed items")
        if tuple(item.rank for item in items) != (1, 2, 3, 4, 5) or {
            item.comparison_id for item in items
        } != set(Stage6CComparisonId):
            raise ValueError("Holm item ranks or comparison family differ")
        adjusted = tuple(_decimal(item.adjusted_p_value) for item in items)
        if adjusted != tuple(sorted(adjusted)):
            raise ValueError("Holm adjusted p-values must be non-decreasing")
        object.__setattr__(self, "items", items)
        reasons = tuple(sorted(set(self.failure_reasons)))
        if tuple(self.failure_reasons) != reasons:
            raise ValueError("failure_reasons must be sorted and unique")
        object.__setattr__(self, "failure_reasons", reasons)
        if self.status is Stage6CHolmStatus.ADJUSTED_INFERENCE_READY and reasons:
            raise ValueError("ready Holm result cannot have failures")
        if self.status is Stage6CHolmStatus.ADJUSTED_INFERENCE_READY and not all(
            item.rejected and _decimal(item.adjusted_p_value) <= Decimal("0.05") for item in items
        ):
            raise ValueError("ready Holm result requires all adjusted tests to pass")
        if self.status is Stage6CHolmStatus.ADJUSTED_INFERENCE_FAILED and not reasons:
            raise ValueError("failed Holm result requires reasons")
        for field_name in (
            "synthetic",
            "validation_only",
            "holdout_artifact_read",
            "authority_eligible",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise TypeError(f"{field_name} must be bool")
        if (
            not self.synthetic
            or not self.validation_only
            or self.holdout_artifact_read
            or (self.authority_eligible)
        ):
            raise ValueError("Holm result exceeded synthetic authority")
        if not isinstance(self.replay_hash, HashDigest) or self.replay_hash != _hash(
            self.identity_payload()
        ):
            raise ValueError("Holm replay_hash differs")

    def identity_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "inference_replay_hashes": self.inference_replay_hashes,
            "status": self.status,
            "items": self.items,
            "failure_reasons": self.failure_reasons,
            "synthetic": self.synthetic,
            "validation_only": self.validation_only,
            "holdout_artifact_read": self.holdout_artifact_read,
            "authority_eligible": self.authority_eligible,
        }


def _path_result(
    path_id: str, estimate: Decimal, draws: tuple[Decimal, ...]
) -> Stage6CInferencePathResult:
    ordered = tuple(sorted(draws))
    lower = _percentile(ordered, Decimal("0.025"))
    upper = _percentile(ordered, Decimal("0.975"))
    centered = tuple(value - estimate for value in draws)
    p_value = _two_sided_centered_p_value(centered, estimate)
    return Stage6CInferencePathResult(
        path_id=path_id,
        estimate=_decimal_text(estimate),
        ci_lower=_decimal_text(lower),
        ci_upper=_decimal_text(upper),
        raw_p_value=_decimal_text(p_value),
        passes_positive_lower_bound=lower > 0,
    )


def _calendar_draws(
    case: Stage6CSyntheticKernelCase, factors: tuple[Decimal, ...]
) -> tuple[Decimal, ...]:
    dates = tuple(point.session_date for point in case.nav_points[1:])
    blocks: dict[str, list[Decimal]] = {}
    for session_date, factor in zip(dates, factors, strict=True):
        month = int(session_date[5:7])
        quarter = (month - 1) // 3 + 1
        block_id = f"{session_date[:4]}-Q{quarter}"
        blocks.setdefault(block_id, []).append(factor)
    ordered_blocks = tuple(tuple(blocks[key]) for key in sorted(blocks))
    draws: list[Decimal] = []
    for draw in range(STAGE6C_BOOTSTRAP_RESAMPLES):
        sampled: list[Decimal] = []
        position = 0
        while len(sampled) < len(factors):
            index = _hash_int(STAGE6C_CALENDAR_BOOTSTRAP_SEED, draw, position) % len(ordered_blocks)
            sampled.extend(ordered_blocks[index])
            position += 1
        draws.append(_annualized(tuple(sampled[: len(factors)])))
    return tuple(draws)


def _cluster_draws(
    rates: tuple[tuple[str, Decimal], ...], *, seed: int
) -> tuple[Decimal, tuple[Decimal, ...]]:
    estimate = sum((rate for _, rate in rates), Decimal(0)) / Decimal(len(rates))
    residuals = tuple((cluster, rate - estimate) for cluster, rate in rates)
    draws: list[Decimal] = []
    for draw in range(STAGE6C_BOOTSTRAP_RESAMPLES):
        total = Decimal(0)
        multiplier_by_cluster: dict[str, Decimal] = {}
        for cluster, residual in residuals:
            multiplier = multiplier_by_cluster.setdefault(
                cluster,
                Decimal(1) if _hash_int(seed, draw, cluster) % 2 else Decimal(-1),
            )
            total += multiplier * residual
        draws.append(estimate + total / Decimal(len(residuals)))
    return estimate, tuple(draws)


def _blocked_result(case: Stage6CInferenceCase, reasons: tuple[str, ...]) -> Stage6CInferenceResult:
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "case_hash": case.case_hash,
        "comparison_id": case.comparison_id,
        "status": Stage6CInferenceStatus.RECONCILIATION_BLOCKED,
        "failure_reasons": tuple(sorted(set(reasons))),
        "calendar_path": None,
        "company_path": None,
        "risk_path": None,
        "synthetic": True,
        "validation_only": True,
        "not_a_complete_stage6c_walk_forward": True,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CInferenceResult(**payload, replay_hash=_hash(payload))


def evaluate_stage6c_synthetic_inference(
    case: Stage6CInferenceCase,
    *,
    inventory: Stage6CCandidateInventory,
    fold_plans: Stage6CFoldPlanSet,
    coverage: Stage6CCoverageAuditResult,
    twr_case: Stage6CSyntheticKernelCase,
    twr_result: Stage6CSyntheticKernelResult,
    capability: ApprovedRuleCapability,
) -> Stage6CInferenceResult:
    """Recompute all synthetic sources and evaluate one approved comparison."""

    if not isinstance(case, Stage6CInferenceCase):
        raise TypeError("case must be Stage6CInferenceCase")
    require_stage6c_synthetic_capability(capability)
    reasons: list[str] = []
    recomputed_folds = plan_stage6c_synthetic_folds(inventory, capability=capability)
    recomputed_coverage = evaluate_stage6c_synthetic_coverage(
        inventory, recomputed_folds, capability=capability
    )
    recomputed_twr = evaluate_stage6c_synthetic_twr_kernel(twr_case, capability=capability)
    if fold_plans != recomputed_folds or case.fold_plan_set_hash != recomputed_folds.plan_set_hash:
        reasons.append("FOLD_SOURCE_MISMATCH")
    if coverage != recomputed_coverage or case.coverage_replay_hash != coverage.replay_hash:
        reasons.append("COVERAGE_SOURCE_MISMATCH")
    if coverage.status is not Stage6CCoverageAuditStatus.COVERAGE_READY:
        reasons.append("COVERAGE_NOT_READY")
    if twr_result != recomputed_twr or case.twr_replay_hash != twr_result.replay_hash:
        reasons.append("TWR_SOURCE_MISMATCH")
    if twr_result.status is not Stage6CSyntheticKernelStatus.TWR_RECONCILED:
        reasons.append("TWR_NOT_RECONCILED")
    if case.inventory_hash != inventory.inventory_hash or case.twr_case_hash != twr_case.case_hash:
        reasons.append("CASE_SOURCE_HASH_MISMATCH")
    candidate_by_id = {candidate.candidate_id: candidate for candidate in inventory.candidates}
    evaluation_candidate_ids = {
        candidate_id for fold in fold_plans.folds for candidate_id in fold.evaluation_candidate_ids
    }
    contribution_ids = tuple(value.candidate_id for value in case.contributions)
    if contribution_ids != tuple(sorted(candidate_by_id)):
        reasons.append("CONTRIBUTION_CANDIDATE_SET_MISMATCH")
    for contribution in case.contributions:
        candidate = candidate_by_id.get(contribution.candidate_id)
        if candidate is None:
            continue
        if contribution.listed_company_id != candidate.listed_company_id:
            reasons.append("CONTRIBUTION_COMPANY_MISMATCH")
        if contribution.candidate_id not in evaluation_candidate_ids and (
            _decimal(contribution.full_net_contribution) != 0
            or _decimal(contribution.comparator_net_contribution) != 0
        ):
            reasons.append("NON_EVALUATION_CANDIDATE_CONTRIBUTION_NONZERO")
        if candidate.disposition is not Stage6CCandidateDisposition.TRADE_READY and (
            _decimal(contribution.full_net_contribution) != 0
            or _decimal(contribution.comparator_net_contribution) != 0
        ):
            reasons.append("NON_TRADING_CANDIDATE_CONTRIBUTION_NONZERO")
    expected_delta = _decimal(case.full_ending_pnl) - _decimal(case.comparator_ending_pnl)
    actual_delta = sum(
        (
            _decimal(value.full_net_contribution) - _decimal(value.comparator_net_contribution)
            for value in case.contributions
        ),
        Decimal(0),
    )
    if actual_delta != expected_delta:
        reasons.append("CONTRIBUTION_PNL_RECONCILIATION_MISMATCH")
    if reasons:
        return _blocked_result(case, tuple(reasons))

    with localcontext(_CONTEXT):
        factors = tuple(_decimal(value) for value in twr_result.daily_excess_factors)
        calendar_estimate = _annualized(factors)
        calendar_path = _path_result(
            "calendar_block_portfolio",
            calendar_estimate,
            _calendar_draws(twr_case, factors),
        )
        beginning_nav = _decimal(case.fold_beginning_nav)
        company_rates = tuple(
            (
                value.listed_company_id,
                (
                    _decimal(value.full_net_contribution)
                    - _decimal(value.comparator_net_contribution)
                )
                / beginning_nav,
            )
            for value in case.contributions
        )
        risk_rates = tuple(
            (
                value.risk_cluster_id,
                (
                    _decimal(value.full_net_contribution)
                    - _decimal(value.comparator_net_contribution)
                )
                / beginning_nav,
            )
            for value in case.contributions
        )
        company_estimate, company_draws = _cluster_draws(
            company_rates, seed=STAGE6C_COMPANY_BOOTSTRAP_SEED
        )
        risk_estimate, risk_draws = _cluster_draws(risk_rates, seed=STAGE6C_RISK_BOOTSTRAP_SEED)
        company_path = _path_result("company_cluster_sensitivity", company_estimate, company_draws)
        risk_path = _path_result("risk_cluster_sensitivity", risk_estimate, risk_draws)
    passed = all(
        path.passes_positive_lower_bound for path in (calendar_path, company_path, risk_path)
    )
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "case_hash": case.case_hash,
        "comparison_id": case.comparison_id,
        "status": (
            Stage6CInferenceStatus.INFERENCE_PASSED
            if passed
            else Stage6CInferenceStatus.INFERENCE_FAILED
        ),
        "failure_reasons": (),
        "calendar_path": calendar_path,
        "company_path": company_path,
        "risk_path": risk_path,
        "synthetic": True,
        "validation_only": True,
        "not_a_complete_stage6c_walk_forward": True,
        "holdout_artifact_read": False,
        "persists_state": False,
        "authority_eligible": False,
    }
    return Stage6CInferenceResult(**payload, replay_hash=_hash(payload))


def _evaluate_stage6c_holm_family_details(
    cases: tuple[Stage6CInferenceCase, ...],
    *,
    inventory: Stage6CCandidateInventory,
    fold_plans: Stage6CFoldPlanSet,
    coverage: Stage6CCoverageAuditResult,
    twr_cases: tuple[Stage6CSyntheticKernelCase, ...],
    twr_results: tuple[Stage6CSyntheticKernelResult, ...],
    capability: ApprovedRuleCapability,
) -> tuple[tuple[Stage6CInferenceResult, ...], Stage6CHolmResult]:
    """Recompute five raw cases and apply Holm without trusting caller results."""

    require_stage6c_synthetic_capability(capability)
    case_values = tuple(cases)
    twr_case_values = tuple(twr_cases)
    twr_result_values = tuple(twr_results)
    expected_ids = tuple(Stage6CComparisonId)
    case_by_id = {case.comparison_id: case for case in case_values}
    if len(case_values) != 5 or set(case_by_id) != set(expected_ids):
        raise ValueError("Holm family must contain every comparison exactly once")
    if (
        len(twr_case_values) != 5
        or len(twr_result_values) != 5
        or len({value.case_hash for value in twr_case_values}) != 5
        or len({value.replay_hash for value in twr_result_values}) != 5
    ):
        raise ValueError("Holm family requires five distinct TWR sources")
    twr_case_by_id = dict(zip(expected_ids, twr_case_values, strict=True))
    twr_result_by_id = dict(zip(expected_ids, twr_result_values, strict=True))
    values = tuple(
        evaluate_stage6c_synthetic_inference(
            case_by_id[comparison_id],
            inventory=inventory,
            fold_plans=fold_plans,
            coverage=coverage,
            twr_case=twr_case_by_id[comparison_id],
            twr_result=twr_result_by_id[comparison_id],
            capability=capability,
        )
        for comparison_id in expected_ids
    )
    by_id = {result.comparison_id: result for result in values}
    if any(result.status is Stage6CInferenceStatus.RECONCILIATION_BLOCKED for result in values):
        raise ValueError("Holm family cannot consume blocked inference")
    with localcontext(_CONTEXT):
        ordered = sorted(
            values,
            key=lambda result: (
                _decimal(result.calendar_path.raw_p_value) if result.calendar_path else Decimal(1),
                result.comparison_id.value,
            ),
        )
        running_adjusted = Decimal(0)
        still_rejecting = True
        items: list[Stage6CHolmItem] = []
        failures: list[str] = []
        for index, result in enumerate(ordered, start=1):
            assert result.calendar_path is not None
            raw = _decimal(result.calendar_path.raw_p_value)
            multiplier = Decimal(6 - index)
            adjusted = min(Decimal(1), max(running_adjusted, raw * multiplier))
            running_adjusted = adjusted
            threshold = Decimal("0.05") / multiplier
            rejected = still_rejecting and raw <= threshold
            if not rejected:
                still_rejecting = False
            items.append(
                Stage6CHolmItem(
                    comparison_id=result.comparison_id,
                    rank=index,
                    raw_p_value=_decimal_text(raw),
                    holm_threshold=_decimal_text(threshold),
                    adjusted_p_value=_decimal_text(adjusted),
                    rejected=rejected,
                )
            )
            if adjusted > Decimal("0.05") or not rejected:
                failures.append("HOLM_ADJUSTED_FAMILY_NOT_ALL_REJECTED")
        primary_ids = {
            Stage6CComparisonId.FULL_VS_MARKET_OR_INDUSTRY_MATCHED,
            Stage6CComparisonId.FULL_VS_FROZEN_BEST_SIMPLE_MATERIAL_INCREMENT,
        }
        for comparison_id in primary_ids:
            result = by_id[comparison_id]
            if not all(
                path is not None and path.passes_positive_lower_bound
                for path in (result.calendar_path, result.company_path, result.risk_path)
            ):
                failures.append("PRIMARY_COMPARISON_THREE_PATH_GATE_FAILED")
    unique_failures = tuple(sorted(set(failures)))
    payload: dict[str, Any] = {
        "schema_version": STAGE6C_SYNTHETIC_KERNEL_SCHEMA_VERSION,
        "inference_replay_hashes": tuple(
            by_id[comparison_id].replay_hash for comparison_id in expected_ids
        ),
        "status": (
            Stage6CHolmStatus.ADJUSTED_INFERENCE_FAILED
            if unique_failures
            else Stage6CHolmStatus.ADJUSTED_INFERENCE_READY
        ),
        "items": tuple(items),
        "failure_reasons": unique_failures,
        "synthetic": True,
        "validation_only": True,
        "holdout_artifact_read": False,
        "authority_eligible": False,
    }
    holm = Stage6CHolmResult(**payload, replay_hash=_hash(payload))
    return values, holm


def evaluate_stage6c_holm_family(
    cases: tuple[Stage6CInferenceCase, ...],
    *,
    inventory: Stage6CCandidateInventory,
    fold_plans: Stage6CFoldPlanSet,
    coverage: Stage6CCoverageAuditResult,
    twr_cases: tuple[Stage6CSyntheticKernelCase, ...],
    twr_results: tuple[Stage6CSyntheticKernelResult, ...],
    capability: ApprovedRuleCapability,
) -> Stage6CHolmResult:
    """Recompute five raw cases and return only the exact Holm result."""

    return _evaluate_stage6c_holm_family_details(
        cases,
        inventory=inventory,
        fold_plans=fold_plans,
        coverage=coverage,
        twr_cases=twr_cases,
        twr_results=twr_results,
        capability=capability,
    )[1]


__all__ = [
    "STAGE6C_BOOTSTRAP_RESAMPLES",
    "STAGE6C_CALENDAR_BOOTSTRAP_SEED",
    "STAGE6C_COMPANY_BOOTSTRAP_SEED",
    "STAGE6C_RISK_BOOTSTRAP_SEED",
    "Stage6CComparisonId",
    "Stage6CHolmItem",
    "Stage6CHolmResult",
    "Stage6CHolmStatus",
    "Stage6CInferenceCase",
    "Stage6CInferencePathResult",
    "Stage6CInferenceResult",
    "Stage6CInferenceStatus",
    "Stage6CPairedContribution",
    "evaluate_stage6c_holm_family",
    "evaluate_stage6c_synthetic_inference",
]
