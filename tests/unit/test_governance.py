from __future__ import annotations

import pytest

from invest_system.governance import (
    RuleGovernanceError,
    validate_rule_maturity,
)
from invest_system.models import DecisionState, PositionState, RuleStatus, RunMode

UNAPPROVED_RULE_STATUSES = (
    RuleStatus.REQUIREMENTS_CONFIRMED,
    RuleStatus.HYPOTHESIS,
    RuleStatus.DRAFT,
    RuleStatus.PLACEHOLDER,
    RuleStatus.TBD,
)


@pytest.mark.parametrize("rule_status", UNAPPROVED_RULE_STATUSES)
@pytest.mark.parametrize(
    ("run_mode", "decision_state"),
    [
        (RunMode.RESEARCH, DecisionState.RESEARCH),
        (RunMode.SHADOW, DecisionState.SHADOW_ONLY),
    ],
)
@pytest.mark.parametrize(
    ("target_weight", "approved_weight", "actual_weight"),
    [(None, None, None), ("0", "0.0", "-0.000")],
)
def test_unapproved_rules_are_limited_to_flat_research_or_shadow(
    rule_status: RuleStatus,
    run_mode: RunMode,
    decision_state: DecisionState,
    target_weight: str | None,
    approved_weight: str | None,
    actual_weight: str | None,
) -> None:
    validate_rule_maturity(
        rule_status=rule_status,
        run_mode=run_mode,
        decision_state=decision_state,
        position_state=PositionState.FLAT,
        target_weight=target_weight,
        approved_weight=approved_weight,
        actual_weight=actual_weight,
    )


@pytest.mark.parametrize("rule_status", UNAPPROVED_RULE_STATUSES)
@pytest.mark.parametrize(
    "override",
    [
        {"run_mode": RunMode.BACKTEST},
        {"run_mode": RunMode.PAPER},
        {"decision_state": DecisionState.TRADE_READY},
        {"decision_state": DecisionState.REJECT},
        {"decision_state": DecisionState.ABSTAIN},
        {"decision_state": DecisionState.BLOCKED},
        {"position_state": PositionState.STARTER},
        {"position_state": PositionState.CORE},
        {"target_weight": "0.0001"},
        {"approved_weight": "1"},
        {"actual_weight": "-0.1"},
        {"approver": "human_approver_001"},
    ],
)
def test_every_unapproved_rule_status_fails_closed_on_non_shadow_output(
    rule_status: RuleStatus,
    override: dict[str, object],
) -> None:
    arguments: dict[str, object] = {
        "rule_status": rule_status,
        "run_mode": RunMode.RESEARCH,
        "decision_state": DecisionState.RESEARCH,
        "position_state": PositionState.FLAT,
        "target_weight": None,
        "approved_weight": None,
        "actual_weight": None,
    }
    arguments.update(override)

    with pytest.raises(RuleGovernanceError, match="is not approved"):
        validate_rule_maturity(**arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize("weight", [0, "nan", "Infinity", "not-a-decimal"])
def test_unapproved_rule_rejects_invalid_weight_representations(weight: object) -> None:
    with pytest.raises(RuleGovernanceError):
        validate_rule_maturity(
            rule_status=RuleStatus.DRAFT,
            run_mode=RunMode.RESEARCH,
            decision_state=DecisionState.RESEARCH,
            position_state=PositionState.FLAT,
            target_weight=weight,  # type: ignore[arg-type]
        )


def test_approved_only_removes_the_rule_maturity_block() -> None:
    validate_rule_maturity(
        rule_status=RuleStatus.APPROVED,
        run_mode=RunMode.PAPER,
        decision_state=DecisionState.TRADE_READY,
        position_state=PositionState.STARTER,
        target_weight="0.01",
    )


@pytest.mark.parametrize("status", ["approved-ish", "", "APPROVED"])
def test_unknown_rule_status_is_rejected(status: str) -> None:
    with pytest.raises(RuleGovernanceError, match="rule_status must be one of"):
        validate_rule_maturity(
            rule_status=status,
            run_mode=RunMode.RESEARCH,
            decision_state=DecisionState.RESEARCH,
            position_state=PositionState.FLAT,
        )
