from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from invest_system import (
    RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION,
    HashDigest,
    RunReleaseStatusConfirmation,
    RunReleaseStatusConfirmationItem,
    StrategyInputRef,
    canonical_json_bytes,
    status_confirmation_from_canonical_bytes,
)

BASE = datetime(2026, 8, 2, 8, tzinfo=UTC)


def digest(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def input_ref(release_id: str, character: str) -> StrategyInputRef:
    return StrategyInputRef(
        schema_version="1.0.0",
        dataset_release_id=release_id,
        knowledge_cutoff=BASE - timedelta(days=1),
        release_manifest_schema_version="1.0.0",
        manifest_hash=digest(character),
    )


def confirmation_item(
    release_id: str,
    character: str,
    *,
    checked_at: datetime = BASE + timedelta(minutes=2),
) -> RunReleaseStatusConfirmationItem:
    return RunReleaseStatusConfirmationItem(
        strategy_input_ref=input_ref(release_id, character),
        status_observation_id=f"status-{release_id}",
        status_event_id=f"provider/status/{release_id}",
        status_event_hash=digest(character),
        status_sequence=3,
        provider_snapshot_at=checked_at - timedelta(seconds=1),
        checked_at=checked_at,
        response_bytes_hash=digest("f"),
    )


def confirmation() -> RunReleaseStatusConfirmation:
    return RunReleaseStatusConfirmation.create(
        confirmation_id="confirmation-001",
        run_id="run-001",
        root_release_id="root-release",
        receipt_hash=digest("a"),
        closure_hash=digest("b"),
        authority_id="kb-http-current-status-v1",
        authority_contract_hash=digest("c"),
        requested_at=BASE,
        confirmed_at=BASE + timedelta(minutes=3),
        expires_at=BASE + timedelta(minutes=8),
        items=(
            confirmation_item("source-release", "e"),
            confirmation_item("root-release", "d"),
        ),
    )


def schema_validator(repository_root: Path) -> Draft202012Validator:
    common_path = repository_root / "contracts/common/common-defs.schema.json"
    confirmation_path = (
        repository_root
        / "contracts/run-release-status-confirmation"
        / "run-release-status-confirmation.schema.json"
    )
    common = json.loads(common_path.read_text(encoding="utf-8"))
    schema = json.loads(confirmation_path.read_text(encoding="utf-8"))
    registry = Registry[Any]().with_resources(
        [
            (str(common["$id"]), Resource.from_contents(common)),
            (str(schema["$id"]), Resource.from_contents(schema)),
        ]
    )
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def test_create_sorts_complete_release_identities_and_hashes_without_self() -> None:
    value = confirmation()

    assert tuple(item.release_id for item in value.items) == (
        "root-release",
        "source-release",
    )
    assert value.items[0].strategy_input_ref == input_ref("root-release", "d")
    assert "confirmation_hash" not in value.identity_payload()
    assert value.confirmation_hash == HashDigest(
        algorithm="sha256",
        value=sha256(canonical_json_bytes(value.identity_payload())).hexdigest(),
    )
    assert value.to_json_value()["confirmation_hash"] == value.confirmation_hash.to_json_value()
    with pytest.raises(FrozenInstanceError):
        value.run_id = "changed"  # type: ignore[misc]


def test_confirmation_identity_covers_every_declared_field_and_item() -> None:
    value = confirmation()

    with pytest.raises(ValueError, match="confirmation_hash does not match"):
        replace(value, run_id="run-002")
    with pytest.raises(ValueError, match="confirmation_hash does not match"):
        replace(
            value,
            items=(
                replace(value.items[0], response_bytes_hash=digest("9")),
                value.items[1],
            ),
        )
    with pytest.raises(ValueError, match="confirmation_hash does not match"):
        replace(value, confirmation_hash=digest("f"))


def test_items_reject_duplicates_unordered_container_and_wrong_members() -> None:
    root = confirmation_item("root-release", "d")

    with pytest.raises(ValueError, match="duplicate release_id"):
        RunReleaseStatusConfirmation.create(
            confirmation_id="confirmation-001",
            run_id="run-001",
            root_release_id="root-release",
            receipt_hash=digest("a"),
            closure_hash=digest("b"),
            authority_id="authority-001",
            authority_contract_hash=digest("c"),
            requested_at=BASE,
            confirmed_at=BASE + timedelta(minutes=3),
            expires_at=BASE + timedelta(minutes=8),
            items=(root, replace(root, status_observation_id="status-root-repeat")),
        )
    with pytest.raises(TypeError, match="ordered list or tuple"):
        RunReleaseStatusConfirmation.create(
            confirmation_id="confirmation-001",
            run_id="run-001",
            root_release_id="root-release",
            receipt_hash=digest("a"),
            closure_hash=digest("b"),
            authority_id="authority-001",
            authority_contract_hash=digest("c"),
            requested_at=BASE,
            confirmed_at=BASE + timedelta(minutes=3),
            expires_at=BASE + timedelta(minutes=8),
            items=cast(tuple[RunReleaseStatusConfirmationItem, ...], {root}),
        )
    with pytest.raises(TypeError, match="only RunReleaseStatusConfirmationItem"):
        RunReleaseStatusConfirmation.create(
            confirmation_id="confirmation-001",
            run_id="run-001",
            root_release_id="root-release",
            receipt_hash=digest("a"),
            closure_hash=digest("b"),
            authority_id="authority-001",
            authority_contract_hash=digest("c"),
            requested_at=BASE,
            confirmed_at=BASE + timedelta(minutes=3),
            expires_at=BASE + timedelta(minutes=8),
            items=cast(tuple[RunReleaseStatusConfirmationItem, ...], ("wrong",)),
        )


@pytest.mark.parametrize(
    ("changes", "error_type", "message"),
    [
        ({"strategy_input_ref": "wrong"}, TypeError, "StrategyInputRef"),
        ({"status_observation_id": "../bad"}, ValueError, "status_observation_id"),
        ({"status_event_id": "../bad"}, ValueError, "status_event_id"),
        ({"status_event_hash": "a" * 64}, TypeError, "status_event_hash"),
        ({"status_sequence": True}, TypeError, "status_sequence"),
        ({"status_sequence": 0}, ValueError, "at least 1"),
        ({"status_sequence": 2**63}, ValueError, "SQLite"),
        ({"response_bytes_hash": "a" * 64}, TypeError, "response_bytes_hash"),
        ({"provider_snapshot_at": BASE.replace(tzinfo=None)}, ValueError, "timezone-aware UTC"),
        ({"checked_at": BASE.replace(tzinfo=None)}, ValueError, "timezone-aware UTC"),
    ],
)
def test_item_rejects_invalid_identity_time_and_exact_types(
    changes: dict[str, Any],
    error_type: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error_type, match=message):
        replace(confirmation_item("root-release", "d"), **changes)


def test_confirmation_rejects_invalid_window_root_and_hash_types() -> None:
    kwargs: dict[str, Any] = {
        "confirmation_id": "confirmation-001",
        "run_id": "run-001",
        "root_release_id": "root-release",
        "receipt_hash": digest("a"),
        "closure_hash": digest("b"),
        "authority_id": "authority-001",
        "authority_contract_hash": digest("c"),
        "requested_at": BASE,
        "confirmed_at": BASE + timedelta(minutes=3),
        "expires_at": BASE + timedelta(minutes=8),
        "items": (confirmation_item("root-release", "d"),),
    }

    with pytest.raises(ValueError, match="exact ID"):
        RunReleaseStatusConfirmation.create(**(kwargs | {"root_release_id": "latest"}))
    with pytest.raises(ValueError, match="present in items"):
        RunReleaseStatusConfirmation.create(**(kwargs | {"root_release_id": "other-release"}))
    with pytest.raises(ValueError, match="requested_at"):
        RunReleaseStatusConfirmation.create(
            **(kwargs | {"requested_at": BASE + timedelta(minutes=4)})
        )
    with pytest.raises(ValueError, match="confirmed_at"):
        RunReleaseStatusConfirmation.create(
            **(kwargs | {"expires_at": BASE + timedelta(minutes=3)})
        )
    with pytest.raises(ValueError, match="confirmation window"):
        RunReleaseStatusConfirmation.create(
            **(
                kwargs
                | {
                    "items": (
                        confirmation_item(
                            "root-release",
                            "d",
                            checked_at=BASE + timedelta(minutes=4),
                        ),
                    )
                }
            )
        )
    with pytest.raises(TypeError, match="receipt_hash"):
        RunReleaseStatusConfirmation.create(**(kwargs | {"receipt_hash": "a" * 64}))
    with pytest.raises(ValueError, match="schema_version"):
        RunReleaseStatusConfirmation.create(**(kwargs | {"schema_version": "0.2.0-draft"}))


def test_provider_consumer_clock_skew_is_deferred_to_storage_policy() -> None:
    item = confirmation_item("root-release", "d")

    skewed = replace(
        item,
        provider_snapshot_at=item.checked_at + timedelta(seconds=5),
    )

    assert skewed.provider_snapshot_at > skewed.checked_at


def test_strict_canonical_parser_round_trips_the_exact_confirmation() -> None:
    value = confirmation()
    content = value.to_canonical_bytes()

    parsed = status_confirmation_from_canonical_bytes(content)

    assert parsed == value
    assert parsed.to_canonical_bytes() == content
    with pytest.raises(TypeError, match="content must be bytes"):
        status_confirmation_from_canonical_bytes(cast(bytes, bytearray(content)))


@pytest.mark.parametrize(
    "mutation",
    [
        "top-level-extra",
        "item-extra",
        "strategy-ref-extra",
        "hash-extra",
        "bool-sequence",
        "items-not-array",
        "noncanonical-utc-offset",
        "noncanonical-utc-precision",
        "checked-before-requested",
        "confirmed-before-requested",
        "expires-at-confirmed",
    ],
)
def test_strict_canonical_parser_rejects_structural_type_and_time_drift(
    mutation: str,
) -> None:
    value = deepcopy(confirmation().to_json_value())

    if mutation == "top-level-extra":
        value["extra"] = True
    elif mutation == "item-extra":
        value["items"][0]["extra"] = True
    elif mutation == "strategy-ref-extra":
        value["items"][0]["strategy_input_ref"]["release_id"] = "root-release"
    elif mutation == "hash-extra":
        value["receipt_hash"]["encoding"] = "hex"
    elif mutation == "bool-sequence":
        value["items"][0]["status_sequence"] = True
    elif mutation == "items-not-array":
        value["items"] = {"release": value["items"][0]}
    elif mutation == "noncanonical-utc-offset":
        value["requested_at"] = "2026-08-02T08:00:00.000000+00:00"
    elif mutation == "noncanonical-utc-precision":
        value["requested_at"] = "2026-08-02T08:00:00Z"
    elif mutation == "checked-before-requested":
        value["items"][0]["checked_at"] = "2026-08-02T07:59:59.000000Z"
    elif mutation == "confirmed-before-requested":
        value["confirmed_at"] = "2026-08-02T07:59:59.000000Z"
    elif mutation == "expires-at-confirmed":
        value["expires_at"] = value["confirmed_at"]
    else:  # pragma: no cover - parametrization is closed above
        raise AssertionError(mutation)

    with pytest.raises((TypeError, ValueError)):
        status_confirmation_from_canonical_bytes(canonical_json_bytes(value))


def test_strict_canonical_parser_rejects_noncanonical_bytes_and_array_order() -> None:
    value = confirmation()
    content = value.to_canonical_bytes()

    with pytest.raises(ValueError, match="canonical status confirmation"):
        status_confirmation_from_canonical_bytes(content + b"\n")

    document = value.to_json_value()
    document["items"] = list(reversed(document["items"]))
    with pytest.raises(ValueError, match="canonical status confirmation"):
        status_confirmation_from_canonical_bytes(canonical_json_bytes(document))


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b'"not-an-object"',
        b'{"schema_version":',
        b"\xff",
    ],
)
def test_strict_canonical_parser_rejects_invalid_documents(content: bytes) -> None:
    with pytest.raises(ValueError):
        status_confirmation_from_canonical_bytes(content)


