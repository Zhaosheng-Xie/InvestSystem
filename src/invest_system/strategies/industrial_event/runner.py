"""Typed, research-only Stage 2B vertical-slice orchestration.

This module is the production composition boundary for the approved synthetic
slice.  It validates one exact Manifest and fixture capability, invokes the
pure engine exactly once, constructs the replay envelope from that typed
decision, and emits a complete DecisionRecord.  No portfolio, broker, order,
backtest, paper, shadow, or live side effect exists here.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from invest_system.canonical import JsonValue, canonical_sha256, to_json_value
from invest_system.domain.replay import ReplayEnvelope, compute_replay_hash
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.domain.synthetic_fixture import (
    ApprovedSyntheticFixtureCapability,
    SyntheticFixtureAuthorizationError,
)
from invest_system.models import (
    DECISION_RECORD_SCHEMA_VERSION,
    DecisionRecord,
    GateEvaluationState,
    GateOutcome,
    HashDigest,
    PositionState,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
)

from .engine import evaluate_industrial_event
from .models import (
    CASE_MATERIAL_HASH_PREDICATE,
    COMPLETE_CASE_PAYLOAD_PREDICATE,
    IndustrialEventCase,
    IndustrialEventDecision,
)
from .rules import (
    INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256,
    INDUSTRIAL_EVENT_STRATEGY_ID,
    ApprovedIndustrialEventRules,
    IndustrialEventRuleCompatibilityError,
)

INDUSTRIAL_EVENT_STAGE2B_STRATEGY_VERSION = "0.1.0"
STAGE2B_NON_TRADE_DECLARATION = (
    "Stage 2B synthetic research validation only; no backtest, paper, shadow, live, "
    "position, portfolio, approval, order, or capital-deployment authority."
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_UTC_AUDIT_TIMESTAMP_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}Z$"
)
_AUDIT_CLASSIFICATIONS = frozenset({"Fact", "Assumption", "Derived", "Judgment"})
_ASSUMPTION_AUDIT_FIELDS = (
    "assumption_id",
    "as_of",
    "scenario",
    "source_reason",
    "falsifier",
)


class Stage2BResearchValidationError(ValueError):
    """Stable fail-closed error from the typed Stage 2B runner."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass(frozen=True, slots=True)
class Stage2BResearchValidationResult:
    """Complete normal-path artifacts from exactly one strategy evaluation."""

    strategy_decision: IndustrialEventDecision
    replay_envelope: ReplayEnvelope
    decision_record: DecisionRecord
    strategy_evaluator_calls: int = field(default=1, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_decision, IndustrialEventDecision):
            raise TypeError("strategy_decision must be an IndustrialEventDecision")
        if not isinstance(self.replay_envelope, ReplayEnvelope):
            raise TypeError("replay_envelope must be a ReplayEnvelope")
        if not isinstance(self.decision_record, DecisionRecord):
            raise TypeError("decision_record must be a DecisionRecord")
        if self.decision_record.replay_hash != compute_replay_hash(self.replay_envelope):
            raise ValueError("DecisionRecord replay_hash must bind the replay envelope")


def _digest(model: Any) -> HashDigest:
    return HashDigest(algorithm="sha256", value=model.canonical_sha256())


def _validate_decision_id(decision_id: str) -> None:
    if not isinstance(decision_id, str) or _ID_RE.fullmatch(decision_id) is None:
        raise Stage2BResearchValidationError(
            "DECISION_ID_INVALID",
            "decision_id must be a valid 1-128 character ASCII audit ID",
        )


def _validate_approved_rules(
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
) -> None:
    """Reject an unpinned or semantically incompatible rule profile before evaluation."""

    try:
        ApprovedIndustrialEventRules.from_approved_bundle(
            rule_document,
            approval_capability,
        )
    except IndustrialEventRuleCompatibilityError as exc:
        raise Stage2BResearchValidationError(
            exc.code,
            "rule document or approval capability is outside the pinned Stage 2B profile",
        ) from exc


