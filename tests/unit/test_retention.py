from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from invest_system.canonical import CanonicalJsonError, canonical_json_bytes
from invest_system.models import CanonicalModel, HashDigest, StrategyInputRef
from invest_system.retention import (
    RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION,
    ArtifactPayload,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
    ReleaseRetentionNode,
    RetentionArtifact,
)

ROOT_CUTOFF = datetime(2026, 7, 31, 8, tzinfo=UTC)


def digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def input_ref(
    release_id: str,
    *,
    cutoff: datetime = ROOT_CUTOFF,
    schema_version: str = "1.0.0",
    manifest_schema_version: str = "1.0.0",
    manifest_digest: str = "a",
) -> StrategyInputRef:
    return StrategyInputRef(
        schema_version=schema_version,
        dataset_release_id=release_id,
        knowledge_cutoff=cutoff,
        release_manifest_schema_version=manifest_schema_version,
        manifest_hash=digest(manifest_digest),
    )


def artifact(
    artifact_id: str,
    *,
    item_type: str = "verified-facts",
    artifact_digest: str = "b",
    size_bytes: int = 10,
    record_count: int | None = 1,
) -> RetentionArtifact:
    return RetentionArtifact(
        artifact_id=artifact_id,
        item_type=item_type,
        artifact_hash=digest(artifact_digest),
        size_bytes=size_bytes,
        record_count=record_count,
    )


def closure_nodes() -> tuple[ReleaseRetentionNode, ...]:
    leaf = ReleaseRetentionNode(
        strategy_input_ref=input_ref(
            "source_release_leaf",
            cutoff=ROOT_CUTOFF - timedelta(days=2),
            manifest_digest="d",
        ),
        manifest_document_hash=digest("8"),
        manifest_size_bytes=101,
        artifacts=(artifact("leaf_facts", artifact_digest="e"),),
    )
    source = ReleaseRetentionNode(
        strategy_input_ref=input_ref(
            "source_release_parent",
            cutoff=ROOT_CUTOFF - timedelta(days=1),
            manifest_digest="c",
        ),
        manifest_document_hash=digest("7"),
        manifest_size_bytes=102,
        artifacts=(
            artifact("source_z", artifact_digest="f"),
            artifact("source_a", artifact_digest="1"),
        ),
        dependency_release_ids=(leaf.release_id,),
    )
    root = ReleaseRetentionNode(
        strategy_input_ref=input_ref("context_release_root", manifest_digest="a"),
        manifest_document_hash=digest("6"),
        manifest_size_bytes=103,
        artifacts=(
            artifact("root_z", artifact_digest="2"),
            artifact("root_a", artifact_digest="3"),
        ),
        dependency_release_ids=(source.release_id,),
    )
    return root, source, leaf


def make_closure() -> ReleaseRetentionClosure:
    root, source, leaf = closure_nodes()
    return ReleaseRetentionClosure.create(
        root_strategy_input_ref=root.strategy_input_ref,
        releases=(leaf, root, source),
    )


def test_closure_normalizes_graph_collections_and_hashes_payload_without_self() -> None:
    closure = make_closure()

    assert tuple(node.release_id for node in closure.releases) == (
        "context_release_root",
        "source_release_leaf",
        "source_release_parent",
    )
    assert tuple(
        item.artifact_id for item in closure.release("context_release_root").artifacts
    ) == (
        "root_a",
        "root_z",
    )
    payload = closure.identity_payload()
    assert set(payload) == {"schema_version", "root_strategy_input_ref", "releases"}
    assert "closure_hash" not in payload
    assert closure.closure_hash == HashDigest(
        algorithm="sha256",
        value=sha256(canonical_json_bytes(payload)).hexdigest(),
    )
    assert closure.to_json_value()["closure_hash"] == closure.closure_hash.to_json_value()


