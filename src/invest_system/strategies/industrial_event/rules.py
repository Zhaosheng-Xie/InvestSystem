"""Strict loader for the approved Stage 2B industrial-event rule profile."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.models import HashDigest, RuleStatus

INDUSTRIAL_EVENT_STRATEGY_ID = "industrial_bottleneck_event"
INDUSTRIAL_EVENT_RULE_BUNDLE_ID = "industrial_event_minimum_order_contract_slice"
INDUSTRIAL_EVENT_RULE_BUNDLE_VERSION = "0.1.0"
INDUSTRIAL_EVENT_SEMANTIC_PROFILE = "industrial_event_minimum_order_contract_v0.1"
INDUSTRIAL_EVENT_RULE_APPROVAL_ID = "rule_approval_stage2b_minimum_order_contract_v0_1_0"
INDUSTRIAL_EVENT_RULE_APPROVAL_RECORD_SHA256 = (
    "25f464a6b15cb8fb944c014aeb4d9d72bbd21129275e5102d84f2a2391f9469e"
)
INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256 = (
    "9c746809cf9d56bf54419dead7dbe33331b0fce9e17899993d1307795fb629d7"
)


class IndustrialEventRuleCompatibilityError(ValueError):
    """The approved document cannot be executed by this exact code profile."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _mapping(path: str, value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise IndustrialEventRuleCompatibilityError(
            "RULE_SHAPE_INVALID", f"{path} must be an object"
        )
    return value


def _exact_keys(path: str, value: Mapping[str, Any], expected: set[str]) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise IndustrialEventRuleCompatibilityError(
            "RULE_KEYS_MISMATCH",
            f"{path} has missing={missing!r}, extra={extra!r}",
        )


def _exact(path: str, actual: Any, expected: Any) -> None:
    if type(actual) is not type(expected) or actual != expected:
        raise IndustrialEventRuleCompatibilityError(
            "RULE_VALUE_UNSUPPORTED",
            f"{path} must be exactly {expected!r}",
        )


def _decimal(path: str, value: Any, expected: str) -> Decimal:
    _exact(path, value, expected)
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise IndustrialEventRuleCompatibilityError(
            "RULE_DECIMAL_INVALID", f"{path} must be an exact decimal string"
        ) from exc
    if not parsed.is_finite():
        raise IndustrialEventRuleCompatibilityError(
            "RULE_DECIMAL_INVALID", f"{path} must be finite"
        )
    return parsed


def _validate_authorization_boundary(value: Any) -> None:
    path = "rules.authorization_boundary"
    rules = _mapping(path, value)
    _exact_keys(
        path,
        rules,
        {
            "approval_scope",
            "default_policy",
            "allowed_run_modes",
            "required_input",
            "forbidden_run_modes",
            "forbidden_effects",
            "shadow_only_is_a_result_label_not_run_authority",
            "scope_must_match_exactly",
            "scope_expansion_by_inference_is_forbidden",
            "new_scope_requires_new_owner_approval",
        },
    )
    expected = {
        "approval_scope": "stage2b_synthetic_validation",
        "default_policy": "deny",
        "allowed_run_modes": ("research",),
        "forbidden_run_modes": ("backtest", "paper", "shadow", "live"),
        "forbidden_effects": (
            "target_portfolio",
            "approved_position",
            "actual_position",
            "broker_order",
            "capital_deployment",
        ),
        "shadow_only_is_a_result_label_not_run_authority": True,
        "scope_must_match_exactly": True,
        "scope_expansion_by_inference_is_forbidden": True,
        "new_scope_requires_new_owner_approval": True,
    }
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)
    required_input = _mapping(f"{path}.required_input", rules["required_input"])
    _exact_keys(
        f"{path}.required_input",
        required_input,
        {
            "provenance",
            "synthetic",
            "validation_only",
            "not_a_published_release",
            "not_strategy_evidence",
            "authorizes_positions",
            "authorizes_orders",
        },
    )
    required_expected = {
        "provenance": "invest_system_synthetic",
        "synthetic": True,
        "validation_only": True,
        "not_a_published_release": True,
        "not_strategy_evidence": True,
        "authorizes_positions": False,
        "authorizes_orders": False,
    }
    for key, expected_value in required_expected.items():
        _exact(f"{path}.required_input.{key}", required_input[key], expected_value)


