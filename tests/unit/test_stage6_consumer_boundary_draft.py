from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256

ADR_PATH = Path("docs/adr/ADR-0002-kb-provider-contract-consumer-profile-boundary.md")
PROFILE_DOCUMENT_PATH = Path(
    "docs/validation/stage6-historical-public-data-consumer-profile-v0.3-draft.md"
)
PROFILE_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-historical-public-data-consumer-profile-v0.3.0-draft.json"
)
V02_DOCUMENT_PATH = Path("docs/validation/stage6-minimum-public-data-consumption-contract-v0.2.md")
V02_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.2.0.json"
)
V02_APPROVAL_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.2.0.approval.json"
)

ADR_RAW_SHA256 = "e18e91423066589b636edd0ca793e6949f45dcf272ce0f81661aa33c3982f22e"
PROFILE_DOCUMENT_RAW_SHA256 = "79abfe814577dd2da644f5a59310021e6151e1c3a585cc6fa69aa69424e6bbad"
PROFILE_MACHINE_RAW_SHA256 = "2ea49cf7cd2cd100ecf6fde345b431a75a3f03c226d79fa4689cb0799fce8f6d"
PROFILE_HASH = "76c8d8eceab4c012dc957ac40edfd7d013a7d2a27a8b4edb997815ce81e3ebc0"
V02_DOCUMENT_RAW_SHA256 = "ea82f2e17b99ecaec0cafde7ce5fe0fdb5d6d6855f6348891369cd0b2f02db43"
V02_MACHINE_RAW_SHA256 = "a7fd65c0d955d4e3610dcbefbaf6a2ec600689986aee0aa80123d167f8c88f6a"
V02_APPROVAL_RAW_SHA256 = "ab40ae5392a8c9d22e507c59066d20d84df7cec78ffcc77ff4aac4ce4a616b31"
V02_CONTRACT_HASH = "4063575384771228433fb8849c0fedd9fac2ba78f704ce5551bb4e23fe8c3557"
V02_DECISIONS_HASH = "211f046282cb31f046db2fa382af38457810cbb03c20dfd60fb41162c84c5da4"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_draft_documents_and_machine_profile_have_exact_identity(
    repository_root: Path,
) -> None:
    assert sha256((repository_root / ADR_PATH).read_bytes()).hexdigest() == ADR_RAW_SHA256
    assert (
        sha256((repository_root / PROFILE_DOCUMENT_PATH).read_bytes()).hexdigest()
        == PROFILE_DOCUMENT_RAW_SHA256
    )
    assert (
        sha256((repository_root / PROFILE_MACHINE_PATH).read_bytes()).hexdigest()
        == PROFILE_MACHINE_RAW_SHA256
    )
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    assert profile["profile_hash"] == PROFILE_HASH
    assert (
        canonical_sha256({key: value for key, value in profile.items() if key != "profile_hash"})
        == PROFILE_HASH
    )


def test_v02_bytes_and_approval_are_preserved_without_revocation(
    repository_root: Path,
) -> None:
    assert (
        sha256((repository_root / V02_DOCUMENT_PATH).read_bytes()).hexdigest()
        == V02_DOCUMENT_RAW_SHA256
    )
    assert (
        sha256((repository_root / V02_MACHINE_PATH).read_bytes()).hexdigest()
        == V02_MACHINE_RAW_SHA256
    )
    assert (
        sha256((repository_root / V02_APPROVAL_PATH).read_bytes()).hexdigest()
        == V02_APPROVAL_RAW_SHA256
    )
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    lineage = profile["preserved_v0_2_lineage"]
    assert lineage["contract_hash"] == V02_CONTRACT_HASH
    assert lineage["approved_decisions_sha256"] == V02_DECISIONS_HASH
    assert lineage["bytes_unchanged"] is True
    assert lineage["approval_not_revoked"] is True
    assert lineage["reinterpretation"] == "IS_CONSUMER_REQUIREMENTS_AND_ACCEPTANCE_PROFILE"


def test_all_boundary_decisions_are_pending_atomic_and_not_silently_approved(
    repository_root: Path,
) -> None:
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    expected_ids = [f"S6BOUND-{number:02d}" for number in range(1, 11)]
    items = profile["owner_confirmation_items"]
    assert [item["id"] for item in items] == expected_ids
    assert {item["status"] for item in items} == {"pending"}
    assert profile["declared_status"] == "draft"
    assert profile["proposed_architecture_decision"]["status"] == ("proposed_pending_owner")
    assert profile["authorization_boundary"]["authorizes_adr_or_profile_approval"] is False

    adr = (repository_root / ADR_PATH).read_text(encoding="utf-8")
    unchecked = re.findall(r"^- \[ \] `(S6BOUND-\d{2})`：", adr, flags=re.MULTILINE)
    assert unchecked == expected_ids
    assert re.search(r"^- \[[xX]\] `S6BOUND-", adr, flags=re.MULTILINE) is None


def test_s6data_01_through_10_are_preserved_exactly_as_consumer_requirements(
    repository_root: Path,
) -> None:
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    v02 = _json(repository_root / V02_MACHINE_PATH)
    decisions = profile["preserved_s6data_decisions"]

    assert decisions == v02["approved_decisions"]
    assert [item["id"] for item in decisions] == [f"S6DATA-{number:02d}" for number in range(1, 11)]
    assert {item["status"] for item in decisions} == {"approved"}
    assert canonical_sha256(decisions) == V02_DECISIONS_HASH


