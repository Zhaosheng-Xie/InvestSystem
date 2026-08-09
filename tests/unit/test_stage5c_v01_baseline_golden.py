"""Immutable Stage 5C v0.1 baseline consumed by later Stage 5D work."""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from invest_system.canonical import canonical_sha256
from invest_system.strategies.industrial_event.stage5_execution_contracts import (
    STAGE5C_CONTRACT_SCHEMA_VERSION,
)
from invest_system.strategies.industrial_event.stage5_fill_projection import (
    Stage5FillLedgerProjection,
)
from invest_system.strategies.industrial_event.stage5_ledger import (
    STAGE5C_LEDGER_PRIORITY,
    DerivedLedgerLot,
    DerivedLedgerState,
    LedgerAccountCode,
    LedgerBalance,
    LedgerEvent,
    LedgerEventType,
    LedgerLotEffect,
    LedgerPosting,
    LedgerReplayResult,
    LedgerReplayStatus,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ExecutionStatus,
)
from invest_system.strategies.industrial_event.stage5_portfolio_ledger_engine import (
    STAGE5C_ENGINE_SCHEMA_VERSION,
    Stage5PortfolioLedgerCase,
    Stage5PortfolioLedgerResult,
    Stage5PositionLayers,
    evaluate_stage5_portfolio_ledger,
    stage5c_portfolio_ledger_projection_sha256,
)
from unit import test_stage5_portfolio_ledger as stage5c_support

RAW_CASE_SHA256 = "06a9eaac57fec706b7bda7566494256cd0df045e1bdab2d826a1a85066a1ee62"
RESULT_SHA256 = "daf123cd8ad8418a5794c5aa86f08b66d6c18e3aebd1cdef58cae1b0d88dab59"
PROJECTION_SHA256 = "0ff3bca75b0561a9aa9fd176d4a4517de157224e80cfab40aa9019c75cf5d3eb"
PROJECTED_V1_EVENT_SHA256 = (
    "1c72a2376b54605c1601920af42c96e7d5a7f86cab1f79bfa5038a7baf8d95e2",
    "5fae923ec9fa1575e06f544d645e1a1e4f33bc7315a3a0a67001b3a41432c542",
    "7a2c86667f5b60205e90b5042f8cb1723955f141e96c56a8b3a28c9d7cfd7b8f",
    "62b9bf472a38dde5470758f7b8ef2be5c08d235b442a2d7c386ca6b492962742",
    "c1b9c6e99876205016fa72d7cdf9594e5c34412c2679d3b1425f17f024039470",
    "64e1545538875d48a61a3a4a889aac7ea6093370d76bc31d45994b8da82cebb4",
    "1b8035b9d0b819aecec45ab3cda1e6f83ab1985aef65b17ef656dee7e4583c79",
    "fbc697cc1a5ad27fc7dbbcba3091a61780db6f7981ec46f36c763aff7fd05c2d",
    "a2d73c906baf8731641b4e3548e5d153c11355ce584eee9ef6ae067cc9cfb967",
)
ORDERED_ACCEPTED_V1_EVENT_SHA256 = (
    "1c72a2376b54605c1601920af42c96e7d5a7f86cab1f79bfa5038a7baf8d95e2",
    "7a2c86667f5b60205e90b5042f8cb1723955f141e96c56a8b3a28c9d7cfd7b8f",
    "5fae923ec9fa1575e06f544d645e1a1e4f33bc7315a3a0a67001b3a41432c542",
    "62b9bf472a38dde5470758f7b8ef2be5c08d235b442a2d7c386ca6b492962742",
    "c1b9c6e99876205016fa72d7cdf9594e5c34412c2679d3b1425f17f024039470",
    "64e1545538875d48a61a3a4a889aac7ea6093370d76bc31d45994b8da82cebb4",
    "1b8035b9d0b819aecec45ab3cda1e6f83ab1985aef65b17ef656dee7e4583c79",
    "fbc697cc1a5ad27fc7dbbcba3091a61780db6f7981ec46f36c763aff7fd05c2d",
    "a2d73c906baf8731641b4e3548e5d153c11355ce584eee9ef6ae067cc9cfb967",
)
JOURNAL_HEAD_SHA256 = "0ae3d4bbe6b465db620cc07780135a9dc5867c59fc5eb4c9e9106a8f56f3a905"

