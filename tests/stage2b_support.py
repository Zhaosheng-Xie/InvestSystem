"""Executable adapters for the checked-in Stage 2B synthetic vectors.

The adapter deliberately contains no Gate or decision rules.  It materializes
the rich JSON vectors into the public industrial-event domain API, binds the
complete semantic payload into provider-neutral synthetic facts, and loads the
real checked-in rule bundle through the approval registry.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from invest_system.canonical import JsonValue, canonical_sha256, to_json_value
from invest_system.domain.replay import ReplayEnvelope
from invest_system.domain.rule_approval import (
    ApprovedRuleCapability,
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleBundleDocument,
    rule_approval_record_from_json_value,
    rule_bundle_document_from_json_value,
)
from invest_system.domain.strategy_input import SyntheticValidationInput
from invest_system.domain.synthetic_fixture import (
    ApprovedSyntheticFixtureCapability,
    FailureInjectionFixtureRegistration,
    SyntheticFixtureRegistration,
    SyntheticFixtureRegistry,
)
from invest_system.models import (
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
    VerifiedFact,
    VerifiedKnowledgeInput,
)
from invest_system.strategies.industrial_event import (
    CASE_MATERIAL_HASH_PREDICATE,
    COMPLETE_CASE_PAYLOAD_PREDICATE,
    CommercialEventInput,
    ContractExpectationTerms,
    EvidenceChain,
    EvidenceSupport,
    ExpectationInput,
    IndustrialEventCase,
    IndustrialEventDecision,
    MinimumObligationKind,
    PriorExpectationSnapshot,
    ProfitBridgeInput,
    ValuationInput,
)

JsonObject = dict[str, Any]

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
STAGE2B_FIXTURE_ROOT = REPOSITORY_ROOT / "tests" / "fixtures" / "stage2b"
STAGE2B_BASE_PATH = STAGE2B_FIXTURE_ROOT / "normal" / "synthetic-order-contract-base.v0.1.0.json"
STAGE2B_GOLDEN_PATH = STAGE2B_FIXTURE_ROOT / "normal" / "strategy-golden-cases.v0.1.0.json"
STAGE2B_BOUNDARY_PATH = STAGE2B_FIXTURE_ROOT / "normal" / "strategy-boundary-cases.v0.1.0.json"
STAGE2B_BLOCKED_PATH = (
    STAGE2B_FIXTURE_ROOT / "failure-injection" / "admission-blocked-cases.v0.1.0.json"
)
STAGE2B_REPLAY_PATH = STAGE2B_FIXTURE_ROOT / "replay" / "replay-hash-relations.v0.1.0.json"
STAGE2B_REGISTRY_PATH = STAGE2B_FIXTURE_ROOT / "synthetic-fixture-registry.v0.1.0.json"

_RULE_ARTIFACT_ROOT = REPOSITORY_ROOT / "产业卡点及事件驱动系统" / "03_规则与规格" / "机器制品"
_RULE_BUNDLE_PATH = (
    _RULE_ARTIFACT_ROOT / "industrial_event_minimum_order_contract_slice_v0.1.0.rule-bundle.json"
)
_RULE_APPROVAL_PATH = (
    _RULE_ARTIFACT_ROOT / "industrial_event_minimum_order_contract_slice_v0.1.0.approval.json"
)

_SEMANTIC_SOURCE_KEYS = (
    "clock",
    "commercial_event",
    "evidence_chains",
    "expectation_snapshot",
    "profit_bridge_input",
    "valuation_input",
)


@dataclass(frozen=True, slots=True)
class ApprovedStage2BArtifacts:
    """The exact executable document and registry-issued capability."""

    document: RuleBundleDocument
    approval: RuleApprovalRecord
    capability: ApprovedRuleCapability
    bundle_json: JsonObject
    approval_json: JsonObject


@dataclass(frozen=True, slots=True)
class MaterializedStage2BCase:
    """One independent vector projection and its run-level replay inputs."""

    vector: JsonObject
    source_document: JsonObject
    semantic_payload: JsonObject
    complete_payload: JsonObject
    case: IndustrialEventCase
    manifest: StrategyRunManifest
    primary_payload_fact_id: str
    material_hash_fact_id: str
    referenced_fact_ids: tuple[str, ...]
    referenced_evidence_ids: tuple[str, ...]


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_float(value: str) -> None:
    raise ValueError(f"JSON floating-point values are forbidden: {value}")


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constants are forbidden: {value}")


def load_json_object(path: Path) -> JsonObject:
    """Load one strict object, rejecting duplicates, floats, and NaN spellings."""

    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_float=_reject_float,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one JSON object")
    return cast(JsonObject, value)


def canonical_lock_path(json_path: Path) -> Path:
    return json_path.with_suffix(".canonical.sha256")


def verify_canonical_lock(json_path: Path) -> str:
    """Return the verified fixture digest or fail on any semantic drift."""

    value = load_json_object(json_path)
    actual = canonical_sha256(value)
    expected = canonical_lock_path(json_path).read_text(encoding="ascii").strip()
    if actual != expected:
        raise AssertionError(
            f"canonical lock mismatch for {json_path.name}: expected {expected}, got {actual}"
        )
    return actual


def load_approved_stage2b_artifacts() -> ApprovedStage2BArtifacts:
    """Resolve authority from the real immutable bundle and approval record."""

    bundle_json = load_json_object(_RULE_BUNDLE_PATH)
    approval_json = load_json_object(_RULE_APPROVAL_PATH)
    document = rule_bundle_document_from_json_value(bundle_json)
    approval = rule_approval_record_from_json_value(approval_json)
    capability = RuleApprovalRegistry((approval,)).require(document)
    return ApprovedStage2BArtifacts(
        document=document,
        approval=approval,
        capability=capability,
        bundle_json=bundle_json,
        approval_json=approval_json,
    )


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str):
        raise TypeError("UTC timestamp must be a string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _hash_from(value: Mapping[str, Any]) -> HashDigest:
    return HashDigest(algorithm=cast(str, value["algorithm"]), value=cast(str, value["value"]))


def _object(value: Any, *, field_name: str) -> JsonObject:
    if not isinstance(value, dict):
        raise TypeError(f"{field_name} must be an object")
    return cast(JsonObject, value)


def _objects(value: Any, *, field_name: str) -> tuple[JsonObject, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise TypeError(f"{field_name} must be a list of objects")
    return tuple(cast(JsonObject, item) for item in value)


def _strings(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise TypeError(f"{field_name} must be a list of strings")
    return tuple(cast(str, item) for item in value)


def _decimal_text(value: Any, *, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a decimal string")
    Decimal(value)
    return value


def _optional_decimal_item(
    value: Any,
    *,
    value_key: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    item = _object(value, field_name=field_name)
    return _decimal_text(item[value_key], field_name=f"{field_name}.{value_key}")


def _pointer_tokens(pointer: str) -> tuple[str, ...]:
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("JSON pointer must begin with /")
    return tuple(token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/"))


def replace_json_pointer(document: JsonObject, pointer: str, value: Any) -> None:
    """Apply the fixtures' deliberately narrow, existing-path replace operation."""

    tokens = _pointer_tokens(pointer)
    if not tokens:
        raise ValueError("root replacement is not supported")
    cursor: Any = document
    for token in tokens[:-1]:
        if isinstance(cursor, list):
            cursor = cursor[int(token)]
        elif isinstance(cursor, dict):
            if token not in cursor:
                raise KeyError(pointer)
            cursor = cursor[token]
        else:
            raise KeyError(pointer)
    final = tokens[-1]
    if isinstance(cursor, list):
        index = int(final)
        if index >= len(cursor):
            raise KeyError(pointer)
        cursor[index] = copy.deepcopy(value)
    elif isinstance(cursor, dict):
        if final not in cursor:
            raise KeyError(pointer)
        cursor[final] = copy.deepcopy(value)
    else:
        raise KeyError(pointer)