def _validate_manifest(
    manifest: StrategyRunManifest,
    case: IndustrialEventCase,
    *,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
    fixture_capability: ApprovedSyntheticFixtureCapability,
) -> None:
    if manifest.strategy_id != INDUSTRIAL_EVENT_STRATEGY_ID:
        raise Stage2BResearchValidationError(
            "MANIFEST_STRATEGY_ID_MISMATCH",
            "Manifest strategy_id is outside the approved industrial-event slice",
        )
    if manifest.strategy_version != INDUSTRIAL_EVENT_STAGE2B_STRATEGY_VERSION:
        raise Stage2BResearchValidationError(
            "MANIFEST_STRATEGY_VERSION_MISMATCH",
            "Manifest strategy_version is not the Stage 2B implementation version",
        )
    if manifest.created_at != case.decision_at:
        raise Stage2BResearchValidationError(
            "MANIFEST_CLOCK_MISMATCH",
            "Stage 2B Manifest created_at must equal the injected decision clock",
        )
    if (
        manifest.strategy_input_ref
        != case.strategy_input.verified_knowledge_input.strategy_input_ref
    ):
        raise Stage2BResearchValidationError(
            "MANIFEST_INPUT_REFERENCE_MISMATCH",
            "Manifest and synthetic strategy input references differ",
        )
    if (
        manifest.rule_bundle_id != rule_document.bundle_id
        or manifest.rule_bundle_version != rule_document.bundle_version
        or manifest.rule_bundle_hash != rule_document.bundle_hash()
        or manifest.rule_status is not RuleStatus.APPROVED
    ):
        raise Stage2BResearchValidationError(
            "MANIFEST_RULE_IDENTITY_MISMATCH",
            "Manifest does not bind the exact approved rule document",
        )
    if (
        approval_capability.bundle_hash != rule_document.bundle_hash()
        or manifest.rule_approval_id != approval_capability.approval_id
        or manifest.rule_approval_record_hash != approval_capability.approval_record_hash
        or manifest.rule_approval_scope != approval_capability.approval_scope.value
        or approval_capability.approval_scope is not RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION
    ):
        raise Stage2BResearchValidationError(
            "MANIFEST_RULE_APPROVAL_MISMATCH",
            "Manifest and rule approval capability do not close over one exact approval",
        )
    strategy_input = case.strategy_input
    if (
        manifest.input_envelope_hash != _digest(strategy_input)
        or manifest.strategy_case_envelope_hash != _digest(case)
        or manifest.strategy_case_input_hash != case.semantic_input_hash()
        or manifest.synthetic_fixture_id != strategy_input.fixture_id
        or manifest.synthetic_fixture_version != strategy_input.fixture_version
        or manifest.synthetic_fixture_payload_hash != strategy_input.fixture_payload_hash
    ):
        raise Stage2BResearchValidationError(
            "MANIFEST_FIXTURE_IDENTITY_MISMATCH",
            "Manifest does not bind all four synthetic input identities",
        )
    if manifest.artifact_consumption_receipt_hash != strategy_input.fixture_payload_hash:
        raise Stage2BResearchValidationError(
            "MANIFEST_SYNTHETIC_RECEIPT_MISMATCH",
            "synthetic harness receipt must bind the exact fixture payload",
        )
    synthetic_audit_ids = (
        (manifest.artifact_fetch_observation_id, "synthetic_fetch_"),
        (manifest.release_status_observation_id, "synthetic_status_"),
        (manifest.release_admission_observation_id, "synthetic_admission_"),
    )
    if any(not value.startswith(prefix) for value, prefix in synthetic_audit_ids):
        raise Stage2BResearchValidationError(
            "MANIFEST_SYNTHETIC_AUDIT_IDENTITY_INVALID",
            "synthetic harness observations must remain in their synthetic namespaces",
        )
    if not (
        manifest.input_path == "synthetic_validation"
        and manifest.synthetic
        and manifest.validation_only
        and manifest.not_a_published_release
        and manifest.not_strategy_evidence
        and not manifest.authorizes_positions
        and not manifest.authorizes_orders
        and manifest.run_mode is RunMode.RESEARCH
    ):
        raise Stage2BResearchValidationError(
            "MANIFEST_AUTHORITY_BOUNDARY_INVALID",
            "Manifest crossed the approved research-validation boundary",
        )
    if (
        fixture_capability.registry_snapshot_hash.value
        != INDUSTRIAL_EVENT_FIXTURE_REGISTRY_SNAPSHOT_SHA256
    ):
        raise Stage2BResearchValidationError(
            "FIXTURE_REGISTRY_SNAPSHOT_UNTRUSTED",
            "fixture capability was not issued by the pinned registry snapshot",
        )
    verified = strategy_input.verified_knowledge_input
    try:
        fixture_capability.require_exact(
            strategy_id=manifest.strategy_id,
            case_id=case.case_id,
            fixture_id=strategy_input.fixture_id,
            fixture_version=strategy_input.fixture_version,
            dataset_release_id=verified.strategy_input_ref.dataset_release_id,
            input_id=verified.input_id,
            input_envelope_hash=_digest(strategy_input),
            verified_input_hash=strategy_input.fixture_payload_hash,
            strategy_case_input_hash=case.semantic_input_hash(),
            strategy_case_envelope_hash=_digest(case),
        )
    except SyntheticFixtureAuthorizationError as exc:
        raise Stage2BResearchValidationError(
            exc.code,
            "fixture capability does not authorize this exact Stage 2B case",
        ) from exc


