from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from invest_system.canonical import CanonicalJsonError
from invest_system.domain.replay import (
    REPLAY_CANONICAL_PROFILE_VERSION,
    REPLAY_ENVELOPE_SCHEMA_VERSION,
    ReplayEnvelope,
    ReplayValidationError,
    compute_replay_hash,
    verify_replay_hash,
)
from invest_system.domain.rule_approval import (
    RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
    ApprovedRuleCapability,
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
)
from invest_system.domain.strategy_input import SyntheticValidationInput
from invest_system.domain.synthetic_fixture import (
    ApprovedSyntheticFixtureCapability,
    SyntheticFixtureRegistration,
    SyntheticFixtureRegistry,
)
from invest_system.models import HashDigest, RuleStatus, StrategyRunManifest, VerifiedKnowledgeInput


def make_hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def prepare_replay_inputs(
    *,
    manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    fixture_id: str = "synthetic_fixture_stage2b_001",
) -> tuple[
    StrategyRunManifest,
    SyntheticValidationInput,
    RuleBundleDocument,
    ApprovedRuleCapability,
    ApprovedSyntheticFixtureCapability,
    HashDigest,
]:
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id=fixture_id,
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    rule_bundle = RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_boundary",
        bundle_version="0.1.0",
        declared_status=RuleStatus.APPROVED,
        rules={"business_semantics": False, "validation_only": True},
    )
    approval = RuleApprovalRecord(
        approval_id="synthetic_stage2b_replay_approval",
        strategy_id=rule_bundle.strategy_id,
        bundle_id=rule_bundle.bundle_id,
        bundle_version=rule_bundle.bundle_version,
        bundle_hash=rule_bundle.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="stage2b_synthetic_replay_test_authorization",
    )
    capability = RuleApprovalRegistry((approval,)).require(rule_bundle)
    case_hash = HashDigest(
        algorithm="sha256",
        value=verified_knowledge_input.canonical_sha256(),
    )
    prepared_manifest = replace(
        manifest,
        rule_bundle_id=rule_bundle.bundle_id,
        rule_bundle_version=rule_bundle.bundle_version,
        rule_bundle_hash=rule_bundle.bundle_hash(),
        rule_status=RuleStatus.APPROVED,
        rule_approval_id=capability.approval_id,
        rule_approval_record_hash=capability.approval_record_hash,
        rule_approval_scope=capability.approval_scope.value,
        input_envelope_hash=HashDigest(
            algorithm="sha256",
            value=synthetic_input.canonical_sha256(),
        ),
        strategy_case_envelope_hash=HashDigest(
            algorithm="sha256",
            value=synthetic_input.canonical_sha256(),
        ),
        strategy_case_input_hash=case_hash,
        synthetic_fixture_id=synthetic_input.fixture_id,
        synthetic_fixture_version=synthetic_input.fixture_version,
        synthetic_fixture_payload_hash=synthetic_input.fixture_payload_hash,
    )
    fixture_registration = SyntheticFixtureRegistration.from_trusted_case(
        registration_id=f"replay_registration_{fixture_id}",
        strategy_id=prepared_manifest.strategy_id,
        case_id="synthetic_replay_case_stage2b_001",
        strategy_input=synthetic_input,
        strategy_case_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
    )
    fixture_registry = SyntheticFixtureRegistry((fixture_registration,))
    fixture_capability = fixture_registry.require_strategy_case(
        strategy_id=prepared_manifest.strategy_id,
        case_id=fixture_registration.case_id,
        strategy_input=synthetic_input,
        strategy_case_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
    )
    return (
        prepared_manifest,
        synthetic_input,
        rule_bundle,
        capability,
        fixture_capability,
        case_hash,
    )


def make_envelope(
    *,
    manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    fixture_id: str = "synthetic_fixture_stage2b_001",
) -> ReplayEnvelope:
    prepared = prepare_replay_inputs(
        manifest=manifest,
        verified_knowledge_input=verified_knowledge_input,
        fixture_id=fixture_id,
    )
    (
        prepared_manifest,
        synthetic_input,
        rule_bundle,
        capability,
        fixture_capability,
        case_hash,
    ) = prepared
    return ReplayEnvelope.from_synthetic_validation(
        manifest=prepared_manifest,
        strategy_input=synthetic_input,
        rule_bundle=rule_bundle,
        approval_capability=capability,
        fixture_capability=fixture_capability,
        strategy_input_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
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
        {"path": {"temporary_path": "D:/tmp/volatile"}},
        {"clock": {"wall_clock": "volatile"}},
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
    with pytest.raises(ReplayValidationError, match="RESERVED_REPLAY_KEY"):
        replace(baseline, semantic_output=semantic_output)  # type: ignore[arg-type]


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


def test_replay_envelope_rejects_non_approved_rule_status(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    baseline = make_envelope(
        manifest=strategy_run_manifest,
        verified_knowledge_input=verified_knowledge_input,
    )

    with pytest.raises(ValueError, match="requires approved rules"):
        replace(baseline, rule_status=RuleStatus.DRAFT)


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
        baseline,
        evaluated_at=baseline.evaluated_at + timedelta(microseconds=1),
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
    manifest, synthetic_input, rule_bundle, capability, fixture_capability, case_hash = (
        prepare_replay_inputs(
            manifest=strategy_run_manifest,
            verified_knowledge_input=verified_knowledge_input,
        )
    )
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=manifest,
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            approval_capability=capability,
            fixture_capability=fixture_capability,
            strategy_input_envelope=synthetic_input,
            strategy_case_input_hash=case_hash,
            evaluated_at=datetime(2026, 7, 30, 8),
            semantic_output={"validation_only": True},
        )


@pytest.mark.parametrize(
    "manifest_change",
    [
        {"strategy_id": "different_strategy"},
        {"rule_bundle_version": "0.1.1"},
        {"rule_bundle_id": "different_bundle"},
    ],
)
def test_replay_builder_rejects_manifest_and_rule_bundle_identity_drift(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
    manifest_change: dict[str, object],
) -> None:
    manifest, synthetic_input, rule_bundle, capability, fixture_capability, case_hash = (
        prepare_replay_inputs(
            manifest=strategy_run_manifest,
            verified_knowledge_input=verified_knowledge_input,
        )
    )

    with pytest.raises(ValueError, match="must match the run Manifest"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=replace(manifest, **manifest_change),  # type: ignore[arg-type]
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            approval_capability=capability,
            fixture_capability=fixture_capability,
            strategy_input_envelope=synthetic_input,
            strategy_case_input_hash=case_hash,
            evaluated_at=manifest.created_at,
            semantic_output={"validation_only": True},
        )


def test_replay_builder_rejects_strategy_input_reference_drift(
    strategy_run_manifest: StrategyRunManifest,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    manifest, synthetic_input, rule_bundle, capability, fixture_capability, case_hash = (
        prepare_replay_inputs(
            manifest=strategy_run_manifest,
            verified_knowledge_input=verified_knowledge_input,
        )
    )
    changed_reference = replace(
        manifest.strategy_input_ref,
        dataset_release_id="synthetic_release_stage2b_other_001",
    )

    with pytest.raises(ValueError, match="strategy input reference must match"):
        ReplayEnvelope.from_synthetic_validation(
            manifest=replace(manifest, strategy_input_ref=changed_reference),
            strategy_input=synthetic_input,
            rule_bundle=rule_bundle,
            approval_capability=capability,
            fixture_capability=fixture_capability,
            strategy_input_envelope=synthetic_input,
            strategy_case_input_hash=case_hash,
            evaluated_at=manifest.created_at,
            semantic_output={"validation_only": True},
        )
