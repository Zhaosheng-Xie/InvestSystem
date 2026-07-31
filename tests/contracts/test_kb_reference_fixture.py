from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system.integrations.investment_research_kb.contracts import (
    KBContractCatalog,
    load_kb_contract_snapshot,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes,
    manifest_sha256,
)
from invest_system.integrations.investment_research_kb.reference_fixture import (
    ReferenceFixtureError,
    ReferenceValidationCode,
    _verify_stage6_reference_document,
    verify_stage6_reference_fixture,
)

SNAPSHOT_RELATIVE = Path("contracts") / "providers" / "investment_research_kb" / "v1"
EXPECTED_MANIFEST_HASH = "affa7ceffce07081ac3e1d930a25c1da7ea2d3bc4a87848e8615f2bf26a2d0f8"
EXPECTED_RECEIPT_HASH = "4ce7f0876ab90fe3dc5dc21abf8e1eda06638ac898dc3783806067506747b901"
EXPECTED_INPUT_ID = "vki_9de3390051890fa8c22a580411c66032"


@pytest.fixture(scope="module")
def catalog(repository_root: Path) -> KBContractCatalog:
    return load_kb_contract_snapshot(repository_root / SNAPSHOT_RELATIVE)


@pytest.fixture
def document(catalog: KBContractCatalog) -> dict[str, Any]:
    return catalog.stage6_fixture


def _release(document: dict[str, Any], release_id: str) -> dict[str, Any]:
    return next(
        release
        for release in document["releases"]
        if release["dataset_release"]["release_id"] == release_id
    )


def _context_release(document: dict[str, Any]) -> dict[str, Any]:
    return _release(document, document["expected_strategy_input_ref"]["dataset_release_id"])


def _semantic_artifact(release: dict[str, Any], item_type: str) -> dict[str, Any]:
    item = next(
        candidate
        for candidate in release["manifest"]["release_items"]
        if candidate["item_type"] == item_type
    )
    value = release["artifacts"][item["artifact_id"]]
    assert isinstance(value, dict)
    return value


def _refresh_semantic_self_hash(value: dict[str, Any]) -> None:
    hash_field = next(field for field in ("bundle_hash", "context_pack_hash") if field in value)
    unsigned = {key: nested for key, nested in value.items() if key != hash_field}
    value[hash_field]["value"] = sha256(canonical_json_bytes(unsigned)).hexdigest()


def _seal_release(
    document: dict[str, Any],
    release: dict[str, Any],
    *,
    refresh_semantic_hash: bool = True,
) -> None:
    manifest = release["manifest"]
    for item in manifest["release_items"]:
        if item["item_type"] == "schema":
            continue
        value = release["artifacts"][item["artifact_id"]]
        if refresh_semantic_hash:
            _refresh_semantic_self_hash(value)
        content = canonical_json_bytes(value) + b"\n"
        digest = sha256(content).hexdigest()
        item["size_bytes"] = len(content)
        item["artifact_hash"]["value"] = digest
        item["logical_content_hash"]["value"] = digest

    digest = manifest_sha256(manifest)
    manifest["manifest_hash"]["value"] = digest
    release["dataset_release"]["manifest_ref"]["hash"]["value"] = digest
    release_id = release["dataset_release"]["release_id"]
    if document["expected_strategy_input_ref"]["dataset_release_id"] == release_id:
        document["expected_strategy_input_ref"]["manifest_hash"]["value"] = digest
    for change in document["changes"]:
        if change["release_id"] == release_id:
            change["manifest_ref"]["hash"]["value"] = digest


def _rebind_context_source(
    document: dict[str, Any],
    source_release: dict[str, Any],
) -> None:
    source_dataset = source_release["dataset_release"]
    source_manifest = source_release["manifest"]
    source_reference = {
        "release_id": source_dataset["release_id"],
        "knowledge_cutoff": source_dataset["knowledge_cutoff"],
        "manifest_hash": source_manifest["manifest_hash"],
    }
    context_release = _context_release(document)
    context_pack = _semantic_artifact(context_release, "context_pack")
    context_pack["source_releases"][0] = source_reference
    context_release["manifest"]["context_pack_build"]["source_release"] = source_reference
    _seal_release(document, context_release)


def _assert_code(
    catalog: KBContractCatalog,
    document: dict[str, Any],
    expected: ReferenceValidationCode,
) -> None:
    with pytest.raises(ReferenceFixtureError) as raised:
        _verify_stage6_reference_document(catalog, document)
    assert raised.value.code is expected