def test_provider_and_consumer_ownership_are_separate_closed_sets(
    repository_root: Path,
) -> None:
    ownership = _json(repository_root / PROFILE_MACHINE_PATH)["ownership"]
    provider = set(ownership["kb_provider"])
    consumer = set(ownership["investsystem_consumer"])

    assert provider.isdisjoint(consumer)
    assert {
        "release",
        "manifest",
        "status_event_chain",
        "artifact",
        "schema",
        "context_pack",
        "generic_dependency_closure",
        "generic_benchmark_identity_observation_methodology",
        "generic_factor_definition_observation_and_raw_basis",
    } <= provider
    assert {
        "strategy_input_ref",
        "strategy_run_manifest",
        "h00985_selection",
        "candidate_coverage_historical_validation",
        "authority_eligible_abstain_blocked_and_run_permissions",
    } <= consumer


def test_generic_kb_input_is_variable_and_excludes_is_runtime_fields(
    repository_root: Path,
) -> None:
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    generic = profile["generic_kb_input"]
    forbidden = set(profile["forbidden_in_new_kb_core_artifacts"])

    assert generic["dependency_closure_is_variable_length"] is True
    assert generic["benchmark_contract"] == "benchmark_identities_and_observations"
    assert generic["factor_contract"] == (
        "factor_definitions_observations_completeness_and_raw_basis_hashes"
    )
    assert generic["corporate_action_types_are_extensible"] is True
    assert generic["industry_classification_levels_are_extensible"] is True
    assert "strategy_input_ref" in forbidden
    assert "authority_eligible" in forbidden
    assert "holdout_or_outcome_flags" in forbidden
    assert "exactly_three_source_release_constraint" in forbidden
    assert "investsystem_snapshot_lock" in forbidden
    assert "closed_five_type_corporate_action_provider_ontology" in forbidden
    assert "closed_level_one_industry_provider_ontology" in forbidden
    serialized_generic = json.dumps(generic, sort_keys=True)
    for value in ("strategy_input_ref", "authority_eligible", "H00985", "stage6"):
        assert value not in serialized_generic


def test_adapter_constructs_is_objects_from_generic_provider_inputs(
    repository_root: Path,
) -> None:
    mapping = _json(repository_root / PROFILE_MACHINE_PATH)["adapter_projection"]
    projected = {item["provider_input"]: item["is_output"] for item in mapping}

    assert projected == {
        "root_release_identity": "StrategyInputRef",
        "generic_dependency_closure": "ReleaseRetentionClosure",
        "artifact_descriptors_and_bytes": "ArtifactConsumptionReceipt",
        "status_event_chain_and_response_bytes": "ReleaseStatusObservation",
        "generic_data_quality_profile": "HistoricalDataReadinessReport",
        "benchmark_identities": "H00985Selection",
        "factor_definitions_and_raw_basis": "ADV20Beta120AcceptanceAndRecomputation",
        "status_confirmation_and_approval_capability": "AuthorityAndAdmissionResult",
    }


def test_h00985_adv20_beta120_and_single_root_remain_is_requirements(
    repository_root: Path,
) -> None:
    requirements = _json(repository_root / PROFILE_MACHINE_PATH)["consumer_requirements"]
    benchmark = requirements["benchmark_selection"]

    assert benchmark == {
        "benchmark_id": "H00985",
        "provider": "CSI",
        "return_type": "gross_total_return",
        "currency": "CNY",
        "fallback": None,
    }
    assert requirements["beta120"]["window"] == ("PREVIOUS_EXACTLY_120_EXCHANGE_SESSIONS")
    assert requirements["beta120"]["estimator"] == "OLS_SLOPE_WITH_INTERCEPT"
    assert requirements["adv20"]["window"] == "PREVIOUS_EXACTLY_20_EXCHANGE_SESSIONS"
    assert requirements["industry_selection"] == "PIT_PRIMARY_LEVEL_ONE_FOR_FIRST_IS_PROFILE"
    assert requirements["exactly_one_root_strategy_input_ref_per_run"] is True


def test_legacy_compatibility_transport_and_zero_authority_fail_closed(
    repository_root: Path,
) -> None:
    profile = _json(repository_root / PROFILE_MACHINE_PATH)
    legacy = profile["legacy_compatibility"]

    assert legacy["kb_strategy_input_ref_v1"] == "READ_ONLY_COMPATIBILITY_PRESERVED"
    assert legacy["stage3d_and_stage6b_specialized_handoffs"] == ("HISTORICAL_VALIDATION_ONLY")
    assert legacy["silent_alias_or_fallback"] is False
    assert legacy["runtime_cross_repository_read"] is False
    assert all(value is False for value in profile["observed_inputs"].values())
    assert all(value is False for value in profile["authorization_boundary"].values())
    assert profile["next_gate"] == (
        "OWNER_ATOMICALLY_APPROVES_ADR_0002_S6BOUND_01_THROUGH_10_AND_CONSUMER_PROFILE_V0_3"
    )
