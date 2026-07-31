from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system.integrations.investment_research_kb.provider_canonical import (
    CANONICALIZATION_PROFILE,
    ProviderCanonicalError,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    manifest_sha256,
    normalize_json_nfc,
    sealed_manifest_bytes,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
VECTOR_PATH = (
    REPOSITORY_ROOT
    / "contracts"
    / "providers"
    / "investment_research_kb"
    / "v1"
    / "vendor"
    / "contracts"
    / "fixtures"
    / "release-hash-vectors.v1.json"
)


def _vectors() -> dict[str, Any]:
    value = json.loads(VECTOR_PATH.read_bytes())
    assert isinstance(value, dict)
    return value


def _digest(value: bytes) -> str:
    return sha256(value).hexdigest()


def test_official_fixture_declares_supported_profile() -> None:
    vectors = _vectors()

    assert vectors["schema_version"] == "1.0.0"
    assert vectors["canonicalization_profile"] == CANONICALIZATION_PROFILE
    assert vectors["encoding"] == "UTF-8"
    assert vectors["hash_algorithm"] == "sha256"


@pytest.mark.parametrize(
    "vector",
    _vectors()["canonical_json_vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_all_official_canonical_json_vectors(vector: dict[str, Any]) -> None:
    encoded = canonical_json_bytes(vector["value"])

    assert encoded.hex() == vector["expected_utf8_hex"]
    assert _digest(encoded) == vector["expected_hash"]["value"]
    assert not encoded.endswith(b"\n")


@pytest.mark.parametrize(
    "vector",
    _vectors()["artifact_vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_all_official_jsonl_vectors(vector: dict[str, Any]) -> None:
    encoded = canonical_jsonl_bytes(
        vector["records"],
        sort_keys=vector["sort_keys"],
    )

    assert len(encoded) == vector["expected_size_bytes"]
    assert encoded.hex() == vector["expected_utf8_hex"]
    assert _digest(encoded) == vector["expected_artifact_hash"]["value"]
    assert encoded.endswith(b"\n")
    record_ids = [json.loads(line)["id"] for line in encoded.splitlines()]
    assert record_ids == vector["expected_record_ids"]


@pytest.mark.parametrize(
    "vector",
    _vectors()["manifest_vectors"],
    ids=lambda vector: vector["vector_id"],
)
def test_all_official_manifest_vectors(vector: dict[str, Any]) -> None:
    unsigned = vector["unsigned_manifest"]
    calculated_hash = manifest_sha256(unsigned)
    sealed_value = {
        **unsigned,
        "manifest_hash": {"algorithm": "sha256", "value": calculated_hash},
    }
    sealed = sealed_manifest_bytes(sealed_value)

    assert calculated_hash == vector["expected_manifest_hash"]["value"]
    assert len(sealed) == vector["expected_sealed_file_size_bytes"]
    assert _digest(sealed) == vector["expected_sealed_file_hash"]["value"]
    assert sealed.endswith(b"\n")
    assert not sealed.endswith(b"\n\n")


def test_recursive_nfc_normalization_and_collision_rejection() -> None:
    value = {"outer": [{"z": "Cafe\u0301"}]}
    assert normalize_json_nfc(value) == {"outer": [{"z": "Café"}]}

    with pytest.raises(ProviderCanonicalError, match="NFC key collision"):
        canonical_json_bytes({"e\u0301": 1, "é": 2})


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_numbers_are_rejected(value: float) -> None:
    with pytest.raises(ProviderCanonicalError, match="non-finite"):
        canonical_json_bytes({"value": value})


@pytest.mark.parametrize(
    "value",
    [b"bytes", ("tuple",), {"set"}, {1: "non-string-key"}],
)
def test_non_json_values_are_rejected(value: object) -> None:
    with pytest.raises(ProviderCanonicalError):
        canonical_json_bytes(value)


def test_jsonl_requires_present_string_sort_values() -> None:
    with pytest.raises(ProviderCanonicalError, match="missing sort key"):
        canonical_jsonl_bytes([{"value": 1}], sort_keys=["id"])
    with pytest.raises(ProviderCanonicalError, match="must be a string"):
        canonical_jsonl_bytes([{"id": 1}], sort_keys=["id"])


def test_manifest_hash_ignores_only_top_level_self_hash_without_mutation() -> None:
    unsigned = {"schema_version": "1.0.0", "nested": {"manifest_hash": "retained"}}
    signed = {
        **unsigned,
        "manifest_hash": {"algorithm": "sha256", "value": "0" * 64},
    }

    assert manifest_sha256(signed) == manifest_sha256(unsigned)
    assert "manifest_hash" in signed
    assert canonical_json_bytes(unsigned).endswith(b"}")
    assert not canonical_json_bytes(unsigned).endswith(b"\n")


@pytest.mark.parametrize("function", [manifest_sha256, sealed_manifest_bytes])
def test_manifest_operations_require_an_object(function: Any) -> None:
    with pytest.raises(ProviderCanonicalError, match="manifest must be a JSON object"):
        function([])
