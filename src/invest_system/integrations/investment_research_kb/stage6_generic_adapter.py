"""Pure offline Adapter for the pinned generic KB Stage 6 provider fixture."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from typing import Any, cast

from invest_system.canonical import canonical_json_bytes, format_utc, normalize_utc
from invest_system.models import CanonicalModel, HashDigest, StrategyInputRef

from .provider_contracts_v1 import Stage6ProviderContractCatalog

ADAPTER_SCHEMA_VERSION = "0.1.0"
ADAPTER_PROFILE_ID = "stage6-generic-kb-offline-adapter-v0.1"
H00985_ID = "H00985"
ADV20_DEFINITION_ID = "adv20-cny-turnover-mean"
BETA120_DEFINITION_ID = "beta120-h00985-gtr-ols"

_CANONICAL_DECIMAL_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?$")


class Stage6GenericAdapterError(ValueError):
    """Stable fail-closed generic provider Adapter error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise Stage6GenericAdapterError(code, message)


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} must be an array")
    return cast(list[Any], value)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} must be non-empty text")
    return cast(str, value)


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} must be a non-negative integer")
    return cast(int, value)


def _boolean(value: object, *, field: str) -> bool:
    if type(value) is not bool:
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} must be a bool")
    return cast(bool, value)


def _digest(value: object, *, field: str) -> HashDigest:
    item = _object(value, field=field)
    if set(item) != {"algorithm", "value"}:
        _fail("PROVIDER_HASH_INVALID", f"{field} fields differ")
    try:
        return HashDigest(algorithm=item["algorithm"], value=item["value"])
    except (TypeError, ValueError) as exc:
        raise Stage6GenericAdapterError("PROVIDER_HASH_INVALID", field) from exc


def _utc(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    if not text.endswith("Z"):
        _fail("PROVIDER_TIME_INVALID", f"{field} must be UTC")
    try:
        parsed = datetime.fromisoformat(f"{text[:-1]}+00:00")
    except ValueError as exc:
        raise Stage6GenericAdapterError("PROVIDER_TIME_INVALID", field) from exc
    normalized = normalize_utc(parsed, field_name=field)
    if format_utc(normalized) != text:
        _fail("PROVIDER_TIME_INVALID", f"{field} is not canonical UTC")
    return normalized


def _unique_texts(value: object, *, field: str) -> tuple[str, ...]:
    values = tuple(_text(item, field=field) for item in _array(value, field=field))
    if len(values) != len(set(values)):
        _fail("PROVIDER_STRUCTURE_INVALID", f"{field} contains duplicates")
    return tuple(sorted(values))


def _release_reference(value: object) -> StrategyInputRef:
    item = _object(value, field="release_reference")
    return StrategyInputRef(
        schema_version=_text(item.get("schema_version"), field="schema_version"),
        dataset_release_id=_text(item.get("release_id"), field="release_id"),
        knowledge_cutoff=_utc(item.get("knowledge_cutoff"), field="knowledge_cutoff"),
        release_manifest_schema_version=_text(
            item.get("manifest_schema_version"), field="manifest_schema_version"
        ),
        manifest_hash=_digest(item.get("manifest_hash"), field="manifest_hash"),
    )


@dataclass(frozen=True, slots=True)
class Stage6DependencyReference(CanonicalModel):
    strategy_input_ref: StrategyInputRef
    roles: tuple[str, ...]
    direct: bool

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if not isinstance(self.roles, (list, tuple)) or not self.roles:
            raise ValueError("roles must not be empty")
        normalized = tuple(sorted(self.roles))
        if len(normalized) != len(set(normalized)) or any(
            not isinstance(role, str) or not role for role in normalized
        ):
            raise ValueError("roles must contain unique non-empty text")
        object.__setattr__(self, "roles", normalized)
        if type(self.direct) is not bool:
            raise TypeError("direct must be a bool")


@dataclass(frozen=True, slots=True)
class Stage6DependencyClosureProjection(CanonicalModel):
    schema_version: str
    provider_closure_id: str
    root_strategy_input_ref: StrategyInputRef
    dependencies: tuple[Stage6DependencyReference, ...]
    provider_declared_closure_hash: HashDigest
    projection_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported dependency projection schema version")
        if not isinstance(self.root_strategy_input_ref, StrategyInputRef):
            raise TypeError("root_strategy_input_ref must be a StrategyInputRef")
        if not isinstance(self.dependencies, (list, tuple)):
            raise TypeError("dependencies must be a sequence")
        normalized = tuple(
            sorted(self.dependencies, key=lambda item: item.strategy_input_ref.dataset_release_id)
        )
        if any(not isinstance(item, Stage6DependencyReference) for item in normalized):
            raise TypeError("dependencies contain an invalid value")
        release_ids = tuple(item.strategy_input_ref.dataset_release_id for item in normalized)
        if len(release_ids) != len(set(release_ids)):
            raise ValueError("dependencies contain duplicate Release IDs")
        if self.root_strategy_input_ref.dataset_release_id in set(release_ids):
            raise ValueError("root Release must not also be a dependency")
        if any(
            item.strategy_input_ref.knowledge_cutoff > self.root_strategy_input_ref.knowledge_cutoff
            for item in normalized
        ):
            raise ValueError("dependency cutoff must not postdate root cutoff")
        object.__setattr__(self, "dependencies", normalized)
        if not isinstance(self.provider_declared_closure_hash, HashDigest) or not isinstance(
            self.projection_hash, HashDigest
        ):
            raise TypeError("closure hashes must be HashDigest values")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.projection_hash.value != expected:
            raise ValueError("projection_hash differs")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider_closure_id": self.provider_closure_id,
            "root_strategy_input_ref": self.root_strategy_input_ref,
            "dependencies": self.dependencies,
            "provider_declared_closure_hash": self.provider_declared_closure_hash,
        }


