from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from invest_system.canonical import canonical_sha256
from invest_system.strategies.industrial_event.stage5d_governance import (
    STAGE5_5D_RULE_APPROVAL_ID,
    STAGE5_5D_RULE_APPROVAL_RECORD_SHA256,
    STAGE5_5D_RULE_BUNDLE_ID,
    STAGE5_5D_RULE_BUNDLE_SHA256,
    STAGE5_5D_RULE_BUNDLE_VERSION,
    STAGE5_5D_RULES_SHA256,
    STAGE5_5D_STAGE5C_BASELINE_COMMIT,
)
from invest_system.strategies.industrial_event.stage5d_ledger_v2 import (
    Stage5DV2EventType,
)
from unit import test_stage5d_source_driven_ledger_slice as source_slice_support

PREREGISTRATION_PATH = Path(
    "tests/fixtures/stage5d/first-order-contract-replay-preregistration.v0.1.0.json"
)
PREREGISTRATION_HASH_PATH = PREREGISTRATION_PATH.with_suffix(".canonical.sha256")
PREREGISTRATION_RAW_SHA256 = "66b8f5e4eef1454ca1459e77c82284a84bb105d0f55655d3d6512449c9453eb7"
PREREGISTRATION_CANONICAL_SHA256 = (
    "f7042c49f72b693d1c9ae5892b1d454be07cf6ad0851c499b47b2fead55492bc"
)
TOP_LEVEL_KEYS = (
    "schema_version",
    "preregistration_id",
    "status",
    "frozen_on",
    "baseline",
    "scope",
    "business_semantics_anchor",
    "case",
    "horizon",
    "inputs",
    "required_financial_event_inventory",
    "current_source_driven_slice_baseline",
    "expected_economic_outcome",
    "support_matrix",
    "completion_gate",
)


def _load(repository_root: Path) -> tuple[Path, dict[str, object]]:
    path = repository_root / PREREGISTRATION_PATH
    return path, json.loads(path.read_text(encoding="utf-8"))


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return value


def test_preregistration_has_exact_identity_and_zero_authority(repository_root: Path) -> None:
    path, document = _load(repository_root)

    assert tuple(document) == TOP_LEVEL_KEYS
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PREREGISTRATION_RAW_SHA256
    assert canonical_sha256(document) == PREREGISTRATION_CANONICAL_SHA256
    assert (
        repository_root.joinpath(PREREGISTRATION_HASH_PATH).read_text(encoding="utf-8").strip()
        == PREREGISTRATION_CANONICAL_SHA256
    )
    assert document["schema_version"] == "0.1.0"
    assert document["status"] == "frozen_for_implementation"

    scope = _mapping(document["scope"])
    assert scope["approval_scope"] == "stage5_synthetic_execution_validation"
    assert scope["run_mode"] == "research"
    assert scope["synthetic"] is True
    assert scope["validation_only"] is True
    for field_name in (
        "authority_eligible",
        "authorizes_backtest",
        "authorizes_paper",
        "authorizes_shadow",
        "authorizes_live",
        "authorizes_positions",
        "authorizes_orders",
        "connects_broker",
        "persists_state",
        "reads_kb_internal_state",
        "writes_kb",
    ):
        assert scope[field_name] is False


def test_preregistration_pins_approved_rules_and_business_anchor(repository_root: Path) -> None:
    _, document = _load(repository_root)
    baseline = _mapping(document["baseline"])

    assert baseline["stage5c_implementation_baseline_commit"] == (STAGE5_5D_STAGE5C_BASELINE_COMMIT)
    assert baseline["stage5d_rule_bundle_id"] == STAGE5_5D_RULE_BUNDLE_ID
    assert baseline["stage5d_rule_bundle_version"] == STAGE5_5D_RULE_BUNDLE_VERSION
    assert baseline["stage5d_rule_bundle_sha256"] == STAGE5_5D_RULE_BUNDLE_SHA256
    assert baseline["stage5d_rules_sha256"] == STAGE5_5D_RULES_SHA256
    assert baseline["stage5d_approval_id"] == STAGE5_5D_RULE_APPROVAL_ID
    assert baseline["stage5d_approval_record_sha256"] == (STAGE5_5D_RULE_APPROVAL_RECORD_SHA256)

    anchor = _mapping(document["business_semantics_anchor"])
    anchor_path = repository_root / str(anchor["fixture_path"])
    anchor_value = json.loads(anchor_path.read_text(encoding="utf-8"))
    assert hashlib.sha256(anchor_path.read_bytes()).hexdigest() == anchor["fixture_raw_sha256"]
    assert canonical_sha256(anchor_value) == anchor["fixture_canonical_sha256"]
    assert anchor["direct_runtime_input"] is False
    assert anchor["not_a_published_release"] is True
    assert anchor["not_strategy_evidence"] is True


