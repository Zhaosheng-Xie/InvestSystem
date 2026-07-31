from __future__ import annotations

from pathlib import Path

from invest_system import VerifiedKnowledgeInput


def test_synthetic_fixture_is_unambiguously_non_kb_and_non_strategy_evidence(
    synthetic_fixture_document: dict[str, object],
) -> None:
    metadata = synthetic_fixture_document["fixture_metadata"]
    assert isinstance(metadata, dict)
    assert metadata == {
        "fixture_class": "invest_system_synthetic",
        "synthetic": True,
        "not_a_published_release": True,
        "not_strategy_evidence": True,
        "purpose": ("Stage 1 provider-neutral representation and deterministic serialization"),
    }

    payload = synthetic_fixture_document["verified_knowledge_input"]
    assert isinstance(payload, dict)
    reference = payload["strategy_input_ref"]
    assert isinstance(reference, dict)
    assert str(reference["dataset_release_id"]).startswith("synthetic_release_stage1_")
    assert "TRADE_READY" not in str(synthetic_fixture_document)


def test_synthetic_verified_input_matches_its_canonical_sha256_golden(
    repository_root: Path,
    verified_knowledge_input: VerifiedKnowledgeInput,
) -> None:
    expected_hash_path = (
        repository_root
        / "tests"
        / "fixtures"
        / "synthetic"
        / "verified_knowledge_input_v0.1.0-draft.sha256"
    )
    expected = expected_hash_path.read_text(encoding="ascii").strip()

    first_bytes = verified_knowledge_input.to_canonical_bytes()
    second_bytes = verified_knowledge_input.to_canonical_bytes()

    assert first_bytes == second_bytes
    assert verified_knowledge_input.canonical_sha256() == expected
