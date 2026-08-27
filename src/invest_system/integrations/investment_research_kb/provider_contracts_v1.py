"""Pinned offline catalog for the generic KB Stage 6 provider contracts.

The caller supplies an InvestSystem-owned snapshot directory. This module
never discovers or reads a sibling KB repository and performs no transport or
storage I/O beyond the checked-in snapshot bytes.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource

from .contracts import load_strict_json_bytes

SNAPSHOT_SCHEMA_VERSION = "1.0.0"
SOURCE_COMMIT = "4352c10c6c639e25d4c190dfc9ec58ee9e76aa86"
PROVIDER_CONTRACT_COMMIT = "50604ea46e14580be976e1cf46c349a2d3088740"
IS_APPROVAL_COMMIT = "eb702559511083d2d0d603725be50997e0c22bbe"
CATALOG_PATH = "contracts/fixtures/provider-contract-catalog.v1.json"
REGISTRY_PATH = "contracts/fixtures/provider-benchmark-factor-registry.v1.json"
FIXTURE_PATH = "contracts/fixtures/provider-contract-synthetic-fixtures.v1.json"
EXPECTED_FILE_COUNT = 19


class ProviderContractSnapshotError(ValueError):
    """Stable fail-closed provider-contract snapshot error."""


@dataclass(frozen=True, slots=True)
class ProviderSnapshotFile:
    relative_path: str
    git_blob: str
    size_bytes: int
    sha256: str


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderContractSnapshotError(f"{field} must be an object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProviderContractSnapshotError(f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ProviderContractSnapshotError(f"{field} must be non-empty text")
    return value


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProviderContractSnapshotError(f"{field} must be a non-negative integer")
    return value


def _safe_path(value: object, *, field: str) -> str:
    raw = _text(value, field=field)
    if "\\" in raw:
        raise ProviderContractSnapshotError(f"{field} must use POSIX separators")
    path = PurePosixPath(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ProviderContractSnapshotError(f"{field} is not a safe relative path")
    if path.as_posix() != raw:
        raise ProviderContractSnapshotError(f"{field} is not normalized")
    return raw


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _regular_snapshot_file(root: Path, relative_path: str) -> Path:
    if _is_link_or_junction(root):
        raise ProviderContractSnapshotError("snapshot root must not be a link")
    current = root
    for part in PurePosixPath(relative_path).parts:
        current = current / part
        if _is_link_or_junction(current):
            raise ProviderContractSnapshotError(
                f"snapshot path must not contain links: {relative_path}"
            )
    try:
        resolved_root = root.resolve(strict=True)
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise ProviderContractSnapshotError(f"snapshot file is missing: {relative_path}") from exc
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ProviderContractSnapshotError(f"snapshot file leaves its root: {relative_path}")
    try:
        if os.stat(resolved).st_nlink != 1:
            raise ProviderContractSnapshotError(
                f"snapshot file must not be hard-linked: {relative_path}"
            )
    except OSError as exc:
        raise ProviderContractSnapshotError(f"cannot inspect: {relative_path}") from exc
    return resolved


def _git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return sha1(header + content, usedforsecurity=False).hexdigest()


def _load_json_bytes(content: bytes, *, source: str) -> dict[str, Any]:
    return _object(load_strict_json_bytes(content, source=source), field=source)


def _load_lock(root: Path) -> tuple[dict[str, Any], dict[str, ProviderSnapshotFile]]:
    lock_path = _regular_snapshot_file(root, "snapshot-lock.json")
    lock = _load_json_bytes(lock_path.read_bytes(), source="snapshot-lock.json")
    expected_scalars = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "provider": "InvestmentResearchKB",
        "source_commit": SOURCE_COMMIT,
        "provider_contract_commit": PROVIDER_CONTRACT_COMMIT,
        "retrieval_method": "git_object",
        "catalog_path": CATALOG_PATH,
        "transport_protocol": "v1",
        "transport_semantics_changed": False,
        "runtime_authority": False,
    }
    for field, expected in expected_scalars.items():
        if lock.get(field) != expected:
            raise ProviderContractSnapshotError(f"snapshot-lock.{field} differs")
    entries: dict[str, ProviderSnapshotFile] = {}
    for index, raw in enumerate(_array(lock.get("files"), field="snapshot-lock.files")):
        item = _object(raw, field=f"snapshot-lock.files[{index}]")
        if set(item) != {"path", "git_blob", "size_bytes", "sha256"}:
            raise ProviderContractSnapshotError("snapshot file entry fields differ")
        path = _safe_path(item["path"], field=f"snapshot-lock.files[{index}].path")
        if path in entries:
            raise ProviderContractSnapshotError(f"duplicate snapshot path: {path}")
        blob = _text(item["git_blob"], field="git_blob")
        digest = _text(item["sha256"], field="sha256")
        if len(blob) != 40 or len(digest) != 64:
            raise ProviderContractSnapshotError(f"invalid lock digest: {path}")
        entries[path] = ProviderSnapshotFile(
            relative_path=path,
            git_blob=blob,
            size_bytes=_integer(item["size_bytes"], field="size_bytes"),
            sha256=digest,
        )
    if len(entries) != EXPECTED_FILE_COUNT or CATALOG_PATH not in entries:
        raise ProviderContractSnapshotError("snapshot inventory count or catalog differs")
    return lock, entries


def _catalog_schema_paths(catalog: Mapping[str, Any]) -> tuple[set[str], dict[str, str]]:
    supporting = _object(catalog.get("supporting_schema"), field="supporting_schema")
    paths = {f"contracts/{_safe_path(supporting.get('path'), field='supporting_schema.path')}"}
    expected_hashes = {next(iter(paths)): _text(supporting.get("sha256"), field="sha256")}
    active = _array(catalog.get("active_provider_drafts"), field="active_provider_drafts")
    if len(active) != 15:
        raise ProviderContractSnapshotError("active provider Schema count differs")
    for raw in active:
        item = _object(raw, field="active_provider_draft")
        path = f"contracts/{_safe_path(item.get('path'), field='active path')}"
        if path in paths:
            raise ProviderContractSnapshotError(f"duplicate active Schema path: {path}")
        paths.add(path)
        expected_hashes[path] = _text(item.get("sha256"), field="active sha256")
    return paths, expected_hashes


class Stage6ProviderContractCatalog:
    """Completely verified generic provider-contract draft catalog."""

    __slots__ = (
        "_registry",
        "_provider_catalog",
        "_registry_document",
        "_schemas_by_id",
        "_schemas_by_path",
        "_snapshot_files",
        "snapshot_root",
        "_synthetic_fixture",
    )

    def __init__(
        self,
        *,
        snapshot_root: Path,
        snapshot_files: Mapping[str, ProviderSnapshotFile],
        schemas_by_id: Mapping[str, dict[str, Any]],
        schemas_by_path: Mapping[str, dict[str, Any]],
        registry: Registry[Any],
        provider_catalog: dict[str, Any],
        registry_document: dict[str, Any],
        synthetic_fixture: dict[str, Any],
    ) -> None:
        self.snapshot_root = snapshot_root
        self._snapshot_files = MappingProxyType(dict(snapshot_files))
        self._schemas_by_id = MappingProxyType(
            {key: deepcopy(value) for key, value in schemas_by_id.items()}
        )
        self._schemas_by_path = MappingProxyType(
            {key: deepcopy(value) for key, value in schemas_by_path.items()}
        )
        self._registry = registry
        self._provider_catalog = deepcopy(provider_catalog)
        self._registry_document = deepcopy(registry_document)
        self._synthetic_fixture = deepcopy(synthetic_fixture)

    @property
    def schema_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._schemas_by_id))

    @property
    def schema_paths(self) -> tuple[str, ...]:
        return tuple(sorted(self._schemas_by_path))

    @property
    def provider_catalog(self) -> dict[str, Any]:
        return deepcopy(self._provider_catalog)

    @property
    def registry_document(self) -> dict[str, Any]:
        return deepcopy(self._registry_document)

    @property
    def synthetic_fixture(self) -> dict[str, Any]:
        return deepcopy(self._synthetic_fixture)

    def schema_for_path(self, relative_contract_path: str) -> dict[str, Any]:
        path = f"contracts/{_safe_path(relative_contract_path, field='schema path')}"
        try:
            return deepcopy(self._schemas_by_path[path])
        except KeyError as exc:
            raise ProviderContractSnapshotError(f"unknown provider Schema path: {path}") from exc

    def validate_schema_path(self, relative_contract_path: str, value: object) -> None:
        schema = self.schema_for_path(relative_contract_path)
        try:
            Draft202012Validator(
                schema,
                registry=self._registry,
                format_checker=FormatChecker(),
            ).validate(value)
        except ValidationError as exc:
            raise ProviderContractSnapshotError(
                f"provider instance violates {relative_contract_path}: {exc.message}"
            ) from exc


def load_stage6_provider_contract_snapshot(
    snapshot_root: str | Path,
) -> Stage6ProviderContractCatalog:
    """Load and completely verify the pinned generic KB provider-contract snapshot."""

    root = Path(snapshot_root).absolute()
    if not root.is_dir() or _is_link_or_junction(root):
        raise ProviderContractSnapshotError("snapshot_root must be an ordinary directory")
    lock, files = _load_lock(root)
    vendor_root = root / "vendor"
    if not vendor_root.is_dir() or _is_link_or_junction(vendor_root):
        raise ProviderContractSnapshotError("snapshot vendor root must be an ordinary directory")
    actual = {
        path.relative_to(vendor_root).as_posix()
        for path in vendor_root.rglob("*")
        if path.is_file()
    }
    if actual != set(files):
        raise ProviderContractSnapshotError("snapshot vendor inventory differs from lock")

    contents: dict[str, bytes] = {}
    for path, entry in files.items():
        content = _regular_snapshot_file(vendor_root, path).read_bytes()
        if (
            len(content) != entry.size_bytes
            or sha256(content).hexdigest() != entry.sha256
            or _git_blob_id(content) != entry.git_blob
        ):
            raise ProviderContractSnapshotError(f"snapshot physical identity differs: {path}")
        contents[path] = content

    catalog_bytes = contents[CATALOG_PATH]
    if sha256(catalog_bytes).hexdigest() != lock.get("catalog_raw_sha256"):
        raise ProviderContractSnapshotError("provider catalog raw SHA-256 differs")
    catalog = _load_json_bytes(catalog_bytes, source=CATALOG_PATH)
    if catalog.get("status") != "DRAFT_ZERO_RUNTIME_AUTHORITY":
        raise ProviderContractSnapshotError("provider catalog is not zero-authority draft")
    governance = _object(catalog.get("governance"), field="catalog.governance")
    if governance.get("is_approval_commit") != IS_APPROVAL_COMMIT:
        raise ProviderContractSnapshotError("provider catalog IS approval binding differs")
    authorization = _object(
        catalog.get("authorization_boundary"), field="catalog.authorization_boundary"
    )
    if not authorization or any(value is not False for value in authorization.values()):
        raise ProviderContractSnapshotError("provider catalog grants runtime authority")

    schema_paths, expected_hashes = _catalog_schema_paths(catalog)
    registries = _array(catalog.get("registries"), field="catalog.registries")
    synthetic = _object(catalog.get("synthetic_fixture"), field="catalog.synthetic_fixture")
    expected_inventory = {
        CATALOG_PATH,
        REGISTRY_PATH,
        FIXTURE_PATH,
        *schema_paths,
    }
    if expected_inventory != set(files):
        raise ProviderContractSnapshotError("catalog and snapshot inventories differ")
    expected_hashes[REGISTRY_PATH] = _text(registries[0].get("sha256"), field="registry sha")
    expected_hashes[FIXTURE_PATH] = _text(synthetic.get("sha256"), field="fixture sha")
    for path, expected in expected_hashes.items():
        if sha256(contents[path]).hexdigest() != expected:
            raise ProviderContractSnapshotError(f"catalog hash differs: {path}")

    schemas_by_id: dict[str, dict[str, Any]] = {}
    schemas_by_path: dict[str, dict[str, Any]] = {}
    registry: Registry[Any] = Registry()
    for path in sorted(schema_paths):
        schema = _load_json_bytes(contents[path], source=path)
        schema_id = _text(schema.get("$id"), field=f"{path}.$id")
        if schema_id in schemas_by_id:
            raise ProviderContractSnapshotError(f"duplicate Schema ID: {schema_id}")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ProviderContractSnapshotError(f"invalid provider Schema: {path}") from exc
        schemas_by_id[schema_id] = schema
        schemas_by_path[path] = schema
        registry = registry.with_resource(schema_id, Resource.from_contents(schema))

    registry_document = _load_json_bytes(contents[REGISTRY_PATH], source=REGISTRY_PATH)
    fixture = _load_json_bytes(contents[FIXTURE_PATH], source=FIXTURE_PATH)
    if registry_document.get("status") != "DRAFT_ZERO_RUNTIME_AUTHORITY" or (
        fixture.get("status") != "DRAFT_SYNTHETIC_ONLY_ZERO_RUNTIME_AUTHORITY"
    ):
        raise ProviderContractSnapshotError("registry or fixture authority status differs")
    for boundary_name, document in (
        ("registry", registry_document),
        ("fixture", fixture),
    ):
        boundary = _object(document.get("authorization_boundary"), field=boundary_name)
        if not boundary or any(value is not False for value in boundary.values()):
            raise ProviderContractSnapshotError(f"{boundary_name} grants runtime authority")

    catalog_object = Stage6ProviderContractCatalog(
        snapshot_root=root,
        snapshot_files=files,
        schemas_by_id=schemas_by_id,
        schemas_by_path=schemas_by_path,
        registry=registry,
        provider_catalog=catalog,
        registry_document=registry_document,
        synthetic_fixture=fixture,
    )
    schema_id_paths = {
        "benchmark_identities": "drafts/benchmark-identity.v1.schema.json",
        "factor_definitions": "drafts/factor-definition.v1.schema.json",
    }
    for collection, path in schema_id_paths.items():
        for value in _array(registry_document.get(collection), field=collection):
            catalog_object.validate_schema_path(path, value)
    examples = _object(fixture.get("examples"), field="fixture.examples")
    for path, values in examples.items():
        if not isinstance(path, str):
            raise ProviderContractSnapshotError("fixture Schema path must be text")
        for value in _array(values, field=f"fixture.examples.{path}"):
            catalog_object.validate_schema_path(path, value)
    return catalog_object
