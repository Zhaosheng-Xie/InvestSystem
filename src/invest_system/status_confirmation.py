"""Run-scoped confirmation of current provider Release status.

This provider-neutral contract records the exact status-event snapshot checked
for a prospective run.  It does not decide whether an authority is trusted,
whether a confirmation is fresh enough, or whether its Release set equals a
persisted retention closure; those are storage/admission policy checks.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from .canonical import canonical_json_bytes, format_utc, normalize_utc
from .models import CanonicalModel, HashDigest, StrategyInputRef

RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION = "0.1.0-draft"
MAX_STATUS_SEQUENCE = 2**63 - 1

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")

_HASH_KEYS = {"algorithm", "value"}
_STRATEGY_INPUT_REF_KEYS = {
    "schema_version",
    "dataset_release_id",
    "knowledge_cutoff",
    "release_manifest_schema_version",
    "manifest_hash",
}
_CONFIRMATION_ITEM_KEYS = {
    "strategy_input_ref",
    "status_observation_id",
    "status_event_id",
    "status_event_hash",
    "status_sequence",
    "provider_snapshot_at",
    "checked_at",
    "response_bytes_hash",
}
_CONFIRMATION_KEYS = {
    "schema_version",
    "confirmation_id",
    "run_id",
    "root_release_id",
    "receipt_hash",
    "closure_hash",
    "authority_id",
    "authority_contract_hash",
    "requested_at",
    "confirmed_at",
    "expires_at",
    "items",
    "confirmation_hash",
}


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


def _normalize_items(
    values: Iterable[RunReleaseStatusConfirmationItem],
) -> tuple[RunReleaseStatusConfirmationItem, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError("items must be an ordered list or tuple")
    items = tuple(values)
    if not items:
        raise ValueError("items must not be empty")
    if any(not isinstance(item, RunReleaseStatusConfirmationItem) for item in items):
        raise TypeError("items must contain only RunReleaseStatusConfirmationItem values")
    release_ids = tuple(item.release_id for item in items)
    if len(release_ids) != len(set(release_ids)):
        raise ValueError("items must not contain duplicate release_id values")
    return tuple(sorted(items, key=lambda item: item.release_id))


@dataclass(frozen=True, slots=True)
class RunReleaseStatusConfirmationItem(CanonicalModel):
    """One exact Release status event observed by a live confirmation check."""

    strategy_input_ref: StrategyInputRef
    status_observation_id: str
    status_event_id: str
    status_event_hash: HashDigest
    status_sequence: int
    provider_snapshot_at: datetime
    checked_at: datetime
    response_bytes_hash: HashDigest

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        _require_id("status_observation_id", self.status_observation_id)
        _require_provider_id("status_event_id", self.status_event_id)
        if not isinstance(self.status_event_hash, HashDigest):
            raise TypeError("status_event_hash must be a HashDigest")
        if isinstance(self.status_sequence, bool) or not isinstance(self.status_sequence, int):
            raise TypeError("status_sequence must be an integer")
        if self.status_sequence < 1:
            raise ValueError("status_sequence must be at least 1")
        if self.status_sequence > MAX_STATUS_SEQUENCE:
            raise ValueError("status_sequence exceeds the SQLite signed integer limit")
        object.__setattr__(
            self,
            "provider_snapshot_at",
            normalize_utc(self.provider_snapshot_at, field_name="provider_snapshot_at"),
        )
        object.__setattr__(
            self,
            "checked_at",
            normalize_utc(self.checked_at, field_name="checked_at"),
        )
        if not isinstance(self.response_bytes_hash, HashDigest):
            raise TypeError("response_bytes_hash must be a HashDigest")

    @property
    def release_id(self) -> str:
        """Exact Release ID preserved by the item's full five-field reference."""

        return self.strategy_input_ref.dataset_release_id


def _confirmation_identity_payload(
    *,
    schema_version: str,
    confirmation_id: str,
    run_id: str,
    root_release_id: str,
    receipt_hash: HashDigest,
    closure_hash: HashDigest,
    authority_id: str,
    authority_contract_hash: HashDigest,
    requested_at: datetime,
    confirmed_at: datetime,
    expires_at: datetime,
    items: tuple[RunReleaseStatusConfirmationItem, ...],
) -> dict[str, Any]:
    """Build the explicit payload whose identity excludes ``confirmation_hash``."""

    return {
        "schema_version": schema_version,
        "confirmation_id": confirmation_id,
        "run_id": run_id,
        "root_release_id": root_release_id,
        "receipt_hash": receipt_hash.to_json_value(),
        "closure_hash": closure_hash.to_json_value(),
        "authority_id": authority_id,
        "authority_contract_hash": authority_contract_hash.to_json_value(),
        "requested_at": requested_at,
        "confirmed_at": confirmed_at,
        "expires_at": expires_at,
        "items": [item.to_json_value() for item in items],
    }


