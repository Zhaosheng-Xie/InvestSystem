from __future__ import annotations

import json
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest

from invest_system.canonical import canonical_sha256
from invest_system.integrations.investment_research_kb import (
    Stage6GenericAdapterError,
    Stage6OfflineAdapterResult,
    adapt_official_stage6_provider_fixture,
    load_stage6_provider_contract_snapshot,
    recompute_adv20_cny_turnover,
    recompute_beta120_ols_with_intercept,
)

SNAPSHOT_PATH = Path("contracts/providers/investment_research_kb/stage6-provider-contracts-v1")
RESULT_HASH = "a9e43b70098be362b3795375f3eb597641416af5b83eed5a12a636c9e8e4c708"
ACCEPTANCE_PATH = Path(
    "docs/validation/machine/stage6-generic-kb-offline-adapter-acceptance-v0.1.json"
)
ACCEPTANCE_RAW_SHA256 = "f8d32a6f567211c6c7b7a401b3cf91b44684175e3b651b3d2be47e7a84438ff2"
ACCEPTANCE_HASH = "7d7fcbb7cbdc93e8373810458016decbdfc0f9519befd254899c96719170268a"


def _result(repository_root: Path) -> Stage6OfflineAdapterResult:
    catalog = load_stage6_provider_contract_snapshot(repository_root / SNAPSHOT_PATH)
    return adapt_official_stage6_provider_fixture(catalog)


def test_official_fixture_projects_root_and_variable_dependency_closure(
    repository_root: Path,
) -> None:
    result = _result(repository_root)
    root = result.strategy_input_ref
    closure = result.dependency_closure

    assert root.dataset_release_id == "rel_synthetic_provider_root"
    assert root.release_manifest_schema_version == "1.0.0"
    assert root.manifest_hash.value == "a" * 64
    assert closure.root_strategy_input_ref == root
    assert [item.strategy_input_ref.dataset_release_id for item in closure.dependencies] == [
        "rel_synthetic_evidence",
        "rel_synthetic_financials",
        "rel_synthetic_market_reference",
        "rel_synthetic_methodology",
    ]
    assert {role for item in closure.dependencies for role in item.roles} == {
        "market_reference",
        "methodology_registry",
        "public_evidence",
        "public_financials",
        "security_reference",
    }
    assert closure.provider_declared_closure_hash.value == "f" * 64


def test_data_profile_preserves_objective_incomplete_domain_without_coverage(
    repository_root: Path,
) -> None:
    profile = _result(repository_root).data_profile

    assert profile.readiness_status == "PARTIALLY_READY_SYNTHETIC_PROFILE"
    assert profile.redistribution_status == "allowed"
    assert [domain.domain_id for domain in profile.domains] == [
        "benchmark_observation",
        "security_lifecycle",
    ]
    benchmark = profile.domains[0]
    assert benchmark.pit_result == "incomplete"
    assert benchmark.declared_missing_items == (
        "full historical continuity is not represented by this fixture",
    )
    assert profile.domains[1].population_status == "includes_inactive_failed_and_delisted"


def test_h00985_is_selected_exactly_but_real_acceptance_remains_blocked(
    repository_root: Path,
) -> None:
    selection = _result(repository_root).benchmark_selection

    assert selection.benchmark_id == "H00985"
    assert selection.provider_id == "CSI"
    assert selection.provider_code == "H00985.CSI"
    assert selection.return_type == "gross_total_return"
    assert selection.currency == "CNY"
    assert selection.redistribution_status == "pending_explicit_permission"
    assert selection.selection_status == "BLOCKED_PENDING_REDISTRIBUTION_PERMISSION"
    assert selection.reason_codes == ("H00985_REDISTRIBUTION_PERMISSION_NOT_PROVEN",)
    assert selection.fallback_used is False


def test_factor_definitions_and_observations_close_without_fake_recomputation(
    repository_root: Path,
) -> None:
    result = _result(repository_root)

    assert result.adv20.factor_definition_id == "adv20-cny-turnover-mean"
    assert result.adv20.completeness == "complete"
    assert result.adv20.basis_record_count == 20
    assert result.adv20.value_decimal == "123456789.12"
    assert result.adv20.acceptance_status == (
        "DEFINITION_ACCEPTED_OBSERVATION_COMPLETE_HASH_BASIS_ONLY"
    )
    assert result.adv20.recomputation_status == ("BLOCKED_RAW_BASIS_RECORDS_NOT_PRESENT_IN_FIXTURE")
    assert result.beta120.factor_definition_id == "beta120-h00985-gtr-ols"
    assert result.beta120.completeness == "incomplete"
    assert result.beta120.basis_record_count == 118
    assert result.beta120.value_decimal is None
    assert result.beta120.reason_codes == ("insufficient_paired_sessions",)


def test_offline_adapter_result_is_deterministic_and_zero_authority(
    repository_root: Path,
) -> None:
    first = _result(repository_root)
    second = _result(repository_root)

    assert first == second
    assert first.result_hash.value == RESULT_HASH
    assert first.synthetic_fixture_only is True
    assert first.validation_only is True
    assert first.authority_eligible is False
    assert first.network_accessed is False
    assert first.real_release_consumed is False


def test_adv20_recomputation_requires_exact_canonical_20_values() -> None:
    assert recompute_adv20_cny_turnover([str(value) for value in range(1, 21)]) == "10.5"

    with pytest.raises(Stage6GenericAdapterError, match="ADV20_EXACT_WINDOW_REQUIRED"):
        recompute_adv20_cny_turnover(["1"] * 19)
    with pytest.raises(Stage6GenericAdapterError, match="NON_CANONICAL_DECIMAL"):
        recompute_adv20_cny_turnover(["1.0"] * 20)
    with pytest.raises(Stage6GenericAdapterError, match="ADV20_NEGATIVE_TURNOVER"):
        recompute_adv20_cny_turnover(["1"] * 19 + ["-1"])


def test_beta120_recomputation_is_exact_paired_ols_with_intercept() -> None:
    benchmark = [format(Decimal(value) / Decimal(1000), "f") for value in range(1, 121)]
    security = [format(Decimal(value * 2) / Decimal(1000), "f") for value in range(1, 121)]

    assert recompute_beta120_ols_with_intercept(security, benchmark) == "2"
    with pytest.raises(
        Stage6GenericAdapterError,
        match="BETA120_EXACT_PAIRED_WINDOW_REQUIRED",
    ):
        recompute_beta120_ols_with_intercept(security[:-1], benchmark[:-1])
    with pytest.raises(Stage6GenericAdapterError, match="BETA120_BENCHMARK_ZERO_VARIANCE"):
        recompute_beta120_ols_with_intercept(["0.01"] * 120, ["0.01"] * 120)


def test_acceptance_record_has_exact_identity_and_zero_authority(
    repository_root: Path,
) -> None:
    path = repository_root / ACCEPTANCE_PATH
    value = json.loads(path.read_text(encoding="utf-8"))

    assert sha256(path.read_bytes()).hexdigest() == ACCEPTANCE_RAW_SHA256
    assert value["acceptance_hash"] == ACCEPTANCE_HASH
    assert (
        canonical_sha256({key: item for key, item in value.items() if key != "acceptance_hash"})
        == ACCEPTANCE_HASH
    )
    assert value["source"]["merge_commit"] == ("4352c10c6c639e25d4c190dfc9ec58ee9e76aa86")
    assert value["snapshot"]["transport_repinned"] is False
    assert all(item is False for item in value["authorization_boundary"].values())
