"""Verified Stage 6B public transport contracts pinned from KB Git objects.

The transport snapshot extends, but never replaces, the Stage 2A core data
contract snapshot.  Both roots are caller supplied through one explicit local
snapshot root; no sibling checkout discovery or provider-package import exists.
"""

from __future__ import annotations

import os
import re
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError, ValidationError
from referencing import Registry, Resource
from referencing.exceptions import Unresolvable

from .contracts import (
    ContractValidationError,
    KBContractCatalog,
    SnapshotIntegrityError,
    load_kb_contract_snapshot,
    load_strict_json_bytes,
)
from .provider_canonical import CANONICALIZATION_PROFILE, canonical_json_bytes

TRANSPORT_SOURCE_COMMIT = "aab36fe229104779b50ec71e2dc37a9fad81d285"
TRANSPORT_SOURCE_COMMIT_TREE = "ab64c1cab45eb646ee767e25a50fb78ef3cc57c8"
TRANSPORT_SOURCE_CONTRACTS_TREE = "ff106b15c815e5d34a2675827485d2b5576e3f7b"
TRANSPORT_SCHEMA_VERSION = "1.0.0"
TRANSPORT_SNAPSHOT_LOCK_SHA256 = "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169"

HTTP_ENVELOPE_ID = "urn:investment-research-kb:contract:http-envelope:v1"
HTTP_ERROR_ID = "urn:investment-research-kb:contract:http-error:v1"
IMMUTABLE_EXPORT_ID = "urn:investment-research-kb:contract:immutable-export-package:v1"
RELEASE_STATUS_HISTORY_ID = "urn:investment-research-kb:contract:release-status-history:v1"

