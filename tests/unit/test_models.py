from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from invest_system import (
    CanonicalJsonError,
    DecisionRecord,
    DecisionState,
    GateEvaluationState,
    GateOutcome,
    GateResult,
    HashDigest,
    PositionState,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
    VerifiedFact,
    VerifiedKnowledgeInput,
)


@pytest.mark.parametrize(
    ("algorithm", "value"),
    [
        ("SHA256", "a" * 64),
        ("sha512", "a" * 64),
        ("sha256", "A" * 64),
        ("sha256", "a" * 63),
        ("sha256", "g" * 64),
    ],
)
def test_hash_digest_accepts_only_structured_lowercase_sha256(
    algorithm: str,
    value: str,
) -> None:
    with pytest.raises(ValueError):
        HashDigest(algorithm=algorithm, value=value)


@pytest.mark.parametrize("release_id", ["latest", "LATEST", "Latest", "", "../release", "x/y"])
def test_strategy_input_ref_rejects_non_exact_release_identifiers(
    strategy_input_ref: StrategyInputRef,
    release_id: str,
) -> None:
    with pytest.raises(ValueError):
        StrategyInputRef(
            schema_version=strategy_input_ref.schema_version,
            dataset_release_id=release_id,
            knowledge_cutoff=strategy_input_ref.knowledge_cutoff,
            release_manifest_schema_version=(strategy_input_ref.release_manifest_schema_version),
            manifest_hash=strategy_input_ref.manifest_hash,
        )


def test_strategy_input_ref_has_exact_five_field_shape(
    strategy_input_ref: StrategyInputRef,
) -> None:
    assert set(strategy_input_ref.to_json_value()) == {
        "schema_version",
        "dataset_release_id",
        "knowledge_cutoff",
        "release_manifest_schema_version",
        "manifest_hash",
    }
    assert isinstance(strategy_input_ref.to_json_value()["manifest_hash"], dict)


def test_verified_input_rejects_future_visible_fact(
    strategy_input_ref: StrategyInputRef,
) -> None:
    future = strategy_input_ref.knowledge_cutoff + timedelta(microseconds=1)
    fact = VerifiedFact(
        fact_id="synthetic_future_fact",
        subject_id="synthetic_company_001",
        predicate="synthetic_future_marker",
        value={"synthetic": True},
        verified_at=future,
        available_at=future,
    )

    with pytest.raises(ValueError, match="available_at must be <= knowledge_cutoff"):
        VerifiedKnowledgeInput(
            schema_version="0.1.0-draft",
            input_id="synthetic_future_input",
            strategy_input_ref=strategy_input_ref,
            facts=(fact,),
        )


def test_verified_fact_rejects_float_in_value_and_metadata() -> None:
    timestamp = datetime(2026, 7, 30, 8, tzinfo=UTC)
    common: dict[str, Any] = {
        "fact_id": "synthetic_fact_float",
        "subject_id": "synthetic_company_001",
        "predicate": "synthetic_float_marker",
        "verified_at": timestamp,
        "available_at": timestamp,
    }

    with pytest.raises(CanonicalJsonError):
        VerifiedFact(value={"nested": [0.1]}, metadata={}, **common)  # type: ignore[dict-item]
    with pytest.raises(CanonicalJsonError):
        VerifiedFact(value=None, metadata={"nested": [0.1]}, **common)  # type: ignore[dict-item]


