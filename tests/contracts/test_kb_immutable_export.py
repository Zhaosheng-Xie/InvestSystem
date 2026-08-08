from __future__ import annotations

import copy
import json
import stat
import zipfile
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system.integrations.investment_research_kb import (
    ExportValidationCode,
    ImmutableExportValidationError,
    KBTransportContractCatalog,
    reconstruct_official_export_fixture,
    verify_immutable_export_members,
    verify_immutable_export_zip,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes,
)


def _reseal_package_manifest(manifest: dict[str, object]) -> None:
    unsigned = {key: value for key, value in manifest.items() if key != "package_manifest_hash"}
    manifest["package_manifest_hash"] = {
        "algorithm": "sha256",
        "value": sha256(canonical_json_bytes(unsigned)).hexdigest(),
    }


def test_official_export_fixture_closes_all_identities_without_granting_authority(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    manifest, members = reconstruct_official_export_fixture(kb_transport_catalog)
    result = verify_immutable_export_members(
        package_manifest=manifest,
        members=members,
        catalog=kb_transport_catalog,
    )

    assert result.release_id == "rel_stage6b_transport_fixture"
    assert result.manifest_hash == (
        "60491fb384a40f310c72b8cd744c99fbfbbe9c29236851a9b43c9d57cb0b3550"
    )
    assert result.status_sequence == 3
    assert result.current_status == "published"
    assert result.authority_eligible is False


@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("manifest_hash", ExportValidationCode.PACKAGE_MANIFEST_HASH_MISMATCH),
        ("member_hash", ExportValidationCode.MEMBER_HASH_MISMATCH),
        ("member_missing", ExportValidationCode.MEMBER_SET_MISMATCH),
        ("path_collision", ExportValidationCode.UNSAFE_MEMBER_PATH),
    ],
)
def test_export_fixture_fails_closed_on_manifest_and_member_mutations(
    kb_transport_catalog: KBTransportContractCatalog,
    mutation: str,
    code: ExportValidationCode,
) -> None:
    source_manifest, source_members = reconstruct_official_export_fixture(kb_transport_catalog)
    manifest = copy.deepcopy(source_manifest)
    members = dict(source_members)
    if mutation == "manifest_hash":
        manifest["package_id"] = "pkg_ffffffffffffffffffffffffffffffff"
    elif mutation == "member_hash":
        path = "artifacts/stage6b-transport-fixture.v1.json"
        members[path] = b"X" + members[path][1:]
    elif mutation == "member_missing":
        members.pop("metadata/release.json")
    else:
        members["Metadata/Release.json"] = members["metadata/release.json"]

    with pytest.raises(ImmutableExportValidationError) as caught:
        verify_immutable_export_members(
            package_manifest=manifest,
            members=members,
            catalog=kb_transport_catalog,
        )
    assert caught.value.code is code


def test_export_status_hash_chain_is_semantically_verified(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    source_manifest, source_members = reconstruct_official_export_fixture(kb_transport_catalog)
    manifest = copy.deepcopy(source_manifest)
    members = dict(source_members)
    path = "metadata/status-events.jsonl"
    events = [json.loads(line) for line in members[path].splitlines()]
    events[1]["previous_event_hash"]["value"] = "0" * 64
    events[1]["event_hash"]["value"] = sha256(
        canonical_json_bytes(
            {key: value for key, value in events[1].items() if key != "event_hash"}
        )
    ).hexdigest()
    members[path] = b"".join(canonical_json_bytes(event) + b"\n" for event in events)
    status_entry = next(item for item in manifest["files"] if item["path"] == path)
    status_entry["size_bytes"] = len(members[path])
    status_entry["sha256"]["value"] = sha256(members[path]).hexdigest()
    _reseal_package_manifest(manifest)

    with pytest.raises(ImmutableExportValidationError) as caught:
        verify_immutable_export_members(
            package_manifest=manifest,
            members=members,
            catalog=kb_transport_catalog,
        )
    assert caught.value.code is ExportValidationCode.STATUS_CHAIN_MISMATCH


def test_zip_carrier_is_checked_without_extraction(
    kb_transport_catalog: KBTransportContractCatalog,
    tmp_path: Path,
) -> None:
    manifest, members = reconstruct_official_export_fixture(kb_transport_catalog)
    path = tmp_path / "fixture.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("package-manifest.json", canonical_json_bytes(manifest) + b"\n")
        for name, content in members.items():
            archive.writestr(name, content)

    result = verify_immutable_export_zip(path, catalog=kb_transport_catalog)
    assert result.release_id == "rel_stage6b_transport_fixture"
    assert list(tmp_path.iterdir()) == [path]


def test_zip_carrier_rejects_symlink_metadata(
    kb_transport_catalog: KBTransportContractCatalog,
    tmp_path: Path,
) -> None:
    path = tmp_path / "unsafe.zip"
    info = zipfile.ZipInfo("package-manifest.json")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(info, b"target")

    with pytest.raises(ImmutableExportValidationError) as caught:
        verify_immutable_export_zip(path, catalog=kb_transport_catalog)
    assert caught.value.code is ExportValidationCode.CARRIER_UNSAFE