_SOURCE_REPOSITORY = "https://github.com/Zhaosheng-Xie/InvestmentResearchKB"
_BASE_SOURCE_COMMIT = "58ed9c5cb5302e3e719f1696bed83a03c5d6313b"
_BASE_LOCK_SHA256 = "4bd79d0e3032a3eeb7824a1b956282e5495dd52a01db81df8bf36b03a2d49092"
_PROVIDER_LOCK_PATH = "contracts/fixtures/contract-locks.stage6b-transport.v1.json"
_FIXTURE_PATH = "contracts/fixtures/stage6b-public-transport.v1.json"
_OPENAPI_PATH = "contracts/openapi.v1.json"
_EXPECTED_PATHS = {
    _PROVIDER_LOCK_PATH,
    _FIXTURE_PATH,
    _OPENAPI_PATH,
    "contracts/http-envelope.v1.schema.json",
    "contracts/http-error.v1.schema.json",
    "contracts/immutable-export-package.v1.schema.json",
    "contracts/release-status-history.v1.schema.json",
}
_EXPECTED_OPERATIONS = {
    "/api/v1/dataset-releases/{release_id}": (
        "get_dataset_release",
        ["research:read"],
    ),
    "/api/v1/dataset-releases/{release_id}/manifest": (
        "get_dataset_release_manifest",
        ["research:read"],
    ),
    "/api/v1/dataset-releases/{release_id}/status": (
        "get_dataset_release_status_history",
        ["research:read"],
    ),
    "/api/v1/dataset-releases/{release_id}/artifacts/{artifact_id}": (
        "download_dataset_release_artifact",
        ["export:read"],
    ),
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_GIT_OBJECT_RE = re.compile(r"^[0-9a-f]{40}$")
_CATALOG_CONSTRUCTION_TOKEN = object()


@dataclass(frozen=True, slots=True)
class TransportSnapshotFile:
    relative_path: str
    git_blob: str
    size_bytes: int
    sha256: str


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractValidationError(f"{field} must be an object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractValidationError(f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContractValidationError(f"{field} must be non-empty text")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], *, field: str) -> None:
    if set(value) != expected:
        raise ContractValidationError(f"{field} has unexpected or missing fields")


def _safe_relative(value: object, *, field: str) -> str:
    raw = _text(value, field=field)
    path = PurePosixPath(raw)
    if (
        "\\" in raw
        or path.is_absolute()
        or raw in {".", ".."}
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != raw
    ):
        raise ContractValidationError(f"{field} must be a normalized safe POSIX path")
    return raw


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


def _ordinary_file(root: Path, relative_path: str) -> Path:
    candidate = root.joinpath(*PurePosixPath(relative_path).parts)
    current = root
    for part in PurePosixPath(relative_path).parts:
        current /= part
        if _is_link(current):
            raise SnapshotIntegrityError(f"transport snapshot link is prohibited: {relative_path}")
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise SnapshotIntegrityError(f"transport snapshot file missing: {relative_path}") from exc
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise SnapshotIntegrityError(f"transport snapshot path escapes root: {relative_path}")
    if os.stat(resolved).st_nlink != 1:
        raise SnapshotIntegrityError(f"transport snapshot hard link prohibited: {relative_path}")
    return resolved


def _git_blob(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode()
    return sha1(header + content).hexdigest()  # noqa: S324 - Git SHA-1 object identity


class KBTransportContractCatalog:
    """Immutable verified view of the Stage 6B transport extension."""

    __slots__ = (
        "_base_catalog",
        "_fixture",
        "_openapi",
        "_registry",
        "_schema_by_id",
        "_snapshot_files",
        "_snapshot_lock_sha256",
        "_snapshot_root",
        "_vendor_root",
    )

    def __init__(
        self,
        *,
        snapshot_root: Path,
        vendor_root: Path,
        snapshot_files: dict[str, TransportSnapshotFile],
        schema_by_id: dict[str, dict[str, Any]],
        base_catalog: KBContractCatalog,
        openapi: dict[str, Any],
        fixture: dict[str, Any],
        snapshot_lock_sha256: str,
        _construction_token: object,
    ) -> None:
        if _construction_token is not _CATALOG_CONSTRUCTION_TOKEN:
            raise TypeError("use load_kb_transport_contract_snapshot()")
        resources: dict[str, Resource[Any]] = {}
        for contract_id in base_catalog.schema_ids:
            resources[contract_id] = Resource.from_contents(base_catalog.schema_for_id(contract_id))
        for contract_id, schema in schema_by_id.items():
            resources[contract_id] = Resource.from_contents(schema)
        self._snapshot_root = snapshot_root
        self._vendor_root = vendor_root
        self._snapshot_files = MappingProxyType(dict(snapshot_files))
        self._snapshot_lock_sha256 = snapshot_lock_sha256
        self._schema_by_id = MappingProxyType(deepcopy(schema_by_id))
        self._registry: Registry[Any] = Registry().with_resources(resources.items())
        self._base_catalog = base_catalog
        self._openapi = deepcopy(openapi)
        self._fixture = deepcopy(fixture)

    @property
    def source_commit(self) -> str:
        return TRANSPORT_SOURCE_COMMIT

    @property
    def base_catalog(self) -> KBContractCatalog:
        return self._base_catalog

    @property
    def snapshot_lock_sha256(self) -> str:
        return self._snapshot_lock_sha256

    def assert_integrity(self) -> None:
        """Recheck the trust anchor and every vendored byte before capability use."""

        lock = _ordinary_file(self._snapshot_root, "snapshot-lock.json").read_bytes()
        if (
            sha256(lock).hexdigest() != TRANSPORT_SNAPSHOT_LOCK_SHA256
            or self._snapshot_lock_sha256 != TRANSPORT_SNAPSHOT_LOCK_SHA256
        ):
            raise SnapshotIntegrityError("transport snapshot lock trust anchor differs")
        base_lock = _ordinary_file(
            self._snapshot_root.parent / "v1", "snapshot-lock.json"
        ).read_bytes()
        if sha256(base_lock).hexdigest() != _BASE_LOCK_SHA256:
            raise SnapshotIntegrityError("Stage 2A base snapshot lock hash differs")
        for relative_path in self._snapshot_files:
            self.read_vendor_bytes(relative_path)

    @property
    def openapi(self) -> dict[str, Any]:
        return deepcopy(self._openapi)

    @property
    def official_fixture(self) -> dict[str, Any]:
        return deepcopy(self._fixture)

    def read_vendor_bytes(self, relative_path: str) -> bytes:
        normalized = _safe_relative(relative_path, field="relative_path")
        entry = self._snapshot_files.get(normalized)
        if entry is None:
            raise SnapshotIntegrityError(f"transport path is not locked: {normalized}")
        content = _ordinary_file(self._vendor_root, normalized).read_bytes()
        if (
            len(content) != entry.size_bytes
            or sha256(content).hexdigest() != entry.sha256
            or _git_blob(content) != entry.git_blob
        ):
            raise SnapshotIntegrityError(f"transport snapshot byte identity failed: {normalized}")
        return content

    def validate_instance(self, contract_id: str, instance: object) -> None:
        schema = self._schema_by_id.get(contract_id)
        if schema is None:
            self._base_catalog.validate_instance(contract_id, instance)
            return
        try:
            Draft202012Validator(
                schema,
                registry=self._registry,
                format_checker=FormatChecker(),
            ).validate(instance)
        except (ValidationError, Unresolvable) as exc:
            raise ContractValidationError(
                f"instance does not satisfy transport contract {contract_id}"
            ) from exc

    def validate_openapi_json_response(
        self,
        path_template: str,
        status_code: int,
        instance: object,
    ) -> None:
        """Validate one response against the exact pinned OpenAPI operation schema."""

        if path_template not in _EXPECTED_OPERATIONS:
            raise ContractValidationError("OpenAPI response path is not an approved operation")
        paths = _object(self._openapi.get("paths"), field="OpenAPI paths")
        path_item = _object(paths.get(path_template), field="OpenAPI path")
        operation = _object(path_item.get("get"), field="OpenAPI GET operation")
        responses = _object(operation.get("responses"), field="OpenAPI responses")
        response = _object(responses.get(str(status_code)), field="OpenAPI response")
        content = _object(response.get("content"), field="OpenAPI response content")
        media_type = _object(
            content.get("application/json"),
            field="OpenAPI application/json response",
        )
        response_schema = _object(media_type.get("schema"), field="OpenAPI response schema")
        components = _object(self._openapi.get("components"), field="OpenAPI components")
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            **deepcopy(response_schema),
            "components": deepcopy(components),
        }
        try:
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(
                schema,
                registry=self._registry,
                format_checker=FormatChecker(),
            ).validate(instance)
        except (SchemaError, ValidationError, Unresolvable) as exc:
            raise ContractValidationError(
                f"instance does not satisfy pinned OpenAPI response {path_template} {status_code}"
            ) from exc


def _load_snapshot_lock(
    root: Path,
) -> tuple[Path, dict[str, TransportSnapshotFile], str]:
    lock_path = _ordinary_file(root, "snapshot-lock.json")
    lock_bytes = lock_path.read_bytes()
    if sha256(lock_bytes).hexdigest() != TRANSPORT_SNAPSHOT_LOCK_SHA256:
        raise SnapshotIntegrityError("transport snapshot lock trust anchor differs")
    lock = _object(load_strict_json_bytes(lock_bytes, source="snapshot-lock"), field="lock")
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
            "base_snapshot",
            "files",
        },
        field="transport snapshot lock",
    )
    expected = {
        "schema_version": TRANSPORT_SCHEMA_VERSION,
        "provider": "InvestmentResearchKB",
        "source_repository": _SOURCE_REPOSITORY,
        "source_commit": TRANSPORT_SOURCE_COMMIT,
        "source_commit_tree": TRANSPORT_SOURCE_COMMIT_TREE,
        "source_contracts_tree": TRANSPORT_SOURCE_CONTRACTS_TREE,
        "retrieval_method": "git_object",
        "canonicalization_profile": CANONICALIZATION_PROFILE,
        "vendor_root": "vendor",
        "selection": "complete Stage 6B public transport contract set",
    }
    if any(lock.get(key) != value for key, value in expected.items()):
        raise SnapshotIntegrityError("transport snapshot identity fields differ")
    base = _object(lock["base_snapshot"], field="base_snapshot")
    if base != {
        "path": "../v1/snapshot-lock.json",
        "source_commit": _BASE_SOURCE_COMMIT,
        "sha256": _BASE_LOCK_SHA256,
    }:
        raise SnapshotIntegrityError("transport base snapshot binding differs")
    vendor_root = root / "vendor"
    if _is_link(vendor_root) or not vendor_root.is_dir():
        raise SnapshotIntegrityError("transport vendor root must be an ordinary directory")
    files: dict[str, TransportSnapshotFile] = {}
    for index, raw in enumerate(_array(lock["files"], field="files")):
        item = _object(raw, field=f"files[{index}]")
        _exact_keys(item, {"path", "git_blob", "size_bytes", "sha256"}, field="file")
        path = _safe_relative(item["path"], field="file.path")
        blob = _text(item["git_blob"], field="file.git_blob")
        digest = _text(item["sha256"], field="file.sha256")
        size = item["size_bytes"]
        if (
            path in files
            or _GIT_OBJECT_RE.fullmatch(blob) is None
            or _SHA256_RE.fullmatch(digest) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise SnapshotIntegrityError(f"invalid transport lock entry: {path}")
        entry = TransportSnapshotFile(path, blob, size, digest)
        content = _ordinary_file(vendor_root, path).read_bytes()
        if (
            len(content) != size
            or sha256(content).hexdigest() != digest
            or _git_blob(content) != blob
        ):
            raise SnapshotIntegrityError(f"transport lock byte mismatch: {path}")
        files[path] = entry
    if set(files) != _EXPECTED_PATHS:
        raise SnapshotIntegrityError("transport snapshot file closure differs")
    actual_vendor_files = {
        path.relative_to(vendor_root).as_posix()
        for path in vendor_root.rglob("*")
        if path.is_file()
    }
    if actual_vendor_files != _EXPECTED_PATHS:
        raise SnapshotIntegrityError("transport vendor directory contains unowned bytes")
    return vendor_root, files, sha256(lock_bytes).hexdigest()


def _load_provider_contracts(
    catalog: KBTransportContractCatalog,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], dict[str, Any]]:
    provider_lock = _object(
        load_strict_json_bytes(
            catalog.read_vendor_bytes(_PROVIDER_LOCK_PATH), source=_PROVIDER_LOCK_PATH
        ),
        field="provider transport lock",
    )
    _exact_keys(
        provider_lock,
        {"schema_version", "purpose", "contracts", "artifacts"},
        field="provider lock",
    )
    if provider_lock["schema_version"] != TRANSPORT_SCHEMA_VERSION:
        raise ContractValidationError("unsupported provider transport lock version")
    schemas: dict[str, dict[str, Any]] = {}
    provider_paths: set[str] = {_PROVIDER_LOCK_PATH}
    for raw in _array(provider_lock["contracts"], field="provider contracts"):
        item = _object(raw, field="provider contract")
        _exact_keys(
            item,
            {"path", "contract_id", "contract_version", "canonical_sha256", "file_sha256"},
            field="provider contract",
        )
        relative = f"contracts/{_safe_relative(item['path'], field='contract.path')}"
        provider_paths.add(relative)
        content = catalog.read_vendor_bytes(relative)
        schema = _object(load_strict_json_bytes(content, source=relative), field=relative)
        contract_id = _text(item["contract_id"], field="contract_id")
        if item["contract_version"] != TRANSPORT_SCHEMA_VERSION:
            raise ContractValidationError(f"provider contract version mismatch: {relative}")
        canonical = _object(item["canonical_sha256"], field="canonical_sha256")
        physical = _object(item["file_sha256"], field="file_sha256")
        if canonical != {
            "algorithm": "sha256",
            "value": sha256(canonical_json_bytes(schema)).hexdigest(),
        }:
            raise SnapshotIntegrityError(f"provider canonical hash mismatch: {relative}")
        if physical != {"algorithm": "sha256", "value": sha256(content).hexdigest()}:
            raise SnapshotIntegrityError(f"provider file hash mismatch: {relative}")
        if (
            schema.get("$id") != contract_id
            or schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema"
        ):
            raise ContractValidationError(f"provider schema identity mismatch: {relative}")
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as exc:
            raise ContractValidationError(f"invalid provider schema: {relative}") from exc
        if contract_id in schemas:
            raise ContractValidationError(f"duplicate transport contract id: {contract_id}")
        schemas[contract_id] = schema
    artifacts: dict[str, dict[str, Any]] = {}
    for raw in _array(provider_lock["artifacts"], field="provider artifacts"):
        item = _object(raw, field="provider artifact")
        _exact_keys(
            item,
            {"path", "document_type", "document_version", "canonical_sha256", "file_sha256"},
            field="provider artifact",
        )
        relative = f"contracts/{_safe_relative(item['path'], field='artifact.path')}"
        provider_paths.add(relative)
        content = catalog.read_vendor_bytes(relative)
        value = _object(load_strict_json_bytes(content, source=relative), field=relative)
        expected_artifact = {
            _FIXTURE_PATH: ("fixture", "1.0.0"),
            _OPENAPI_PATH: ("openapi", "3.1.0"),
        }.get(relative)
        if (
            expected_artifact is None
            or (
                item["document_type"],
                item["document_version"],
            )
            != expected_artifact
        ):
            raise ContractValidationError(f"provider artifact identity mismatch: {relative}")
        canonical = _object(item["canonical_sha256"], field="canonical_sha256")
        physical = _object(item["file_sha256"], field="file_sha256")
        if canonical != {
            "algorithm": "sha256",
            "value": sha256(canonical_json_bytes(value)).hexdigest(),
        }:
            raise SnapshotIntegrityError(f"provider artifact canonical hash mismatch: {relative}")
        if physical != {"algorithm": "sha256", "value": sha256(content).hexdigest()}:
            raise SnapshotIntegrityError(f"provider artifact file hash mismatch: {relative}")
        artifacts[relative] = value
    if provider_paths != _EXPECTED_PATHS:
        raise ContractValidationError("provider transport lock closure differs")
    return schemas, artifacts[_OPENAPI_PATH], artifacts[_FIXTURE_PATH]


