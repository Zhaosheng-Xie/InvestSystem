from __future__ import annotations

import copy
from typing import Any, cast

import pytest

from invest_system.domain.synthetic_fixture import (
    ApprovedSyntheticFixtureCapability,
    FailureInjectionFixtureRegistration,
    SyntheticFixtureAuthorizationError,
    SyntheticFixtureRegistry,
)
from invest_system.models import HashDigest
from invest_system.strategies.industrial_event import (
    IndustrialEventEvaluationError,
    evaluate_industrial_event,
)
from stage2b_support import (
    STAGE2B_BLOCKED_PATH,
    STAGE2B_GOLDEN_PATH,
    STAGE2B_REGISTRY_PATH,
    build_stage2b_fixture_registry,
    find_case,
    fixture_capability_for,
    load_approved_stage2b_artifacts,
    load_json_object,
    load_stage2b_fixture_registry,
    materialize_stage2b_case,
)

_PINNED_REGISTRY_SNAPSHOT = "9c746809cf9d56bf54419dead7dbe33331b0fce9e17899993d1307795fb629d7"


def _trade_case() -> Any:
    matrix = load_json_object(STAGE2B_GOLDEN_PATH)
    vector = find_case(cast(list[dict[str, Any]], matrix["cases"]), "SYN-TRADE-001")
    return materialize_stage2b_case(vector)


def _exact_capability_arguments(materialized: Any) -> dict[str, Any]:
    case = materialized.case
    strategy_input = case.strategy_input
    verified = strategy_input.verified_knowledge_input
    return {
        "strategy_id": materialized.manifest.strategy_id,
        "case_id": case.case_id,
        "fixture_id": strategy_input.fixture_id,
        "fixture_version": strategy_input.fixture_version,
        "dataset_release_id": verified.strategy_input_ref.dataset_release_id,
        "input_id": verified.input_id,
        "input_envelope_hash": HashDigest(
            algorithm="sha256",
            value=strategy_input.canonical_sha256(),
        ),
        "verified_input_hash": strategy_input.fixture_payload_hash,
        "strategy_case_input_hash": case.semantic_input_hash(),
        "strategy_case_envelope_hash": HashDigest(
            algorithm="sha256",
            value=case.canonical_sha256(),
        ),
    }


def test_checked_in_registry_is_complete_rebuildable_and_pinned() -> None:
    loaded = load_stage2b_fixture_registry()
    rebuilt = build_stage2b_fixture_registry()

    assert len(loaded.strategy_records) == 24
    assert len(loaded.failure_records) == 10
    assert loaded.snapshot_hash.value == _PINNED_REGISTRY_SNAPSHOT
    assert rebuilt.snapshot_hash == loaded.snapshot_hash
    assert rebuilt.to_artifact_payload() == loaded.to_artifact_payload()


def test_capability_binds_the_four_non_overlapping_input_identities() -> None:
    materialized = _trade_case()
    capability = fixture_capability_for(materialized)
    arguments = _exact_capability_arguments(materialized)

    capability.require_exact(**arguments)
    assert capability.input_envelope_hash == materialized.manifest.input_envelope_hash
    assert capability.verified_input_hash == materialized.case.strategy_input.fixture_payload_hash
    assert capability.strategy_case_input_hash == materialized.manifest.strategy_case_input_hash
    assert (
        capability.strategy_case_envelope_hash == materialized.manifest.strategy_case_envelope_hash
    )


def test_capability_constructor_rejects_non_registry_issuer() -> None:
    registry = load_stage2b_fixture_registry()
    registration = registry.strategy_records[0]

    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="SYNTHETIC_FIXTURE_CAPABILITY_ISSUER_INVALID",
    ):
        ApprovedSyntheticFixtureCapability(
            _issuer=object(),
            registration=registration,
            registry_snapshot_hash=registry.snapshot_hash,
        )


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    (
        ("strategy_id", "industrial_bottleneck"),
        ("case_id", "SYN-TRADE"),
        ("fixture_id", "synthetic_fixture_stage2b_trade"),
        ("fixture_version", "0.1.1"),
        ("dataset_release_id", "synthetic_release_stage2b_trade"),
        ("input_id", "synthetic_input_stage2b_trade"),
        ("input_envelope_hash", HashDigest(algorithm="sha256", value="0" * 64)),
        ("verified_input_hash", HashDigest(algorithm="sha256", value="1" * 64)),
        ("strategy_case_input_hash", HashDigest(algorithm="sha256", value="2" * 64)),
        ("strategy_case_envelope_hash", HashDigest(algorithm="sha256", value="3" * 64)),
    ),
)
def test_capability_rejects_every_identity_or_content_drift(
    field_name: str,
    replacement: Any,
) -> None:
    materialized = _trade_case()
    capability = fixture_capability_for(materialized)
    arguments = _exact_capability_arguments(materialized)
    arguments[field_name] = replacement

    with pytest.raises(SyntheticFixtureAuthorizationError):
        capability.require_exact(**arguments)


