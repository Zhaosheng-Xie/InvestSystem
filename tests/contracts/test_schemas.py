from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from invest_system import (
    DecisionRecord,
    GateResult,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
    VerifiedKnowledgeInput,
)

SCHEMA_PATHS = {
    "common": Path("contracts/common/common-defs.schema.json"),
    "verified_knowledge_input": Path(
        "contracts/verified-knowledge-input/verified-knowledge-input.schema.json"
    ),
    "gate_result": Path("contracts/gate-result/gate-result.schema.json"),
    "strategy_run_manifest": Path(
        "contracts/strategy-run-manifest/strategy-run-manifest.schema.json"
    ),
    "decision_record": Path("contracts/decision-record/decision-record.schema.json"),
}


def load_schemas(repository_root: Path) -> dict[str, dict[str, Any]]:
    return {
        name: json.loads((repository_root / path).read_text(encoding="utf-8"))
        for name, path in SCHEMA_PATHS.items()
    }


def make_registry(schemas: dict[str, dict[str, Any]]) -> Registry[Any]:
    resources: list[tuple[str, Resource[Any]]] = []
    for schema in schemas.values():
        resource_id = schema.get("$id")
        if not isinstance(resource_id, str):
            raise TypeError("schema $id must be a string")
        resources.append((resource_id, Resource.from_contents(schema)))
    return Registry[Any]().with_resources(resources)


def make_validator(
    name: str,
    schemas: dict[str, dict[str, Any]],
) -> Draft202012Validator:
    return Draft202012Validator(
        schemas[name],
        registry=make_registry(schemas),
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def iter_references(value: Any) -> list[str]:
    references: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "$ref" and isinstance(nested, str):
                references.append(nested)
            else:
                references.extend(iter_references(nested))
    elif isinstance(value, list):
        for nested in value:
            references.extend(iter_references(nested))
    return references


def test_all_contracts_are_valid_draft_2020_12_schemas(repository_root: Path) -> None:
    schemas = load_schemas(repository_root)
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
        assert schema["x-owner"] == "InvestSystem"
        assert schema["x-contract-status"] == "draft"
        assert schema["x-contract-version"] == "0.1.0-draft"
        assert schema["$id"].startswith("https://schemas.investsystem.local/")


def test_every_schema_reference_resolves_from_the_checked_in_registry(
    repository_root: Path,
) -> None:
    schemas = load_schemas(repository_root)
    registered_ids = {schema["$id"] for schema in schemas.values()}

    for schema in schemas.values():
        for reference in iter_references(schema):
            referenced_document = reference.split("#", maxsplit=1)[0]
            if referenced_document:
                assert referenced_document in registered_ids


def test_models_serialize_to_their_draft_schemas(
    repository_root: Path,
    verified_knowledge_input: VerifiedKnowledgeInput,
    gate_result: GateResult,
    strategy_run_manifest: StrategyRunManifest,
    decision_record: DecisionRecord,
) -> None:
    schemas = load_schemas(repository_root)
    values = {
        "verified_knowledge_input": verified_knowledge_input.to_json_value(),
        "gate_result": gate_result.to_json_value(),
        "strategy_run_manifest": strategy_run_manifest.to_json_value(),
        "decision_record": decision_record.to_json_value(),
    }

    for name, value in values.items():
        make_validator(name, schemas).validate(value)


@pytest.mark.parametrize(
    "mutation",
    [
        "latest-release",
        "bare-hash",
        "uppercase-hash",
        "non-utc-time",
        "invalid-calendar-date",
        "release-id-alias",
        "extra-field",
        "nested-float",
    ],
)
def test_verified_input_schema_fails_closed_on_contract_drift(
    repository_root: Path,
    verified_knowledge_input: VerifiedKnowledgeInput,
    mutation: str,
) -> None:
    schemas = load_schemas(repository_root)
    value = deepcopy(verified_knowledge_input.to_json_value())
    reference = value["strategy_input_ref"]

    if mutation == "latest-release":
        reference["dataset_release_id"] = "latest"
    elif mutation == "bare-hash":
        reference["manifest_hash"] = "a" * 64
    elif mutation == "uppercase-hash":
        reference["manifest_hash"]["value"] = "A" * 64
    elif mutation == "non-utc-time":
        reference["knowledge_cutoff"] = "2026-07-30T16:00:00.000000+08:00"
    elif mutation == "invalid-calendar-date":
        reference["knowledge_cutoff"] = "2026-02-30T08:00:00.000000Z"
    elif mutation == "release-id-alias":
        reference["release_id"] = reference.pop("dataset_release_id")
    elif mutation == "extra-field":
        reference["downloaded_at"] = "2026-07-30T08:00:00.000000Z"
    elif mutation == "nested-float":
        value["facts"][0]["value"]["amount_scaled"] = 1.25
    else:  # pragma: no cover - the parametrization is closed above
        raise AssertionError(f"unknown mutation: {mutation}")

    with pytest.raises(ValidationError):
        make_validator("verified_knowledge_input", schemas).validate(value)


def test_strategy_input_reference_schema_has_exact_five_fields(
    repository_root: Path,
) -> None:
    common = load_schemas(repository_root)["common"]
    reference = common["$defs"]["strategyInputRef"]

    assert reference["additionalProperties"] is False
    assert set(reference["required"]) == {
        "schema_version",
        "dataset_release_id",
        "knowledge_cutoff",
        "release_manifest_schema_version",
        "manifest_hash",
    }
    assert set(reference["properties"]) == set(reference["required"])


def test_canonical_json_schema_profile_has_integer_but_no_number_branch(
    repository_root: Path,
) -> None:
    common = load_schemas(repository_root)["common"]
    branches = common["$defs"]["jsonValue"]["anyOf"]
    primitive_types = {branch.get("type") for branch in branches}

    assert "integer" in primitive_types
    assert "number" not in primitive_types


def test_manifest_schema_and_model_share_the_same_run_modes(repository_root: Path) -> None:
    manifest = load_schemas(repository_root)["strategy_run_manifest"]

    assert set(manifest["properties"]["run_mode"]["enum"]) == {mode.value for mode in RunMode}


def test_rule_status_schema_enums_follow_the_authoritative_model(repository_root: Path) -> None:
    schemas = load_schemas(repository_root)
    expected = {status.value for status in RuleStatus}

    assert set(schemas["strategy_run_manifest"]["properties"]["rule_status"]["enum"]) == expected
    assert set(schemas["decision_record"]["properties"]["rule_status"]["enum"]) == expected


def test_schemas_fail_closed_for_rule_maturity_and_full_commit_ids(
    repository_root: Path,
    strategy_run_manifest: StrategyRunManifest,
    decision_record: DecisionRecord,
) -> None:
    schemas = load_schemas(repository_root)
    manifest_validator = make_validator("strategy_run_manifest", schemas)
    decision_validator = make_validator("decision_record", schemas)

    manifest = deepcopy(strategy_run_manifest.to_json_value())
    manifest["run_mode"] = "paper"
    with pytest.raises(ValidationError):
        manifest_validator.validate(manifest)

    manifest = deepcopy(strategy_run_manifest.to_json_value())
    manifest["code_commit"] = "a" * 39
    with pytest.raises(ValidationError):
        manifest_validator.validate(manifest)

    decision = deepcopy(decision_record.to_json_value())
    decision["approver"] = "human_approver_001"
    with pytest.raises(ValidationError):
        decision_validator.validate(decision)

    decision = deepcopy(decision_record.to_json_value())
    decision["target_weight"] = "0.01"
    with pytest.raises(ValidationError):
        decision_validator.validate(decision)
