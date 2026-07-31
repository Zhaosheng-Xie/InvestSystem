from __future__ import annotations

import json
import os
import shutil
from hashlib import sha1, sha256
from pathlib import Path
from typing import Any

import pytest

from invest_system.integrations.investment_research_kb.contracts import (
    SOURCE_COMMIT,
    ContractValidationError,
    SnapshotIntegrityError,
    StrictJsonError,
    load_kb_contract_snapshot,
    load_strict_json_bytes,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes,
)

SNAPSHOT_RELATIVE = Path("contracts") / "providers" / "investment_research_kb" / "v1"
STRATEGY_INPUT_REF_ID = "urn:investment-research-kb:contract:strategy-input-ref:v1"
STAGE6_FIXTURE = "contracts/fixtures/stage6-reference-consumer.v1.json"
STAGE6_FIXTURE_LOCK = "contracts/fixtures/stage6-reference-consumer.v1.lock.json"


def _snapshot_root(repository_root: Path) -> Path:
    return repository_root / SNAPSHOT_RELATIVE


def _copy_snapshot(repository_root: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "snapshot"
    shutil.copytree(_snapshot_root(repository_root), destination)
    return destination


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    path.write_bytes(encoded)


def _git_blob_id(content: bytes) -> str:
    header = f"blob {len(content)}\0".encode("ascii")
    return sha1(header + content, usedforsecurity=False).hexdigest()


def _reseal_snapshot(snapshot_root: Path, *vendor_paths: str) -> None:
    lock_path = snapshot_root / "snapshot-lock.json"
    lock = _load_json(lock_path)
    entries = {entry["path"]: entry for entry in lock["files"]}
    for relative_path in vendor_paths:
        content = (snapshot_root / "vendor" / Path(relative_path)).read_bytes()
        entry = entries[relative_path]
        entry["size_bytes"] = len(content)
        entry["sha256"] = sha256(content).hexdigest()
        entry["git_blob"] = _git_blob_id(content)
    _write_json(lock_path, lock)


def _reseal_stage6_fixture(snapshot_root: Path, fixture: dict[str, Any]) -> None:
    fixture_path = snapshot_root / "vendor" / Path(STAGE6_FIXTURE)
    _write_json(fixture_path, fixture)

    fixture_lock_path = snapshot_root / "vendor" / Path(STAGE6_FIXTURE_LOCK)
    fixture_lock = _load_json(fixture_lock_path)
    fixture_lock["file_sha256"]["value"] = sha256(fixture_path.read_bytes()).hexdigest()
    _write_json(fixture_lock_path, fixture_lock)
    _reseal_snapshot(snapshot_root, STAGE6_FIXTURE, STAGE6_FIXTURE_LOCK)


def test_fixed_public_catalog_verifies_all_fourteen_schemas_and_stage6_fixture(
    repository_root: Path,
) -> None:
    catalog = load_kb_contract_snapshot(_snapshot_root(repository_root))

    assert catalog.source_commit == SOURCE_COMMIT
    assert len(catalog.schema_contracts) == 14
    assert len(catalog.schema_ids) == 14
    assert {contract.contract_id for contract in catalog.schema_contracts} == set(
        catalog.schema_ids
    )
    assert all(len(contract.file_sha256) == 64 for contract in catalog.schema_contracts)
    assert all(len(contract.canonical_sha256) == 64 for contract in catalog.schema_contracts)
    assert catalog.stage6_fixture["schema_version"] == "1.0.0"
    assert len(catalog.stage6_fixture["releases"]) == 2

    schema = catalog.schema_for_id(STRATEGY_INPUT_REF_ID)
    schema["title"] = "caller mutation"
    assert catalog.schema_for_id(STRATEGY_INPUT_REF_ID)["title"] != "caller mutation"


def test_catalog_reads_only_locked_safe_vendor_paths(repository_root: Path) -> None:
    catalog = load_kb_contract_snapshot(_snapshot_root(repository_root))

    content = catalog.read_vendor_bytes("contracts/strategy-input-ref.v1.schema.json")
    assert sha256(content).hexdigest() == next(
        contract.file_sha256
        for contract in catalog.schema_contracts
        if contract.contract_id == STRATEGY_INPUT_REF_ID
    )
    assert catalog.load_vendor_json("contracts/strategy-input-ref.v1.schema.json")["$id"] == (
        STRATEGY_INPUT_REF_ID
    )

    for unsafe in ("../snapshot-lock.json", "/absolute/path.json", "contracts\\x.json"):
        with pytest.raises((ContractValidationError, SnapshotIntegrityError)):
            catalog.read_vendor_bytes(unsafe)
    with pytest.raises(SnapshotIntegrityError, match="not present"):
        catalog.read_vendor_bytes("contracts/not-locked.json")


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b'{"a":1,"a":2}', "duplicate"),
        ('{"e\\u0301":1,"é":2}'.encode(), "NFC"),
        (b'{"number":NaN}', "non-finite"),
        (b'{"number":Infinity}', "non-finite"),
        (b'{"number":-Infinity}', "non-finite"),
        (b'{"number":1e999}', "non-finite"),
    ],
)
def test_strict_json_rejects_ambiguous_keys_and_non_finite_numbers(
    content: bytes,
    message: str,
) -> None:
    with pytest.raises(StrictJsonError, match=message):
        load_strict_json_bytes(content, source="attack.json")