@dataclass(frozen=True, slots=True)
class Stage6DomainProfileProjection(CanonicalModel):
    domain_id: str
    artifact_ids: tuple[str, ...]
    grain: str
    primary_keys: tuple[str, ...]
    start_inclusive: str | None
    end_inclusive: str | None
    record_count: int
    required_missing_count: int
    duplicate_key_count: int
    orphan_reference_count: int
    pit_result: str
    revision_lineage_result: str
    population_status: str
    declared_missing_items: tuple[str, ...]
    unrecoverable_items: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stage6DataProfileProjection(CanonicalModel):
    schema_version: str
    provider_profile_id: str
    strategy_input_ref: StrategyInputRef
    dependency_closure_hash: HashDigest | None
    domains: tuple[Stage6DomainProfileProjection, ...]
    redistribution_status: str
    redistribution_limitations: tuple[str, ...]
    readiness_status: str
    provider_declared_profile_hash: HashDigest
    projection_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION:
            raise ValueError("unsupported data profile projection schema version")
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.dependency_closure_hash is not None and not isinstance(
            self.dependency_closure_hash, HashDigest
        ):
            raise TypeError("dependency_closure_hash must be HashDigest or None")
        normalized = tuple(sorted(self.domains, key=lambda item: item.domain_id))
        if any(not isinstance(item, Stage6DomainProfileProjection) for item in normalized):
            raise TypeError("domains contain an invalid value")
        ids = tuple(item.domain_id for item in normalized)
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("domains must contain unique values")
        object.__setattr__(self, "domains", normalized)
        if not isinstance(self.provider_declared_profile_hash, HashDigest) or not isinstance(
            self.projection_hash, HashDigest
        ):
            raise TypeError("profile hashes must be HashDigest values")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.projection_hash.value != expected:
            raise ValueError("projection_hash differs")

    def identity_payload(self) -> dict[str, Any]:
        return {
            key: value for key, value in self.to_json_value().items() if key != "projection_hash"
        }


@dataclass(frozen=True, slots=True)
class Stage6BenchmarkSelection(CanonicalModel):
    benchmark_id: str
    provider_id: str
    provider_code: str
    return_type: str
    currency: str
    identity_hash: HashDigest
    redistribution_status: str
    selection_status: str
    reason_codes: tuple[str, ...]
    fallback_used: bool = False