def test_closure_identity_is_independent_of_caller_collection_order() -> None:
    root, source, leaf = closure_nodes()
    forward = ReleaseRetentionClosure.create(
        root_strategy_input_ref=root.strategy_input_ref,
        releases=(root, source, leaf),
    )
    reordered_root = replace(
        root,
        artifacts=tuple(reversed(root.artifacts)),
    )
    reverse = ReleaseRetentionClosure.create(
        root_strategy_input_ref=root.strategy_input_ref,
        releases=(leaf, source, reordered_root),
    )

    assert forward.closure_hash == reverse.closure_hash
    assert forward.to_canonical_bytes() == reverse.to_canonical_bytes()


def test_node_preserves_full_five_field_release_identity() -> None:
    root = closure_nodes()[0]
    value = root.to_json_value()

    assert set(value) == {
        "strategy_input_ref",
        "manifest_document_hash",
        "manifest_size_bytes",
        "artifacts",
        "dependency_release_ids",
    }
    assert value["strategy_input_ref"] == root.strategy_input_ref.to_json_value()
    assert root.release_id == root.strategy_input_ref.dataset_release_id
    assert root.knowledge_cutoff == root.strategy_input_ref.knowledge_cutoff
    assert root.release_manifest_schema_version == (
        root.strategy_input_ref.release_manifest_schema_version
    )
    assert root.manifest_hash == root.strategy_input_ref.manifest_hash
    assert root.manifest_document_hash == digest("6")
    assert root.manifest_size_bytes == 103


@pytest.mark.parametrize(
    "node_change",
    [
        {"manifest_document_hash": digest("9")},
        {"manifest_size_bytes": 104},
    ],
)
def test_manifest_document_commitment_is_covered_by_closure_identity(
    node_change: dict[str, Any],
) -> None:
    closure = make_closure()
    root, source, leaf = closure_nodes()
    changed_root = replace(root, **node_change)
    changed = ReleaseRetentionClosure.create(
        root_strategy_input_ref=changed_root.strategy_input_ref,
        releases=(changed_root, source, leaf),
    )

    assert changed.closure_hash != closure.closure_hash
    with pytest.raises(ValueError, match="closure_hash does not match"):
        replace(closure, releases=(changed_root, source, leaf))


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ({"manifest_document_hash": "a" * 64}, TypeError),
        ({"manifest_size_bytes": 0}, ValueError),
        ({"manifest_size_bytes": -1}, ValueError),
        ({"manifest_size_bytes": 1.0}, TypeError),
        ({"manifest_size_bytes": True}, TypeError),
    ],
)
def test_manifest_document_commitment_rejects_wrong_hash_or_size(
    changes: dict[str, Any],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(closure_nodes()[0], **changes)


@pytest.mark.parametrize(
    "changed_ref",
    [
        input_ref("context_release_root", schema_version="2.0.0"),
        input_ref("different_root"),
        input_ref("context_release_root", cutoff=ROOT_CUTOFF - timedelta(microseconds=1)),
        input_ref("context_release_root", manifest_schema_version="2.0.0"),
        input_ref("context_release_root", manifest_digest="9"),
    ],
)
def test_closure_rejects_any_root_five_field_identity_mismatch(
    changed_ref: StrategyInputRef,
) -> None:
    root, source, leaf = closure_nodes()
    with pytest.raises(ValueError):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=changed_ref,
            releases=(root, source, leaf),
        )


def test_closure_rejects_missing_dependency_and_future_dependency_cutoff() -> None:
    root, source, _leaf = closure_nodes()
    with pytest.raises(ValueError, match="absent from releases"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=root.strategy_input_ref,
            releases=(root, source),
        )

    future_source = replace(
        source,
        strategy_input_ref=replace(
            source.strategy_input_ref,
            knowledge_cutoff=ROOT_CUTOFF + timedelta(microseconds=1),
        ),
        dependency_release_ids=(),
    )
    root_to_future = replace(root, dependency_release_ids=(future_source.release_id,))
    with pytest.raises(ValueError, match="dependency knowledge_cutoff"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=root_to_future.strategy_input_ref,
            releases=(root_to_future, future_source),
        )


