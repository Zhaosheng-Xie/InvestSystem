"""Fail-closed validation for KB immutable export package content sets."""

from __future__ import annotations

import stat
import unicodedata
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, NoReturn

from .contracts import ContractValidationError, load_strict_json_bytes
from .provider_canonical import canonical_json_bytes, manifest_sha256
from .transport_contracts import IMMUTABLE_EXPORT_ID, KBTransportContractCatalog

_DATASET_RELEASE_ID = "urn:investment-research-kb:contract:dataset-release:v1"
_RELEASE_MANIFEST_ID = "urn:investment-research-kb:contract:release-manifest:v1"
_STATUS_EVENT_ID = "urn:investment-research-kb:contract:release-status-event:v1"
DEFAULT_MAX_PACKAGE_BYTES = 20 * 1024**3


class ExportValidationCode(StrEnum):
    MANIFEST_INVALID = "manifest_invalid"
    PACKAGE_MANIFEST_HASH_MISMATCH = "package_manifest_hash_mismatch"
    MEMBER_SET_MISMATCH = "member_set_mismatch"
    UNSAFE_MEMBER_PATH = "unsafe_member_path"
    MEMBER_SIZE_MISMATCH = "member_size_mismatch"
    MEMBER_HASH_MISMATCH = "member_hash_mismatch"
    MEMBER_ENCODING_MISMATCH = "member_encoding_mismatch"
    IDENTITY_CLOSURE_MISMATCH = "identity_closure_mismatch"
    STATUS_CHAIN_MISMATCH = "status_chain_mismatch"
    ARTIFACT_CLOSURE_MISMATCH = "artifact_closure_mismatch"
    CARRIER_UNSAFE = "carrier_unsafe"
    PACKAGE_TOO_LARGE = "package_too_large"


class ImmutableExportValidationError(ValueError):
    def __init__(self, code: ExportValidationCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True, slots=True)
class VerifiedExportMember:
    path: str
    role: str
    artifact_id: str | None
    media_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class VerifiedImmutableExport:
    package_id: str
    package_manifest_hash: str
    release_id: str
    release_schema_version: str
    knowledge_cutoff: str
    manifest_hash: str
    status_event_hash: str
    status_sequence: int
    current_status: str
    members: tuple[VerifiedExportMember, ...]
    authority_eligible: bool = False


