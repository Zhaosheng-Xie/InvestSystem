from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from invest_system.canonical import canonical_json_bytes
from invest_system.consumption import (
    ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ArtifactReceiptItem,
    ConsumptionObservationType,
    DeliveryTransport,
    ProviderReleaseStatus,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    ReleaseStatusObservation,
    SchemaValidationResult,
    consumption_observation_from_canonical_bytes,
)
from invest_system.models import HashDigest, StrategyInputRef

FIXED_TIME = datetime(2026, 7, 31, 8, tzinfo=UTC)


def digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


@pytest.fixture
def input_ref() -> StrategyInputRef:
    return StrategyInputRef(
        schema_version="1.0.0",
        dataset_release_id="synthetic_release_consumption_001",
        knowledge_cutoff=FIXED_TIME,
        release_manifest_schema_version="1.0.0",
        manifest_hash=digest("a"),
    )


@pytest.fixture
def receipt_items() -> tuple[ArtifactReceiptItem, ArtifactReceiptItem]:
    return (
        ArtifactReceiptItem(
            artifact_id="facts_b",
            item_type="verified-facts",
            artifact_hash=digest("b"),
            size_bytes=20,
            record_count=None,
        ),
        ArtifactReceiptItem(
            artifact_id="facts_a",
            item_type="verified-facts",
            artifact_hash=digest("c"),
            size_bytes=10,
            record_count=1,
        ),
    )


@pytest.fixture
def receipt(
    input_ref: StrategyInputRef,
    receipt_items: tuple[ArtifactReceiptItem, ArtifactReceiptItem],
) -> ArtifactConsumptionReceipt:
    return ArtifactConsumptionReceipt.create(
        consumer_contract_version="1.0.0",
        strategy_input_ref=input_ref,
        artifacts=receipt_items,
    )


def test_receipt_sorts_artifacts_and_hashes_explicit_payload_without_self(
    receipt: ArtifactConsumptionReceipt,
) -> None:
    assert tuple(item.artifact_id for item in receipt.artifacts) == ("facts_a", "facts_b")
    assert receipt.artifacts[1].record_count is None
    payload = receipt.identity_payload()
    assert set(payload) == {
        "schema_version",
        "consumer_contract_version",
        "strategy_input_ref",
        "artifacts",
    }
    assert "receipt_hash" not in payload
    assert receipt.receipt_hash == HashDigest(
        algorithm="sha256",
        value=sha256(canonical_json_bytes(payload)).hexdigest(),
    )
    assert receipt.to_json_value()["receipt_hash"] == receipt.receipt_hash.to_json_value()


def test_receipt_is_order_independent_but_rejects_duplicate_artifact_ids(
    input_ref: StrategyInputRef,
    receipt_items: tuple[ArtifactReceiptItem, ArtifactReceiptItem],
) -> None:
    forward = ArtifactConsumptionReceipt.create(
        consumer_contract_version="1.0.0",
        strategy_input_ref=input_ref,
        artifacts=receipt_items,
    )
    reverse = ArtifactConsumptionReceipt.create(
        consumer_contract_version="1.0.0",
        strategy_input_ref=input_ref,
        artifacts=tuple(reversed(receipt_items)),
    )
    assert forward.to_canonical_bytes() == reverse.to_canonical_bytes()
    assert forward.receipt_hash == reverse.receipt_hash

    conflicting = replace(receipt_items[0], artifact_hash=digest("d"))
    with pytest.raises(ValueError, match="duplicate artifact_id"):
        ArtifactConsumptionReceipt.create(
            consumer_contract_version="1.0.0",
            strategy_input_ref=input_ref,
            artifacts=(receipt_items[0], conflicting),
        )


def test_receipt_rejects_wrong_self_hash_empty_or_unordered_items(
    receipt: ArtifactConsumptionReceipt,
    input_ref: StrategyInputRef,
    receipt_items: tuple[ArtifactReceiptItem, ArtifactReceiptItem],
) -> None:
    with pytest.raises(ValueError, match="receipt_hash does not match"):
        replace(receipt, receipt_hash=digest("f"))
    with pytest.raises(ValueError, match="must not be empty"):
        ArtifactConsumptionReceipt.create(
            consumer_contract_version="1.0.0",
            strategy_input_ref=input_ref,
            artifacts=(),
        )
    with pytest.raises(TypeError, match="ordered list or tuple"):
        ArtifactConsumptionReceipt.create(
            consumer_contract_version="1.0.0",
            strategy_input_ref=input_ref,
            artifacts=set(receipt_items),
        )