def test_closure_rejects_unreachable_nodes_and_cycles() -> None:
    root, source, leaf = closure_nodes()
    disconnected_root = replace(root, dependency_release_ids=())
    with pytest.raises(ValueError, match="every Release must be reachable"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=disconnected_root.strategy_input_ref,
            releases=(disconnected_root, source, leaf),
        )

    same_cutoff = ROOT_CUTOFF - timedelta(days=1)
    cycle_a = ReleaseRetentionNode(
        strategy_input_ref=input_ref("cycle_a", cutoff=same_cutoff),
        manifest_document_hash=digest("4"),
        manifest_size_bytes=10,
        artifacts=(artifact("cycle_a_facts"),),
        dependency_release_ids=("cycle_b",),
    )
    cycle_b = ReleaseRetentionNode(
        strategy_input_ref=input_ref("cycle_b", cutoff=same_cutoff),
        manifest_document_hash=digest("5"),
        manifest_size_bytes=11,
        artifacts=(artifact("cycle_b_facts"),),
        dependency_release_ids=("cycle_a",),
    )
    cycle_root = replace(root, dependency_release_ids=("cycle_a",))
    with pytest.raises(ValueError, match="must not contain a cycle"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=cycle_root.strategy_input_ref,
            releases=(cycle_root, cycle_a, cycle_b),
        )


def test_nodes_and_closure_reject_duplicate_or_unordered_collections() -> None:
    root, source, leaf = closure_nodes()
    with pytest.raises(ValueError, match="duplicate artifact_id"):
        replace(root, artifacts=(root.artifacts[0], root.artifacts[0]))
    with pytest.raises(ValueError, match="duplicate release IDs"):
        replace(root, dependency_release_ids=(source.release_id, source.release_id))
    with pytest.raises(ValueError, match="duplicate release_id"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=root.strategy_input_ref,
            releases=(root, root),
        )
    with pytest.raises(TypeError, match="ordered list or tuple"):
        replace(root, artifacts=set(root.artifacts))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ordered list or tuple"):
        replace(root, dependency_release_ids={source.release_id})  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ordered list or tuple"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=root.strategy_input_ref,
            releases={root, source, leaf},
        )


def test_node_rejects_empty_artifacts_self_dependency_and_wrong_member_types() -> None:
    root = closure_nodes()[0]
    with pytest.raises(ValueError, match="must not be empty"):
        replace(root, artifacts=())
    with pytest.raises(ValueError, match="must not depend on itself"):
        replace(root, dependency_release_ids=(root.release_id,))
    with pytest.raises(TypeError, match="only RetentionArtifact"):
        replace(root, artifacts=("not-an-artifact",))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="StrategyInputRef"):
        ReleaseRetentionNode(
            strategy_input_ref="not-a-ref",  # type: ignore[arg-type]
            manifest_document_hash=digest("a"),
            manifest_size_bytes=10,
            artifacts=(artifact("facts"),),
        )


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ({"artifact_id": "../facts"}, ValueError),
        ({"item_type": ""}, ValueError),
        ({"artifact_hash": "a" * 64}, TypeError),
        ({"size_bytes": -1}, ValueError),
        ({"size_bytes": 1.0}, TypeError),
        ({"size_bytes": True}, TypeError),
        ({"record_count": -1}, ValueError),
        ({"record_count": 1.0}, TypeError),
        ({"record_count": False}, TypeError),
    ],
)
def test_retention_artifact_validates_exact_types(
    changes: dict[str, Any],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(artifact("facts"), **changes)


def test_closure_rejects_empty_wrong_schema_and_wrong_self_hash() -> None:
    closure = make_closure()
    with pytest.raises(ValueError, match="must not be empty"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=closure.root_strategy_input_ref,
            releases=(),
        )
    with pytest.raises(ValueError, match="schema_version"):
        ReleaseRetentionClosure.create(
            root_strategy_input_ref=closure.root_strategy_input_ref,
            releases=closure.releases,
            schema_version="0.2.0-draft",
        )
    with pytest.raises(ValueError, match="closure_hash does not match"):
        replace(closure, closure_hash=digest("f"))
    with pytest.raises(TypeError, match="closure_hash"):
        replace(closure, closure_hash="f" * 64)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        ArtifactPayload(
            release_id="release_001",
            artifact_id="facts_001",
            content=b"exact-artifact-bytes",
        ),
        ReleaseManifestPayload(
            release_id="release_001",
            content=b'{"canonical":"manifest"}',
        ),
    ],
)
def test_byte_payloads_are_frozen_strict_and_intentionally_noncanonical(
    payload: ArtifactPayload | ReleaseManifestPayload,
) -> None:
    assert not isinstance(payload, CanonicalModel)
    assert not hasattr(payload, "to_canonical_bytes")
    with pytest.raises(CanonicalJsonError, match="unsupported canonical JSON value"):
        canonical_json_bytes(payload)
    with pytest.raises(FrozenInstanceError):
        payload.release_id = "changed"  # type: ignore[misc]