SELL_RAW_CASE_SHA256 = "cb9b08c4590cecff47f9e3c0777cc1229eea2523b07c1da4cedd19228a2484fe"
SELL_RESULT_SHA256 = "12e92312a23c80311c65b0c26232fba552e8efcaffbb3ee32bb32cf59a045234"
SELL_PROJECTION_SHA256 = "360565d797bde2b89d528fe089b50b9dc704aaf164f574b0a327bb9fc9b20199"
SELL_ORDERED_V1_EVENT_SHA256 = (
    "b4457ec18477506facbfe1e06a30a4609998de7a547cbfd85dc747a5127102e5",
    "31f8ab48214c8d04e0ebc44b2537676401daf964ebe34b4ce586903462282595",
    "537cc4a299c2f65bd5697a887605760cc804a69e959197e87469683477354b86",
    "746ebd39fc1850f816b23ca0711b3931c0040e23bbff7f52bbbbe2f9b703e2be",
    "8ec012d136a99785d075896a894fa373feeabce87fb741367e7ca0993042cf89",
    "6985216bba1a070b8f58ac7be7795562f3613efcba271df89c15e19e2bca0ccf",
    "07dac918f4e3eb91f7e7989c91c81cc3e5743068dabfc75bd5b48d6e87c1274d",
)
SELL_JOURNAL_HEAD_SHA256 = "a064f13f08b50947ab713ab5c92f46866d19b2f40cb4bcf6dea9132736761235"

NO_FILL_RAW_CASE_SHA256 = "b772340347b92d15162f12443982a35c7c9c4570c45a4b32e2b80558a709ecb3"
NO_FILL_RESULT_SHA256 = "1b9c71f31e2ff5507b85fe1e06e515183fcda0f7c669f204cd702eced05aceda"
NO_FILL_PROJECTION_SHA256 = "2b03839261ca6473f471b1551b021427e0110548784b9d50194e28155ebb3e64"
NO_FILL_OPENING_EVENT_SHA256 = "1c72a2376b54605c1601920af42c96e7d5a7f86cab1f79bfa5038a7baf8d95e2"
NO_FILL_JOURNAL_HEAD_SHA256 = "c1bcec9052751af5c8299d97d4cea8e01a545139f2634260d343e20ab7f98fbb"

