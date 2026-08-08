from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from invest_system import DeliveryTransport
from invest_system.integrations.investment_research_kb import (
    TRANSPORT_SNAPSHOT_LOCK_SHA256,
    TRANSPORT_SOURCE_COMMIT,
    KBTransportContractCatalog,
    SnapshotIntegrityError,
    TransportSupportStatus,
    kb_transport_capabilities,
    load_kb_transport_contract_snapshot,
    require_supported_kb_transport,
)


def test_stage6b_transport_snapshot_extends_the_unchanged_stage2a_base(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    assert kb_transport_catalog.source_commit == TRANSPORT_SOURCE_COMMIT
    assert kb_transport_catalog.source_commit == ("2c84277ef463b5dd9a3fda3f2976a30cade53af5")
    assert kb_transport_catalog.snapshot_lock_sha256 == TRANSPORT_SNAPSHOT_LOCK_SHA256
    assert kb_transport_catalog.base_catalog.source_commit == (
        "58ed9c5cb5302e3e719f1696bed83a03c5d6313b"
    )
    assert kb_transport_catalog.openapi["openapi"] == "3.1.0"
    assert kb_transport_catalog.official_fixture["schema_version"] == "1.0.0"


def test_transports_enable_only_with_the_verified_extension(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    default = kb_transport_capabilities()
    verified = kb_transport_capabilities(contract_catalog=kb_transport_catalog)

    assert all(item.status is TransportSupportStatus.NOT_SUPPORTED for item in default)
    assert all(item.status is TransportSupportStatus.SUPPORTED for item in verified)
    for transport in DeliveryTransport:
        capability = require_supported_kb_transport(
            transport,
            contract_catalog=kb_transport_catalog,
        )
        assert capability.transport is transport
        assert capability.blocker is None


def test_transport_snapshot_rejects_one_byte_tampering(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    source = repository_root / "contracts" / "providers" / "investment_research_kb"
    copied = tmp_path / "provider"
    shutil.copytree(source, copied)
    target = (
        copied / "stage6b-transport-v1" / "vendor" / "contracts" / "http-envelope.v1.schema.json"
    )
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(SnapshotIntegrityError, match="byte mismatch"):
        load_kb_transport_contract_snapshot(copied / "stage6b-transport-v1")


def test_stage6b_support_matrix_does_not_claim_authenticated_authority(
    repository_root: Path,
) -> None:
    path = (
        repository_root
        / "contracts"
        / "providers"
        / "investment_research_kb"
        / "stage6b-transport-v1"
        / "support-matrix.json"
    )
    matrix = json.loads(path.read_bytes())
    assert matrix["source_commit"] == TRANSPORT_SOURCE_COMMIT
    assert {item["transport"] for item in matrix["capabilities"]} == {
        "read_only_http_api",
        "immutable_export",
    }
    assert all(item["authority_status"].startswith("requires_") for item in matrix["capabilities"])


def test_capability_rechecks_snapshot_integrity_before_enabling_io(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    source = repository_root / "contracts" / "providers" / "investment_research_kb"
    copied = tmp_path / "provider"
    shutil.copytree(source, copied)
    catalog = load_kb_transport_contract_snapshot(copied / "stage6b-transport-v1")
    target = copied / "stage6b-transport-v1" / "vendor" / "contracts" / "http-error.v1.schema.json"
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(SnapshotIntegrityError, match="byte identity"):
        kb_transport_capabilities(contract_catalog=catalog)