def _validate_decision_safety(value: Any) -> None:
    path = "rules.decision_safety"
    rules = _mapping(path, value)
    expected = {
        "position_state": "FLAT",
        "target_weight": "0",
        "approved_weight": "0",
        "actual_weight": "0",
        "approver": None,
        "authorizes_real_trade_ready": False,
        "synthetic_trade_ready_proves_path_reachability_only": True,
    }
    _exact_keys(path, rules, set(expected))
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)


def _validate_decimal_policy(value: Any) -> None:
    path = "rules.decimal_policy"
    rules = _mapping(path, value)
    expected = {
        "binary_float_forbidden": True,
        "intermediate_rounding_forbidden": True,
        "comparison_uses_unrounded_decimal": True,
        "display_decimal_places": 6,
        "display_rounding": "ROUND_HALF_EVEN",
        "unknown_is_not_zero": True,
    }
    _exact_keys(path, rules, set(expected))
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)


def _validate_event_rules(value: Any) -> tuple[Decimal, Decimal, Decimal, int, int, int]:
    path = "rules.event_and_gate_rules"
    rules = _mapping(path, value)
    expected_keys = {
        "semantic_profile",
        "e4_predicate",
        "e3_5_decision_state",
        "minimum_independent_evidence_chains",
        "minimum_authoritative_original_chains",
        "standard_track_requires_positive_base_and_downside_counterfactual_profit",
        "gate_3_comparison",
        "gate_4_nonpositive_downside_loss_outcome",
        "rule_ids",
        "gate_2_profit_materiality_threshold",
        "gate_4_net_base_return_threshold",
        "gate_4_reward_to_downside_threshold",
        "next_verification_trading_days_max",
        "gate_aggregation",
        "evaluation_order",
        "short_circuit",
        "short_circuit_outcomes",
        "not_evaluated_is_not_an_outcome",
    }
    _exact_keys(path, rules, expected_keys)
    expected = {
        "semantic_profile": INDUSTRIAL_EVENT_SEMANTIC_PROFILE,
        "e4_predicate": "strict_and",
        "e3_5_decision_state": "SHADOW_ONLY",
        "minimum_independent_evidence_chains": 2,
        "minimum_authoritative_original_chains": 1,
        "standard_track_requires_positive_base_and_downside_counterfactual_profit": True,
        "gate_3_comparison": "strict_exact_no_tolerance",
        "gate_4_nonpositive_downside_loss_outcome": "ABSTAIN",
        "rule_ids": (
            "S2B-EVT-001",
            "S2B-EVT-002",
            "S2B-G1-001",
            "S2B-G2-001",
            "S2B-G3-001",
            "S2B-G4-001",
            "S2B-AGG-001",
            "S2B-PIT-001",
            "S2B-AUDIT-001",
            "S2B-ISOLATION-001",
        ),
        "next_verification_trading_days_max": 120,
        "gate_aggregation": "strict_and",
        "evaluation_order": (
            "admission",
            "event_state",
            "gate_1_authenticity",
            "gate_2_profit_materiality",
            "gate_3_expectation_gap",
            "gate_4_executable_return",
            "decision_state",
        ),
        "short_circuit": True,
        "short_circuit_outcomes": ("REJECT", "ABSTAIN", "SHADOW_ONLY", "BLOCKED"),
        "not_evaluated_is_not_an_outcome": True,
    }
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)
    profit_threshold = _decimal(
        f"{path}.gate_2_profit_materiality_threshold",
        rules["gate_2_profit_materiality_threshold"],
        "0.10",
    )
    net_return_threshold = _decimal(
        f"{path}.gate_4_net_base_return_threshold",
        rules["gate_4_net_base_return_threshold"],
        "0.15",
    )
    reward_threshold = _decimal(
        f"{path}.gate_4_reward_to_downside_threshold",
        rules["gate_4_reward_to_downside_threshold"],
        "2.00",
    )
    return profit_threshold, net_return_threshold, reward_threshold, 120, 2, 1


