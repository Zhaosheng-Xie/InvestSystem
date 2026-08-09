from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from invest_system.strategies.industrial_event.stage5_execution_contracts import (
    bind_stage5c_artifact,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ExecutionStatus,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    evaluate_stage5_portfolio_ledger,
)
from unit import test_stage5_portfolio_ledger as stage5c_support


def test_stage5c_rejects_unbound_settlement_special_exception(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root)
    terms = case.settlement_terms[0]
    exceptional_terms = bind_stage5c_artifact(
        replace(terms, special_exception_id="unbound_synthetic_exception")
    )

    result = evaluate_stage5_portfolio_ledger(
        replace(case, settlement_terms=(exceptional_terms,)),
        market_rules,
        portfolio_rules,
    )

    assert result.status is Stage5ExecutionStatus.RECONCILIATION_BLOCKED
    assert result.reason_codes == ("SETTLEMENT_SPECIAL_EXCEPTION_CONTRACT_NOT_IMPLEMENTED",)
    assert result.fill_ledger_projection is None
