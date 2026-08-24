"""Pure typed inputs for the preregistered Stage 5D normal lifecycle slice.

This module materializes anonymous synthetic inputs only.  It deliberately has
no lifecycle evaluator, no I/O, no persistence, and no runtime authority.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from invest_system.canonical import canonical_sha256, normalize_utc
from invest_system.models import CanonicalModel, HashDigest, RunMode

from .stage5_market_execution import Stage5ActionIntent
from .stage5_portfolio_ledger_engine import Stage5PortfolioLedgerCase

STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION = "0.1.0"
STAGE5D_LIFECYCLE_INPUT_SCOPE = "stage5_synthetic_execution_validation"
STAGE5D_LIFECYCLE_EXIT_ORIGIN = "STAGE6C_VALIDATION_HORIZON_LIQUIDATION"
STAGE6C_V02_SPECIFICATION_SHA256 = (
    "3886580f1785d4545b02d76ca81ce449577ba406cf1d829efb8b5d4f4e55d368"
)
STAGE6C_V02_APPROVED_BUNDLE_RAW_SHA256 = (
    "77e76205b2d4de2163b914bcab2fffb0baa2087e6b89c543dfb538ac366e863a"
)
STAGE6C_V02_APPROVAL_RECORD_RAW_SHA256 = (
    "7fd3756f005f20e3c345d06549340cba9abd5a974d6cd9977121eab98d08a2a0"
)
STAGE6C_V02_APPROVAL_ID = "rule_approval_stage6_6c_development_walk_forward_v0_2_0"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
_ZERO_HASH = HashDigest(algorithm="sha256", value="0" * 64)


def _id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical ID")
    return value


def _decimal(field_name: str, value: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str) or _DECIMAL_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a canonical decimal")
    parsed = Decimal(value)
    if positive and parsed <= 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _strict_bool(field_name: str, value: bool) -> None:
    if type(value) is not bool:
        raise TypeError(f"{field_name} must be bool")


def _hash(payload: object) -> HashDigest:
    return HashDigest(algorithm="sha256", value=canonical_sha256(payload))


def _identity_payload(value: CanonicalModel, hash_field: str) -> dict[str, Any]:
    payload = value.to_json_value()
    del payload[hash_field]
    return payload


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleSession(CanonicalModel):
    schema_version: str
    ordinal: int
    session_id: str
    local_trade_date: str
    opens_at: datetime
    closes_at: datetime
    valuation_at: datetime
    session_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported lifecycle session schema_version")
        if isinstance(self.ordinal, bool) or not isinstance(self.ordinal, int) or self.ordinal < 1:
            raise ValueError("ordinal must be a positive integer")
        _id("session_id", self.session_id)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.local_trade_date):
            raise ValueError("local_trade_date must be YYYY-MM-DD")
        for name in ("opens_at", "closes_at", "valuation_at"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if not self.opens_at < self.closes_at < self.valuation_at:
            raise ValueError("session temporal order differs")
        if not isinstance(self.session_hash, HashDigest) or self.session_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "session_hash")),
        ):
            raise ValueError("session_hash differs")


def bind_stage5d_lifecycle_session(value: Stage5DLifecycleSession) -> Stage5DLifecycleSession:
    return replace(value, session_hash=_hash(_identity_payload(value, "session_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleCalendar(CanonicalModel):
    schema_version: str
    calendar_id: str
    sessions: tuple[Stage5DLifecycleSession, ...]
    construction_rule: str
    synthetic: bool
    validation_only: bool
    not_a_real_exchange_calendar: bool
    usable_for_formal_execution: bool
    calendar_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported lifecycle calendar schema_version")
        _id("calendar_id", self.calendar_id)
        sessions = tuple(self.sessions)
        if len(sessions) != 60 or any(
            not isinstance(item, Stage5DLifecycleSession) for item in sessions
        ):
            raise ValueError("calendar must contain exactly 60 typed sessions")
        if tuple(item.ordinal for item in sessions) != tuple(range(1, 61)):
            raise ValueError("calendar session ordinals differ")
        if tuple(item.local_trade_date for item in sessions) != tuple(
            sorted(item.local_trade_date for item in sessions)
        ):
            raise ValueError("calendar dates must be increasing")
        if len({item.session_id for item in sessions}) != len(sessions):
            raise ValueError("calendar session IDs must be unique")
        object.__setattr__(self, "sessions", sessions)
        if self.construction_rule != "FIRST_60_MONDAY_TO_FRIDAY_DATES_FROM_2025_01_20_INCLUSIVE":
            raise ValueError("calendar construction_rule differs")
        for name in (
            "synthetic",
            "validation_only",
            "not_a_real_exchange_calendar",
            "usable_for_formal_execution",
        ):
            _strict_bool(name, getattr(self, name))
        if (
            not self.synthetic
            or not self.validation_only
            or not self.not_a_real_exchange_calendar
            or self.usable_for_formal_execution
        ):
            raise ValueError("calendar authority boundary differs")
        if not isinstance(self.calendar_hash, HashDigest) or self.calendar_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "calendar_hash")),
        ):
            raise ValueError("calendar_hash differs")


def bind_stage5d_lifecycle_calendar(value: Stage5DLifecycleCalendar) -> Stage5DLifecycleCalendar:
    return replace(value, calendar_hash=_hash(_identity_payload(value, "calendar_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleMarkObservation(CanonicalModel):
    schema_version: str
    ordinal: int
    mark_id: str
    session_id: str
    session_hash: HashDigest
    security_id: str
    price: str
    currency: str
    observed_at: datetime
    available_at: datetime
    valuation_at: datetime
    source_id: str
    source_bytes_hash: HashDigest
    market_rule_hash: HashDigest
    unadjusted: bool
    executable: bool
    synthetic: bool
    validation_only: bool
    mark_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported lifecycle mark schema_version")
        if (
            isinstance(self.ordinal, bool)
            or not isinstance(self.ordinal, int)
            or not 1 <= self.ordinal <= 59
        ):
            raise ValueError("mark ordinal must be between 1 and 59")
        for name in ("mark_id", "session_id", "security_id", "source_id"):
            _id(name, getattr(self, name))
        _decimal("price", self.price, positive=True)
        if self.currency != "CNY":
            raise ValueError("mark currency must be CNY")
        for name in ("observed_at", "available_at", "valuation_at"):
            object.__setattr__(self, name, normalize_utc(getattr(self, name), field_name=name))
        if not self.observed_at < self.available_at or self.available_at != self.valuation_at:
            raise ValueError("mark PIT or valuation time differs")
        for name in ("session_hash", "source_bytes_hash", "market_rule_hash"):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        for name in ("unadjusted", "executable", "synthetic", "validation_only"):
            _strict_bool(name, getattr(self, name))
        if not self.unadjusted or self.executable or not self.synthetic or not self.validation_only:
            raise ValueError("mark semantic boundary differs")
        if not isinstance(self.mark_hash, HashDigest) or self.mark_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "mark_hash")),
        ):
            raise ValueError("mark_hash differs")


def bind_stage5d_lifecycle_mark(
    value: Stage5DLifecycleMarkObservation,
) -> Stage5DLifecycleMarkObservation:
    return replace(value, mark_hash=_hash(_identity_payload(value, "mark_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleMarkSet(CanonicalModel):
    schema_version: str
    mark_set_id: str
    security_id: str
    calendar_hash: HashDigest
    marks: tuple[Stage5DLifecycleMarkObservation, ...]
    mark_set_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported lifecycle mark-set schema_version")
        _id("mark_set_id", self.mark_set_id)
        _id("security_id", self.security_id)
        if not isinstance(self.calendar_hash, HashDigest):
            raise TypeError("calendar_hash must be HashDigest")
        marks = tuple(self.marks)
        if len(marks) != 59 or any(
            not isinstance(item, Stage5DLifecycleMarkObservation) for item in marks
        ):
            raise ValueError("mark set must contain exactly 59 typed marks")
        if tuple(item.ordinal for item in marks) != tuple(range(1, 60)):
            raise ValueError("mark ordinals differ")
        if any(item.security_id != self.security_id for item in marks):
            raise ValueError("mark security scope differs")
        if len({item.mark_id for item in marks}) != len(marks):
            raise ValueError("mark IDs must be unique")
        object.__setattr__(self, "marks", marks)
        if not isinstance(self.mark_set_hash, HashDigest) or self.mark_set_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "mark_set_hash")),
        ):
            raise ValueError("mark_set_hash differs")


def bind_stage5d_lifecycle_mark_set(value: Stage5DLifecycleMarkSet) -> Stage5DLifecycleMarkSet:
    return replace(value, mark_set_hash=_hash(_identity_payload(value, "mark_set_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DLifecycleMarkCoverage(CanonicalModel):
    schema_version: str
    coverage_id: str
    security_id: str
    calendar_hash: HashDigest
    mark_set_hash: HashDigest
    expected_session_ordinals: tuple[int, ...]
    observed_mark_ids: tuple[str, ...]
    complete: bool
    contains_future_mark: bool
    coverage_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported lifecycle coverage schema_version")
        _id("coverage_id", self.coverage_id)
        _id("security_id", self.security_id)
        for name in ("calendar_hash", "mark_set_hash"):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        expected = tuple(self.expected_session_ordinals)
        observed = tuple(self.observed_mark_ids)
        if expected != tuple(range(1, 60)) or len(observed) != 59:
            raise ValueError("coverage closed world differs")
        if len(set(observed)) != len(observed):
            raise ValueError("coverage mark IDs must be unique")
        object.__setattr__(self, "expected_session_ordinals", expected)
        object.__setattr__(self, "observed_mark_ids", observed)
        for name in ("complete", "contains_future_mark"):
            _strict_bool(name, getattr(self, name))
        if not self.complete or self.contains_future_mark:
            raise ValueError("coverage must be complete and PIT-safe")
        if not isinstance(self.coverage_hash, HashDigest) or self.coverage_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "coverage_hash")),
        ):
            raise ValueError("coverage_hash differs")


def bind_stage5d_lifecycle_mark_coverage(
    value: Stage5DLifecycleMarkCoverage,
) -> Stage5DLifecycleMarkCoverage:
    return replace(value, coverage_hash=_hash(_identity_payload(value, "coverage_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DValidationHorizonExitMandate(CanonicalModel):
    schema_version: str
    mandate_id: str
    candidate_id: str
    strategy_id: str
    security_id: str
    account_fixture_id: str
    exit_origin: str
    exit_session_ordinal: int
    exit_decision_at: datetime
    full_exit_required: bool
    validates_stage4_exit_rule: bool
    stage6c_specification_hash: HashDigest
    stage6c_approved_bundle_raw_hash: HashDigest
    stage6c_approval_record_raw_hash: HashDigest
    stage6c_approval_id: str
    synthetic: bool
    validation_only: bool
    authority_eligible: bool
    mandate_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported exit mandate schema_version")
        for name in (
            "mandate_id",
            "candidate_id",
            "strategy_id",
            "security_id",
            "account_fixture_id",
            "stage6c_approval_id",
        ):
            _id(name, getattr(self, name))
        if self.exit_origin != STAGE5D_LIFECYCLE_EXIT_ORIGIN or self.exit_session_ordinal != 60:
            raise ValueError("exit mandate origin or session differs")
        object.__setattr__(
            self,
            "exit_decision_at",
            normalize_utc(self.exit_decision_at, field_name="exit_decision_at"),
        )
        for name in (
            "full_exit_required",
            "validates_stage4_exit_rule",
            "synthetic",
            "validation_only",
            "authority_eligible",
        ):
            _strict_bool(name, getattr(self, name))
        if (
            not self.full_exit_required
            or self.validates_stage4_exit_rule
            or not self.synthetic
            or not self.validation_only
            or self.authority_eligible
        ):
            raise ValueError("exit mandate boundary differs")
        expected = {
            "stage6c_specification_hash": STAGE6C_V02_SPECIFICATION_SHA256,
            "stage6c_approved_bundle_raw_hash": STAGE6C_V02_APPROVED_BUNDLE_RAW_SHA256,
            "stage6c_approval_record_raw_hash": STAGE6C_V02_APPROVAL_RECORD_RAW_SHA256,
        }
        for name, digest in expected.items():
            value = getattr(self, name)
            if not isinstance(value, HashDigest) or value.value != digest:
                raise ValueError(f"{name} differs")
        if self.stage6c_approval_id != STAGE6C_V02_APPROVAL_ID:
            raise ValueError("stage6c_approval_id differs")
        if not isinstance(self.mandate_hash, HashDigest) or self.mandate_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "mandate_hash")),
        ):
            raise ValueError("mandate_hash differs")


def bind_stage5d_exit_mandate(
    value: Stage5DValidationHorizonExitMandate,
) -> Stage5DValidationHorizonExitMandate:
    return replace(value, mandate_hash=_hash(_identity_payload(value, "mandate_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DExitInputClosure(CanonicalModel):
    schema_version: str
    closure_id: str
    exit_stage5c_case_hash: HashDigest
    exit_mandate_hash: HashDigest
    stage5_market_rule_hashes: tuple[HashDigest, ...]
    stage5_trading_calendar_hash: HashDigest
    stage5_cost_schedule_hashes: tuple[HashDigest, ...]
    stage5_impact_curve_hashes: tuple[HashDigest, ...]
    stage5_settlement_terms_hashes: tuple[HashDigest, ...]
    synthetic: bool
    validation_only: bool
    closure_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported exit closure schema_version")
        _id("closure_id", self.closure_id)
        for name in (
            "exit_stage5c_case_hash",
            "exit_mandate_hash",
            "stage5_trading_calendar_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        for name in (
            "stage5_market_rule_hashes",
            "stage5_cost_schedule_hashes",
            "stage5_impact_curve_hashes",
            "stage5_settlement_terms_hashes",
        ):
            values = tuple(getattr(self, name))
            if not values or any(not isinstance(item, HashDigest) for item in values):
                raise ValueError(f"{name} must contain typed hashes")
            object.__setattr__(self, name, values)
        for name in ("synthetic", "validation_only"):
            _strict_bool(name, getattr(self, name))
        if not self.synthetic or not self.validation_only:
            raise ValueError("exit closure must remain synthetic validation")
        if not isinstance(self.closure_hash, HashDigest) or self.closure_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "closure_hash")),
        ):
            raise ValueError("closure_hash differs")


def bind_stage5d_exit_input_closure(value: Stage5DExitInputClosure) -> Stage5DExitInputClosure:
    return replace(value, closure_hash=_hash(_identity_payload(value, "closure_hash")))


@dataclass(frozen=True, slots=True)
class Stage5DNormalLifecycleMaterializedInputs(CanonicalModel):
    schema_version: str
    input_set_id: str
    preregistration_raw_hash: HashDigest
    entry_complete_replay_hash: HashDigest
    entry_ending_journal_head_hash: HashDigest
    entry_derived_lot_hash: HashDigest
    exit_stage5c_case: Stage5PortfolioLedgerCase
    lifecycle_calendar: Stage5DLifecycleCalendar
    mark_set: Stage5DLifecycleMarkSet
    mark_coverage: Stage5DLifecycleMarkCoverage
    exit_mandate: Stage5DValidationHorizonExitMandate
    exit_input_closure: Stage5DExitInputClosure
    exit_account_snapshot_crosscheck_only: bool
    evaluator_implementation_authorized: bool
    run_mode: RunMode
    synthetic: bool
    validation_only: bool
    authority_eligible: bool
    persists_state: bool
    connects_broker: bool
    reads_kb_internal_state: bool
    writes_kb: bool
    input_set_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION:
            raise ValueError("unsupported materialized input schema_version")
        _id("input_set_id", self.input_set_id)
        for name in (
            "preregistration_raw_hash",
            "entry_complete_replay_hash",
            "entry_ending_journal_head_hash",
            "entry_derived_lot_hash",
        ):
            if not isinstance(getattr(self, name), HashDigest):
                raise TypeError(f"{name} must be HashDigest")
        if not isinstance(self.exit_stage5c_case, Stage5PortfolioLedgerCase):
            raise TypeError("exit_stage5c_case must be Stage5PortfolioLedgerCase")
        for name, expected_type in (
            ("lifecycle_calendar", Stage5DLifecycleCalendar),
            ("mark_set", Stage5DLifecycleMarkSet),
            ("mark_coverage", Stage5DLifecycleMarkCoverage),
            ("exit_mandate", Stage5DValidationHorizonExitMandate),
            ("exit_input_closure", Stage5DExitInputClosure),
        ):
            if not isinstance(getattr(self, name), expected_type):
                raise TypeError(f"{name} has the wrong type")
        market_case = self.exit_stage5c_case.market_execution_case
        if market_case.action_intent is not Stage5ActionIntent.EXIT:
            raise ValueError("exit Stage5C case must use EXIT")
        if (
            market_case.proposed_quantity != 200
            or self.exit_stage5c_case.synthetic_portfolio_approval.approved_quantity != 200
        ):
            raise ValueError("exit Stage5C approval must be 200")
        if market_case.risk_exit_mandate_ref != self.exit_mandate.mandate_id:
            raise ValueError("exit Stage5C mandate ref differs")
        if (
            market_case.security_id != self.exit_mandate.security_id
            or market_case.strategy_id != self.exit_mandate.strategy_id
            or market_case.account_fixture_id != self.exit_mandate.account_fixture_id
        ):
            raise ValueError("exit Stage5C mandate scope differs")
        account = self.exit_stage5c_case.synthetic_account_snapshot
        if (
            account.available_cash != "98386.77"
            or account.net_asset_value != "99986.77"
            or len(account.positions) != 1
            or len(account.positions[0].lots) != 1
            or account.positions[0].quantity != 200
            or account.positions[0].sellable_quantity != 200
            or account.positions[0].lots[0].full_cost != "1613.23"
        ):
            raise ValueError("exit Stage5C opening crosscheck differs")
        if (
            not self.exit_stage5c_case.corporate_action_set.explicitly_empty_for_stage5c
            or self.exit_stage5c_case.corporate_action_set.applicable_action_ids
        ):
            raise ValueError("exit Stage5C corporate actions must be explicitly empty")
        if self.mark_set.calendar_hash != self.lifecycle_calendar.calendar_hash:
            raise ValueError("mark-set calendar hash differs")
        if self.mark_coverage.calendar_hash != self.lifecycle_calendar.calendar_hash:
            raise ValueError("coverage calendar hash differs")
        if self.mark_coverage.mark_set_hash != self.mark_set.mark_set_hash:
            raise ValueError("coverage mark-set hash differs")
        if self.mark_coverage.observed_mark_ids != tuple(
            item.mark_id for item in self.mark_set.marks
        ):
            raise ValueError("coverage observed mark IDs differ")
        if any(
            mark.session_hash != self.lifecycle_calendar.sessions[mark.ordinal - 1].session_hash
            for mark in self.mark_set.marks
        ):
            raise ValueError("mark session binding differs")
        materialized_hashes = (
            self.lifecycle_calendar.calendar_hash,
            self.mark_set.mark_set_hash,
            self.mark_coverage.coverage_hash,
            self.exit_mandate.mandate_hash,
            self.exit_input_closure.closure_hash,
            *(item.session_hash for item in self.lifecycle_calendar.sessions),
            *(item.mark_hash for item in self.mark_set.marks),
        )
        if any(item == _ZERO_HASH for item in materialized_hashes):
            raise ValueError("materialized lifecycle input hashes must be non-zero")
        closure = self.exit_input_closure
        if closure.exit_stage5c_case_hash.value != canonical_sha256(self.exit_stage5c_case):
            raise ValueError("exit closure case hash differs")
        if closure.exit_mandate_hash != self.exit_mandate.mandate_hash:
            raise ValueError("exit closure mandate hash differs")
        if closure.stage5_market_rule_hashes != tuple(
            item.identity.declared_content_hash for item in market_case.market_rule_sets
        ):
            raise ValueError("exit closure market-rule hashes differ")
        if closure.stage5_trading_calendar_hash != (
            market_case.trading_calendar.identity.declared_content_hash
        ):
            raise ValueError("exit closure trading-calendar hash differs")
        if closure.stage5_cost_schedule_hashes != tuple(
            item.identity.declared_content_hash for item in market_case.cost_schedules
        ):
            raise ValueError("exit closure cost hashes differ")
        if closure.stage5_impact_curve_hashes != tuple(
            item.identity.declared_content_hash for item in market_case.impact_curves
        ):
            raise ValueError("exit closure impact hashes differ")
        if closure.stage5_settlement_terms_hashes != tuple(
            item.identity.declared_content_hash for item in self.exit_stage5c_case.settlement_terms
        ):
            raise ValueError("exit closure settlement hashes differ")
        for name in (
            "exit_account_snapshot_crosscheck_only",
            "evaluator_implementation_authorized",
            "synthetic",
            "validation_only",
            "authority_eligible",
            "persists_state",
            "connects_broker",
            "reads_kb_internal_state",
            "writes_kb",
        ):
            _strict_bool(name, getattr(self, name))
        if (
            not self.exit_account_snapshot_crosscheck_only
            or self.evaluator_implementation_authorized
            or self.run_mode is not RunMode.RESEARCH
            or not self.synthetic
            or not self.validation_only
            or self.authority_eligible
            or self.persists_state
            or self.connects_broker
            or self.reads_kb_internal_state
            or self.writes_kb
            or self.exit_stage5c_case.run_mode is not RunMode.RESEARCH
            or not self.exit_stage5c_case.anonymous_synthetic_fixture
            or not self.exit_stage5c_case.validation_only
            or self.exit_stage5c_case.persists_state
            or self.exit_stage5c_case.connects_broker
            or self.exit_stage5c_case.reads_kb_internal_state
        ):
            raise ValueError("materialized input authority boundary differs")
        if not isinstance(self.input_set_hash, HashDigest) or self.input_set_hash not in (
            _ZERO_HASH,
            _hash(_identity_payload(self, "input_set_hash")),
        ):
            raise ValueError("input_set_hash differs")


def bind_stage5d_normal_lifecycle_inputs(
    value: Stage5DNormalLifecycleMaterializedInputs,
) -> Stage5DNormalLifecycleMaterializedInputs:
    return replace(value, input_set_hash=_hash(_identity_payload(value, "input_set_hash")))


__all__ = [
    "STAGE5D_LIFECYCLE_EXIT_ORIGIN",
    "STAGE5D_LIFECYCLE_INPUT_SCHEMA_VERSION",
    "STAGE5D_LIFECYCLE_INPUT_SCOPE",
    "STAGE6C_V02_APPROVAL_ID",
    "STAGE6C_V02_APPROVAL_RECORD_RAW_SHA256",
    "STAGE6C_V02_APPROVED_BUNDLE_RAW_SHA256",
    "STAGE6C_V02_SPECIFICATION_SHA256",
    "Stage5DExitInputClosure",
    "Stage5DLifecycleCalendar",
    "Stage5DLifecycleMarkCoverage",
    "Stage5DLifecycleMarkObservation",
    "Stage5DLifecycleMarkSet",
    "Stage5DLifecycleSession",
    "Stage5DNormalLifecycleMaterializedInputs",
    "Stage5DValidationHorizonExitMandate",
    "bind_stage5d_exit_input_closure",
    "bind_stage5d_exit_mandate",
    "bind_stage5d_lifecycle_calendar",
    "bind_stage5d_lifecycle_mark",
    "bind_stage5d_lifecycle_mark_coverage",
    "bind_stage5d_lifecycle_mark_set",
    "bind_stage5d_lifecycle_session",
    "bind_stage5d_normal_lifecycle_inputs",
]
