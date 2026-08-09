"""Exact Stage 5A approval boundary without execution business logic.

The owner-approved bundle may issue only an anonymous synthetic execution-
validation capability.  This module deliberately implements no market-rule
table, fill model, portfolio state, ledger, P&L, replay engine, persistence,
broker adapter, or real-account integration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from invest_system.canonical import canonical_sha256
from invest_system.domain.rule_approval import (
    CURRENT_RULE_APPROVAL_REGISTRY,
    ApprovedRuleCapability,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import HashDigest

STAGE5_STRATEGY_ID = "industrial_bottleneck_event"
STAGE5_APPROVAL_SCOPE = RuleApprovalScope.STAGE5_SYNTHETIC_EXECUTION_VALIDATION
STAGE5_5A_RULE_BUNDLE_ID = "industrial_event_stage5_5a_execution_portfolio_ledger_replay"
STAGE5_5A_RULE_BUNDLE_VERSION = "0.1.0"
STAGE5_5A_RULE_BUNDLE_SHA256 = "c69bc7170b608bc6f3e2dd4119e08b13d4f10f03730be115dbc191b47544eeb7"
STAGE5_5A_RULES_SHA256 = "bb7ef84b1287be1111fe95571efa58cd268a65d862b7d235508fc31ccbaf0c69"
STAGE5_5A_RULE_APPROVAL_ID = "rule_approval_stage5_5a_execution_portfolio_ledger_replay_v0_1_0"
STAGE5_5A_RULE_APPROVAL_RECORD_SHA256 = (
    "5b9536f546337ba38408d255b3fbad68fbbdf6d9ccba9af79b10b6e04ca8cd78"
)
STAGE5_5A_SPECIFICATION_SHA256 = "df866949bdfcc8eb52451b38155080551291d7539f17b730a01a233cf60a5740"
STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256 = (
    "d0664b6b371ad042218f5d3c6caac9b9f1d1edd3ff475a5f7b36e401ca3d02db"
)
STAGE5_5A_DRAFT_RULES_SHA256 = "ecc61a4ee3eb3a7e4dea7238c027aca2ac3c2ce145eb40f0fa80bb34085463f5"
STAGE5_5A_APPROVAL_DOCUMENT_SHA256 = (
    "4862d0c8add5d28db8f24432d4d3958c9de6f73bf74ae7d4754e0290916cbf02"
)
STAGE5_5A_OWNER_APPROVAL_ITEM_IDS = tuple(f"5A-{number:02d}" for number in range(1, 41))

_EXPECTED_UPSTREAM = {
    "batch_id": "4B",
    "bundle_id": "industrial_event_stage4_4b_complete_engine_integration",
    "bundle_version": "0.1.0",
    "bundle_hash": "ba8886cf85beef084c2a2d3b83446b499c7786fbc3f0e56066fb8cedc8e27e77",
    "rules_hash": "3477d237523ce84239ca1363ad1c8d2e467528ec90acb0034193aeb320740019",
    "approval_record_hash": ("d809394ef00beab2053795779878025fb1b3b0cd2a49da76302e500ef7f4b2fe"),
    "stage4_inventory_hash": ("fc07b10bb17d91b3447504fe7f5b2e346023fd98bb14da991e1a1dd85381bf53"),
}


class Stage5RuleCompatibilityError(ValueError):
    """Stable fail-closed rejection from the Stage 5A approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