def _validate_fixture_identity(value: Any) -> tuple[str, str, str, str]:
    path = "rules.fixture_identity"
    rules = _mapping(path, value)
    expected = {
        "fixture_id": "synthetic_fixture_stage2b_optical_contract_001",
        "fixture_version": "0.1.0",
        "dataset_release_id_prefix": "synthetic_release_",
        "currency": "CNY",
        "real_world_entity_mapping": "prohibited",
    }
    _exact_keys(path, rules, set(expected))
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)
    return (
        "synthetic_fixture_stage2b_optical_contract_001",
        "0.1.0",
        "synthetic_release_",
        "CNY",
    )


def _validate_pit_policy(value: Any) -> None:
    path = "rules.pit_policy"
    rules = _mapping(path, value)
    expected = {
        "required_relation": "available_at <= knowledge_cutoff <= decision_at",
        "provider_available_at_must_not_be_recomputed": True,
        "future_fact_policy": "BLOCKED",
    }
    _exact_keys(path, rules, set(expected))
    for key, expected_value in expected.items():
        _exact(f"{path}.{key}", rules[key], expected_value)


def _validate_tracking_sections(rules: Mapping[str, Any]) -> None:
    approval_items = rules["approval_items"]
    if not isinstance(approval_items, tuple) or len(approval_items) != 22:
        raise IndustrialEventRuleCompatibilityError(
            "RULE_TRACKING_INVALID", "rules.approval_items must contain 22 approved IDs"
        )
    expected_approval_items = tuple(f"S2B-APPROVAL-{index:03d}" for index in range(1, 23))
    _exact("rules.approval_items", approval_items, expected_approval_items)

    binding = _mapping("rules.document_binding", rules["document_binding"])
    _exact_keys("rules.document_binding", binding, {"path", "hash"})
    if not isinstance(binding["path"], str) or not binding["path"]:
        raise IndustrialEventRuleCompatibilityError(
            "RULE_TRACKING_INVALID", "rules.document_binding.path must be non-empty"
        )
    digest = _mapping("rules.document_binding.hash", binding["hash"])
    _exact_keys("rules.document_binding.hash", digest, {"algorithm", "value"})
    try:
        HashDigest(algorithm=digest["algorithm"], value=digest["value"])
    except (TypeError, ValueError) as exc:
        raise IndustrialEventRuleCompatibilityError(
            "RULE_TRACKING_INVALID", "rules.document_binding.hash is invalid"
        ) from exc

    golden = _mapping("rules.golden_matrix", rules["golden_matrix"])
    expected_golden = {
        "strategy_fixture_results": ("TRADE_READY", "SHADOW_ONLY", "REJECT", "ABSTAIN"),
        "admission_failure_result": "BLOCKED",
        "blocked_must_precede_strategy_evaluation": True,
    }
    _exact_keys("rules.golden_matrix", golden, set(expected_golden))
    for key, expected_value in expected_golden.items():
        _exact(f"rules.golden_matrix.{key}", golden[key], expected_value)
    _exact(
        "rules.document_binding_is_traceability_only",
        rules["document_binding_is_traceability_only"],
        True,
    )
    _exact("rules.runtime_must_not_parse_markdown", rules["runtime_must_not_parse_markdown"], True)