def _verify_openapi(openapi: dict[str, Any]) -> None:
    if openapi.get("openapi") != "3.1.0" or not isinstance(openapi.get("paths"), dict):
        raise ContractValidationError("unsupported provider OpenAPI document")
    paths = openapi["paths"]
    for path, (operation_id, scopes) in _EXPECTED_OPERATIONS.items():
        operation = paths.get(path, {}).get("get") if isinstance(paths.get(path), dict) else None
        if not isinstance(operation, dict):
            raise ContractValidationError(f"OpenAPI GET operation missing: {path}")
        if (
            operation.get("operationId") != operation_id
            or operation.get("x-required-scopes") != scopes
        ):
            raise ContractValidationError(f"OpenAPI operation identity differs: {path}")


def load_kb_transport_contract_snapshot(snapshot_root: str | Path) -> KBTransportContractCatalog:
    """Verify the pinned Stage 6B transport extension and its Stage 2A base."""

    root = Path(snapshot_root).absolute()
    if _is_link(root) or not root.is_dir():
        raise SnapshotIntegrityError("transport snapshot root must be an ordinary directory")
    base_root = root.parent / "v1"
    base_lock = _ordinary_file(base_root, "snapshot-lock.json").read_bytes()
    if sha256(base_lock).hexdigest() != _BASE_LOCK_SHA256:
        raise SnapshotIntegrityError("Stage 2A base snapshot lock hash differs")
    base_catalog = load_kb_contract_snapshot(base_root)
    vendor_root, files, snapshot_lock_sha256 = _load_snapshot_lock(root)
    preliminary = KBTransportContractCatalog(
        snapshot_root=root,
        vendor_root=vendor_root,
        snapshot_files=files,
        schema_by_id={},
        base_catalog=base_catalog,
        openapi={},
        fixture={},
        snapshot_lock_sha256=snapshot_lock_sha256,
        _construction_token=_CATALOG_CONSTRUCTION_TOKEN,
    )
    schemas, openapi, fixture = _load_provider_contracts(preliminary)
    _verify_openapi(openapi)
    if fixture.get("schema_version") != TRANSPORT_SCHEMA_VERSION:
        raise ContractValidationError("unsupported official transport fixture version")
    result = KBTransportContractCatalog(
        snapshot_root=root,
        vendor_root=vendor_root,
        snapshot_files=files,
        schema_by_id=schemas,
        base_catalog=base_catalog,
        openapi=openapi,
        fixture=fixture,
        snapshot_lock_sha256=snapshot_lock_sha256,
        _construction_token=_CATALOG_CONSTRUCTION_TOKEN,
    )
    success = _object(
        _object(fixture.get("http_examples"), field="http_examples").get("release_status_success"),
        field="release_status_success",
    )
    response = _object(success.get("response"), field="status response")
    result.validate_instance(HTTP_ENVELOPE_ID, response)
    result.validate_instance(RELEASE_STATUS_HISTORY_ID, response.get("data"))
    error = _object(
        _object(fixture["http_examples"], field="http_examples").get("withdrawn_artifact_error"),
        field="withdrawn_artifact_error",
    )
    result.validate_instance(HTTP_ERROR_ID, error.get("response"))
    export_example = _object(fixture.get("immutable_export_example"), field="export example")
    result.validate_instance(IMMUTABLE_EXPORT_ID, export_example.get("package_manifest"))
    return result