def _validate_decision(
    case: IndustrialEventCase,
    decision: IndustrialEventDecision,
    *,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
) -> None:
    if decision.case_id != case.case_id or decision.decision_at != case.decision_at:
        raise Stage2BResearchValidationError(
            "DECISION_CASE_IDENTITY_MISMATCH",
            "strategy decision does not bind the exact case and injected clock",
        )
    if decision.strategy_case_envelope_hash != _digest(case):
        raise Stage2BResearchValidationError(
            "DECISION_CASE_HASH_MISMATCH",
            "strategy decision does not bind the complete IndustrialEventCase",
        )
    if (
        decision.rule_bundle_hash != rule_document.bundle_hash()
        or decision.approval_id != approval_capability.approval_id
    ):
        raise Stage2BResearchValidationError(
            "DECISION_RULE_IDENTITY_MISMATCH",
            "strategy decision does not bind the exact approved rule identity",
        )
    if not (
        decision.synthetic
        and decision.validation_only
        and decision.run_mode is RunMode.RESEARCH
        and decision.position_state is PositionState.FLAT
        and decision.target_weight == "0"
        and decision.approved_weight == "0"
        and decision.actual_weight == "0"
        and decision.approver is None
        and not decision.authorizes_positions
        and not decision.authorizes_orders
    ):
        raise Stage2BResearchValidationError(
            "DECISION_AUTHORITY_BOUNDARY_INVALID",
            "strategy decision crossed the zero-authority validation boundary",
        )
    if any(gate.evaluated_at != case.decision_at for gate in decision.gate_results):
        raise Stage2BResearchValidationError(
            "DECISION_GATE_CLOCK_MISMATCH",
            "every evaluated or short-circuited Gate must use the injected decision clock",
        )
    known_fact_ids = {fact.fact_id for fact in case.strategy_input.verified_knowledge_input.facts}
    referenced = set(decision.supporting_fact_ids) | set(decision.conflicting_fact_ids)
    if not referenced.issubset(known_fact_ids):
        raise Stage2BResearchValidationError(
            "DECISION_FACT_REFERENCE_UNKNOWN",
            "Decision references Facts outside its exact VerifiedKnowledgeInput",
        )