@pytest.mark.parametrize(
    ("changes", "error_type"),
    [
        ({"artifact_id": "../facts"}, ValueError),
        ({"item_type": ""}, ValueError),
        ({"size_bytes": -1}, ValueError),
        ({"size_bytes": 1.0}, TypeError),
        ({"record_count": -1}, ValueError),
        ({"record_count": True}, TypeError),
        ({"artifact_hash": "a" * 64}, TypeError),
    ],
)
def test_receipt_item_validates_exact_types(
    receipt_items: tuple[ArtifactReceiptItem, ArtifactReceiptItem],
    changes: dict[str, object],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        replace(receipt_items[0], **changes)  # type: ignore[arg-type]


def test_observation_axes_are_separate_and_provider_event_identity_is_preserved(
    input_ref: StrategyInputRef,
    receipt: ArtifactConsumptionReceipt,
) -> None:
    fetch = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_observation_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        source_endpoint="https://provider.invalid/releases/release_001",
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(item.artifact_id for item in reversed(receipt.artifacts)),
        response_or_export_bytes_hash=digest("d"),
        local_cache_keys=("sha256/dd/dddddd",),
    )
    status = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="status_observation_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.PUBLISHED,
        status_event_id="provider_status_event_001",
        status_event_hash=digest("e"),
        previous_status_event_hash=digest("d"),
        status_sequence=3,
        status_recorded_at=FIXED_TIME,
    )
    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="admission_observation_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        status_observation_id=status.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
    )

    fetch_value = fetch.to_json_value()
    status_value = status.to_json_value()
    admission_value = admission.to_json_value()
    assert fetch_value["observation_type"] == ConsumptionObservationType.ARTIFACT_FETCH
    assert status_value["observation_type"] == ConsumptionObservationType.RELEASE_STATUS
    assert admission_value["observation_type"] == ConsumptionObservationType.RELEASE_ADMISSION
    assert "status_event_id" not in fetch_value
    assert "admission_status" not in status_value
    assert "status_event_id" not in admission_value
    assert status_value["status_event_id"] == "provider_status_event_001"
    assert status_value["status_event_hash"] == digest("e").to_json_value()
    assert admission.status_observation_id == status.observation_id
    assert fetch.artifact_ids == ("facts_a", "facts_b")
    assert fetch.strategy_input_ref == status.strategy_input_ref == admission.strategy_input_ref


def test_canonical_observation_parser_round_trips_all_axes_and_rejects_drift(
    input_ref: StrategyInputRef,
    receipt: ArtifactConsumptionReceipt,
) -> None:
    fetch = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_strict_parser_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        transport=DeliveryTransport.IMMUTABLE_EXPORT,
        source_endpoint="export:strict-parser",
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(item.artifact_id for item in receipt.artifacts),
        response_or_export_bytes_hash=digest("1"),
        local_cache_keys=("sha256/strict-parser",),
    )
    status = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="status_strict_parser_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.PUBLISHED,
        status_event_id="provider/status/strict-parser",
        status_event_hash=digest("2"),
        previous_status_event_hash=digest("1"),
        status_sequence=2,
        status_recorded_at=FIXED_TIME,
    )
    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="admission_strict_parser_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        status_observation_id=status.observation_id,
        admission_status=ReleaseAdmissionStatus.AUTHORIZED,
    )
    for observation in (fetch, status, admission):
        assert (
            consumption_observation_from_canonical_bytes(observation.to_canonical_bytes())
            == observation
        )

    invalid_documents: list[dict[str, Any]] = []
    unexpected = status.to_json_value()
    unexpected["unexpected_contract_field"] = True
    invalid_documents.append(unexpected)
    nested_input = status.to_json_value()
    nested_input["strategy_input_ref"]["unexpected_contract_field"] = True
    invalid_documents.append(nested_input)
    nested_hash = status.to_json_value()
    nested_hash["status_event_hash"]["unexpected_contract_field"] = True
    invalid_documents.append(nested_hash)
    bool_sequence = status.to_json_value()
    bool_sequence["status_sequence"] = True
    invalid_documents.append(bool_sequence)
    noncanonical_time = status.to_json_value()
    noncanonical_time["observed_at"] = "2026-07-31T08:00:00+00:00"
    invalid_documents.append(noncanonical_time)
    future_status_time = status.to_json_value()
    future_status_time["status_recorded_at"] = "2026-07-31T08:00:00.000001Z"
    invalid_documents.append(future_status_time)

    for document in invalid_documents:
        with pytest.raises((TypeError, ValueError)):
            consumption_observation_from_canonical_bytes(canonical_json_bytes(document))

    with pytest.raises(ValueError, match="SQLite signed integer limit"):
        replace(status, status_sequence=2**63)