_STAGE5_MARKET_RULE_ISSUER = object()
_STAGE5_PORTFOLIO_LEDGER_RULE_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage5MarketExecutionRules:
    """Unforgeable typed view of the approved Stage 5B market semantics."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    maximum_participation_rate: Decimal
    entry_attempt_days: int
    order_time_in_force: str
    minimum_net_base_remaining_return: Decimal
    minimum_reward_to_downside: Decimal
    event_order: tuple[str, ...]

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
    ) -> None:
        if _issuer is not _STAGE5_MARKET_RULE_ISSUER:
            raise Stage5RuleCompatibilityError(
                "STAGE5_MARKET_RULE_ISSUER_INVALID",
                "Stage 5B typed rules require the exact approved Stage 5A capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(self, "maximum_participation_rate", Decimal("0.05"))
        object.__setattr__(self, "entry_attempt_days", 3)
        object.__setattr__(self, "order_time_in_force", "DAY")
        object.__setattr__(self, "minimum_net_base_remaining_return", Decimal("0.15"))
        object.__setattr__(self, "minimum_reward_to_downside", Decimal("2.00"))
        object.__setattr__(
            self,
            "event_order",
            ("event_time", "event_type_priority", "stable_event_id"),
        )

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage5MarketExecutionRules:
        """Bind the exact approved bundle to executable Stage 5B constants."""

        if capability.bundle_hash != document.bundle_hash():
            raise Stage5RuleCompatibilityError(
                "STAGE5_CAPABILITY_BUNDLE_MISMATCH",
                "capability and Stage 5A bundle identities differ",
            )
        if capability.approval_scope is not STAGE5_APPROVAL_SCOPE:
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_SCOPE_MISMATCH",
                "only Stage 5 synthetic execution validation is approved",
            )
        if (
            document.bundle_hash().value != STAGE5_5A_RULE_BUNDLE_SHA256
            or canonical_sha256(document.rules) != STAGE5_5A_RULES_SHA256
            or capability.approval_id != STAGE5_5A_RULE_APPROVAL_ID
            or capability.approval_record_hash.value != STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_MARKET_RULE_IDENTITY_UNSUPPORTED",
                "Stage 5B requires the exact owner-approved Stage 5A identities",
            )
        market = _mapping(
            _mapping(document.rules.get("rule_modules"), field_name="rule_modules").get(
                "market_rules_and_executable_price"
            ),
            field_name="market_rules_and_executable_price",
        )
        fill = _mapping(
            _mapping(document.rules.get("rule_modules"), field_name="rule_modules").get(
                "capacity_cost_and_fill"
            ),
            field_name="capacity_cost_and_fill",
        )
        impact = _mapping(fill.get("impact_curve"), field_name="impact_curve")
        if (
            market.get("entry_attempt_days") != 3
            or market.get("gate3_and_gate4_rerun_each_attempt") is not True
            or market.get("daily_low_precision_vwap", {}).get("formula") != "turnover/volume"
            or fill.get("synthetic_maximum_participation_rate") != "0.05"
            or fill.get("participation_comparison") != "lte"
            or impact.get("interpolation") != "linear"
            or impact.get("extrapolation") != "forbidden"
            or fill.get("order_time_in_force") != "DAY"
            or tuple(fill.get("event_order", ()))
            != ("event_time", "event_type_priority", "stable_event_id")
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_MARKET_MACHINE_SEMANTICS_UNSUPPORTED",
                "approved Stage 5B market semantics differ from the implemented slice",
            )
        return cls(
            _issuer=_STAGE5_MARKET_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
        )


@dataclass(frozen=True, slots=True, init=False)
class ApprovedStage5PortfolioLedgerRules:
    """Unforgeable typed view of the approved Stage 5C portfolio semantics."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    normal_planned_loss_rate: Decimal
    defensive_planned_loss_rate: Decimal
    crisis_new_risk_rate: Decimal
    initial_weight_cap: Decimal
    company_weight_cap: Decimal
    cluster_planned_loss_cap: Decimal
    cluster_market_value_cap: Decimal
    aggregate_planned_loss_cap: Decimal
    drawdown_caution: Decimal
    drawdown_derisk_only: Decimal
    drawdown_stopped: Decimal
    drawdown_survival_breach: Decimal
    event_order: tuple[str, ...]
    ledger_event_types: tuple[str, ...]

    def __init__(
        self,
        *,
        _issuer: object,
        bundle_hash: HashDigest,
        approval_record_hash: HashDigest,
        approval_id: str,
        ledger_event_types: tuple[str, ...],
    ) -> None:
        if _issuer is not _STAGE5_PORTFOLIO_LEDGER_RULE_ISSUER:
            raise Stage5RuleCompatibilityError(
                "STAGE5_PORTFOLIO_LEDGER_RULE_ISSUER_INVALID",
                "Stage 5C typed rules require the exact approved Stage 5A capability",
            )
        object.__setattr__(self, "bundle_hash", bundle_hash)
        object.__setattr__(self, "approval_record_hash", approval_record_hash)
        object.__setattr__(self, "approval_id", approval_id)
        object.__setattr__(self, "normal_planned_loss_rate", Decimal("0.005"))
        object.__setattr__(self, "defensive_planned_loss_rate", Decimal("0.0025"))
        object.__setattr__(self, "crisis_new_risk_rate", Decimal("0"))
        object.__setattr__(self, "initial_weight_cap", Decimal("0.05"))
        object.__setattr__(self, "company_weight_cap", Decimal("0.10"))
        object.__setattr__(self, "cluster_planned_loss_cap", Decimal("0.015"))
        object.__setattr__(self, "cluster_market_value_cap", Decimal("0.20"))
        object.__setattr__(self, "aggregate_planned_loss_cap", Decimal("0.04"))
        object.__setattr__(self, "drawdown_caution", Decimal("0.08"))
        object.__setattr__(self, "drawdown_derisk_only", Decimal("0.12"))
        object.__setattr__(self, "drawdown_stopped", Decimal("0.15"))
        object.__setattr__(self, "drawdown_survival_breach", Decimal("0.20"))
        object.__setattr__(
            self,
            "event_order",
            ("effective_at", "event_type_priority", "ledger_event_id"),
        )
        object.__setattr__(self, "ledger_event_types", ledger_event_types)

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedStage5PortfolioLedgerRules:
        """Bind the exact approved bundle to executable Stage 5C constants."""

        if capability.bundle_hash != document.bundle_hash():
            raise Stage5RuleCompatibilityError(
                "STAGE5_CAPABILITY_BUNDLE_MISMATCH",
                "capability and Stage 5A bundle identities differ",
            )
        if capability.approval_scope is not STAGE5_APPROVAL_SCOPE:
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_SCOPE_MISMATCH",
                "only Stage 5 synthetic execution validation is approved",
            )
        if (
            document.bundle_hash().value != STAGE5_5A_RULE_BUNDLE_SHA256
            or canonical_sha256(document.rules) != STAGE5_5A_RULES_SHA256
            or capability.approval_id != STAGE5_5A_RULE_APPROVAL_ID
            or capability.approval_record_hash.value != STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_PORTFOLIO_LEDGER_IDENTITY_UNSUPPORTED",
                "Stage 5C requires the exact owner-approved Stage 5A identities",
            )
        modules = _mapping(document.rules.get("rule_modules"), field_name="rule_modules")
        portfolio = _mapping(
            modules.get("portfolio_and_risk"),
            field_name="portfolio_and_risk",
        )
        limits = _mapping(portfolio.get("limits"), field_name="portfolio_and_risk.limits")
        drawdown = _mapping(
            portfolio.get("drawdown"),
            field_name="portfolio_and_risk.drawdown",
        )
        ledger = _mapping(
            modules.get("ledger_corporate_actions_and_pnl"),
            field_name="ledger_corporate_actions_and_pnl",
        )
        journal = _mapping(ledger.get("journal"), field_name="ledger.journal")
        settlement = _mapping(
            ledger.get("settlement_and_availability"),
            field_name="ledger.settlement_and_availability",
        )
        lots = _mapping(ledger.get("lots"), field_name="ledger.lots")
        derived = _mapping(ledger.get("derived_state"), field_name="ledger.derived_state")
        event_types = tuple(journal.get("event_types", ()))
        expected_event_types = (
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
        )
        if (
            portfolio.get("stress_loss_rate_formula")
            != "max(abs(min(0,stress_scenario_return)),0.10)"
            or portfolio.get("initial_target_value_formula")
            != "min(account_nav*planned_account_loss_rate/stress_loss_rate,account_nav*0.05,liquidity_capacity_value,company_remaining_cap,every_risk_cluster_remaining_cap,aggregate_open_risk_remaining_value,available_cash_after_cost_reserve)"
            or limits.get("normal_planned_account_loss_rate") != "0.005"
            or limits.get("defensive_planned_account_loss_rate") != "0.0025"
            or limits.get("crisis_new_risk_rate") != "0"
            or limits.get("initial_e4_weight_cap") != "0.05"
            or limits.get("single_company_total_weight_cap") != "0.10"
            or limits.get("risk_cluster_planned_loss_cap") != "0.015"
            or limits.get("risk_cluster_market_value_cap") != "0.20"
            or limits.get("aggregate_open_planned_loss_cap") != "0.04"
            or limits.get("comparison") != "lte"
            or tuple(portfolio.get("market_regime_states", ())) != ("NORMAL", "DEFENSIVE", "CRISIS")
            or drawdown.get("equality_enters_stricter_band") is not True
            or journal.get("append_only") is not True
            or journal.get("double_entry") is not True
            or journal.get("direct_balance_mutation") != "forbidden"
            or tuple(journal.get("sort_order", ()))
            != ("effective_at", "event_type_priority", "ledger_event_id")
            or event_types != expected_event_types
            or settlement.get("trade_settlement_sellability_and_cash_availability_separate")
            is not True
            or settlement.get("cash_reserve_covers_price_and_worst_applicable_cost") is not True
            or lots.get("method") != "FIFO"
            or derived.get("actual_quantity_cash_cost_sellable_and_nav_derived_from_journal")
            is not True
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_PORTFOLIO_LEDGER_MACHINE_SEMANTICS_UNSUPPORTED",
                "approved Stage 5C portfolio or ledger semantics differ from this slice",
            )
        return cls(
            _issuer=_STAGE5_PORTFOLIO_LEDGER_RULE_ISSUER,
            bundle_hash=capability.bundle_hash,
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            ledger_event_types=event_types,
        )


