"""Immutable Stage 1 models for InvestSystem-owned draft contracts.

The models are provider-neutral.  In particular, they neither import nor claim
to implement any InvestmentResearchKB package or official provider schema.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from .canonical import (
    JsonValue,
    canonical_json,
    canonical_json_bytes,
    canonical_sha256,
    freeze_json,
    normalize_utc,
    to_json_value,
)

VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION = "0.1.0-draft"
GATE_RESULT_SCHEMA_VERSION = "0.1.0-draft"
STRATEGY_RUN_MANIFEST_SCHEMA_VERSION = "0.1.0-draft"
DECISION_RECORD_SCHEMA_VERSION = "0.1.0-draft"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _require_id(field_name: str, value: str, *, forbid_latest: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-128 ASCII ID characters "
            "([A-Za-z0-9._:-]) and start with an alphanumeric character"
        )
    if forbid_latest and value.casefold() == "latest":
        raise ValueError(f"{field_name} must be an exact ID, not 'latest'")
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_version(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _SEMVER_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")
    return value


def _require_schema_version(field_name: str, value: str, expected: str) -> str:
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}")
    return value


def _require_decimal(field_name: str, value: str | None) -> str | None:
    if value is not None and (not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None):
        raise ValueError(f"{field_name} must be a canonical decimal string or None")
    return value


def _freeze_ids(
    field_name: str, values: Iterable[str], *, forbid_latest: bool = False
) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple of IDs")
    result = tuple(_require_id(field_name, value, forbid_latest=forbid_latest) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return result


def _freeze_texts(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple of strings")
    return tuple(_require_text(field_name, value) for value in values)


def _ordered_tuple(field_name: str, values: Iterable[Any]) -> tuple[Any, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    return tuple(values)


def _is_zero_or_none(value: str | None) -> bool:
    return value is None or Decimal(value) == 0


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


class CanonicalModel:
    """Convenience methods shared by immutable contract models."""

    def to_json_value(self) -> dict[str, Any]:
        projected = to_json_value(self)
        if not isinstance(projected, dict):
            raise TypeError("canonical models must project to a JSON object")
        return projected

    def to_canonical_json(self) -> str:
        return canonical_json(self)

    def to_canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self)

    def canonical_sha256(self) -> str:
        """Hash the complete model; this does not omit self-hash fields."""

        return canonical_sha256(self)


@dataclass(frozen=True, slots=True)
class HashDigest(CanonicalModel):
    """A validated lowercase SHA-256 digest object."""

    algorithm: str
    value: str

    def __post_init__(self) -> None:
        if self.algorithm != "sha256":
            raise ValueError("algorithm must be 'sha256'")
        if not isinstance(self.value, str) or _SHA256_RE.fullmatch(self.value) is None:
            raise ValueError("value must be exactly 64 lowercase hexadecimal characters")


@dataclass(frozen=True, slots=True)
class StrategyInputRef(CanonicalModel):
    """Provider-boundary reference preserved by InvestSystem without drift."""

    schema_version: str
    dataset_release_id: str
    knowledge_cutoff: datetime
    release_manifest_schema_version: str
    manifest_hash: HashDigest

    def __post_init__(self) -> None:
        _require_version("schema_version", self.schema_version)
        _require_id("dataset_release_id", self.dataset_release_id, forbid_latest=True)
        object.__setattr__(
            self,
            "knowledge_cutoff",
            normalize_utc(self.knowledge_cutoff, field_name="knowledge_cutoff"),
        )
        _require_version(
            "release_manifest_schema_version",
            self.release_manifest_schema_version,
        )
        if not isinstance(self.manifest_hash, HashDigest):
            raise TypeError("manifest_hash must be a HashDigest")


@dataclass(frozen=True, slots=True)
class VerifiedFact(CanonicalModel):
    """Provider-neutral, PIT-preserving fact available to strategy code."""

    fact_id: str
    subject_id: str
    predicate: str
    value: JsonValue
    verified_at: datetime
    available_at: datetime
    evidence_ids: tuple[str, ...] = ()
    event_at: datetime | None = None
    source_published_at: datetime | None = None
    first_seen_at: datetime | None = None
    metadata: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_id("fact_id", self.fact_id)
        _require_id("subject_id", self.subject_id)
        _require_text("predicate", self.predicate)
        object.__setattr__(self, "value", freeze_json(self.value, path="$.value"))
        for field_name in ("verified_at", "available_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        for field_name in ("event_at", "source_published_at", "first_seen_at"):
            timestamp = getattr(self, field_name)
            if timestamp is not None:
                object.__setattr__(
                    self,
                    field_name,
                    normalize_utc(timestamp, field_name=field_name),
                )
        object.__setattr__(self, "evidence_ids", _freeze_ids("evidence_ids", self.evidence_ids))
        frozen_metadata = freeze_json(self.metadata, path="$.metadata")
        if not isinstance(frozen_metadata, Mapping):
            raise TypeError("metadata must be a mapping")
        object.__setattr__(self, "metadata", frozen_metadata)


@dataclass(frozen=True, slots=True)
class VerifiedKnowledgeInput(CanonicalModel):
    """InvestSystem-owned provider-neutral input for a single exact release."""

    schema_version: str
    input_id: str
    strategy_input_ref: StrategyInputRef
    facts: tuple[VerifiedFact, ...]

    def __post_init__(self) -> None:
        _require_schema_version(
            "schema_version",
            self.schema_version,
            VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
        )
        _require_id("input_id", self.input_id)
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        # Keep a deterministic runtime boundary for callers that do not use static typing.
        facts = _ordered_tuple("facts", self.facts)
        if any(not isinstance(fact, VerifiedFact) for fact in facts):
            raise TypeError("facts must contain only VerifiedFact values")
        fact_ids = tuple(fact.fact_id for fact in facts)
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("facts must not contain duplicate fact_id values")
        cutoff = self.strategy_input_ref.knowledge_cutoff
        if any(fact.available_at > cutoff for fact in facts):
            raise ValueError("every fact.available_at must be <= knowledge_cutoff")
        object.__setattr__(self, "facts", facts)


class GateId(StrEnum):
    AUTHENTICITY = "gate_1_authenticity"
    PROFIT_MATERIALITY = "gate_2_profit_materiality"
    EXPECTATION_GAP = "gate_3_expectation_gap"
    EXECUTABLE_RETURN = "gate_4_executable_return"


class GateOutcome(StrEnum):
    PASS = "PASS"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    BLOCKED = "BLOCKED"
    SHADOW_ONLY = "SHADOW_ONLY"


class RuleStatus(StrEnum):
    """Authoritative maturity labels used by rule bundles and decisions."""

    REQUIREMENTS_CONFIRMED = "requirements_confirmed"
    HYPOTHESIS = "hypothesis"
    DRAFT = "draft"
    PLACEHOLDER = "placeholder"
    TBD = "TBD"
    APPROVED = "approved"


@dataclass(frozen=True, slots=True)
class GateResult(CanonicalModel):
    """Auditable gate output without a scoring or compensation rule."""

    schema_version: str
    gate_id: GateId
    outcome: GateOutcome
    evaluated_at: datetime
    rule_id: str
    rule_version: str
    supporting_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    details: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_schema_version("schema_version", self.schema_version, GATE_RESULT_SCHEMA_VERSION)
        object.__setattr__(self, "gate_id", _coerce_enum("gate_id", GateId, self.gate_id))
        object.__setattr__(self, "outcome", _coerce_enum("outcome", GateOutcome, self.outcome))
        object.__setattr__(
            self,
            "evaluated_at",
            normalize_utc(self.evaluated_at, field_name="evaluated_at"),
        )
        _require_id("rule_id", self.rule_id)
        _require_version("rule_version", self.rule_version)
        for field_name in ("supporting_fact_ids", "conflicting_fact_ids", "reason_codes"):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        frozen_details = freeze_json(self.details, path="$.details")
        if not isinstance(frozen_details, Mapping):
            raise TypeError("details must be a mapping")
        object.__setattr__(self, "details", frozen_details)


class RunMode(StrEnum):
    RESEARCH = "research"
    BACKTEST = "backtest"
    PAPER = "paper"
    SHADOW = "shadow"


@dataclass(frozen=True, slots=True)
class StrategyRunManifest(CanonicalModel):
    """Minimum immutable identity and audit inputs for one strategy run."""

    strategy_run_manifest_schema_version: str
    run_id: str
    created_at: datetime
    strategy_id: str
    strategy_version: str
    code_commit: str
    rule_bundle_version: str
    rule_status: RuleStatus
    config_hash: HashDigest
    strategy_input_ref: StrategyInputRef
    artifact_consumption_receipt_hash: HashDigest
    artifact_fetch_observation_id: str
    release_status_observation_id: str
    release_admission_observation_id: str
    random_seed: int
    run_mode: RunMode
    runtime_environment_lock_hash: HashDigest

    def __post_init__(self) -> None:
        _require_schema_version(
            "strategy_run_manifest_schema_version",
            self.strategy_run_manifest_schema_version,
            STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        )
        _require_id("run_id", self.run_id)
        object.__setattr__(
            self,
            "created_at",
            normalize_utc(self.created_at, field_name="created_at"),
        )
        _require_id("strategy_id", self.strategy_id)
        _require_version("strategy_version", self.strategy_version)
        if (
            not isinstance(self.code_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.code_commit) is None
        ):
            raise ValueError("code_commit must be a full 40- or 64-character lowercase hex ID")
        _require_version("rule_bundle_version", self.rule_bundle_version)
        object.__setattr__(
            self,
            "rule_status",
            _coerce_enum("rule_status", RuleStatus, self.rule_status),
        )
        for field_name in (
            "config_hash",
            "artifact_consumption_receipt_hash",
            "runtime_environment_lock_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.strategy_input_ref.knowledge_cutoff > self.created_at:
            raise ValueError("knowledge_cutoff must be <= created_at")
        _require_id("artifact_fetch_observation_id", self.artifact_fetch_observation_id)
        _require_id("release_status_observation_id", self.release_status_observation_id)
        _require_id("release_admission_observation_id", self.release_admission_observation_id)
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        object.__setattr__(self, "run_mode", _coerce_enum("run_mode", RunMode, self.run_mode))
        if self.rule_status is not RuleStatus.APPROVED and self.run_mode not in {
            RunMode.RESEARCH,
            RunMode.SHADOW,
        }:
            raise ValueError("unapproved rule_status requires research or shadow run_mode")


class EventState(StrEnum):
    E0 = "E0"
    E1 = "E1"
    E2 = "E2"
    E3 = "E3"
    E3_5 = "E3.5"
    E4 = "E4"
    E5 = "E5"
    E6 = "E6"
    E7 = "E7"


class DecisionState(StrEnum):
    RESEARCH = "RESEARCH"
    SHADOW_ONLY = "SHADOW_ONLY"
    TRADE_READY = "TRADE_READY"
    REJECT = "REJECT"
    ABSTAIN = "ABSTAIN"
    BLOCKED = "BLOCKED"


class PositionState(StrEnum):
    FLAT = "FLAT"
    STARTER = "STARTER"
    CORE = "CORE"
    TRIM = "TRIM"
    EXIT = "EXIT"


class ExpectationClass(StrEnum):
    UNEXPECTED = "unexpected"
    PARTIALLY_PRICED = "partially_priced"
    FULLY_PRICED = "fully_priced"
    UNKNOWN = "unknown"


class MarketRegime(StrEnum):
    NORMAL = "NORMAL"
    DEFENSIVE = "DEFENSIVE"
    CRISIS = "CRISIS"


@dataclass(frozen=True, slots=True)
class DecisionRecord(CanonicalModel):
    """PRD-shaped, non-business Stage 1 decision audit skeleton.

    Economic models remain opaque JSON values until their rule specifications
    are approved.  Exact decimal quantities are represented as strings so the
    draft contract never relies on binary floating point.
    """

    decision_record_schema_version: str
    decision_id: str
    run_id: str
    decision_at: datetime
    strategy_input_ref: StrategyInputRef
    strategy_version: str
    rule_status: RuleStatus
    event_state: EventState
    decision_state: DecisionState
    position_state: PositionState
    replay_hash: HashDigest
    supporting_fact_ids: tuple[str, ...] = ()
    conflicting_fact_ids: tuple[str, ...] = ()
    gate_results: tuple[GateResult, ...] = ()
    facts_used: tuple[str, ...] = ()
    assumptions: tuple[JsonValue, ...] = ()
    judgments: tuple[JsonValue, ...] = ()
    profit_bridge: JsonValue = None
    scenarios: tuple[JsonValue, ...] = ()
    expectation_class: ExpectationClass | None = None
    first_executable_at: datetime | None = None
    first_executable_price: str | None = None
    execution_window: JsonValue = None
    price_method: str | None = None
    estimated_cost_rate: str | None = None
    estimated_slippage_rate: str | None = None
    market_regime: MarketRegime | None = None
    risk_cluster_ids: tuple[str, ...] = ()
    planned_account_risk: str | None = None
    risk_limits: JsonValue = None
    target_weight: str | None = None
    approved_weight: str | None = None
    actual_weight: str | None = None
    falsifiers: tuple[str, ...] = ()
    next_verification: JsonValue = None
    block_reasons: tuple[str, ...] = ()
    approver: str | None = None
    supersedes: str | None = None

    def __post_init__(self) -> None:
        _require_schema_version(
            "decision_record_schema_version",
            self.decision_record_schema_version,
            DECISION_RECORD_SCHEMA_VERSION,
        )
        _require_id("decision_id", self.decision_id)
        _require_id("run_id", self.run_id)
        object.__setattr__(
            self,
            "decision_at",
            normalize_utc(self.decision_at, field_name="decision_at"),
        )
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.strategy_input_ref.knowledge_cutoff > self.decision_at:
            raise ValueError("knowledge_cutoff must be <= decision_at")
        _require_version("strategy_version", self.strategy_version)
        object.__setattr__(
            self,
            "rule_status",
            _coerce_enum("rule_status", RuleStatus, self.rule_status),
        )
        object.__setattr__(
            self, "event_state", _coerce_enum("event_state", EventState, self.event_state)
        )
        object.__setattr__(
            self,
            "decision_state",
            _coerce_enum("decision_state", DecisionState, self.decision_state),
        )
        object.__setattr__(
            self,
            "position_state",
            _coerce_enum("position_state", PositionState, self.position_state),
        )
        if not isinstance(self.replay_hash, HashDigest):
            raise TypeError("replay_hash must be a HashDigest")
        for field_name in (
            "supporting_fact_ids",
            "conflicting_fact_ids",
            "facts_used",
            "risk_cluster_ids",
        ):
            object.__setattr__(self, field_name, _freeze_ids(field_name, getattr(self, field_name)))
        gates = _ordered_tuple("gate_results", self.gate_results)
        if any(not isinstance(gate, GateResult) for gate in gates):
            raise TypeError("gate_results must contain only GateResult values")
        object.__setattr__(self, "gate_results", gates)
        for field_name in ("assumptions", "judgments", "scenarios"):
            values = _ordered_tuple(field_name, getattr(self, field_name))
            object.__setattr__(
                self,
                field_name,
                tuple(
                    freeze_json(item, path=f"$.{field_name}[{index}]")
                    for index, item in enumerate(values)
                ),
            )
        for field_name in (
            "profit_bridge",
            "execution_window",
            "risk_limits",
            "next_verification",
        ):
            object.__setattr__(
                self,
                field_name,
                freeze_json(getattr(self, field_name), path=f"$.{field_name}"),
            )
        if self.expectation_class is not None:
            object.__setattr__(
                self,
                "expectation_class",
                _coerce_enum("expectation_class", ExpectationClass, self.expectation_class),
            )
        if self.first_executable_at is not None:
            object.__setattr__(
                self,
                "first_executable_at",
                normalize_utc(self.first_executable_at, field_name="first_executable_at"),
            )
        for field_name in (
            "first_executable_price",
            "estimated_cost_rate",
            "estimated_slippage_rate",
            "planned_account_risk",
            "target_weight",
            "approved_weight",
            "actual_weight",
        ):
            _require_decimal(field_name, getattr(self, field_name))
        if self.price_method is not None:
            _require_text("price_method", self.price_method)
        if self.market_regime is not None:
            object.__setattr__(
                self,
                "market_regime",
                _coerce_enum("market_regime", MarketRegime, self.market_regime),
            )
        object.__setattr__(self, "falsifiers", _freeze_texts("falsifiers", self.falsifiers))
        object.__setattr__(
            self, "block_reasons", _freeze_texts("block_reasons", self.block_reasons)
        )
        if self.approver is not None:
            _require_id("approver", self.approver)
        if self.supersedes is not None:
            _require_id("supersedes", self.supersedes)
        if self.rule_status is not RuleStatus.APPROVED:
            violations: list[str] = []
            if self.decision_state not in {
                DecisionState.RESEARCH,
                DecisionState.SHADOW_ONLY,
            }:
                violations.append("decision_state must be RESEARCH or SHADOW_ONLY")
            if self.position_state is not PositionState.FLAT:
                violations.append("position_state must be FLAT")
            for field_name in ("target_weight", "approved_weight", "actual_weight"):
                if not _is_zero_or_none(getattr(self, field_name)):
                    violations.append(f"{field_name} must be zero or None")
            if self.approver is not None:
                violations.append("approver must be None")
            if violations:
                raise ValueError(
                    f"rule status {self.rule_status.value!r} is not approved: "
                    + "; ".join(violations)
                )