def test_prefix_only_identity_is_not_a_registry_match() -> None:
    materialized = _trade_case()
    registry = load_stage2b_fixture_registry()

    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="SYNTHETIC_FIXTURE_NOT_REGISTERED",
    ):
        registry.require_strategy_case(
            strategy_id=materialized.manifest.strategy_id,
            case_id="SYN-TRADE",
            strategy_input=materialized.case.strategy_input,
            strategy_case_envelope=materialized.case,
            strategy_case_input_hash=materialized.case.semantic_input_hash(),
        )


def test_old_capability_rejects_materialized_business_content_mutation() -> None:
    matrix = load_json_object(STAGE2B_GOLDEN_PATH)
    vector = find_case(cast(list[dict[str, Any]], matrix["cases"]), "SYN-TRADE-001")
    baseline = materialize_stage2b_case(vector)
    capability = fixture_capability_for(baseline)
    changed = materialize_stage2b_case(
        vector,
        additional_mutations=(
            {
                "op": "replace",
                "path": "/commercial_event/seller_legal_entity_id",
                "value": "SYN-SELLER-CHANGED-999",
            },
        ),
    )

    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="SYNTHETIC_FIXTURE_INPUT_ENVELOPE_HASH_MISMATCH",
    ):
        capability.require_exact(**_exact_capability_arguments(changed))


def test_failure_inventory_validates_exact_payload_but_never_issues_capability() -> None:
    registry = load_stage2b_fixture_registry()
    matrix = load_json_object(STAGE2B_BLOCKED_PATH)
    vector = cast(list[dict[str, Any]], matrix["cases"])[0]
    payload = cast(dict[str, Any], vector["failure_input"])
    registration = registry.require_failure_payload(
        case_id=cast(str, vector["case_id"]),
        fixture_id=cast(str, payload["fixture_id"]),
        fixture_version=cast(str, matrix["fixture_matrix_schema_version"]),
        failure_payload=payload,
    )

    assert isinstance(registration, FailureInjectionFixtureRegistration)
    assert not isinstance(registration, ApprovedSyntheticFixtureCapability)

    changed = copy.deepcopy(payload)
    changed["input_id"] = f"{changed['input_id']}_changed"
    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="FAILURE_INJECTION_FIXTURE_HASH_MISMATCH",
    ):
        registry.require_failure_payload(
            case_id=cast(str, vector["case_id"]),
            fixture_id=cast(str, payload["fixture_id"]),
            fixture_version=cast(str, matrix["fixture_matrix_schema_version"]),
            failure_payload=changed,
        )


def test_dynamic_registry_cannot_reproduce_the_pinned_aggregate() -> None:
    official = load_stage2b_fixture_registry()
    materialized = _trade_case()
    registration = next(
        record for record in official.strategy_records if record.case_id == "SYN-TRADE-001"
    )
    dynamic = SyntheticFixtureRegistry((registration,))
    dynamic_capability = fixture_capability_for(materialized, dynamic)

    assert dynamic.snapshot_hash != official.snapshot_hash
    assert dynamic_capability.registry_snapshot_hash != official.snapshot_hash

    approved = load_approved_stage2b_artifacts()
    with pytest.raises(
        IndustrialEventEvaluationError,
        match="SYNTHETIC_FIXTURE_REGISTRY_UNTRUSTED",
    ):
        evaluate_industrial_event(
            materialized.case,
            rule_document=approved.document,
            approval_capability=approved.capability,
            fixture_capability=dynamic_capability,
        )


def test_registry_parser_rejects_unknown_fields_and_aggregate_drift() -> None:
    artifact = load_json_object(STAGE2B_REGISTRY_PATH)
    unknown = copy.deepcopy(artifact)
    unknown["untrusted_extension"] = True
    with pytest.raises(ValueError, match="fields differ"):
        SyntheticFixtureRegistry.from_artifact_payload(unknown)

    drifted = copy.deepcopy(artifact)
    snapshot = cast(dict[str, str], drifted["registry_snapshot_hash"])
    snapshot["value"] = "f" * 64
    with pytest.raises(
        SyntheticFixtureAuthorizationError,
        match="SYNTHETIC_FIXTURE_REGISTRY_SNAPSHOT_MISMATCH",
    ):
        SyntheticFixtureRegistry.from_artifact_payload(drifted)