def test_official_reference_fixture_projects_deterministically(
    catalog: KBContractCatalog,
) -> None:
    first = verify_stage6_reference_fixture(catalog)
    second = verify_stage6_reference_fixture(catalog)

    assert first == second
    assert first.strategy_input_ref.manifest_hash.value == EXPECTED_MANIFEST_HASH
    assert first.receipt.receipt_hash.value == EXPECTED_RECEIPT_HASH
    assert first.receipt.canonical_sha256() == second.receipt.canonical_sha256()
    assert first.verified_knowledge_input.input_id == EXPECTED_INPUT_ID
    assert (
        first.verified_knowledge_input.canonical_sha256()
        == second.verified_knowledge_input.canonical_sha256()
    )
    assert [release.release_id for release in first.releases] == [
        "rel_stage6_fixture_context",
        "rel_stage6_fixture_evidence",
    ]
    assert [change.release_id for change in first.changes] == [
        "rel_stage6_fixture_evidence",
        "rel_stage6_fixture_context",
    ]
    assert [item.artifact_id for item in first.receipt.artifacts] == [
        "context-pack-fixture-v1",
        "context-pack-fixture-v1-record-schema",
    ]
    assert [item.record_count for item in first.receipt.artifacts] == [1, None]
    assert [fact.fact_id for fact in first.verified_knowledge_input.facts] == [
        "iedgev_stage6_fixture_v1"
    ]
    projected = first.verified_knowledge_input.facts[0]
    assert projected.verified_at.isoformat() == "2026-07-27T11:00:00+00:00"
    assert projected.available_at.isoformat() == "2026-07-27T12:00:00+00:00"
    assert projected.source_published_at is not None
    assert projected.source_published_at.isoformat() == "2026-07-27T09:00:00+00:00"
    assert projected.first_seen_at is not None
    assert projected.first_seen_at.isoformat() == "2026-07-27T10:00:00+00:00"


def test_public_reference_entrypoint_accepts_only_the_hash_locked_catalog_fixture(
    catalog: KBContractCatalog,
) -> None:
    with pytest.raises(TypeError):
        verify_stage6_reference_fixture(catalog, catalog.stage6_fixture)  # type: ignore[call-arg]