def test_byte_payloads_reject_invalid_ids_and_non_bytes() -> None:
    with pytest.raises(ValueError, match="exact ID"):
        ReleaseManifestPayload(release_id="latest", content=b"manifest")
    with pytest.raises(ValueError):
        ArtifactPayload(release_id="release_001", artifact_id="../facts", content=b"facts")
    with pytest.raises(TypeError, match="content must be bytes"):
        ReleaseManifestPayload(
            release_id="release_001",
            content=cast(bytes, bytearray(b"manifest")),
        )


def test_provider_owned_artifact_ids_allow_public_contract_width_and_slash(
    repository_root: Path,
) -> None:
    provider_id = "provider/artifacts/" + ("x" * 237)
    assert len(provider_id) == 256
    payload = ArtifactPayload(
        release_id="release_001",
        artifact_id=provider_id,
        content=b"facts",
    )
    assert payload.artifact_id == provider_id
    root, source, leaf = closure_nodes()
    root = replace(root, artifacts=(artifact(provider_id),))
    closure = ReleaseRetentionClosure.create(
        root_strategy_input_ref=root.strategy_input_ref,
        releases=(root, source, leaf),
    )
    _contract, validator = retention_contract_validator(repository_root)
    validator.validate(closure.to_json_value())
    with pytest.raises(ValueError, match="must not be empty"):
        ReleaseManifestPayload(release_id="release_001", content=b"")
    with pytest.raises(TypeError, match="content must be bytes"):
        ArtifactPayload(
            release_id="release_001",
            artifact_id="facts_001",
            content="facts",  # type: ignore[arg-type]
        )


def test_release_lookup_fails_closed_for_unknown_or_non_exact_ids() -> None:
    closure = make_closure()
    with pytest.raises(KeyError):
        closure.release("unknown_release")
    with pytest.raises(ValueError, match="exact ID"):
        closure.release("latest")


def test_retention_schema_version_is_exact_draft_constant() -> None:
    assert RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION == "0.1.0-draft"


