"""InvestSystem-owned Release consumption receipts and observations.

The receipt is a deterministic identity for verified content.  Transport,
time, endpoints, retries, provider status, and local admission are deliberately
kept in append-only observations and never enter the receipt identity.

These models describe consumer audit data only.  They neither implement a KB
transport nor define strategy, gate, valuation, or trading semantics.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any

from .canonical import canonical_json_bytes, format_utc, normalize_utc
from .models import CanonicalModel, HashDigest, StrategyInputRef

ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION = "0.1.0-draft"
CONSUMPTION_OBSERVATION_SCHEMA_VERSION = "0.2.0-draft"
MAX_STATUS_SEQUENCE = 2**63 - 1

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _require_schema_version(field_name: str, value: str, expected: str) -> str:
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}")
    return value


def _require_id(field_name: str, value: str, *, exact_release: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-128 ASCII ID characters "
            "([A-Za-z0-9._:-]) and start with an alphanumeric character"
        )
    if exact_release and value.casefold() == "latest":
        raise ValueError(f"{field_name} must be an exact ID, not 'latest'")
    return value


def _require_provider_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _PROVIDER_ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-256 provider ID characters "
            "([A-Za-z0-9._:/-]) and start with an alphanumeric character"
        )
    return value


def _require_text(field_name: str, value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_version(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _SEMVER_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")
    return value


def _require_non_negative_int(field_name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _freeze_unique_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple of IDs")
    result = tuple(_require_id(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicate IDs")
    return result


def _freeze_unique_provider_ids(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple of provider IDs")
    result = tuple(_require_provider_id(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicate provider IDs")
    return result


def _freeze_unique_texts(field_name: str, values: Iterable[str]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple of strings")
    result = tuple(_require_text(field_name, value) for value in values)
    if len(result) != len(set(result)):
        raise ValueError(f"{field_name} must not contain duplicate values")
    return result


def _validate_supersedes(observation_id: str, supersedes: str | None) -> None:
    if supersedes is None:
        return
    _require_id("supersedes", supersedes)
    if supersedes == observation_id:
        raise ValueError("supersedes must not refer to the observation itself")


class DeliveryTransport(StrEnum):
    """Approved read-only KB delivery surfaces."""

    READ_ONLY_HTTP_API = "read_only_http_api"
    IMMUTABLE_EXPORT = "immutable_export"


class SchemaValidationResult(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


class ProviderReleaseStatus(StrEnum):
    """A validated provider status; an unconfirmable status is represented as absent."""

    BUILDING = "building"
    VALIDATED = "validated"
    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class ReleaseAdmissionStatus(StrEnum):
    """InvestSystem-local admission, separate from provider status."""

    AUTHORIZED = "authorized"
    UNCONFIRMED = "unconfirmed"
    DENIED = "denied"


class ConsumptionObservationType(StrEnum):
    ARTIFACT_FETCH = "artifact_fetch"
    RELEASE_STATUS = "release_status"
    RELEASE_ADMISSION = "release_admission"


@dataclass(frozen=True, slots=True)
class ArtifactReceiptItem(CanonicalModel):
    """One exact artifact included in a deterministic consumption receipt."""

    artifact_id: str
    item_type: str
    artifact_hash: HashDigest
    size_bytes: int
    record_count: int | None

    def __post_init__(self) -> None:
        _require_provider_id("artifact_id", self.artifact_id)
        _require_id("item_type", self.item_type)
        if not isinstance(self.artifact_hash, HashDigest):
            raise TypeError("artifact_hash must be a HashDigest")
        _require_non_negative_int("size_bytes", self.size_bytes)
        if self.record_count is not None:
            _require_non_negative_int("record_count", self.record_count)


def _normalize_artifacts(values: Iterable[ArtifactReceiptItem]) -> tuple[ArtifactReceiptItem, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError("artifacts must be an ordered list or tuple")
    artifacts = tuple(values)
    if not artifacts:
        raise ValueError("artifacts must not be empty")
    if any(not isinstance(item, ArtifactReceiptItem) for item in artifacts):
        raise TypeError("artifacts must contain only ArtifactReceiptItem values")
    artifact_ids = tuple(item.artifact_id for item in artifacts)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("artifacts must not contain duplicate artifact_id values")
    return tuple(sorted(artifacts, key=lambda item: item.artifact_id))


def _receipt_identity_payload(
    *,
    schema_version: str,
    consumer_contract_version: str,
    strategy_input_ref: StrategyInputRef,
    artifacts: tuple[ArtifactReceiptItem, ...],
) -> dict[str, Any]:
    """Build the explicit receipt payload whose identity excludes ``receipt_hash``."""

    return {
        "schema_version": schema_version,
        "consumer_contract_version": consumer_contract_version,
        "strategy_input_ref": strategy_input_ref.to_json_value(),
        "artifacts": [item.to_json_value() for item in artifacts],
    }


@dataclass(frozen=True, slots=True)
class ArtifactConsumptionReceipt(CanonicalModel):
    """Deterministic identity for one validated artifact set and consumer contract."""

    schema_version: str
    consumer_contract_version: str
    strategy_input_ref: StrategyInputRef
    artifacts: tuple[ArtifactReceiptItem, ...]
    receipt_hash: HashDigest

    def __post_init__(self) -> None:
        _require_schema_version(
            "schema_version",
            self.schema_version,
            ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
        )
        _require_version("consumer_contract_version", self.consumer_contract_version)
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        artifacts = _normalize_artifacts(self.artifacts)
        object.__setattr__(self, "artifacts", artifacts)
        if not isinstance(self.receipt_hash, HashDigest):
            raise TypeError("receipt_hash must be a HashDigest")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.receipt_hash.value != expected:
            raise ValueError("receipt_hash does not match the canonical identity payload")

    @classmethod
    def create(
        cls,
        *,
        consumer_contract_version: str,
        strategy_input_ref: StrategyInputRef,
        artifacts: Iterable[ArtifactReceiptItem],
        schema_version: str = ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
    ) -> ArtifactConsumptionReceipt:
        """Create a receipt after sorting artifacts and hashing the explicit identity payload."""

        _require_schema_version("schema_version", schema_version, cls.schema_version_default())
        _require_version("consumer_contract_version", consumer_contract_version)
        if not isinstance(strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        normalized = _normalize_artifacts(artifacts)
        payload = _receipt_identity_payload(
            schema_version=schema_version,
            consumer_contract_version=consumer_contract_version,
            strategy_input_ref=strategy_input_ref,
            artifacts=normalized,
        )
        receipt_hash = HashDigest(
            algorithm="sha256",
            value=sha256(canonical_json_bytes(payload)).hexdigest(),
        )
        return cls(
            schema_version=schema_version,
            consumer_contract_version=consumer_contract_version,
            strategy_input_ref=strategy_input_ref,
            artifacts=normalized,
            receipt_hash=receipt_hash,
        )

    @staticmethod
    def schema_version_default() -> str:
        return ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION

    def identity_payload(self) -> dict[str, Any]:
        """Return exactly the canonical payload covered by ``receipt_hash``."""

        return _receipt_identity_payload(
            schema_version=self.schema_version,
            consumer_contract_version=self.consumer_contract_version,
            strategy_input_ref=self.strategy_input_ref,
            artifacts=self.artifacts,
        )


@dataclass(frozen=True, slots=True)
class ArtifactFetchObservation(CanonicalModel):
    """Append-only observation of a transport fetch attempt."""

    schema_version: str
    observation_id: str
    release_id: str
    strategy_input_ref: StrategyInputRef
    observed_at: datetime
    transport: DeliveryTransport
    source_endpoint: str
    schema_validation_result: SchemaValidationResult
    receipt_hash: HashDigest | None = None
    artifact_ids: tuple[str, ...] = ()
    response_or_export_bytes_hash: HashDigest | None = None
    failure_reasons: tuple[str, ...] = ()
    local_cache_keys: tuple[str, ...] = ()
    supersedes: str | None = None
    observation_type: ConsumptionObservationType = field(
        init=False,
        default=ConsumptionObservationType.ARTIFACT_FETCH,
    )

    def __post_init__(self) -> None:
        _require_schema_version(
            "schema_version",
            self.schema_version,
            CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        )
        _require_id("observation_id", self.observation_id)
        _require_id("release_id", self.release_id, exact_release=True)
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.strategy_input_ref.dataset_release_id != self.release_id:
            raise ValueError("strategy_input_ref release does not match release_id")
        object.__setattr__(
            self,
            "observed_at",
            normalize_utc(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(
            self,
            "transport",
            _coerce_enum("transport", DeliveryTransport, self.transport),
        )
        _require_text("source_endpoint", self.source_endpoint)
        object.__setattr__(
            self,
            "schema_validation_result",
            _coerce_enum(
                "schema_validation_result",
                SchemaValidationResult,
                self.schema_validation_result,
            ),
        )
        if self.receipt_hash is not None and not isinstance(self.receipt_hash, HashDigest):
            raise TypeError("receipt_hash must be a HashDigest or None")
        artifact_ids = _freeze_unique_provider_ids("artifact_ids", self.artifact_ids)
        object.__setattr__(self, "artifact_ids", tuple(sorted(artifact_ids)))
        if self.response_or_export_bytes_hash is not None and not isinstance(
            self.response_or_export_bytes_hash, HashDigest
        ):
            raise TypeError("response_or_export_bytes_hash must be a HashDigest or None")
        reasons = _freeze_unique_ids("failure_reasons", self.failure_reasons)
        object.__setattr__(self, "failure_reasons", reasons)
        cache_keys = _freeze_unique_texts("local_cache_keys", self.local_cache_keys)
        object.__setattr__(self, "local_cache_keys", cache_keys)
        _validate_supersedes(self.observation_id, self.supersedes)
        if self.schema_validation_result is SchemaValidationResult.PASSED:
            if self.receipt_hash is None or not artifact_ids:
                raise ValueError("passed fetch observation requires receipt_hash and artifact_ids")
            if reasons:
                raise ValueError("passed fetch observation must not contain failure_reasons")
        else:
            if self.receipt_hash is not None or artifact_ids:
                raise ValueError(
                    "failed fetch observation must not expose receipt_hash or artifact_ids"
                )
            if cache_keys:
                raise ValueError("failed fetch observation must not expose local_cache_keys")
            if not reasons:
                raise ValueError("failed fetch observation requires failure_reasons")


@dataclass(frozen=True, slots=True)
class ReleaseStatusObservation(CanonicalModel):
    """Append-only observation of a validated provider status event."""

    schema_version: str
    observation_id: str
    release_id: str
    strategy_input_ref: StrategyInputRef
    observed_at: datetime
    schema_validation_result: SchemaValidationResult
    status: ProviderReleaseStatus | None = None
    status_event_id: str | None = None
    status_event_hash: HashDigest | None = None
    previous_status_event_hash: HashDigest | None = None
    status_sequence: int | None = None
    status_recorded_at: datetime | None = None
    failure_reasons: tuple[str, ...] = ()
    supersedes: str | None = None
    observation_type: ConsumptionObservationType = field(
        init=False,
        default=ConsumptionObservationType.RELEASE_STATUS,
    )

    def __post_init__(self) -> None:
        _require_schema_version(
            "schema_version",
            self.schema_version,
            CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        )
        _require_id("observation_id", self.observation_id)
        _require_id("release_id", self.release_id, exact_release=True)
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.strategy_input_ref.dataset_release_id != self.release_id:
            raise ValueError("strategy_input_ref release does not match release_id")
        object.__setattr__(
            self,
            "observed_at",
            normalize_utc(self.observed_at, field_name="observed_at"),
        )
        object.__setattr__(
            self,
            "schema_validation_result",
            _coerce_enum(
                "schema_validation_result",
                SchemaValidationResult,
                self.schema_validation_result,
            ),
        )
        if self.status is not None:
            object.__setattr__(
                self,
                "status",
                _coerce_enum("status", ProviderReleaseStatus, self.status),
            )
        if self.status_event_id is not None:
            _require_provider_id("status_event_id", self.status_event_id)
        if self.status_event_hash is not None and not isinstance(
            self.status_event_hash, HashDigest
        ):
            raise TypeError("status_event_hash must be a HashDigest or None")
        if self.previous_status_event_hash is not None and not isinstance(
            self.previous_status_event_hash, HashDigest
        ):
            raise TypeError("previous_status_event_hash must be a HashDigest or None")
        if self.status_sequence is not None:
            if isinstance(self.status_sequence, bool) or not isinstance(self.status_sequence, int):
                raise TypeError("status_sequence must be an integer or None")
            if self.status_sequence < 1:
                raise ValueError("status_sequence must be at least 1")
            if self.status_sequence > MAX_STATUS_SEQUENCE:
                raise ValueError("status_sequence exceeds the SQLite signed integer limit")
        if self.status_recorded_at is not None:
            object.__setattr__(
                self,
                "status_recorded_at",
                normalize_utc(self.status_recorded_at, field_name="status_recorded_at"),
            )
            if self.status_recorded_at > self.observed_at:
                raise ValueError("status_recorded_at must be <= observed_at")
        reasons = _freeze_unique_ids("failure_reasons", self.failure_reasons)
        object.__setattr__(self, "failure_reasons", reasons)
        _validate_supersedes(self.observation_id, self.supersedes)

        required_event_fields = (
            self.status,
            self.status_event_id,
            self.status_event_hash,
            self.status_sequence,
            self.status_recorded_at,
        )
        if self.schema_validation_result is SchemaValidationResult.PASSED:
            if any(value is None for value in required_event_fields):
                raise ValueError(
                    "passed status observation requires status, status_event_id, "
                    "status_event_hash, status_sequence, and status_recorded_at"
                )
            if self.status_sequence == 1:
                if self.previous_status_event_hash is not None:
                    raise ValueError(
                        "the first provider status event must not have a previous hash"
                    )
                if self.status is not ProviderReleaseStatus.BUILDING:
                    raise ValueError("the first provider status event must be building")
            elif self.previous_status_event_hash is None:
                raise ValueError("provider status events after sequence 1 require a previous hash")
            if reasons:
                raise ValueError("passed status observation must not contain failure_reasons")
        else:
            if any(
                value is not None
                for value in (*required_event_fields, self.previous_status_event_hash)
            ):
                raise ValueError(
                    "failed status observation must not expose unvalidated event fields"
                )
            if not reasons:
                raise ValueError("failed status observation requires failure_reasons")


@dataclass(frozen=True, slots=True)
class ReleaseAdmissionObservation(CanonicalModel):
    """Append-only InvestSystem-local admission for one status observation."""

    schema_version: str
    observation_id: str
    release_id: str
    strategy_input_ref: StrategyInputRef
    observed_at: datetime
    status_observation_id: str
    admission_status: ReleaseAdmissionStatus
    failure_reasons: tuple[str, ...] = ()
    supersedes: str | None = None
    observation_type: ConsumptionObservationType = field(
        init=False,
        default=ConsumptionObservationType.RELEASE_ADMISSION,
    )

    def __post_init__(self) -> None:
        _require_schema_version(
            "schema_version",
            self.schema_version,
            CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        )
        _require_id("observation_id", self.observation_id)
        _require_id("release_id", self.release_id, exact_release=True)
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if self.strategy_input_ref.dataset_release_id != self.release_id:
            raise ValueError("strategy_input_ref release does not match release_id")
        object.__setattr__(
            self,
            "observed_at",
            normalize_utc(self.observed_at, field_name="observed_at"),
        )
        _require_id("status_observation_id", self.status_observation_id)
        object.__setattr__(
            self,
            "admission_status",
            _coerce_enum(
                "admission_status",
                ReleaseAdmissionStatus,
                self.admission_status,
            ),
        )
        reasons = _freeze_unique_ids("failure_reasons", self.failure_reasons)
        object.__setattr__(self, "failure_reasons", reasons)
        _validate_supersedes(self.observation_id, self.supersedes)
        if self.admission_status is ReleaseAdmissionStatus.AUTHORIZED and reasons:
            raise ValueError("authorized admission must not contain failure_reasons")
        if self.admission_status is not ReleaseAdmissionStatus.AUTHORIZED and not reasons:
            raise ValueError("unconfirmed or denied admission requires failure_reasons")


ConsumptionObservation = (
    ArtifactFetchObservation | ReleaseStatusObservation | ReleaseAdmissionObservation
)

_STRATEGY_INPUT_REF_KEYS = {
    "schema_version",
    "dataset_release_id",
    "knowledge_cutoff",
    "release_manifest_schema_version",
    "manifest_hash",
}
_HASH_KEYS = {"algorithm", "value"}
_OBSERVATION_COMMON_KEYS = {
    "schema_version",
    "observation_id",
    "release_id",
    "strategy_input_ref",
    "observed_at",
    "failure_reasons",
    "supersedes",
    "observation_type",
}
_OBSERVATION_KEYS = {
    ConsumptionObservationType.ARTIFACT_FETCH: _OBSERVATION_COMMON_KEYS
    | {
        "transport",
        "source_endpoint",
        "schema_validation_result",
        "receipt_hash",
        "artifact_ids",
        "response_or_export_bytes_hash",
        "local_cache_keys",
    },
    ConsumptionObservationType.RELEASE_STATUS: _OBSERVATION_COMMON_KEYS
    | {
        "schema_validation_result",
        "status",
        "status_event_id",
        "status_event_hash",
        "previous_status_event_hash",
        "status_sequence",
        "status_recorded_at",
    },
    ConsumptionObservationType.RELEASE_ADMISSION: _OBSERVATION_COMMON_KEYS
    | {"status_observation_id", "admission_status"},
}


def _strict_object(value: Any, *, keys: set[str], field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{field_name} must contain exactly the contract fields")
    return value


def _strict_list(value: Any, *, field_name: str) -> tuple[Any, ...]:
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be a JSON array")
    return tuple(value)


def _parse_canonical_utc(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a canonical UTC timestamp") from exc
    if format_utc(parsed) != value:
        raise ValueError(f"{field_name} must be a canonical UTC timestamp")
    return parsed


def _parse_hash(value: Any, *, field_name: str, nullable: bool = False) -> HashDigest | None:
    if value is None and nullable:
        return None
    item = _strict_object(value, keys=_HASH_KEYS, field_name=field_name)
    return HashDigest(algorithm=item["algorithm"], value=item["value"])


def _parse_strategy_input_ref(value: Any) -> StrategyInputRef:
    item = _strict_object(
        value,
        keys=_STRATEGY_INPUT_REF_KEYS,
        field_name="strategy_input_ref",
    )
    manifest_hash = _parse_hash(item["manifest_hash"], field_name="manifest_hash")
    if manifest_hash is None:  # pragma: no cover - impossible without nullable=True
        raise TypeError("manifest_hash must not be null")
    return StrategyInputRef(
        schema_version=item["schema_version"],
        dataset_release_id=item["dataset_release_id"],
        knowledge_cutoff=_parse_canonical_utc(
            item["knowledge_cutoff"], field_name="knowledge_cutoff"
        ),
        release_manifest_schema_version=item["release_manifest_schema_version"],
        manifest_hash=manifest_hash,
    )


def _consumption_observation_from_json_value(value: Any) -> ConsumptionObservation:
    """Strictly reconstruct one Observation from its complete JSON contract value."""

    if not isinstance(value, dict):
        raise TypeError("observation must be a JSON object")
    observation_type_value = value.get("observation_type")
    if not isinstance(observation_type_value, str):
        raise ValueError("observation_type is unknown")
    try:
        observation_type = ConsumptionObservationType(observation_type_value)
    except ValueError as exc:
        raise ValueError("observation_type is unknown") from exc
    item = _strict_object(
        value,
        keys=_OBSERVATION_KEYS[observation_type],
        field_name="observation",
    )
    common: dict[str, Any] = {
        "schema_version": item["schema_version"],
        "observation_id": item["observation_id"],
        "release_id": item["release_id"],
        "strategy_input_ref": _parse_strategy_input_ref(item["strategy_input_ref"]),
        "observed_at": _parse_canonical_utc(item["observed_at"], field_name="observed_at"),
        "failure_reasons": _strict_list(item["failure_reasons"], field_name="failure_reasons"),
        "supersedes": item["supersedes"],
    }
    if observation_type is ConsumptionObservationType.ARTIFACT_FETCH:
        return ArtifactFetchObservation(
            **common,
            transport=item["transport"],
            source_endpoint=item["source_endpoint"],
            schema_validation_result=item["schema_validation_result"],
            receipt_hash=_parse_hash(
                item["receipt_hash"], field_name="receipt_hash", nullable=True
            ),
            artifact_ids=_strict_list(item["artifact_ids"], field_name="artifact_ids"),
            response_or_export_bytes_hash=_parse_hash(
                item["response_or_export_bytes_hash"],
                field_name="response_or_export_bytes_hash",
                nullable=True,
            ),
            local_cache_keys=_strict_list(item["local_cache_keys"], field_name="local_cache_keys"),
        )
    if observation_type is ConsumptionObservationType.RELEASE_STATUS:
        status_recorded_at = item["status_recorded_at"]
        return ReleaseStatusObservation(
            **common,
            schema_validation_result=item["schema_validation_result"],
            status=item["status"],
            status_event_id=item["status_event_id"],
            status_event_hash=_parse_hash(
                item["status_event_hash"], field_name="status_event_hash", nullable=True
            ),
            previous_status_event_hash=_parse_hash(
                item["previous_status_event_hash"],
                field_name="previous_status_event_hash",
                nullable=True,
            ),
            status_sequence=item["status_sequence"],
            status_recorded_at=(
                _parse_canonical_utc(status_recorded_at, field_name="status_recorded_at")
                if status_recorded_at is not None
                else None
            ),
        )
    return ReleaseAdmissionObservation(
        **common,
        status_observation_id=item["status_observation_id"],
        admission_status=item["admission_status"],
    )


def consumption_observation_from_canonical_bytes(content: bytes) -> ConsumptionObservation:
    """Parse exact canonical bytes into a fully validated Observation model."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    try:
        value = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("content is not a UTF-8 JSON document") from exc
    observation = _consumption_observation_from_json_value(value)
    if observation.to_canonical_bytes() != content:
        raise ValueError("content is not the canonical Observation representation")
    return observation
