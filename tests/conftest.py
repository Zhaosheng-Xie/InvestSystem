"""Shared Stage 1 synthetic factories.

These fixtures exercise InvestSystem-owned draft representations only.  They
are not KB fixtures, published releases, receipts, or strategy-positive cases.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest

from invest_system import (
    DECISION_RECORD_SCHEMA_VERSION,
    GATE_RESULT_SCHEMA_VERSION,
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
    DecisionRecord,
    DecisionState,
    EventState,
    GateEvaluationState,
    GateId,
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

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_FIXTURE_PATH = (
    REPOSITORY_ROOT
    / "tests"
    / "fixtures"
    / "synthetic"
    / "verified_knowledge_input_v0.1.0-draft.json"
)


def parse_utc(value: str) -> datetime:
    """Parse fixture UTC text; model validation remains authoritative."""

    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def make_hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


@pytest.fixture(scope="session")
def repository_root() -> Path:
    return REPOSITORY_ROOT


@pytest.fixture(scope="session")
def synthetic_fixture_document() -> dict[str, Any]:
    document = json.loads(SYNTHETIC_FIXTURE_PATH.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise TypeError("synthetic fixture root must be an object")
    return cast(dict[str, Any], document)


@pytest.fixture
def strategy_input_ref(synthetic_fixture_document: dict[str, Any]) -> StrategyInputRef:
    raw = synthetic_fixture_document["verified_knowledge_input"]["strategy_input_ref"]
    return StrategyInputRef(
        schema_version=raw["schema_version"],
        dataset_release_id=raw["dataset_release_id"],
        knowledge_cutoff=parse_utc(raw["knowledge_cutoff"]),
        release_manifest_schema_version=raw["release_manifest_schema_version"],
        manifest_hash=HashDigest(**raw["manifest_hash"]),
    )


@pytest.fixture
def verified_knowledge_input(
    synthetic_fixture_document: dict[str, Any],
    strategy_input_ref: StrategyInputRef,
) -> VerifiedKnowledgeInput:
    raw = synthetic_fixture_document["verified_knowledge_input"]
    facts = tuple(
        VerifiedFact(
            fact_id=fact["fact_id"],
            subject_id=fact["subject_id"],
            predicate=fact["predicate"],
            value=fact["value"],
            verified_at=parse_utc(fact["verified_at"]),
            available_at=parse_utc(fact["available_at"]),
            evidence_ids=tuple(fact["evidence_ids"]),
            event_at=parse_utc(fact["event_at"]) if fact["event_at"] else None,
            source_published_at=(
                parse_utc(fact["source_published_at"]) if fact["source_published_at"] else None
            ),
            first_seen_at=(parse_utc(fact["first_seen_at"]) if fact["first_seen_at"] else None),
            metadata=fact["metadata"],
        )
        for fact in raw["facts"]
    )
    return VerifiedKnowledgeInput(
        schema_version=VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
        input_id=raw["input_id"],
        strategy_input_ref=strategy_input_ref,
        facts=facts,
    )


@pytest.fixture
def gate_result() -> GateResult:
    return GateResult(
        schema_version=GATE_RESULT_SCHEMA_VERSION,
        gate_id=GateId.AUTHENTICITY,
        evaluation_state=GateEvaluationState.EVALUATED,
        outcome=GateOutcome.SHADOW_ONLY,
        evaluated_at=parse_utc("2026-07-30T08:00:00.000000Z"),
        rule_id="synthetic_rule_representation_only",
        rule_version="0.1.0-draft",
        supporting_fact_ids=("synthetic_fact_001",),
        reason_codes=("stage1_representation_only",),
        details={"synthetic": True, "business_semantics": False},
    )


@pytest.fixture
def strategy_run_manifest(strategy_input_ref: StrategyInputRef) -> StrategyRunManifest:
    return StrategyRunManifest(
        strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        run_id="synthetic_run_stage1_001",
        created_at=parse_utc("2026-07-30T08:00:00.000000Z"),
        strategy_id="industrial_bottleneck_event",
        strategy_version="0.1.0-draft",
        code_commit="0123456789abcdef0123456789abcdef01234567",
        rule_bundle_id="synthetic_stage1_rule_bundle",
        rule_bundle_version="0.1.0-draft",
        rule_bundle_hash=make_hash("f"),
        rule_status=RuleStatus.DRAFT,
        rule_approval_id=None,
        rule_approval_record_hash=None,
        rule_approval_scope=None,
        config_hash=make_hash("b"),
        strategy_input_ref=strategy_input_ref,
        input_envelope_hash=make_hash("7"),
        strategy_case_envelope_hash=make_hash("6"),
        strategy_case_input_hash=make_hash("8"),
        synthetic_fixture_id="synthetic_fixture_stage1_001",
        synthetic_fixture_version="0.1.0-draft",
        synthetic_fixture_payload_hash=make_hash("9"),
        input_path="synthetic_validation",
        synthetic=True,
        validation_only=True,
        not_a_published_release=True,
        not_strategy_evidence=True,
        authorizes_positions=False,
        authorizes_orders=False,
        artifact_consumption_receipt_hash=make_hash("c"),
        artifact_fetch_observation_id="synthetic_fetch_observation_stage1_001",
        release_status_observation_id="synthetic_status_observation_stage1_001",
        release_admission_observation_id="synthetic_admission_observation_stage1_001",
        random_seed=0,
        run_mode=RunMode.RESEARCH,
        runtime_environment_lock_hash=make_hash("d"),
    )


@pytest.fixture
def decision_record(
    strategy_input_ref: StrategyInputRef,
    gate_result: GateResult,
) -> DecisionRecord:
    return DecisionRecord(
        decision_record_schema_version=DECISION_RECORD_SCHEMA_VERSION,
        decision_id="synthetic_decision_stage1_001",
        run_id="synthetic_run_stage1_001",
        decision_at=parse_utc("2026-07-30T08:00:00.000000Z"),
        strategy_input_ref=strategy_input_ref,
        strategy_version="0.1.0-draft",
        rule_bundle_id="synthetic_stage1_rule_bundle",
        rule_bundle_version="0.1.0-draft",
        rule_bundle_hash=make_hash("f"),
        rule_status=RuleStatus.DRAFT,
        rule_approval_id=None,
        rule_approval_record_hash=None,
        rule_approval_scope=None,
        run_mode=RunMode.RESEARCH,
        synthetic=True,
        validation_only=True,
        not_a_published_release=True,
        not_strategy_evidence=True,
        authorizes_positions=False,
        authorizes_orders=False,
        event_state=EventState.E0,
        decision_state=DecisionState.SHADOW_ONLY,
        position_state=PositionState.FLAT,
        replay_hash=make_hash("e"),
        supporting_fact_ids=("synthetic_fact_001",),
        gate_results=(gate_result,),
        assumptions=({"synthetic": True},),
        target_weight="0",
        approved_weight=None,
        actual_weight=None,
        block_reasons=("stage1_representation_only",),
        non_trade_declaration="synthetic validation representation only",
    )