V1_PUBLIC_SCHEMA_DESCRIPTOR = {
    "dataclass_fields": (
        (
            "Stage5PortfolioLedgerCase",
            (
                "case_id",
                "market_execution_case",
                "synthetic_account_snapshot",
                "risk_cluster_snapshot",
                "market_regime_snapshot",
                "stress_scenario_input",
                "portfolio_sizing_inputs",
                "synthetic_portfolio_approval",
                "initial_ledger_snapshot",
                "settlement_terms",
                "corporate_action_set",
                "target_identity",
                "constraint_identity",
                "code_commit",
                "config_hash",
                "injected_clock",
                "run_mode",
                "anonymous_synthetic_fixture",
                "validation_only",
                "reads_kb_internal_state",
                "connects_broker",
                "persists_state",
            ),
        ),
        (
            "Stage5PositionLayers",
            (
                "target_quantity",
                "approved_quantity",
                "submitted_quantity",
                "filled_quantity",
                "actual_quantity",
                "unsubmitted_approved_quantity",
                "unfilled_cancelled_quantity",
                "reason_codes",
            ),
        ),
        (
            "Stage5PortfolioLedgerResult",
            (
                "schema_version",
                "case_id",
                "status",
                "reason_codes",
                "input_hash",
                "rule_bundle_hash",
                "rule_approval_id",
                "rule_approval_record_hash",
                "portfolio_risk_evaluation",
                "portfolio_approval_hash",
                "market_candidate",
                "submission_constraint",
                "constrained_market_projection",
                "fill_ledger_projection",
                "ledger_replay",
                "position_layers",
                "ledger_replay_as_of",
                "projection_replay_hash",
                "decimal_context_id",
                "approval_scope",
                "run_mode",
                "synthetic",
                "validation_only",
                "not_a_complete_stage5_replay",
                "persists_state",
                "authorizes_backtest",
                "authorizes_paper",
                "authorizes_shadow",
                "authorizes_live",
                "authorizes_real_accounts",
                "authorizes_positions",
                "authorizes_orders",
                "connects_broker",
            ),
        ),
        (
            "Stage5FillLedgerProjection",
            (
                "events",
                "unsubmitted_approved_quantity",
                "unfilled_cancelled_quantity",
                "reason_codes",
                "projection_hash",
                "synthetic",
                "validation_only",
                "persists_state",
            ),
        ),
        (
            "LedgerEvent",
            (
                "ledger_event_id",
                "idempotency_key",
                "event_type",
                "event_type_priority",
                "strategy_id",
                "account_fixture_id",
                "security_id",
                "effective_at",
                "trade_date",
                "settlement_date",
                "source_object_ids",
                "source_hashes",
                "postings",
                "lot_effects",
                "rule_ids",
                "rule_versions",
                "rule_hashes",
                "supersedes_or_reversal_of",
                "declared_canonical_hash",
            ),
        ),
        ("LedgerPosting", ("account", "currency_or_security", "debit", "credit")),
        (
            "LedgerLotEffect",
            (
                "lot_id",
                "security_id",
                "quantity_delta",
                "sellable_quantity_delta",
                "full_cost_delta",
                "acquired_at",
                "governing_market_rule_hash",
                "source_fill_id",
            ),
        ),
        ("LedgerBalance", ("account", "currency_or_security", "debit_less_credit")),
        (
            "DerivedLedgerLot",
            (
                "lot_id",
                "security_id",
                "acquired_at",
                "original_quantity",
                "remaining_quantity",
                "sellable_quantity",
                "remaining_full_cost",
                "governing_market_rule_hash",
                "source_fill_id",
            ),
        ),
        (
            "DerivedLedgerState",
            (
                "balances",
                "lots",
                "journal_head_hash",
                "available_cash",
                "reserved_cash",
                "unsettled_cash_receivable",
                "unsettled_cash_payable",
                "settled_unavailable_cash",
            ),
        ),
        (
            "LedgerReplayResult",
            (
                "status",
                "reason_codes",
                "accepted_events",
                "derived_state",
                "in_memory_reconciled",
                "persists_state",
                "atomic_durable_commit",
                "full_cost_to_security_cost_reconciled",
            ),
        ),
    ),
    "enum_values": (
        (
            "LedgerEventType",
            (
                "OPENING_BALANCE",
                "CASH_RESERVATION",
                "CASH_RELEASE",
                "SYNTHETIC_ORDER_ACCEPTED",
                "SYNTHETIC_ORDER_CANCELLED",
                "TRADE_FILL",
                "FEE",
                "TAX",
                "TRADE_SETTLEMENT",
                "SECURITY_AVAILABILITY",
                "CASH_DIVIDEND",
                "SHARE_DISTRIBUTION",
                "SPLIT_OR_CONSOLIDATION",
                "RIGHTS_OR_ALLOTMENT",
                "DELISTING_OR_CASH_OUT",
                "MARK_TO_MARKET",
                "EXTERNAL_CASH_FLOW",
                "REVERSAL",
                "REPLACEMENT",
            ),
        ),
        (
            "LedgerAccountCode",
            (
                "CASH_AVAILABLE",
                "CASH_RESERVED",
                "CASH_RECEIVABLE",
                "CASH_SETTLED_UNAVAILABLE",
                "CASH_PAYABLE",
                "SECURITY_COST",
                "FEE_EXPENSE",
                "TAX_EXPENSE",
                "TRADE_CLEARING",
                "OPENING_CONTROL",
                "SECURITY_UNSETTLED",
                "SECURITY_UNSELLABLE",
                "SECURITY_SELLABLE",
                "SECURITY_CONTROL",
            ),
        ),
        (
            "LedgerReplayStatus",
            ("RECONCILED", "PRECHECK_BLOCKED", "RECONCILIATION_BLOCKED"),
        ),
    ),
    "ledger_priority": (
        ("REVERSAL", 5),
        ("OPENING_BALANCE", 10),
        ("CASH_RESERVATION", 20),
        ("SYNTHETIC_ORDER_ACCEPTED", 30),
        ("TRADE_FILL", 40),
        ("FEE", 50),
        ("TAX", 51),
        ("SYNTHETIC_ORDER_CANCELLED", 60),
        ("CASH_RELEASE", 70),
        ("TRADE_SETTLEMENT", 80),
        ("SECURITY_AVAILABILITY", 90),
        ("REPLACEMENT", 95),
        ("CASH_DIVIDEND", 100),
        ("SHARE_DISTRIBUTION", 101),
        ("SPLIT_OR_CONSOLIDATION", 102),
        ("RIGHTS_OR_ALLOTMENT", 103),
        ("DELISTING_OR_CASH_OUT", 104),
        ("MARK_TO_MARKET", 105),
        ("EXTERNAL_CASH_FLOW", 106),
    ),
}
V1_PUBLIC_SCHEMA_DESCRIPTOR_SHA256 = (
    "dfdd8439d9f98771177c6fbab6b1e4ef7a07645b67ae90a1f20ca1260f042046"
)