def test_confirmation_schema_is_valid_owned_and_matches_model(repository_root: Path) -> None:
    path = (
        repository_root
        / "contracts/run-release-status-confirmation"
        / "run-release-status-confirmation.schema.json"
    )
    schema = json.loads(path.read_text(encoding="utf-8"))

    Draft202012Validator.check_schema(schema)
    assert schema["x-owner"] == "InvestSystem"
    assert schema["x-contract-status"] == "draft"
    assert schema["x-contract-version"] == RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION
    assert schema["x-canonical-profile"] == "investsystem-canonical-json-v1"
    value = confirmation().to_json_value()
    schema_validator(repository_root).validate(value)
    assert set(value) == set(schema["required"]) == set(schema["properties"])
    assert set(value["items"][0]) == set(
        schema["$defs"]["runReleaseStatusConfirmationItem"]["required"]
    )


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-field",
        "latest-root",
        "bare-hash",
        "uppercase-hash",
        "empty-items",
        "item-extra",
        "item-latest",
        "zero-sequence",
        "non-utc-time",
        "wrong-version",
    ],
)
def test_confirmation_schema_rejects_structural_drift(
    repository_root: Path,
    mutation: str,
) -> None:
    value = deepcopy(confirmation().to_json_value())

    if mutation == "extra-field":
        value["transport"] = "read_only_http_api"
    elif mutation == "latest-root":
        value["root_release_id"] = "latest"
    elif mutation == "bare-hash":
        value["confirmation_hash"] = "a" * 64
    elif mutation == "uppercase-hash":
        value["receipt_hash"]["value"] = "A" * 64
    elif mutation == "empty-items":
        value["items"] = []
    elif mutation == "item-extra":
        value["items"][0]["provider"] = "InvestmentResearchKB"
    elif mutation == "item-latest":
        value["items"][0]["strategy_input_ref"]["dataset_release_id"] = "latest"
    elif mutation == "zero-sequence":
        value["items"][0]["status_sequence"] = 0
    elif mutation == "non-utc-time":
        value["confirmed_at"] = "2026-08-02T16:03:00.000000+08:00"
    elif mutation == "wrong-version":
        value["schema_version"] = "0.2.0-draft"
    else:  # pragma: no cover - parametrization is closed above
        raise AssertionError(mutation)

    with pytest.raises(ValidationError):
        schema_validator(repository_root).validate(value)
