"""Pinned, offline-only InvestmentResearchKB public contract catalog.

The caller must explicitly supply the snapshot root.  This module never
discovers a repository root, imports the provider package, or reads a sibling
checkout.  Every vendored byte is admitted only after the checked-in snapshot
lock, the provider contract locks, and the Stage 6 fixture lock agree.
"""

from __future__ import annotations

import json
import math
import os
import re
import unicodedata
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, NoReturn

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable

from .provider_canonical import CANONICALIZATION_PROFILE, canonical_json_bytes

SNAPSHOT_SCHEMA_VERSION = "1.0.0"
PROVIDER_NAME = "InvestmentResearchKB"
SOURCE_REPOSITORY = "https://github.com/Zhaosheng-Xie/InvestmentResearchKB"
SOURCE_COMMIT = "58ed9c5cb5302e3e719f1696bed83a03c5d6313b"
SOURCE_COMMIT_TREE = "9eb315afc2eef438892d10aeb9549b609fe91031"
SOURCE_CONTRACTS_TREE = "70dde21b860b5a854fa648e5c1550e3f218e7ab1"

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
_CONTRACT_LOCK_PATHS = (
    "contracts/fixtures/contract-locks.v1.json",
    "contracts/fixtures/contract-locks.stage6.v1.json",
)
_STAGE6_FIXTURE_PATH = "contracts/fixtures/stage6-reference-consumer.v1.json"
_STAGE6_FIXTURE_LOCK_PATH = "contracts/fixtures/stage6-reference-consumer.v1.lock.json"
_FIXTURE_SUPPORT_PATHS = {
    "contracts/fixtures/README.md",
    *_CONTRACT_LOCK_PATHS,
    "contracts/fixtures/release-hash-vectors.v1.json",
    _STAGE6_FIXTURE_PATH,
    _STAGE6_FIXTURE_LOCK_PATH,
}
_EXPECTED_SCHEMA_PATHS = {
    "contracts/change-record.v1.schema.json",
    "contracts/context-pack.v1.schema.json",
    "contracts/dataset-release.v1.schema.json",
    "contracts/disclosure-schedule-record.v1.schema.json",
    "contracts/evidence-bundle.v1.schema.json",
    "contracts/evidence.v1.schema.json",
    "contracts/financial-segment-record.v1.schema.json",
    "contracts/financial-statement-record.v1.schema.json",
    "contracts/market-daily-record.v1.schema.json",
    "contracts/release-manifest.v1.schema.json",
    "contracts/release-status-event.v1.schema.json",
    "contracts/source-document-manifest.v1.schema.json",
    "contracts/strategy-input-ref.v1.schema.json",
    "contracts/tushare-financial-precision-manifest.v1.schema.json",
}
_EXPECTED_SNAPSHOT_PATHS = _EXPECTED_SCHEMA_PATHS | _FIXTURE_SUPPORT_PATHS

_DATASET_RELEASE_ID = "urn:investment-research-kb:contract:dataset-release:v1"
_RELEASE_MANIFEST_ID = "urn:investment-research-kb:contract:release-manifest:v1"
_CHANGE_RECORD_ID = "urn:investment-research-kb:contract:change-record:v1"
_STRATEGY_INPUT_REF_ID = "urn:investment-research-kb:contract:strategy-input-ref:v1"


class ContractSnapshotError(ValueError):
    """Base class for fail-closed snapshot and public-contract errors."""


class StrictJsonError(ContractSnapshotError):
    """A JSON byte sequence is ambiguous or outside the strict input profile."""


class SnapshotIntegrityError(ContractSnapshotError):
    """Vendored bytes do not match the pinned snapshot identity."""


class ContractValidationError(ContractSnapshotError):
    """A provider lock, Schema, or official fixture is invalid or unsupported."""


@dataclass(frozen=True, slots=True)
class SnapshotFile:
    """Physical identity of one path relative to the snapshot vendor root."""

    relative_path: str
    git_blob: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True, slots=True)
class SchemaContract:
    """Provider-declared physical and semantic identity of one JSON Schema."""

    relative_path: str
    contract_id: str
    schema_version: str
    canonical_sha256: str
    file_sha256: str


def _raise_non_finite(token: str) -> NoReturn:
    raise StrictJsonError(f"non-finite JSON number is prohibited: {token}")