@dataclass(frozen=True, slots=True)
class RunReleaseStatusConfirmation(CanonicalModel):
    """Canonical all-Release current-status confirmation for one prospective run."""

    schema_version: str
    confirmation_id: str
    run_id: str
    root_release_id: str
    receipt_hash: HashDigest
    closure_hash: HashDigest
    authority_id: str
    authority_contract_hash: HashDigest
    requested_at: datetime
    confirmed_at: datetime
    expires_at: datetime
    items: tuple[RunReleaseStatusConfirmationItem, ...]
    confirmation_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION!r}"
            )
        _require_id("confirmation_id", self.confirmation_id)
        _require_id("run_id", self.run_id)
        _require_id("root_release_id", self.root_release_id, exact_release=True)
        if not isinstance(self.receipt_hash, HashDigest):
            raise TypeError("receipt_hash must be a HashDigest")
        if not isinstance(self.closure_hash, HashDigest):
            raise TypeError("closure_hash must be a HashDigest")
        _require_id("authority_id", self.authority_id)
        if not isinstance(self.authority_contract_hash, HashDigest):
            raise TypeError("authority_contract_hash must be a HashDigest")
        for field_name in ("requested_at", "confirmed_at", "expires_at"):
            object.__setattr__(
                self,
                field_name,
                normalize_utc(getattr(self, field_name), field_name=field_name),
            )
        if self.requested_at > self.confirmed_at:
            raise ValueError("requested_at must be <= confirmed_at")
        if self.confirmed_at >= self.expires_at:
            raise ValueError("confirmed_at must be < expires_at")
        items = _normalize_items(self.items)
        object.__setattr__(self, "items", items)
        if self.root_release_id not in {item.release_id for item in items}:
            raise ValueError("root_release_id must be present in items")
        if any(
            item.checked_at < self.requested_at or item.checked_at > self.confirmed_at
            for item in items
        ):
            raise ValueError("every item.checked_at must be within the confirmation window")
        if not isinstance(self.confirmation_hash, HashDigest):
            raise TypeError("confirmation_hash must be a HashDigest")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.confirmation_hash.value != expected:
            raise ValueError("confirmation_hash does not match the canonical identity payload")

    @classmethod
    def create(
        cls,
        *,
        confirmation_id: str,
        run_id: str,
        root_release_id: str,
        receipt_hash: HashDigest,
        closure_hash: HashDigest,
        authority_id: str,
        authority_contract_hash: HashDigest,
        requested_at: datetime,
        confirmed_at: datetime,
        expires_at: datetime,
        items: Iterable[RunReleaseStatusConfirmationItem],
        schema_version: str = RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION,
    ) -> RunReleaseStatusConfirmation:
        """Normalize, validate, and hash one run-scoped Release status snapshot."""

        if schema_version != RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION:
            raise ValueError(
                f"schema_version must be {RUN_RELEASE_STATUS_CONFIRMATION_SCHEMA_VERSION!r}"
            )
        _require_id("confirmation_id", confirmation_id)
        _require_id("run_id", run_id)
        _require_id("root_release_id", root_release_id, exact_release=True)
        if not isinstance(receipt_hash, HashDigest):
            raise TypeError("receipt_hash must be a HashDigest")
        if not isinstance(closure_hash, HashDigest):
            raise TypeError("closure_hash must be a HashDigest")
        _require_id("authority_id", authority_id)
        if not isinstance(authority_contract_hash, HashDigest):
            raise TypeError("authority_contract_hash must be a HashDigest")
        normalized_requested_at = normalize_utc(requested_at, field_name="requested_at")
        normalized_confirmed_at = normalize_utc(confirmed_at, field_name="confirmed_at")
        normalized_expires_at = normalize_utc(expires_at, field_name="expires_at")
        if normalized_requested_at > normalized_confirmed_at:
            raise ValueError("requested_at must be <= confirmed_at")
        if normalized_confirmed_at >= normalized_expires_at:
            raise ValueError("confirmed_at must be < expires_at")
        normalized = _normalize_items(items)
        if root_release_id not in {item.release_id for item in normalized}:
            raise ValueError("root_release_id must be present in items")
        if any(
            item.checked_at < normalized_requested_at or item.checked_at > normalized_confirmed_at
            for item in normalized
        ):
            raise ValueError("every item.checked_at must be within the confirmation window")
        payload = _confirmation_identity_payload(
            schema_version=schema_version,
            confirmation_id=confirmation_id,
            run_id=run_id,
            root_release_id=root_release_id,
            receipt_hash=receipt_hash,
            closure_hash=closure_hash,
            authority_id=authority_id,
            authority_contract_hash=authority_contract_hash,
            requested_at=normalized_requested_at,
            confirmed_at=normalized_confirmed_at,
            expires_at=normalized_expires_at,
            items=normalized,
        )
        confirmation_hash = HashDigest(
            algorithm="sha256",
            value=sha256(canonical_json_bytes(payload)).hexdigest(),
        )
        return cls(
            schema_version=schema_version,
            confirmation_id=confirmation_id,
            run_id=run_id,
            root_release_id=root_release_id,
            receipt_hash=receipt_hash,
            closure_hash=closure_hash,
            authority_id=authority_id,
            authority_contract_hash=authority_contract_hash,
            requested_at=normalized_requested_at,
            confirmed_at=normalized_confirmed_at,
            expires_at=normalized_expires_at,
            items=normalized,
            confirmation_hash=confirmation_hash,
        )

    def identity_payload(self) -> dict[str, Any]:
        """Return exactly the canonical payload covered by ``confirmation_hash``."""

        return _confirmation_identity_payload(
            schema_version=self.schema_version,
            confirmation_id=self.confirmation_id,
            run_id=self.run_id,
            root_release_id=self.root_release_id,
            receipt_hash=self.receipt_hash,
            closure_hash=self.closure_hash,
            authority_id=self.authority_id,
            authority_contract_hash=self.authority_contract_hash,
            requested_at=self.requested_at,
            confirmed_at=self.confirmed_at,
            expires_at=self.expires_at,
            items=self.items,
        )


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