def _runtime_v1_public_schema_descriptor() -> dict[str, object]:
    classes = (
        Stage5PortfolioLedgerCase,
        Stage5PositionLayers,
        Stage5PortfolioLedgerResult,
        Stage5FillLedgerProjection,
        LedgerEvent,
        LedgerPosting,
        LedgerLotEffect,
        LedgerBalance,
        DerivedLedgerLot,
        DerivedLedgerState,
        LedgerReplayResult,
    )
    return {
        "dataclass_fields": tuple(
            (value.__name__, tuple(item.name for item in fields(value))) for value in classes
        ),
        "enum_values": (
            ("LedgerEventType", tuple(item.value for item in LedgerEventType)),
            ("LedgerAccountCode", tuple(item.value for item in LedgerAccountCode)),
            ("LedgerReplayStatus", tuple(item.value for item in LedgerReplayStatus)),
        ),
        "ledger_priority": tuple(
            (event_type.value, priority) for event_type, priority in STAGE5C_LEDGER_PRIORITY.items()
        ),
    }


def test_stage5c_v01_deterministic_buy_baseline_is_byte_stable(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)
    repeated = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert STAGE5C_CONTRACT_SCHEMA_VERSION == "0.1.0"
    assert STAGE5C_ENGINE_SCHEMA_VERSION == "0.1.0"
    assert result.schema_version == "0.1.0"
    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    assert result.fill_ledger_projection is not None
    assert result.ledger_replay.derived_state is not None

    assert canonical_sha256(case) == RAW_CASE_SHA256
    assert canonical_sha256(result) == RESULT_SHA256
    assert canonical_sha256(repeated) == RESULT_SHA256
    assert stage5c_portfolio_ledger_projection_sha256(case, result) == PROJECTION_SHA256
    assert result.projection_replay_hash.value == PROJECTION_SHA256
    assert (
        tuple(event.declared_canonical_hash.value for event in result.fill_ledger_projection.events)
        == PROJECTED_V1_EVENT_SHA256
    )
    assert (
        tuple(event.declared_canonical_hash.value for event in result.ledger_replay.accepted_events)
        == ORDERED_ACCEPTED_V1_EVENT_SHA256
    )
    assert result.ledger_replay.derived_state.journal_head_hash.value == JOURNAL_HEAD_SHA256

    assert result.position_layers is not None
    assert (
        result.position_layers.target_quantity,
        result.position_layers.approved_quantity,
        result.position_layers.submitted_quantity,
        result.position_layers.filled_quantity,
        result.position_layers.actual_quantity,
    ) == (300, 300, 200, 200, 200)
    assert result.ledger_replay.derived_state.actual_quantity("600000.SH") == 200
    assert result.ledger_replay.derived_state.sellable_quantity("600000.SH") == 200
    assert result.persists_state is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False


def test_stage5c_v01_public_schema_descriptor_is_frozen() -> None:
    runtime = _runtime_v1_public_schema_descriptor()

    assert runtime == V1_PUBLIC_SCHEMA_DESCRIPTOR
    assert canonical_sha256(V1_PUBLIC_SCHEMA_DESCRIPTOR) == V1_PUBLIC_SCHEMA_DESCRIPTOR_SHA256