def _parse_finite_float(token: str) -> float:
    value = float(token)
    if not math.isfinite(value):
        raise StrictJsonError(f"non-finite JSON number is prohibited: {token}")
    return value


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    normalized_keys: dict[str, str] = {}
    for key, value in pairs:
        if key in result:
            raise StrictJsonError(f"duplicate JSON object key: {key!r}")
        normalized = unicodedata.normalize("NFC", key)
        prior = normalized_keys.get(normalized)
        if prior is not None:
            raise StrictJsonError(f"NFC JSON key collision: {prior!r} and {key!r}")
        normalized_keys[normalized] = key
        result[key] = value
    return result


def load_strict_json_bytes(content: bytes, *, source: str = "<bytes>") -> Any:
    """Parse one UTF-8 JSON value without duplicate/NFC-colliding keys or NaN.

    Provider string normalization remains the responsibility of the pinned
    provider canonicalizer.  Parsing preserves source strings while rejecting
    object-key ambiguity before a canonical hash is calculated.
    """

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    try:
        text = content.decode("utf-8")
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_raise_non_finite,
            parse_float=_parse_finite_float,
        )
    except StrictJsonError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StrictJsonError(f"invalid strict UTF-8 JSON in {source}: {exc}") from exc


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError(f"{field} must be a JSON object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field} must be a JSON array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{field} must be a non-empty string")
    return value


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        raise ContractValidationError(f"{field} must be a non-negative integer")
    if not isinstance(value, int):
        raise ContractValidationError(f"{field} must be a non-negative integer")
    if value < 0:
        raise ContractValidationError(f"{field} must be a non-negative integer")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], *, field: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise ContractValidationError(
            f"{field} keys differ; missing={missing!r}, unknown={unknown!r}"
        )


def _digest_object(value: object, *, field: str) -> str:
    digest = _object(value, field=field)
    _exact_keys(digest, {"algorithm", "value"}, field=field)
    if digest["algorithm"] != "sha256":
        raise ContractValidationError(f"{field}.algorithm must be 'sha256'")
    result = _text(digest["value"], field=f"{field}.value")
    if _SHA256_RE.fullmatch(result) is None:
        raise ContractValidationError(f"{field}.value must be lowercase SHA-256")
    return result