@dataclass(frozen=True, slots=True)
class Stage6FactorAcceptance(CanonicalModel):
    factor_definition_id: str
    definition_hash: HashDigest
    observation_id: str
    as_of_session: str
    completeness: str
    value_decimal: str | None
    basis_record_count: int
    basis_records_hash: HashDigest
    acceptance_status: str
    recomputation_status: str
    reason_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Stage6OfflineAdapterResult(CanonicalModel):
    schema_version: str
    adapter_profile_id: str
    strategy_input_ref: StrategyInputRef
    dependency_closure: Stage6DependencyClosureProjection
    data_profile: Stage6DataProfileProjection
    benchmark_selection: Stage6BenchmarkSelection
    adv20: Stage6FactorAcceptance
    beta120: Stage6FactorAcceptance
    synthetic_fixture_only: bool
    validation_only: bool
    authority_eligible: bool
    network_accessed: bool
    real_release_consumed: bool
    result_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != ADAPTER_SCHEMA_VERSION or self.adapter_profile_id != (
            ADAPTER_PROFILE_ID
        ):
            raise ValueError("offline Adapter identity differs")
        if self.dependency_closure.root_strategy_input_ref != self.strategy_input_ref or (
            self.data_profile.strategy_input_ref != self.strategy_input_ref
        ):
            raise ValueError("offline Adapter root identity differs")
        if not self.synthetic_fixture_only or not self.validation_only:
            raise ValueError("offline Adapter result must be synthetic validation only")
        if self.authority_eligible or self.network_accessed or self.real_release_consumed:
            raise ValueError("offline Adapter result must have zero runtime authority")
        if not isinstance(self.result_hash, HashDigest):
            raise TypeError("result_hash must be a HashDigest")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.result_hash.value != expected:
            raise ValueError("result_hash differs")

    def identity_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_json_value().items() if key != "result_hash"}


def _project_closure(value: dict[str, Any]) -> Stage6DependencyClosureProjection:
    root = _release_reference(value.get("root_release"))
    dependencies: list[Stage6DependencyReference] = []
    for raw in _array(value.get("dependencies"), field="dependencies"):
        item = _object(raw, field="dependency")
        dependencies.append(
            Stage6DependencyReference(
                strategy_input_ref=_release_reference(item.get("release")),
                roles=_unique_texts(item.get("roles"), field="dependency.roles"),
                direct=_boolean(item.get("direct"), field="dependency.direct"),
            )
        )
    provider_closure_id = _text(value.get("closure_id"), field="closure_id")
    normalized_dependencies = tuple(
        sorted(dependencies, key=lambda item: item.strategy_input_ref.dataset_release_id)
    )
    provider_hash = _digest(value.get("closure_hash"), field="closure_hash")
    payload = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "provider_closure_id": provider_closure_id,
        "root_strategy_input_ref": root,
        "dependencies": normalized_dependencies,
        "provider_declared_closure_hash": provider_hash,
    }
    return Stage6DependencyClosureProjection(
        schema_version=ADAPTER_SCHEMA_VERSION,
        provider_closure_id=provider_closure_id,
        root_strategy_input_ref=root,
        dependencies=normalized_dependencies,
        provider_declared_closure_hash=provider_hash,
        projection_hash=HashDigest(
            algorithm="sha256", value=sha256(canonical_json_bytes(payload)).hexdigest()
        ),
    )