def _fail(code: ExportValidationCode, message: str) -> NoReturn:
    raise ImmutableExportValidationError(code, message)


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(ExportValidationCode.MANIFEST_INVALID, f"{field} must be an object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(ExportValidationCode.MANIFEST_INVALID, f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(ExportValidationCode.MANIFEST_INVALID, f"{field} must be non-empty text")
    return value


def _digest(value: object, *, field: str) -> str:
    item = _object(value, field=field)
    if set(item) != {"algorithm", "value"} or item.get("algorithm") != "sha256":
        _fail(ExportValidationCode.MANIFEST_INVALID, f"{field} must be SHA-256")
    digest = item.get("value")
    if not isinstance(digest, str) or len(digest) != 64:
        _fail(ExportValidationCode.MANIFEST_INVALID, f"{field} must be SHA-256")
    return digest


def _safe_member_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail(ExportValidationCode.UNSAFE_MEMBER_PATH, "member path is not POSIX relative")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or value in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        _fail(ExportValidationCode.UNSAFE_MEMBER_PATH, f"unsafe member path: {value!r}")
    return value


def _canonical_json_document(content: bytes, *, source: str) -> dict[str, Any]:
    try:
        value = load_strict_json_bytes(content, source=source)
    except ValueError as exc:
        raise ImmutableExportValidationError(
            ExportValidationCode.MEMBER_ENCODING_MISMATCH,
            f"invalid JSON member: {source}",
        ) from exc
    item = _object(value, field=source)
    if canonical_json_bytes(item) + b"\n" != content:
        _fail(
            ExportValidationCode.MEMBER_ENCODING_MISMATCH,
            f"member is not canonical JSON plus LF: {source}",
        )
    return item


def _status_events(content: bytes, catalog: KBTransportContractCatalog) -> list[dict[str, Any]]:
    if not content.endswith(b"\n") or b"\r" in content:
        _fail(ExportValidationCode.MEMBER_ENCODING_MISMATCH, "status JSONL framing differs")
    lines = content[:-1].split(b"\n")
    if not lines or any(not line for line in lines):
        _fail(ExportValidationCode.MEMBER_ENCODING_MISMATCH, "status JSONL has empty records")
    events: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        try:
            raw = load_strict_json_bytes(line, source=f"status-events[{index}]")
        except ValueError as exc:
            raise ImmutableExportValidationError(
                ExportValidationCode.MEMBER_ENCODING_MISMATCH,
                f"invalid status JSONL record {index}",
            ) from exc
        event = _object(raw, field=f"status-events[{index}]")
        if canonical_json_bytes(event) != line:
            _fail(
                ExportValidationCode.MEMBER_ENCODING_MISMATCH,
                f"status event {index} is not canonical JSON",
            )
        try:
            catalog.validate_instance(_STATUS_EVENT_ID, event)
        except ContractValidationError as exc:
            raise ImmutableExportValidationError(
                ExportValidationCode.STATUS_CHAIN_MISMATCH,
                f"status event {index} violates the provider schema",
            ) from exc
        events.append(event)
    return events


def _verify_status_chain(events: list[dict[str, Any]], release_id: str) -> dict[str, Any]:
    prior_hash: str | None = None
    for index, event in enumerate(events, start=1):
        if event.get("release_id") != release_id or event.get("sequence") != index:
            _fail(ExportValidationCode.STATUS_CHAIN_MISMATCH, "status identity or sequence differs")
        previous = event.get("previous_event_hash")
        previous_value = (
            None if previous is None else _digest(previous, field="previous_event_hash")
        )
        if previous_value != prior_hash:
            _fail(ExportValidationCode.STATUS_CHAIN_MISMATCH, "status previous hash link differs")
        declared = _digest(event.get("event_hash"), field="event_hash")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if sha256(canonical_json_bytes(unsigned)).hexdigest() != declared:
            _fail(ExportValidationCode.STATUS_CHAIN_MISMATCH, "status event self-hash differs")
        prior_hash = declared
    return events[-1]


def verify_immutable_export_members(
    *,
    package_manifest: object,
    members: Mapping[str, bytes],
    catalog: KBTransportContractCatalog,
) -> VerifiedImmutableExport:
    """Verify a complete in-memory package content set without granting authority."""

    if not isinstance(catalog, KBTransportContractCatalog):
        raise TypeError("catalog must be a verified KBTransportContractCatalog")
    manifest = _object(package_manifest, field="package_manifest")
    try:
        catalog.validate_instance(IMMUTABLE_EXPORT_ID, manifest)
    except ContractValidationError as exc:
        raise ImmutableExportValidationError(
            ExportValidationCode.MANIFEST_INVALID,
            "package manifest violates the provider schema",
        ) from exc
    declared_manifest_hash = _digest(
        manifest.get("package_manifest_hash"), field="package_manifest_hash"
    )
    unsigned = {key: value for key, value in manifest.items() if key != "package_manifest_hash"}
    if sha256(canonical_json_bytes(unsigned)).hexdigest() != declared_manifest_hash:
        _fail(
            ExportValidationCode.PACKAGE_MANIFEST_HASH_MISMATCH,
            "package manifest self-hash differs",
        )
    normalized_members: dict[str, bytes] = {}
    collision_keys: set[str] = set()
    for raw_path, content in members.items():
        path = _safe_member_path(raw_path)
        if not isinstance(content, bytes):
            raise TypeError("every package member value must be bytes")
        collision_key = unicodedata.normalize("NFC", path).casefold()
        if collision_key in collision_keys:
            _fail(ExportValidationCode.UNSAFE_MEMBER_PATH, "member path case/NFC collision")
        collision_keys.add(collision_key)
        normalized_members[path] = content
    file_entries = _array(manifest.get("files"), field="package_manifest.files")
    expected_paths = [
        _safe_member_path(_object(item, field="file").get("path")) for item in file_entries
    ]
    if len(expected_paths) != len(set(expected_paths)) or set(normalized_members) != set(
        expected_paths
    ):
        _fail(ExportValidationCode.MEMBER_SET_MISMATCH, "package member closure differs")

    verified_members: list[VerifiedExportMember] = []
    role_paths: dict[str, str] = {}
    for raw in file_entries:
        item = _object(raw, field="file")
        path = item["path"]
        content = normalized_members[path]
        if len(content) != item.get("size_bytes"):
            _fail(ExportValidationCode.MEMBER_SIZE_MISMATCH, f"member size differs: {path}")
        declared_hash = _digest(item.get("sha256"), field=f"{path}.sha256")
        if sha256(content).hexdigest() != declared_hash:
            _fail(ExportValidationCode.MEMBER_HASH_MISMATCH, f"member hash differs: {path}")
        role = _text(item.get("role"), field=f"{path}.role")
        media_type = _text(item.get("media_type"), field=f"{path}.media_type")
        if role in {"dataset_release", "release_manifest", "release_status_events"}:
            if role in role_paths:
                _fail(ExportValidationCode.MEMBER_SET_MISMATCH, f"duplicate role: {role}")
            role_paths[role] = path
        verified_members.append(
            VerifiedExportMember(
                path=path,
                role=role,
                artifact_id=item.get("artifact_id"),
                media_type=media_type,
                size_bytes=item["size_bytes"],
                sha256=declared_hash,
            )
        )
    required_roles = {"dataset_release", "release_manifest", "release_status_events"}
    if set(role_paths) != required_roles:
        _fail(ExportValidationCode.MEMBER_SET_MISMATCH, "required metadata roles differ")
    expected_metadata = {
        "dataset_release": ("metadata/release.json", "application/json"),
        "release_manifest": ("metadata/manifest.json", "application/json"),
        "release_status_events": (
            "metadata/status-events.jsonl",
            "application/x-ndjson",
        ),
    }
    member_by_role = {member.role: member for member in verified_members}
    if any(
        (member_by_role[role].path, member_by_role[role].media_type) != expected
        for role, expected in expected_metadata.items()
    ):
        _fail(ExportValidationCode.MEMBER_SET_MISMATCH, "metadata path or media type differs")

    release = _canonical_json_document(
        normalized_members[role_paths["dataset_release"]], source="dataset release"
    )
    release_manifest = _canonical_json_document(
        normalized_members[role_paths["release_manifest"]], source="release manifest"
    )
    try:
        catalog.validate_instance(_DATASET_RELEASE_ID, release)
        catalog.validate_instance(_RELEASE_MANIFEST_ID, release_manifest)
    except ContractValidationError as exc:
        raise ImmutableExportValidationError(
            ExportValidationCode.IDENTITY_CLOSURE_MISMATCH,
            "Release metadata violates the pinned core contract",
        ) from exc

    package_release = _object(manifest.get("release"), field="package release")
    release_id = _text(package_release.get("release_id"), field="release.release_id")
    manifest_hash = _digest(package_release.get("manifest_hash"), field="release.manifest_hash")
    status_hash = _digest(
        package_release.get("status_event_hash"), field="release.status_event_hash"
    )
    identities = {
        release_id,
        release.get("release_id"),
        release_manifest.get("release_id"),
    }
    cutoffs = {
        package_release.get("knowledge_cutoff"),
        release.get("knowledge_cutoff"),
        release_manifest.get("knowledge_cutoff"),
    }
    if len(identities) != 1 or len(cutoffs) != 1:
        _fail(ExportValidationCode.IDENTITY_CLOSURE_MISMATCH, "Release identity or cutoff differs")
    if manifest_sha256(release_manifest) != manifest_hash:
        _fail(ExportValidationCode.IDENTITY_CLOSURE_MISMATCH, "Manifest self-hash differs")
    release_manifest_hash = _digest(release_manifest.get("manifest_hash"), field="manifest_hash")
    manifest_ref = _object(release.get("manifest_ref"), field="release.manifest_ref")
    if (
        release_manifest_hash != manifest_hash
        or _digest(manifest_ref.get("hash"), field="manifest_ref.hash") != manifest_hash
        or release.get("schema_version") != package_release.get("release_schema_version")
        or manifest_ref.get("schema_version") != package_release.get("release_schema_version")
        or release_manifest.get("schema_version") != package_release.get("release_schema_version")
    ):
        _fail(ExportValidationCode.IDENTITY_CLOSURE_MISMATCH, "Manifest reference differs")

    events = _status_events(normalized_members[role_paths["release_status_events"]], catalog)
    head = _verify_status_chain(events, release_id)
    current = _object(release.get("current_status"), field="release.current_status")
    if (
        head.get("event_hash", {}).get("value") != status_hash
        or head.get("sequence") != package_release.get("status_sequence")
        or current.get("event_hash", {}).get("value") != status_hash
        or current.get("sequence") != head.get("sequence")
        or current.get("event_id") != head.get("event_id")
        or current.get("status") != head.get("status")
        or current.get("recorded_at") != head.get("recorded_at")
    ):
        _fail(ExportValidationCode.STATUS_CHAIN_MISMATCH, "status chain head differs")

    raw_release_items = _array(release_manifest.get("release_items"), field="release_items")
    if any(not isinstance(item, dict) for item in raw_release_items):
        _fail(ExportValidationCode.ARTIFACT_CLOSURE_MISMATCH, "release item is not an object")
    release_item_ids = [item.get("artifact_id") for item in raw_release_items]
    artifact_members = [
        member for member in verified_members if member.role in {"artifact", "schema"}
    ]
    package_artifact_ids = [member.artifact_id for member in artifact_members]
    if (
        None in package_artifact_ids
        or len(release_item_ids) != len(set(release_item_ids))
        or len(package_artifact_ids) != len(set(package_artifact_ids))
    ):
        _fail(ExportValidationCode.ARTIFACT_CLOSURE_MISMATCH, "duplicate artifact identity")
    release_items = {item["artifact_id"]: item for item in raw_release_items}
    package_artifacts = {member.artifact_id: member for member in artifact_members}
    if set(package_artifacts) != set(release_items):
        _fail(ExportValidationCode.ARTIFACT_CLOSURE_MISMATCH, "artifact inventory differs")
    for artifact_id, member in package_artifacts.items():
        item = release_items[artifact_id]
        if (
            member.role != ("schema" if item.get("item_type") == "schema" else "artifact")
            or item.get("logical_path") != member.path
            or item.get("media_type") != member.media_type
            or item.get("size_bytes") != member.size_bytes
            or item.get("artifact_hash", {}).get("value") != member.sha256
        ):
            _fail(
                ExportValidationCode.ARTIFACT_CLOSURE_MISMATCH,
                f"artifact identity differs: {artifact_id}",
            )

    return VerifiedImmutableExport(
        package_id=manifest["package_id"],
        package_manifest_hash=declared_manifest_hash,
        release_id=release_id,
        release_schema_version=package_release["release_schema_version"],
        knowledge_cutoff=package_release["knowledge_cutoff"],
        manifest_hash=manifest_hash,
        status_event_hash=status_hash,
        status_sequence=package_release["status_sequence"],
        current_status=head["status"],
        members=tuple(sorted(verified_members, key=lambda item: item.path)),
    )


def reconstruct_official_export_fixture(
    catalog: KBTransportContractCatalog,
) -> tuple[dict[str, Any], Mapping[str, bytes]]:
    """Reconstruct the provider fixture's exact member bytes language-neutrally."""

    example = _object(catalog.official_fixture.get("immutable_export_example"), field="example")
    manifest = _object(example.get("package_manifest"), field="package_manifest")
    members: dict[str, bytes] = {}
    for raw in _array(example.get("file_sources"), field="file_sources"):
        source = _object(raw, field="file_source")
        path = _safe_member_path(source.get("path"))
        if source.get("content_kind") == "canonical-json":
            content = canonical_json_bytes(source.get("value")) + b"\n"
        elif source.get("content_kind") == "canonical-jsonl":
            records = _array(source.get("records"), field="file_source.records")
            content = b"".join(canonical_json_bytes(record) + b"\n" for record in records)
        else:
            _fail(ExportValidationCode.MANIFEST_INVALID, "unknown fixture content kind")
        members[path] = content
    return manifest, MappingProxyType(members)


def verify_immutable_export_zip(
    path: str | Path,
    *,
    catalog: KBTransportContractCatalog,
    package_manifest_path: str = "package-manifest.json",
    max_total_bytes: int = DEFAULT_MAX_PACKAGE_BYTES,
) -> VerifiedImmutableExport:
    """Read a ZIP carrier without extraction and verify its content closure."""

    if (
        isinstance(max_total_bytes, bool)
        or not isinstance(max_total_bytes, int)
        or max_total_bytes < 1
    ):
        raise ValueError("max_total_bytes must be a positive integer")
    manifest_path = _safe_member_path(package_manifest_path)
    carrier = Path(path)
    members: dict[str, bytes] = {}
    seen: set[str] = set()
    total = 0
    try:
        with zipfile.ZipFile(carrier, "r") as archive:
            infos = archive.infolist()
            for info in infos:
                member_path = _safe_member_path(info.filename)
                collision_key = unicodedata.normalize("NFC", member_path).casefold()
                if collision_key in seen or info.is_dir() or info.flag_bits & 0x1:
                    _fail(
                        ExportValidationCode.CARRIER_UNSAFE,
                        "duplicate, directory, or encrypted ZIP member",
                    )
                seen.add(collision_key)
                unix_mode = info.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if file_type not in {0, stat.S_IFREG}:
                    _fail(ExportValidationCode.CARRIER_UNSAFE, "non-regular ZIP member")
                total += info.file_size
                if total > max_total_bytes:
                    _fail(ExportValidationCode.PACKAGE_TOO_LARGE, "ZIP declared size exceeds limit")
                content = archive.read(info)
                if len(content) != info.file_size:
                    _fail(ExportValidationCode.CARRIER_UNSAFE, "ZIP member size differs")
                members[member_path] = content
    except zipfile.BadZipFile as exc:
        raise ImmutableExportValidationError(
            ExportValidationCode.CARRIER_UNSAFE, "invalid ZIP carrier"
        ) from exc
    manifest_bytes = members.pop(manifest_path, None)
    if manifest_bytes is None:
        _fail(ExportValidationCode.MEMBER_SET_MISMATCH, "package manifest carrier member missing")
    manifest = _canonical_json_document(manifest_bytes, source=manifest_path)
    return verify_immutable_export_members(
        package_manifest=manifest,
        members=members,
        catalog=catalog,
    )