def test_models_are_immutable_and_deep_frozen(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    fact = verified_knowledge_input.facts[0]
    original = fact.to_canonical_bytes()

    with pytest.raises(FrozenInstanceError):
        fact.fact_id = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        fact.metadata["changed"] = True  # type: ignore[index]

    assert fact.to_canonical_bytes() == original


def test_duplicate_fact_and_evidence_ids_are_rejected(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    fact = verified_knowledge_input.facts[0]
    with pytest.raises(ValueError, match="duplicate fact_id"):
        VerifiedKnowledgeInput(
            schema_version=verified_knowledge_input.schema_version,
            input_id="synthetic_duplicate_input",
            strategy_input_ref=verified_knowledge_input.strategy_input_ref,
            facts=(fact, fact),
        )

    with pytest.raises(ValueError, match="must not contain duplicate IDs"):
        VerifiedFact(
            fact_id="synthetic_duplicate_evidence",
            subject_id="synthetic_company_001",
            predicate="synthetic_duplicate_marker",
            value=None,
            verified_at=fact.verified_at,
            available_at=fact.available_at,
            evidence_ids=("synthetic_evidence_001", "synthetic_evidence_001"),
        )


def test_manifest_is_deterministic_for_fixed_inputs(
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    assert strategy_run_manifest.to_canonical_bytes() == (
        strategy_run_manifest.to_canonical_bytes()
    )
    assert strategy_run_manifest.canonical_sha256() == (strategy_run_manifest.canonical_sha256())


def test_gate_result_distinguishes_evaluated_from_short_circuited(
    gate_result: GateResult,
) -> None:
    skipped = replace(
        gate_result,
        evaluation_state=GateEvaluationState.NOT_EVALUATED,
        outcome=None,
        short_circuit_reason_code="prior_gate_rejected",
    )

    assert skipped.outcome is None
    assert skipped.short_circuit_reason_code == "prior_gate_rejected"

    with pytest.raises(ValueError, match="evaluated gates require an outcome"):
        replace(gate_result, outcome=None)
    with pytest.raises(ValueError, match="must not have a short_circuit"):
        replace(gate_result, short_circuit_reason_code="not_applicable")
    with pytest.raises(ValueError, match="require outcome=None"):
        replace(
            gate_result,
            evaluation_state=GateEvaluationState.NOT_EVALUATED,
            outcome=GateOutcome.REJECT,
            short_circuit_reason_code="prior_gate_rejected",
        )
    with pytest.raises(ValueError, match="require a short_circuit"):
        replace(
            gate_result,
            evaluation_state=GateEvaluationState.NOT_EVALUATED,
            outcome=None,
        )


def test_manifest_requires_full_commit_and_pit_cutoff(
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    for invalid_commit in ("a" * 7, "a" * 39, "a" * 41, "a" * 63):
        with pytest.raises(ValueError, match="full 40- or 64-character"):
            replace(strategy_run_manifest, code_commit=invalid_commit)

    assert replace(strategy_run_manifest, code_commit="a" * 40).code_commit == "a" * 40
    assert replace(strategy_run_manifest, code_commit="a" * 64).code_commit == "a" * 64

    future_ref = replace(
        strategy_run_manifest.strategy_input_ref,
        knowledge_cutoff=strategy_run_manifest.created_at + timedelta(microseconds=1),
    )
    with pytest.raises(ValueError, match="knowledge_cutoff must be <= created_at"):
        replace(strategy_run_manifest, strategy_input_ref=future_ref)


def test_models_enforce_unapproved_rule_maturity_at_construction(
    strategy_run_manifest: StrategyRunManifest,
    decision_record: DecisionRecord,
) -> None:
    for run_mode in (RunMode.BACKTEST, RunMode.PAPER):
        with pytest.raises(ValueError, match="requires research or shadow"):
            replace(strategy_run_manifest, run_mode=run_mode, validation_only=False)

    assert (
        replace(
            strategy_run_manifest,
            run_mode=RunMode.SHADOW,
            validation_only=False,
        ).run_mode
        is RunMode.SHADOW
    )
    assert (
        replace(
            strategy_run_manifest,
            rule_status=RuleStatus.APPROVED,
            rule_approval_id="future_manifest_approval",
            rule_approval_record_hash=HashDigest(algorithm="sha256", value="7" * 64),
            rule_approval_scope="future_manifest_test_scope",
            run_mode=RunMode.PAPER,
            validation_only=False,
        ).run_mode
        is RunMode.PAPER
    )

    invalid_decisions = (
        {"decision_state": DecisionState.TRADE_READY},
        {"position_state": PositionState.STARTER},
        {"target_weight": "0.01"},
        {"approved_weight": "0.01"},
        {"actual_weight": "0.01"},
        {"approver": "human_approver_001"},
    )
    for changes in invalid_decisions:
        with pytest.raises(ValueError, match="is not approved"):
            replace(decision_record, **changes)

    approved = replace(
        decision_record,
        rule_status=RuleStatus.APPROVED,
        rule_approval_id="future_test_approval",
        rule_approval_record_hash=HashDigest(algorithm="sha256", value="9" * 64),
        rule_approval_scope="future_position_test_scope",
        run_mode=RunMode.PAPER,
        synthetic=False,
        validation_only=False,
        not_a_published_release=False,
        not_strategy_evidence=False,
        authorizes_positions=True,
        decision_state=DecisionState.TRADE_READY,
        position_state=PositionState.STARTER,
        target_weight="0.01",
        approver="human_approver_001",
    )
    assert approved.rule_status is RuleStatus.APPROVED


def test_stage2b_synthetic_approval_never_authorizes_positions_or_orders(
    decision_record: DecisionRecord,
) -> None:
    stage2b = replace(
        decision_record,
        rule_status=RuleStatus.APPROVED,
        rule_approval_id="stage2b_test_approval",
        rule_approval_record_hash=HashDigest(algorithm="sha256", value="8" * 64),
        rule_approval_scope="stage2b_synthetic_validation",
        decision_state=DecisionState.TRADE_READY,
    )
    assert stage2b.position_state is PositionState.FLAT
    assert stage2b.target_weight == "0"
    assert stage2b.approver is None

    violations = (
        {"run_mode": RunMode.SHADOW},
        {"validation_only": False},
        {"synthetic": False},
        {"authorizes_positions": True},
        {"authorizes_orders": True},
        {"position_state": PositionState.STARTER},
        {"target_weight": "0.01"},
        {"approver": "human_approver_001"},
    )
    for changes in violations:
        with pytest.raises(ValueError):
            replace(stage2b, **changes)


def test_contract_collections_reject_unordered_inputs_and_preserve_list_order(
    verified_knowledge_input: VerifiedKnowledgeInput,
    decision_record: DecisionRecord,
) -> None:
    fact = verified_knowledge_input.facts[0]
    ordered = replace(fact, evidence_ids=["evidence_b", "evidence_a"])  # type: ignore[arg-type]
    assert ordered.evidence_ids == ("evidence_b", "evidence_a")

    with pytest.raises(TypeError, match="ordered list or tuple"):
        replace(fact, evidence_ids={"evidence_a", "evidence_b"})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ordered list or tuple"):
        replace(decision_record, falsifiers=frozenset({"first", "second"}))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ordered list or tuple"):
        replace(decision_record, assumptions={"unordered"})  # type: ignore[arg-type]


def test_decision_rejects_future_cutoff_and_float_business_values(
    decision_record: DecisionRecord,
) -> None:
    future_ref = StrategyInputRef(
        schema_version=decision_record.strategy_input_ref.schema_version,
        dataset_release_id="synthetic_release_future_001",
        knowledge_cutoff=decision_record.decision_at + timedelta(microseconds=1),
        release_manifest_schema_version=(
            decision_record.strategy_input_ref.release_manifest_schema_version
        ),
        manifest_hash=decision_record.strategy_input_ref.manifest_hash,
    )
    with pytest.raises(ValueError, match="knowledge_cutoff must be <= decision_at"):
        replace(decision_record, strategy_input_ref=future_ref)

    with pytest.raises(ValueError, match="canonical decimal string"):
        replace(decision_record, target_weight=0.1)  # type: ignore[arg-type]