def _project_data_profile(value: dict[str, Any]) -> Stage6DataProfileProjection:
    domains: list[Stage6DomainProfileProjection] = []
    any_incomplete = False
    for raw in _array(value.get("domains"), field="domains"):
        item = _object(raw, field="domain")
        date_range = _object(item.get("date_range"), field="date_range")
        pit = _text(item.get("pit_result"), field="pit_result")
        revision = _text(item.get("revision_lineage_result"), field="revision_lineage_result")
        missing = _unique_texts(item.get("declared_missing_items"), field="declared_missing")
        unrecoverable = _unique_texts(item.get("unrecoverable_items"), field="unrecoverable_items")
        required_missing_count = _integer(
            item.get("required_missing_count"), field="required_missing_count"
        )
        duplicate_key_count = _integer(item.get("duplicate_key_count"), field="duplicate_key_count")
        orphan_reference_count = _integer(
            item.get("orphan_reference_count"), field="orphan_reference_count"
        )
        any_incomplete = (
            any_incomplete
            or pit != "passed"
            or revision
            not in {
                "passed",
                "not_applicable",
            }
            or bool(missing or unrecoverable)
            or any(
                count > 0
                for count in (
                    required_missing_count,
                    duplicate_key_count,
                    orphan_reference_count,
                )
            )
        )
        domains.append(
            Stage6DomainProfileProjection(
                domain_id=_text(item.get("domain_id"), field="domain_id"),
                artifact_ids=_unique_texts(item.get("artifact_ids"), field="artifact_ids"),
                grain=_text(item.get("grain"), field="grain"),
                primary_keys=_unique_texts(item.get("primary_keys"), field="primary_keys"),
                start_inclusive=date_range.get("start_inclusive"),
                end_inclusive=date_range.get("end_inclusive"),
                record_count=_integer(item.get("record_count"), field="record_count"),
                required_missing_count=required_missing_count,
                duplicate_key_count=duplicate_key_count,
                orphan_reference_count=orphan_reference_count,
                pit_result=pit,
                revision_lineage_result=revision,
                population_status=_text(item.get("population_status"), field="population_status"),
                declared_missing_items=missing,
                unrecoverable_items=unrecoverable,
            )
        )
    redistribution = _object(value.get("redistribution"), field="redistribution")
    redistribution_status = _text(redistribution.get("status"), field="redistribution.status")
    readiness = (
        "PARTIALLY_READY_SYNTHETIC_PROFILE"
        if any_incomplete
        else "READY_FOR_OFFLINE_CONTRACT_VALIDATION_ONLY"
    )
    closure_hash = value.get("dependency_closure_hash")
    provider_profile_id = _text(value.get("profile_id"), field="profile_id")
    strategy_input_ref = _release_reference(value.get("release"))
    projected_closure_hash = (
        None if closure_hash is None else _digest(closure_hash, field="dependency_closure_hash")
    )
    normalized_domains = tuple(sorted(domains, key=lambda item: item.domain_id))
    limitations = _unique_texts(
        redistribution.get("limitations"), field="redistribution.limitations"
    )
    provider_hash = _digest(value.get("profile_hash"), field="profile_hash")
    payload = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "provider_profile_id": provider_profile_id,
        "strategy_input_ref": strategy_input_ref,
        "dependency_closure_hash": projected_closure_hash,
        "domains": normalized_domains,
        "redistribution_status": redistribution_status,
        "redistribution_limitations": limitations,
        "readiness_status": readiness,
        "provider_declared_profile_hash": provider_hash,
    }
    return Stage6DataProfileProjection(
        schema_version=ADAPTER_SCHEMA_VERSION,
        provider_profile_id=provider_profile_id,
        strategy_input_ref=strategy_input_ref,
        dependency_closure_hash=projected_closure_hash,
        domains=normalized_domains,
        redistribution_status=redistribution_status,
        redistribution_limitations=limitations,
        readiness_status=readiness,
        provider_declared_profile_hash=provider_hash,
        projection_hash=HashDigest(
            algorithm="sha256", value=sha256(canonical_json_bytes(payload)).hexdigest()
        ),
    )


def _select_h00985(registry: dict[str, Any]) -> Stage6BenchmarkSelection:
    matches = [
        _object(value, field="benchmark_identity")
        for value in _array(registry.get("benchmark_identities"), field="benchmark_identities")
        if _object(value, field="benchmark_identity").get("benchmark_id") == H00985_ID
    ]
    if len(matches) != 1:
        _fail("H00985_IDENTITY_NOT_UNIQUE", "registry must contain exactly one H00985 identity")
    item = matches[0]
    if (
        item.get("provider_id") != "CSI"
        or item.get("provider_code") != "H00985.CSI"
        or item.get("return_type") != "gross_total_return"
        or item.get("currency") != "CNY"
    ):
        _fail("H00985_IDENTITY_MISMATCH", "H00985 provider identity differs")
    redistribution = _object(item.get("redistribution"), field="H00985.redistribution")
    status = _text(redistribution.get("status"), field="redistribution.status")
    reasons = () if status == "allowed" else ("H00985_REDISTRIBUTION_PERMISSION_NOT_PROVEN",)
    return Stage6BenchmarkSelection(
        benchmark_id=H00985_ID,
        provider_id="CSI",
        provider_code="H00985.CSI",
        return_type="gross_total_return",
        currency="CNY",
        identity_hash=_digest(item.get("identity_hash"), field="identity_hash"),
        redistribution_status=status,
        selection_status=(
            "SELECTED_FOR_OFFLINE_CONTRACT_ONLY"
            if status == "allowed"
            else "BLOCKED_PENDING_REDISTRIBUTION_PERMISSION"
        ),
        reason_codes=reasons,
    )


