from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from invest_system.canonical import CanonicalJsonError
from invest_system.domain.replay import (
    REPLAY_CANONICAL_PROFILE_VERSION,
    REPLAY_ENVELOPE_SCHEMA_VERSION,
    ReplayEnvelope,
    compute_replay_hash,
    verify_replay_hash,
)
from invest_system.domain.rule_approval import (
    RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
    RuleBundleDocument,
)
from invest_system.domain.strategy_input import SyntheticValidationInput
from invest_system.models import (
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
    VerifiedKnowledgeInput,
)


def make_hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def make_envelope(
    *,
    manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    fixture_id: str = "synthetic_fixture_stage2b_001",
) -> ReplayEnvelope:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id=fixture_id,
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version=manifest.rule_bundle_version,
        declared_status=manifest.rule_status,
        rules={"business_semantics": False, "validation_only": True},
    )
    return ReplayEnvelope.from_synthetic_validation(
        manifest=manifest,
        strategy_input=synthetic_input,
        rule_bundle=rule_bundle,
        evaluated_at=datetime(2026, 7, 30, 8, tzinfo=UTC),
        semantic_output={
            "artifact_class": "synthetic_validation",
            "business_semantics": False,
            "validation_only": True,
        },
    )


def test_replay_envelope_hashes_an_explicit_self_excluding_projection(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    envelope = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )
    replay_hash = compute_replay_hash(envelope)

    assert envelope.schema_version == REPLAY_ENVELOPE_SCHEMA_VERSION
    assert envelope.canonical_profile_version == REPLAY_CANONICAL_PROFILE_VERSION
    assert "replay_hash" not in envelope.to_json_value()
    assert envelope.input_envelope_hash.value != envelope.verified_input_hash.value
    assert replay_hash == HashDigest(algorithm="sha256", value=envelope.canonical_sha256())
    assert verify_replay_hash(envelope, replay_hash) is True
    assert verify_replay_hash(envelope, make_hash("0")) is False


def test_run_and_transport_audit_identities_do_not_change_replay_hash(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    first = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )
    audit_only_variant = replace(
        strategy_run_manifest,
        run_id="synthetic_run_stage2b_retry_999",
        created_at=strategy_run_manifest.created_at + timedelta(minutes=1),
        artifact_fetch_observation_id="synthetic_fetch_observation_stage2b_999",
        release_status_observation_id="synthetic_status_observation_stage2b_999",
        release_admission_observation_id="synthetic_admission_observation_stage2b_999",
    )
    second = make_envelope(
        manifest=audit_only_variant,
        verified_knowledge_input=verified_knowledge_input,
    )

    assert first.to_canonical_bytes() == second.to_canonical_bytes()
    assert compute_replay_hash(first) == compute_replay_hash(second)


@pytest.mark.parametrize(
    "semantic_output",
    [
        {"replay_hash": {"algorithm": "sha256", "value": "0" * 64}},
        {"nested": {"run_id": "volatile_run"}},
        {"items": [{"release_status_observation_id": "volatile_status"}]},
        {"transport": {"endpoint": "https://provider.invalid"}},
    ],
)
def test_replay_envelope_rejects_self_and_volatile_audit_keys(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    semantic_output: dict[str, object],
) -> None:
    baseline = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )
    with pytest.raises(ValueError, match="reserved replay key"):
        replace(
            baseline,
            semantic_output=semantic_output,  # type: ignore[arg-type]
        )


def test_replay_envelope_rejects_float_semantics(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    baseline = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )
    with pytest.raises(CanonicalJsonError, match="floating-point values are forbidden"):
        replace(
            baseline,
            semantic_output={"implicit_binary_float": 0.1},  # type: ignore[dict-item]
        )


def test_replay_hash_changes_when_a_deterministic_input_changes(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    baseline = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )
    changed_rule = replace(baseline, rule_bundle_hash=make_hash("8"))
    changed_seed = replace(baseline, random_seed=baseline.random_seed + 1)
    changed_clock = replace(
        baseline, evaluated_at=baseline.evaluated_at + timedelta(microseconds=1)
    )
    changed_output = replace(
        baseline,
        semantic_output={"artifact_class": "synthetic_validation", "validation_only": False},
    )
    changed_input_envelope = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
        fixture_id="synthetic_fixture_stage2b_002",
    )

    baseline_hash = compute_replay_hash(baseline)
    assert compute_replay_hash(changed_rule) != baseline_hash
    assert compute_replay_hash(changed_seed) != baseline_hash
    assert compute_replay_hash(changed_clock) != baseline_hash
    assert compute_replay_hash(changed_output) != baseline_hash
    assert compute_replay_hash(changed_input_envelope) != baseline_hash


def test_replay_envelope_requires_utc_evaluation_clock(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=strategy_run_manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version=strategy_run_manifest.rule_bundle_version,
        declared_status=strategy_run_manifest.rule_status,
        rules={"business_semantics": False},
    )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=strategy_run_manifest,
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            evaluated_at=datetime(2026, 7, 30, 8),
            semantic_output={"validation_only": True},
        )


@pytest.mark.parametrize(
    "manifest_change",
    [
        {"strategy_id": "different_strategy"},
        {"rule_bundle_version": "0.1.1"},
        {"rule_status": RuleStatus.HYPOTHESIS},
    ],
)
def test_replay_builder_rejects_manifest_and_rule_bundle_identity_drift(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    manifest_change: dict[str, object],
) -> None:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=strategy_run_manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version=strategy_run_manifest.rule_bundle_version,
        declared_status=strategy_run_manifest.rule_status,
        rules={"business_semantics": False},
    )

    with pytest.raises(ValueError, match="must match the run Manifest"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=replace(strategy_run_manifest, **manifest_change),  # type: ignore[arg-type]
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            evaluated_at=strategy_run_manifest.created_at,
            semantic_output={"validation_only": True},
        )


def test_synthetic_replay_builder_rejects_non_research_run_modes(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=strategy_run_manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version=strategy_run_manifest.rule_bundle_version,
        declared_status=strategy_run_manifest.rule_status,
        rules={"business_semantics": False},
    )

    with pytest.raises(ValueError, match="requires research run_mode"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=replace(strategy_run_manifest, run_mode=RunMode.SHADOW),
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            evaluated_at=strategy_run_manifest.created_at,
            semantic_output={"validation_only": True},
        )


def test_replay_builder_rejects_strategy_input_reference_drift(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=strategy_run_manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version=strategy_run_manifest.rule_bundle_version,
        declared_status=strategy_run_manifest.rule_status,
        rules={"business_semantics": False},
    )
    changed_reference = replace(
        strategy_run_manifest.strategy_input_ref,
        dataset_release_id="synthetic_release_stage2b_other_001",
    )

    with pytest.raises(ValueError, match="strategy input reference must match"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=replace(strategy_run_manifest, strategy_input_ref=changed_reference),
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            evaluated_at=strategy_run_manifest.created_at,
            semantic_output={"validation_only": True},
        )