def retention_contract_validator(
    repository_root: Path,
) -> tuple[dict[str, Any], Draft202012Validator]:
    common_path = repository_root / "contracts/common/common-defs.schema.json"
    closure_path = (
        repository_root
        / "contracts/release-retention-closure/release-retention-closure.schema.json"
    )
    common = json.loads(common_path.read_text(encoding="utf-8"))
    closure = json.loads(closure_path.read_text(encoding="utf-8"))
    registry = Registry[Any]().with_resources(
        [(str(document["$id"]), Resource.from_contents(document)) for document in (common, closure)]
    )
    return closure, Draft202012Validator(
        closure,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def test_retention_machine_contract_is_valid_owned_and_matches_model(
    repository_root: Path,
) -> None:
    contract, validator = retention_contract_validator(repository_root)
    Draft202012Validator.check_schema(contract)

    assert contract["$id"] == (
        "https://schemas.investsystem.local/release-retention-closure/"
        "0.1.0-draft/release-retention-closure.schema.json"
    )
    assert contract["x-owner"] == "InvestSystem"
    assert contract["x-contract-status"] == "draft"
    assert contract["x-contract-version"] == RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION
    assert contract["x-canonical-profile"] == "investsystem-canonical-json-v1"
    assert any("acyclic" in invariant for invariant in contract["x-semantic-invariants"])

    closure = make_closure()
    value = closure.to_json_value()
    validator.validate(value)
    assert set(value) == {
        "schema_version",
        "root_strategy_input_ref",
        "releases",
        "closure_hash",
    }
    assert set(value["releases"][0]) == {
        "strategy_input_ref",
        "manifest_document_hash",
        "manifest_size_bytes",
        "artifacts",
        "dependency_release_ids",
    }
    assert set(value["releases"][0]["artifacts"][0]) == {
        "artifact_id",
        "item_type",
        "artifact_hash",
        "size_bytes",
        "record_count",
    }


@pytest.mark.parametrize(
    "mutation",
    [
        "top-level-extra",
        "wrong-version",
        "bare-closure-hash",
        "missing-root-field",
        "release-extra",
        "missing-manifest-document-hash",
        "bare-manifest-document-hash",
        "zero-manifest-size",
        "empty-releases",
        "duplicate-release",
        "empty-artifacts",
        "duplicate-artifact",
        "artifact-extra",
        "float-size",
        "negative-record-count",
        "duplicate-dependency-edge",
        "latest-dependency",
    ],
)
def test_retention_machine_contract_rejects_structural_drift(
    repository_root: Path,
    mutation: str,
) -> None:
    _contract, validator = retention_contract_validator(repository_root)
    value = deepcopy(make_closure().to_json_value())
    root = value["releases"][0]
    if mutation == "top-level-extra":
        value["provider"] = "kb"
    elif mutation == "wrong-version":
        value["schema_version"] = "0.2.0-draft"
    elif mutation == "bare-closure-hash":
        value["closure_hash"] = "a" * 64
    elif mutation == "missing-root-field":
        del value["root_strategy_input_ref"]["knowledge_cutoff"]
    elif mutation == "release-extra":
        root["transport"] = "http"
    elif mutation == "missing-manifest-document-hash":
        del root["manifest_document_hash"]
    elif mutation == "bare-manifest-document-hash":
        root["manifest_document_hash"] = "a" * 64
    elif mutation == "zero-manifest-size":
        root["manifest_size_bytes"] = 0
    elif mutation == "empty-releases":
        value["releases"] = []
    elif mutation == "duplicate-release":
        value["releases"].append(deepcopy(root))
    elif mutation == "empty-artifacts":
        root["artifacts"] = []
    elif mutation == "duplicate-artifact":
        root["artifacts"].append(deepcopy(root["artifacts"][0]))
    elif mutation == "artifact-extra":
        root["artifacts"][0]["cache_key"] = "provider/path"
    elif mutation == "float-size":
        root["artifacts"][0]["size_bytes"] = 1.5
    elif mutation == "negative-record-count":
        root["artifacts"][0]["record_count"] = -1
    elif mutation == "duplicate-dependency-edge":
        root["dependency_release_ids"].append(root["dependency_release_ids"][0])
    elif mutation == "latest-dependency":
        root["dependency_release_ids"] = ["latest"]
    else:  # pragma: no cover - parametrization is closed above
        raise AssertionError(mutation)

    with pytest.raises(ValidationError):
        validator.validate(value)