def _relative_path(value: object, *, field: str) -> str:
    raw = _text(value, field=field)
    if "\\" in raw:
        raise ContractValidationError(f"{field} must use POSIX separators")
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or raw in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ContractValidationError(f"{field} must be a safe relative path")
    normalized = path.as_posix()
    if normalized != raw:
        raise ContractValidationError(f"{field} must be a normalized relative path")
    return normalized


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _assert_regular_owned_path(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    current = root
    if _is_link_or_junction(current):
        raise SnapshotIntegrityError(f"snapshot root must not be a link: {root}")
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if _is_link_or_junction(current):
            raise SnapshotIntegrityError(f"snapshot path must not contain links: {relative_path}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
    except OSError as exc:
        raise SnapshotIntegrityError(f"snapshot file is missing: {relative_path}") from exc
    if not resolved_candidate.is_relative_to(resolved_root) or not resolved_candidate.is_file():
        raise SnapshotIntegrityError(
            f"snapshot path is not a regular in-root file: {relative_path}"
        )
    try:
        if os.stat(resolved_candidate).st_nlink != 1:
            raise SnapshotIntegrityError(f"snapshot file must not be hard-linked: {relative_path}")
    except OSError as exc:
        raise SnapshotIntegrityError(f"cannot inspect snapshot file: {relative_path}") from exc
    return resolved_candidate


def _read_unlocked_snapshot_file(snapshot_root: Path, relative_path: str) -> bytes:
    path = _assert_regular_owned_path(snapshot_root, relative_path)
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SnapshotIntegrityError(f"cannot read snapshot file: {relative_path}") from exc


def _git_blob_id(content: bytes) -> str:
    """Return the source Git SHA-1 blob identity for exact file bytes."""

    header = f"blob {len(content)}\0".encode("ascii")
    return sha1(header + content, usedforsecurity=False).hexdigest()


def _parse_snapshot_files(value: object) -> dict[str, SnapshotFile]:
    entries: dict[str, SnapshotFile] = {}
    for index, raw_entry in enumerate(_array(value, field="snapshot-lock.files")):
        entry = _object(raw_entry, field=f"snapshot-lock.files[{index}]")
        _exact_keys(
            entry,
            {"path", "git_blob", "size_bytes", "sha256"},
            field=f"snapshot-lock.files[{index}]",
        )
        path = _relative_path(entry["path"], field=f"snapshot-lock.files[{index}].path")
        if path in entries:
            raise ContractValidationError(f"duplicate snapshot path: {path}")
        git_blob = _text(entry["git_blob"], field=f"snapshot-lock.files[{index}].git_blob")
        if _GIT_OBJECT_RE.fullmatch(git_blob) is None:
            raise ContractValidationError(f"invalid Git blob identity for {path}")
        digest = _text(entry["sha256"], field=f"snapshot-lock.files[{index}].sha256")
        if _SHA256_RE.fullmatch(digest) is None:
            raise ContractValidationError(f"invalid snapshot SHA-256 for {path}")
        entries[path] = SnapshotFile(
            relative_path=path,
            git_blob=git_blob,
            size_bytes=_integer(
                entry["size_bytes"], field=f"snapshot-lock.files[{index}].size_bytes"
            ),
            sha256=digest,
        )
    if set(entries) != _EXPECTED_SNAPSHOT_PATHS:
        raise ContractValidationError("snapshot file inventory is not the fixed Stage 2A selection")
    return entries


class KBContractCatalog:
    """A verified catalog over one caller-supplied immutable snapshot root."""

    __slots__ = (
        "_registry",
        "_schema_by_id",
        "_schema_contracts",
        "_snapshot_files",
        "_stage6_fixture",
        "_vendor_root",
        "snapshot_root",
        "source_commit",
    )

    def __init__(
        self,
        *,
        snapshot_root: Path,
        vendor_root: Path,
        source_commit: str,
        snapshot_files: Mapping[str, SnapshotFile],
        schema_contracts: tuple[SchemaContract, ...],
        schemas: Mapping[str, dict[str, Any]],
        stage6_fixture: dict[str, Any],
    ) -> None:
        self.snapshot_root = snapshot_root
        self._vendor_root = vendor_root
        self.source_commit = source_commit
        self._snapshot_files = MappingProxyType(dict(snapshot_files))
        self._schema_contracts = schema_contracts
        self._schema_by_id = {key: deepcopy(value) for key, value in schemas.items()}
        registry: Registry[Any] = Registry()
        for contract_id, schema in self._schema_by_id.items():
            registry = registry.with_resource(contract_id, Resource.from_contents(schema))
        self._registry = registry
        self._stage6_fixture = deepcopy(stage6_fixture)

    @property
    def schema_contracts(self) -> tuple[SchemaContract, ...]:
        return self._schema_contracts

    @property
    def schema_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._schema_by_id))

    @property
    def stage6_fixture(self) -> dict[str, Any]:
        return deepcopy(self._stage6_fixture)

    def read_vendor_bytes(self, relative_path: str) -> bytes:
        """Read one locked vendor file and recheck its physical identity."""

        normalized = _relative_path(relative_path, field="relative_path")
        locked = self._snapshot_files.get(normalized)
        if locked is None:
            raise SnapshotIntegrityError(
                f"vendor path is not present in snapshot lock: {normalized}"
            )
        content = _read_unlocked_snapshot_file(self._vendor_root, normalized)
        if len(content) != locked.size_bytes:
            raise SnapshotIntegrityError(f"snapshot size mismatch: {normalized}")
        if sha256(content).hexdigest() != locked.sha256:
            raise SnapshotIntegrityError(f"snapshot SHA-256 mismatch: {normalized}")
        if _git_blob_id(content) != locked.git_blob:
            raise SnapshotIntegrityError(f"snapshot Git blob mismatch: {normalized}")
        return content

    def load_vendor_json(self, relative_path: str) -> Any:
        """Strictly parse one locked JSON file from the vendor root."""

        return load_strict_json_bytes(
            self.read_vendor_bytes(relative_path),
            source=relative_path,
        )

    def schema_for_id(self, contract_id: str) -> dict[str, Any]:
        """Return a detached copy of a verified provider Schema."""

        try:
            return deepcopy(self._schema_by_id[contract_id])
        except KeyError as exc:
            raise ContractValidationError(f"unknown provider contract id: {contract_id}") from exc

    def validate_instance(self, contract_id: str, instance: Any) -> None:
        """Validate an instance with Draft 2020-12 and active format checks."""

        schema = self._schema_by_id.get(contract_id)
        if schema is None:
            raise ContractValidationError(f"unknown provider contract id: {contract_id}")
        try:
            Draft202012Validator(
                schema,
                registry=self._registry,
                format_checker=FormatChecker(),
            ).validate(instance)
        except (ValidationError, Unresolvable) as exc:
            raise ContractValidationError(
                f"instance does not satisfy provider contract {contract_id}: {exc.message}"
                if isinstance(exc, ValidationError)
                else f"provider contract reference cannot be resolved: {exc}"
            ) from exc