def test_observations_enforce_failure_and_admission_semantics(
    input_ref: StrategyInputRef,
) -> None:
    with pytest.raises(ValueError, match="failed fetch observation requires"):
        ArtifactFetchObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="fetch_failed_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            transport="immutable_export",  # type: ignore[arg-type]
            source_endpoint="authorized-export-001",
            schema_validation_result="failed",  # type: ignore[arg-type]
        )

    failed_fetch = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_failed_001",
        release_id=input_ref.dataset_release_id,
        strategy_input_ref=input_ref,
        observed_at=FIXED_TIME,
        transport="immutable_export",  # type: ignore[arg-type]
        source_endpoint="authorized-export-001",
        schema_validation_result="failed",  # type: ignore[arg-type]
        failure_reasons=("artifact_hash_mismatch",),
    )
    assert failed_fetch.transport is DeliveryTransport.IMMUTABLE_EXPORT
    assert failed_fetch.schema_validation_result is SchemaValidationResult.FAILED

    with pytest.raises(ValueError, match="must not expose receipt_hash or artifact_ids"):
        replace(
            failed_fetch,
            receipt_hash=digest("b"),
            artifact_ids=("facts_a",),
        )

    with pytest.raises(ValueError, match="requires status"):
        ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="status_invalid_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.PASSED,
        )
    with pytest.raises(ValueError, match="status_sequence"):
        ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="status_invalid_sequence_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.PASSED,
            status=ProviderReleaseStatus.PUBLISHED,
            status_event_id="provider_status_event_invalid_sequence_001",
            status_event_hash=digest("a"),
            status_sequence=0,
            status_recorded_at=FIXED_TIME,
        )
    with pytest.raises(ValueError, match="must be <= observed_at"):
        ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="status_future_recorded_at_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.PASSED,
            status=ProviderReleaseStatus.PUBLISHED,
            status_event_id="provider_status_event_future_001",
            status_event_hash=digest("a"),
            status_sequence=1,
            status_recorded_at=FIXED_TIME + timedelta(microseconds=1),
        )
    with pytest.raises(ValueError, match="must not expose"):
        ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="status_invalid_002",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.FAILED,
            status=ProviderReleaseStatus.PUBLISHED,
            status_event_id="untrusted_event_001",
            status_event_hash=digest("a"),
            failure_reasons=("status_event_hash_mismatch",),
        )
    with pytest.raises(ValueError, match="requires failure_reasons"):
        ReleaseAdmissionObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="admission_unconfirmed_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            status_observation_id="status_failed_001",
            admission_status=ReleaseAdmissionStatus.UNCONFIRMED,
        )
    with pytest.raises(ValueError, match="authorized admission"):
        ReleaseAdmissionObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="admission_authorized_001",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            status_observation_id="status_passed_001",
            admission_status=ReleaseAdmissionStatus.AUTHORIZED,
            failure_reasons=("unexpected_reason",),
        )


