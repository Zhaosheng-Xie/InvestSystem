"""Trusted, exact-match authorization for Stage 2B synthetic fixtures.

A synthetic namespace is provenance, not authority.  This module separates
checked-in fixture registrations from the capability needed to execute one
exact materialized strategy case.  The registry matches complete content
identities; prefixes and directory presence never grant execution authority.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast

from invest_system.canonical import JsonValue, canonical_sha256, freeze_json, to_json_value
from invest_system.domain.strategy_input import SyntheticValidationInput
from invest_system.models import CanonicalModel, HashDigest

SYNTHETIC_FIXTURE_REGISTRATION_SCHEMA_VERSION = "0.1.0-draft"
FAILURE_INJECTION_REGISTRATION_SCHEMA_VERSION = "0.1.0-draft"
SYNTHETIC_FIXTURE_REGISTRY_SCHEMA_VERSION = "0.1.0-draft"
SYNTHETIC_FIXTURE_REGISTRY_PROFILE = "invest_system.stage2b.synthetic_fixture_registry.v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)

_HASH_KEYS = frozenset({"algorithm", "value"})
_STRATEGY_REGISTRATION_KEYS = frozenset(
    {
        "capability_scope",
        "case_id",
        "dataset_release_id",
        "fixture_id",
        "fixture_version",
        "input_envelope_hash",
        "input_id",
        "registration_id",
        "schema_version",
        "strategy_case_envelope_hash",
        "strategy_case_input_hash",
        "strategy_id",
        "verified_input_hash",
    }
)
_FAILURE_REGISTRATION_KEYS = frozenset(
    {
        "case_id",
        "dataset_release_id",
        "expected_blocker_code",
        "failure_layer",
        "failure_payload_hash",
        "fixture_id",
        "fixture_version",
        "input_id",
        "registration_id",
        "schema_version",
    }
)
_REGISTRY_ARTIFACT_KEYS = frozenset(
    {
        "failure_registration_count",
        "failure_registrations",
        "profile",
        "registry_snapshot_hash",
        "schema_version",
        "strategy_registration_count",
        "strategy_registrations",
    }
)


def _require_id(field_name: str, value: str, *, forbid_latest: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a valid 1-128 character ASCII ID")
    if forbid_latest and value.casefold() == "latest":
        raise ValueError(f"{field_name} must be exact, not 'latest'")
    return value


def _require_version(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _SEMVER_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")
    return value


def _strict_object(
    value: Any,
    *,
    keys: frozenset[str],
    field_name: str,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a JSON object")
    actual = set(value)
    if actual != keys:
        missing = sorted(keys - actual)
        extra = sorted(actual - keys)
        raise ValueError(f"{field_name} fields differ; missing={missing}, extra={extra}")
    return dict(value)


def _strict_object_array(value: Any, *, field_name: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a JSON array")
    if any(not isinstance(item, Mapping) for item in value):
        raise TypeError(f"{field_name} must contain only JSON objects")
    return cast(tuple[Mapping[str, Any], ...], tuple(value))


def _parse_hash(value: Any, *, field_name: str) -> HashDigest:
    item = _strict_object(value, keys=_HASH_KEYS, field_name=field_name)
    return HashDigest(algorithm=item["algorithm"], value=item["value"])


def _parse_count(value: Any, *, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


class SyntheticFixtureAuthorizationError(ValueError):
    """Stable fail-closed rejection from the fixture authorization boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class SyntheticFixtureCapabilityScope(StrEnum):
    """Execution scope granted by the current fixture registry."""

    STAGE2B_STRATEGY_EVALUATION = "stage2b_strategy_evaluation"