def _mapping(value: Any, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an object",
        )
    return value


def _hash_value(value: Any, *, field_name: str) -> str:
    item = _mapping(value, field_name=field_name)
    if set(item) != {"algorithm", "value"} or item.get("algorithm") != "sha256":
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name} must be an exact SHA-256 identity",
        )
    digest = item.get("value")
    if not isinstance(digest, str):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVED_CONTRACT_INVALID",
            f"{field_name}.value must be text",
        )
    return digest


def _require_exact_authority(rules: Mapping[str, Any]) -> None:
    boundary = _mapping(rules.get("authorization_boundary"), field_name="authorization_boundary")
    expected = {
        "approval_scope": STAGE5_APPROVAL_SCOPE.value,
        "allowed_run_modes": ("research",),
        "synthetic_only": True,
        "validation_only": True,
        "runtime_capability_issued": True,
        "authorizes_backtest": False,
        "authorizes_paper": False,
        "authorizes_shadow": False,
        "authorizes_live": False,
        "authorizes_real_positions": False,
        "authorizes_real_accounts": False,
        "authorizes_real_orders": False,
        "authorizes_broker_connectivity": False,
        "authorizes_kb_write": False,
    }
    if dict(boundary) != expected:
        raise Stage5RuleCompatibilityError(
            "STAGE5_AUTHORIZATION_BOUNDARY_MISMATCH",
            "the approved Stage 5A capability must remain synthetic research validation only",
        )