def test_stage5c_v01_sell_fifo_cost_receivable_and_cash_release_are_byte_stable(
    repository_root: Path,
) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root, sell=True)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.FILLED
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    assert result.fill_ledger_projection is not None
    assert result.ledger_replay.derived_state is not None
    assert canonical_sha256(case) == SELL_RAW_CASE_SHA256
    assert canonical_sha256(result) == SELL_RESULT_SHA256
    assert stage5c_portfolio_ledger_projection_sha256(case, result) == SELL_PROJECTION_SHA256
    assert result.projection_replay_hash.value == SELL_PROJECTION_SHA256
    assert (
        tuple(event.declared_canonical_hash.value for event in result.fill_ledger_projection.events)
        == SELL_ORDERED_V1_EVENT_SHA256
    )
    assert (
        tuple(event.declared_canonical_hash.value for event in result.ledger_replay.accepted_events)
        == SELL_ORDERED_V1_EVENT_SHA256
    )
    assert result.ledger_replay.derived_state.journal_head_hash.value == (SELL_JOURNAL_HEAD_SHA256)
    assert tuple(event.event_type for event in result.ledger_replay.accepted_events) == (
        LedgerEventType.OPENING_BALANCE,
        LedgerEventType.SYNTHETIC_ORDER_ACCEPTED,
        LedgerEventType.TRADE_FILL,
        LedgerEventType.FEE,
        LedgerEventType.TAX,
        LedgerEventType.TRADE_SETTLEMENT,
        LedgerEventType.CASH_RELEASE,
    )

    state = result.ledger_replay.derived_state
    assert tuple(lot.lot_id for lot in state.lots) == ("opening_lot_002",)
    assert state.lots[0].remaining_quantity == 100
    assert state.lots[0].sellable_quantity == 50
    assert state.lots[0].remaining_full_cost == "800"
    assert state.available_cash == "91585.18"
    assert state.unsettled_cash_receivable == "0"
    assert state.settled_unavailable_cash == "0"
    balances = {
        (item.account, item.currency_or_security): item.debit_less_credit for item in state.balances
    }
    assert balances[(LedgerAccountCode.FEE_EXPENSE, "CNY")] == "5.22"
    assert balances[(LedgerAccountCode.TAX_EXPENSE, "CNY")] == "1.6"
    assert balances[(LedgerAccountCode.SECURITY_COST, "CNY")] == "800"
    assert result.position_layers is not None
    assert (
        result.position_layers.target_quantity,
        result.position_layers.approved_quantity,
        result.position_layers.submitted_quantity,
        result.position_layers.filled_quantity,
        result.position_layers.actual_quantity,
    ) == (200, 200, 200, 200, 100)


def test_stage5c_v01_explicit_no_fill_path_is_byte_stable(repository_root: Path) -> None:
    case, market_rules, portfolio_rules = stage5c_support._case(repository_root, reject=True)
    result = evaluate_stage5_portfolio_ledger(case, market_rules, portfolio_rules)

    assert result.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
    assert result.market_candidate is None
    assert result.submission_constraint is None
    assert result.constrained_market_projection is None
    assert result.fill_ledger_projection is None
    assert result.ledger_replay is not None
    assert result.ledger_replay.status is LedgerReplayStatus.RECONCILED
    assert result.ledger_replay.derived_state is not None
    assert canonical_sha256(case) == NO_FILL_RAW_CASE_SHA256
    assert canonical_sha256(result) == NO_FILL_RESULT_SHA256
    assert stage5c_portfolio_ledger_projection_sha256(case, result) == NO_FILL_PROJECTION_SHA256
    assert result.projection_replay_hash.value == NO_FILL_PROJECTION_SHA256
    assert tuple(
        event.declared_canonical_hash.value for event in result.ledger_replay.accepted_events
    ) == (NO_FILL_OPENING_EVENT_SHA256,)
    assert result.ledger_replay.derived_state.journal_head_hash.value == (
        NO_FILL_JOURNAL_HEAD_SHA256
    )
    assert result.ledger_replay.derived_state.available_cash == "100000"
    assert result.ledger_replay.derived_state.lots == ()
    assert result.position_layers is not None
    assert (
        result.position_layers.approved_quantity,
        result.position_layers.submitted_quantity,
        result.position_layers.filled_quantity,
        result.position_layers.actual_quantity,
    ) == (0, 0, 0, 0)
    assert result.persists_state is False
    assert result.authorizes_positions is False
    assert result.authorizes_orders is False