def test_same_size_artifact_tampering_fails_hash_check(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    context_pack = _semantic_artifact(_context_release(document), "context_pack")
    context_pack["industry_graph"]["edges"][0]["attributes"]["role"] = "domponent_supplier"

    _assert_code(catalog, document, ReferenceValidationCode.ARTIFACT_HASH_MISMATCH)


def test_artifact_size_tampering_fails_before_projection(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    context_pack = _semantic_artifact(_context_release(document), "context_pack")
    context_pack["sources"][0]["title"] += "!"

    _assert_code(catalog, document, ReferenceValidationCode.ARTIFACT_SIZE_MISMATCH)


def test_manifest_self_hash_is_verified(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    _context_release(document)["manifest"]["manifest_hash"]["value"] = "0" * 64

    _assert_code(catalog, document, ReferenceValidationCode.MANIFEST_HASH_MISMATCH)


def test_semantic_self_hash_is_verified_after_artifact_resealing(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["industry_graph"]["edges"][0]["attributes"]["role"] = "changed_supplier"
    _seal_release(document, release, refresh_semantic_hash=False)

    _assert_code(catalog, document, ReferenceValidationCode.CONTENT_HASH_MISMATCH)


@pytest.mark.parametrize("status", ["building", "validated", "withdrawn"])
def test_every_non_published_current_status_fails_closed(
    catalog: KBContractCatalog,
    document: dict[str, Any],
    status: str,
) -> None:
    _context_release(document)["dataset_release"]["current_status"]["status"] = status

    _assert_code(catalog, document, ReferenceValidationCode.RELEASE_NOT_PUBLISHED)


def test_future_available_at_fails_pit_after_valid_resealing(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["industry_graph"]["edges"][0]["available_at"] = "2026-07-28T00:00:00.000001Z"
    _seal_release(document, release)

    _assert_code(catalog, document, ReferenceValidationCode.PIT_VIOLATION)


def test_source_release_cutoff_cannot_exceed_context_cutoff(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    source_release = _release(document, "rel_stage6_fixture_evidence")
    future_cutoff = "2026-07-28T00:30:00.000000Z"
    source_release["dataset_release"]["knowledge_cutoff"] = future_cutoff
    source_release["manifest"]["knowledge_cutoff"] = future_cutoff
    _semantic_artifact(source_release, "evidence_bundle")["knowledge_cutoff"] = future_cutoff
    source_change = next(
        change
        for change in document["changes"]
        if change["release_id"] == source_release["dataset_release"]["release_id"]
    )
    source_change["knowledge_cutoff"] = future_cutoff
    _seal_release(document, source_release)
    _rebind_context_source(document, source_release)

    _assert_code(catalog, document, ReferenceValidationCode.PIT_VIOLATION)


def test_future_review_and_publication_times_fail_pit_after_full_resealing(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    source_release = _release(document, "rel_stage6_fixture_evidence")
    evidence_bundle = _semantic_artifact(source_release, "evidence_bundle")
    future_time = "2026-07-29T00:00:00.000000Z"
    evidence_bundle["evidence_spans"][0]["review"]["reviewed_at"] = future_time
    fact = evidence_bundle["facts"][0]
    fact["review"]["reviewed_at"] = future_time
    fact["knowledge_published_at"] = future_time
    fact["publication"]["recorded_at"] = future_time
    _seal_release(document, source_release)
    _rebind_context_source(document, source_release)

    _assert_code(catalog, document, ReferenceValidationCode.PIT_VIOLATION)


def test_graph_cannot_be_available_before_its_source_document(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    source_release = _release(document, "rel_stage6_fixture_evidence")
    evidence_bundle = _semantic_artifact(source_release, "evidence_bundle")
    document_version = evidence_bundle["document_versions"][0]
    later_time = "2026-07-27T12:30:00.000000Z"
    for field in ("first_seen_at", "fetched_at", "available_at"):
        document_version[field] = later_time
    _seal_release(document, source_release)
    _rebind_context_source(document, source_release)
    context_release = _context_release(document)
    context_pack = _semantic_artifact(context_release, "context_pack")
    context_pack["sources"][0]["available_at"] = later_time
    _seal_release(document, context_release)

    _assert_code(catalog, document, ReferenceValidationCode.PIT_VIOLATION)


def test_graph_edge_cannot_predate_its_endpoint_nodes(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    context_release = _context_release(document)
    context_pack = _semantic_artifact(context_release, "context_pack")
    context_pack["industry_graph"]["nodes"][0]["available_at"] = "2026-07-27T12:30:00.000000Z"
    _seal_release(document, context_release)

    _assert_code(catalog, document, ReferenceValidationCode.PIT_VIOLATION)


def test_change_event_must_bind_the_validated_release(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    context_release_id = document["expected_strategy_input_ref"]["dataset_release_id"]
    change = next(item for item in document["changes"] if item["release_id"] == context_release_id)
    change["status_event"]["event_hash"]["value"] = "6" * 64

    _assert_code(catalog, document, ReferenceValidationCode.CHANGE_STREAM_MISMATCH)


def test_nonempty_unsupported_collection_is_never_silently_dropped(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["terminology"].append(
        {
            "term_id": "term_stage6_fixture",
            "name": "Stage 6 fixture term",
            "node_type": "term",
            "node_key": "term:stage6_fixture",
            "provenance_status": "approved",
        }
    )
    _seal_release(document, release)

    _assert_code(catalog, document, ReferenceValidationCode.PROJECTION_UNSUPPORTED)


def test_context_pack_source_release_must_match_manifest_build(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["source_releases"][0]["manifest_hash"]["value"] = "0" * 64
    _seal_release(document, release)

    _assert_code(catalog, document, ReferenceValidationCode.SOURCE_RELEASE_MISMATCH)


def test_graph_endpoint_must_close_to_the_pinned_evidence_chain(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["industry_graph"]["edges"][0]["from_node_key"] = "component:stage6_fixture"
    _seal_release(document, release)

    _assert_code(catalog, document, ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH)


def test_graph_edge_semantics_must_match_the_pinned_provider_fact(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    release = _context_release(document)
    context_pack = _semantic_artifact(release, "context_pack")
    context_pack["industry_graph"]["edges"][0]["attributes"]["role"] = "conflicting_role"
    _seal_release(document, release)

    _assert_code(catalog, document, ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH)


def test_five_field_input_reference_must_match_the_validated_release(
    catalog: KBContractCatalog,
    document: dict[str, Any],
) -> None:
    document["expected_strategy_input_ref"]["manifest_hash"]["value"] = "0" * 64

    _assert_code(catalog, document, ReferenceValidationCode.INPUT_REF_MISMATCH)