@dataclass(frozen=True, slots=True)
class SyntheticFixtureRegistration(CanonicalModel):
    """Trusted allowlist record for one complete materialized strategy case."""

    registration_id: str
    strategy_id: str
    case_id: str
    fixture_id: str
    fixture_version: str
    dataset_release_id: str
    input_id: str
    verified_input_hash: HashDigest
    input_envelope_hash: HashDigest
    strategy_case_input_hash: HashDigest
    strategy_case_envelope_hash: HashDigest
    capability_scope: SyntheticFixtureCapabilityScope = field(
        default=SyntheticFixtureCapabilityScope.STAGE2B_STRATEGY_EVALUATION,
        init=False,
    )
    schema_version: str = field(
        default=SYNTHETIC_FIXTURE_REGISTRATION_SCHEMA_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "registration_id",
            "strategy_id",
            "case_id",
            "fixture_id",
            "input_id",
        ):
            _require_id(field_name, getattr(self, field_name))
        _require_id("dataset_release_id", self.dataset_release_id, forbid_latest=True)
        _require_version("fixture_version", self.fixture_version)
        for field_name in (
            "verified_input_hash",
            "input_envelope_hash",
            "strategy_case_input_hash",
            "strategy_case_envelope_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        if not self.fixture_id.startswith("synthetic_fixture_stage2b_"):
            raise ValueError("fixture_id must use the Stage 2B synthetic fixture namespace")
        if not self.dataset_release_id.startswith("synthetic_release_"):
            raise ValueError("dataset_release_id must use the synthetic Release namespace")
        if not self.input_id.startswith("synthetic_input_"):
            raise ValueError("input_id must use the synthetic input namespace")

    @classmethod
    def from_trusted_case(
        cls,
        *,
        registration_id: str,
        strategy_id: str,
        case_id: str,
        strategy_input: SyntheticValidationInput,
        strategy_case_envelope: CanonicalModel,
        strategy_case_input_hash: HashDigest,
    ) -> SyntheticFixtureRegistration:
        """Snapshot exact identities at a trusted composition boundary."""

        if not isinstance(strategy_input, SyntheticValidationInput):
            raise TypeError("strategy_input must be a SyntheticValidationInput")
        if not isinstance(strategy_case_envelope, CanonicalModel):
            raise TypeError("strategy_case_envelope must be a CanonicalModel")
        if not isinstance(strategy_case_input_hash, HashDigest):
            raise TypeError("strategy_case_input_hash must be a HashDigest")
        verified = strategy_input.verified_knowledge_input
        return cls(
            registration_id=registration_id,
            strategy_id=strategy_id,
            case_id=case_id,
            fixture_id=strategy_input.fixture_id,
            fixture_version=strategy_input.fixture_version,
            dataset_release_id=verified.strategy_input_ref.dataset_release_id,
            input_id=verified.input_id,
            input_envelope_hash=HashDigest(
                algorithm="sha256",
                value=strategy_input.canonical_sha256(),
            ),
            verified_input_hash=strategy_input.fixture_payload_hash,
            strategy_case_envelope_hash=HashDigest(
                algorithm="sha256",
                value=strategy_case_envelope.canonical_sha256(),
            ),
            strategy_case_input_hash=strategy_case_input_hash,
        )

    def registration_hash(self) -> HashDigest:
        return HashDigest(algorithm="sha256", value=self.canonical_sha256())


@dataclass(frozen=True, slots=True)
class FailureInjectionFixtureRegistration(CanonicalModel):
    """Exact asset identity for a pre-admission failure vector.

    These records are inventory and audit allowlists only.  They can never
    issue a strategy-evaluation capability.
    """

    registration_id: str
    case_id: str
    fixture_id: str
    fixture_version: str
    dataset_release_id: str
    input_id: str
    expected_blocker_code: str
    failure_layer: str
    failure_payload_hash: HashDigest
    schema_version: str = field(
        default=FAILURE_INJECTION_REGISTRATION_SCHEMA_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "registration_id",
            "case_id",
            "fixture_id",
            "input_id",
            "expected_blocker_code",
            "failure_layer",
        ):
            _require_id(field_name, getattr(self, field_name))
        _require_id("dataset_release_id", self.dataset_release_id, forbid_latest=True)
        _require_version("fixture_version", self.fixture_version)
        if not isinstance(self.failure_payload_hash, HashDigest):
            raise TypeError("failure_payload_hash must be a HashDigest")
        if not self.fixture_id.startswith("synthetic_failure_injection_"):
            raise ValueError("failure fixture_id must use the failure-injection namespace")

    @classmethod
    def from_trusted_payload(
        cls,
        *,
        registration_id: str,
        case_id: str,
        fixture_version: str,
        expected_blocker_code: str,
        failure_layer: str,
        failure_payload: Mapping[str, JsonValue],
    ) -> FailureInjectionFixtureRegistration:
        if not isinstance(failure_payload, Mapping):
            raise TypeError("failure_payload must be a mapping")
        fixture_id = failure_payload.get("fixture_id")
        dataset_release_id = failure_payload.get("dataset_release_id")
        input_id = failure_payload.get("input_id")
        if not all(isinstance(value, str) for value in (fixture_id, dataset_release_id, input_id)):
            raise ValueError("failure payload must contain fixture, Release, and input IDs")
        return cls(
            registration_id=registration_id,
            case_id=case_id,
            fixture_id=cast(str, fixture_id),
            fixture_version=fixture_version,
            dataset_release_id=cast(str, dataset_release_id),
            input_id=cast(str, input_id),
            expected_blocker_code=expected_blocker_code,
            failure_layer=failure_layer,
            failure_payload_hash=HashDigest(
                algorithm="sha256",
                value=canonical_sha256(failure_payload),
            ),
        )


def synthetic_fixture_registration_from_json_value(
    value: Any,
) -> SyntheticFixtureRegistration:
    """Strictly parse one complete strategy fixture registration."""

    item = _strict_object(
        value,
        keys=_STRATEGY_REGISTRATION_KEYS,
        field_name="strategy fixture registration",
    )
    if item["schema_version"] != SYNTHETIC_FIXTURE_REGISTRATION_SCHEMA_VERSION:
        raise ValueError(
            "strategy fixture registration schema_version must be "
            f"{SYNTHETIC_FIXTURE_REGISTRATION_SCHEMA_VERSION!r}"
        )
    try:
        scope = SyntheticFixtureCapabilityScope(item["capability_scope"])
    except (TypeError, ValueError) as exc:
        raise ValueError("strategy fixture capability_scope is not supported") from exc
    if scope is not SyntheticFixtureCapabilityScope.STAGE2B_STRATEGY_EVALUATION:
        raise ValueError("strategy fixture capability_scope cannot grant another scope")
    return SyntheticFixtureRegistration(
        registration_id=item["registration_id"],
        strategy_id=item["strategy_id"],
        case_id=item["case_id"],
        fixture_id=item["fixture_id"],
        fixture_version=item["fixture_version"],
        dataset_release_id=item["dataset_release_id"],
        input_id=item["input_id"],
        verified_input_hash=_parse_hash(
            item["verified_input_hash"],
            field_name="verified_input_hash",
        ),
        input_envelope_hash=_parse_hash(
            item["input_envelope_hash"],
            field_name="input_envelope_hash",
        ),
        strategy_case_input_hash=_parse_hash(
            item["strategy_case_input_hash"],
            field_name="strategy_case_input_hash",
        ),
        strategy_case_envelope_hash=_parse_hash(
            item["strategy_case_envelope_hash"],
            field_name="strategy_case_envelope_hash",
        ),
    )


def failure_injection_registration_from_json_value(
    value: Any,
) -> FailureInjectionFixtureRegistration:
    """Strictly parse one inventory-only failure fixture registration."""

    item = _strict_object(
        value,
        keys=_FAILURE_REGISTRATION_KEYS,
        field_name="failure fixture registration",
    )
    if item["schema_version"] != FAILURE_INJECTION_REGISTRATION_SCHEMA_VERSION:
        raise ValueError(
            "failure fixture registration schema_version must be "
            f"{FAILURE_INJECTION_REGISTRATION_SCHEMA_VERSION!r}"
        )
    return FailureInjectionFixtureRegistration(
        registration_id=item["registration_id"],
        case_id=item["case_id"],
        fixture_id=item["fixture_id"],
        fixture_version=item["fixture_version"],
        dataset_release_id=item["dataset_release_id"],
        input_id=item["input_id"],
        expected_blocker_code=item["expected_blocker_code"],
        failure_layer=item["failure_layer"],
        failure_payload_hash=_parse_hash(
            item["failure_payload_hash"],
            field_name="failure_payload_hash",
        ),
    )


def _assert_exact_case_binding(
    binding: SyntheticFixtureRegistration | ApprovedSyntheticFixtureCapability,
    *,
    strategy_id: str,
    case_id: str,
    strategy_input: SyntheticValidationInput,
    strategy_case_envelope: CanonicalModel,
    strategy_case_input_hash: HashDigest,
) -> None:
    if not isinstance(strategy_input, SyntheticValidationInput):
        raise TypeError("strategy_input must be a SyntheticValidationInput")
    if not isinstance(strategy_case_envelope, CanonicalModel):
        raise TypeError("strategy_case_envelope must be a CanonicalModel")
    if not isinstance(strategy_case_input_hash, HashDigest):
        raise TypeError("strategy_case_input_hash must be a HashDigest")
    verified = strategy_input.verified_knowledge_input
    identity = (
        strategy_id,
        case_id,
        strategy_input.fixture_id,
        strategy_input.fixture_version,
        verified.strategy_input_ref.dataset_release_id,
        verified.input_id,
    )
    expected_identity = (
        binding.strategy_id,
        binding.case_id,
        binding.fixture_id,
        binding.fixture_version,
        binding.dataset_release_id,
        binding.input_id,
    )
    if identity != expected_identity:
        raise SyntheticFixtureAuthorizationError(
            "SYNTHETIC_FIXTURE_IDENTITY_MISMATCH",
            "strategy, case, fixture, Release, or input identity is not registered",
        )
    actual_input_envelope_hash = HashDigest(
        algorithm="sha256",
        value=strategy_input.canonical_sha256(),
    )
    if actual_input_envelope_hash != binding.input_envelope_hash:
        raise SyntheticFixtureAuthorizationError(
            "SYNTHETIC_FIXTURE_INPUT_ENVELOPE_HASH_MISMATCH",
            "complete SyntheticValidationInput content is not registered",
        )
    if strategy_input.fixture_payload_hash != binding.verified_input_hash:
        raise SyntheticFixtureAuthorizationError(
            "SYNTHETIC_FIXTURE_VERIFIED_INPUT_HASH_MISMATCH",
            "complete VerifiedKnowledgeInput content is not registered",
        )
    actual_strategy_case_envelope_hash = HashDigest(
        algorithm="sha256",
        value=strategy_case_envelope.canonical_sha256(),
    )
    if actual_strategy_case_envelope_hash != binding.strategy_case_envelope_hash:
        raise SyntheticFixtureAuthorizationError(
            "SYNTHETIC_FIXTURE_STRATEGY_CASE_ENVELOPE_HASH_MISMATCH",
            "complete IndustrialEventCase content is not registered",
        )
    if strategy_case_input_hash != binding.strategy_case_input_hash:
        raise SyntheticFixtureAuthorizationError(
            "SYNTHETIC_FIXTURE_SEMANTIC_HASH_MISMATCH",
            "strategy case semantic identity is not registered",
        )


_CAPABILITY_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedSyntheticFixtureCapability(CanonicalModel):
    """Opaque proof that a registry authorized one exact strategy case."""

    registration_id: str
    registration_hash: HashDigest
    registry_snapshot_hash: HashDigest
    strategy_id: str
    case_id: str
    fixture_id: str
    fixture_version: str
    dataset_release_id: str
    input_id: str
    verified_input_hash: HashDigest
    input_envelope_hash: HashDigest
    strategy_case_input_hash: HashDigest
    strategy_case_envelope_hash: HashDigest
    capability_scope: SyntheticFixtureCapabilityScope

    def __init__(
        self,
        *,
        _issuer: object,
        registration: SyntheticFixtureRegistration,
        registry_snapshot_hash: HashDigest,
    ) -> None:
        if _issuer is not _CAPABILITY_ISSUER:
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_CAPABILITY_ISSUER_INVALID",
                "fixture capabilities can only be issued by SyntheticFixtureRegistry",
            )
        object.__setattr__(self, "registration_id", registration.registration_id)
        object.__setattr__(self, "registration_hash", registration.registration_hash())
        object.__setattr__(self, "registry_snapshot_hash", registry_snapshot_hash)
        for field_name in (
            "strategy_id",
            "case_id",
            "fixture_id",
            "fixture_version",
            "dataset_release_id",
            "input_id",
            "verified_input_hash",
            "input_envelope_hash",
            "strategy_case_input_hash",
            "strategy_case_envelope_hash",
            "capability_scope",
        ):
            object.__setattr__(self, field_name, getattr(registration, field_name))

    def require_exact(
        self,
        *,
        strategy_id: str,
        case_id: str,
        fixture_id: str,
        fixture_version: str,
        dataset_release_id: str,
        input_id: str,
        input_envelope_hash: HashDigest,
        verified_input_hash: HashDigest,
        strategy_case_input_hash: HashDigest,
        strategy_case_envelope_hash: HashDigest,
    ) -> None:
        """Fail closed if this capability is replayed against any other bytes."""

        if self.capability_scope is not SyntheticFixtureCapabilityScope.STAGE2B_STRATEGY_EVALUATION:
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_SCOPE_INVALID",
                "fixture capability does not authorize Stage 2B strategy evaluation",
            )
        identity = (
            strategy_id,
            case_id,
            fixture_id,
            fixture_version,
            dataset_release_id,
            input_id,
        )
        expected_identity = (
            self.strategy_id,
            self.case_id,
            self.fixture_id,
            self.fixture_version,
            self.dataset_release_id,
            self.input_id,
        )
        if identity != expected_identity:
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_IDENTITY_MISMATCH",
                "strategy, case, fixture, Release, or input identity is not registered",
            )
        hash_bindings = (
            (
                input_envelope_hash,
                self.input_envelope_hash,
                "SYNTHETIC_FIXTURE_INPUT_ENVELOPE_HASH_MISMATCH",
            ),
            (
                verified_input_hash,
                self.verified_input_hash,
                "SYNTHETIC_FIXTURE_VERIFIED_INPUT_HASH_MISMATCH",
            ),
            (
                strategy_case_input_hash,
                self.strategy_case_input_hash,
                "SYNTHETIC_FIXTURE_SEMANTIC_HASH_MISMATCH",
            ),
            (
                strategy_case_envelope_hash,
                self.strategy_case_envelope_hash,
                "SYNTHETIC_FIXTURE_STRATEGY_CASE_ENVELOPE_HASH_MISMATCH",
            ),
        )
        for actual, expected, code in hash_bindings:
            if not isinstance(actual, HashDigest):
                raise TypeError("fixture identity hashes must be HashDigest values")
            if actual != expected:
                raise SyntheticFixtureAuthorizationError(
                    code,
                    "materialized synthetic fixture content is not registered",
                )