def test_snapshot_lock_detects_one_byte_tampering(repository_root: Path, tmp_path: Path) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    target = snapshot / "vendor" / "contracts" / "strategy-input-ref.v1.schema.json"
    target.write_bytes(target.read_bytes() + b" ")

    with pytest.raises(SnapshotIntegrityError, match="size mismatch"):
        load_kb_contract_snapshot(snapshot)


def test_snapshot_lock_requires_the_exact_source_tree_identities(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    lock_path = snapshot / "snapshot-lock.json"
    lock = _load_json(lock_path)
    lock["source_contracts_tree"] = "0" * 40
    _write_json(lock_path, lock)

    with pytest.raises(ContractValidationError, match="source_contracts_tree.*fixed"):
        load_kb_contract_snapshot(snapshot)


def test_snapshot_lock_binds_each_source_git_blob_identity(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    lock_path = snapshot / "snapshot-lock.json"
    lock = _load_json(lock_path)
    lock["files"][0]["git_blob"] = "0" * 40
    _write_json(lock_path, lock)

    with pytest.raises(SnapshotIntegrityError, match="Git blob mismatch"):
        load_kb_contract_snapshot(snapshot)


def test_stage6_fixture_lock_is_checked_independently_of_snapshot_lock(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    fixture_lock_path = snapshot / "vendor" / Path(STAGE6_FIXTURE_LOCK)
    fixture_lock = _load_json(fixture_lock_path)
    fixture_lock["file_sha256"]["value"] = "0" * 64
    _write_json(fixture_lock_path, fixture_lock)
    _reseal_snapshot(snapshot, STAGE6_FIXTURE_LOCK)

    with pytest.raises(SnapshotIntegrityError, match="official lock"):
        load_kb_contract_snapshot(snapshot)


def test_unknown_artifact_schema_in_stage6_fixture_fails_closed(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    fixture = _load_json(snapshot / "vendor" / Path(STAGE6_FIXTURE))
    fixture["releases"][0]["manifest"]["release_items"][0]["record_schema_id"] = (
        "urn:investment-research-kb:contract:unknown:v1"
    )
    _reseal_stage6_fixture(snapshot, fixture)

    with pytest.raises(ContractValidationError, match="unknown provider contract id"):
        load_kb_contract_snapshot(snapshot)


def test_invalid_resealed_schema_fails_draft_2020_12_self_check(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    schema_relative = "contracts/strategy-input-ref.v1.schema.json"
    schema_path = snapshot / "vendor" / Path(schema_relative)
    schema = _load_json(schema_path)
    schema["type"] = 42
    _write_json(schema_path, schema)

    contract_lock_relative = "contracts/fixtures/contract-locks.v1.json"
    contract_lock_path = snapshot / "vendor" / Path(contract_lock_relative)
    contract_lock = _load_json(contract_lock_path)
    entry = next(
        item
        for item in contract_lock["contracts"]
        if item["path"] == "strategy-input-ref.v1.schema.json"
    )
    entry["file_sha256"]["value"] = sha256(schema_path.read_bytes()).hexdigest()
    entry["canonical_sha256"]["value"] = sha256(canonical_json_bytes(schema)).hexdigest()
    _write_json(contract_lock_path, contract_lock)
    _reseal_snapshot(snapshot, schema_relative, contract_lock_relative)

    with pytest.raises(ContractValidationError, match="invalid provider Schema"):
        load_kb_contract_snapshot(snapshot)


def test_format_checker_rejects_calendar_invalid_but_pattern_matching_timestamp(
    repository_root: Path,
) -> None:
    catalog = load_kb_contract_snapshot(_snapshot_root(repository_root))
    reference = catalog.stage6_fixture["expected_strategy_input_ref"]
    reference["knowledge_cutoff"] = "2026-02-31T00:00:00.000000Z"

    with pytest.raises(ContractValidationError, match="does not satisfy"):
        catalog.validate_instance(STRATEGY_INPUT_REF_ID, reference)


def test_locked_vendor_file_replaced_by_link_is_rejected(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = _copy_snapshot(repository_root, tmp_path)
    catalog = load_kb_contract_snapshot(snapshot)
    relative = "contracts/strategy-input-ref.v1.schema.json"
    target = snapshot / "vendor" / Path(relative)
    replacement = tmp_path / "replacement.json"
    replacement.write_bytes(target.read_bytes())
    target.unlink()
    try:
        os.symlink(replacement, target)
    except OSError as exc:
        pytest.skip(f"current account cannot create symlinks: {exc}")

    with pytest.raises(SnapshotIntegrityError, match="link"):
        catalog.read_vendor_bytes(relative)