def _parse_hash(value: Any, *, field_name: str) -> HashDigest:
    item = _strict_object(value, keys=_HASH_KEYS, field_name=field_name)
    return HashDigest(algorithm=item["algorithm"], value=item["value"])


def _parse_strategy_input_ref(value: Any) -> StrategyInputRef:
    item = _strict_object(
        value,
        keys=_STRATEGY_INPUT_REF_KEYS,
        field_name="strategy_input_ref",
    )
    return StrategyInputRef(
        schema_version=item["schema_version"],
        dataset_release_id=item["dataset_release_id"],
        knowledge_cutoff=_parse_canonical_utc(
            item["knowledge_cutoff"], field_name="knowledge_cutoff"
        ),
        release_manifest_schema_version=item["release_manifest_schema_version"],
        manifest_hash=_parse_hash(item["manifest_hash"], field_name="manifest_hash"),
    )


def _parse_confirmation_item(value: Any) -> RunReleaseStatusConfirmationItem:
    item = _strict_object(
        value,
        keys=_CONFIRMATION_ITEM_KEYS,
        field_name="confirmation item",
    )
    return RunReleaseStatusConfirmationItem(
        strategy_input_ref=_parse_strategy_input_ref(item["strategy_input_ref"]),
        status_observation_id=item["status_observation_id"],
        status_event_id=item["status_event_id"],
        status_event_hash=_parse_hash(item["status_event_hash"], field_name="status_event_hash"),
        status_sequence=item["status_sequence"],
        provider_snapshot_at=_parse_canonical_utc(
            item["provider_snapshot_at"], field_name="provider_snapshot_at"
        ),
        checked_at=_parse_canonical_utc(item["checked_at"], field_name="checked_at"),
        response_bytes_hash=_parse_hash(
            item["response_bytes_hash"], field_name="response_bytes_hash"
        ),
    )


def _status_confirmation_from_json_value(value: Any) -> RunReleaseStatusConfirmation:
    item = _strict_object(
        value,
        keys=_CONFIRMATION_KEYS,
        field_name="status confirmation",
    )
    raw_items = _strict_list(item["items"], field_name="items")
    return RunReleaseStatusConfirmation(
        schema_version=item["schema_version"],
        confirmation_id=item["confirmation_id"],
        run_id=item["run_id"],
        root_release_id=item["root_release_id"],
        receipt_hash=_parse_hash(item["receipt_hash"], field_name="receipt_hash"),
        closure_hash=_parse_hash(item["closure_hash"], field_name="closure_hash"),
        authority_id=item["authority_id"],
        authority_contract_hash=_parse_hash(
            item["authority_contract_hash"], field_name="authority_contract_hash"
        ),
        requested_at=_parse_canonical_utc(item["requested_at"], field_name="requested_at"),
        confirmed_at=_parse_canonical_utc(item["confirmed_at"], field_name="confirmed_at"),
        expires_at=_parse_canonical_utc(item["expires_at"], field_name="expires_at"),
        items=tuple(_parse_confirmation_item(raw_item) for raw_item in raw_items),
        confirmation_hash=_parse_hash(item["confirmation_hash"], field_name="confirmation_hash"),
    )


def status_confirmation_from_canonical_bytes(
    content: bytes,
) -> RunReleaseStatusConfirmation:
    """Parse exact canonical bytes into a fully validated status confirmation."""

    if not isinstance(content, bytes):
        raise TypeError("content must be bytes")
    try:
        value = json.loads(content)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("content is not a UTF-8 JSON document") from exc
    confirmation = _status_confirmation_from_json_value(value)
    if confirmation.to_canonical_bytes() != content:
        raise ValueError("content is not the canonical status confirmation representation")
    return confirmation
