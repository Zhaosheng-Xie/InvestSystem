from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import rule_bundle_document_from_json_value
from invest_system.storage import STORAGE_SCHEMA_VERSION

SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/"
    "Stage5_5D公司行动估值P&L完整回放与原子持久化精确规则包_v0.1.md"
)
DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_"
    "v0.1.0-draft.rule-bundle.json"
)
APPROVED_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_"
    "v0.1.0.rule-bundle.json"
)
APPROVAL_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence_"
    "v0.1.0.approval.json"
)
STAGE5A_SPECIFICATION_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/Stage5_5A成交组合账本与确定性回放精确规则包_v0.1.md"
)
STAGE5A_DRAFT_BUNDLE_PATH = Path(
    "产业卡点及事件驱动系统/03_规则与规格/机器制品/"
    "industrial_event_stage5_5a_execution_portfolio_ledger_replay_"
    "v0.1.0-draft.rule-bundle.json"
)

STAGE5A_SPECIFICATION_SHA256 = "df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740"
STAGE5A_DRAFT_BUNDLE_SHA256 = "d0664b6b371ad042218f5d3c6caac9b9f1d1edd3ff475a5f7b36e401ca3d02db"
STAGE5A_DRAFT_RULES_SHA256 = "ecc61a4ee3eb3a7e4dea7238c027aca2ac3c2ce145eb40f0fa80bb34085463f5"
STAGE5D_SPECIFICATION_SHA256 = "db09ab438836167e0736aaa459d82fc24c6a22de6868ef7b0952e6546b410f46"
STAGE5D_DRAFT_RAW_SHA256 = "a17de440604be1bd3bd1d981af3bbf0dd458e0db97251830053b4aaf711f29d2"
STAGE5D_DRAFT_BUNDLE_SHA256 = "88189304fa4a68262c2ee72a0ca74f3d6235f995ffb4858bece32087ce579d22"
STAGE5D_DRAFT_RULES_SHA256 = "04b693c343fd85e07284bbf1b15eef09fa5b00b9a3dfc01ad82cf4597e3606ac"
STAGE5D_OWNER_APPROVAL_ITEMS_SHA256 = (
    "38bfe202d8583c531a4ce17a08d5ce3c2d02fe55db9bddf70850de4e0ab7e337"
)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resolve_json_pointer(root: dict[str, Any], pointer: str) -> Any:
    assert pointer.startswith("/")
    current: Any = root
    for raw_token in pointer[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        assert isinstance(current, dict)
        assert token in current
        current = current[token]
    return current


def _section_13_decision_lines(specification: str) -> dict[str, str]:
    owner_section = specification.split("## 13. Owner 逐项批准清单", 1)[1].split(
        "## 14. 批准后的唯一实施顺序", 1
    )[0]
    decision_lines: dict[str, str] = {}
    for line in owner_section.splitlines():
        match = re.fullmatch(r"- \[ \] `(5D-\d{2})`：.+", line)
        if match is not None:
            decision_lines[match.group(1)] = line
    return decision_lines


def test_stage5d_draft_strict_identity_and_document_binding(repository_root: Path) -> None:
    draft_path = repository_root / DRAFT_BUNDLE_PATH
    raw = _json(draft_path)
    document = rule_bundle_document_from_json_value(raw)

    assert sha256(draft_path.read_bytes()).hexdigest() == STAGE5D_DRAFT_RAW_SHA256
    assert document.to_json_value() == raw
    assert document.schema_version == "0.1.0-draft"
    assert document.strategy_id == "industrial_bottleneck_event"
    assert document.bundle_id == (
        "industrial_event_stage5_5d_corporate_action_pnl_replay_persistence"
    )
    assert document.bundle_version == "0.1.0-draft"
    assert document.declared_status.value == "draft"
    assert document.bundle_hash().value == STAGE5D_DRAFT_BUNDLE_SHA256
    assert canonical_sha256(document.rules) == STAGE5D_DRAFT_RULES_SHA256

    binding = raw["rules"]["document_binding"]
    specification = repository_root / SPECIFICATION_PATH
    specification_bytes = specification.read_bytes()
    assert not specification_bytes.startswith(b"\xef\xbb\xbf")
    assert sha256(specification_bytes).hexdigest() == STAGE5D_SPECIFICATION_SHA256
    assert binding["path"] == SPECIFICATION_PATH.as_posix()
    assert binding["hash"] == {
        "algorithm": "sha256",
        "value": STAGE5D_SPECIFICATION_SHA256,
    }
    assert binding["traceability_only"] is True
    assert raw["rules"]["runtime_must_not_parse_markdown"] is True


def test_stage5d_all_48_items_are_pending_with_zero_runtime_authority(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    batch = rules["batch"]
    items = rules["owner_approval_items"]

    assert batch["stage"] == "Stage 5"
    assert batch["batch_id"] == "5D"
    assert batch["purpose"] == "rule_governance_only"
    assert batch["owner_approval_required"] is True
    assert batch["approval_items_required"] == 48
    assert batch["approved_items"] == 0
    assert tuple(item["approval_item_id"] for item in items) == tuple(
        f"5D-{number:02d}" for number in range(1, 49)
    )
    assert len(items) == 48
    assert {item["status"] for item in items} == {"pending"}
    assert all(item["rule_paths"] for item in items)
    assert canonical_sha256(items) == STAGE5D_OWNER_APPROVAL_ITEMS_SHA256
    for item in items:
        for pointer in item["rule_paths"]:
            _resolve_json_pointer(rules, pointer)

    specification = (repository_root / SPECIFICATION_PATH).read_text(encoding="utf-8")
    decision_lines = _section_13_decision_lines(specification)
    assert tuple(decision_lines) == tuple(item["approval_item_id"] for item in items)
    for item in items:
        decision_line = decision_lines[item["approval_item_id"]]
        assert item["decision_text_sha256"] == sha256(decision_line.encode("utf-8")).hexdigest()
    assert re.search(r"^- \[[xX]\] `5D-", specification, flags=re.MULTILINE) is None

    assert rules["owner_approval_atomicity"] == {
        "authorization_predicate": "all(5D-01..5D-48==approved)",
        "all_48_required": True,
        "same_exact_bundle_document_and_approval_record_required": True,
        "pending_rejected_missing_or_identity_drift_result": ("draft_zero_runtime_authority"),
        "partial_capability_forbidden": True,
        "partial_implementation_authority_forbidden": True,
        "decision_text_sha256_contract": {
            "algorithm": "sha256",
            "source": "section_13_complete_checkbox_line",
            "byte_encoding": "utf-8_without_bom",
            "line_slice": "from_-_[ ]_through_end_of_line",
            "line_terminator_included": False,
        },
    }

    assert batch["approved_machine_bundle_exists"] is False
    assert batch["approval_record_exists"] is False
    assert batch["runtime_code_exists"] is False
    assert batch["evaluator_exists"] is False
    assert batch["persistence_exists"] is False
    boundary = rules["authorization_boundary"]
    assert boundary["proposed_approval_scope"] == "stage5_synthetic_execution_validation"
    assert boundary["allowed_run_modes"] == []
    assert boundary["specification_validation_only"] is True
    assert boundary["runtime_capability_issued"] is False
    assert all(value is False for key, value in boundary.items() if key.startswith("authorizes_"))
    assert {module["status"] for module in rules["rule_modules"].values()} == {"draft"}
    assert STORAGE_SCHEMA_VERSION == 3


def test_stage5d_draft_pins_exact_stage5a_and_stage5c_baselines(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    upstream = rules["exact_upstream_dependencies"]

    assert upstream["stage5a_rule_governance"] == {
        "batch_id": "5A",
        "bundle_id": "industrial_event_stage5_5a_execution_portfolio_ledger_replay",
        "bundle_version": "0.1.0",
        "bundle_hash": {
            "algorithm": "sha256",
            "value": "c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7",
        },
        "rules_hash": {
            "algorithm": "sha256",
            "value": "bb7ef84b1287be1111fe95571efa58cd268a65d862b7d235508fc31ccbaf0c69",
        },
        "approval_record_hash": {
            "algorithm": "sha256",
            "value": "5b9536f546337ba38408d255b3fbad68fbbdf6d9ccba9af79b10b6e04ca8cd78",
        },
        "approval_id": "rule_approval_stage5_5a_execution_portfolio_ledger_replay_v0_1_0",
        "specification_hash": {
            "algorithm": "sha256",
            "value": "df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740",
        },
        "approval_document_hash": {
            "algorithm": "sha256",
            "value": "4862d0c8add5d28db8f24432d4d3958c9de6f73bf74ae7d4754e0290916cbf02",
        },
        "existing_stage5a_artifact_bytes_must_remain_unchanged": True,
        "dependency_is_approved_rule_authority": True,
    }
    assert upstream["stage5c_implementation_baseline"] == {
        "commit_algorithm": "git-sha1",
        "commit": "7f64c584c5c7be5e2385a177fab9e5d31e3f665b",
        "commit_is_implementation_baseline_not_runtime_capability": True,
        "standalone_stage5b_v0_1_contract_must_remain_unchanged": True,
        "ledger_v2_changes_require_stage5c_schema_version_increment": True,
        "ledger_v2_may_change_stage5c_canonical_event_and_replay_bytes": True,
        "stage5a_through_stage5c_regression_must_be_rerun": True,
        "future_approved_bundle_must_bind_baseline_and_actual_stage5d_code_commit": True,
        "stage5d_must_not_backfill_or_overwrite_historical_stage5c_artifacts": True,
    }
    assert upstream["dependency_identity_drift"] == "PRECHECK_BLOCKED"

    assert (
        sha256((repository_root / STAGE5A_SPECIFICATION_PATH).read_bytes()).hexdigest()
        == STAGE5A_SPECIFICATION_SHA256
    )
    stage5a_draft = rule_bundle_document_from_json_value(
        _json(repository_root / STAGE5A_DRAFT_BUNDLE_PATH)
    )
    assert stage5a_draft.bundle_hash().value == STAGE5A_DRAFT_BUNDLE_SHA256
    assert canonical_sha256(stage5a_draft.rules) == STAGE5A_DRAFT_RULES_SHA256


def test_stage5d_exact_event_semantic_map_fixes_accounts_formulas_and_times(
    repository_root: Path,
) -> None:
    modules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["rule_modules"]
    ledger = modules["ledger_v2"]
    event_map = ledger["exact_event_semantic_map"]

    assert ledger["posting_signed_delta_formula"] == "debit-credit"
    assert ledger["posting_exactly_one_positive_side_required"] is True
    assert ledger["zero_posting"] == "forbidden"
    assert ledger["account_scope_allowlist"] == {
        "CNY_null": [
            "CASH_AVAILABLE",
            "CASH_RESERVED",
            "CASH_SETTLED_UNAVAILABLE",
            "EXTERNAL_CAPITAL",
            "OPENING_CONTROL",
        ],
        "CNY_security": [
            "CASH_RECEIVABLE",
            "CASH_PAYABLE",
            "SECURITY_COST",
            "TRADE_CLEARING",
            "REALIZED_PNL_CONTROL",
            "FEE_EXPENSE_CONTROL",
            "TAX_EXPENSE_CONTROL",
            "CORPORATE_ACTION_RECEIVABLE",
            "CORPORATE_ACTION_PAYABLE",
            "CORPORATE_ACTION_CLEARING",
            "CORPORATE_ACTION_INCOME_CONTROL",
            "DIVIDEND_INCOME_CONTROL",
            "OTHER_RECEIVABLE",
            "OTHER_PAYABLE",
            "OPENING_CONTROL",
        ],
        "SHARE_security": [
            "SECURITY_UNSETTLED",
            "SECURITY_UNSELLABLE",
            "SECURITY_SELLABLE",
            "SECURITY_CONTROL",
            "OPENING_CONTROL",
        ],
    }

    assert event_map["event_semantic_map_id"] == "stage5d_ledger_v2_exact_event_map"
    assert event_map["version"] == "1.0.0"
    assert event_map["closed_world_allowlist"] is True
    assert event_map["canonical_hash_enters_every_event_and_complete_replay"] is True
    assert event_map["base_variables"] == {
        "quantity": "q>0",
        "buy_benchmark_principal": "B=q*buy_benchmark_price",
        "buy_slippage": "S_buy=q*(buy_execution_price-buy_benchmark_price)",
        "buy_gross": "G_buy=B+S_buy=q*buy_execution_price>0",
        "buy_fee": "F_buy>=0",
        "buy_tax": "T_buy>=0",
        "buy_full_cost": "K_buy=G_buy+F_buy+T_buy",
        "sell_gross": "G_sell=q*sell_execution_price>0",
        "disposed_fifo_cost": "C_disposed=sum(exact_FIFO_disposed_lot_components)>=0",
        "sell_fee": "F_sell>=0",
        "sell_tax": "T_sell>=0",
        "sell_net_receivable": "P_sell=G_sell-F_sell-T_sell>=0",
        "gain_control_close_nonnegative": ("D(clearing,x)+C(REALIZED_PNL_CONTROL,x)"),
        "gain_control_close_negative": ("D(REALIZED_PNL_CONTROL,-x)+C(clearing,-x)"),
    }

    stage5c_entries = {
        entry["semantic_id"]: entry for entry in event_map["stage5c_event_semantics"]
    }
    stage5d_entries = {
        entry["semantic_id"]: entry for entry in event_map["stage5d_event_semantics"]
    }
    assert len(stage5c_entries) == event_map["stage5c_semantic_count"] == 18
    assert len(stage5d_entries) == event_map["stage5d_semantic_count"] == 18
    assert all(
        set(entry)
        == {
            "semantic_id",
            "event_type",
            "phase",
            "postings_formula",
            "lot_effect_formula",
            "recognized_time",
        }
        for entry in (*stage5c_entries.values(), *stage5d_entries.values())
    )

    assert stage5c_entries["TRADE_FILL_BUY"] == {
        "semantic_id": "TRADE_FILL_BUY",
        "event_type": "TRADE_FILL",
        "phase": "BUY",
        "postings_formula": (
            "D(SECURITY_COST,G_buy,s)+C(CASH_PAYABLE,G_buy,s)+"
            "D(SECURITY_UNSETTLED,q,s)+C(SECURITY_CONTROL,q,s)"
        ),
        "lot_effect_formula": (
            "create_fill_lot(+q,sellable+0,B,S_buy,fee=0,tax=0,basis=0,full=G_buy)"
        ),
        "recognized_time": "filled_at",
    }
    assert stage5c_entries["TRADE_FILL_SELL"] == {
        "semantic_id": "TRADE_FILL_SELL",
        "event_type": "TRADE_FILL",
        "phase": "SELL",
        "postings_formula": (
            "D(CASH_RECEIVABLE,G_sell,s)+C(TRADE_CLEARING,G_sell,s);"
            "D(TRADE_CLEARING,C_disposed,s)+C(SECURITY_COST,C_disposed,s);"
            "D(SECURITY_CONTROL,q,s)+C(SECURITY_SELLABLE,q,s);"
            "gain(G_sell-C_disposed)_zeros_TRADE_CLEARING"
        ),
        "lot_effect_formula": (
            "exact_FIFO_-q_-sellable_and_remove_all_five_components_and_full_cost"
        ),
        "recognized_time": "filled_at",
    }
    assert stage5d_entries["CASH_DIVIDEND_RECOGNIZE"] == {
        "semantic_id": "CASH_DIVIDEND_RECOGNIZE",
        "event_type": "CASH_DIVIDEND",
        "phase": "RECOGNIZE",
        "postings_formula": (
            "D(CORPORATE_ACTION_RECEIVABLE,G_action,s)+"
            "C(DIVIDEND_INCOME_CONTROL,G_action,s);if_typed_F_T_same_time:"
            "D(FEE_EXPENSE_CONTROL,F,s)+D(TAX_EXPENSE_CONTROL,T,s)+"
            "C(CORPORATE_ACTION_RECEIVABLE,F+T,s)"
        ),
        "lot_effect_formula": ("none;P=G_action-F-T;gross_fee_tax_are_three_unique_pnl_cells"),
        "recognized_time": "recognized_at",
    }
    assert stage5d_entries["RIGHTS_OR_ALLOTMENT_EXERCISE_RECOGNIZE"] == {
        "semantic_id": "RIGHTS_OR_ALLOTMENT_EXERCISE_RECOGNIZE",
        "event_type": "RIGHTS_OR_ALLOTMENT",
        "phase": "EXERCISE_RECOGNIZE",
        "postings_formula": (
            "CASH_AVAILABLE_to_CASH_RESERVED(K_rights);"
            "D(SECURITY_COST,K_rights,s)+C(CORPORATE_ACTION_PAYABLE,K_rights,s);"
            "D(SECURITY_UNSETTLED,Q_action,s)+C(SECURITY_CONTROL,Q_action,s)"
        ),
        "lot_effect_formula": (
            "create_unsettled_action_lot(+Q_action,sellable+0,"
            "benchmark_principal_fee_tax,slippage=0,basis=0,full=K_rights);"
            "nonzero_basis_requires_separate_approved_rule"
        ),
        "recognized_time": "recognized_at",
    }
    assert event_map["corporate_action_cash_phases"] == {
        "paid_before_available": (
            "D(CASH_SETTLED_UNAVAILABLE,P,null)+C(CORPORATE_ACTION_RECEIVABLE,P,s)"
        ),
        "available_after_paid": "CASH_SETTLED_UNAVAILABLE_to_CASH_AVAILABLE(P)",
        "paid_equals_available_compound": (
            "D(CASH_AVAILABLE,P,null)+C(CORPORATE_ACTION_RECEIVABLE,P,s)"
        ),
        "same_time_adjacent_phases_must_algebraically_merge": True,
        "same_priority_event_id_or_hash_order_dependency": "forbidden",
    }

    recognized_times = {
        semantic_id: entries[semantic_id]["recognized_time"]
        for entries, semantic_ids in (
            (
                stage5c_entries,
                (
                    "TRADE_SETTLEMENT_BUY_CASH",
                    "TRADE_SETTLEMENT_BUY_SECURITY",
                    "SECURITY_AVAILABILITY_BUY",
                    "TRADE_SETTLEMENT_SELL_CASH",
                    "CASH_RELEASE_SELL_CASH_AVAILABLE",
                ),
            ),
            (
                stage5d_entries,
                (
                    "CASH_DIVIDEND_RECOGNIZE",
                    "CASH_DIVIDEND_PAID_OR_AVAILABLE",
                    "SHARE_DISTRIBUTION_DELIVERED",
                    "SHARE_DISTRIBUTION_SELLABLE",
                    "RIGHTS_OR_ALLOTMENT_PAID",
                    "RIGHTS_OR_ALLOTMENT_DELIVERED",
                    "RIGHTS_OR_ALLOTMENT_SELLABLE",
                    "DELISTING_OR_CASH_OUT_PAID_OR_AVAILABLE",
                ),
            ),
        )
        for semantic_id in semantic_ids
    }
    assert recognized_times == {
        "TRADE_SETTLEMENT_BUY_CASH": "buy_cash_paid_recognized_at",
        "TRADE_SETTLEMENT_BUY_SECURITY": "security_delivered_recognized_at",
        "SECURITY_AVAILABILITY_BUY": "security_sellable_recognized_at",
        "TRADE_SETTLEMENT_SELL_CASH": "sell_cash_paid_recognized_at",
        "CASH_RELEASE_SELL_CASH_AVAILABLE": "sell_cash_available_recognized_at",
        "CASH_DIVIDEND_RECOGNIZE": "recognized_at",
        "CASH_DIVIDEND_PAID_OR_AVAILABLE": ("paid_recognized_at_or_cash_available_recognized_at"),
        "SHARE_DISTRIBUTION_DELIVERED": "security_delivered_recognized_at",
        "SHARE_DISTRIBUTION_SELLABLE": "security_sellable_recognized_at",
        "RIGHTS_OR_ALLOTMENT_PAID": "paid_recognized_at",
        "RIGHTS_OR_ALLOTMENT_DELIVERED": "security_delivered_recognized_at",
        "RIGHTS_OR_ALLOTMENT_SELLABLE": "security_sellable_recognized_at",
        "DELISTING_OR_CASH_OUT_PAID_OR_AVAILABLE": (
            "paid_recognized_at_or_cash_available_recognized_at"
        ),
    }


def test_stage5d_state_times_and_period_boundaries_are_fail_closed(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    input_contract = rules["stage5d_input_contract"]
    temporal = input_contract["state_specific_temporal_semantics"]

    assert temporal == {
        "terms_fields": ["announced_at", "terms_available_at"],
        "entitlement_fields": [
            "entitlement_cutoff_at",
            "entitlement_rule_available_at",
        ],
        "economic_action_fields": [
            "economic_effective_at",
            "economic_state_available_at",
        ],
        "cash_fields": [
            "payable_at",
            "paid_at",
            "paid_state_available_at",
            "cash_available_at",
            "cash_available_state_available_at",
        ],
        "security_fields": [
            "security_delivered_at",
            "delivered_state_available_at",
            "security_sellable_at",
            "sellable_state_available_at",
        ],
        "recognized_time_formulas": {
            "entitlement_determined_at": (
                "max(entitlement_cutoff_at,terms_available_at,entitlement_rule_available_at)"
            ),
            "recognized_at": (
                "max(economic_effective_at,economic_state_available_at,entitlement_determined_at)"
            ),
            "paid_recognized_at": ("max(paid_at,paid_state_available_at,recognized_at)"),
            "cash_available_recognized_at": (
                "max(cash_available_at,cash_available_state_available_at,paid_recognized_at)"
            ),
            "security_delivered_recognized_at": (
                "max(security_delivered_at,delivered_state_available_at,recognized_at)"
            ),
            "security_sellable_recognized_at": (
                "max(security_sellable_at,sellable_state_available_at,"
                "security_delivered_recognized_at)"
            ),
        },
        "not_applicable_must_be_explicit": True,
        "event_effective_at_uses_its_own_recognized_time": True,
        "action_wide_available_at_reuse": "forbidden",
        "paid_fact_unknown_remains_receivable": True,
        "paid_but_cash_unavailable_uses_cash_settled_unavailable": True,
        "recognized_but_undelivered_security_uses_security_unsettled": True,
        "delivered_but_unsellable_security_uses_security_unsellable": True,
    }
    assert input_contract["stage5c_settlement_temporal_semantics"] == {
        "each_moment_fields": [
            "moment_effective_at",
            "market_rule_available_at",
            "state_available_at",
        ],
        "recognized_moments": [
            "buy_cash_paid_recognized_at",
            "security_delivered_recognized_at",
            "security_sellable_recognized_at",
            "sell_cash_paid_recognized_at",
            "sell_cash_available_recognized_at",
        ],
        "formula_for_each": (
            "max(moment_effective_at,market_rule_available_at,state_available_at)"
        ),
        "reuse_another_state_available_time": "forbidden",
        "nonempty_special_exception_fails_before_time_derivation": True,
    }

    corporate_actions = rules["rule_modules"]["corporate_actions"]
    assert corporate_actions["required_temporal_fields"] == {
        "terms": ["announced_at", "terms_available_at"],
        "entitlement": [
            "entitlement_cutoff_at",
            "entitlement_rule_available_at",
            "entitlement_determined_at",
        ],
        "economic_recognition": [
            "economic_effective_at",
            "economic_state_available_at",
            "recognized_at",
        ],
        "cash": [
            "payable_at",
            "paid_at",
            "paid_state_available_at",
            "paid_recognized_at",
            "cash_available_at",
            "cash_available_state_available_at",
            "cash_available_recognized_at",
        ],
        "security": [
            "security_delivered_at",
            "delivered_state_available_at",
            "security_delivered_recognized_at",
            "security_sellable_at",
            "sellable_state_available_at",
            "security_sellable_recognized_at",
        ],
    }
    assert corporate_actions["not_applicable_state_fields_must_be_typed"] is True
    assert (
        corporate_actions["action_wide_available_at_or_single_recognized_at_for_all_phases"]
        == "forbidden"
    )

    assert input_contract["valuation_period"] == {
        "beginning_at_and_ending_at_required": True,
        "ordering": "beginning_at_lt_ending_at_lte_injected_clock",
        "beginning_prefix": "effective_at_lte_beginning_at",
        "ending_prefix": "effective_at_lte_ending_at",
        "period_interval": "beginning_at_lt_effective_at_lte_ending_at",
        "beginning_inclusive_ending_inclusive_prefixes_required": True,
        "beginning_inclusive_ending_exclusive_implementation": "forbidden",
    }
    pnl = rules["rule_modules"]["two_dimensional_pnl"]
    assert pnl["period_boundary"] == "(beginning_at,ending_at]"
    assert pnl["prefix_boundary_semantics"] == {
        "beginning_prefix": "all_events_with_effective_at_lte_beginning_at",
        "ending_prefix": "all_events_with_effective_at_lte_ending_at",
        "event_exactly_at_beginning_at_period_contribution": "zero",
        "event_exactly_at_ending_at": "included",
        "beginning_inclusive_ending_exclusive": "forbidden",
    }
    assert pnl["period_matrix_formula"] == (
        "cumulative_matrix_at_ending_inclusive-cumulative_matrix_at_beginning_inclusive"
    )
    assert pnl["period_equity_formula"] == (
        "ending_equity-beginning_equity-net_external_cash_inflow"
    )

    complete_replay = rules["rule_modules"]["complete_replay"]
    assert complete_replay["ending_at_is_inclusive"] is True
    assert complete_replay["complete_horizon_formula"] == (
        "all_events_whose_own_state_recognized_at_lte_ending_at_where_ending_at_lte_injected_clock"
    )
    assert (
        complete_replay[
            "future_payment_cash_availability_security_delivery_or_"
            "sellability_may_enter_accepted_state"
        ]
        is False
    )

    goldens = set(rules["rule_modules"]["validation_matrix"]["golden_cases_required"])
    assert {
        "state_specific_knowledge_payment_cash_delivery_and_sellable_time_shift_non_leakage",
        "period_event_exactly_at_beginning_has_zero_contribution",
        "period_event_inside_or_exactly_at_ending_is_included",
        "beginning_inclusive_ending_exclusive_boundary_implementation_fails",
    } <= goldens


def test_stage5d_election_contract_is_pit_complete_and_fail_closed(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    election = rules["stage5d_input_contract"]["corporate_action_election_set"]

    assert election["typed"] is True
    assert election["election_requirement_required_for_every_covered_action"] is True
    assert election["election_requirement_allowlist"] == [
        "NOT_APPLICABLE",
        "MANDATORY",
        "CHOICE_REQUIRED",
    ]
    assert election["not_applicable_or_mandatory_choice_fields_and_times"] == (
        "typed_NOT_APPLICABLE_only"
    )
    assert election["caller_choice_for_not_applicable_or_mandatory"] == "forbidden"
    assert election["choice_required_fields"] == [
        "election_id",
        "action_id",
        "strategy_id",
        "account_fixture_id",
        "security_id",
        "choice_code",
        "election_made_at",
        "election_available_at",
        "election_deadline_at",
        "deadline_rule_id",
        "deadline_rule_version",
        "deadline_rule_hash",
        "source_id",
        "source_bytes_hash",
        "revision_id",
        "supersedes",
        "canonical_hash",
    ]
    assert election["choice_code_must_come_from_exact_action_terms"] is True
    assert election["recognized_time_formulas"] == {
        "choice_made_ordering": (
            "terms_available_at_lte_election_made_at_lte_election_deadline_at"
        ),
        "election_recognized_at": (
            "max(election_made_at,election_available_at,terms_available_at)"
        ),
        "choice_dependent_phase_recognized_at": (
            "max(base_action_phase_recognized_at,election_recognized_at)"
        ),
        "default_recognized_at": (
            "max(election_deadline_at,default_available_at,terms_available_at)"
        ),
        "default_choice_dependent_phase_recognized_at": (
            "max(base_action_phase_recognized_at,default_recognized_at)"
        ),
        "revised_election_recognized_at": (
            "max(revision_made_at,revision_available_at,terms_available_at)"
        ),
    }
    assert election["pit_horizon_contract"] == {
        "choice_made_before_deadline_but_available_after_horizon": (
            "PENDING_ELECTION_future_plan_only"
        ),
        "choice_dependent_phase_required_in_horizon_without_valid_choice": (
            "PRECHECK_BLOCKED_before_first_accepted_event"
        ),
        "choice_or_revision_may_not_be_backfilled_to_earlier_phase": True,
    }
    assert election["default_contract"] == {
        "may_apply_only_after_deadline": True,
        "required_fields": [
            "default_choice_code",
            "default_rule_id",
            "default_rule_version",
            "default_rule_hash",
            "default_available_at",
        ],
        "must_be_explicit_in_exact_action_terms_versioned_and_content_addressed": True,
        "recognized_time_formula_ref": (
            "/stage5d_input_contract/corporate_action_election_set/"
            "recognized_time_formulas/default_recognized_at"
        ),
        "missing_explicit_default": "UNKNOWN_BLOCKED",
        "missing_choice_may_be_inferred_as_decline": False,
    }
    assert election["active_election_per_journal_prefix"] == "at_most_one"
    assert election["idempotency"] == {
        "same_identity_same_canonical_bytes": "idempotent",
        "same_identity_different_canonical_bytes": "PRECHECK_BLOCKED_conflict",
    }
    assert election["revision_contract"] == {
        "action_terms_must_explicitly_allow_revision": True,
        "required_fields_when_present": [
            "revision_id",
            "supersedes",
            "revision_made_at",
            "revision_available_at",
        ],
        "revision_made_at_must_be_lte_election_deadline_at": True,
        "recognized_time_formula_ref": (
            "/stage5d_input_contract/corporate_action_election_set/"
            "recognized_time_formulas/revised_election_recognized_at"
        ),
        "effective_correction": (
            "append_only_REVERSAL_then_REPLACEMENT_after_revision_recognized_at"
        ),
        "overwrite_or_backwrite": "forbidden",
    }

    corporate_actions = rules["rule_modules"]["corporate_actions"]
    assert corporate_actions["election_contract_ref"] == (
        "/stage5d_input_contract/corporate_action_election_set"
    )
    assert corporate_actions["rights_allotment"]["election_requirement_by_choice"] == {
        "DECLINE": "CHOICE_REQUIRED",
        "EXERCISE": "CHOICE_REQUIRED",
        "MANDATORY": "MANDATORY",
    }
    assert (
        corporate_actions["rights_allotment"][
            "decline_or_exercise_requires_choice_made_lte_deadline_and_pit_available"
        ]
        is True
    )
    assert (
        corporate_actions["delisting_or_cash_out"]["mandatory_exit_election_requirement"]
        == "MANDATORY"
    )
    assert corporate_actions["delisting_or_cash_out"]["voluntary_choice_allowlist"] == [
        "ACCEPT_CASH",
        "DECLINE",
    ]
    assert (
        corporate_actions["delisting_or_cash_out"]["voluntary_exit_election_requirement"]
        == "CHOICE_REQUIRED"
    )
    assert (
        corporate_actions[
            "action_event_and_lot_effect_bind_action_election_deadline_default_"
            "source_rule_and_revision_hashes"
        ]
        is True
    )

    complete_replay = rules["rule_modules"]["complete_replay"]
    assert (
        complete_replay["election_choice_default_and_revision_each_use_their_own_recognized_time"]
        is True
    )
    assert complete_replay["future_election_default_or_revision_may_enter_accepted_state"] is False
    assert (
        "corporate_action_coverage_election_deadline_default_revision_and_generated_events"
        in complete_replay["replay_hash_includes"]
    )


def test_stage5d_mark_nav_and_persistence_outcomes_are_closed_world(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    input_contract = rules["stage5d_input_contract"]
    mark_input = input_contract["unadjusted_mark_observation_set"]
    opening_state = input_contract["account_wide_multi_security_opening_state"]
    modules = rules["rule_modules"]
    marks = modules["marks_and_nav"]

    assert mark_input["coverage_scope_at_each_valuation_point"] == (
        "securities_with_actual_quantity_gt_zero_in_that_inclusive_journal_prefix"
    )
    assert mark_input["actual_quantity_eq_zero_market_value"] == (
        "exact_decimal_zero_without_mark_requirement"
    )
    assert mark_input["fully_disposed_security_requires_ending_mark"] is False
    assert (
        mark_input["missing_or_unverifiable_scope_coverage_completeness_or_source_hash"]
        == "PRECHECK_BLOCKED"
    )
    assert mark_input["complete_coverage_may_prove_no_eligible_legal_observation"] is True
    assert "unknown_coverage_mark_flow_opening_cost_or_replay_basis" not in input_contract
    assert (
        "every_nonzero_security_requires_opening_attribution_actions_and_beginning_ending_marks"
        not in opening_state
    )
    assert (
        opening_state[
            "each_valuation_point_requires_mark_coverage_only_for_prefix_actual_quantity_gt_zero"
        ]
        is True
    )
    assert opening_state["fully_disposed_security_requires_ending_mark"] is False

    assert marks["mark_scope_contract"] == {
        "scope_is_evaluated_separately_at_each_valuation_point": True,
        "mark_required_when": ("actual_quantity_gt_zero_in_that_inclusive_journal_prefix"),
        "actual_quantity_eq_zero_market_value": "exact_decimal_zero",
        "actual_quantity_eq_zero_mark_requirement": "none",
        "fully_disposed_before_ending_requires_ending_mark": False,
        "one_missing_required_security_mark_makes_whole_account_incomplete": True,
        "partial_account_nav_or_pnl": "forbidden",
    }
    assert marks["outcome_precedence"] == [
        {
            "priority": 1,
            "condition": (
                "scope_coverage_completeness_source_hash_identity_pit_or_same_time_"
                "uniqueness_missing_unverifiable_malformed_or_conflicting"
            ),
            "result": "PRECHECK_BLOCKED",
        },
        {
            "priority": 2,
            "condition": (
                "ledger_posting_lot_cost_cash_equity_cell_matrix_or_other_reconciliation_failure"
            ),
            "result": "RECONCILIATION_BLOCKED",
        },
        {
            "priority": 3,
            "condition": (
                "coverage_complete_ledger_reconciled_required_position_has_no_"
                "legal_historical_observation"
            ),
            "result": "ABSTAIN_incomplete_account_nav_and_pnl",
        },
    ]
    assert marks["reconciliation_failure_may_be_downgraded_to_mark_missing_abstain"] is False
    assert (
        marks["missing_historical_legal_mark_after_complete_coverage_and_reconciled_ledger"]
        == "ABSTAIN_incomplete_account_nav_and_pnl"
    )

    nav_map = marks["closed_world_account_to_nav_mapping"]
    assert nav_map["closed_world"] is True
    classified = (
        nav_map["direct_add_once"]
        + nav_map["direct_subtract_once"]
        + nav_map["replaced_by_position_market_value"]
        + nav_map["excluded_from_direct_nav"]
    )
    assert len(classified) == len(set(classified)) == 25
    ledger_accounts = modules["ledger_v2"]["account_scope_allowlist"]
    all_ledger_account_scope_pairs = (
        {f"CNY/null:{account}" for account in ledger_accounts["CNY_null"]}
        | {f"CNY/security:{account}" for account in ledger_accounts["CNY_security"]}
        | {f"SHARE/security:{account}" for account in ledger_accounts["SHARE_security"]}
    )
    assert set(classified) == all_ledger_account_scope_pairs
    assert nav_map["direct_add_once"] == [
        "CNY/null:CASH_AVAILABLE",
        "CNY/null:CASH_RESERVED",
        "CNY/null:CASH_SETTLED_UNAVAILABLE",
        "CNY/security:CASH_RECEIVABLE",
        "CNY/security:CORPORATE_ACTION_RECEIVABLE",
        "CNY/security:OTHER_RECEIVABLE",
    ]
    assert nav_map["direct_subtract_once"] == [
        "CNY/security:CASH_PAYABLE",
        "CNY/security:CORPORATE_ACTION_PAYABLE",
        "CNY/security:OTHER_PAYABLE",
    ]
    assert nav_map["replaced_by_position_market_value"] == ["CNY/security:SECURITY_COST"]
    assert nav_map["each_included_balance_enters_exactly_once"] is True
    assert nav_map["every_ledger_account_scope_pair_must_be_classified_exactly_once"] is True
    assert nav_map["security_cost_is_not_added_because_market_value_replaces_cost"] is True
    assert marks["equity_formula"] == (
        "settled_cash+trade_cash_receivable-trade_cash_payable+"
        "corporate_action_receivable-corporate_action_payable+position_market_value+"
        "other_receivable-other_payable"
    )

    pnl_outcome = modules["two_dimensional_pnl"]["incomplete_mark_or_unreconciled_cell"]
    assert pnl_outcome == {
        "complete_mark_coverage_missing_legal_observation_after_reconciled_ledger": (
            "ABSTAIN_incomplete_pnl"
        ),
        "unreconciled_contribution_cell_formula_matrix_cost_cash_or_equity": (
            "RECONCILIATION_BLOCKED"
        ),
        "reconciliation_failure_may_be_downgraded_to_abstain": False,
        "partial_security_or_account_nav_or_pnl": "forbidden",
    }

    sqlite = modules["sqlite_v4_durable_persistence"]
    assert sqlite["persistence_outcome_precedence"] == [
        {
            "priority": 1,
            "condition": ("mark_missing_ABSTAIN_with_incomplete_pnl_or_any_other_incomplete_pnl"),
            "result": "must_not_call_5d_2_zero_visible_write",
        },
        {
            "priority": 2,
            "condition": (
                "technical_codec_schema_hash_identity_concurrency_reconciliation_"
                "sqlite_interrupt_or_read_back_failure"
            ),
            "result": "zero_visible_write",
        },
        {
            "priority": 3,
            "condition": (
                "pnl_complete_and_all_reconciliation_passed_and_zero_financial_"
                "mutation_and_business_BLOCKED_or_ABSTAIN"
            ),
            "result": ("may_persist_sealed_immutable_evaluation_without_advancing_financial_state"),
        },
    ]
    assert sqlite["mark_missing_abstain_incomplete_pnl_may_call_5d_2"] is False
    assert (
        sqlite["complete_pnl_reconciled_zero_financial_mutation_business_blocked_or_abstain"]
        == "may_persist_as_sealed_immutable_evaluation_without_advancing_financial_state"
    )

    goldens = set(modules["validation_matrix"]["golden_cases_required"])
    assert {
        "mark_scope_or_coverage_missing_is_precheck_blocked",
        "complete_mark_coverage_without_legal_observation_is_account_abstain_incomplete_pnl",
        "unreconciled_ledger_or_pnl_is_reconciliation_blocked_not_mark_abstain",
        "mark_scope_uses_actual_quantity_at_each_valuation_point_and_fully_disposed_security_needs_no_ending_mark",
        "closed_world_account_to_nav_includes_each_balance_once_replaces_security_cost_with_market_value_and_excludes_controls",
        "complete_pnl_business_abstain_may_seal_but_mark_missing_incomplete_pnl_never_calls_5d_2",
    } <= goldens


def test_stage5d_two_dimensional_pnl_uses_atomic_cells_without_double_sum(
    repository_root: Path,
) -> None:
    modules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]["rule_modules"]
    pnl = modules["two_dimensional_pnl"]

    assert pnl["pnl_formula_map_id"] == "stage5d_pnl_3x6_signed_formula_map"
    assert pnl["version"] == "1.0.0"
    assert pnl["canonical_hash_enters_every_pnl_envelope_and_complete_replay"] is True
    assert pnl["sign_convention"] == (
        "positive_increases_equity_or_pnl_negative_decreases_equity_or_pnl"
    )
    assert pnl["atomic_fact_object"] == "Stage5PnlCell"
    assert pnl["row_axis_name"] == "realization"
    assert pnl["row_axis_values"] == ["realized", "unrealized", "non_position_income"]
    assert pnl["column_axis_name"] == "driver"
    assert pnl["column_axis_values"] == [
        "price",
        "slippage",
        "fee",
        "tax",
        "cash_dividend",
        "corporate_action_cash",
    ]
    assert pnl["only_atomic_cells_are_summable_facts"] is True
    assert pnl["each_economic_amount_maps_to_exactly_one_atomic_cell"] is True
    assert pnl["atomic_cell_identity_dimensions"] == [
        "strategy_id",
        "account_fixture_id",
        "security_id",
        "as_of",
        "realization",
        "driver",
    ]
    assert pnl["contribution_object"] == "Stage5PnlContribution"
    assert pnl["contribution_identity_dimensions"] == [
        "strategy_id",
        "account_fixture_id",
        "security_id",
        "as_of",
        "realization",
        "driver",
        "formula_term",
        "source_event_id",
        "source_lot_id",
        "source_action_id",
    ]
    assert pnl["formula_term_allowlist"] == [
        "TB",
        "TS",
        "DB",
        "DS",
        "DF",
        "DT",
        "DA",
        "SF",
        "ST",
        "CAD",
        "MV",
        "RB",
        "RS",
        "RF",
        "RT",
        "RA",
        "NF",
        "NT",
        "DIV",
        "CAI",
    ]
    assert pnl["contribution_signed_amounts_sum_exactly_to_atomic_cell"] is True
    assert pnl["source_event_id_in_atomic_cell_identity_or_direct_period_cell_subtraction"] == (
        "forbidden"
    )

    assert pnl["closed_world_signed_formula_cells"] == [
        {
            "realization": "realized",
            "driver": "price",
            "allowed": True,
            "formula": "TB(t)-DB(t)-DA(t)",
        },
        {
            "realization": "realized",
            "driver": "slippage",
            "allowed": True,
            "formula": "TS(t)-DS(t)",
        },
        {
            "realization": "realized",
            "driver": "fee",
            "allowed": True,
            "formula": "-SF(t)-DF(t)",
        },
        {
            "realization": "realized",
            "driver": "tax",
            "allowed": True,
            "formula": "-ST(t)-DT(t)",
        },
        {
            "realization": "realized",
            "driver": "cash_dividend",
            "allowed": False,
            "formula": "0",
            "classification": "FORBIDDEN",
        },
        {
            "realization": "realized",
            "driver": "corporate_action_cash",
            "allowed": True,
            "formula": "CAD(t)",
            "gross_only": True,
        },
        {
            "realization": "unrealized",
            "driver": "price",
            "allowed": True,
            "formula": "MV(t)-RB(t)-RA(t)",
        },
        {
            "realization": "unrealized",
            "driver": "slippage",
            "allowed": True,
            "formula": "-RS(t)",
        },
        {
            "realization": "unrealized",
            "driver": "fee",
            "allowed": True,
            "formula": "-RF(t)",
        },
        {
            "realization": "unrealized",
            "driver": "tax",
            "allowed": True,
            "formula": "-RT(t)",
        },
        {
            "realization": "unrealized",
            "driver": "cash_dividend",
            "allowed": False,
            "formula": "0",
            "classification": "FORBIDDEN",
        },
        {
            "realization": "unrealized",
            "driver": "corporate_action_cash",
            "allowed": False,
            "formula": "0",
            "classification": "FORBIDDEN",
        },
        {
            "realization": "non_position_income",
            "driver": "price",
            "allowed": False,
            "formula": "0",
            "classification": "FORBIDDEN",
        },
        {
            "realization": "non_position_income",
            "driver": "slippage",
            "allowed": False,
            "formula": "0",
            "classification": "FORBIDDEN",
        },
        {
            "realization": "non_position_income",
            "driver": "fee",
            "allowed": True,
            "formula": "-NF(t)",
        },
        {
            "realization": "non_position_income",
            "driver": "tax",
            "allowed": True,
            "formula": "-NT(t)",
        },
        {
            "realization": "non_position_income",
            "driver": "cash_dividend",
            "allowed": True,
            "formula": "DIV(t)",
            "gross_only": True,
        },
        {
            "realization": "non_position_income",
            "driver": "corporate_action_cash",
            "allowed": True,
            "formula": "CAI(t)",
            "gross_only": True,
        },
    ]
    assert pnl["cell_count"] == 18
    assert pnl["allowed_cell_count"] == 13
    assert pnl["forbidden_cell_count"] == 5
    assert pnl["forbidden_cells_materialize_exact_decimal_zero"] is True
    assert pnl["forbidden_cells_allow_no_contribution"] is True
    assert pnl["forbidden_nonzero_or_contribution"] == "RECONCILIATION_BLOCKED"
    assert pnl["row_marginals"] == "derived_disclosure_only"
    assert pnl["column_marginals"] == "derived_disclosure_only"
    assert pnl["grand_total"] == "sum_atomic_cells_exactly_once"
    assert pnl["adding_marginals_or_grand_total_back_to_cells"] == "forbidden"
    assert pnl["corporate_action_basis_adjustment_classification"] == {
        "driver": "price_only",
        "disposed_formula_term": "-DA",
        "remaining_formula_term": "-RA",
        "may_enter_corporate_action_cash_driver": False,
    }
    assert pnl["gross_and_component_uniqueness"] == {
        "corporate_action_cash_cells_store_gross_not_net": True,
        "acquisition_fee_and_tax_enter_only_DF_DT_RF_RT": True,
        "sell_or_action_fee_and_tax_enter_only_SF_ST_NF_NT": True,
        "same_gross_cash_basis_fee_tax_or_slippage_enters_exactly_one_cell": True,
        "basis_disposal_status_unprovable": "PRECHECK_BLOCKED_entire_action",
    }
    assert pnl["ordinary_sell_gross_formula"] == "TB+TS"
    assert pnl["basis_disposal_corporate_action_has_no_TB_or_TS_and_uses_gross_CAD"] is True
    assert pnl["components_must_reconcile_to_period_total_pnl"] is True
    assert pnl["automatic_plug_cell"] == "forbidden"
    assert pnl["security_to_portfolio_aggregation"] == {
        "is_independent_reconciliation_layer_not_a_pnl_axis": True,
        "portfolio_cells_equal_exact_sum_of_security_cells_and_account_only_cells": True,
        "security_marginals_must_not_be_resummed": True,
        "portfolio_total_must_reconcile_to_account_equity_change_less_net_external_cash_inflow": (
            True
        ),
    }

    ledger = modules["ledger_v2"]
    assert ledger["full_cost_formula"] == (
        "benchmark_principal+execution_slippage+fees+taxes+corporate_action_basis_adjustment"
    )
    assert (
        ledger["buy_fee_and_tax"]["separate_fee_or_tax_expense_posting_that_duplicates_cost"]
        == "forbidden"
    )
    assert ledger["sell_cost_and_proceeds"]["fee_tax_or_cost_as_second_expense_after_netting"] == (
        "forbidden"
    )

    entitlement = modules["corporate_actions"]["entitlement_contract"]
    assert entitlement == {
        "record_cutoff_and_eligible_quantity_rules_must_be_proven_by_action_terms_and_market_rule_set": (
            True
        ),
        "settled_unsettled_and_restricted_security_treatment_must_be_explicit": True,
        "sellable_quantity_may_not_substitute_for_entitlement_quantity": True,
        "unprovable_cutoff_or_eligibility_treatment": "PRECHECK_BLOCKED_entire_action",
    }


def test_stage5d_sqlite_v4_is_one_atomic_same_database_proposal(
    repository_root: Path,
) -> None:
    rules = _json(repository_root / DRAFT_BUNDLE_PATH)["rules"]
    modules = rules["rule_modules"]
    sqlite = modules["sqlite_v4_durable_persistence"]

    assert sqlite["owned_database"] == "var/state/invest_system.sqlite3"
    assert sqlite["target_schema_version"] == 4
    assert sqlite["second_database_or_attach"] == "forbidden"
    assert sqlite["required_tables"] == [
        "stage5_artifacts",
        "stage5_run_aggregates",
        "stage5_run_artifacts",
        "stage5_ledger_events",
        "stage5_run_ledger_events",
        "stage5_account_generations",
    ]
    assert sqlite["migration"] == {
        "exact_v3_schema_snapshot_must_be_frozen": True,
        "unknown_or_tampered_v3_schema": "refuse_with_zero_writes",
        "path": "verified_v3_to_v4_additive_migration",
        "transaction": "BEGIN_IMMEDIATE",
        "migration_failure_rolls_back_schema_and_user_version": True,
        "lazy_create_table_if_not_exists": "forbidden",
    }
    assert sqlite["atomic_commit_group"] == [
        "strategy_run_manifest_and_local_release_pin_identity",
        "stage4_case_result_input_and_replay",
        "stage5c_complete_case_and_result",
        "target_approval_constraint_order_intent_and_fill",
        "projected_and_accepted_as_of_ledger_events",
        "corporate_action_inputs_and_events",
        "marks_nav_and_atomic_pnl_cells",
        "security_to_portfolio_reconciliation",
        "complete_stage5_replay",
        "replay_seal_root_and_ordered_typed_memberships",
        "artifact_role_closure",
        "account_generation",
    ]
    assert sqlite["any_precheck_reconciliation_hash_or_sql_failure"] == ("rollback_entire_group")
    assert sqlite["idempotency"] == {
        "same_run_case_or_event_identity_same_canonical_bytes": (
            "return_verified_existing_receipt"
        ),
        "same_run_case_or_event_identity_different_canonical_bytes": (
            "immutable_conflict_and_rollback"
        ),
        "same_replay_hash_different_canonical_bytes": "integrity_failure_and_rollback",
    }
    assert sqlite["account_concurrency"] == {
        "append_only_generation_records": True,
        "expected_base_event_set_hash_required": True,
        "generation_or_event_set_conflict": "rollback_reload_and_recompute_full_stage5",
        "sql_only_retry_or_silent_fill_rebase": "forbidden",
    }
    assert (
        sqlite[
            "technical_codec_schema_hash_identity_concurrency_reconciliation_"
            "incomplete_pnl_sqlite_interrupt_or_read_back_failure"
        ]
        == "zero_visible_write"
    )
    assert sqlite["historical_withdrawn_material_only_allowed_for_zero_write_audit_replay"] is True

    audit = modules["complete_replay"]["audit_replay"]
    assert audit["audit_only"] is True
    assert audit["runtime_capability_issued"] is False
    assert audit["updates_account_generation"] is False
    assert audit["durable_write"] is False
    assert rules["authorization_boundary"]["authorizes_durable_persistence"] is False