@dataclass(frozen=True, slots=True)
class ApprovedIndustrialEventRules:
    """Typed, exact Stage 2B rules backed by an opaque approval capability."""

    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_id: str
    baseline_fixture_id: str
    fixture_version: str
    dataset_release_id_prefix: str
    currency: str
    profit_materiality_threshold: Decimal
    net_base_return_threshold: Decimal
    reward_to_downside_threshold: Decimal
    next_verification_trading_days_max: int
    minimum_independent_evidence_chains: int
    minimum_authoritative_original_chains: int

    @classmethod
    def from_approved_bundle(
        cls,
        document: RuleBundleDocument,
        capability: ApprovedRuleCapability,
    ) -> ApprovedIndustrialEventRules:
        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be a RuleBundleDocument")
        if not isinstance(capability, ApprovedRuleCapability):
            raise TypeError("capability must be an ApprovedRuleCapability")
        expected_identity = (
            INDUSTRIAL_EVENT_STRATEGY_ID,
            INDUSTRIAL_EVENT_RULE_BUNDLE_ID,
            INDUSTRIAL_EVENT_RULE_BUNDLE_VERSION,
        )
        document_identity = (document.strategy_id, document.bundle_id, document.bundle_version)
        capability_identity = (
            capability.strategy_id,
            capability.bundle_id,
            capability.bundle_version,
        )
        if document_identity != expected_identity or capability_identity != expected_identity:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_IDENTITY_UNSUPPORTED",
                "strategy, bundle, and version must match the Stage 2B v0.1 profile",
            )
        if document.declared_status is not RuleStatus.APPROVED:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_DOCUMENT_NOT_APPROVED", "rule document must declare approved"
            )
        if capability.rule_status is not RuleStatus.APPROVED:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_CAPABILITY_NOT_APPROVED", "capability must carry approved status"
            )
        if capability.approval_scope is not RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_SCOPE_UNSUPPORTED", "approval scope must be Stage 2B synthetic validation"
            )
        if capability.bundle_hash != document.bundle_hash():
            raise IndustrialEventRuleCompatibilityError(
                "RULE_HASH_MISMATCH", "capability does not bind the exact rule document"
            )
        if capability.approval_id != INDUSTRIAL_EVENT_RULE_APPROVAL_ID:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_APPROVAL_ID_UNSUPPORTED",
                "capability does not carry the pinned Stage 2B owner approval ID",
            )
        if capability.approval_record_hash.value != INDUSTRIAL_EVENT_RULE_APPROVAL_RECORD_SHA256:
            raise IndustrialEventRuleCompatibilityError(
                "RULE_APPROVAL_RECORD_HASH_UNSUPPORTED",
                "capability does not carry the pinned Stage 2B owner approval record hash",
            )

        rules = _mapping("rules", document.rules)
        _exact_keys(
            "rules",
            rules,
            {
                "approval_items",
                "authorization_boundary",
                "decision_safety",
                "decimal_policy",
                "document_binding",
                "event_and_gate_rules",
                "fixture_identity",
                "golden_matrix",
                "pit_policy",
                "document_binding_is_traceability_only",
                "runtime_must_not_parse_markdown",
            },
        )
        _validate_authorization_boundary(rules["authorization_boundary"])
        _validate_decision_safety(rules["decision_safety"])
        _validate_decimal_policy(rules["decimal_policy"])
        (
            profit_threshold,
            net_return_threshold,
            reward_threshold,
            max_days,
            minimum_chains,
            minimum_authoritative,
        ) = _validate_event_rules(rules["event_and_gate_rules"])
        (
            baseline_fixture_id,
            fixture_version,
            dataset_release_id_prefix,
            currency,
        ) = _validate_fixture_identity(rules["fixture_identity"])
        _validate_pit_policy(rules["pit_policy"])
        _validate_tracking_sections(rules)
        return cls(
            bundle_hash=document.bundle_hash(),
            approval_record_hash=capability.approval_record_hash,
            approval_id=capability.approval_id,
            baseline_fixture_id=baseline_fixture_id,
            fixture_version=fixture_version,
            dataset_release_id_prefix=dataset_release_id_prefix,
            currency=currency,
            profit_materiality_threshold=profit_threshold,
            net_base_return_threshold=net_return_threshold,
            reward_to_downside_threshold=reward_threshold,
            next_verification_trading_days_max=max_days,
            minimum_independent_evidence_chains=minimum_chains,
            minimum_authoritative_original_chains=minimum_authoritative,
        )