def test_observations_reject_latest_non_utc_unknown_enum_and_self_supersession(
    input_ref: StrategyInputRef,
    receipt: ArtifactConsumptionReceipt,
) -> None:
    common: dict[str, Any] = {
        "schema_version": CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        "observation_id": "fetch_observation_001",
        "release_id": input_ref.dataset_release_id,
        "strategy_input_ref": input_ref,
        "observed_at": FIXED_TIME,
        "transport": DeliveryTransport.READ_ONLY_HTTP_API,
        "source_endpoint": "https://provider.invalid/release_001",
        "schema_validation_result": SchemaValidationResult.PASSED,
        "receipt_hash": receipt.receipt_hash,
        "artifact_ids": ("facts_a", "facts_b"),
    }
    with pytest.raises(ValueError, match="exact ID"):
        ArtifactFetchObservation(**{**common, "release_id": "latest"})
    with pytest.raises(ValueError, match="non-zero offset"):
        ArtifactFetchObservation(
            **{
                **common,
                "observed_at": datetime(
                    2026,
                    7,
                    31,
                    16,
                    tzinfo=timezone(timedelta(hours=8)),
                ),
            }
        )
    with pytest.raises(ValueError, match="transport must be one of"):
        ArtifactFetchObservation(**{**common, "transport": "shared_directory"})
    with pytest.raises(ValueError, match="must not refer"):
        ArtifactFetchObservation(
            **{**common, "supersedes": common["observation_id"]},
        )


def test_every_observation_binds_the_full_input_reference_identity(
    input_ref: StrategyInputRef,
    receipt: ArtifactConsumptionReceipt,
) -> None:
    mismatched_ref = replace(input_ref, dataset_release_id="different_release_001")
    common: dict[str, Any] = {
        "schema_version": CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        "release_id": input_ref.dataset_release_id,
        "strategy_input_ref": mismatched_ref,
        "observed_at": FIXED_TIME,
    }

    with pytest.raises(ValueError, match="does not match release_id"):
        ArtifactFetchObservation(
            **common,
            observation_id="fetch_identity_mismatch_001",
            transport=DeliveryTransport.READ_ONLY_HTTP_API,
            source_endpoint="https://provider.invalid/manifest",
            schema_validation_result=SchemaValidationResult.PASSED,
            receipt_hash=receipt.receipt_hash,
            artifact_ids=("facts_a",),
        )
    with pytest.raises(ValueError, match="does not match release_id"):
        ReleaseStatusObservation(
            **common,
            observation_id="status_identity_mismatch_001",
            schema_validation_result=SchemaValidationResult.PASSED,
            status=ProviderReleaseStatus.PUBLISHED,
            status_event_id="provider_status_event_001",
            status_event_hash=digest("c"),
            previous_status_event_hash=digest("b"),
            status_sequence=3,
            status_recorded_at=FIXED_TIME,
        )
    with pytest.raises(ValueError, match="does not match release_id"):
        ReleaseAdmissionObservation(
            **common,
            observation_id="admission_identity_mismatch_001",
            status_observation_id="status_observation_001",
            admission_status=ReleaseAdmissionStatus.AUTHORIZED,
        )


def test_transport_time_and_endpoint_never_enter_receipt_identity(
    receipt: ArtifactConsumptionReceipt,
) -> None:
    first = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_observation_001",
        release_id=receipt.strategy_input_ref.dataset_release_id,
        strategy_input_ref=receipt.strategy_input_ref,
        observed_at=FIXED_TIME,
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        source_endpoint="https://one.invalid/manifest",
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(item.artifact_id for item in receipt.artifacts),
    )
    second = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_observation_002",
        release_id=receipt.strategy_input_ref.dataset_release_id,
        strategy_input_ref=receipt.strategy_input_ref,
        observed_at=FIXED_TIME + timedelta(seconds=1),
        transport=DeliveryTransport.IMMUTABLE_EXPORT,
        source_endpoint="authorized-export-002",
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(item.artifact_id for item in receipt.artifacts),
    )

    assert first.to_canonical_bytes() != second.to_canonical_bytes()
    identity = receipt.identity_payload()
    assert "observed_at" not in identity
    assert "transport" not in identity
    assert "source_endpoint" not in identity
    assert receipt.receipt_hash.value == sha256(canonical_json_bytes(identity)).hexdigest()


