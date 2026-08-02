from __future__ import annotations

from dataclasses import replace

import pytest

from invest_system.domain.strategy_input import (
    SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION,
    StrategyInputProvenance,
    SyntheticValidationInput,
)
from invest_system.models import HashDigest, VerifiedKnowledgeInput


def test_synthetic_wrapper_preserves_non_authoritative_provenance(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    wrapped = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )

    assert wrapped.schema_version == SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION
    assert wrapped.fixture_version == "0.1.0-draft"
    assert wrapped.provenance is StrategyInputProvenance.INVEST_SYSTEM_SYNTHETIC
    assert wrapped.fixture_payload_hash == HashDigest(
        algorithm="sha256",
        value=verified_knowledge_input.canonical_sha256(),
    )
    assert wrapped.synthetic is True
    assert wrapped.validation_only is True
    assert wrapped.not_a_published_release is True
    assert wrapped.not_strategy_evidence is True
    assert wrapped.authorizes_positions is False
    assert wrapped.authorizes_orders is False

    canonical = wrapped.to_json_value()
    assert canonical["provenance"] == "invest_system_synthetic"
    assert canonical["validation_only"] is True
    assert canonical["not_a_published_release"] is True
    assert canonical["not_strategy_evidence"] is True
    assert canonical["authorizes_positions"] is False
    assert canonical["authorizes_orders"] is False


def test_synthetic_wrapper_is_deterministic_for_the_same_payload(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    first = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    second = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )

    assert first is not second
    assert first.to_canonical_bytes() == second.to_canonical_bytes()
    assert first.canonical_sha256() == second.canonical_sha256()


def test_synthetic_wrapper_recomputes_and_rejects_a_claimed_payload_hash(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    with pytest.raises(ValueError, match="fixture_payload_hash does not match"):
        SyntheticValidationInput(
            fixture_id="synthetic_fixture_stage2b_001",
            fixture_version="0.1.0-draft",
            fixture_payload_hash=HashDigest(algorithm="sha256", value="f" * 64),
            verified_knowledge_input=verified_knowledge_input,
        )


@pytest.mark.parametrize(
    "fixture_id",
    ["real_fixture_001", "SYNTHETIC_fixture_001", "synthetic_", "latest", "bad fixture"],
)
def test_synthetic_wrapper_requires_an_unambiguous_fixture_namespace(
    verified_knowledge_input: VerifiedKnowledgeInput,
    fixture_id: str,
) -> None:
    with pytest.raises(ValueError, match="fixture_id"):
        SyntheticValidationInput.from_verified_input(
            fixture_id=fixture_id,
            fixture_version="0.1.0-draft",
            verified_knowledge_input=verified_knowledge_input,
        )


@pytest.mark.parametrize("fixture_version", ["", "draft", "v0.1", "0.1"])
def test_synthetic_wrapper_requires_an_explicit_semantic_fixture_version(
    verified_knowledge_input: VerifiedKnowledgeInput,
    fixture_version: str,
) -> None:
    with pytest.raises(ValueError, match="fixture_version must be a semantic version"):
        SyntheticValidationInput.from_verified_input(
            fixture_id="synthetic_fixture_stage2b_001",
            fixture_version=fixture_version,
            verified_knowledge_input=verified_knowledge_input,
        )


def test_synthetic_wrapper_rejects_a_real_release_namespace(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    real_reference = replace(
        verified_knowledge_input.strategy_input_ref,
        dataset_release_id="rel_real_001",
    )
    relabeled = replace(verified_knowledge_input, strategy_input_ref=real_reference)

    with pytest.raises(ValueError, match="synthetic_release_ namespace"):
        SyntheticValidationInput.from_verified_input(
            fixture_id="synthetic_fixture_stage2b_001",
            fixture_version="0.1.0-draft",
            verified_knowledge_input=relabeled,
        )


def test_synthetic_wrapper_rejects_a_non_synthetic_input_identity(
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    relabeled = replace(verified_knowledge_input, input_id="provider_input_001")

    with pytest.raises(ValueError, match="input_id must use the synthetic_ namespace"):
        SyntheticValidationInput.from_verified_input(
            fixture_id="synthetic_fixture_stage2b_001",
            fixture_version="0.1.0-draft",
            verified_knowledge_input=relabeled,
        )


@pytest.mark.parametrize("missing_marker", ["synthetic", "not_a_published_release"])
def test_every_synthetic_fact_retains_required_provenance_markers(
    verified_knowledge_input: VerifiedKnowledgeInput,
    missing_marker: str,
) -> None:
    fact = verified_knowledge_input.facts[0]
    metadata = dict(fact.metadata)
    metadata.pop(missing_marker)
    relabeled_fact = replace(fact, metadata=metadata)
    relabeled = replace(verified_knowledge_input, facts=(relabeled_fact,))

    with pytest.raises(ValueError, match=missing_marker):
        SyntheticValidationInput.from_verified_input(
            fixture_id="synthetic_fixture_stage2b_001",
            fixture_version="0.1.0-draft",
            verified_knowledge_input=relabeled,
        )