def _load_snapshot_lock(snapshot_root: Path) -> tuple[Path, dict[str, SnapshotFile]]:
    raw = load_strict_json_bytes(
        _read_unlocked_snapshot_file(snapshot_root, "snapshot-lock.json"),
        source="snapshot-lock.json",
    )
    lock = _object(raw, field="snapshot-lock")
    _exact_keys(
        lock,
        {
            "schema_version",
            "provider",
            "source_repository",
            "source_commit",
            "source_commit_tree",
            "source_contracts_tree",
            "retrieval_method",
            "canonicalization_profile",
            "vendor_root",
            "selection",
            "files",
        },
        field="snapshot-lock",
    )
    expected_scalars = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "provider": PROVIDER_NAME,
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "retrieval_method": "git_object",
        "canonicalization_profile": CANONICALIZATION_PROFILE,
        "vendor_root": "vendor",
    }
    for field, expected in expected_scalars.items():
        if lock[field] != expected:
            raise ContractValidationError(f"snapshot-lock.{field} is not the fixed value")
    for field in ("source_commit_tree", "source_contracts_tree"):
        value = _text(lock[field], field=f"snapshot-lock.{field}")
        if _GIT_OBJECT_RE.fullmatch(value) is None:
            raise ContractValidationError(f"snapshot-lock.{field} must be a Git object ID")
    if lock["source_commit_tree"] != SOURCE_COMMIT_TREE:
        raise ContractValidationError("snapshot-lock.source_commit_tree is not the fixed value")
    if lock["source_contracts_tree"] != SOURCE_CONTRACTS_TREE:
        raise ContractValidationError("snapshot-lock.source_contracts_tree is not the fixed value")
    _text(lock["selection"], field="snapshot-lock.selection")
    files = _parse_snapshot_files(lock["files"])

    vendor_root = snapshot_root / "vendor"
    if _is_link_or_junction(vendor_root) or not vendor_root.is_dir():
        raise SnapshotIntegrityError("snapshot vendor root must be an ordinary directory")
    actual_paths: set[str] = set()
    for path in vendor_root.rglob("*"):
        if _is_link_or_junction(path):
            raise SnapshotIntegrityError("snapshot vendor tree contains a link")
        if path.is_file():
            actual_paths.add(path.relative_to(vendor_root).as_posix())
    if actual_paths != set(files):
        raise SnapshotIntegrityError("snapshot vendor inventory differs from snapshot lock")
    for entry in files.values():
        content = _read_unlocked_snapshot_file(vendor_root, entry.relative_path)
        if len(content) != entry.size_bytes:
            raise SnapshotIntegrityError(f"snapshot size mismatch: {entry.relative_path}")
        if sha256(content).hexdigest() != entry.sha256:
            raise SnapshotIntegrityError(f"snapshot SHA-256 mismatch: {entry.relative_path}")
        if _git_blob_id(content) != entry.git_blob:
            raise SnapshotIntegrityError(f"snapshot Git blob mismatch: {entry.relative_path}")
    return vendor_root, files


def _parse_contract_entry(raw_entry: object, *, location: str) -> SchemaContract:
    entry = _object(raw_entry, field=location)
    _exact_keys(
        entry,
        {
            "path",
            "contract_id",
            "schema_version",
            "canonical_sha256",
            "file_sha256",
        },
        field=location,
    )
    schema_path = _relative_path(entry["path"], field=f"{location}.path")
    relative_path = f"contracts/{schema_path}"
    return SchemaContract(
        relative_path=relative_path,
        contract_id=_text(entry["contract_id"], field=f"{location}.contract_id"),
        schema_version=_text(entry["schema_version"], field=f"{location}.schema_version"),
        canonical_sha256=_digest_object(
            entry["canonical_sha256"], field=f"{location}.canonical_sha256"
        ),
        file_sha256=_digest_object(entry["file_sha256"], field=f"{location}.file_sha256"),
    )