class SyntheticFixtureRegistry:
    """Immutable trusted allowlist for strategy and failure-injection fixtures."""

    __slots__ = (
        "_failure_by_identity",
        "_failure_records",
        "_strategy_by_identity",
        "_strategy_records",
        "_snapshot_hash",
    )

    _strategy_records: tuple[SyntheticFixtureRegistration, ...]
    _failure_records: tuple[FailureInjectionFixtureRegistration, ...]
    _strategy_by_identity: Mapping[tuple[str, str, str, str], SyntheticFixtureRegistration]
    _failure_by_identity: Mapping[tuple[str, str, str], FailureInjectionFixtureRegistration]
    _snapshot_hash: HashDigest

    def __init__(
        self,
        strategy_registrations: Iterable[SyntheticFixtureRegistration] = (),
        failure_registrations: Iterable[FailureInjectionFixtureRegistration] = (),
    ) -> None:
        strategies = tuple(strategy_registrations)
        failures = tuple(failure_registrations)
        if any(not isinstance(item, SyntheticFixtureRegistration) for item in strategies):
            raise TypeError(
                "strategy_registrations must contain SyntheticFixtureRegistration values"
            )
        if any(not isinstance(item, FailureInjectionFixtureRegistration) for item in failures):
            raise TypeError(
                "failure_registrations must contain FailureInjectionFixtureRegistration values"
            )
        registration_ids = [item.registration_id for item in strategies]
        registration_ids.extend(item.registration_id for item in failures)
        if len(registration_ids) != len(set(registration_ids)):
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_REGISTRATION_ID_REUSED",
                "registration_id must be globally unique",
            )
        fixture_ids = [item.fixture_id for item in strategies]
        fixture_ids.extend(item.fixture_id for item in failures)
        if len(fixture_ids) != len(set(fixture_ids)):
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_ID_REUSED",
                "each fixture_id must identify exactly one registered case",
            )

        strategy_by_identity: dict[tuple[str, str, str, str], SyntheticFixtureRegistration] = {}
        for strategy_item in strategies:
            strategy_identity = (
                strategy_item.strategy_id,
                strategy_item.case_id,
                strategy_item.fixture_id,
                strategy_item.fixture_version,
            )
            if strategy_identity in strategy_by_identity:
                raise SyntheticFixtureAuthorizationError(
                    "SYNTHETIC_FIXTURE_REGISTRY_AMBIGUOUS",
                    "one strategy fixture identity may bind exactly one content identity",
                )
            strategy_by_identity[strategy_identity] = strategy_item

        failure_by_identity: dict[tuple[str, str, str], FailureInjectionFixtureRegistration] = {}
        for failure_item in failures:
            failure_identity = (
                failure_item.case_id,
                failure_item.fixture_id,
                failure_item.fixture_version,
            )
            if failure_identity in failure_by_identity:
                raise SyntheticFixtureAuthorizationError(
                    "SYNTHETIC_FIXTURE_REGISTRY_AMBIGUOUS",
                    "one failure fixture identity may bind exactly one payload",
                )
            failure_by_identity[failure_identity] = failure_item

        self._strategy_records = tuple(sorted(strategies, key=lambda item: item.registration_id))
        self._failure_records = tuple(sorted(failures, key=lambda item: item.registration_id))
        self._strategy_by_identity = MappingProxyType(strategy_by_identity)
        self._failure_by_identity = MappingProxyType(failure_by_identity)
        self._snapshot_hash = HashDigest(
            algorithm="sha256",
            value=canonical_sha256(
                {
                    "profile": SYNTHETIC_FIXTURE_REGISTRY_PROFILE,
                    "strategy_registrations": self._strategy_records,
                    "failure_registrations": self._failure_records,
                }
            ),
        )

    @property
    def strategy_records(self) -> tuple[SyntheticFixtureRegistration, ...]:
        return self._strategy_records

    @property
    def failure_records(self) -> tuple[FailureInjectionFixtureRegistration, ...]:
        return self._failure_records

    @property
    def snapshot_hash(self) -> HashDigest:
        """Content identity that an engine must pin before trusting capabilities."""

        return self._snapshot_hash

    def to_artifact_payload(self) -> Mapping[str, JsonValue]:
        """Project the complete immutable registry into its machine artifact."""

        projected = to_json_value(
            {
                "schema_version": SYNTHETIC_FIXTURE_REGISTRY_SCHEMA_VERSION,
                "profile": SYNTHETIC_FIXTURE_REGISTRY_PROFILE,
                "strategy_registration_count": len(self._strategy_records),
                "failure_registration_count": len(self._failure_records),
                "strategy_registrations": self._strategy_records,
                "failure_registrations": self._failure_records,
                "registry_snapshot_hash": self._snapshot_hash,
            }
        )
        if not isinstance(projected, dict):  # pragma: no cover - fixed projection shape
            raise TypeError("registry artifact projection must be an object")
        return cast(dict[str, JsonValue], projected)

    @classmethod
    def from_artifact_payload(cls, value: Any) -> SyntheticFixtureRegistry:
        """Strictly parse and verify a complete pinned registry artifact."""

        item = _strict_object(
            value,
            keys=_REGISTRY_ARTIFACT_KEYS,
            field_name="synthetic fixture registry artifact",
        )
        if item["schema_version"] != SYNTHETIC_FIXTURE_REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                "synthetic fixture registry schema_version must be "
                f"{SYNTHETIC_FIXTURE_REGISTRY_SCHEMA_VERSION!r}"
            )
        if item["profile"] != SYNTHETIC_FIXTURE_REGISTRY_PROFILE:
            raise ValueError(
                f"synthetic fixture registry profile must be {SYNTHETIC_FIXTURE_REGISTRY_PROFILE!r}"
            )

        strategy_values = _strict_object_array(
            item["strategy_registrations"],
            field_name="strategy_registrations",
        )
        failure_values = _strict_object_array(
            item["failure_registrations"],
            field_name="failure_registrations",
        )
        strategies = tuple(
            synthetic_fixture_registration_from_json_value(record) for record in strategy_values
        )
        failures = tuple(
            failure_injection_registration_from_json_value(record) for record in failure_values
        )
        strategy_count = _parse_count(
            item["strategy_registration_count"],
            field_name="strategy_registration_count",
        )
        failure_count = _parse_count(
            item["failure_registration_count"],
            field_name="failure_registration_count",
        )
        if strategy_count != len(strategies) or failure_count != len(failures):
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_REGISTRY_COUNT_MISMATCH",
                "declared fixture counts must match the complete registration arrays",
            )

        strategy_ids = tuple(record.registration_id for record in strategies)
        failure_ids = tuple(record.registration_id for record in failures)
        if strategy_ids != tuple(sorted(strategy_ids)) or failure_ids != tuple(sorted(failure_ids)):
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_REGISTRY_ORDER_INVALID",
                "registration arrays must be ordered by registration_id",
            )

        registry = cls(strategies, failures)
        declared_snapshot_hash = _parse_hash(
            item["registry_snapshot_hash"],
            field_name="registry_snapshot_hash",
        )
        if declared_snapshot_hash != registry.snapshot_hash:
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_REGISTRY_SNAPSHOT_MISMATCH",
                "declared registry snapshot does not match the complete registrations",
            )
        return registry

    def require_strategy_case(
        self,
        *,
        strategy_id: str,
        case_id: str,
        strategy_input: SyntheticValidationInput,
        strategy_case_envelope: CanonicalModel,
        strategy_case_input_hash: HashDigest,
    ) -> ApprovedSyntheticFixtureCapability:
        """Issue a capability only for one exact registered case identity and bytes."""

        if not isinstance(strategy_input, SyntheticValidationInput):
            raise TypeError("strategy_input must be a SyntheticValidationInput")
        identity = (
            strategy_id,
            case_id,
            strategy_input.fixture_id,
            strategy_input.fixture_version,
        )
        registration = self._strategy_by_identity.get(identity)
        if registration is None:
            raise SyntheticFixtureAuthorizationError(
                "SYNTHETIC_FIXTURE_NOT_REGISTERED",
                "exact strategy, case, fixture ID, and version are not registered",
            )
        _assert_exact_case_binding(
            registration,
            strategy_id=strategy_id,
            case_id=case_id,
            strategy_input=strategy_input,
            strategy_case_envelope=strategy_case_envelope,
            strategy_case_input_hash=strategy_case_input_hash,
        )
        return ApprovedSyntheticFixtureCapability(
            _issuer=_CAPABILITY_ISSUER,
            registration=registration,
            registry_snapshot_hash=self._snapshot_hash,
        )

    def require_failure_payload(
        self,
        *,
        case_id: str,
        fixture_id: str,
        fixture_version: str,
        failure_payload: Mapping[str, JsonValue],
    ) -> FailureInjectionFixtureRegistration:
        """Validate exact failure inventory without granting strategy authority."""

        identity = (case_id, fixture_id, fixture_version)
        registration = self._failure_by_identity.get(identity)
        if registration is None:
            raise SyntheticFixtureAuthorizationError(
                "FAILURE_INJECTION_FIXTURE_NOT_REGISTERED",
                "exact failure-injection fixture identity is not registered",
            )
        frozen = freeze_json(failure_payload, path="$.failure_payload")
        if not isinstance(frozen, Mapping):
            raise TypeError("failure_payload must be a mapping")
        actual_hash = HashDigest(algorithm="sha256", value=canonical_sha256(frozen))
        if actual_hash != registration.failure_payload_hash:
            raise SyntheticFixtureAuthorizationError(
                "FAILURE_INJECTION_FIXTURE_HASH_MISMATCH",
                "failure-injection payload content is not registered",
            )
        return registration