def test_preregistered_case_matches_the_existing_source_driven_buy_slice(
    repository_root: Path,
) -> None:
    _, document = _load(repository_root)
    registered_case = _mapping(document["case"])
    inputs = _mapping(document["inputs"])
    registered_fill = _mapping(inputs["fill"])
    baseline = _mapping(document["current_source_driven_slice_baseline"])
    case, market_rules, portfolio_rules, result = source_slice_support._evaluate(repository_root)
    raw = case.market_execution_case
    constrained_projection = result.stage5c_result.constrained_market_projection

    assert constrained_projection is not None
    fill = constrained_projection.market_execution_result.fill
    assert fill is not None
    assert canonical_sha256(case) == registered_case["stage5c_case_sha256"]
    assert canonical_sha256(result.stage5c_result) == registered_case["stage5c_result_sha256"]
    assert canonical_sha256(raw.stage4_case) == registered_case["stage4_case_sha256"]
    assert canonical_sha256(raw.stage4_complete_result) == registered_case["stage4_result_sha256"]
    assert canonical_sha256(raw) == registered_case["stage5_market_execution_case_sha256"]
    assert (
        market_rules.bundle_hash.value
        == _mapping(document["baseline"])["stage5a_rule_bundle_sha256"]
    )
    assert portfolio_rules.bundle_hash == market_rules.bundle_hash
    assert canonical_sha256(fill) == registered_fill["fill_sha256"]
    assert fill.fill_id == registered_fill["fill_id"]
    assert fill.quantity == registered_fill["quantity"]
    assert fill.cash_effect == registered_fill["cash_effect"]

    assert result.v2_replay is not None
    assert canonical_sha256(result) == baseline["result_sha256"]
    assert result.slice_replay_hash.value == baseline["slice_replay_sha256"]
    assert result.v2_replay.replay_hash.value == baseline["v2_replay_sha256"]
    assert result.v2_replay.derived_state is not None
    assert result.v2_replay.derived_state.journal_head_hash.value == baseline["v2_head_sha256"]
    assert [item.declared_canonical_hash.value for item in result.v2_replay.projected_events] == (
        baseline["projected_event_sha256"]
    )


def test_horizon_inventory_and_economic_golden_are_closed_world(repository_root: Path) -> None:
    _, document = _load(repository_root)
    horizon = _mapping(document["horizon"])
    inventory = document["required_financial_event_inventory"]
    outcome = _mapping(document["expected_economic_outcome"])
    support = _mapping(document["support_matrix"])
    gate = _mapping(document["completion_gate"])

    assert isinstance(inventory, list)
    assert [item["ordinal"] for item in inventory] == list(range(5))
    assert [item["event_type"] for item in inventory] == [
        Stage5DV2EventType.OPENING_BALANCE.value,
        Stage5DV2EventType.BUY_TRADE.value,
        Stage5DV2EventType.BUY_CASH_SETTLEMENT.value,
        Stage5DV2EventType.SECURITY_SETTLEMENT.value,
        Stage5DV2EventType.SECURITY_SELLABLE.value,
    ]
    beginning = datetime.fromisoformat(str(horizon["beginning_at"]).replace("Z", "+00:00"))
    fill_at = datetime.fromisoformat(str(horizon["fill_at"]).replace("Z", "+00:00"))
    ending = datetime.fromisoformat(str(horizon["ending_at"]).replace("Z", "+00:00"))
    assert beginning.tzinfo is UTC
    assert beginning < fill_at < ending
    assert horizon["period_convention"] == "(beginning_at, ending_at]"
    assert horizon["opening_snapshot_effective_at_must_equal_beginning_at"] is True

    assert Decimal(str(outcome["ending_available_cash"])) + Decimal(
        str(outcome["ending_market_value"])
    ) == Decimal(str(outcome["ending_nav"]))
    assert Decimal(str(outcome["ending_nav"])) - Decimal(str(outcome["opening_nav"])) - Decimal(
        str(outcome["external_cash_flow"])
    ) == Decimal(str(outcome["total_pnl"]))
    assert Decimal(str(outcome["price_movement_contribution"])) + Decimal(
        str(outcome["fee_contribution"])
    ) + Decimal(str(outcome["tax_contribution"])) + Decimal(
        str(outcome["slippage_contribution"])
    ) == Decimal(str(outcome["total_pnl"]))

    assert support["supported_action_intents"] == ["ENTER"]
    assert support["supported_trade_sides"] == ["BUY"]
    assert support["supported_corporate_action_types"] == []
    assert support["unsupported_trade_sides"] == ["SELL"]
    assert support["no_selection_by_outcome"] is True
    assert gate["sqlite_or_durable_persistence_required"] is False
    assert gate["full_securities_accounting_coverage_required"] is False