def _definition(registry: dict[str, Any], definition_id: str) -> dict[str, Any]:
    matches = [
        _object(value, field="factor_definition")
        for value in _array(registry.get("factor_definitions"), field="factor_definitions")
        if _object(value, field="factor_definition").get("factor_definition_id") == definition_id
    ]
    if len(matches) != 1:
        _fail("FACTOR_DEFINITION_NOT_UNIQUE", definition_id)
    return matches[0]


def _require_is_factor_definition(definition: dict[str, Any]) -> None:
    definition_id = definition.get("factor_definition_id")
    window = _object(definition.get("window"), field="window")
    calculation = _object(definition.get("calculation"), field="calculation")
    common_expected = {
        "unit": "exchange_session",
        "includes_as_of_session": False,
    }
    if any(window.get(key) != value for key, value in common_expected.items()) or (
        definition.get("raw_basis_required") is not True
    ):
        _fail("FACTOR_DEFINITION_PROFILE_MISMATCH", str(definition_id))
    if definition_id == ADV20_DEFINITION_ID:
        expected = {
            "factor_kind": "average_turnover",
            "window_count": 20,
            "estimator_id": "arithmetic_mean",
            "formula_version": "adv20.cny-turnover-mean.v1",
            "measure_id": "cny_turnover",
            "imputation_policy_id": "none_except_proven_full_day_suspension",
        }
        actual = {
            "factor_kind": definition.get("factor_kind"),
            "window_count": window.get("count"),
            **calculation,
        }
        if any(actual.get(key) != value for key, value in expected.items()) or (
            definition.get("benchmark_requirement") is not None
        ):
            _fail("ADV20_DEFINITION_PROFILE_MISMATCH", "ADV20 definition differs")
        return
    if definition_id == BETA120_DEFINITION_ID:
        benchmark = _object(definition.get("benchmark_requirement"), field="benchmark")
        expected = {
            "factor_kind": "market_beta",
            "window_count": 120,
            "estimator_id": "ols_slope_with_intercept",
            "formula_version": "beta120.ols-with-intercept.v1",
            "measure_id": "pit_one_session_total_return",
            "imputation_policy_id": "none_except_proven_full_day_suspension",
        }
        actual = {
            "factor_kind": definition.get("factor_kind"),
            "window_count": window.get("count"),
            **calculation,
        }
        if any(actual.get(key) != value for key, value in expected.items()) or (
            benchmark.get("benchmark_id") != H00985_ID
            or benchmark.get("return_type") != "gross_total_return"
        ):
            _fail("BETA120_DEFINITION_PROFILE_MISMATCH", "Beta120 definition differs")
        return
    _fail("FACTOR_DEFINITION_NOT_SUPPORTED", str(definition_id))


