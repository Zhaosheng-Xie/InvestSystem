"""Fail-closed Stage 1 governance for rule maturity.

This module does not approve a strategy or implement decision semantics.  It
only prevents non-approved rule material from escaping research/shadow mode or
creating a non-zero position.  Additional approval, risk, and execution gates
belong to later stages.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum

from .models import DecisionState, PositionState, RuleStatus, RunMode


class RuleGovernanceError(ValueError):
    """Raised when a rule-maturity boundary would be crossed."""


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: object) -> EnumT:
    try:
        if isinstance(value, enum_type):
            return value
        if not isinstance(value, str):
            raise TypeError
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise RuleGovernanceError(f"{field_name} must be one of: {allowed}") from exc


def _is_zero_or_none(field_name: str, value: str | None) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        raise RuleGovernanceError(f"{field_name} must be a decimal string or None")
    try:
        decimal_value = Decimal(value)
    except InvalidOperation as exc:
        raise RuleGovernanceError(f"{field_name} must be a decimal string or None") from exc
    if not decimal_value.is_finite():
        raise RuleGovernanceError(f"{field_name} must be finite")
    return decimal_value == 0


def validate_rule_maturity(
    *,
    rule_status: RuleStatus | str,
    run_mode: RunMode | str,
    decision_state: DecisionState | str,
    position_state: PositionState | str,
    target_weight: str | None = None,
    approved_weight: str | None = None,
    actual_weight: str | None = None,
    approver: str | None = None,
) -> None:
    """Reject unsafe outputs from any rule bundle that is not ``approved``.

    Passing this guard never grants paper/live authority and never creates a
    ``TRADE_READY`` decision.  For approved rules it only confirms that rule
    maturity is not the blocking reason; all later decision and human-approval
    gates still apply.
    """

    status = _coerce_enum("rule_status", RuleStatus, rule_status)
    mode = _coerce_enum("run_mode", RunMode, run_mode)
    decision = _coerce_enum("decision_state", DecisionState, decision_state)
    position = _coerce_enum("position_state", PositionState, position_state)

    if status is RuleStatus.APPROVED:
        return

    violations: list[str] = []
    if mode not in {RunMode.RESEARCH, RunMode.SHADOW}:
        violations.append("run_mode must be research or shadow")
    if decision not in {DecisionState.RESEARCH, DecisionState.SHADOW_ONLY}:
        violations.append("decision_state must be RESEARCH or SHADOW_ONLY")
    if position is not PositionState.FLAT:
        violations.append("position_state must be FLAT")

    for field_name, value in (
        ("target_weight", target_weight),
        ("approved_weight", approved_weight),
        ("actual_weight", actual_weight),
    ):
        if not _is_zero_or_none(field_name, value):
            violations.append(f"{field_name} must be zero or None")
    if approver is not None:
        violations.append("approver must be None")

    if violations:
        detail = "; ".join(violations)
        raise RuleGovernanceError(f"rule status {status.value!r} is not approved: {detail}")