def load_contracts(repository_root: Path) -> dict[str, dict[str, Any]]:
    paths = {
        "common": repository_root / "contracts/common/common-defs.schema.json",
        "receipt": (
            repository_root
            / "contracts/artifact-consumption-receipt/artifact-consumption-receipt.schema.json"
        ),
        "observations": (
            repository_root / "contracts/observations/consumption-observations.schema.json"
        ),
    }
    return {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}


def contract_registry(contracts: dict[str, dict[str, Any]]) -> Registry[Any]:
    return Registry[Any]().with_resources(
        [
            (str(document["$id"]), Resource.from_contents(document))
            for document in contracts.values()
        ]
    )


def validator(
    name: str,
    contracts: dict[str, dict[str, Any]],
) -> Draft202012Validator:
    return Draft202012Validator(
        contracts[name],
        registry=contract_registry(contracts),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def test_consumption_contracts_are_valid_and_models_serialize_to_them(
    repository_root: Path,
    receipt: ArtifactConsumptionReceipt,
) -> None:
    contracts = load_contracts(repository_root)
    for name in ("receipt", "observations"):
        Draft202012Validator.check_schema(contracts[name])
        assert contracts[name]["x-owner"] == "InvestSystem"
        assert contracts[name]["x-contract-status"] == "draft"
    assert contracts["receipt"]["x-contract-version"] == "0.1.0-draft"
    assert contracts["observations"]["x-contract-version"] == "0.2.0-draft"

    fetch = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="fetch_observation_schema_001",
        release_id=receipt.strategy_input_ref.dataset_release_id,
        strategy_input_ref=receipt.strategy_input_ref,
        observed_at=FIXED_TIME,
        transport=DeliveryTransport.IMMUTABLE_EXPORT,
        source_endpoint="authorized-export-schema-001",
        schema_validation_result=SchemaValidationResult.FAILED,
        failure_reasons=("artifact_schema_invalid",),
    )
    status = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="status_observation_schema_001",
        release_id=receipt.strategy_input_ref.dataset_release_id,
        strategy_input_ref=receipt.strategy_input_ref,
        observed_at=FIXED_TIME,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.WITHDRAWN,
        status_event_id="provider_status_event_schema_001",
        status_event_hash=digest("e"),
        previous_status_event_hash=digest("d"),
        status_sequence=4,
        status_recorded_at=FIXED_TIME,
    )
    admission = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id="admission_observation_schema_001",
        release_id=receipt.strategy_input_ref.dataset_release_id,
        strategy_input_ref=receipt.strategy_input_ref,
        observed_at=FIXED_TIME,
        status_observation_id=status.observation_id,
        admission_status=ReleaseAdmissionStatus.DENIED,
        failure_reasons=("release_withdrawn",),
    )

    validator("receipt", contracts).validate(receipt.to_json_value())
    for observation in (fetch, status, admission):
        validator("observations", contracts).validate(observation.to_json_value())