def _require_exact_approval_items(rules: Mapping[str, Any]) -> None:
    raw_items = rules.get("owner_approval_items")
    if not isinstance(raw_items, tuple):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_ITEMS_INVALID",
            "owner_approval_items must be an immutable sequence",
        )
    identities: list[str] = []
    for raw_item in raw_items:
        item = _mapping(raw_item, field_name="owner_approval_items[]")
        if set(item) != {"approval_item_id", "status"} or item.get("status") != "approved":
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_ITEMS_INVALID",
                "all and only the forty owner decisions must be approved",
            )
        item_id = item.get("approval_item_id")
        if not isinstance(item_id, str):
            raise Stage5RuleCompatibilityError(
                "STAGE5_APPROVAL_ITEMS_INVALID",
                "approval_item_id must be text",
            )
        identities.append(item_id)
    if tuple(identities) != STAGE5_5A_OWNER_APPROVAL_ITEM_IDS:
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_ITEMS_INVALID",
            "the approved decision identity sequence differs from 5A-01 through 5A-40",
        )


def _require_exact_lineage(rules: Mapping[str, Any]) -> None:
    upstream = _mapping(rules.get("exact_upstream_dependency"), field_name="upstream")
    for field_name in ("batch_id", "bundle_id", "bundle_version"):
        if upstream.get(field_name) != _EXPECTED_UPSTREAM[field_name]:
            raise Stage5RuleCompatibilityError(
                "STAGE5_UPSTREAM_IDENTITY_MISMATCH",
                f"{field_name} differs from the approved Stage 4B identity",
            )
    for field_name in (
        "bundle_hash",
        "rules_hash",
        "approval_record_hash",
        "stage4_inventory_hash",
    ):
        if (
            _hash_value(upstream.get(field_name), field_name=field_name)
            != _EXPECTED_UPSTREAM[field_name]
        ):
            raise Stage5RuleCompatibilityError(
                "STAGE5_UPSTREAM_IDENTITY_MISMATCH",
                f"{field_name} differs from the approved Stage 4B identity",
            )

    source = _mapping(rules.get("approval_source_binding"), field_name="approval_source_binding")
    if (
        _hash_value(source.get("specification_hash"), field_name="specification_hash")
        != STAGE5_5A_SPECIFICATION_SHA256
        or _hash_value(source.get("draft_bundle_hash"), field_name="draft_bundle_hash")
        != STAGE5_5A_DRAFT_RULE_BUNDLE_SHA256
        or _hash_value(source.get("draft_rules_hash"), field_name="draft_rules_hash")
        != STAGE5_5A_DRAFT_RULES_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SOURCE_MISMATCH",
            "the approved bundle is not bound to the exact owner-reviewed draft lineage",
        )
    document_binding = _mapping(rules.get("document_binding"), field_name="document_binding")
    if (
        _hash_value(document_binding.get("hash"), field_name="document_binding.hash")
        != STAGE5_5A_APPROVAL_DOCUMENT_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SOURCE_MISMATCH",
            "the approved bundle is not bound to the exact owner approval document",
        )


