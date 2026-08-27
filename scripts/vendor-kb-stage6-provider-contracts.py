"""Vendor the exact KB Stage 6 provider-contract draft snapshot from Git objects.

This explicit dependency-update tool reads blobs from one pinned KB commit. It
never imports the KB package, opens its working-tree files, or reads KB data.
The destination must not exist so an update cannot silently overwrite history.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
from typing import Any

SOURCE_REPOSITORY = "https://github.com/Zhaosheng-Xie/InvestmentResearchKB"
SOURCE_COMMIT = "4352c10c6c639e25d4c190dfc9ec58ee9e76aa86"
PROVIDER_CONTRACT_COMMIT = "50604ea46e14580be976e1cf46c349a2d3088740"
IS_APPROVAL_COMMIT = "eb702559511083d2d0d603725be50997e0c22bbe"
CATALOG_PATH = "contracts/fixtures/provider-contract-catalog.v1.json"


class VendorError(RuntimeError):
    """Raised when pinned provider Git objects or their catalog do not close."""


def _git(repository: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repository.as_posix()}", "-C", str(repository), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip()
        raise VendorError(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def _blob(repository: Path, path: str) -> bytes:
    normalized = PurePosixPath(path)
    if normalized.is_absolute() or any(part in {"", ".", ".."} for part in normalized.parts):
        raise VendorError(f"unsafe provider path: {path}")
    return _git(repository, "show", f"{SOURCE_COMMIT}:{normalized.as_posix()}")


def _object_id(repository: Path, path: str) -> str:
    value = _git(repository, "rev-parse", f"{SOURCE_COMMIT}:{path}").decode("ascii").strip()
    if len(value) != 40 or any(character not in "0123456789abcdef" for character in value):
        raise VendorError(f"invalid Git blob ID for {path}")
    return value


def _json_object(content: bytes, *, source: str) -> dict[str, Any]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VendorError(f"invalid UTF-8 JSON in {source}") from exc
    if not isinstance(value, dict):
        raise VendorError(f"JSON root must be an object: {source}")
    return value


def _git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return sha1(header + content, usedforsecurity=False).hexdigest()


def _provider_path(relative_contract_path: str) -> str:
    normalized = PurePosixPath(relative_contract_path)
    if normalized.is_absolute() or normalized.parts[0] not in {"drafts", "fixtures"}:
        raise VendorError(f"catalog path is outside contracts: {relative_contract_path}")
    if any(part in {"", ".", ".."} for part in normalized.parts):
        raise VendorError(f"catalog path is unsafe: {relative_contract_path}")
    return f"contracts/{normalized.as_posix()}"


def _catalog_selection(catalog: dict[str, Any]) -> tuple[list[str], dict[str, str]]:
    if catalog.get("status") != "DRAFT_ZERO_RUNTIME_AUTHORITY":
        raise VendorError("provider catalog is not the zero-authority draft")
    governance = catalog.get("governance")
    if not isinstance(governance, dict) or governance.get("is_approval_commit") != (
        IS_APPROVAL_COMMIT
    ):
        raise VendorError("provider catalog does not bind the approved IS boundary")
    transport = catalog.get("transport")
    if not isinstance(transport, dict) or transport.get("semantics_changed") is not False:
        raise VendorError("provider catalog reports a transport semantic change")
    authorization = catalog.get("authorization_boundary")
    if (
        not isinstance(authorization, dict)
        or not authorization
        or any(value is not False for value in authorization.values())
    ):
        raise VendorError("provider catalog grants runtime or data authority")

    expected_hashes: dict[str, str] = {}
    supporting = catalog.get("supporting_schema")
    if not isinstance(supporting, dict):
        raise VendorError("supporting_schema is missing")
    supporting_path = _provider_path(str(supporting.get("path")))
    expected_hashes[supporting_path] = str(supporting.get("sha256"))

    active = catalog.get("active_provider_drafts")
    if not isinstance(active, list) or len(active) != 15:
        raise VendorError("active provider draft inventory must contain exactly 15 Schemas")
    for entry in active:
        if not isinstance(entry, dict):
            raise VendorError("active provider draft entry is not an object")
        path = _provider_path(str(entry.get("path")))
        if path in expected_hashes:
            raise VendorError(f"duplicate provider contract path: {path}")
        expected_hashes[path] = str(entry.get("sha256"))

    registries = catalog.get("registries")
    if not isinstance(registries, list) or len(registries) != 1:
        raise VendorError("provider catalog must bind exactly one registry")
    registry = registries[0]
    if not isinstance(registry, dict):
        raise VendorError("provider registry entry is not an object")
    registry_path = _provider_path(str(registry.get("path")))
    expected_hashes[registry_path] = str(registry.get("sha256"))

    fixture = catalog.get("synthetic_fixture")
    if not isinstance(fixture, dict):
        raise VendorError("provider synthetic fixture is missing")
    fixture_path = _provider_path(str(fixture.get("path")))
    expected_hashes[fixture_path] = str(fixture.get("sha256"))

    selected = [CATALOG_PATH, *sorted(expected_hashes)]
    if len(selected) != 19:
        raise VendorError("provider snapshot must contain exactly 19 files")
    return selected, expected_hashes


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def vendor(repository: Path, destination: Path) -> None:
    if not repository.is_dir():
        raise VendorError("KB repository path must be an existing directory")
    if destination.exists():
        raise VendorError("destination already exists; create a new versioned snapshot")
    resolved_commit = _git(repository, "rev-parse", SOURCE_COMMIT).decode("ascii").strip()
    if resolved_commit != SOURCE_COMMIT:
        raise VendorError("KB source commit does not resolve exactly")
    parents = _git(repository, "show", "-s", "--format=%P", SOURCE_COMMIT).decode("ascii").split()
    if PROVIDER_CONTRACT_COMMIT not in parents:
        raise VendorError("merge commit does not retain the approved provider-contract commit")

    catalog_bytes = _blob(repository, CATALOG_PATH)
    catalog = _json_object(catalog_bytes, source=CATALOG_PATH)
    selected, expected_hashes = _catalog_selection(catalog)

    destination.mkdir(parents=True, exist_ok=False)
    vendor_root = destination / "vendor"
    lock_entries: list[dict[str, object]] = []
    for path in selected:
        content = catalog_bytes if path == CATALOG_PATH else _blob(repository, path)
        digest = sha256(content).hexdigest()
        expected = expected_hashes.get(path)
        if expected is not None and digest != expected:
            raise VendorError(f"provider catalog SHA-256 mismatch: {path}")
        provider_blob = _object_id(repository, path)
        if _git_blob_id(content) != provider_blob:
            raise VendorError(f"Git blob identity mismatch: {path}")
        target = vendor_root.joinpath(*PurePosixPath(path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        lock_entries.append(
            {
                "path": path,
                "git_blob": provider_blob,
                "size_bytes": len(content),
                "sha256": digest,
            }
        )

    source_tree = (
        _git(repository, "show", "-s", "--format=%T", SOURCE_COMMIT).decode("ascii").strip()
    )
    lock = {
        "schema_version": "1.0.0",
        "provider": "InvestmentResearchKB",
        "source_repository": SOURCE_REPOSITORY,
        "source_commit": SOURCE_COMMIT,
        "source_commit_tree": source_tree,
        "provider_contract_commit": PROVIDER_CONTRACT_COMMIT,
        "retrieval_method": "git_object",
        "selection": (
            "provider catalog plus one supporting defs Schema, 15 active provider draft "
            "Schemas, one benchmark/factor registry, and one official synthetic fixture"
        ),
        "catalog_path": CATALOG_PATH,
        "catalog_raw_sha256": sha256(catalog_bytes).hexdigest(),
        "transport_protocol": "v1",
        "transport_semantics_changed": False,
        "runtime_authority": False,
        "files": lock_entries,
    }
    _write_json(destination / "snapshot-lock.json", lock)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-repository", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    vendor(args.kb_repository.resolve(), args.destination.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
