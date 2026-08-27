from __future__ import annotations

import json
import shutil
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system.integrations.investment_research_kb import (
    ProviderContractSnapshotError,
    load_stage6_provider_contract_snapshot,
)

SNAPSHOT_PATH = Path("contracts/providers/investment_research_kb/stage6-provider-contracts-v1")
SNAPSHOT_LOCK_RAW_SHA256 = "513b3e8728fc299780bbd3205f0fa049a63bb4946b5eaa8193fc51447b5b333a"
SUPPORT_MATRIX_RAW_SHA256 = "34f7f4055bb243ed4852f36074d44d31819f255ec524198f2f044d781db3cab8"
SOURCE_COMMIT = "4352c10c6c639e25d4c190dfc9ec58ee9e76aa86"
CATALOG_RAW_SHA256 = "59a50eba88fb62f70a01df3d058ad15460d92004fc7cd83c864b3cb1fd901b7a"


def _snapshot(repository_root: Path) -> Path:
    return repository_root / SNAPSHOT_PATH


def test_snapshot_lock_and_support_matrix_have_exact_identity(repository_root: Path) -> None:
    root = _snapshot(repository_root)
    lock_path = root / "snapshot-lock.json"
    support_path = root / "support-matrix.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    support = json.loads(support_path.read_text(encoding="utf-8"))

    assert sha256(lock_path.read_bytes()).hexdigest() == SNAPSHOT_LOCK_RAW_SHA256
    assert sha256(support_path.read_bytes()).hexdigest() == SUPPORT_MATRIX_RAW_SHA256
    assert lock["source_commit"] == SOURCE_COMMIT
    assert lock["provider_contract_commit"] == ("50604ea46e14580be976e1cf46c349a2d3088740")
    assert lock["catalog_raw_sha256"] == CATALOG_RAW_SHA256
    assert lock["transport_protocol"] == "v1"
    assert lock["transport_semantics_changed"] is False
    assert lock["runtime_authority"] is False
    assert len(lock["files"]) == 19
    assert support["snapshot"] == {
        "official_file_count": 19,
        "active_schema_count": 16,
        "registry_count": 1,
        "synthetic_fixture_count": 1,
        "lock_file": "snapshot-lock.json",
    }


def test_loader_validates_complete_catalog_registry_and_fixture(repository_root: Path) -> None:
    catalog = load_stage6_provider_contract_snapshot(_snapshot(repository_root))

    assert len(catalog.schema_ids) == len(catalog.schema_paths) == 16
    assert catalog.provider_catalog["status"] == "DRAFT_ZERO_RUNTIME_AUTHORITY"
    assert catalog.registry_document["status"] == "DRAFT_ZERO_RUNTIME_AUTHORITY"
    assert catalog.synthetic_fixture["status"] == ("DRAFT_SYNTHETIC_ONLY_ZERO_RUNTIME_AUTHORITY")
    assert len(catalog.synthetic_fixture["examples"]) == 9
    assert all(
        value is False for value in catalog.provider_catalog["authorization_boundary"].values()
    )


def test_active_provider_schemas_exclude_consumer_and_strategy_semantics(
    repository_root: Path,
) -> None:
    catalog = load_stage6_provider_contract_snapshot(_snapshot(repository_root))
    forbidden = (
        "strategy_input_ref",
        "authority_eligible",
        "contains_holdout_content",
        "contains_outcome_content",
        "decision_session",
        "owner_fixed_no_caller_override",
        "candidate_coverage",
        "target_weight",
        "order_id",
    )

    for path in catalog.schema_paths:
        serialized = json.dumps(catalog.schema_for_path(path.removeprefix("contracts/")))
        for value in forbidden:
            assert value not in serialized, f"{value} leaked into {path}"


def test_catalog_preserves_legacy_and_superseded_lineage_without_vendoring_it(
    repository_root: Path,
) -> None:
    catalog = load_stage6_provider_contract_snapshot(_snapshot(repository_root))
    provider = catalog.provider_catalog
    superseded = provider["superseded_never_published"]
    legacy = provider["legacy_read_only_compatibility"]

    assert len(superseded) == 5
    assert {item["path"] for item in superseded} == {
        "drafts/historical-stage6-public-input-manifest.v1.schema.json",
        "drafts/benchmark-total-return-daily-record.v1.schema.json",
        "drafts/common-reference-factor-record.v1.schema.json",
        "drafts/corporate-action-record.v1.schema.json",
        "drafts/primary-industry-history-record.v1.schema.json",
    }
    assert legacy == [
        {
            "path": "strategy-input-ref.v1.schema.json",
            "sha256": "55b381df48a80a046388c19c53bb27e924c25bd10294d7dba0d55097280f86b6",
            "status": "locked_read_only_compatibility_not_new_producer_template",
        }
    ]
    vendor_root = _snapshot(repository_root) / "vendor"
    for item in superseded:
        assert not (vendor_root / "contracts" / item["path"]).exists()


def test_returned_documents_are_detached_from_catalog_state(repository_root: Path) -> None:
    catalog = load_stage6_provider_contract_snapshot(_snapshot(repository_root))
    registry = catalog.registry_document
    registry["benchmark_identities"].clear()

    assert len(catalog.registry_document["benchmark_identities"]) == 2


def test_unknown_provider_field_fails_schema_validation(repository_root: Path) -> None:
    catalog = load_stage6_provider_contract_snapshot(_snapshot(repository_root))
    release = catalog.synthetic_fixture["examples"]["drafts/release-reference.v1.schema.json"][0]
    release["strategy_input_ref"] = {}

    with pytest.raises(ProviderContractSnapshotError, match="Additional properties"):
        catalog.validate_schema_path("drafts/release-reference.v1.schema.json", release)


def test_snapshot_tamper_fails_before_catalog_use(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    shutil.copytree(_snapshot(repository_root), snapshot)
    target = snapshot / "vendor/contracts/drafts/release-reference.v1.schema.json"
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(ProviderContractSnapshotError, match="physical identity differs"):
        load_stage6_provider_contract_snapshot(snapshot)


def test_dependency_update_script_has_no_local_kb_path_or_runtime_discovery(
    repository_root: Path,
) -> None:
    script = (repository_root / "scripts/vendor-kb-stage6-provider-contracts.py").read_text(
        encoding="utf-8"
    )

    assert "--kb-repository" in script
    assert "D:\\Python\\Python_Project\\InvestmentResearchKB" not in script
    assert 'SOURCE_COMMIT = "4352c10c6c639e25d4c190dfc9ec58ee9e76aa86"' in script
    assert "destination already exists" in script