def _complete_payload(case: IndustrialEventCase) -> Mapping[str, JsonValue]:
    matches = tuple(
        fact
        for fact in case.strategy_input.verified_knowledge_input.facts
        if fact.predicate == COMPLETE_CASE_PAYLOAD_PREDICATE
    )
    if len(matches) != 1 or not isinstance(matches[0].value, Mapping):
        raise Stage2BResearchValidationError(
            "COMPLETE_CASE_PAYLOAD_UNAVAILABLE",
            "one validated complete-case payload Fact is required for audit assembly",
        )
    payload = matches[0].value
    typed = payload.get("strategy_case_payload")
    raw = payload.get("raw_semantic_source")
    if (
        not isinstance(typed, Mapping)
        or canonical_sha256(typed) != case.semantic_input_hash().value
        or not isinstance(raw, Mapping)
    ):
        raise Stage2BResearchValidationError(
            "COMPLETE_CASE_PAYLOAD_MISMATCH",
            "complete-case payload does not bind the typed case and raw semantic source",
        )
    return payload


def _collect_classified_records(
    value: Any,
    *,
    path: str = "$.raw_semantic_source",
    parent_classification: str | None = None,
) -> tuple[tuple[str, str, JsonValue], ...]:
    records: list[tuple[str, str, JsonValue]] = []
    if isinstance(value, Mapping):
        raw_classification = value.get("classification")
        current_parent = parent_classification
        if "classification" in value:
            if (
                not isinstance(raw_classification, str)
                or raw_classification not in _AUDIT_CLASSIFICATIONS
            ):
                raise Stage2BResearchValidationError(
                    "AUDIT_CLASSIFICATION_INVALID",
                    f"{path}.classification is outside Fact/Assumption/Derived/Judgment",
                )
            if parent_classification is not None:
                raise Stage2BResearchValidationError(
                    "AUDIT_CLASSIFICATION_NESTED",
                    f"{path} nests {raw_classification} inside {parent_classification}",
                )
            projected = to_json_value(value)
            records.append((path, raw_classification, projected))
            current_parent = raw_classification
        for key in sorted(value):
            records.extend(
                _collect_classified_records(
                    value[key],
                    path=f"{path}.{key}",
                    parent_classification=current_parent,
                )
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            records.extend(
                _collect_classified_records(
                    item,
                    path=f"{path}[{index}]",
                    parent_classification=parent_classification,
                )
            )
    return tuple(records)


def _classified_records(
    value: Any,
    *,
    classification: str,
) -> tuple[JsonValue, ...]:
    return tuple(
        {"field_path": path, "value": projected}
        for path, record_classification, projected in _collect_classified_records(value)
        if record_classification == classification
    )


def _validate_audit_payload(case: IndustrialEventCase) -> Mapping[str, JsonValue]:
    """Validate F/A/D/J separation and complete assumption audit metadata."""

    payload = _complete_payload(case)
    raw = payload["raw_semantic_source"]
    records = _collect_classified_records(raw)
    assumption_records = tuple(
        (path, projected)
        for path, classification, projected in records
        if classification == "Assumption"
    )
    if not assumption_records:
        raise Stage2BResearchValidationError(
            "ASSUMPTION_AUDIT_METADATA_MISSING",
            "Stage 2B audit assembly requires explicit Assumption records",
        )

    assumption_ids: set[str] = set()
    for path, projected in assumption_records:
        if not isinstance(projected, Mapping):
            raise Stage2BResearchValidationError(
                "ASSUMPTION_AUDIT_METADATA_INVALID",
                f"{path} must project to an audit object",
            )
        for field_name in _ASSUMPTION_AUDIT_FIELDS:
            value = projected.get(field_name)
            if not isinstance(value, str) or not value.strip():
                raise Stage2BResearchValidationError(
                    "ASSUMPTION_AUDIT_METADATA_INCOMPLETE",
                    f"{path}.{field_name} must be an explicit non-empty string",
                )
        assumption_id = projected["assumption_id"]
        if not isinstance(assumption_id, str) or _ID_RE.fullmatch(assumption_id) is None:
            raise Stage2BResearchValidationError(
                "ASSUMPTION_ID_INVALID",
                f"{path}.assumption_id must be a valid audit ID",
            )
        if assumption_id in assumption_ids:
            raise Stage2BResearchValidationError(
                "ASSUMPTION_ID_DUPLICATE",
                f"duplicate assumption_id {assumption_id!r}",
            )
        assumption_ids.add(assumption_id)

        as_of = projected["as_of"]
        if not isinstance(as_of, str) or _UTC_AUDIT_TIMESTAMP_RE.fullmatch(as_of) is None:
            raise Stage2BResearchValidationError(
                "ASSUMPTION_AS_OF_INVALID",
                f"{path}.as_of must be a canonical UTC timestamp",
            )
        try:
            parsed_as_of = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
        except ValueError as exc:
            raise Stage2BResearchValidationError(
                "ASSUMPTION_AS_OF_INVALID",
                f"{path}.as_of must be a valid calendar timestamp",
            ) from exc
        knowledge_cutoff = (
            case.strategy_input.verified_knowledge_input.strategy_input_ref.knowledge_cutoff
        )
        if parsed_as_of > knowledge_cutoff:
            raise Stage2BResearchValidationError(
                "ASSUMPTION_AS_OF_AFTER_KNOWLEDGE_CUTOFF",
                f"{path}.as_of must not be later than the pinned knowledge cutoff",
            )
    return payload


def _evidence_for_facts(case: IndustrialEventCase, fact_ids: tuple[str, ...]) -> tuple[str, ...]:
    wanted = set(fact_ids)
    evidence = {
        evidence_id
        for fact in case.strategy_input.verified_knowledge_input.facts
        if fact.fact_id in wanted
        for evidence_id in fact.evidence_ids
    }
    return tuple(sorted(evidence))


def _binding_fact_ids(case: IndustrialEventCase) -> tuple[str, ...]:
    return tuple(
        sorted(
            fact.fact_id
            for fact in case.strategy_input.verified_knowledge_input.facts
            if fact.predicate in {COMPLETE_CASE_PAYLOAD_PREDICATE, CASE_MATERIAL_HASH_PREDICATE}
        )
    )


def _block_reasons(decision: IndustrialEventDecision) -> tuple[str, ...]:
    reasons = {"stage2b_synthetic_research_validation_only"}
    for gate in decision.gate_results:
        if (
            gate.evaluation_state is GateEvaluationState.EVALUATED
            and gate.outcome is not GateOutcome.PASS
        ):
            reasons.update(gate.reason_codes)
    return tuple(sorted(reasons))


def _make_decision_record(
    *,
    decision_id: str,
    manifest: StrategyRunManifest,
    case: IndustrialEventCase,
    decision: IndustrialEventDecision,
    payload: Mapping[str, JsonValue],
    replay_hash: HashDigest,
    approval_capability: ApprovedRuleCapability,
    fixture_capability: ApprovedSyntheticFixtureCapability,
) -> DecisionRecord:
    raw = payload["raw_semantic_source"]
    assumptions = _classified_records(raw, classification="Assumption")
    classified_derived = _classified_records(raw, classification="Derived")
    classified_judgments = _classified_records(raw, classification="Judgment")
    judgments: tuple[JsonValue, ...] = (
        *classified_judgments,
        {
            "classification": "Judgment",
            "judgment_id": "stage2b_rule_bound_classification",
            "evaluated_at": decision.decision_at,
            "event_state": decision.event_state.value,
            "decision_state": decision.decision_state.value,
            "expectation_class": (
                decision.expectation_class.value if decision.expectation_class is not None else None
            ),
            "gate_outcomes": tuple(
                {
                    "gate_id": gate.gate_id.value,
                    "evaluation_state": gate.evaluation_state.value,
                    "outcome": gate.outcome.value if gate.outcome is not None else None,
                    "rule_id": gate.rule_id,
                    "rule_version": gate.rule_version,
                    "reason_codes": gate.reason_codes,
                    "short_circuit_reason_code": gate.short_circuit_reason_code,
                }
                for gate in decision.gate_results
            ),
        },
    )
    profit_bridge = (
        decision.profit_bridge.to_json_value() if decision.profit_bridge is not None else None
    )
    scenario_valuation = (
        decision.scenario_valuation.to_json_value()
        if decision.scenario_valuation is not None
        else None
    )
    valuation_input = case.valuation
    supporting_evidence = _evidence_for_facts(case, decision.supporting_fact_ids)
    conflicting_evidence = _evidence_for_facts(case, decision.conflicting_fact_ids)
    facts_used = tuple(
        sorted(
            set(decision.supporting_fact_ids)
            | set(decision.conflicting_fact_ids)
            | set(_binding_fact_ids(case))
        )
    )
    derived_values: Mapping[str, JsonValue] = {
        "classified_inputs": classified_derived,
        "input_envelope_hash": _digest(case.strategy_input).to_json_value(),
        "verified_input_hash": case.strategy_input.fixture_payload_hash.to_json_value(),
        "strategy_case_input_hash": case.semantic_input_hash().to_json_value(),
        "strategy_case_envelope_hash": decision.strategy_case_envelope_hash.to_json_value(),
        "synthetic_fixture_registration_id": fixture_capability.registration_id,
        "synthetic_fixture_registration_hash": (
            fixture_capability.registration_hash.to_json_value()
        ),
        "synthetic_fixture_registry_snapshot_hash": (
            fixture_capability.registry_snapshot_hash.to_json_value()
        ),
        "profit_bridge": profit_bridge,
        "scenario_valuation": scenario_valuation,
    }
    scenarios: tuple[JsonValue, ...] = (
        (
            {
                "scenario_id": "stage2b_base_and_downside_valuation",
                "valuation": scenario_valuation,
            },
        )
        if scenario_valuation is not None
        else ()
    )
    first_executable_at = (
        valuation_input.first_executable_at if valuation_input is not None else None
    )
    first_executable_price = (
        valuation_input.first_executable_price if valuation_input is not None else None
    )
    estimated_cost_rate = (
        valuation_input.explicit_cost_rate if valuation_input is not None else None
    )
    estimated_slippage_rate = (
        valuation_input.explicit_slippage_rate if valuation_input is not None else None
    )
    next_verification_days = (
        valuation_input.next_verification_trading_days if valuation_input is not None else None
    )
    return DecisionRecord(
        decision_record_schema_version=DECISION_RECORD_SCHEMA_VERSION,
        decision_id=decision_id,
        run_id=manifest.run_id,
        decision_at=decision.decision_at,
        strategy_input_ref=manifest.strategy_input_ref,
        strategy_version=manifest.strategy_version,
        rule_bundle_id=manifest.rule_bundle_id,
        rule_bundle_version=manifest.rule_bundle_version,
        rule_bundle_hash=manifest.rule_bundle_hash,
        rule_status=manifest.rule_status,
        rule_approval_id=approval_capability.approval_id,
        rule_approval_record_hash=approval_capability.approval_record_hash,
        rule_approval_scope=approval_capability.approval_scope.value,
        run_mode=RunMode.RESEARCH,
        synthetic=True,
        validation_only=True,
        not_a_published_release=True,
        not_strategy_evidence=True,
        authorizes_positions=False,
        authorizes_orders=False,
        event_state=decision.event_state,
        decision_state=decision.decision_state,
        position_state=PositionState.FLAT,
        replay_hash=replay_hash,
        supporting_fact_ids=decision.supporting_fact_ids,
        conflicting_fact_ids=decision.conflicting_fact_ids,
        supporting_evidence_ids=supporting_evidence,
        conflicting_evidence_ids=conflicting_evidence,
        gate_results=decision.gate_results,
        facts_used=facts_used,
        assumptions=assumptions,
        judgments=judgments,
        derived_values=derived_values,
        profit_bridge=profit_bridge,
        scenarios=scenarios,
        expectation_class=decision.expectation_class,
        first_executable_at=first_executable_at,
        first_executable_price=first_executable_price,
        execution_window={
            "mode": "synthetic_research_validation_only",
            "orders_forbidden": True,
        },
        price_method=(
            "synthetic_explicit_first_executable_price"
            if first_executable_price is not None
            else None
        ),
        estimated_cost_rate=estimated_cost_rate,
        estimated_slippage_rate=estimated_slippage_rate,
        market_regime=None,
        risk_cluster_ids=(),
        planned_account_risk="0",
        risk_limits={
            "authorizes_positions": False,
            "authorizes_orders": False,
            "validation_only": True,
        },
        target_weight="0",
        approved_weight="0",
        actual_weight="0",
        falsifiers=decision.falsifiers,
        next_verification={
            "trading_days": next_verification_days,
            "falsifiers": decision.falsifiers,
        },
        block_reasons=_block_reasons(decision),
        approver=None,
        non_trade_declaration=STAGE2B_NON_TRADE_DECLARATION,
        supersedes=None,
    )


def run_stage2b_research_validation(
    *,
    decision_id: str,
    manifest: StrategyRunManifest,
    case: IndustrialEventCase,
    rule_document: RuleBundleDocument,
    approval_capability: ApprovedRuleCapability,
    fixture_capability: ApprovedSyntheticFixtureCapability,
) -> Stage2BResearchValidationResult:
    """Run the one authorized Stage 2B synthetic strategy path exactly once."""

    if not isinstance(manifest, StrategyRunManifest):
        raise TypeError("manifest must be a StrategyRunManifest")
    if not isinstance(case, IndustrialEventCase):
        raise TypeError("case must be an IndustrialEventCase")
    if not isinstance(rule_document, RuleBundleDocument):
        raise TypeError("rule_document must be a RuleBundleDocument")
    if not isinstance(approval_capability, ApprovedRuleCapability):
        raise TypeError("approval_capability must be an ApprovedRuleCapability")
    if not isinstance(fixture_capability, ApprovedSyntheticFixtureCapability):
        raise TypeError("fixture_capability must be an ApprovedSyntheticFixtureCapability")
    _validate_decision_id(decision_id)
    _validate_approved_rules(rule_document, approval_capability)
    payload = _validate_audit_payload(case)
    _validate_manifest(
        manifest,
        case,
        rule_document=rule_document,
        approval_capability=approval_capability,
        fixture_capability=fixture_capability,
    )
    decision = evaluate_industrial_event(
        case,
        rule_document=rule_document,
        approval_capability=approval_capability,
        fixture_capability=fixture_capability,
    )
    _validate_decision(
        case,
        decision,
        rule_document=rule_document,
        approval_capability=approval_capability,
    )
    replay_envelope = ReplayEnvelope.from_synthetic_validation(
        manifest=manifest,
        strategy_input=case.strategy_input,
        rule_bundle=rule_document,
        approval_capability=approval_capability,
        fixture_capability=fixture_capability,
        strategy_input_envelope=case,
        strategy_case_input_hash=case.semantic_input_hash(),
        evaluated_at=decision.decision_at,
        semantic_output=decision.to_json_value(),
    )
    replay_hash = compute_replay_hash(replay_envelope)
    decision_record = _make_decision_record(
        decision_id=decision_id,
        manifest=manifest,
        case=case,
        decision=decision,
        payload=payload,
        replay_hash=replay_hash,
        approval_capability=approval_capability,
        fixture_capability=fixture_capability,
    )
    return Stage2BResearchValidationResult(
        strategy_decision=decision,
        replay_envelope=replay_envelope,
        decision_record=decision_record,
    )
