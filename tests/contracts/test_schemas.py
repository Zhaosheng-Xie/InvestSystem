from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing import Registry, Resource

from invest_system import (
    DecisionRecord,
    DecisionState,
    GateResult,
    HashDigest,
    PositionState,
    ReplayEnvelope,
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
    SyntheticValidationInput,
    VerifiedKnowledgeInput,
)
from invest_system.domain.synthetic_fixture import (
    SyntheticFixtureRegistration,
    SyntheticFixtureRegistry,
)
from invest_system.strategies.industrial_event import (
    run_stage2b_research_validation,
    stage4_rule_inventory_from_json_value,
)
from stage2b_support import (
    STAGE2B_GOLDEN_PATH,
    fixture_capability_for,
    load_approved_stage2b_artifacts,
    materialize_stage2b_case,
    matrix_cases,
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
    "synthetic_validation_input": Path(
        "contracts/synthetic-validation-input/synthetic-validation-input.schema.json"
    ),
    "replay_envelope": Path("contracts/replay-envelope/replay-envelope.schema.json"),
    "rule_bundle": Path("contracts/rule-bundle/rule-bundle.schema.json"),
    "rule_approval_record": Path("contracts/rule-approval/rule-approval-record.schema.json"),
    "stage4_rule_inventory": Path(
        "contracts/stage4-rule-inventory/stage4-rule-inventory.schema.json"
    ),
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


def make_schema_replay(
    manifest: StrategyRunManifest,
    synthetic_input: SyntheticValidationInput,
) -> tuple[ReplayEnvelope, RuleBundleDocument, RuleApprovalRecord]:
    rule_bundle = RuleBundleDocument(
        schema_version="0.1.0-draft",
        strategy_id=manifest.strategy_id,
        bundle_id="synthetic_stage2b_replay_contract_boundary",
        bundle_version="0.1.0",
        declared_status=RuleStatus.APPROVED,
        rules={"business_semantics": False, "validation_only": True},
    )
    approval = RuleApprovalRecord(
        approval_id="synthetic_contract_approval_001",
        strategy_id=rule_bundle.strategy_id,
        bundle_id=rule_bundle.bundle_id,
        bundle_version=rule_bundle.bundle_version,
        bundle_hash=rule_bundle.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="synthetic_contract_authorization_001",
    )
    capability = RuleApprovalRegistry((approval,)).require(rule_bundle)
    case_hash = HashDigest(
        algorithm="sha256",
        value=synthetic_input.verified_knowledge_input.canonical_sha256(),
    )
    prepared_manifest = replace(
        manifest,
        rule_bundle_id=rule_bundle.bundle_id,
        rule_bundle_version=rule_bundle.bundle_version,
        rule_bundle_hash=rule_bundle.bundle_hash(),
        rule_status=RuleStatus.APPROVED,
        rule_approval_id=capability.approval_id,
        rule_approval_record_hash=capability.approval_record_hash,
        rule_approval_scope=capability.approval_scope.value,
        input_envelope_hash=HashDigest(
            algorithm="sha256",
            value=synthetic_input.canonical_sha256(),
        ),
        strategy_case_envelope_hash=HashDigest(
            algorithm="sha256",
            value=synthetic_input.canonical_sha256(),
        ),
        strategy_case_input_hash=case_hash,
        synthetic_fixture_id=synthetic_input.fixture_id,
        synthetic_fixture_version=synthetic_input.fixture_version,
        synthetic_fixture_payload_hash=synthetic_input.fixture_payload_hash,
    )
    fixture_registration = SyntheticFixtureRegistration.from_trusted_case(
        registration_id="synthetic_schema_replay_registration",
        strategy_id=prepared_manifest.strategy_id,
        case_id="synthetic_schema_replay_case",
        strategy_input=synthetic_input,
        strategy_case_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
    )
    fixture_registry = SyntheticFixtureRegistry((fixture_registration,))
    fixture_capability = fixture_registry.require_strategy_case(
        strategy_id=prepared_manifest.strategy_id,
        case_id=fixture_registration.case_id,
        strategy_input=synthetic_input,
        strategy_case_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
    )
    replay = ReplayEnvelope.from_synthetic_validation(
        manifest=prepared_manifest,
        strategy_input=synthetic_input,
        rule_bundle=rule_bundle,
        approval_capability=capability,
        fixture_capability=fixture_capability,
        strategy_input_envelope=synthetic_input,
        strategy_case_input_hash=case_hash,
        evaluated_at=prepared_manifest.created_at,
        semantic_output={"business_semantics": False, "validation_only": True},
    )
    return replay, rule_bundle, approval


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
        assert schema["$id"].startswith("https://schemas.investsystem.local/")
        assert schema["$id"].split("/")[-2] == schema["x-contract-version"]


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


def test_gate_result_schema_enforces_short_circuit_state_machine(
    repository_root: Path,
    gate_result: GateResult,
) -> None:
    schemas = load_schemas(repository_root)
    validator = make_validator("gate_result", schemas)
    skipped = deepcopy(gate_result.to_json_value())
    skipped["evaluation_state"] = "not_evaluated"
    skipped["outcome"] = None
    skipped["short_circuit_reason_code"] = "prior_gate_rejected"
    validator.validate(skipped)

    missing_reason = deepcopy(skipped)
    missing_reason["short_circuit_reason_code"] = None
    with pytest.raises(ValidationError):
        validator.validate(missing_reason)

    fabricated_outcome = deepcopy(skipped)
    fabricated_outcome["outcome"] = "ABSTAIN"
    with pytest.raises(ValidationError):
        validator.validate(fabricated_outcome)

    evaluated_with_reason = deepcopy(gate_result.to_json_value())
    evaluated_with_reason["short_circuit_reason_code"] = "not_applicable"
    with pytest.raises(ValidationError):
        validator.validate(evaluated_with_reason)


def test_stage2b0_models_serialize_to_their_draft_schemas(
    repository_root: Path,
    verified_knowledge_input: VerifiedKnowledgeInput,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    schemas = load_schemas(repository_root)
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_contract_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    replay, approved_rule_bundle, approval = make_schema_replay(
        strategy_run_manifest,
        synthetic_input,
    )
    values = {
        "synthetic_validation_input": synthetic_input.to_json_value(),
        "replay_envelope": replay.to_json_value(),
        "rule_bundle": approved_rule_bundle.to_json_value(),
        "rule_approval_record": approval.to_json_value(),
    }

    for name, value in values.items():
        make_validator(name, schemas).validate(value)


def test_real_stage2b_runner_decision_record_validates_against_contract(
    repository_root: Path,
) -> None:
    schemas = load_schemas(repository_root)
    approved = load_approved_stage2b_artifacts()
    _matrix, vectors = matrix_cases(STAGE2B_GOLDEN_PATH)
    materialized = materialize_stage2b_case(vectors[0], artifacts=approved)
    result = run_stage2b_research_validation(
        decision_id="synthetic_schema_runner_decision_001",
        manifest=materialized.manifest,
        case=materialized.case,
        rule_document=approved.document,
        approval_capability=approved.capability,
        fixture_capability=fixture_capability_for(materialized),
    )

    make_validator("decision_record", schemas).validate(result.decision_record.to_json_value())


def test_checked_in_stage2b_rule_artifacts_validate_against_contracts(
    repository_root: Path,
) -> None:
    schemas = load_schemas(repository_root)
    artifact_directory = repository_root / "产业卡点及事件驱动系统" / "03_规则与规格" / "机器制品"
    artifacts = {
        "rule_bundle": "industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json",
        "rule_approval_record": (
            "industrial_event_minimum_order_contract_slice_v0.1.0.approval.json"
        ),
    }

    for schema_name, filename in artifacts.items():
        value = json.loads((artifact_directory / filename).read_text(encoding="utf-8"))
        make_validator(schema_name, schemas).validate(value)


def test_checked_in_stage4_rule_inventory_validates_but_grants_no_authority(
    repository_root: Path,
) -> None:
    schemas = load_schemas(repository_root)
    path = (
        repository_root
        / "产业卡点及事件驱动系统"
        / "03_规则与规格"
        / "机器制品"
        / "industrial_event_stage4_p0_rule_inventory_v0.1.0-draft.json"
    )
    value = json.loads(path.read_text(encoding="utf-8"))
    make_validator("stage4_rule_inventory", schemas).validate(value)
    inventory = stage4_rule_inventory_from_json_value(value)

    assert inventory.to_json_value() == value
    assert inventory.unapproved_requirement_ids == ()
    inventory.require_complete()
    assert inventory.authorizes_backtest is False
    assert inventory.authorizes_paper is False
    assert inventory.authorizes_shadow is False
    assert inventory.authorizes_live is False
    assert inventory.authorizes_positions is False
    assert inventory.authorizes_orders is False


def test_rule_approval_scope_schema_matches_authoritative_model(
    repository_root: Path,
) -> None:
    schemas = load_schemas(repository_root)
    expected = {scope.value for scope in RuleApprovalScope}

    assert set(schemas["rule_approval_record"]["properties"]["approval_scope"]["enum"]) == expected


def test_stage2b0_schemas_fail_closed_on_provenance_and_audit_drift(
    repository_root: Path,
    verified_knowledge_input: VerifiedKnowledgeInput,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    schemas = load_schemas(repository_root)
    synthetic_input = SyntheticValidationInput.from_verified_input(
        fixture_id="synthetic_fixture_stage2b_contract_001",
        fixture_version="0.1.0-draft",
        verified_knowledge_input=verified_knowledge_input,
    )
    relabeled = synthetic_input.to_json_value()
    relabeled["authorizes_positions"] = True
    with pytest.raises(ValidationError):
        make_validator("synthetic_validation_input", schemas).validate(relabeled)

    replay_envelope, _, _ = make_schema_replay(strategy_run_manifest, synthetic_input)
    replay_value = replay_envelope.to_json_value()
    replay_value["run_id"] = "volatile_run_id"
    with pytest.raises(ValidationError):
        make_validator("replay_envelope", schemas).validate(replay_value)

    replay_value.pop("run_id")
    replay_value["semantic_output"] = {"nested": {"run_id": "volatile_run_id"}}
    with pytest.raises(ValidationError):
        make_validator("replay_envelope", schemas).validate(replay_value)


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


def test_decision_schema_enforces_stage2b_synthetic_zero_authority(
    repository_root: Path,
    decision_record: DecisionRecord,
) -> None:
    schemas = load_schemas(repository_root)
    validator = make_validator("decision_record", schemas)
    stage2b = replace(
        decision_record,
        rule_status=RuleStatus.APPROVED,
        rule_approval_id="stage2b_schema_approval",
        rule_approval_record_hash=decision_record.replay_hash,
        rule_approval_scope="stage2b_synthetic_validation",
        decision_state=DecisionState.TRADE_READY,
    ).to_json_value()
    validator.validate(stage2b)

    mutations = {
        "run_mode": "shadow",
        "synthetic": False,
        "validation_only": False,
        "authorizes_positions": True,
        "authorizes_orders": True,
        "position_state": PositionState.STARTER.value,
        "target_weight": "0.01",
        "approver": "human_approver_001",
    }
    for field_name, invalid_value in mutations.items():
        changed = deepcopy(stage2b)
        changed[field_name] = invalid_value
        with pytest.raises(ValidationError):
            validator.validate(changed)