@pytest.mark.parametrize(
    "mutation",
    [
        "receipt-extra-observation",
        "receipt-bare-hash",
        "receipt-float-size",
        "fetch-passed-with-failure",
        "fetch-failed-with-success-fields",
        "fetch-missing-input-ref",
        "status-passed-without-event-hash",
        "status-passed-without-sequence",
        "status-sequence-overflow",
        "status-failed-with-untrusted-event",
        "admission-authorized-with-failure",
        "admission-unknown-state",
    ],
)
def test_consumption_schemas_fail_closed(
    repository_root: Path,
    receipt: ArtifactConsumptionReceipt,
    mutation: str,
) -> None:
    contracts = load_contracts(repository_root)
    if mutation.startswith("receipt-"):
        value = deepcopy(receipt.to_json_value())
        if mutation == "receipt-extra-observation":
            value["observed_at"] = "2026-07-31T08:00:00.000000Z"
        elif mutation == "receipt-bare-hash":
            value["receipt_hash"] = "a" * 64
        elif mutation == "receipt-float-size":
            value["artifacts"][0]["size_bytes"] = 1.5
        else:  # pragma: no cover - parametrization is closed above
            raise AssertionError(mutation)
        with pytest.raises(ValidationError):
            validator("receipt", contracts).validate(value)
        return

    if mutation in {
        "fetch-passed-with-failure",
        "fetch-failed-with-success-fields",
        "fetch-missing-input-ref",
    }:
        value = ArtifactFetchObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="fetch_schema_failure_001",
            release_id=receipt.strategy_input_ref.dataset_release_id,
            strategy_input_ref=receipt.strategy_input_ref,
            observed_at=FIXED_TIME,
            transport=DeliveryTransport.READ_ONLY_HTTP_API,
            source_endpoint="https://provider.invalid/release_schema_001",
            schema_validation_result=SchemaValidationResult.PASSED,
            receipt_hash=receipt.receipt_hash,
            artifact_ids=tuple(item.artifact_id for item in receipt.artifacts),
        ).to_json_value()
        if mutation == "fetch-passed-with-failure":
            value["failure_reasons"] = ["unexpected_failure"]
        elif mutation == "fetch-failed-with-success-fields":
            value["schema_validation_result"] = "failed"
            value["failure_reasons"] = ["artifact_hash_mismatch"]
        else:
            del value["strategy_input_ref"]
    elif mutation in {
        "status-passed-without-event-hash",
        "status-passed-without-sequence",
        "status-sequence-overflow",
        "status-failed-with-untrusted-event",
    }:
        value = ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="status_schema_failure_001",
            release_id=receipt.strategy_input_ref.dataset_release_id,
            strategy_input_ref=receipt.strategy_input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.PASSED,
            status=ProviderReleaseStatus.PUBLISHED,
            status_event_id="provider_status_event_schema_001",
            status_event_hash=digest("a"),
            previous_status_event_hash=digest("b"),
            status_sequence=3,
            status_recorded_at=FIXED_TIME,
        ).to_json_value()
        if mutation == "status-passed-without-event-hash":
            value["status_event_hash"] = None
        elif mutation == "status-passed-without-sequence":
            value["status_sequence"] = None
        elif mutation == "status-sequence-overflow":
            value["status_sequence"] = 2**63
        else:
            value["schema_validation_result"] = "failed"
            value["failure_reasons"] = ["status_event_hash_mismatch"]
    else:
        value = ReleaseAdmissionObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id="admission_schema_failure_001",
            release_id=receipt.strategy_input_ref.dataset_release_id,
            strategy_input_ref=receipt.strategy_input_ref,
            observed_at=FIXED_TIME,
            status_observation_id="status_schema_001",
            admission_status=ReleaseAdmissionStatus.AUTHORIZED,
        ).to_json_value()
        if mutation == "admission-authorized-with-failure":
            value["failure_reasons"] = ["unexpected_failure"]
        elif mutation == "admission-unknown-state":
            value["admission_status"] = "unknown"
        else:  # pragma: no cover - parametrization is closed above
            raise AssertionError(mutation)

    with pytest.raises(ValidationError):
        validator("observations", contracts).validate(value)


def test_contract_schema_versions_are_exact_constants() -> None:
    assert ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION == "0.1.0-draft"
    assert CONSUMPTION_OBSERVATION_SCHEMA_VERSION == "0.2.0-draft"


def test_provider_status_axis_preserves_every_public_release_state(
    repository_root: Path,
    input_ref: StrategyInputRef,
) -> None:
    assert {status.value for status in ProviderReleaseStatus} == {
        "building",
        "validated",
        "published",
        "withdrawn",
    }
    contracts = load_contracts(repository_root)
    for index, status in enumerate(ProviderReleaseStatus):
        observation = ReleaseStatusObservation(
            schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
            observation_id=f"status_axis_{index}",
            release_id=input_ref.dataset_release_id,
            strategy_input_ref=input_ref,
            observed_at=FIXED_TIME,
            schema_validation_result=SchemaValidationResult.PASSED,
            status=status,
            status_event_id=(
                "provider/events/" + ("x" * 239) + str(index)
                if index == 0
                else f"provider_status_event_{index}"
            ),
            status_event_hash=digest("a"),
            previous_status_event_hash=digest("a") if index > 0 else None,
            status_sequence=index + 1,
            status_recorded_at=FIXED_TIME,
        )
        validator("observations", contracts).validate(observation.to_json_value())