def require_stage5_rule_capability(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Issue only the exact Stage 5A synthetic execution-validation capability."""

    if not isinstance(document, RuleBundleDocument):
        raise TypeError("document must be a RuleBundleDocument")
    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    expected_identity = (
        STAGE5_STRATEGY_ID,
        STAGE5_5A_RULE_BUNDLE_ID,
        STAGE5_5A_RULE_BUNDLE_VERSION,
    )
    if (document.strategy_id, document.bundle_id, document.bundle_version) != expected_identity:
        raise Stage5RuleCompatibilityError(
            "STAGE5_RULE_IDENTITY_UNSUPPORTED",
            "only the exact approved Stage 5A bundle may issue capability",
        )
    _require_exact_authority(document.rules)
    _require_exact_approval_items(document.rules)
    _require_exact_lineage(document.rules)
    if canonical_sha256(document.rules) != STAGE5_5A_RULES_SHA256 or (
        document.bundle_hash().value != STAGE5_5A_RULE_BUNDLE_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_RULE_HASH_UNSUPPORTED",
            "the Stage 5A machine semantics differ from the owner-approved version",
        )
    capability = registry.require(document)
    if capability.approval_scope is not STAGE5_APPROVAL_SCOPE:
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_SCOPE_MISMATCH",
            "another stage or run scope cannot authorize Stage 5A",
        )
    if capability.approval_id != STAGE5_5A_RULE_APPROVAL_ID or (
        capability.approval_record_hash.value != STAGE5_5A_RULE_APPROVAL_RECORD_SHA256
    ):
        raise Stage5RuleCompatibilityError(
            "STAGE5_APPROVAL_RECORD_UNSUPPORTED",
            "the capability requires the exact owner approval record",
        )
    return capability