def _factor_acceptance(
    *,
    definition: dict[str, Any],
    observation: dict[str, Any],
) -> Stage6FactorAcceptance:
    reference = _object(observation.get("factor_definition"), field="factor_definition_ref")
    definition_hash = _digest(definition.get("definition_hash"), field="definition_hash")
    if (
        reference.get("factor_definition_id") != definition.get("factor_definition_id")
        or reference.get("definition_version") != definition.get("definition_version")
        or _digest(reference.get("definition_hash"), field="definition_ref_hash") != definition_hash
    ):
        _fail("FACTOR_DEFINITION_BINDING_MISMATCH", "observation definition differs")
    window = _object(definition.get("window"), field="window")
    basis = _object(observation.get("basis"), field="basis")
    record_count = _integer(basis.get("record_count"), field="basis.record_count")
    completeness = _text(observation.get("completeness"), field="completeness")
    reasons = _unique_texts(observation.get("incomplete_reason_ids"), field="reasons")
    expected_count = _integer(window.get("count"), field="window.count")
    if completeness == "complete" and (record_count != expected_count or reasons):
        _fail("FACTOR_COMPLETENESS_MISMATCH", "complete factor has an incomplete basis")
    if completeness == "incomplete" and (record_count >= expected_count or not reasons):
        _fail("FACTOR_COMPLETENESS_MISMATCH", "incomplete factor reason/count differs")
    observed_at = _utc(observation.get("observed_at"), field="observed_at")
    available_at = _utc(observation.get("available_at"), field="available_at")
    cutoff = _utc(observation.get("knowledge_cutoff"), field="knowledge_cutoff")
    latest_basis = _utc(basis.get("latest_basis_available_at"), field="latest_basis_available_at")
    if not (observed_at <= available_at <= cutoff) or latest_basis > available_at:
        _fail("FACTOR_PIT_ORDER_INVALID", "factor availability order differs")
    return Stage6FactorAcceptance(
        factor_definition_id=_text(
            definition.get("factor_definition_id"), field="factor_definition_id"
        ),
        definition_hash=definition_hash,
        observation_id=_text(
            observation.get("factor_observation_id"), field="factor_observation_id"
        ),
        as_of_session=_text(observation.get("as_of_session"), field="as_of_session"),
        completeness=completeness,
        value_decimal=observation.get("value_decimal"),
        basis_record_count=record_count,
        basis_records_hash=_digest(basis.get("records_hash"), field="basis.records_hash"),
        acceptance_status=(
            "DEFINITION_ACCEPTED_OBSERVATION_COMPLETE_HASH_BASIS_ONLY"
            if completeness == "complete"
            else "DEFINITION_ACCEPTED_OBSERVATION_INCOMPLETE"
        ),
        recomputation_status="BLOCKED_RAW_BASIS_RECORDS_NOT_PRESENT_IN_FIXTURE",
        reason_codes=(reasons if reasons else ("RAW_BASIS_RECORDS_NOT_PRESENT_IN_FIXTURE",)),
    )


def adapt_official_stage6_provider_fixture(
    catalog: Stage6ProviderContractCatalog,
) -> Stage6OfflineAdapterResult:
    """Validate and project only the snapshot's official synthetic fixture."""

    if not isinstance(catalog, Stage6ProviderContractCatalog):
        raise TypeError("catalog must be a Stage6ProviderContractCatalog")
    fixture = catalog.synthetic_fixture
    examples = _object(fixture.get("examples"), field="examples")

    def one(path: str) -> dict[str, Any]:
        values = _array(examples.get(path), field=path)
        if len(values) != 1:
            _fail("FIXTURE_CARDINALITY_MISMATCH", path)
        return _object(values[0], field=path)

    release = one("drafts/release-reference.v1.schema.json")
    closure = _project_closure(one("drafts/aggregate-release-dependency-closure.v1.schema.json"))
    profile = _project_data_profile(one("drafts/release-data-profile.v1.schema.json"))
    strategy_input_ref = _release_reference(release)
    if closure.root_strategy_input_ref != strategy_input_ref or (
        profile.strategy_input_ref != strategy_input_ref
    ):
        _fail("ROOT_RELEASE_IDENTITY_MISMATCH", "fixture root identities differ")
    if profile.dependency_closure_hash != closure.provider_declared_closure_hash:
        _fail("CLOSURE_PROFILE_BINDING_MISMATCH", "profile closure hash differs")

    registry = catalog.registry_document
    benchmark = _select_h00985(registry)
    definitions = {
        ADV20_DEFINITION_ID: _definition(registry, ADV20_DEFINITION_ID),
        BETA120_DEFINITION_ID: _definition(registry, BETA120_DEFINITION_ID),
    }
    for definition in definitions.values():
        _require_is_factor_definition(definition)
    observations = {
        _text(
            value.get("factor_definition", {}).get("factor_definition_id"), field="factor id"
        ): _object(value, field="factor observation")
        for value in _array(
            examples.get("drafts/factor-observation.v1.schema.json"),
            field="factor observations",
        )
    }
    if set(observations) != set(definitions):
        _fail("FACTOR_OBSERVATION_INVENTORY_MISMATCH", "factor observations differ")
    adv20 = _factor_acceptance(
        definition=definitions[ADV20_DEFINITION_ID],
        observation=observations[ADV20_DEFINITION_ID],
    )
    beta120 = _factor_acceptance(
        definition=definitions[BETA120_DEFINITION_ID],
        observation=observations[BETA120_DEFINITION_ID],
    )
    payload = {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "adapter_profile_id": ADAPTER_PROFILE_ID,
        "strategy_input_ref": strategy_input_ref,
        "dependency_closure": closure,
        "data_profile": profile,
        "benchmark_selection": benchmark,
        "adv20": adv20,
        "beta120": beta120,
        "synthetic_fixture_only": True,
        "validation_only": True,
        "authority_eligible": False,
        "network_accessed": False,
        "real_release_consumed": False,
    }
    return Stage6OfflineAdapterResult(
        schema_version=ADAPTER_SCHEMA_VERSION,
        adapter_profile_id=ADAPTER_PROFILE_ID,
        strategy_input_ref=strategy_input_ref,
        dependency_closure=closure,
        data_profile=profile,
        benchmark_selection=benchmark,
        adv20=adv20,
        beta120=beta120,
        synthetic_fixture_only=True,
        validation_only=True,
        authority_eligible=False,
        network_accessed=False,
        real_release_consumed=False,
        result_hash=HashDigest(
            algorithm="sha256", value=sha256(canonical_json_bytes(payload)).hexdigest()
        ),
    )