def apply_mutations(document: JsonObject, mutations: Sequence[Mapping[str, Any]]) -> JsonObject:
    result = copy.deepcopy(document)
    for mutation in mutations:
        if set(mutation) != {"op", "path", "value"} or mutation["op"] != "replace":
            raise ValueError("Stage 2B vectors permit only exact existing-path replace mutations")
        replace_json_pointer(result, cast(str, mutation["path"]), mutation["value"])
    return result


def _case_slug(case_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", case_id.casefold()).strip("_")
    if not slug:
        raise ValueError("case_id cannot produce an empty synthetic identity")
    return slug


def _materialized_identity(vector: JsonObject) -> JsonObject:
    explicit = vector.get("materialized_identity")
    if explicit is not None:
        return copy.deepcopy(_object(explicit, field_name="materialized_identity"))
    slug = _case_slug(cast(str, vector["case_id"]))
    return {
        "dataset_release_id": f"synthetic_release_stage2b_{slug}",
        "fixture_id": f"synthetic_fixture_stage2b_{slug}",
        "input_id": f"synthetic_input_stage2b_{slug}",
    }


def _materialize_source(
    base: JsonObject,
    vector: JsonObject,
    *,
    additional_mutations: Sequence[Mapping[str, Any]] = (),
) -> JsonObject:
    mutations = tuple(_objects(vector.get("mutations", []), field_name="mutations"))
    source = apply_mutations(base, (*mutations, *additional_mutations))
    identity = _materialized_identity(vector)
    fixture_identity = _object(source["fixture_identity"], field_name="fixture_identity")
    fixture_identity.update(identity)

    slug = _case_slug(cast(str, vector["case_id"]))
    run_identity = _object(source["run_identity"], field_name="run_identity")
    audit_ids = _object(run_identity["audit_only_ids"], field_name="audit_only_ids")
    audit_ids.update(
        {
            "artifact_fetch_observation_id": f"synthetic_fetch_stage2b_{slug}",
            "decision_id": f"synthetic_decision_stage2b_{slug}",
            "release_admission_observation_id": f"synthetic_admission_stage2b_{slug}",
            "release_status_observation_id": f"synthetic_status_stage2b_{slug}",
            "run_id": f"synthetic_run_stage2b_{slug}",
        }
    )
    return source


def _collect_string_references(value: Any, *, singular: str, plural: set[str]) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key == singular and isinstance(item, str):
                result.add(item)
            elif key in plural and isinstance(item, list):
                result.update(member for member in item if isinstance(member, str))
            else:
                result.update(_collect_string_references(item, singular=singular, plural=plural))
    elif isinstance(value, list):
        for item in value:
            result.update(_collect_string_references(item, singular=singular, plural=plural))
    return result


def referenced_fact_ids(source: JsonObject) -> tuple[str, ...]:
    return tuple(
        sorted(
            _collect_string_references(
                {key: source[key] for key in _SEMANTIC_SOURCE_KEYS},
                singular="fact_id",
                plural={"fact_ids", "source_fact_ids"},
            )
        )
    )


def referenced_evidence_ids(source: JsonObject) -> tuple[str, ...]:
    return tuple(
        sorted(
            _collect_string_references(
                {key: source[key] for key in _SEMANTIC_SOURCE_KEYS},
                singular="evidence_id",
                plural={"evidence_ids"},
            )
        )
    )


def _build_evidence_chains(source: JsonObject) -> tuple[EvidenceChain, ...]:
    chains: list[EvidenceChain] = []
    for raw in _objects(source["evidence_chains"], field_name="evidence_chains"):
        supports = tuple(
            EvidenceSupport(value) for value in _strings(raw["supports"], field_name="supports")
        )
        chains.append(
            EvidenceChain(
                chain_id=cast(str, raw["evidence_chain_id"]),
                source_document_id=cast(str, raw["source_document_id"]),
                publisher_id=cast(str, raw["publisher_responsibility_id"]),
                acquisition_chain_id=cast(str, raw["acquisition_chain_id"]),
                content_hash=_hash_from(
                    _object(raw["content_hash"], field_name="evidence_chain.content_hash")
                ),
                evidence_ids=_strings(raw["evidence_ids"], field_name="evidence_ids"),
                fact_ids=_strings(raw["fact_ids"], field_name="fact_ids"),
                authoritative_original=cast(bool, raw["authoritative_original"]),
                supports=supports,
                derivative_of_another_chain=(raw["derived_from_source_document_id"] is not None),
            )
        )
    return tuple(chains)


def _build_commercial_event(
    source: JsonObject,
    chains: tuple[EvidenceChain, ...],
) -> CommercialEventInput:
    raw = _object(source["commercial_event"], field_name="commercial_event")
    clock = _object(source["clock"], field_name="clock")
    ownership_ratio = raw["seller_to_listed_company_ownership_ratio"]
    ownership_verified = (
        None
        if ownership_ratio is None
        else Decimal(_decimal_text(ownership_ratio, field_name="ownership_ratio")) > 0
    )
    fact_ids = tuple(sorted({fact_id for chain in chains for fact_id in chain.fact_ids}))
    minimum_kind: MinimumObligationKind | None
    if raw["binding_minimum_obligation"] is not True:
        minimum_kind = None
    elif raw["binding_minimum_contract_amount"] is not None:
        minimum_kind = MinimumObligationKind.AMOUNT
    elif raw["binding_minimum_quantity"] is not None:
        minimum_kind = MinimumObligationKind.QUANTITY
    else:
        minimum_kind = MinimumObligationKind.NON_CANCELLABLE_OBLIGATION
    return CommercialEventInput(
        strong_commercial_clue=bool(chains),
        authorized_public_evidence=True if chains else None,
        ownership_path_verified=ownership_verified,
        contract_signed_or_formally_ordered=cast(bool | None, raw["contract_signed"]),
        contract_effective=cast(bool | None, raw["contract_effective"]),
        material_conditions_satisfied=cast(
            bool | None, raw["material_conditions_precedent_satisfied"]
        ),
        binding_minimum_obligation=cast(bool | None, raw["binding_minimum_obligation"]),
        minimum_obligation_kind=minimum_kind,
        cancellation_can_zero_minimum=cast(
            bool | None, raw["unilateral_cancellation_can_zero_minimum"]
        ),
        return_or_acceptance_can_zero_minimum=cast(
            bool | None, raw["return_or_acceptance_can_zero_minimum"]
        ),
        e4_first_public_at=parse_utc(cast(str, clock["contract_source_published_at"])),
        evidence_chains=chains,
        supporting_fact_ids=fact_ids,
    )


def _source_fact_ids(value: Any) -> tuple[str, ...]:
    return tuple(
        sorted(
            _collect_string_references(
                value,
                singular="__unused_fact_id__",
                plural={"source_fact_ids"},
            )
        )
    )


def _build_profit_bridge(source: JsonObject) -> ProfitBridgeInput | None:
    value = source["profit_bridge_input"]
    if value is None:
        return None
    raw = _object(value, field_name="profit_bridge_input")
    revenue = raw["ntm_recognizable_revenue"]
    contract = _object(source["commercial_event"], field_name="commercial_event")
    currency = (
        cast(str, _object(revenue, field_name="ntm_recognizable_revenue")["currency"])
        if revenue is not None
        else cast(str, contract["contract_currency"])
    )
    currencies = {
        cast(str, item["currency"])
        for item in (
            _object(member, field_name="profit amount")
            for member in raw.values()
            if isinstance(member, dict) and "currency" in member
        )
    }
    return ProfitBridgeInput(
        currency=currency,
        ntm_recognizable_revenue=_optional_decimal_item(
            revenue,
            value_key="amount",
            field_name="ntm_recognizable_revenue",
        ),
        incremental_gross_margin_rate=_optional_decimal_item(
            raw["incremental_gross_margin_rate"],
            value_key="value",
            field_name="incremental_gross_margin_rate",
        ),
        incremental_operating_expense=_optional_decimal_item(
            raw["incremental_operating_expense"],
            value_key="amount",
            field_name="incremental_operating_expense",
        ),
        incremental_tax_and_surcharges=_optional_decimal_item(
            raw["incremental_tax_and_surcharges"],
            value_key="amount",
            field_name="incremental_tax_and_surcharges",
        ),
        minority_interest_deduction=_optional_decimal_item(
            raw["minority_interest_deduction"],
            value_key="amount",
            field_name="minority_interest_deduction",
        ),
        counterfactual_ntm_normalized_parent_profit_base=_optional_decimal_item(
            raw["counterfactual_ntm_normalized_parent_profit_base"],
            value_key="amount",
            field_name="counterfactual_ntm_normalized_parent_profit_base",
        ),
        counterfactual_ntm_normalized_parent_profit_downside=_optional_decimal_item(
            raw["counterfactual_ntm_normalized_parent_profit_downside"],
            value_key="amount",
            field_name="counterfactual_ntm_normalized_parent_profit_downside",
        ),
        incremental_non_cash_items=_optional_decimal_item(
            raw["incremental_non_cash_items"],
            value_key="amount",
            field_name="incremental_non_cash_items",
        ),
        incremental_working_capital=_optional_decimal_item(
            raw["incremental_working_capital"],
            value_key="amount",
            field_name="incremental_working_capital",
        ),
        incremental_capex=_optional_decimal_item(
            raw["incremental_capex"],
            value_key="amount",
            field_name="incremental_capex",
        ),
        units_consistent=(len(currencies) == 1),
        attribution_verified=(
            True
            if contract["seller_to_listed_company_ownership_ratio"] is not None
            and contract["profit_attribution_ratio"] is not None
            else None
        ),
        counterfactual_bridge_verified=(
            raw["counterfactual_ntm_normalized_parent_profit_base"] is not None
            and raw["counterfactual_ntm_normalized_parent_profit_downside"] is not None
        ),
        supporting_fact_ids=_source_fact_ids(raw),
    )


def _current_expectation_terms(
    source: JsonObject,
    baseline_expectation: JsonObject,
) -> ContractExpectationTerms:
    commercial = _object(source["commercial_event"], field_name="commercial_event")
    minimum = commercial["binding_minimum_contract_amount"]
    amount = (
        None
        if minimum is None
        else _decimal_text(
            _object(minimum, field_name="binding_minimum_contract_amount")["amount"],
            field_name="binding_minimum_contract_amount.amount",
        )
    )
    return ContractExpectationTerms(
        counterparty_scope=cast(str, commercial["buyer_legal_entity_id"]),
        product_scope=cast(str, commercial["product_scope"]),
        currency=cast(str, commercial["contract_currency"]),
        binding_minimum_amount=amount,
        effective_period=cast(str, baseline_expectation["effective_period"]),
        material_conditions=(cast(str, baseline_expectation["material_conditions"]),),
    )


def _build_expectation(
    source: JsonObject,
    baseline_expectation: JsonObject,
) -> ExpectationInput:
    current = _current_expectation_terms(source, baseline_expectation)
    value = source["expectation_snapshot"]
    if value is None:
        return ExpectationInput(current_terms=current, prior_snapshot=None)
    raw = _object(value, field_name="expectation_snapshot")
    fact_id = cast(str, raw["fact_id"])
    prior_terms = ContractExpectationTerms(
        counterparty_scope=cast(str, raw["counterparty_scope"]),
        product_scope=cast(str, raw["product_scope"]),
        currency=cast(str, raw["currency"]),
        binding_minimum_amount=_decimal_text(
            raw["prior_expected_binding_minimum_amount"],
            field_name="prior_expected_binding_minimum_amount",
        ),
        effective_period=cast(str, raw["effective_period"]),
        material_conditions=(cast(str, raw["material_conditions"]),),
    )
    prior = PriorExpectationSnapshot(
        terms=prior_terms,
        available_at=parse_utc(cast(str, raw["available_at"])),
        explicit_public_statement=(raw["basis"] == "explicit_public_statement"),
        based_only_on_search_absence=(raw["basis"] == "search_absence"),
        material_conflict=False,
        supporting_fact_ids=(fact_id,),
    )
    return ExpectationInput(
        current_terms=current,
        prior_snapshot=prior,
        supporting_fact_ids=(fact_id,),
    )


def _build_valuation(source: JsonObject) -> ValuationInput | None:
    value = source["valuation_input"]
    if value is None:
        return None
    raw = _object(value, field_name="valuation_input")
    first_price = raw["first_executable_price"]
    first_price_object = (
        _object(first_price, field_name="first_executable_price")
        if first_price is not None
        else None
    )
    next_verification = _object(raw["next_verification"], field_name="next_verification")
    return ValuationInput(
        currency=(
            cast(str, first_price_object["currency"]) if first_price_object is not None else "CNY"
        ),
        base_business_equity_value=_optional_decimal_item(
            raw["base_business_equity_value"],
            value_key="amount",
            field_name="base_business_equity_value",
        ),
        event_finite_life_incremental_fcf_present_value=_optional_decimal_item(
            raw["event_finite_life_incremental_fcf_present_value"],
            value_key="amount",
            field_name="event_finite_life_incremental_fcf_present_value",
        ),
        downside_scenario_equity_value=_optional_decimal_item(
            raw["downside_scenario_equity_value"],
            value_key="amount",
            field_name="downside_scenario_equity_value",
        ),
        fully_diluted_shares=_optional_decimal_item(
            raw["fully_diluted_shares"],
            value_key="value",
            field_name="fully_diluted_shares",
        ),
        first_executable_price=(
            _decimal_text(first_price_object["amount"], field_name="first_executable_price.amount")
            if first_price_object is not None
            else None
        ),
        explicit_cost_rate=_optional_decimal_item(
            raw["explicit_cost_rate"],
            value_key="value",
            field_name="explicit_cost_rate",
        ),
        explicit_slippage_rate=_optional_decimal_item(
            raw["explicit_slippage_rate"],
            value_key="value",
            field_name="explicit_slippage_rate",
        ),
        first_executable_at=(
            parse_utc(cast(str, first_price_object["available_at"]))
            if first_price_object is not None
            else None
        ),
        next_verification_trading_days=cast(int | None, next_verification["trading_days"]),
        base_business_excludes_event_value=True,
        event_value_is_finite_life=True,
        supporting_fact_ids=_source_fact_ids(raw),
    )


def _evidence_by_fact(source: JsonObject) -> dict[str, tuple[str, ...]]:
    result: dict[str, set[str]] = {}
    for chain in _objects(source["evidence_chains"], field_name="evidence_chains"):
        evidence_ids = _strings(chain["evidence_ids"], field_name="evidence_ids")
        for fact_id in _strings(chain["fact_ids"], field_name="fact_ids"):
            result.setdefault(fact_id, set()).update(evidence_ids)
    expectation = source["expectation_snapshot"]
    if expectation is not None:
        raw = _object(expectation, field_name="expectation_snapshot")
        result.setdefault(cast(str, raw["fact_id"]), set()).add(cast(str, raw["evidence_id"]))
    return {fact_id: tuple(sorted(evidence_ids)) for fact_id, evidence_ids in result.items()}


def _available_at_by_fact(source: JsonObject) -> dict[str, datetime]:
    result: dict[str, datetime] = {}
    for chain in _objects(source["evidence_chains"], field_name="evidence_chains"):
        available_at = parse_utc(cast(str, chain["available_at"]))
        for fact_id in _strings(chain["fact_ids"], field_name="fact_ids"):
            result[fact_id] = available_at
    expectation = source["expectation_snapshot"]
    if expectation is not None:
        raw = _object(expectation, field_name="expectation_snapshot")
        result[cast(str, raw["fact_id"])] = parse_utc(cast(str, raw["available_at"]))
    valuation = _object(source["valuation_input"], field_name="valuation_input")
    first_price = valuation["first_executable_price"]
    if first_price is not None:
        raw_price = _object(first_price, field_name="first_executable_price")
        available_at = parse_utc(cast(str, raw_price["available_at"]))
        for fact_id in _strings(raw_price["source_fact_ids"], field_name="source_fact_ids"):
            result[fact_id] = available_at
    return result


def _complete_payload(source: JsonObject, semantic_payload: JsonObject) -> JsonObject:
    """Preserve every non-volatile business field plus the exact typed DTO."""

    return {
        "case_input_schema_version": copy.deepcopy(source["case_input_schema_version"]),
        "raw_semantic_source": {key: copy.deepcopy(source[key]) for key in _SEMANTIC_SOURCE_KEYS},
        "strategy_case_payload": copy.deepcopy(semantic_payload),
    }


def _verified_input(
    source: JsonObject,
    *,
    semantic_payload: JsonObject,
    semantic_hash: HashDigest,
    case_id: str,
) -> tuple[SyntheticValidationInput, str, str, tuple[str, ...], tuple[str, ...]]:
    clock = _object(source["clock"], field_name="clock")
    identity = _object(source["fixture_identity"], field_name="fixture_identity")
    commercial = _object(source["commercial_event"], field_name="commercial_event")
    cutoff = parse_utc(cast(str, clock["knowledge_cutoff"]))
    strategy_payload_hash = canonical_sha256(semantic_payload)
    if strategy_payload_hash != semantic_hash.value:
        raise AssertionError("public semantic payload and semantic_input_hash must agree")
    complete_payload = _complete_payload(source, semantic_payload)
    complete_payload_hash = canonical_sha256(complete_payload)
    referenced_facts = referenced_fact_ids(source)
    referenced_evidence = referenced_evidence_ids(source)
    evidence_by_fact = _evidence_by_fact(source)
    available_by_fact = _available_at_by_fact(source)
    slug = _case_slug(case_id).upper()
    primary_fact_id = f"SYN-FACT-CASE-PAYLOAD-{slug}"
    material_hash_fact_id = f"SYN-FACT-CASE-MATERIAL-HASH-{slug}"
    metadata: dict[str, JsonValue] = {
        "not_a_published_release": True,
        "not_strategy_evidence": True,
        "complete_case_payload_hash": complete_payload_hash,
        "semantic_payload_hash": strategy_payload_hash,
        "synthetic": True,
        "validation_only": True,
    }
    facts: list[VerifiedFact] = [
        VerifiedFact(
            fact_id=primary_fact_id,
            subject_id=case_id,
            predicate=COMPLETE_CASE_PAYLOAD_PREDICATE,
            value=complete_payload,
            verified_at=cutoff,
            available_at=cutoff,
            evidence_ids=referenced_evidence,
            metadata=metadata,
        ),
        VerifiedFact(
            fact_id=material_hash_fact_id,
            subject_id=case_id,
            predicate=CASE_MATERIAL_HASH_PREDICATE,
            value=semantic_hash.value,
            verified_at=cutoff,
            available_at=cutoff,
            metadata=metadata,
        ),
    ]
    for fact_id in referenced_facts:
        available_at = available_by_fact.get(fact_id, cutoff)
        facts.append(
            VerifiedFact(
                fact_id=fact_id,
                subject_id=cast(str, commercial["subject_company_id"]),
                predicate="stage2b_case_fact_binding",
                value={
                    "fact_id": fact_id,
                    "complete_case_payload_hash": complete_payload_hash,
                    "semantic_payload_hash": strategy_payload_hash,
                },
                verified_at=cutoff,
                available_at=available_at,
                evidence_ids=evidence_by_fact.get(fact_id, ()),
                event_at=parse_utc(cast(str, clock["contract_event_at"])),
                source_published_at=available_at,
                first_seen_at=available_at,
                metadata=metadata,
            )
        )
    strategy_input_ref = StrategyInputRef(
        schema_version=cast(str, identity["strategy_input_ref_schema_version"]),
        dataset_release_id=cast(str, identity["dataset_release_id"]),
        knowledge_cutoff=cutoff,
        release_manifest_schema_version=cast(str, identity["release_manifest_schema_version"]),
        manifest_hash=_hash_from(_object(identity["manifest_hash"], field_name="manifest_hash")),
    )
    verified = VerifiedKnowledgeInput(
        schema_version=VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
        input_id=cast(str, identity["input_id"]),
        strategy_input_ref=strategy_input_ref,
        facts=tuple(sorted(facts, key=lambda fact: fact.fact_id)),
    )
    synthetic = SyntheticValidationInput.from_verified_input(
        fixture_id=cast(str, identity["fixture_id"]),
        fixture_version=cast(str, identity["fixture_version"]),
        verified_knowledge_input=verified,
    )
    return (
        synthetic,
        primary_fact_id,
        material_hash_fact_id,
        referenced_facts,
        referenced_evidence,
    )


def _provisional_strategy_input(source: JsonObject, *, case_id: str) -> SyntheticValidationInput:
    """Make the provider wrapper needed for the first, non-evaluated DTO pass."""

    clock = _object(source["clock"], field_name="clock")
    identity = _object(source["fixture_identity"], field_name="fixture_identity")
    cutoff = parse_utc(cast(str, clock["knowledge_cutoff"]))
    provenance = {
        "not_a_published_release": True,
        "not_strategy_evidence": True,
        "synthetic": True,
        "validation_only": True,
    }
    provisional_fact = VerifiedFact(
        fact_id=f"SYN-FACT-PROVISIONAL-{_case_slug(case_id).upper()}",
        subject_id=case_id,
        predicate="stage2b_provisional_case_materialization",
        value={"provisional": True},
        verified_at=cutoff,
        available_at=cutoff,
        metadata=provenance,
    )
    reference = StrategyInputRef(
        schema_version=cast(str, identity["strategy_input_ref_schema_version"]),
        dataset_release_id=cast(str, identity["dataset_release_id"]),
        knowledge_cutoff=cutoff,
        release_manifest_schema_version=cast(str, identity["release_manifest_schema_version"]),
        manifest_hash=_hash_from(_object(identity["manifest_hash"], field_name="manifest_hash")),
    )
    verified = VerifiedKnowledgeInput(
        schema_version=VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
        input_id=cast(str, identity["input_id"]),
        strategy_input_ref=reference,
        facts=(provisional_fact,),
    )
    return SyntheticValidationInput.from_verified_input(
        fixture_id=cast(str, identity["fixture_id"]),
        fixture_version=cast(str, identity["fixture_version"]),
        verified_knowledge_input=verified,
    )


def _manifest(
    source: JsonObject,
    case: IndustrialEventCase,
    artifacts: ApprovedStage2BArtifacts,
) -> StrategyRunManifest:
    raw = _object(source["run_identity"], field_name="run_identity")
    audit = _object(raw["audit_only_ids"], field_name="audit_only_ids")
    strategy_input = case.strategy_input
    decision_at = parse_utc(cast(str, _object(source["clock"], field_name="clock")["decision_at"]))
    return StrategyRunManifest(
        strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        run_id=cast(str, audit["run_id"]),
        created_at=decision_at,
        strategy_id=cast(str, raw["strategy_id"]),
        strategy_version=cast(str, raw["strategy_version"]),
        code_commit=cast(str, raw["code_commit"]),
        rule_bundle_id=artifacts.document.bundle_id,
        rule_bundle_version=cast(str, raw["rule_bundle_version"]),
        rule_bundle_hash=artifacts.capability.bundle_hash,
        rule_status=RuleStatus(cast(str, raw["rule_status"])),
        rule_approval_id=artifacts.capability.approval_id,
        rule_approval_record_hash=artifacts.capability.approval_record_hash,
        rule_approval_scope=artifacts.capability.approval_scope.value,
        config_hash=_hash_from(_object(raw["config_hash"], field_name="config_hash")),
        strategy_input_ref=strategy_input.verified_knowledge_input.strategy_input_ref,
        input_envelope_hash=HashDigest(
            algorithm="sha256",
            value=strategy_input.canonical_sha256(),
        ),
        strategy_case_envelope_hash=HashDigest(
            algorithm="sha256",
            value=case.canonical_sha256(),
        ),
        strategy_case_input_hash=case.semantic_input_hash(),
        synthetic_fixture_id=strategy_input.fixture_id,
        synthetic_fixture_version=strategy_input.fixture_version,
        synthetic_fixture_payload_hash=strategy_input.fixture_payload_hash,
        input_path="synthetic_validation",
        synthetic=strategy_input.synthetic,
        validation_only=strategy_input.validation_only,
        not_a_published_release=strategy_input.not_a_published_release,
        not_strategy_evidence=strategy_input.not_strategy_evidence,
        authorizes_positions=strategy_input.authorizes_positions,
        authorizes_orders=strategy_input.authorizes_orders,
        artifact_consumption_receipt_hash=strategy_input.fixture_payload_hash,
        artifact_fetch_observation_id=cast(str, audit["artifact_fetch_observation_id"]),
        release_status_observation_id=cast(str, audit["release_status_observation_id"]),
        release_admission_observation_id=cast(str, audit["release_admission_observation_id"]),
        random_seed=cast(int, raw["random_seed"]),
        run_mode=RunMode(cast(str, raw["run_mode"])),
        runtime_environment_lock_hash=_hash_from(
            _object(raw["runtime_environment_lock_hash"], field_name="runtime lock hash")
        ),
    )


def materialize_stage2b_case(
    vector: JsonObject,
    *,
    additional_mutations: Sequence[Mapping[str, Any]] = (),
    artifacts: ApprovedStage2BArtifacts | None = None,
    audit_identity_overrides: Mapping[str, str] | None = None,
) -> MaterializedStage2BCase:
    """Create an independent typed input; no object is shared across cases."""

    base = load_json_object(STAGE2B_BASE_PATH)
    baseline_expectation = _object(
        base["expectation_snapshot"], field_name="baseline expectation_snapshot"
    )
    source = _materialize_source(
        base,
        copy.deepcopy(vector),
        additional_mutations=additional_mutations,
    )
    if audit_identity_overrides:
        audit_ids = _object(
            _object(source["run_identity"], field_name="run_identity")["audit_only_ids"],
            field_name="audit_only_ids",
        )
        unknown = set(audit_identity_overrides) - set(audit_ids)
        if unknown:
            raise ValueError(f"unknown audit identity override fields: {sorted(unknown)}")
        audit_ids.update(audit_identity_overrides)
    case_id = cast(str, vector["case_id"])
    chains = _build_evidence_chains(source)
    commercial_event = _build_commercial_event(source, chains)
    profit_bridge = _build_profit_bridge(source)
    expectation = _build_expectation(source, baseline_expectation)
    valuation = _build_valuation(source)
    valuation_raw = _object(source["valuation_input"], field_name="valuation_input")
    next_verification = _object(valuation_raw["next_verification"], field_name="next_verification")
    falsifiers = _strings(next_verification["falsifiers"], field_name="falsifiers")
    decision_at = parse_utc(cast(str, _object(source["clock"], field_name="clock")["decision_at"]))
    provisional_case = IndustrialEventCase(
        case_id=case_id,
        strategy_input=_provisional_strategy_input(source, case_id=case_id),
        decision_at=decision_at,
        commercial_event=commercial_event,
        profit_bridge=profit_bridge,
        expectation=expectation,
        valuation=valuation,
        falsifiers=falsifiers,
    )
    projected_payload = to_json_value(provisional_case.semantic_payload())
    if not isinstance(projected_payload, dict):
        raise TypeError("industrial-event semantic payload must project to an object")
    semantic_payload = cast(JsonObject, projected_payload)
    semantic_hash = provisional_case.semantic_input_hash()
    complete_payload = _complete_payload(source, semantic_payload)
    (
        strategy_input,
        primary_fact_id,
        material_hash_fact_id,
        fact_ids,
        evidence_ids,
    ) = _verified_input(
        source,
        semantic_payload=semantic_payload,
        semantic_hash=semantic_hash,
        case_id=case_id,
    )
    case = IndustrialEventCase(
        case_id=case_id,
        strategy_input=strategy_input,
        decision_at=decision_at,
        commercial_event=commercial_event,
        profit_bridge=profit_bridge,
        expectation=expectation,
        valuation=valuation,
        falsifiers=falsifiers,
    )
    resolved_artifacts = load_approved_stage2b_artifacts() if artifacts is None else artifacts
    return MaterializedStage2BCase(
        vector=copy.deepcopy(vector),
        source_document=source,
        semantic_payload=semantic_payload,
        complete_payload=complete_payload,
        case=case,
        manifest=_manifest(source, case, resolved_artifacts),
        primary_payload_fact_id=primary_fact_id,
        material_hash_fact_id=material_hash_fact_id,
        referenced_fact_ids=fact_ids,
        referenced_evidence_ids=evidence_ids,
    )


def replay_envelope_for_decision(
    materialized: MaterializedStage2BCase,
    decision: IndustrialEventDecision,
    artifacts: ApprovedStage2BArtifacts,
    *,
    manifest: StrategyRunManifest | None = None,
    semantic_output: Mapping[str, Any] | None = None,
    evaluated_at: datetime | None = None,
) -> ReplayEnvelope:
    """Build replay identity through the production self-excluding contract."""

    output = decision.to_json_value() if semantic_output is None else dict(semantic_output)
    return ReplayEnvelope.from_synthetic_validation(
        manifest=materialized.manifest if manifest is None else manifest,
        strategy_input=materialized.case.strategy_input,
        rule_bundle=artifacts.document,
        approval_capability=artifacts.capability,
        fixture_capability=fixture_capability_for(materialized),
        strategy_input_envelope=materialized.case,
        strategy_case_input_hash=materialized.case.semantic_input_hash(),
        evaluated_at=decision.decision_at if evaluated_at is None else evaluated_at,
        semantic_output=output,
    )


def matrix_cases(path: Path) -> tuple[JsonObject, tuple[JsonObject, ...]]:
    matrix = load_json_object(path)
    return matrix, _objects(matrix["cases"], field_name=f"{path.name}.cases")


def build_stage2b_fixture_registry(
    artifacts: ApprovedStage2BArtifacts | None = None,
) -> SyntheticFixtureRegistry:
    """Rebuild the trusted registry snapshot from all checked-in vector sources."""

    resolved_artifacts = load_approved_stage2b_artifacts() if artifacts is None else artifacts
    strategy_registrations: list[SyntheticFixtureRegistration] = []
    for matrix_path in (STAGE2B_GOLDEN_PATH, STAGE2B_BOUNDARY_PATH):
        matrix, cases = matrix_cases(matrix_path)
        rule_reference = _object(
            matrix["rule_bundle_reference"],
            field_name=f"{matrix_path.name}.rule_bundle_reference",
        )
        strategy_id = cast(str, rule_reference["strategy_id"])
        for vector in cases:
            materialized = materialize_stage2b_case(
                vector,
                artifacts=resolved_artifacts,
            )
            case_id = cast(str, vector["case_id"])
            strategy_registrations.append(
                SyntheticFixtureRegistration.from_trusted_case(
                    registration_id=f"stage2b_strategy_fixture_{_case_slug(case_id)}",
                    strategy_id=strategy_id,
                    case_id=case_id,
                    strategy_input=materialized.case.strategy_input,
                    strategy_case_envelope=materialized.case,
                    strategy_case_input_hash=materialized.case.semantic_input_hash(),
                )
            )

    failure_matrix, failure_cases = matrix_cases(STAGE2B_BLOCKED_PATH)
    fixture_version = cast(str, failure_matrix["fixture_matrix_schema_version"])
    failure_registrations: list[FailureInjectionFixtureRegistration] = []
    for vector in failure_cases:
        case_id = cast(str, vector["case_id"])
        failure_payload = _object(
            vector["failure_input"],
            field_name=f"{case_id}.failure_input",
        )
        failure_registrations.append(
            FailureInjectionFixtureRegistration.from_trusted_payload(
                registration_id=f"stage2b_failure_fixture_{_case_slug(case_id)}",
                case_id=case_id,
                fixture_version=fixture_version,
                expected_blocker_code=cast(str, vector["expected_blocker_code"]),
                failure_layer=cast(str, vector["failure_layer"]),
                failure_payload=cast(Mapping[str, JsonValue], failure_payload),
            )
        )
    return SyntheticFixtureRegistry(strategy_registrations, failure_registrations)


def load_stage2b_fixture_registry() -> SyntheticFixtureRegistry:
    """Load the exact machine artifact after verifying its canonical sidecar."""

    verify_canonical_lock(STAGE2B_REGISTRY_PATH)
    return SyntheticFixtureRegistry.from_artifact_payload(load_json_object(STAGE2B_REGISTRY_PATH))


def fixture_capability_for(
    materialized: MaterializedStage2BCase,
    registry: SyntheticFixtureRegistry | None = None,
) -> ApprovedSyntheticFixtureCapability:
    """Authorize one exact official case; dynamic input variants fail closed."""

    resolved_registry = load_stage2b_fixture_registry() if registry is None else registry
    return resolved_registry.require_strategy_case(
        strategy_id=materialized.manifest.strategy_id,
        case_id=materialized.case.case_id,
        strategy_input=materialized.case.strategy_input,
        strategy_case_envelope=materialized.case,
        strategy_case_input_hash=materialized.case.semantic_input_hash(),
    )


def find_case(cases: Iterable[JsonObject], case_id: str) -> JsonObject:
    matches = [case for case in cases if case.get("case_id") == case_id]
    if len(matches) != 1:
        raise LookupError(f"expected one Stage 2B case {case_id!r}, found {len(matches)}")
    return copy.deepcopy(matches[0])