def _load_schema_contracts(
    catalog: KBContractCatalog,
) -> tuple[tuple[SchemaContract, ...], dict[str, dict[str, Any]]]:
    entries: list[SchemaContract] = []
    for lock_path in _CONTRACT_LOCK_PATHS:
        raw_lock = _object(catalog.load_vendor_json(lock_path), field=lock_path)
        _exact_keys(raw_lock, {"schema_version", "purpose", "contracts"}, field=lock_path)
        if raw_lock["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
            raise ContractValidationError(f"unsupported contract lock version: {lock_path}")
        _text(raw_lock["purpose"], field=f"{lock_path}.purpose")
        for index, raw_entry in enumerate(
            _array(raw_lock["contracts"], field=f"{lock_path}.contracts")
        ):
            entries.append(
                _parse_contract_entry(raw_entry, location=f"{lock_path}.contracts[{index}]")
            )

    paths = [entry.relative_path for entry in entries]
    ids = [entry.contract_id for entry in entries]
    if len(paths) != len(set(paths)) or len(ids) != len(set(ids)):
        raise ContractValidationError(
            "provider contract locks contain duplicate path or contract ID"
        )
    if set(paths) != _EXPECTED_SCHEMA_PATHS or len(entries) != 14:
        raise ContractValidationError(
            "the two official contract locks must cover exactly 14 Schemas"
        )

    schemas: dict[str, dict[str, Any]] = {}
    for entry in entries:
        content = catalog.read_vendor_bytes(entry.relative_path)
        physical_hash = sha256(content).hexdigest()
        if physical_hash != entry.file_sha256:
            raise SnapshotIntegrityError(
                f"provider file hash disagrees with snapshot: {entry.relative_path}"
            )
        schema = _object(
            load_strict_json_bytes(content, source=entry.relative_path),
            field=entry.relative_path,
        )
        if sha256(canonical_json_bytes(schema)).hexdigest() != entry.canonical_sha256:
            raise SnapshotIntegrityError(f"provider canonical hash mismatch: {entry.relative_path}")
        if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
            raise ContractValidationError(
                f"Schema does not declare Draft 2020-12: {entry.relative_path}"
            )
        if schema.get("$id") != entry.contract_id:
            raise ContractValidationError(
                f"Schema ID disagrees with contract lock: {entry.relative_path}"
            )
        schema_version = (
            schema.get("properties", {}).get("schema_version", {}).get("const")
            if isinstance(schema.get("properties"), dict)
            else None
        )
        if schema_version != entry.schema_version:
            raise ContractValidationError(
                f"Schema version disagrees with contract lock: {entry.relative_path}"
            )
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ContractValidationError(
                f"invalid provider Schema: {entry.relative_path}"
            ) from exc
        schemas[entry.contract_id] = schema
    return tuple(sorted(entries, key=lambda item: item.contract_id)), schemas


def _verify_stage6_fixture_lock(catalog: KBContractCatalog) -> None:
    fixture_lock = _object(
        catalog.load_vendor_json(_STAGE6_FIXTURE_LOCK_PATH),
        field=_STAGE6_FIXTURE_LOCK_PATH,
    )
    _exact_keys(
        fixture_lock,
        {"schema_version", "path", "file_sha256"},
        field=_STAGE6_FIXTURE_LOCK_PATH,
    )
    if fixture_lock["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ContractValidationError("unsupported Stage 6 fixture lock version")
    locked_name = _relative_path(fixture_lock["path"], field="stage6 fixture lock path")
    expected_name = PurePosixPath(_STAGE6_FIXTURE_PATH).name
    if locked_name != expected_name:
        raise ContractValidationError("Stage 6 fixture lock targets an unexpected path")
    expected_hash = _digest_object(
        fixture_lock["file_sha256"], field="stage6 fixture lock file_sha256"
    )
    actual_hash = sha256(catalog.read_vendor_bytes(_STAGE6_FIXTURE_PATH)).hexdigest()
    if actual_hash != expected_hash:
        raise SnapshotIntegrityError("Stage 6 fixture hash disagrees with its official lock")


def _validate_stage6_fixture(catalog: KBContractCatalog, fixture: dict[str, Any]) -> None:
    if fixture.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ContractValidationError("unsupported Stage 6 reference fixture version")
    releases = _array(fixture.get("releases"), field="stage6 fixture releases")
    for release_index, raw_release in enumerate(releases):
        release = _object(raw_release, field=f"stage6 fixture releases[{release_index}]")
        _exact_keys(
            release,
            {"dataset_release", "manifest", "artifacts"},
            field=f"stage6 fixture releases[{release_index}]",
        )
        dataset_release = _object(
            release["dataset_release"],
            field=f"stage6 fixture releases[{release_index}].dataset_release",
        )
        manifest = _object(
            release["manifest"], field=f"stage6 fixture releases[{release_index}].manifest"
        )
        artifacts = _object(
            release["artifacts"], field=f"stage6 fixture releases[{release_index}].artifacts"
        )
        catalog.validate_instance(_DATASET_RELEASE_ID, dataset_release)
        catalog.validate_instance(_RELEASE_MANIFEST_ID, manifest)
        if dataset_release.get("release_id") != manifest.get("release_id"):
            raise ContractValidationError("Stage 6 dataset Release and Manifest IDs differ")

        release_items = _array(
            manifest.get("release_items"),
            field=f"stage6 fixture releases[{release_index}].manifest.release_items",
        )
        artifact_ids: set[str] = set()
        for item_index, raw_item in enumerate(release_items):
            item = _object(
                raw_item,
                field=(
                    f"stage6 fixture releases[{release_index}].manifest.release_items[{item_index}]"
                ),
            )
            artifact_id = _text(item.get("artifact_id"), field="release item artifact_id")
            if artifact_id in artifact_ids:
                raise ContractValidationError("Stage 6 fixture has duplicate artifact_id")
            artifact_ids.add(artifact_id)
            if artifact_id not in artifacts:
                raise ContractValidationError("Stage 6 fixture is missing a declared artifact")
            schema_id = _text(item.get("record_schema_id"), field="release item schema ID")
            catalog.schema_for_id(schema_id)
            if item.get("item_type") == "schema":
                pointer = _object(artifacts[artifact_id], field=f"artifact {artifact_id}")
                _exact_keys(pointer, {"fixture_contract_file"}, field=f"artifact {artifact_id}")
                pointed_name = _relative_path(
                    pointer["fixture_contract_file"], field="fixture_contract_file"
                )
                expected_contract = next(
                    (
                        contract
                        for contract in catalog.schema_contracts
                        if contract.contract_id == schema_id
                    ),
                    None,
                )
                if (
                    expected_contract is None
                    or PurePosixPath(expected_contract.relative_path).name != pointed_name
                ):
                    raise ContractValidationError(
                        "Stage 6 Schema artifact points to another contract"
                    )
            else:
                catalog.validate_instance(schema_id, artifacts[artifact_id])
        if set(artifacts) != artifact_ids:
            raise ContractValidationError("Stage 6 fixture contains an undeclared artifact")

    for index, change in enumerate(_array(fixture.get("changes"), field="stage6 fixture changes")):
        if not isinstance(change, dict):
            raise ContractValidationError(f"stage6 fixture changes[{index}] must be an object")
        catalog.validate_instance(_CHANGE_RECORD_ID, change)
    expected_ref = _object(
        fixture.get("expected_strategy_input_ref"),
        field="stage6 fixture expected_strategy_input_ref",
    )
    catalog.validate_instance(_STRATEGY_INPUT_REF_ID, expected_ref)


def load_kb_contract_snapshot(snapshot_root: str | Path) -> KBContractCatalog:
    """Load and completely verify the fixed KB v1 public contract snapshot.

    The supplied directory must directly contain ``snapshot-lock.json`` and
    ``vendor/``.  No default path exists by design.
    """

    root = Path(snapshot_root).absolute()
    if _is_link_or_junction(root) or not root.is_dir():
        raise SnapshotIntegrityError("snapshot_root must be an existing ordinary directory")
    vendor_root, snapshot_files = _load_snapshot_lock(root)

    # Build a temporary catalog so all subsequent reads use the same locked,
    # path-safe API.  It is replaced after Schema and fixture verification.
    preliminary = KBContractCatalog(
        snapshot_root=root,
        vendor_root=vendor_root,
        source_commit=SOURCE_COMMIT,
        snapshot_files=snapshot_files,
        schema_contracts=(),
        schemas={},
        stage6_fixture={},
    )
    schema_contracts, schemas = _load_schema_contracts(preliminary)
    fixture = _object(
        preliminary.load_vendor_json(_STAGE6_FIXTURE_PATH),
        field=_STAGE6_FIXTURE_PATH,
    )
    catalog = KBContractCatalog(
        snapshot_root=root,
        vendor_root=vendor_root,
        source_commit=SOURCE_COMMIT,
        snapshot_files=snapshot_files,
        schema_contracts=schema_contracts,
        schemas=schemas,
        stage6_fixture=fixture,
    )
    _verify_stage6_fixture_lock(catalog)
    _validate_stage6_fixture(catalog, fixture)
    return catalog