def _decimal(value: str, *, field: str) -> Decimal:
    if not isinstance(value, str) or _CANONICAL_DECIMAL_RE.fullmatch(value) is None:
        _fail("NON_CANONICAL_DECIMAL", field)
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise Stage6GenericAdapterError("NON_CANONICAL_DECIMAL", field) from exc


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        _fail("NON_FINITE_RESULT", "factor result")
    if value == 0:
        return "0"
    result = format(value, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


def recompute_adv20_cny_turnover(values: list[str] | tuple[str, ...]) -> str:
    """Recompute the exact 20-session arithmetic mean without imputation."""

    if not isinstance(values, (list, tuple)) or len(values) != 20:
        _fail("ADV20_EXACT_WINDOW_REQUIRED", "exactly 20 observations are required")
    numbers = tuple(_decimal(value, field="turnover") for value in values)
    if any(value < 0 for value in numbers):
        _fail("ADV20_NEGATIVE_TURNOVER", "turnover must be non-negative")
    with localcontext() as context:
        context.prec = 50
        return _canonical_decimal(sum(numbers, Decimal(0)) / Decimal(20))


def recompute_beta120_ols_with_intercept(
    security_returns: list[str] | tuple[str, ...],
    benchmark_returns: list[str] | tuple[str, ...],
) -> str:
    """Recompute exact paired 120-session OLS slope with an intercept."""

    if not isinstance(security_returns, (list, tuple)) or not isinstance(
        benchmark_returns, (list, tuple)
    ):
        raise TypeError("returns must be ordered lists or tuples")
    if len(security_returns) != 120 or len(benchmark_returns) != 120:
        _fail("BETA120_EXACT_PAIRED_WINDOW_REQUIRED", "exactly 120 pairs are required")
    y_values = tuple(_decimal(value, field="security_return") for value in security_returns)
    x_values = tuple(_decimal(value, field="benchmark_return") for value in benchmark_returns)
    with localcontext() as context:
        context.prec = 50
        count = Decimal(120)
        x_mean = sum(x_values, Decimal(0)) / count
        y_mean = sum(y_values, Decimal(0)) / count
        variance = sum(((value - x_mean) ** 2 for value in x_values), Decimal(0))
        if variance == 0:
            _fail("BETA120_BENCHMARK_ZERO_VARIANCE", "benchmark variance must be non-zero")
        covariance = sum(
            (
                (x_value - x_mean) * (y_value - y_mean)
                for x_value, y_value in zip(x_values, y_values, strict=True)
            ),
            Decimal(0),
        )
        return _canonical_decimal(covariance / variance)
