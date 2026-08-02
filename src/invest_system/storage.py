"""InvestSystem-owned SQLite v3 state and immutable KB Release cache.

The storage boundary accepts only provider-neutral, already validated
InvestSystem contracts.  A receipt identifies the root Release payload while
the retention closure records every transitive source Release and artifact
which an admitted run must preserve.  Transport observations are append-only;
``pin_run`` rechecks their current heads in one ``BEGIN IMMEDIATE`` transaction
and derives its pins from the persisted receipt/closure -- callers cannot
choose a subset of artifacts.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

from .canonical import canonical_json_bytes, format_utc
from .clock import Clock, SystemClock, read_clock
from .consumption import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ProviderReleaseStatus,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    ReleaseStatusObservation,
    SchemaValidationResult,
    consumption_observation_from_canonical_bytes,
)
from .models import HashDigest, StrategyInputRef, StrategyRunManifest
from .retention import (
    ArtifactPayload,
    ReleaseManifestPayload,
    ReleaseRetentionClosure,
)
from .status_confirmation import (
    RunReleaseStatusConfirmation,
    status_confirmation_from_canonical_bytes,
)

STORAGE_SCHEMA_VERSION = 3
DEFAULT_CACHE_SOFT_LIMIT_BYTES = 20 * 1024**3
STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION = "investsystem-canonical-json-v1"

# Compatibility names are aliases, not duplicate status models.
ReleaseStatus = ProviderReleaseStatus
AdmissionStatus = ReleaseAdmissionStatus

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StorageError(RuntimeError):
    """Base class for fail-closed storage errors."""


class StorageSchemaError(StorageError):
    """The SQLite schema is unknown, incomplete, or unsafe to adopt."""


class CacheIntegrityError(StorageError):
    """Declared, persisted, or read-back content has conflicting identity."""


class ReleaseAccessError(StorageError):
    """Current observations, purpose, or pin policy denies access."""


class ImmutableMappingError(StorageError):
    """An immutable identifier was reused for different canonical content."""


class RunPurpose(StrEnum):
    NEW_RUN = "new_run"
    AUDIT_REPLAY = "audit_replay"


@dataclass(frozen=True, slots=True)
class CurrentStatusAuthorityPolicy:
    """Trust and freshness limits for one status-confirmation authority contract."""

    authority_id: str
    authority_contract_hash: HashDigest
    max_age: timedelta
    max_clock_skew: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        _require_id("authority_id", self.authority_id)
        if not isinstance(self.authority_contract_hash, HashDigest):
            raise TypeError("authority_contract_hash must be a HashDigest")
        if not isinstance(self.max_age, timedelta):
            raise TypeError("max_age must be a timedelta")
        if self.max_age <= timedelta(0):
            raise ValueError("max_age must be positive")
        if not isinstance(self.max_clock_skew, timedelta):
            raise TypeError("max_clock_skew must be a timedelta")
        if self.max_clock_skew < timedelta(0):
            raise ValueError("max_clock_skew must be non-negative")


class CacheIssueKind(StrEnum):
    MISSING = "missing"
    CORRUPT = "corrupt"
    METADATA = "metadata"
    SCAN_FAILURE = "scan_failure"


@dataclass(frozen=True, slots=True)
class AuditReplayRequest:
    """Read-only capability referring to one already-pinned source run."""

    source_run_id: str
    source_manifest_hash: str
    purpose: RunPurpose = field(init=False, default=RunPurpose.AUDIT_REPLAY)

    def __post_init__(self) -> None:
        _require_id("source_run_id", self.source_run_id)
        _require_digest(self.source_manifest_hash, field_name="source_manifest_hash")


@dataclass(frozen=True, slots=True)
class CachedArtifact:
    release_id: str
    artifact_id: str
    sha256: str
    size_bytes: int
    path: Path


@dataclass(frozen=True, slots=True)
class CacheScanIssue:
    kind: CacheIssueKind
    relative_path: str
    detail: str
    pinned: bool = False


@dataclass(frozen=True, slots=True)
class CacheQuotaReport:
    soft_limit_bytes: int
    physical_bytes: int
    registered_bytes: int
    orphan_bytes: int
    pinned_bytes: int
    integrity_checked: bool
    issues: tuple[CacheScanIssue, ...]

    @property
    def stored_bytes(self) -> int:
        return self.physical_bytes

    @property
    def remaining_bytes(self) -> int:
        return max(0, self.soft_limit_bytes - self.physical_bytes)

    @property
    def over_limit(self) -> bool:
        return self.physical_bytes > self.soft_limit_bytes

    @property
    def scan_complete(self) -> bool:
        return not any(issue.kind is CacheIssueKind.SCAN_FAILURE for issue in self.issues)

    @property
    def has_anomalies(self) -> bool:
        return bool(self.issues)

    def issues_of_kind(self, kind: CacheIssueKind) -> tuple[CacheScanIssue, ...]:
        return tuple(issue for issue in self.issues if issue.kind is kind)


@dataclass(frozen=True, slots=True)
class ReleaseAccessContext:
    status_validation_result: SchemaValidationResult | None
    provider_status: ProviderReleaseStatus | None
    provider_status_observation_id: str | None
    admission_status: ReleaseAdmissionStatus | None
    admission_observation_id: str | None
    admission_provider_status_observation_id: str | None

    @property
    def authorized(self) -> bool:
        return (
            self.status_validation_result is SchemaValidationResult.PASSED
            and self.provider_status is ProviderReleaseStatus.PUBLISHED
            and self.admission_status is ReleaseAdmissionStatus.AUTHORIZED
            and self.provider_status_observation_id == self.admission_provider_status_observation_id
        )


@dataclass(frozen=True, slots=True)
class ArtifactRead:
    content: bytes
    artifact: CachedArtifact
    purpose: RunPurpose
    source_run_id: str
    source_manifest_hash: str
    source_manifest_profile_version: str
    pinned_release_status_observation_id: str
    pinned_root_admission_observation_id: str
    current_release_access: ReleaseAccessContext


def _require_id(name: str, value: str, *, exact_release: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a valid 1-128 character identifier")
    if exact_release and value.casefold() == "latest":
        raise ValueError(f"{name} must be exact, not 'latest'")
    return value


def _require_digest(value: str, *, field_name: str = "sha256") -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return value


def _require_provider_id(name: str, value: str) -> str:
    if not isinstance(value, str) or _PROVIDER_ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a valid 1-256 character provider identifier")
    return value


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


_TABLE_SQL: dict[str, str] = {
    "release_identities": """CREATE TABLE release_identities (
        release_id TEXT NOT NULL PRIMARY KEY,
        input_ref_schema_version TEXT NOT NULL,
        knowledge_cutoff TEXT NOT NULL,
        manifest_schema_version TEXT NOT NULL,
        manifest_hash TEXT NOT NULL CHECK(length(manifest_hash) = 64 AND manifest_hash NOT GLOB '*[^0-9a-f]*'),
        created_at TEXT NOT NULL
    )""",
    "cache_objects": """CREATE TABLE cache_objects (
        sha256 TEXT NOT NULL PRIMARY KEY CHECK(length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'),
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        relative_path TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL
    )""",
    "release_manifests": """CREATE TABLE release_manifests (
        release_id TEXT NOT NULL PRIMARY KEY,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        document_sha256 TEXT NOT NULL CHECK(length(document_sha256) = 64 AND document_sha256 NOT GLOB '*[^0-9a-f]*'),
        persisted_at TEXT NOT NULL,
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(sha256) REFERENCES cache_objects(sha256)
    )""",
    "retention_closures": """CREATE TABLE retention_closures (
        closure_hash TEXT NOT NULL PRIMARY KEY CHECK(length(closure_hash) = 64 AND closure_hash NOT GLOB '*[^0-9a-f]*'),
        schema_version TEXT NOT NULL,
        root_release_id TEXT NOT NULL,
        canonical_document BLOB NOT NULL,
        canonical_document_hash TEXT NOT NULL CHECK(length(canonical_document_hash) = 64 AND canonical_document_hash NOT GLOB '*[^0-9a-f]*'),
        persisted_at TEXT NOT NULL,
        FOREIGN KEY(root_release_id) REFERENCES release_identities(release_id)
    )""",
    "closure_releases": """CREATE TABLE closure_releases (
        closure_hash TEXT NOT NULL,
        release_id TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,
        manifest_size_bytes INTEGER NOT NULL CHECK(manifest_size_bytes > 0),
        PRIMARY KEY(closure_hash, release_id),
        FOREIGN KEY(closure_hash) REFERENCES retention_closures(closure_hash),
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(manifest_sha256) REFERENCES cache_objects(sha256)
    )""",
    "closure_dependencies": """CREATE TABLE closure_dependencies (
        closure_hash TEXT NOT NULL,
        parent_release_id TEXT NOT NULL,
        dependency_release_id TEXT NOT NULL,
        PRIMARY KEY(closure_hash, parent_release_id, dependency_release_id),
        FOREIGN KEY(closure_hash, parent_release_id) REFERENCES closure_releases(closure_hash, release_id),
        FOREIGN KEY(closure_hash, dependency_release_id) REFERENCES closure_releases(closure_hash, release_id),
        CHECK(parent_release_id <> dependency_release_id)
    )""",
    "closure_artifacts": """CREATE TABLE closure_artifacts (
        closure_hash TEXT NOT NULL,
        release_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        record_count INTEGER CHECK(record_count IS NULL OR record_count >= 0),
        PRIMARY KEY(closure_hash, release_id, artifact_id),
        FOREIGN KEY(closure_hash, release_id) REFERENCES closure_releases(closure_hash, release_id),
        FOREIGN KEY(sha256) REFERENCES cache_objects(sha256)
    )""",
    "release_artifacts": """CREATE TABLE release_artifacts (
        release_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        record_count INTEGER CHECK(record_count IS NULL OR record_count >= 0),
        persisted_at TEXT NOT NULL,
        PRIMARY KEY(release_id, artifact_id),
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(sha256) REFERENCES cache_objects(sha256)
    )""",
    "receipts": """CREATE TABLE receipts (
        receipt_hash TEXT NOT NULL PRIMARY KEY CHECK(length(receipt_hash) = 64 AND receipt_hash NOT GLOB '*[^0-9a-f]*'),
        schema_version TEXT NOT NULL,
        consumer_contract_version TEXT NOT NULL,
        release_id TEXT NOT NULL,
        canonical_document BLOB NOT NULL,
        canonical_document_hash TEXT NOT NULL CHECK(length(canonical_document_hash) = 64 AND canonical_document_hash NOT GLOB '*[^0-9a-f]*'),
        persisted_at TEXT NOT NULL,
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        UNIQUE(release_id, consumer_contract_version)
    )""",
    "receipt_artifacts": """CREATE TABLE receipt_artifacts (
        receipt_hash TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        item_type TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        record_count INTEGER CHECK(record_count IS NULL OR record_count >= 0),
        PRIMARY KEY(receipt_hash, artifact_id),
        FOREIGN KEY(receipt_hash) REFERENCES receipts(receipt_hash),
        FOREIGN KEY(sha256) REFERENCES cache_objects(sha256)
    )""",
    "receipt_closures": """CREATE TABLE receipt_closures (
        receipt_hash TEXT NOT NULL PRIMARY KEY,
        closure_hash TEXT NOT NULL,
        FOREIGN KEY(receipt_hash) REFERENCES receipts(receipt_hash),
        FOREIGN KEY(closure_hash) REFERENCES retention_closures(closure_hash)
    )""",
    "observations": """CREATE TABLE observations (
        observation_id TEXT NOT NULL PRIMARY KEY,
        observation_type TEXT NOT NULL CHECK(observation_type IN ('artifact_fetch','release_status','release_admission')),
        release_id TEXT NOT NULL,
        observed_at TEXT NOT NULL,
        supersedes TEXT UNIQUE,
        canonical_document BLOB NOT NULL,
        canonical_document_hash TEXT NOT NULL CHECK(length(canonical_document_hash) = 64 AND canonical_document_hash NOT GLOB '*[^0-9a-f]*'),
        persisted_at TEXT NOT NULL,
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(supersedes) REFERENCES observations(observation_id),
        CHECK(supersedes IS NULL OR supersedes <> observation_id)
    )""",
    "artifact_fetch_observations": """CREATE TABLE artifact_fetch_observations (
        observation_id TEXT NOT NULL PRIMARY KEY,
        validation_result TEXT NOT NULL CHECK(validation_result IN ('passed','failed')),
        receipt_hash TEXT,
        FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
        FOREIGN KEY(receipt_hash) REFERENCES receipts(receipt_hash),
        CHECK((validation_result = 'passed' AND receipt_hash IS NOT NULL) OR
              (validation_result = 'failed' AND receipt_hash IS NULL))
    )""",
    "release_status_observations": """CREATE TABLE release_status_observations (
        observation_id TEXT NOT NULL PRIMARY KEY,
        validation_result TEXT NOT NULL CHECK(validation_result IN ('passed','failed')),
        status TEXT CHECK(status IS NULL OR status IN ('building','validated','published','withdrawn')),
        status_event_id TEXT,
        status_event_hash TEXT CHECK(status_event_hash IS NULL OR
                                     (length(status_event_hash) = 64 AND status_event_hash NOT GLOB '*[^0-9a-f]*')),
        previous_status_event_hash TEXT CHECK(previous_status_event_hash IS NULL OR
                                              (length(previous_status_event_hash) = 64 AND previous_status_event_hash NOT GLOB '*[^0-9a-f]*')),
        status_sequence INTEGER CHECK(status_sequence IS NULL OR status_sequence >= 1),
        status_recorded_at TEXT,
        FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
        CHECK((validation_result = 'passed' AND status IS NOT NULL AND status_event_id IS NOT NULL
               AND status_event_hash IS NOT NULL AND status_sequence IS NOT NULL
               AND status_recorded_at IS NOT NULL
               AND ((status_sequence = 1 AND previous_status_event_hash IS NULL) OR
                    (status_sequence > 1 AND previous_status_event_hash IS NOT NULL))) OR
              (validation_result = 'failed' AND status IS NULL AND status_event_id IS NULL
               AND status_event_hash IS NULL AND previous_status_event_hash IS NULL
               AND status_sequence IS NULL
               AND status_recorded_at IS NULL))
    )""",
    "release_admission_observations": """CREATE TABLE release_admission_observations (
        observation_id TEXT NOT NULL PRIMARY KEY,
        status_observation_id TEXT NOT NULL,
        admission_status TEXT NOT NULL CHECK(admission_status IN ('authorized','unconfirmed','denied')),
        FOREIGN KEY(observation_id) REFERENCES observations(observation_id),
        FOREIGN KEY(status_observation_id) REFERENCES release_status_observations(observation_id)
    )""",
    "release_heads": """CREATE TABLE release_heads (
        release_id TEXT NOT NULL PRIMARY KEY,
        current_fetch_observation_id TEXT UNIQUE,
        current_status_observation_id TEXT UNIQUE,
        current_admission_observation_id TEXT UNIQUE,
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(current_fetch_observation_id) REFERENCES artifact_fetch_observations(observation_id),
        FOREIGN KEY(current_status_observation_id) REFERENCES release_status_observations(observation_id),
        FOREIGN KEY(current_admission_observation_id) REFERENCES release_admission_observations(observation_id)
    )""",
    "strategy_run_pins": """CREATE TABLE strategy_run_pins (
        run_id TEXT NOT NULL PRIMARY KEY,
        root_release_id TEXT NOT NULL,
        receipt_hash TEXT NOT NULL,
        closure_hash TEXT NOT NULL,
        fetch_observation_id TEXT NOT NULL,
        status_observation_id TEXT NOT NULL,
        admission_observation_id TEXT NOT NULL,
        run_manifest_canonical BLOB NOT NULL,
        run_manifest_hash TEXT NOT NULL CHECK(length(run_manifest_hash) = 64 AND run_manifest_hash NOT GLOB '*[^0-9a-f]*'),
        canonical_profile_version TEXT NOT NULL,
        pinned_at TEXT NOT NULL,
        FOREIGN KEY(root_release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(receipt_hash) REFERENCES receipts(receipt_hash),
        FOREIGN KEY(closure_hash) REFERENCES retention_closures(closure_hash),
        FOREIGN KEY(fetch_observation_id) REFERENCES artifact_fetch_observations(observation_id),
        FOREIGN KEY(status_observation_id) REFERENCES release_status_observations(observation_id),
        FOREIGN KEY(admission_observation_id) REFERENCES release_admission_observations(observation_id)
    )""",
    "run_release_status_confirmations": """CREATE TABLE run_release_status_confirmations (
        confirmation_hash TEXT NOT NULL PRIMARY KEY CHECK(length(confirmation_hash) = 64 AND confirmation_hash NOT GLOB '*[^0-9a-f]*'),
        confirmation_id TEXT NOT NULL UNIQUE,
        schema_version TEXT NOT NULL,
        run_id TEXT NOT NULL UNIQUE,
        root_release_id TEXT NOT NULL,
        receipt_hash TEXT NOT NULL,
        closure_hash TEXT NOT NULL,
        authority_id TEXT NOT NULL,
        authority_contract_hash TEXT NOT NULL CHECK(length(authority_contract_hash) = 64 AND authority_contract_hash NOT GLOB '*[^0-9a-f]*'),
        requested_at TEXT NOT NULL,
        confirmed_at TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        canonical_document BLOB NOT NULL,
        canonical_document_hash TEXT NOT NULL CHECK(length(canonical_document_hash) = 64 AND canonical_document_hash NOT GLOB '*[^0-9a-f]*'),
        persisted_at TEXT NOT NULL,
        FOREIGN KEY(root_release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(receipt_hash) REFERENCES receipts(receipt_hash),
        FOREIGN KEY(closure_hash) REFERENCES retention_closures(closure_hash)
    )""",
    "run_release_status_confirmation_items": """CREATE TABLE run_release_status_confirmation_items (
        confirmation_hash TEXT NOT NULL,
        release_id TEXT NOT NULL,
        input_ref_schema_version TEXT NOT NULL,
        knowledge_cutoff TEXT NOT NULL,
        manifest_schema_version TEXT NOT NULL,
        manifest_hash TEXT NOT NULL CHECK(length(manifest_hash) = 64 AND manifest_hash NOT GLOB '*[^0-9a-f]*'),
        status_observation_id TEXT NOT NULL,
        status_event_id TEXT NOT NULL,
        status_event_hash TEXT NOT NULL CHECK(length(status_event_hash) = 64 AND status_event_hash NOT GLOB '*[^0-9a-f]*'),
        status_sequence INTEGER NOT NULL CHECK(status_sequence >= 1),
        provider_snapshot_at TEXT NOT NULL,
        checked_at TEXT NOT NULL,
        response_bytes_hash TEXT NOT NULL CHECK(length(response_bytes_hash) = 64 AND response_bytes_hash NOT GLOB '*[^0-9a-f]*'),
        PRIMARY KEY(confirmation_hash, release_id),
        FOREIGN KEY(confirmation_hash) REFERENCES run_release_status_confirmations(confirmation_hash),
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(status_observation_id) REFERENCES release_status_observations(observation_id)
    )""",
    "strategy_run_confirmation_bindings": """CREATE TABLE strategy_run_confirmation_bindings (
        run_id TEXT NOT NULL PRIMARY KEY,
        confirmation_hash TEXT NOT NULL UNIQUE,
        bound_at TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES strategy_run_pins(run_id),
        FOREIGN KEY(confirmation_hash) REFERENCES run_release_status_confirmations(confirmation_hash)
    )""",
    "legacy_v2_quarantined_run_pins": """CREATE TABLE legacy_v2_quarantined_run_pins (
        run_id TEXT NOT NULL PRIMARY KEY,
        source_schema_version INTEGER NOT NULL CHECK(source_schema_version = 2),
        quarantined_at TEXT NOT NULL,
        reason TEXT NOT NULL,
        FOREIGN KEY(run_id) REFERENCES strategy_run_pins(run_id)
    )""",
    "pin_releases": """CREATE TABLE pin_releases (
        run_id TEXT NOT NULL,
        release_id TEXT NOT NULL,
        manifest_sha256 TEXT NOT NULL,
        status_observation_id TEXT NOT NULL,
        PRIMARY KEY(run_id, release_id),
        FOREIGN KEY(run_id) REFERENCES strategy_run_pins(run_id),
        FOREIGN KEY(release_id) REFERENCES release_identities(release_id),
        FOREIGN KEY(manifest_sha256) REFERENCES cache_objects(sha256),
        FOREIGN KEY(status_observation_id) REFERENCES release_status_observations(observation_id)
    )""",
    "pin_artifacts": """CREATE TABLE pin_artifacts (
        run_id TEXT NOT NULL,
        release_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
        PRIMARY KEY(run_id, release_id, artifact_id),
        FOREIGN KEY(run_id, release_id) REFERENCES pin_releases(run_id, release_id),
        FOREIGN KEY(sha256) REFERENCES cache_objects(sha256)
    )""",
}

_INDEX_SQL: dict[str, str] = {
    "idx_observations_release_type_time": "CREATE INDEX idx_observations_release_type_time ON observations(release_id, observation_type, observed_at)",
    "idx_closure_artifacts_sha": "CREATE INDEX idx_closure_artifacts_sha ON closure_artifacts(sha256)",
    "idx_pin_artifacts_sha": "CREATE INDEX idx_pin_artifacts_sha ON pin_artifacts(sha256)",
    "idx_status_confirmations_authority_confirmed": "CREATE INDEX idx_status_confirmations_authority_confirmed ON run_release_status_confirmations(authority_id, authority_contract_hash, confirmed_at)",
    "idx_status_confirmation_items_observation": "CREATE INDEX idx_status_confirmation_items_observation ON run_release_status_confirmation_items(status_observation_id)",
}

# BEFORE INSERT conflict guards make append-only identities robust even when
# an external SQLite client uses INSERT OR REPLACE with recursive_triggers
# disabled (SQLite's default).  Every declared PRIMARY KEY / UNIQUE conflict
# path is covered so REPLACE cannot delete an immutable row before inserting
# its replacement.
_INSERT_CONFLICT_PREDICATES: dict[str, str] = {
    "release_identities": "release_id = NEW.release_id",
    "cache_objects": "sha256 = NEW.sha256 OR relative_path = NEW.relative_path",
    "release_manifests": "release_id = NEW.release_id",
    "retention_closures": "closure_hash = NEW.closure_hash",
    "closure_releases": ("closure_hash = NEW.closure_hash AND release_id = NEW.release_id"),
    "closure_dependencies": (
        "closure_hash = NEW.closure_hash "
        "AND parent_release_id = NEW.parent_release_id "
        "AND dependency_release_id = NEW.dependency_release_id"
    ),
    "closure_artifacts": (
        "closure_hash = NEW.closure_hash AND release_id = NEW.release_id "
        "AND artifact_id = NEW.artifact_id"
    ),
    "release_artifacts": ("release_id = NEW.release_id AND artifact_id = NEW.artifact_id"),
    "receipts": (
        "receipt_hash = NEW.receipt_hash OR "
        "(release_id = NEW.release_id "
        "AND consumer_contract_version = NEW.consumer_contract_version)"
    ),
    "receipt_artifacts": ("receipt_hash = NEW.receipt_hash AND artifact_id = NEW.artifact_id"),
    "receipt_closures": "receipt_hash = NEW.receipt_hash",
    "observations": (
        "observation_id = NEW.observation_id OR "
        "(NEW.supersedes IS NOT NULL AND supersedes = NEW.supersedes)"
    ),
    "artifact_fetch_observations": "observation_id = NEW.observation_id",
    "release_status_observations": "observation_id = NEW.observation_id",
    "release_admission_observations": "observation_id = NEW.observation_id",
    "release_heads": (
        "release_id = NEW.release_id "
        "OR (NEW.current_fetch_observation_id IS NOT NULL "
        "AND current_fetch_observation_id = NEW.current_fetch_observation_id) "
        "OR (NEW.current_status_observation_id IS NOT NULL "
        "AND current_status_observation_id = NEW.current_status_observation_id) "
        "OR (NEW.current_admission_observation_id IS NOT NULL "
        "AND current_admission_observation_id = NEW.current_admission_observation_id)"
    ),
    "strategy_run_pins": "run_id = NEW.run_id",
    "run_release_status_confirmations": (
        "confirmation_hash = NEW.confirmation_hash OR confirmation_id = NEW.confirmation_id "
        "OR run_id = NEW.run_id"
    ),
    "run_release_status_confirmation_items": (
        "confirmation_hash = NEW.confirmation_hash AND release_id = NEW.release_id"
    ),
    "strategy_run_confirmation_bindings": (
        "run_id = NEW.run_id OR confirmation_hash = NEW.confirmation_hash"
    ),
    "legacy_v2_quarantined_run_pins": "run_id = NEW.run_id",
    "pin_releases": "run_id = NEW.run_id AND release_id = NEW.release_id",
    "pin_artifacts": (
        "run_id = NEW.run_id AND release_id = NEW.release_id AND artifact_id = NEW.artifact_id"
    ),
}

_IMMUTABLE_TABLES = tuple(name for name in _TABLE_SQL if name != "release_heads")


def _trigger_name(table: str, operation: str) -> str:
    return f"prevent_{operation.lower()}_{table}"


def _trigger_sql(table: str, operation: str) -> str:
    name = _trigger_name(table, operation)
    return (
        f"CREATE TRIGGER {name} BEFORE {operation} ON {table} "
        f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
    )


def _conflict_trigger_name(table: str) -> str:
    return f"prevent_conflicting_insert_{table}"


def _conflict_trigger_sql(table: str, predicate: str) -> str:
    name = _conflict_trigger_name(table)
    return (
        f"CREATE TRIGGER {name} BEFORE INSERT ON {table} "
        f"WHEN EXISTS (SELECT 1 FROM {table} WHERE {predicate}) "
        f"BEGIN SELECT RAISE(ABORT, '{table} immutable identity conflict'); END"
    )


def _release_heads_update_trigger_sql() -> str:
    return """CREATE TRIGGER prevent_invalid_update_release_heads
        BEFORE UPDATE ON release_heads
        WHEN investsystem_head_write_allowed() <> 1 OR NOT (
            NEW.release_id = OLD.release_id AND (
                (
                    NEW.current_fetch_observation_id IS NOT OLD.current_fetch_observation_id
                    AND NEW.current_status_observation_id IS OLD.current_status_observation_id
                    AND NEW.current_admission_observation_id IS OLD.current_admission_observation_id
                    AND NEW.current_fetch_observation_id IS NOT NULL
                    AND EXISTS (
                        SELECT 1 FROM observations AS observation
                        JOIN artifact_fetch_observations AS fetch USING(observation_id)
                        WHERE observation.observation_id = NEW.current_fetch_observation_id
                          AND observation.release_id = OLD.release_id
                          AND observation.observation_type = 'artifact_fetch'
                          AND observation.supersedes IS OLD.current_fetch_observation_id
                    )
                ) OR (
                    NEW.current_status_observation_id IS NOT OLD.current_status_observation_id
                    AND NEW.current_fetch_observation_id IS OLD.current_fetch_observation_id
                    AND NEW.current_admission_observation_id IS OLD.current_admission_observation_id
                    AND NEW.current_status_observation_id IS NOT NULL
                    AND EXISTS (
                        SELECT 1 FROM observations AS observation
                        JOIN release_status_observations AS status USING(observation_id)
                        WHERE observation.observation_id = NEW.current_status_observation_id
                          AND observation.release_id = OLD.release_id
                          AND observation.observation_type = 'release_status'
                          AND observation.supersedes IS OLD.current_status_observation_id
                    )
                ) OR (
                    NEW.current_admission_observation_id IS NOT OLD.current_admission_observation_id
                    AND NEW.current_fetch_observation_id IS OLD.current_fetch_observation_id
                    AND NEW.current_status_observation_id IS OLD.current_status_observation_id
                    AND NEW.current_admission_observation_id IS NOT NULL
                    AND EXISTS (
                        SELECT 1 FROM observations AS observation
                        JOIN release_admission_observations AS admission USING(observation_id)
                        WHERE observation.observation_id = NEW.current_admission_observation_id
                          AND observation.release_id = OLD.release_id
                          AND observation.observation_type = 'release_admission'
                          AND observation.supersedes IS OLD.current_admission_observation_id
                          AND admission.status_observation_id = NEW.current_status_observation_id
                    )
                )
            )
        )
        BEGIN SELECT RAISE(ABORT, 'release_heads transition is invalid'); END"""


def _release_heads_insert_trigger_sql() -> str:
    return """CREATE TRIGGER validate_insert_release_heads
        BEFORE INSERT ON release_heads
        WHEN NEW.current_fetch_observation_id IS NOT NULL
          OR NEW.current_status_observation_id IS NOT NULL
          OR NEW.current_admission_observation_id IS NOT NULL
        BEGIN SELECT RAISE(ABORT, 'release_heads must start empty'); END"""


def _subtype_insert_trigger_sql(table: str, observation_type: str) -> str:
    return (
        f"CREATE TRIGGER validate_parent_insert_{table} BEFORE INSERT ON {table} "
        "WHEN NOT EXISTS (SELECT 1 FROM observations "
        "WHERE observation_id = NEW.observation_id "
        f"AND observation_type = '{observation_type}') "
        f"BEGIN SELECT RAISE(ABORT, '{table} parent observation type mismatch'); END"
    )


_TRIGGER_SQL = {
    _trigger_name(table, operation): _trigger_sql(table, operation)
    for table in _IMMUTABLE_TABLES
    for operation in ("UPDATE", "DELETE")
}
_TRIGGER_SQL[_trigger_name("release_heads", "DELETE")] = _trigger_sql("release_heads", "DELETE")
_TRIGGER_SQL.update(
    {
        _conflict_trigger_name(table): _conflict_trigger_sql(table, predicate)
        for table, predicate in _INSERT_CONFLICT_PREDICATES.items()
    }
)
_TRIGGER_SQL["prevent_invalid_update_release_heads"] = _release_heads_update_trigger_sql()
_TRIGGER_SQL["validate_insert_release_heads"] = _release_heads_insert_trigger_sql()
for _subtype_table, _parent_type in {
    "artifact_fetch_observations": "artifact_fetch",
    "release_status_observations": "release_status",
    "release_admission_observations": "release_admission",
}.items():
    _TRIGGER_SQL[f"validate_parent_insert_{_subtype_table}"] = _subtype_insert_trigger_sql(
        _subtype_table, _parent_type
    )

_V3_TABLE_NAMES = {
    "run_release_status_confirmations",
    "run_release_status_confirmation_items",
    "strategy_run_confirmation_bindings",
    "legacy_v2_quarantined_run_pins",
}
_V3_INDEX_NAMES = {
    "idx_status_confirmations_authority_confirmed",
    "idx_status_confirmation_items_observation",
}
# Exact inventories of the previously released v2 schema.  v3 changes only by
# adding immutable confirmation/binding objects, so migration can preserve all
# existing rows and prove that it is upgrading the schema we actually shipped.
_V2_TABLE_SQL = {name: sql for name, sql in _TABLE_SQL.items() if name not in _V3_TABLE_NAMES}
_V2_INDEX_SQL = {name: sql for name, sql in _INDEX_SQL.items() if name not in _V3_INDEX_NAMES}
_V2_TRIGGER_SQL = {
    name: sql
    for name, sql in _TRIGGER_SQL.items()
    if not any(name.endswith(table) for table in _V3_TABLE_NAMES)
}

_V1_TABLES = {
    "releases",
    "release_status_observations",
    "release_admission_observations",
    "cache_objects",
    "release_artifacts",
    "release_pins",
    "pin_artifacts",
}
_V1_INDEX_NAMES = {
    "status_observations_release_idx",
    "admission_observations_release_idx",
    "release_artifacts_sha_idx",
    "release_pins_release_idx",
    "pin_artifacts_sha_idx",
}
_V1_COLUMN_SPECS: dict[str, tuple[tuple[str, str, int, int], ...]] = {
    "releases": (
        ("release_id", "TEXT", 1, 1),
        ("current_status_observation_id", "TEXT", 0, 0),
        ("current_admission_observation_id", "TEXT", 0, 0),
        ("created_at", "TEXT", 1, 0),
    ),
    "release_status_observations": (
        ("status_observation_id", "TEXT", 1, 1),
        ("release_id", "TEXT", 1, 0),
        ("status", "TEXT", 1, 0),
        ("input_ref_schema_version", "TEXT", 1, 0),
        ("dataset_release_id", "TEXT", 1, 0),
        ("knowledge_cutoff", "TEXT", 1, 0),
        ("release_manifest_schema_version", "TEXT", 1, 0),
        ("manifest_hash_algorithm", "TEXT", 1, 0),
        ("manifest_hash_value", "TEXT", 1, 0),
        ("observed_at", "TEXT", 1, 0),
        ("reason", "TEXT", 0, 0),
    ),
    "release_admission_observations": (
        ("admission_observation_id", "TEXT", 1, 1),
        ("release_id", "TEXT", 1, 0),
        ("status_observation_id", "TEXT", 1, 0),
        ("admission_status", "TEXT", 1, 0),
        ("observed_at", "TEXT", 1, 0),
        ("reason", "TEXT", 0, 0),
    ),
    "cache_objects": (
        ("sha256", "TEXT", 1, 1),
        ("size_bytes", "INTEGER", 1, 0),
        ("relative_path", "TEXT", 1, 0),
        ("stored_at", "TEXT", 1, 0),
    ),
    "release_artifacts": (
        ("release_id", "TEXT", 1, 1),
        ("artifact_id", "TEXT", 1, 2),
        ("sha256", "TEXT", 1, 0),
    ),
    "release_pins": (
        ("run_id", "TEXT", 1, 1),
        ("release_id", "TEXT", 1, 0),
        ("run_manifest_canonical", "BLOB", 1, 0),
        ("run_manifest_hash_algorithm", "TEXT", 1, 0),
        ("run_manifest_hash_value", "TEXT", 1, 0),
        ("canonical_profile_version", "TEXT", 1, 0),
        ("source_run_mode", "TEXT", 1, 0),
        ("input_ref_schema_version", "TEXT", 1, 0),
        ("dataset_release_id", "TEXT", 1, 0),
        ("knowledge_cutoff", "TEXT", 1, 0),
        ("release_manifest_schema_version", "TEXT", 1, 0),
        ("input_manifest_hash_algorithm", "TEXT", 1, 0),
        ("input_manifest_hash_value", "TEXT", 1, 0),
        ("receipt_hash_algorithm", "TEXT", 1, 0),
        ("receipt_hash_value", "TEXT", 1, 0),
        ("status_observation_id", "TEXT", 1, 0),
        ("admission_observation_id", "TEXT", 1, 0),
        ("pinned_at", "TEXT", 1, 0),
    ),
    "pin_artifacts": (
        ("run_id", "TEXT", 1, 1),
        ("release_id", "TEXT", 1, 0),
        ("artifact_id", "TEXT", 1, 2),
        ("sha256", "TEXT", 1, 0),
        ("size_bytes", "INTEGER", 1, 0),
    ),
}


def _normalized_sql(value: str) -> str:
    return " ".join(value.replace("\n", " ").split()).strip().rstrip(";")


class ReleaseCacheStore:
    """Durable v3 receipt/observation/confirmation/pin store with an immutable CAS."""

    def __init__(
        self,
        *,
        database_path: Path,
        cache_root: Path,
        soft_limit_bytes: int = DEFAULT_CACHE_SOFT_LIMIT_BYTES,
        clock: Clock | None = None,
        authority_policies: Iterable[CurrentStatusAuthorityPolicy] = (),
    ) -> None:
        if isinstance(soft_limit_bytes, bool) or not isinstance(soft_limit_bytes, int):
            raise TypeError("soft_limit_bytes must be an integer")
        if soft_limit_bytes < 0:
            raise ValueError("soft_limit_bytes must be non-negative")
        self.database_path = Path(database_path).absolute()
        self.cache_root = Path(cache_root).absolute()
        if self.database_path == self.cache_root or self.database_path.is_relative_to(
            self.cache_root
        ):
            raise ValueError("database_path must be outside cache_root")
        self.soft_limit_bytes = soft_limit_bytes
        self.clock = clock or SystemClock()
        if not isinstance(self.clock, Clock):
            raise TypeError("clock must implement Clock")
        policy_map: dict[tuple[str, str], CurrentStatusAuthorityPolicy] = {}
        for policy in authority_policies:
            if not isinstance(policy, CurrentStatusAuthorityPolicy):
                raise TypeError(
                    "authority_policies must contain CurrentStatusAuthorityPolicy values"
                )
            key = (policy.authority_id, policy.authority_contract_hash.value)
            if key in policy_map:
                raise ValueError("authority_policies contains a duplicate authority contract")
            policy_map[key] = policy
        self._authority_policies = MappingProxyType(policy_map)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        if _is_link_or_junction(self.database_path) or _is_link_or_junction(self.cache_root):
            raise CacheIntegrityError("database/cache roots must not be links or junctions")
        self._assert_safe_cache_path(self.cache_root)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.create_function("investsystem_head_write_allowed", 0, lambda: 0)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA recursive_triggers = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    @contextmanager
    def _head_update_gate(connection: sqlite3.Connection) -> Iterator[None]:
        connection.create_function("investsystem_head_write_allowed", 0, lambda: 1)
        try:
            yield
        finally:
            connection.create_function("investsystem_head_write_allowed", 0, lambda: 0)

    def _initialize(self) -> None:
        with self._connection() as connection:
            # Reject unknown/non-migratable databases before any persistent
            # journal-mode change.  The same checks run again under
            # BEGIN IMMEDIATE after WAL is established to close TOCTOU races.
            self._preflight_initialization(connection)
            # Establish WAL before taking the schema transaction.  Doing this
            # after COMMIT leaves a race in which another initializer can take
            # BEGIN IMMEDIATE and make the first initializer's journal-mode
            # switch fail with "database is locked".
            self._enable_wal(connection)
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                tables = self._user_tables(connection)
                if version == 0:
                    if tables:
                        raise StorageSchemaError("unversioned non-empty schema is not adoptable")
                    self._create_schema(connection)
                elif version == 1:
                    self._upgrade_empty_v1(connection, tables)
                elif version == 2:
                    self._upgrade_v2(connection)
                elif version != STORAGE_SCHEMA_VERSION:
                    raise StorageSchemaError(f"unsupported SQLite user_version: {version}")
                self._verify_schema(connection)
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _enable_wal(connection: sqlite3.Connection) -> None:
        """Enable WAL with bounded retry for concurrent first initialization."""

        attempts = 200
        for attempt in range(attempts):
            try:
                row = connection.execute("PRAGMA journal_mode = WAL").fetchone()
            except sqlite3.OperationalError as exc:
                code = getattr(exc, "sqlite_errorcode", None)
                base_code = code & 0xFF if isinstance(code, int) else None
                if base_code not in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    raise
                if attempt == attempts - 1:
                    raise StorageSchemaError(
                        "could not establish SQLite WAL mode after bounded retries"
                    ) from exc
                time.sleep(min(0.001 * (2 ** min(attempt, 6)), 0.05))
                continue
            if row is None or str(row[0]).casefold() != "wal":
                raise StorageSchemaError("SQLite WAL journal mode is required")
            return
        raise AssertionError("unreachable WAL retry state")

    @classmethod
    def _preflight_initialization(cls, connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN")
        try:
            # The first sqlite_master read establishes one consistent read
            # snapshot, so concurrent initialization cannot yield version=0
            # from before another commit and a v2 table inventory from after it.
            user_objects = connection.execute(
                """SELECT type, name FROM sqlite_master
                   WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name"""
            ).fetchall()
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            tables = cls._user_tables(connection)
            if version == 0:
                if user_objects:
                    raise StorageSchemaError("unversioned non-empty schema is not adoptable")
                return
            if version == 1:
                cls._validate_empty_v1(connection, tables)
                return
            if version == 2:
                cls._verify_schema_inventory(
                    connection,
                    version=2,
                    table_sql=_V2_TABLE_SQL,
                    index_sql=_V2_INDEX_SQL,
                    trigger_sql=_V2_TRIGGER_SQL,
                    label="storage v2",
                )
                return
            if version == STORAGE_SCHEMA_VERSION:
                cls._verify_schema(connection)
                return
            raise StorageSchemaError(f"unsupported SQLite user_version: {version}")
        finally:
            connection.rollback()

    @staticmethod
    def _user_tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @classmethod
    def _create_schema(cls, connection: sqlite3.Connection) -> None:
        for sql in _TABLE_SQL.values():
            connection.execute(sql)
        for sql in _INDEX_SQL.values():
            connection.execute(sql)
        for sql in _TRIGGER_SQL.values():
            connection.execute(sql)
        connection.execute(f"PRAGMA user_version = {STORAGE_SCHEMA_VERSION}")

    @classmethod
    def _upgrade_empty_v1(cls, connection: sqlite3.Connection, tables: set[str]) -> None:
        cls._validate_empty_v1(connection, tables)
        for table in (
            "pin_artifacts",
            "release_pins",
            "release_artifacts",
            "cache_objects",
            "release_admission_observations",
            "release_status_observations",
            "releases",
        ):
            connection.execute(f'DROP TABLE "{table}"')
        cls._create_schema(connection)

    def _upgrade_v2(self, connection: sqlite3.Connection) -> None:
        self._verify_schema_inventory(
            connection,
            version=2,
            table_sql=_V2_TABLE_SQL,
            index_sql=_V2_INDEX_SQL,
            trigger_sql=_V2_TRIGGER_SQL,
            label="storage v2",
        )
        for name in _V3_TABLE_NAMES:
            connection.execute(_TABLE_SQL[name])
        for name in _V3_INDEX_NAMES:
            connection.execute(_INDEX_SQL[name])
        connection.execute(
            """INSERT INTO legacy_v2_quarantined_run_pins (
                   run_id, source_schema_version, quarantined_at, reason
               )
               SELECT run_id, 2, ?, 'v2 pin predates run-scoped status confirmation'
               FROM strategy_run_pins""",
            (self._now(),),
        )
        for name, sql in _TRIGGER_SQL.items():
            if name not in _V2_TRIGGER_SQL:
                connection.execute(sql)
        connection.execute(f"PRAGMA user_version = {STORAGE_SCHEMA_VERSION}")

    @classmethod
    def _validate_empty_v1(cls, connection: sqlite3.Connection, tables: set[str]) -> None:
        if tables != _V1_TABLES:
            raise StorageSchemaError("v1 schema inventory is unknown; refusing migration")
        views_or_triggers = connection.execute(
            """SELECT name FROM sqlite_master
               WHERE type IN ('view','trigger') ORDER BY type, name"""
        ).fetchall()
        if views_or_triggers:
            raise StorageSchemaError("v1 schema has unexpected views or triggers")
        explicit_indexes = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            )
        }
        if explicit_indexes != _V1_INDEX_NAMES:
            raise StorageSchemaError("v1 explicit index inventory is unknown")
        for table, expected in _V1_COLUMN_SPECS.items():
            actual = tuple(
                (str(row[1]), str(row[2]).upper(), int(row[3]), int(row[5]))
                for row in connection.execute(f'PRAGMA table_info("{table}")')
            )
            if actual != expected:
                raise StorageSchemaError(f"v1 column inventory is unknown: {table}")
        if any(
            int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            for table in sorted(tables)
        ):
            raise StorageSchemaError(
                "non-empty v1 state lacks formal receipts and cannot be migrated safely"
            )

    @classmethod
    def _verify_schema(cls, connection: sqlite3.Connection) -> None:
        cls._verify_schema_inventory(
            connection,
            version=STORAGE_SCHEMA_VERSION,
            table_sql=_TABLE_SQL,
            index_sql=_INDEX_SQL,
            trigger_sql=_TRIGGER_SQL,
            label="storage v3",
        )

    @classmethod
    def _verify_schema_inventory(
        cls,
        connection: sqlite3.Connection,
        *,
        version: int,
        table_sql: dict[str, str],
        index_sql: dict[str, str],
        trigger_sql: dict[str, str],
        label: str,
    ) -> None:
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != version:
            raise StorageSchemaError("SQLite user_version changed unexpectedly")
        if cls._user_tables(connection) != set(table_sql):
            raise StorageSchemaError(f"SQLite table inventory does not match {label}")
        for name, expected in table_sql.items():
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
            if row is None or _normalized_sql(str(row[0])) != _normalized_sql(expected):
                raise StorageSchemaError(f"table definition mismatch: {name}")
        indexes = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
            )
        }
        if set(indexes) != set(index_sql) or any(
            _normalized_sql(indexes[name]) != _normalized_sql(sql)
            for name, sql in index_sql.items()
        ):
            raise StorageSchemaError(f"SQLite index inventory does not match {label}")
        triggers = {
            str(row[0]): str(row[1])
            for row in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
            )
        }
        if set(triggers) != set(trigger_sql) or any(
            _normalized_sql(triggers[name]) != _normalized_sql(sql)
            for name, sql in trigger_sql.items()
        ):
            raise StorageSchemaError(f"append-only trigger inventory does not match {label}")
        quick = connection.execute("PRAGMA quick_check").fetchall()
        if [str(row[0]) for row in quick] != ["ok"]:
            raise StorageSchemaError("SQLite quick_check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise StorageSchemaError("SQLite foreign_key_check failed")
        if (
            connection.execute("SELECT 1 FROM sqlite_master WHERE type='view' LIMIT 1").fetchone()
            is not None
        ):
            raise StorageSchemaError("SQLite view inventory must be empty")

    def _now(self) -> str:
        return format_utc(read_clock(self.clock, field_name="storage clock"))

    @property
    def schema_version(self) -> int:
        with self._connection() as connection:
            return int(connection.execute("PRAGMA user_version").fetchone()[0])

    @staticmethod
    def _relative_path(digest: str) -> Path:
        return Path("sha256") / digest[:2] / digest

    def _assert_safe_cache_path(self, path: Path) -> None:
        try:
            relative = path.absolute().relative_to(self.cache_root)
        except ValueError as exc:
            raise CacheIntegrityError("cache path escapes cache_root") from exc
        current = self.cache_root
        if _is_link_or_junction(current):
            raise CacheIntegrityError("cache_root became a symlink or junction")
        for component in relative.parts:
            current /= component
            if _is_link_or_junction(current):
                raise CacheIntegrityError(
                    f"cache path contains a symlink or junction: {relative.as_posix()}"
                )
        resolved = path.resolve(strict=False)
        if resolved != self.cache_root and not resolved.is_relative_to(self.cache_root):
            raise CacheIntegrityError("resolved cache path escapes cache_root")

    def _object_path(self, digest: str) -> Path:
        path = self.cache_root / self._relative_path(_require_digest(digest))
        self._assert_safe_cache_path(path)
        return path

    def _verified_read(self, path: Path, digest: str, size_bytes: int) -> bytes:
        self._assert_safe_cache_path(path)
        try:
            metadata = path.stat()
            if metadata.st_nlink > 1:
                raise CacheIntegrityError(
                    f"cached object has multiple hard links and is not independently owned: {digest}"
                )
            content = path.read_bytes()
        except CacheIntegrityError:
            raise
        except OSError as exc:
            raise CacheIntegrityError(f"cached object unavailable: {digest}") from exc
        if len(content) != size_bytes or sha256(content).hexdigest() != digest:
            raise CacheIntegrityError(f"cached object failed size/hash validation: {digest}")
        return content

    def _atomic_write(self, content: bytes, digest: str) -> Path:
        target = self._object_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._assert_safe_cache_path(target)
        if target.exists():
            self._verified_read(target, digest, len(content))
            return target
        temporary = target.parent / f".{digest}.{uuid4().hex}.tmp"
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            self._verified_read(temporary, digest, len(content))
            os.replace(temporary, target)
            self._verified_read(target, digest, len(content))
        finally:
            temporary.unlink(missing_ok=True)
        return target

    @staticmethod
    def _input_ref_identity(input_ref: StrategyInputRef) -> tuple[str, str, str, str, str]:
        return (
            input_ref.dataset_release_id,
            input_ref.schema_version,
            format_utc(input_ref.knowledge_cutoff),
            input_ref.release_manifest_schema_version,
            input_ref.manifest_hash.value,
        )

    def _ensure_release_identity(
        self,
        connection: sqlite3.Connection,
        input_ref: StrategyInputRef,
        *,
        persisted_at: str,
    ) -> None:
        expected = self._input_ref_identity(input_ref)
        row = connection.execute(
            """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                      manifest_schema_version, manifest_hash
               FROM release_identities WHERE release_id = ?""",
            (input_ref.dataset_release_id,),
        ).fetchone()
        if row is not None:
            if tuple(row) != expected:
                raise ImmutableMappingError("Release identity was remapped")
            return
        connection.execute(
            "INSERT INTO release_identities VALUES (?, ?, ?, ?, ?, ?)",
            (*expected, persisted_at),
        )
        connection.execute(
            "INSERT INTO release_heads VALUES (?, NULL, NULL, NULL)",
            (input_ref.dataset_release_id,),
        )

    def _ensure_cache_object(
        self,
        connection: sqlite3.Connection,
        *,
        digest: str,
        size_bytes: int,
        persisted_at: str,
    ) -> None:
        relative = self._relative_path(digest).as_posix()
        row = connection.execute(
            "SELECT size_bytes, relative_path FROM cache_objects WHERE sha256 = ?", (digest,)
        ).fetchone()
        if row is not None:
            if int(row["size_bytes"]) != size_bytes or str(row["relative_path"]) != relative:
                raise CacheIntegrityError("content-addressed object metadata conflict")
            self._verified_read(self._object_path(digest), digest, size_bytes)
            return
        self._verified_read(self._object_path(digest), digest, size_bytes)
        connection.execute(
            "INSERT INTO cache_objects VALUES (?, ?, ?, ?)",
            (digest, size_bytes, relative, persisted_at),
        )

    @staticmethod
    def _manifest_document(content: bytes, *, release_id: str) -> tuple[str, int]:
        # The adapter has already validated the provider's canonical profile
        # and semantic/self-excluding Manifest hash.  Storage remains
        # provider-neutral: it treats the exact non-empty bytes as an opaque
        # immutable document and records a separate physical SHA-256.
        if not content:
            raise CacheIntegrityError(f"Release Manifest for {release_id!r} is empty")
        return sha256(content).hexdigest(), len(content)

    @staticmethod
    def _load_canonical_object(
        content: bytes,
        *,
        document_hash: str,
        label: str,
    ) -> dict[str, Any]:
        if sha256(content).hexdigest() != document_hash:
            raise CacheIntegrityError(f"{label} canonical document hash changed")
        try:
            value = json.loads(content)
            if not isinstance(value, dict) or canonical_json_bytes(value) != content:
                raise ValueError("document is not a canonical object")
        except (TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
            raise CacheIntegrityError(f"{label} canonical document is invalid") from exc
        return cast(dict[str, Any], value)

    @staticmethod
    def _json_input_identity(value: Any) -> tuple[str, str, str, str, str]:
        if not isinstance(value, dict):
            raise TypeError
        manifest_hash = value["manifest_hash"]
        if not isinstance(manifest_hash, dict) or manifest_hash.get("algorithm") != "sha256":
            raise ValueError
        return (
            value["dataset_release_id"],
            value["schema_version"],
            value["knowledge_cutoff"],
            value["release_manifest_schema_version"],
            manifest_hash["value"],
        )

    def _verify_receipt_aggregate(
        self,
        connection: sqlite3.Connection,
        receipt_hash: str,
    ) -> sqlite3.Row:
        """Treat the canonical Receipt as authority and child rows as exact indexes."""

        row = connection.execute(
            """SELECT schema_version, consumer_contract_version, release_id,
                      canonical_document, canonical_document_hash
               FROM receipts WHERE receipt_hash=?""",
            (receipt_hash,),
        ).fetchone()
        if row is None:
            raise CacheIntegrityError("Receipt aggregate is missing")
        content = bytes(row["canonical_document"])
        document = self._load_canonical_object(
            content,
            document_hash=str(row["canonical_document_hash"]),
            label="Receipt",
        )
        try:
            hash_object = document["receipt_hash"]
            input_ref = document["strategy_input_ref"]
            artifacts = document["artifacts"]
            if not isinstance(hash_object, dict) or not isinstance(input_ref, dict):
                raise TypeError
            if hash_object != {"algorithm": "sha256", "value": receipt_hash}:
                raise ValueError
            identity = dict(document)
            del identity["receipt_hash"]
            if sha256(canonical_json_bytes(identity)).hexdigest() != receipt_hash:
                raise ValueError
            input_identity = self._json_input_identity(input_ref)
            release_id = input_identity[0]
            if (
                document["schema_version"] != row["schema_version"]
                or document["consumer_contract_version"] != row["consumer_contract_version"]
                or release_id != row["release_id"]
                or not isinstance(artifacts, list)
            ):
                raise ValueError
            expected_artifacts = tuple(
                sorted(
                    (
                        item["artifact_id"],
                        item["item_type"],
                        item["artifact_hash"]["value"],
                        item["size_bytes"],
                        item["record_count"],
                    )
                    for item in artifacts
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheIntegrityError("Receipt canonical identity is inconsistent") from exc
        persisted_identity = connection.execute(
            """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                      manifest_schema_version, manifest_hash
               FROM release_identities WHERE release_id=?""",
            (release_id,),
        ).fetchone()
        if persisted_identity is None or tuple(persisted_identity) != input_identity:
            raise CacheIntegrityError(
                "Receipt input reference differs from persisted Release identity"
            )
        actual_artifacts = tuple(
            tuple(item)
            for item in connection.execute(
                """SELECT artifact_id, item_type, sha256, size_bytes, record_count
                   FROM receipt_artifacts WHERE receipt_hash=? ORDER BY artifact_id""",
                (receipt_hash,),
            )
        )
        if actual_artifacts != expected_artifacts:
            raise CacheIntegrityError("Receipt artifact index differs from canonical Receipt")
        return cast(sqlite3.Row, row)

    def _verify_closure_aggregate(
        self,
        connection: sqlite3.Connection,
        closure_hash: str,
    ) -> sqlite3.Row:
        """Treat the canonical closure as authority and relational rows as exact indexes."""

        row = connection.execute(
            """SELECT schema_version, root_release_id, canonical_document,
                      canonical_document_hash
               FROM retention_closures WHERE closure_hash=?""",
            (closure_hash,),
        ).fetchone()
        if row is None:
            raise CacheIntegrityError("retention closure aggregate is missing")
        content = bytes(row["canonical_document"])
        document = self._load_canonical_object(
            content,
            document_hash=str(row["canonical_document_hash"]),
            label="retention closure",
        )
        try:
            hash_object = document["closure_hash"]
            root_input_ref = document["root_strategy_input_ref"]
            releases = document["releases"]
            if not isinstance(hash_object, dict) or not isinstance(root_input_ref, dict):
                raise TypeError
            if hash_object != {"algorithm": "sha256", "value": closure_hash}:
                raise ValueError
            identity = dict(document)
            del identity["closure_hash"]
            if sha256(canonical_json_bytes(identity)).hexdigest() != closure_hash:
                raise ValueError
            root_input_identity = self._json_input_identity(root_input_ref)
            root_release_id = root_input_identity[0]
            if (
                document["schema_version"] != row["schema_version"]
                or root_release_id != row["root_release_id"]
                or not isinstance(releases, list)
            ):
                raise ValueError
            node_identities = tuple(
                (self._json_input_identity(node["strategy_input_ref"]), node) for node in releases
            )
            expected_release_identities = tuple(
                sorted(identity for identity, _node in node_identities)
            )
            expected_releases = tuple(
                sorted(
                    (
                        node_identity[0],
                        node["manifest_document_hash"]["value"],
                        node["manifest_size_bytes"],
                    )
                    for node_identity, node in node_identities
                )
            )
            expected_dependencies = tuple(
                sorted(
                    (
                        closure_hash,
                        node["strategy_input_ref"]["dataset_release_id"],
                        dependency_id,
                    )
                    for node in releases
                    for dependency_id in node["dependency_release_ids"]
                )
            )
            expected_artifacts = tuple(
                sorted(
                    (
                        closure_hash,
                        node["strategy_input_ref"]["dataset_release_id"],
                        artifact["artifact_id"],
                        artifact["item_type"],
                        artifact["artifact_hash"]["value"],
                        artifact["size_bytes"],
                        artifact["record_count"],
                    )
                    for node in releases
                    for artifact in node["artifacts"]
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheIntegrityError(
                "retention closure canonical identity is inconsistent"
            ) from exc
        if root_input_identity not in expected_release_identities:
            raise CacheIntegrityError("closure root input reference differs from its root node")
        for expected_identity in expected_release_identities:
            persisted_identity = connection.execute(
                """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                          manifest_schema_version, manifest_hash
                   FROM release_identities WHERE release_id=?""",
                (expected_identity[0],),
            ).fetchone()
            if persisted_identity is None or tuple(persisted_identity) != expected_identity:
                raise CacheIntegrityError(
                    "closure input reference differs from persisted Release identity"
                )
        actual_releases = tuple(
            tuple(item)
            for item in connection.execute(
                """SELECT release_id, manifest_sha256, manifest_size_bytes
                   FROM closure_releases WHERE closure_hash=? ORDER BY release_id""",
                (closure_hash,),
            )
        )
        actual_dependencies = tuple(
            tuple(item)
            for item in connection.execute(
                """SELECT closure_hash, parent_release_id, dependency_release_id
                   FROM closure_dependencies WHERE closure_hash=?
                   ORDER BY parent_release_id, dependency_release_id""",
                (closure_hash,),
            )
        )
        actual_artifacts = tuple(
            tuple(item)
            for item in connection.execute(
                """SELECT closure_hash, release_id, artifact_id, item_type, sha256,
                          size_bytes, record_count
                   FROM closure_artifacts WHERE closure_hash=?
                   ORDER BY release_id, artifact_id""",
                (closure_hash,),
            )
        )
        if actual_releases != expected_releases:
            raise CacheIntegrityError("closure Release index differs from canonical closure")
        if actual_dependencies != expected_dependencies:
            raise CacheIntegrityError("closure dependency index differs from canonical closure")
        if actual_artifacts != expected_artifacts:
            raise CacheIntegrityError("closure artifact index differs from canonical closure")
        return cast(sqlite3.Row, row)

    @staticmethod
    def _json_sha256_value(value: Any, *, nullable: bool = False) -> str | None:
        if value is None and nullable:
            return None
        if not isinstance(value, dict) or value.get("algorithm") != "sha256":
            raise ValueError
        digest = value.get("value")
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise ValueError
        return digest

    def _verify_observation_aggregate(
        self,
        connection: sqlite3.Connection,
        observation_id: str,
    ) -> dict[str, Any]:
        """Verify canonical parent, subtype projection, and full Release identity."""

        row = connection.execute(
            """SELECT observation_type, release_id, observed_at, supersedes,
                      canonical_document, canonical_document_hash
               FROM observations WHERE observation_id=?""",
            (observation_id,),
        ).fetchone()
        if row is None:
            raise CacheIntegrityError("observation aggregate is missing")
        content = bytes(row["canonical_document"])
        if sha256(content).hexdigest() != str(row["canonical_document_hash"]):
            raise CacheIntegrityError("observation canonical document hash changed")
        try:
            observation = consumption_observation_from_canonical_bytes(content)
            document = observation.to_json_value()
            observation_type, _head_column = self._observation_kind(observation)
            input_identity = self._input_ref_identity(observation.strategy_input_ref)
            if (
                observation.schema_version != CONSUMPTION_OBSERVATION_SCHEMA_VERSION
                or observation.observation_id != observation_id
                or observation_type != row["observation_type"]
                or observation.release_id != row["release_id"]
                or format_utc(observation.observed_at) != row["observed_at"]
                or observation.supersedes != row["supersedes"]
                or input_identity[0] != row["release_id"]
            ):
                raise ValueError
            failure_reasons = observation.failure_reasons
            validation_result = (
                observation.schema_validation_result.value
                if isinstance(observation, (ArtifactFetchObservation, ReleaseStatusObservation))
                else None
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheIntegrityError("observation canonical parent is inconsistent") from exc
        persisted_identity = connection.execute(
            """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                      manifest_schema_version, manifest_hash
               FROM release_identities WHERE release_id=?""",
            (input_identity[0],),
        ).fetchone()
        if persisted_identity is None or tuple(persisted_identity) != input_identity:
            raise CacheIntegrityError(
                "observation input reference differs from persisted Release identity"
            )

        subtype_tables = {
            "artifact_fetch": "artifact_fetch_observations",
            "release_status": "release_status_observations",
            "release_admission": "release_admission_observations",
        }
        observation_type = str(row["observation_type"])
        if observation_type not in subtype_tables:
            raise CacheIntegrityError("observation type is unknown")
        subtype_presence = {
            name: connection.execute(
                f"SELECT 1 FROM {table} WHERE observation_id=?", (observation_id,)
            ).fetchone()
            is not None
            for name, table in subtype_tables.items()
        }
        if subtype_presence != {name: name == observation_type for name in subtype_tables}:
            raise CacheIntegrityError("observation subtype projection is not exact")

        try:
            if observation_type == "artifact_fetch":
                subtype = connection.execute(
                    """SELECT validation_result, receipt_hash
                       FROM artifact_fetch_observations WHERE observation_id=?""",
                    (observation_id,),
                ).fetchone()
                receipt_hash = self._json_sha256_value(document["receipt_hash"], nullable=True)
                if subtype is None or (subtype["validation_result"], subtype["receipt_hash"]) != (
                    validation_result,
                    receipt_hash,
                ):
                    raise ValueError
                artifact_ids = document["artifact_ids"]
                if not isinstance(artifact_ids, list):
                    raise ValueError
                if validation_result == "passed":
                    if receipt_hash is None or failure_reasons:
                        raise ValueError
                    self._verify_receipt_aggregate(connection, receipt_hash)
                    persisted_artifact_ids = tuple(
                        str(item[0])
                        for item in connection.execute(
                            """SELECT artifact_id FROM receipt_artifacts
                               WHERE receipt_hash=? ORDER BY artifact_id""",
                            (receipt_hash,),
                        )
                    )
                    if tuple(artifact_ids) != persisted_artifact_ids:
                        raise ValueError
                elif receipt_hash is not None or artifact_ids or not failure_reasons:
                    raise ValueError
            elif observation_type == "release_status":
                subtype = connection.execute(
                    """SELECT validation_result, status, status_event_id,
                              status_event_hash, previous_status_event_hash,
                              status_sequence, status_recorded_at
                       FROM release_status_observations WHERE observation_id=?""",
                    (observation_id,),
                ).fetchone()
                expected_status = (
                    validation_result,
                    document["status"],
                    document["status_event_id"],
                    self._json_sha256_value(document["status_event_hash"], nullable=True),
                    self._json_sha256_value(document["previous_status_event_hash"], nullable=True),
                    document["status_sequence"],
                    document["status_recorded_at"],
                )
                if subtype is None or tuple(subtype) != expected_status:
                    raise ValueError
                event_values = expected_status[1:]
                if validation_result == "passed":
                    if (
                        any(
                            value is None
                            for value in (
                                event_values[0],
                                event_values[1],
                                event_values[2],
                                event_values[4],
                                event_values[5],
                            )
                        )
                        or failure_reasons
                    ):
                        raise ValueError
                    sequence = event_values[4]
                    if not isinstance(sequence, int) or isinstance(sequence, bool):
                        raise ValueError
                    if sequence == 1:
                        if event_values[3] is not None or event_values[0] != "building":
                            raise ValueError
                    elif sequence < 2 or event_values[3] is None:
                        raise ValueError
                elif any(value is not None for value in event_values) or not failure_reasons:
                    raise ValueError
            else:
                subtype = connection.execute(
                    """SELECT status_observation_id, admission_status
                       FROM release_admission_observations WHERE observation_id=?""",
                    (observation_id,),
                ).fetchone()
                expected_admission = (
                    document["status_observation_id"],
                    document["admission_status"],
                )
                if subtype is None or tuple(subtype) != expected_admission:
                    raise ValueError
                if (document["admission_status"] == "authorized") == bool(failure_reasons):
                    raise ValueError
        except (KeyError, TypeError, ValueError) as exc:
            raise CacheIntegrityError("observation subtype differs from canonical parent") from exc
        return document

    def _verify_observation_chain(
        self,
        connection: sqlite3.Connection,
        *,
        release_id: str,
        observation_type: str,
        expected_head_id: str | None,
    ) -> tuple[dict[str, Any], ...]:
        """Rebuild one append-only chain and revalidate its domain semantics."""

        rows = connection.execute(
            """SELECT observation_id, supersedes, observed_at
               FROM observations WHERE release_id=? AND observation_type=?""",
            (release_id, observation_type),
        ).fetchall()
        if not rows:
            if expected_head_id is not None:
                raise CacheIntegrityError("observation head points to an empty chain")
            return ()
        if expected_head_id is None:
            raise CacheIntegrityError("observation chain has no current head")
        by_id = {str(row["observation_id"]): row for row in rows}
        roots = [row for row in rows if row["supersedes"] is None]
        if len(roots) != 1:
            raise CacheIntegrityError("observation chain must have exactly one root")
        successor_by_id: dict[str, str] = {}
        for row in rows:
            predecessor = row["supersedes"]
            if predecessor is None:
                continue
            predecessor_id = str(predecessor)
            if predecessor_id not in by_id or predecessor_id in successor_by_id:
                raise CacheIntegrityError("observation chain is forked or disconnected")
            successor_by_id[predecessor_id] = str(row["observation_id"])
        ordered_ids: list[str] = []
        current_id = str(roots[0]["observation_id"])
        while True:
            if current_id in ordered_ids:
                raise CacheIntegrityError("observation chain contains a cycle")
            ordered_ids.append(current_id)
            successor = successor_by_id.get(current_id)
            if successor is None:
                break
            current_id = successor
        if len(ordered_ids) != len(rows) or ordered_ids[-1] != expected_head_id:
            raise CacheIntegrityError("observation head is not the exact chain tail")
        documents = tuple(
            self._verify_observation_aggregate(connection, observation_id)
            for observation_id in ordered_ids
        )
        if any(
            str(documents[index]["observed_at"]) < str(documents[index - 1]["observed_at"])
            for index in range(1, len(documents))
        ):
            raise CacheIntegrityError("observation chain time moved backwards")

        if observation_type == "release_status":
            latest_event: tuple[str, str, str, str | None, int, str] | None = None
            identities: dict[str, tuple[str, str, str, str | None, int, str]] = {}
            hashes: dict[str, tuple[str, str, str, str | None, int, str]] = {}
            for document in documents:
                if document["schema_validation_result"] != "passed":
                    continue
                event = (
                    str(document["status"]),
                    str(document["status_event_id"]),
                    cast(str, self._json_sha256_value(document["status_event_hash"])),
                    self._json_sha256_value(document["previous_status_event_hash"], nullable=True),
                    int(document["status_sequence"]),
                    str(document["status_recorded_at"]),
                )
                prior_for_id = identities.get(event[1])
                prior_for_hash = hashes.get(event[2])
                if (prior_for_id is not None and prior_for_id != event) or (
                    prior_for_hash is not None and prior_for_hash != event
                ):
                    raise CacheIntegrityError("provider status event identity was remapped")
                identities[event[1]] = event
                hashes[event[2]] = event
                if latest_event is None:
                    if event[4] != 1 or event[0] != "building" or event[3] is not None:
                        raise CacheIntegrityError(
                            "provider status chain must start at building sequence 1"
                        )
                elif event == latest_event:
                    continue
                else:
                    if latest_event[0] == "withdrawn":
                        raise CacheIntegrityError("withdrawn provider status is terminal")
                    if event[4] != latest_event[4] + 1:
                        raise CacheIntegrityError("provider status sequence is not contiguous")
                    if event[3] != latest_event[2]:
                        raise CacheIntegrityError("provider status previous hash breaks the chain")
                    if event[5] < latest_event[5]:
                        raise CacheIntegrityError("provider status recorded_at moved backwards")
                latest_event = event
        elif observation_type == "release_admission":
            for document in documents:
                status_id = str(document["status_observation_id"])
                status = self._verify_observation_aggregate(connection, status_id)
                if (
                    status["release_id"] != release_id
                    or status["observation_type"] != "release_status"
                    or str(document["observed_at"]) < str(status["observed_at"])
                ):
                    raise CacheIntegrityError("admission does not target its Release status")
                if document["admission_status"] == "authorized" and not (
                    status["schema_validation_result"] == "passed"
                    and status["status"] == "published"
                ):
                    raise CacheIntegrityError("invalid status was locally authorized")
        return documents

    def _verify_release_observation_chains(
        self,
        connection: sqlite3.Connection,
        release_id: str,
    ) -> sqlite3.Row:
        heads = connection.execute(
            "SELECT * FROM release_heads WHERE release_id=?", (release_id,)
        ).fetchone()
        if heads is None:
            raise CacheIntegrityError("Release identity has no observation heads row")
        for observation_type, column in (
            ("artifact_fetch", "current_fetch_observation_id"),
            ("release_status", "current_status_observation_id"),
            ("release_admission", "current_admission_observation_id"),
        ):
            self._verify_observation_chain(
                connection,
                release_id=release_id,
                observation_type=observation_type,
                expected_head_id=(str(heads[column]) if heads[column] is not None else None),
            )
        return cast(sqlite3.Row, heads)

    @staticmethod
    def _unique_payloads[T](
        values: Iterable[T],
        *,
        expected_type: type[T],
        key: Any,
        field_name: str,
    ) -> dict[Any, T]:
        if isinstance(values, (bytes, str)):
            raise TypeError(f"{field_name} must be an iterable of payload objects")
        result: dict[Any, T] = {}
        for value in values:
            if not isinstance(value, expected_type):
                raise TypeError(f"{field_name} contains an unexpected payload type")
            payload_key = key(value)
            if payload_key in result:
                raise ValueError(f"{field_name} contains duplicate payload identities")
            result[payload_key] = value
        return result

    def record_verified_consumption(
        self,
        receipt: ArtifactConsumptionReceipt,
        retention_closure: ReleaseRetentionClosure,
        artifact_payloads: Iterable[ArtifactPayload],
        manifest_payloads: Iterable[ReleaseManifestPayload],
    ) -> bool:
        """Persist one verified root receipt and its exact transitive closure.

        Payload bytes are validated and placed in the CAS before the metadata
        transaction.  A failed metadata transaction can therefore leave only a
        harmless, unregistered content-addressed orphan; it cannot expose a
        partial receipt or closure.
        """

        if not isinstance(receipt, ArtifactConsumptionReceipt):
            raise TypeError("receipt must be an ArtifactConsumptionReceipt")
        if not isinstance(retention_closure, ReleaseRetentionClosure):
            raise TypeError("retention_closure must be a ReleaseRetentionClosure")
        if receipt.strategy_input_ref != retention_closure.root_strategy_input_ref:
            raise ValueError("receipt and retention closure root identities differ")

        root = retention_closure.release(receipt.strategy_input_ref.dataset_release_id)
        receipt_descriptors = {
            item.artifact_id: (
                item.item_type,
                item.artifact_hash.value,
                item.size_bytes,
                item.record_count,
            )
            for item in receipt.artifacts
        }
        root_descriptors = {
            item.artifact_id: (
                item.item_type,
                item.artifact_hash.value,
                item.size_bytes,
                item.record_count,
            )
            for item in root.artifacts
        }
        if receipt_descriptors != root_descriptors:
            raise ValueError("receipt artifacts must exactly equal root closure artifacts")

        artifacts = self._unique_payloads(
            artifact_payloads,
            expected_type=ArtifactPayload,
            key=lambda value: (value.release_id, value.artifact_id),
            field_name="artifact_payloads",
        )
        expected_artifacts = {
            (node.release_id, descriptor.artifact_id): descriptor
            for node in retention_closure.releases
            for descriptor in node.artifacts
        }
        if set(artifacts) != set(expected_artifacts):
            raise ValueError("artifact payloads must exactly cover the retention closure")
        object_specs: dict[str, tuple[bytes, int]] = {}
        for key, descriptor in expected_artifacts.items():
            payload = artifacts[key]
            digest = sha256(payload.content).hexdigest()
            if (
                digest != descriptor.artifact_hash.value
                or len(payload.content) != descriptor.size_bytes
            ):
                raise CacheIntegrityError(f"artifact payload failed declared hash/size: {key!r}")
            object_specs.setdefault(digest, (payload.content, len(payload.content)))
            if object_specs[digest][0] != payload.content:
                raise CacheIntegrityError("SHA-256 collision detected between payload bytes")

        manifests = self._unique_payloads(
            manifest_payloads,
            expected_type=ReleaseManifestPayload,
            key=lambda value: value.release_id,
            field_name="manifest_payloads",
        )
        expected_release_ids = {node.release_id for node in retention_closure.releases}
        if set(manifests) != expected_release_ids:
            raise ValueError("manifest payloads must exactly cover the retention closure")
        manifest_specs: dict[str, tuple[str, int]] = {}
        for release_id, manifest_payload in manifests.items():
            digest, size_bytes = self._manifest_document(
                manifest_payload.content, release_id=release_id
            )
            node = retention_closure.release(release_id)
            if (
                digest != node.manifest_document_hash.value
                or size_bytes != node.manifest_size_bytes
            ):
                raise CacheIntegrityError(
                    f"Release Manifest payload failed committed hash/size: {release_id!r}"
                )
            manifest_specs[release_id] = (digest, size_bytes)
            object_specs.setdefault(digest, (manifest_payload.content, size_bytes))
            if object_specs[digest][0] != manifest_payload.content:
                raise CacheIntegrityError("SHA-256 collision detected between payload bytes")

        # Files are immutable content-addressed objects.  Metadata becomes
        # visible only in the transaction below.
        for digest, (content, _size) in object_specs.items():
            self._atomic_write(content, digest)

        receipt_document = receipt.to_canonical_bytes()
        receipt_document_hash = sha256(receipt_document).hexdigest()
        closure_document = retention_closure.to_canonical_bytes()
        closure_document_hash = sha256(closure_document).hexdigest()
        receipt_hash = receipt.receipt_hash.value
        closure_hash = retention_closure.closure_hash.value

        with self._write() as connection:
            persisted_at = self._now()
            for node in retention_closure.releases:
                self._ensure_release_identity(
                    connection, node.strategy_input_ref, persisted_at=persisted_at
                )
            for digest, (_content, size_bytes) in object_specs.items():
                self._ensure_cache_object(
                    connection,
                    digest=digest,
                    size_bytes=size_bytes,
                    persisted_at=persisted_at,
                )

            existing_receipt = connection.execute(
                "SELECT canonical_document, canonical_document_hash FROM receipts WHERE receipt_hash=?",
                (receipt_hash,),
            ).fetchone()
            contract_receipt = connection.execute(
                """SELECT receipt_hash FROM receipts
                   WHERE release_id=? AND consumer_contract_version=?""",
                (root.release_id, receipt.consumer_contract_version),
            ).fetchone()
            if (
                contract_receipt is not None
                and str(contract_receipt["receipt_hash"]) != receipt_hash
            ):
                raise ImmutableMappingError(
                    "Release/consumer-contract receipt identity was remapped"
                )
            if existing_receipt is not None:
                if (
                    bytes(existing_receipt["canonical_document"]) != receipt_document
                    or str(existing_receipt["canonical_document_hash"]) != receipt_document_hash
                ):
                    raise ImmutableMappingError("receipt hash was remapped")
                mapping = connection.execute(
                    "SELECT closure_hash FROM receipt_closures WHERE receipt_hash=?",
                    (receipt_hash,),
                ).fetchone()
                if mapping is None or str(mapping["closure_hash"]) != closure_hash:
                    raise ImmutableMappingError("receipt retention closure was remapped")
                stored_closure = connection.execute(
                    """SELECT canonical_document, canonical_document_hash
                       FROM retention_closures WHERE closure_hash=?""",
                    (closure_hash,),
                ).fetchone()
                if stored_closure is None or (
                    bytes(stored_closure["canonical_document"]) != closure_document
                    or str(stored_closure["canonical_document_hash"]) != closure_document_hash
                ):
                    raise ImmutableMappingError("retention closure hash was remapped")
                for node in retention_closure.releases:
                    manifest_digest, manifest_size = manifest_specs[node.release_id]
                    manifest_row = connection.execute(
                        """SELECT sha256, size_bytes, document_sha256
                           FROM release_manifests WHERE release_id=?""",
                        (node.release_id,),
                    ).fetchone()
                    if manifest_row is None or tuple(manifest_row) != (
                        manifest_digest,
                        manifest_size,
                        manifest_digest,
                    ):
                        raise ImmutableMappingError("Release Manifest snapshot was remapped")
                    for descriptor in node.artifacts:
                        mapped = connection.execute(
                            """SELECT item_type, sha256, size_bytes, record_count
                               FROM release_artifacts
                               WHERE release_id=? AND artifact_id=?""",
                            (node.release_id, descriptor.artifact_id),
                        ).fetchone()
                        if mapped is None or tuple(mapped) != (
                            descriptor.item_type,
                            descriptor.artifact_hash.value,
                            descriptor.size_bytes,
                            descriptor.record_count,
                        ):
                            raise ImmutableMappingError("Release artifact identity was remapped")
                self._verify_receipt_aggregate(connection, receipt_hash)
                self._verify_closure_aggregate(connection, closure_hash)
                return False

            existing_closure = connection.execute(
                """SELECT canonical_document, canonical_document_hash
                   FROM retention_closures WHERE closure_hash=?""",
                (closure_hash,),
            ).fetchone()
            if existing_closure is not None and (
                bytes(existing_closure["canonical_document"]) != closure_document
                or str(existing_closure["canonical_document_hash"]) != closure_document_hash
            ):
                raise ImmutableMappingError("retention closure hash was remapped")
            if existing_closure is not None:
                self._verify_closure_aggregate(connection, closure_hash)

            for node in retention_closure.releases:
                manifest_digest, manifest_size = manifest_specs[node.release_id]
                manifest_row = connection.execute(
                    "SELECT sha256, size_bytes, document_sha256 FROM release_manifests WHERE release_id=?",
                    (node.release_id,),
                ).fetchone()
                manifest_expected = (manifest_digest, manifest_size, manifest_digest)
                if manifest_row is not None:
                    if tuple(manifest_row) != manifest_expected:
                        raise ImmutableMappingError("Release Manifest snapshot was remapped")
                else:
                    connection.execute(
                        "INSERT INTO release_manifests VALUES (?, ?, ?, ?, ?)",
                        (node.release_id, *manifest_expected, persisted_at),
                    )
                for descriptor in node.artifacts:
                    expected = (
                        descriptor.item_type,
                        descriptor.artifact_hash.value,
                        descriptor.size_bytes,
                        descriptor.record_count,
                    )
                    mapped = connection.execute(
                        """SELECT item_type, sha256, size_bytes, record_count
                           FROM release_artifacts WHERE release_id=? AND artifact_id=?""",
                        (node.release_id, descriptor.artifact_id),
                    ).fetchone()
                    if mapped is not None:
                        if tuple(mapped) != expected:
                            raise ImmutableMappingError("Release artifact identity was remapped")
                    else:
                        connection.execute(
                            "INSERT INTO release_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                node.release_id,
                                descriptor.artifact_id,
                                *expected,
                                persisted_at,
                            ),
                        )

            if existing_closure is None:
                connection.execute(
                    "INSERT INTO retention_closures VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        closure_hash,
                        retention_closure.schema_version,
                        root.release_id,
                        closure_document,
                        closure_document_hash,
                        persisted_at,
                    ),
                )
                for node in retention_closure.releases:
                    connection.execute(
                        "INSERT INTO closure_releases VALUES (?, ?, ?, ?)",
                        (
                            closure_hash,
                            node.release_id,
                            node.manifest_document_hash.value,
                            node.manifest_size_bytes,
                        ),
                    )
                for node in retention_closure.releases:
                    for dependency_id in node.dependency_release_ids:
                        connection.execute(
                            "INSERT INTO closure_dependencies VALUES (?, ?, ?)",
                            (closure_hash, node.release_id, dependency_id),
                        )
                    for descriptor in node.artifacts:
                        connection.execute(
                            "INSERT INTO closure_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                closure_hash,
                                node.release_id,
                                descriptor.artifact_id,
                                descriptor.item_type,
                                descriptor.artifact_hash.value,
                                descriptor.size_bytes,
                                descriptor.record_count,
                            ),
                        )

            connection.execute(
                "INSERT INTO receipts VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    receipt_hash,
                    receipt.schema_version,
                    receipt.consumer_contract_version,
                    root.release_id,
                    receipt_document,
                    receipt_document_hash,
                    persisted_at,
                ),
            )
            for receipt_descriptor in receipt.artifacts:
                connection.execute(
                    "INSERT INTO receipt_artifacts VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        receipt_hash,
                        receipt_descriptor.artifact_id,
                        receipt_descriptor.item_type,
                        receipt_descriptor.artifact_hash.value,
                        receipt_descriptor.size_bytes,
                        receipt_descriptor.record_count,
                    ),
                )
            connection.execute(
                "INSERT INTO receipt_closures VALUES (?, ?)",
                (receipt_hash, closure_hash),
            )
            return True

    @staticmethod
    def _observation_kind(
        observation: (
            ArtifactFetchObservation | ReleaseStatusObservation | ReleaseAdmissionObservation
        ),
    ) -> tuple[str, str]:
        if isinstance(observation, ArtifactFetchObservation):
            return "artifact_fetch", "current_fetch_observation_id"
        if isinstance(observation, ReleaseStatusObservation):
            return "release_status", "current_status_observation_id"
        if isinstance(observation, ReleaseAdmissionObservation):
            return "release_admission", "current_admission_observation_id"
        raise TypeError("observation must be an InvestSystem consumption observation")

    def append_observation(
        self,
        observation: (
            ArtifactFetchObservation | ReleaseStatusObservation | ReleaseAdmissionObservation
        ),
    ) -> bool:
        """Append one immutable observation and advance exactly one linear head."""

        observation_type, head_column = self._observation_kind(observation)
        canonical = observation.to_canonical_bytes()
        document_hash = sha256(canonical).hexdigest()
        with self._write() as connection:
            persisted_at = self._now()
            if format_utc(observation.observed_at) > persisted_at:
                raise ReleaseAccessError(
                    "observation time cannot be later than its persistence time"
                )
            self._ensure_release_identity(
                connection, observation.strategy_input_ref, persisted_at=persisted_at
            )
            existing = connection.execute(
                """SELECT observation_type, release_id, canonical_document,
                          canonical_document_hash
                   FROM observations WHERE observation_id=?""",
                (observation.observation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    str(existing["observation_type"]) != observation_type
                    or str(existing["release_id"]) != observation.release_id
                    or bytes(existing["canonical_document"]) != canonical
                    or str(existing["canonical_document_hash"]) != document_hash
                ):
                    raise ImmutableMappingError("observation identifier was remapped")
                self._verify_observation_aggregate(connection, observation.observation_id)
                self._verify_release_observation_chains(connection, observation.release_id)
                return False

            heads = connection.execute(
                "SELECT * FROM release_heads WHERE release_id=?", (observation.release_id,)
            ).fetchone()
            if heads is None:
                raise StorageSchemaError("Release identity has no observation heads row")
            current_id = heads[head_column]
            self._verify_observation_chain(
                connection,
                release_id=observation.release_id,
                observation_type=observation_type,
                expected_head_id=str(current_id) if current_id is not None else None,
            )
            if observation.supersedes != current_id:
                raise ImmutableMappingError(
                    f"{observation_type} must supersede its exact current head"
                )
            if current_id is not None:
                current = connection.execute(
                    "SELECT observed_at FROM observations WHERE observation_id=?",
                    (current_id,),
                ).fetchone()
                if current is None:
                    raise StorageSchemaError("observation head points to missing observation")
                if format_utc(observation.observed_at) < str(current["observed_at"]):
                    raise ReleaseAccessError("observation time cannot move backwards")

            if isinstance(observation, ArtifactFetchObservation):
                self._validate_fetch_observation(connection, observation)
            elif isinstance(observation, ReleaseStatusObservation):
                self._validate_status_observation(connection, observation)
            else:
                self._validate_admission_observation(connection, observation)

            connection.execute(
                "INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    observation.observation_id,
                    observation_type,
                    observation.release_id,
                    format_utc(observation.observed_at),
                    observation.supersedes,
                    canonical,
                    document_hash,
                    persisted_at,
                ),
            )
            if isinstance(observation, ArtifactFetchObservation):
                connection.execute(
                    "INSERT INTO artifact_fetch_observations VALUES (?, ?, ?)",
                    (
                        observation.observation_id,
                        observation.schema_validation_result.value,
                        observation.receipt_hash.value
                        if observation.receipt_hash is not None
                        else None,
                    ),
                )
            elif isinstance(observation, ReleaseStatusObservation):
                connection.execute(
                    "INSERT INTO release_status_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        observation.observation_id,
                        observation.schema_validation_result.value,
                        observation.status.value if observation.status is not None else None,
                        observation.status_event_id,
                        observation.status_event_hash.value
                        if observation.status_event_hash is not None
                        else None,
                        observation.previous_status_event_hash.value
                        if observation.previous_status_event_hash is not None
                        else None,
                        observation.status_sequence,
                        format_utc(observation.status_recorded_at)
                        if observation.status_recorded_at is not None
                        else None,
                    ),
                )
            else:
                connection.execute(
                    "INSERT INTO release_admission_observations VALUES (?, ?, ?)",
                    (
                        observation.observation_id,
                        observation.status_observation_id,
                        observation.admission_status.value,
                    ),
                )
            with self._head_update_gate(connection):
                if isinstance(observation, ReleaseStatusObservation):
                    connection.execute(
                        """UPDATE release_heads
                           SET current_status_observation_id=?
                           WHERE release_id=?""",
                        (observation.observation_id, observation.release_id),
                    )
                else:
                    connection.execute(
                        f"UPDATE release_heads SET {head_column}=? WHERE release_id=?",
                        (observation.observation_id, observation.release_id),
                    )
            return True

    def _validate_fetch_observation(
        self,
        connection: sqlite3.Connection,
        observation: ArtifactFetchObservation,
    ) -> None:
        if observation.schema_validation_result is not SchemaValidationResult.PASSED:
            return
        if observation.receipt_hash is None:
            raise ReleaseAccessError("passed fetch observation lacks a receipt")
        receipt = connection.execute(
            "SELECT release_id FROM receipts WHERE receipt_hash=?",
            (observation.receipt_hash.value,),
        ).fetchone()
        if receipt is None or str(receipt["release_id"]) != observation.release_id:
            raise ReleaseAccessError("fetch receipt is unavailable or belongs to another Release")
        self._verify_receipt_aggregate(connection, observation.receipt_hash.value)
        artifact_ids = tuple(
            str(row[0])
            for row in connection.execute(
                "SELECT artifact_id FROM receipt_artifacts WHERE receipt_hash=? ORDER BY artifact_id",
                (observation.receipt_hash.value,),
            )
        )
        if artifact_ids != observation.artifact_ids:
            raise ReleaseAccessError("fetch observation artifact IDs differ from its receipt")

    @staticmethod
    def _validate_status_observation(
        connection: sqlite3.Connection, observation: ReleaseStatusObservation
    ) -> None:
        if observation.schema_validation_result is not SchemaValidationResult.PASSED:
            return
        if (
            observation.status is None
            or observation.status_event_id is None
            or observation.status_event_hash is None
            or observation.status_sequence is None
            or observation.status_recorded_at is None
        ):
            raise ReleaseAccessError("passed status observation lacks validated event fields")
        event_matches = connection.execute(
            """SELECT status.status, status.status_event_id,
                      status.status_event_hash, status.previous_status_event_hash,
                      status.status_sequence,
                      status.status_recorded_at
               FROM release_status_observations AS status
               JOIN observations AS observation USING(observation_id)
               WHERE observation.release_id=? AND status.validation_result='passed'
                 AND (status.status_event_id=? OR status.status_event_hash=?)
               ORDER BY status.status_sequence DESC""",
            (
                observation.release_id,
                observation.status_event_id,
                observation.status_event_hash.value,
            ),
        ).fetchall()
        incoming_event = (
            observation.status.value,
            observation.status_event_id,
            observation.status_event_hash.value,
            observation.previous_status_event_hash.value
            if observation.previous_status_event_hash is not None
            else None,
            observation.status_sequence,
            format_utc(observation.status_recorded_at),
        )
        if any(tuple(row) != incoming_event for row in event_matches):
            raise ReleaseAccessError("provider status event identity was remapped")
        prior = connection.execute(
            """SELECT status.status, status.status_event_id, status.status_event_hash,
                      status.previous_status_event_hash, status.status_sequence,
                      status.status_recorded_at
               FROM release_status_observations AS status
               JOIN observations AS observation USING(observation_id)
               WHERE observation.release_id=? AND status.validation_result='passed'
               ORDER BY status.status_sequence DESC, observation.observed_at DESC LIMIT 1""",
            (observation.release_id,),
        ).fetchone()
        if prior is None:
            if observation.status_sequence != 1:
                raise ReleaseAccessError(
                    "the first persisted provider status event must have sequence 1"
                )
            return
        prior_event = (
            str(prior["status"]),
            str(prior["status_event_id"]),
            str(prior["status_event_hash"]),
            str(prior["previous_status_event_hash"])
            if prior["previous_status_event_hash"] is not None
            else None,
            int(prior["status_sequence"]),
            str(prior["status_recorded_at"]),
        )
        if observation.status_sequence < int(prior["status_sequence"]):
            raise ReleaseAccessError("provider status sequence cannot move backwards")
        if observation.status_sequence == int(prior["status_sequence"]):
            if incoming_event != prior_event:
                raise ReleaseAccessError(
                    "a provider status sequence may repeat only for the exact latest event"
                )
            return
        if str(prior["status"]) == ProviderReleaseStatus.WITHDRAWN.value:
            raise ReleaseAccessError("withdrawn provider status is terminal")
        if observation.status_sequence != int(prior["status_sequence"]) + 1:
            raise ReleaseAccessError("provider status events must form a contiguous sequence")
        if (
            observation.previous_status_event_hash is None
            or observation.previous_status_event_hash.value != str(prior["status_event_hash"])
        ):
            raise ReleaseAccessError("provider status event previous hash breaks the chain")
        if format_utc(observation.status_recorded_at) < str(prior["status_recorded_at"]):
            raise ReleaseAccessError("provider status recorded_at cannot move backwards")

    def _validate_admission_observation(
        self,
        connection: sqlite3.Connection,
        observation: ReleaseAdmissionObservation,
    ) -> None:
        current_status = connection.execute(
            "SELECT current_status_observation_id FROM release_heads WHERE release_id=?",
            (observation.release_id,),
        ).fetchone()
        if current_status is None:
            raise ReleaseAccessError("admission Release has no observation heads row")
        current_status_id = current_status["current_status_observation_id"]
        self._verify_observation_chain(
            connection,
            release_id=observation.release_id,
            observation_type="release_status",
            expected_head_id=str(current_status_id) if current_status_id is not None else None,
        )
        if current_status_id != observation.status_observation_id:
            raise ReleaseAccessError("admission must target the exact current status observation")
        status = connection.execute(
            """SELECT validation_result, status FROM release_status_observations
               WHERE observation_id=?""",
            (observation.status_observation_id,),
        ).fetchone()
        if status is None:
            raise ReleaseAccessError("admission status observation does not exist")
        status_time = connection.execute(
            "SELECT observed_at FROM observations WHERE observation_id=?",
            (observation.status_observation_id,),
        ).fetchone()
        if status_time is None or format_utc(observation.observed_at) < str(
            status_time["observed_at"]
        ):
            raise ReleaseAccessError("admission cannot predate its status observation")
        if observation.admission_status is ReleaseAdmissionStatus.AUTHORIZED and not (
            str(status["validation_result"]) == SchemaValidationResult.PASSED.value
            and str(status["status"]) == ProviderReleaseStatus.PUBLISHED.value
        ):
            raise ReleaseAccessError("only a validated published status may be authorized")

    @staticmethod
    def _manifest_values(manifest: StrategyRunManifest) -> tuple[bytes, str]:
        canonical = manifest.to_canonical_bytes()
        return canonical, sha256(canonical).hexdigest()

    @staticmethod
    def _assert_observation_head_is_tail(
        connection: sqlite3.Connection,
        *,
        release_id: str,
        observation_type: str,
        observation_id: str | None,
    ) -> None:
        if observation_id is None:
            return
        parent = connection.execute(
            """SELECT 1 FROM observations
               WHERE observation_id=? AND release_id=? AND observation_type=?""",
            (observation_id, release_id, observation_type),
        ).fetchone()
        successor = connection.execute(
            """SELECT 1 FROM observations
               WHERE release_id=? AND observation_type=? AND supersedes=? LIMIT 1""",
            (release_id, observation_type, observation_id),
        ).fetchone()
        if parent is None or successor is not None:
            raise CacheIntegrityError(
                f"{observation_type} head is not the unique persisted chain tail"
            )

    @staticmethod
    def _current_access(connection: sqlite3.Connection, release_id: str) -> ReleaseAccessContext:
        row = connection.execute(
            """SELECT status.validation_result, status.status,
                      heads.current_status_observation_id,
                      admission.admission_status,
                      heads.current_admission_observation_id,
                      admission.status_observation_id AS admitted_status_observation_id
               FROM release_heads AS heads
               LEFT JOIN release_status_observations AS status
                 ON status.observation_id=heads.current_status_observation_id
               LEFT JOIN release_admission_observations AS admission
                 ON admission.observation_id=heads.current_admission_observation_id
               WHERE heads.release_id=?""",
            (release_id,),
        ).fetchone()
        if row is None:
            return ReleaseAccessContext(None, None, None, None, None, None)
        ReleaseCacheStore._assert_observation_head_is_tail(
            connection,
            release_id=release_id,
            observation_type="release_status",
            observation_id=row["current_status_observation_id"],
        )
        ReleaseCacheStore._assert_observation_head_is_tail(
            connection,
            release_id=release_id,
            observation_type="release_admission",
            observation_id=row["current_admission_observation_id"],
        )
        validation = (
            SchemaValidationResult(str(row["validation_result"]))
            if row["validation_result"] is not None
            else None
        )
        provider_status = (
            ProviderReleaseStatus(str(row["status"])) if row["status"] is not None else None
        )
        admission_status = (
            ReleaseAdmissionStatus(str(row["admission_status"]))
            if row["admission_status"] is not None
            else None
        )
        return ReleaseAccessContext(
            validation,
            provider_status,
            row["current_status_observation_id"],
            admission_status,
            row["current_admission_observation_id"],
            row["admitted_status_observation_id"],
        )

    @staticmethod
    def _require_current_published(connection: sqlite3.Connection, release_id: str) -> sqlite3.Row:
        row = connection.execute(
            """SELECT heads.current_status_observation_id, status.validation_result,
                      status.status
               FROM release_heads AS heads
               LEFT JOIN release_status_observations AS status
                 ON status.observation_id=heads.current_status_observation_id
               WHERE heads.release_id=?""",
            (release_id,),
        ).fetchone()
        if row is not None:
            ReleaseCacheStore._assert_observation_head_is_tail(
                connection,
                release_id=release_id,
                observation_type="release_status",
                observation_id=row["current_status_observation_id"],
            )
        if row is None or not (
            str(row["validation_result"]) == SchemaValidationResult.PASSED.value
            and str(row["status"]) == ProviderReleaseStatus.PUBLISHED.value
        ):
            raise ReleaseAccessError(f"Release {release_id!r} is not currently confirmed published")
        return cast(sqlite3.Row, row)

    def _verify_pin_objects(
        self, connection: sqlite3.Connection, closure_hash: str
    ) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
        self._verify_closure_aggregate(connection, closure_hash)
        releases = connection.execute(
            """SELECT closure.release_id, closure.manifest_sha256 AS sha256,
                      closure.manifest_size_bytes AS size_bytes,
                      manifest.sha256 AS mapped_sha256,
                      manifest.size_bytes AS mapped_size_bytes, object.relative_path
               FROM closure_releases AS closure
               JOIN release_manifests AS manifest USING(release_id)
               JOIN cache_objects AS object
                 ON object.sha256=closure.manifest_sha256
               WHERE closure.closure_hash=? ORDER BY closure.release_id""",
            (closure_hash,),
        ).fetchall()
        expected_release_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM closure_releases WHERE closure_hash=?", (closure_hash,)
            ).fetchone()[0]
        )
        if len(releases) != expected_release_count or expected_release_count == 0:
            raise CacheIntegrityError("retention closure has incomplete Manifest mappings")
        artifacts = connection.execute(
            """SELECT closure.release_id, closure.artifact_id, closure.item_type,
                      closure.sha256, closure.size_bytes, closure.record_count,
                      object.relative_path,
                      mapped.item_type AS mapped_item_type,
                      mapped.sha256 AS mapped_sha256,
                      mapped.size_bytes AS mapped_size_bytes,
                      mapped.record_count AS mapped_record_count
               FROM closure_artifacts AS closure
               JOIN cache_objects AS object USING(sha256)
               JOIN release_artifacts AS mapped
                 ON mapped.release_id=closure.release_id
                AND mapped.artifact_id=closure.artifact_id
               WHERE closure.closure_hash=?
               ORDER BY closure.release_id, closure.artifact_id""",
            (closure_hash,),
        ).fetchall()
        expected_artifact_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM closure_artifacts WHERE closure_hash=?", (closure_hash,)
            ).fetchone()[0]
        )
        if len(artifacts) != expected_artifact_count or expected_artifact_count == 0:
            raise CacheIntegrityError("retention closure has incomplete artifact mappings")
        for row in releases:
            digest = str(row["sha256"])
            if str(row["mapped_sha256"]) != digest or int(row["mapped_size_bytes"]) != int(
                row["size_bytes"]
            ):
                raise CacheIntegrityError("closure Manifest mapping changed")
            expected_relative = self._relative_path(digest).as_posix()
            if str(row["relative_path"]) != expected_relative:
                raise CacheIntegrityError("Manifest CAS path metadata conflict")
            self._verified_read(self.cache_root / expected_relative, digest, int(row["size_bytes"]))
        for row in artifacts:
            digest = str(row["sha256"])
            if (
                str(row["mapped_item_type"]) != str(row["item_type"])
                or str(row["mapped_sha256"]) != digest
                or int(row["mapped_size_bytes"]) != int(row["size_bytes"])
                or row["mapped_record_count"] != row["record_count"]
            ):
                raise CacheIntegrityError("closure artifact mapping changed")
            expected_relative = self._relative_path(digest).as_posix()
            if str(row["relative_path"]) != expected_relative:
                raise CacheIntegrityError("artifact CAS path metadata conflict")
            self._verified_read(self.cache_root / expected_relative, digest, int(row["size_bytes"]))
        return releases, artifacts

    def _verify_persisted_pin_closure(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        closure_hash: str,
    ) -> None:
        """Revalidate every retained object and every derived historical pin."""

        release_rows, artifact_rows = self._verify_pin_objects(connection, closure_hash)
        expected_release_map = {str(row["release_id"]): str(row["sha256"]) for row in release_rows}
        persisted_releases = connection.execute(
            """SELECT pin.release_id, pin.manifest_sha256,
                      observation.release_id AS status_release_id,
                      status.validation_result, status.status
               FROM pin_releases AS pin
               JOIN release_status_observations AS status
                 ON status.observation_id=pin.status_observation_id
               JOIN observations AS observation
                 ON observation.observation_id=pin.status_observation_id
               WHERE pin.run_id=? ORDER BY pin.release_id""",
            (run_id,),
        ).fetchall()
        if len(persisted_releases) != len(expected_release_map) or any(
            str(row["release_id"]) not in expected_release_map
            or str(row["manifest_sha256"]) != expected_release_map[str(row["release_id"])]
            or str(row["status_release_id"]) != str(row["release_id"])
            or str(row["validation_result"]) != SchemaValidationResult.PASSED.value
            or str(row["status"]) != ProviderReleaseStatus.PUBLISHED.value
            for row in persisted_releases
        ):
            raise CacheIntegrityError("run Release retention pins are inconsistent")
        persisted_artifacts = tuple(
            (str(row[0]), str(row[1]), str(row[2]), int(row[3]))
            for row in connection.execute(
                """SELECT release_id, artifact_id, sha256, size_bytes
                   FROM pin_artifacts WHERE run_id=? ORDER BY release_id, artifact_id""",
                (run_id,),
            )
        )
        expected_artifacts = tuple(
            (
                str(row["release_id"]),
                str(row["artifact_id"]),
                str(row["sha256"]),
                int(row["size_bytes"]),
            )
            for row in artifact_rows
        )
        if persisted_artifacts != expected_artifacts:
            raise CacheIntegrityError("run artifact retention pins are inconsistent")

    def _verify_confirmation_aggregate(
        self,
        connection: sqlite3.Connection,
        confirmation_hash: str,
        *,
        expected: RunReleaseStatusConfirmation | None = None,
    ) -> sqlite3.Row:
        """Rebuild an immutable confirmation from its canonical parent and projections."""

        row = connection.execute(
            """SELECT confirmation_hash, confirmation_id, schema_version, run_id,
                      root_release_id, receipt_hash, closure_hash, authority_id,
                      authority_contract_hash, requested_at, confirmed_at, expires_at,
                      canonical_document, canonical_document_hash, persisted_at
               FROM run_release_status_confirmations WHERE confirmation_hash=?""",
            (confirmation_hash,),
        ).fetchone()
        if row is None:
            raise CacheIntegrityError("run status confirmation is missing")
        content = bytes(row["canonical_document"])
        if sha256(content).hexdigest() != str(row["canonical_document_hash"]):
            raise CacheIntegrityError("run status confirmation canonical document hash changed")
        if expected is not None and content != expected.to_canonical_bytes():
            raise ImmutableMappingError("run status confirmation identity was remapped")
        try:
            parsed = status_confirmation_from_canonical_bytes(content)
            header = (
                parsed.confirmation_hash.value,
                parsed.confirmation_id,
                parsed.schema_version,
                parsed.run_id,
                parsed.root_release_id,
                parsed.receipt_hash.value,
                parsed.closure_hash.value,
                parsed.authority_id,
                parsed.authority_contract_hash.value,
                format_utc(parsed.requested_at),
                format_utc(parsed.confirmed_at),
                format_utc(parsed.expires_at),
            )
            if header != tuple(
                row[field]
                for field in (
                    "confirmation_hash",
                    "confirmation_id",
                    "schema_version",
                    "run_id",
                    "root_release_id",
                    "receipt_hash",
                    "closure_hash",
                    "authority_id",
                    "authority_contract_hash",
                    "requested_at",
                    "confirmed_at",
                    "expires_at",
                )
            ):
                raise ValueError
            projected_items = tuple(
                (
                    *self._input_ref_identity(item.strategy_input_ref),
                    item.status_observation_id,
                    item.status_event_id,
                    item.status_event_hash.value,
                    item.status_sequence,
                    format_utc(item.provider_snapshot_at),
                    format_utc(item.checked_at),
                    item.response_bytes_hash.value,
                )
                for item in parsed.items
            )
        except (TypeError, ValueError) as exc:
            raise CacheIntegrityError(
                "run status confirmation canonical parent is inconsistent"
            ) from exc
        persisted_items = tuple(
            tuple(item)
            for item in connection.execute(
                """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                          manifest_schema_version, manifest_hash, status_observation_id,
                          status_event_id, status_event_hash, status_sequence,
                          provider_snapshot_at, checked_at, response_bytes_hash
                   FROM run_release_status_confirmation_items
                   WHERE confirmation_hash=? ORDER BY release_id""",
                (confirmation_hash,),
            )
        )
        if projected_items != persisted_items:
            raise CacheIntegrityError(
                "run status confirmation item index differs from canonical parent"
            )
        return cast(sqlite3.Row, row)

    def _persist_confirmation(
        self,
        connection: sqlite3.Connection,
        confirmation: RunReleaseStatusConfirmation,
        *,
        persisted_at: str,
    ) -> None:
        canonical = confirmation.to_canonical_bytes()
        confirmation_hash = confirmation.confirmation_hash.value
        conflict = connection.execute(
            """SELECT confirmation_hash FROM run_release_status_confirmations
               WHERE confirmation_hash=? OR confirmation_id=? OR run_id=?""",
            (confirmation_hash, confirmation.confirmation_id, confirmation.run_id),
        ).fetchone()
        if conflict is not None:
            if str(conflict["confirmation_hash"]) != confirmation_hash:
                raise ImmutableMappingError("run status confirmation identity was remapped")
            self._verify_confirmation_aggregate(
                connection, confirmation_hash, expected=confirmation
            )
            return
        connection.execute(
            """INSERT INTO run_release_status_confirmations (
                   confirmation_hash, confirmation_id, schema_version, run_id,
                   root_release_id, receipt_hash, closure_hash, authority_id,
                   authority_contract_hash, requested_at, confirmed_at, expires_at,
                   canonical_document, canonical_document_hash, persisted_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                confirmation_hash,
                confirmation.confirmation_id,
                confirmation.schema_version,
                confirmation.run_id,
                confirmation.root_release_id,
                confirmation.receipt_hash.value,
                confirmation.closure_hash.value,
                confirmation.authority_id,
                confirmation.authority_contract_hash.value,
                format_utc(confirmation.requested_at),
                format_utc(confirmation.confirmed_at),
                format_utc(confirmation.expires_at),
                canonical,
                sha256(canonical).hexdigest(),
                persisted_at,
            ),
        )
        for item in confirmation.items:
            identity = self._input_ref_identity(item.strategy_input_ref)
            connection.execute(
                """INSERT INTO run_release_status_confirmation_items (
                       confirmation_hash, release_id, input_ref_schema_version,
                       knowledge_cutoff, manifest_schema_version, manifest_hash,
                       status_observation_id, status_event_id, status_event_hash,
                       status_sequence, provider_snapshot_at, checked_at,
                       response_bytes_hash
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    confirmation_hash,
                    *identity,
                    item.status_observation_id,
                    item.status_event_id,
                    item.status_event_hash.value,
                    item.status_sequence,
                    format_utc(item.provider_snapshot_at),
                    format_utc(item.checked_at),
                    item.response_bytes_hash.value,
                ),
            )
        self._verify_confirmation_aggregate(connection, confirmation_hash, expected=confirmation)

    def _validate_confirmation_for_pin(
        self,
        connection: sqlite3.Connection,
        *,
        manifest: StrategyRunManifest,
        confirmation: RunReleaseStatusConfirmation,
        receipt_hash: str,
        closure_hash: str,
        closure_release_ids: tuple[str, ...],
        pin_started: datetime,
    ) -> dict[str, str]:
        """Fail closed unless one trusted, fresh snapshot covers the exact closure."""

        if confirmation.run_id != manifest.run_id:
            raise ReleaseAccessError("status confirmation belongs to another run")
        root_release_id = manifest.strategy_input_ref.dataset_release_id
        if (
            confirmation.root_release_id != root_release_id
            or confirmation.receipt_hash.value != receipt_hash
            or confirmation.closure_hash.value != closure_hash
        ):
            raise ReleaseAccessError(
                "status confirmation does not bind the run Release/receipt/closure"
            )
        policy = self._authority_policies.get(
            (confirmation.authority_id, confirmation.authority_contract_hash.value)
        )
        if policy is None:
            raise ReleaseAccessError("status confirmation authority contract is not allowed")
        if confirmation.confirmed_at > manifest.created_at:
            raise ReleaseAccessError("run Manifest cannot predate its status confirmation")
        if confirmation.confirmed_at > pin_started + policy.max_clock_skew:
            raise ReleaseAccessError("status confirmation is ahead of the local clock")
        if confirmation.expires_at <= pin_started:
            raise ReleaseAccessError("status confirmation has expired")

        items_by_release = {item.release_id: item for item in confirmation.items}
        if set(items_by_release) != set(closure_release_ids):
            raise ReleaseAccessError(
                "status confirmation must cover the full retention closure exactly"
            )
        status_by_release: dict[str, str] = {}
        for release_id in closure_release_ids:
            item = items_by_release[release_id]
            persisted_identity = connection.execute(
                """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                          manifest_schema_version, manifest_hash
                   FROM release_identities WHERE release_id=?""",
                (release_id,),
            ).fetchone()
            if persisted_identity is None or tuple(persisted_identity) != self._input_ref_identity(
                item.strategy_input_ref
            ):
                raise ReleaseAccessError(
                    "status confirmation Release identity differs from the persisted closure"
                )
            if item.checked_at > pin_started + policy.max_clock_skew:
                raise ReleaseAccessError("status confirmation check is ahead of the local clock")
            if item.provider_snapshot_at > pin_started + policy.max_clock_skew:
                raise ReleaseAccessError("provider status snapshot is ahead of the local clock")
            if item.provider_snapshot_at > item.checked_at + policy.max_clock_skew:
                raise ReleaseAccessError(
                    "provider status snapshot exceeds the permitted clock skew"
                )
            if pin_started - item.provider_snapshot_at > policy.max_age + policy.max_clock_skew:
                raise ReleaseAccessError("provider status snapshot is stale")

            heads = self._verify_release_observation_chains(connection, release_id)
            current = self._require_current_published(connection, release_id)
            current_observation_id = str(current["current_status_observation_id"])
            if (
                heads["current_status_observation_id"] != item.status_observation_id
                or current_observation_id != item.status_observation_id
            ):
                raise ReleaseAccessError(
                    "status confirmation is no longer the current provider status head"
                )
            document = self._verify_observation_aggregate(connection, item.status_observation_id)
            if not (
                document["schema_validation_result"] == SchemaValidationResult.PASSED.value
                and document["status"] == ProviderReleaseStatus.PUBLISHED.value
                and document["status_event_id"] == item.status_event_id
                and self._json_sha256_value(document["status_event_hash"])
                == item.status_event_hash.value
                and document["status_sequence"] == item.status_sequence
            ):
                raise ReleaseAccessError(
                    "status confirmation item does not match its passed published event"
                )
            recorded_at = datetime.fromisoformat(
                str(document["status_recorded_at"]).replace("Z", "+00:00")
            )
            if recorded_at > item.provider_snapshot_at + policy.max_clock_skew:
                raise ReleaseAccessError(
                    "provider status event postdates the confirmed provider snapshot"
                )
            status_by_release[release_id] = current_observation_id
        return status_by_release

    def pin_run(
        self,
        manifest: StrategyRunManifest,
        confirmation: RunReleaseStatusConfirmation | None = None,
    ) -> bool:
        """Atomically confirm current status, admit, and pin the full closure."""

        if not isinstance(manifest, StrategyRunManifest):
            raise TypeError("manifest must be a StrategyRunManifest")
        canonical, manifest_hash = self._manifest_values(manifest)
        input_ref = manifest.strategy_input_ref
        root_release_id = input_ref.dataset_release_id
        receipt_hash = manifest.artifact_consumption_receipt_hash.value
        with self._write() as connection:
            if (
                connection.execute(
                    "SELECT 1 FROM legacy_v2_quarantined_run_pins WHERE run_id=?",
                    (manifest.run_id,),
                ).fetchone()
                is not None
            ):
                raise ReleaseAccessError("legacy v2 run pins are permanently audit-only")
            if confirmation is None:
                raise ReleaseAccessError("a run-scoped current-status confirmation is required")
            if not isinstance(confirmation, RunReleaseStatusConfirmation):
                raise TypeError("confirmation must be a RunReleaseStatusConfirmation")
            pin_started = read_clock(self.clock, field_name="storage clock")
            pin_started_at = format_utc(pin_started)
            manifest_created_at = format_utc(manifest.created_at)
            if manifest_created_at > pin_started_at:
                raise ReleaseAccessError("run Manifest created_at cannot be in the future")
            identity = connection.execute(
                """SELECT release_id, input_ref_schema_version, knowledge_cutoff,
                          manifest_schema_version, manifest_hash
                   FROM release_identities WHERE release_id=?""",
                (root_release_id,),
            ).fetchone()
            if identity is None or tuple(identity) != self._input_ref_identity(input_ref):
                raise ReleaseAccessError("run input identity is not the persisted exact Release")
            receipt = connection.execute(
                """SELECT receipts.release_id, receipt_closures.closure_hash,
                          receipts.persisted_at AS receipt_persisted_at,
                          closure.persisted_at AS closure_persisted_at
                   FROM receipts JOIN receipt_closures USING(receipt_hash)
                   JOIN retention_closures AS closure USING(closure_hash)
                   WHERE receipts.receipt_hash=?""",
                (receipt_hash,),
            ).fetchone()
            if receipt is None or str(receipt["release_id"]) != root_release_id:
                raise ReleaseAccessError("run receipt is unavailable or belongs to another Release")
            self._verify_receipt_aggregate(connection, receipt_hash)
            closure_hash = str(receipt["closure_hash"])
            closure_aggregate = self._verify_closure_aggregate(connection, closure_hash)
            if str(closure_aggregate["root_release_id"]) != root_release_id:
                raise CacheIntegrityError("Receipt and closure root identities differ")
            if any(
                str(receipt[field]) > manifest_created_at
                for field in ("receipt_persisted_at", "closure_persisted_at")
            ):
                raise ReleaseAccessError(
                    "run Manifest cannot predate persisted receipt/closure material"
                )

            # Exact retries do not admit a new run.  Validate their immutable
            # historical binding and return before applying current freshness
            # or publication policy, which may legitimately have changed.
            existing_retry = connection.execute(
                "SELECT * FROM strategy_run_pins WHERE run_id=?", (manifest.run_id,)
            ).fetchone()
            if existing_retry is not None:
                expected_retry = {
                    "root_release_id": root_release_id,
                    "receipt_hash": receipt_hash,
                    "closure_hash": closure_hash,
                    "fetch_observation_id": manifest.artifact_fetch_observation_id,
                    "status_observation_id": manifest.release_status_observation_id,
                    "admission_observation_id": manifest.release_admission_observation_id,
                    "run_manifest_hash": manifest_hash,
                    "canonical_profile_version": (STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION),
                }
                if bytes(existing_retry["run_manifest_canonical"]) != canonical or any(
                    existing_retry[key] != value for key, value in expected_retry.items()
                ):
                    raise ImmutableMappingError("run identifier was remapped")
                retry_binding = connection.execute(
                    """SELECT confirmation_hash FROM strategy_run_confirmation_bindings
                       WHERE run_id=?""",
                    (manifest.run_id,),
                ).fetchone()
                if retry_binding is None:
                    raise ReleaseAccessError(
                        "legacy v2 run pins are audit-only and cannot be reauthorized"
                    )
                if str(retry_binding["confirmation_hash"]) != confirmation.confirmation_hash.value:
                    raise ImmutableMappingError("run confirmation binding was remapped")
                retry_confirmation = self._verify_confirmation_aggregate(
                    connection,
                    confirmation.confirmation_hash.value,
                    expected=confirmation,
                )
                if not (
                    str(retry_confirmation["run_id"]) == manifest.run_id
                    and str(retry_confirmation["root_release_id"]) == root_release_id
                    and str(retry_confirmation["receipt_hash"]) == receipt_hash
                    and str(retry_confirmation["closure_hash"]) == closure_hash
                ):
                    raise CacheIntegrityError(
                        "run status confirmation binding differs from its pin"
                    )
                self._verify_persisted_pin_closure(
                    connection, run_id=manifest.run_id, closure_hash=closure_hash
                )
                return False

            heads = self._verify_release_observation_chains(connection, root_release_id)
            self._assert_observation_head_is_tail(
                connection,
                release_id=root_release_id,
                observation_type="artifact_fetch",
                observation_id=heads["current_fetch_observation_id"],
            )
            self._assert_observation_head_is_tail(
                connection,
                release_id=root_release_id,
                observation_type="release_admission",
                observation_id=heads["current_admission_observation_id"],
            )
            if heads["current_fetch_observation_id"] != manifest.artifact_fetch_observation_id:
                raise ReleaseAccessError("run fetch observation is not the current fetch head")
            fetch = connection.execute(
                """SELECT validation_result, receipt_hash
                   FROM artifact_fetch_observations WHERE observation_id=?""",
                (manifest.artifact_fetch_observation_id,),
            ).fetchone()
            if fetch is None or not (
                str(fetch["validation_result"]) == SchemaValidationResult.PASSED.value
                and str(fetch["receipt_hash"]) == receipt_hash
            ):
                raise ReleaseAccessError("run fetch observation did not pass for its receipt")

            root_status = self._require_current_published(connection, root_release_id)
            if (
                root_status["current_status_observation_id"]
                != manifest.release_status_observation_id
            ):
                raise ReleaseAccessError("run status observation is not the current status head")
            if (
                heads["current_admission_observation_id"]
                != manifest.release_admission_observation_id
            ):
                raise ReleaseAccessError("run admission is not the current admission head")
            admission = connection.execute(
                """SELECT status_observation_id, admission_status
                   FROM release_admission_observations WHERE observation_id=?""",
                (manifest.release_admission_observation_id,),
            ).fetchone()
            if admission is None or not (
                str(admission["status_observation_id"]) == manifest.release_status_observation_id
                and str(admission["admission_status"]) == ReleaseAdmissionStatus.AUTHORIZED.value
            ):
                raise ReleaseAccessError("run does not have current local authorization")

            required_observation_ids = (
                manifest.artifact_fetch_observation_id,
                manifest.release_status_observation_id,
                manifest.release_admission_observation_id,
            )
            required_times = connection.execute(
                """SELECT observation_id, observed_at, persisted_at FROM observations
                   WHERE observation_id IN (?, ?, ?)""",
                required_observation_ids,
            ).fetchall()
            if len(required_times) != 3 or any(
                str(row[field]) > manifest_created_at
                for row in required_times
                for field in ("observed_at", "persisted_at")
            ):
                raise ReleaseAccessError(
                    "run Manifest cannot predate a required consumption observation"
                )

            closure_release_ids = tuple(
                str(row[0])
                for row in connection.execute(
                    "SELECT release_id FROM closure_releases WHERE closure_hash=? ORDER BY release_id",
                    (closure_hash,),
                )
            )
            if not closure_release_ids:
                raise CacheIntegrityError("run retention closure is empty")
            pin_status_by_release = self._validate_confirmation_for_pin(
                connection,
                manifest=manifest,
                confirmation=confirmation,
                receipt_hash=receipt_hash,
                closure_hash=closure_hash,
                closure_release_ids=closure_release_ids,
                pin_started=pin_started,
            )
            for release_id in closure_release_ids:
                current_status_observation_id = pin_status_by_release[release_id]
                observed = connection.execute(
                    "SELECT observed_at, persisted_at FROM observations WHERE observation_id=?",
                    (current_status_observation_id,),
                ).fetchone()
                if observed is None or any(
                    str(observed[field]) > manifest_created_at
                    for field in ("observed_at", "persisted_at")
                ):
                    raise ReleaseAccessError(
                        "run Manifest cannot predate a retained Release status observation"
                    )
            material_times = connection.execute(
                """SELECT manifest.persisted_at
                   FROM release_manifests AS manifest
                   JOIN closure_releases AS closure USING(release_id)
                   WHERE closure.closure_hash=?
                   UNION ALL
                   SELECT artifact.persisted_at
                   FROM release_artifacts AS artifact
                   JOIN closure_artifacts AS closure
                     ON closure.release_id=artifact.release_id
                    AND closure.artifact_id=artifact.artifact_id
                   WHERE closure.closure_hash=?""",
                (closure_hash, closure_hash),
            ).fetchall()
            if any(str(row[0]) > manifest_created_at for row in material_times):
                raise ReleaseAccessError(
                    "run Manifest cannot predate persisted Manifest/artifact material"
                )
            release_rows, artifact_rows = self._verify_pin_objects(connection, closure_hash)

            self._persist_confirmation(connection, confirmation, persisted_at=pin_started_at)
            connection.execute(
                "INSERT INTO strategy_run_pins VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    manifest.run_id,
                    root_release_id,
                    receipt_hash,
                    closure_hash,
                    manifest.artifact_fetch_observation_id,
                    manifest.release_status_observation_id,
                    manifest.release_admission_observation_id,
                    canonical,
                    manifest_hash,
                    STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                    pin_started_at,
                ),
            )
            for row in release_rows:
                connection.execute(
                    "INSERT INTO pin_releases VALUES (?, ?, ?, ?)",
                    (
                        manifest.run_id,
                        row["release_id"],
                        row["sha256"],
                        pin_status_by_release[str(row["release_id"])],
                    ),
                )
            for row in artifact_rows:
                connection.execute(
                    "INSERT INTO pin_artifacts VALUES (?, ?, ?, ?, ?)",
                    (
                        manifest.run_id,
                        row["release_id"],
                        row["artifact_id"],
                        row["sha256"],
                        row["size_bytes"],
                    ),
                )
            connection.execute(
                """INSERT INTO strategy_run_confirmation_bindings (
                       run_id, confirmation_hash, bound_at
                   ) VALUES (?, ?, ?)""",
                (manifest.run_id, confirmation.confirmation_hash.value, pin_started_at),
            )
            return True

    @staticmethod
    def _purpose(value: RunPurpose | str) -> RunPurpose:
        try:
            return value if isinstance(value, RunPurpose) else RunPurpose(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown run purpose") from exc

    def read_artifact(
        self,
        *,
        artifact_id: str,
        purpose: RunPurpose | str,
        source_manifest: StrategyRunManifest,
        release_id: str | None = None,
        audit_request: AuditReplayRequest | None = None,
    ) -> ArtifactRead:
        """Read root content normally, or retained source content for explicit audit."""

        artifact_id = _require_provider_id("artifact_id", artifact_id)
        access_purpose = self._purpose(purpose)
        if not isinstance(source_manifest, StrategyRunManifest):
            raise TypeError("source_manifest must be the original StrategyRunManifest")
        canonical, manifest_hash = self._manifest_values(source_manifest)
        root_release_id = source_manifest.strategy_input_ref.dataset_release_id
        target_release_id = (
            root_release_id
            if release_id is None
            else _require_id("release_id", release_id, exact_release=True)
        )
        if access_purpose is RunPurpose.AUDIT_REPLAY:
            if not isinstance(audit_request, AuditReplayRequest):
                raise ReleaseAccessError("audit replay requires an AuditReplayRequest")
            if (
                audit_request.source_run_id != source_manifest.run_id
                or audit_request.source_manifest_hash != manifest_hash
            ):
                raise ReleaseAccessError("audit request does not identify the source Manifest")
        elif audit_request is not None:
            raise ReleaseAccessError("AuditReplayRequest cannot authorize an ordinary read")
        if access_purpose is RunPurpose.NEW_RUN and target_release_id != root_release_id:
            raise ReleaseAccessError(
                "ordinary strategy reads cannot expose source Release artifacts"
            )

        with self._connection() as connection:
            connection.execute("BEGIN")
            try:
                pin = connection.execute(
                    "SELECT * FROM strategy_run_pins WHERE run_id=?",
                    (source_manifest.run_id,),
                ).fetchone()
                expected = {
                    "root_release_id": root_release_id,
                    "receipt_hash": source_manifest.artifact_consumption_receipt_hash.value,
                    "fetch_observation_id": source_manifest.artifact_fetch_observation_id,
                    "status_observation_id": source_manifest.release_status_observation_id,
                    "admission_observation_id": source_manifest.release_admission_observation_id,
                    "run_manifest_hash": manifest_hash,
                    "canonical_profile_version": STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                }
                if (
                    pin is None
                    or bytes(pin["run_manifest_canonical"]) != canonical
                    or any(pin[key] != value for key, value in expected.items())
                ):
                    raise ReleaseAccessError("source run is not this exact persisted pin")
                quarantined = connection.execute(
                    "SELECT 1 FROM legacy_v2_quarantined_run_pins WHERE run_id=?",
                    (source_manifest.run_id,),
                ).fetchone()
                if quarantined is not None and access_purpose is RunPurpose.NEW_RUN:
                    raise ReleaseAccessError("legacy v2 run pins are permanently audit-only")
                binding = (
                    None
                    if quarantined is not None
                    else connection.execute(
                        """SELECT confirmation_hash FROM strategy_run_confirmation_bindings
                           WHERE run_id=?""",
                        (source_manifest.run_id,),
                    ).fetchone()
                )
                if binding is None:
                    if access_purpose is RunPurpose.NEW_RUN:
                        raise ReleaseAccessError(
                            "legacy v2 run pins are audit-only and cannot authorize ordinary access"
                        )
                else:
                    confirmation_row = self._verify_confirmation_aggregate(
                        connection, str(binding["confirmation_hash"])
                    )
                    if not (
                        str(confirmation_row["run_id"]) == source_manifest.run_id
                        and str(confirmation_row["root_release_id"]) == root_release_id
                        and str(confirmation_row["receipt_hash"]) == str(pin["receipt_hash"])
                        and str(confirmation_row["closure_hash"]) == str(pin["closure_hash"])
                    ):
                        raise CacheIntegrityError(
                            "run status confirmation binding differs from its pin"
                        )
                receipt_closure = connection.execute(
                    "SELECT closure_hash FROM receipt_closures WHERE receipt_hash=?",
                    (pin["receipt_hash"],),
                ).fetchone()
                if receipt_closure is None or str(receipt_closure["closure_hash"]) != str(
                    pin["closure_hash"]
                ):
                    raise CacheIntegrityError("run receipt/closure mapping changed")
                self._verify_receipt_aggregate(connection, str(pin["receipt_hash"]))
                closure_aggregate = self._verify_closure_aggregate(
                    connection, str(pin["closure_hash"])
                )
                if str(closure_aggregate["root_release_id"]) != root_release_id:
                    raise CacheIntegrityError("run Receipt and closure root identities differ")
                self._verify_persisted_pin_closure(
                    connection,
                    run_id=source_manifest.run_id,
                    closure_hash=str(pin["closure_hash"]),
                )
                retained_release_ids = tuple(
                    str(item[0])
                    for item in connection.execute(
                        "SELECT release_id FROM pin_releases WHERE run_id=? ORDER BY release_id",
                        (source_manifest.run_id,),
                    )
                )
                for retained_release_id in retained_release_ids:
                    self._verify_release_observation_chains(connection, retained_release_id)

                row = connection.execute(
                    """SELECT pin.sha256, pin.size_bytes, object.relative_path,
                              release_pin.status_observation_id,
                              mapped.sha256 AS mapped_sha256,
                              mapped.size_bytes AS mapped_size_bytes
                       FROM pin_artifacts AS pin
                       JOIN pin_releases AS release_pin
                         ON release_pin.run_id=pin.run_id
                        AND release_pin.release_id=pin.release_id
                       JOIN cache_objects AS object USING(sha256)
                       JOIN release_artifacts AS mapped
                         ON mapped.release_id=pin.release_id
                        AND mapped.artifact_id=pin.artifact_id
                       WHERE pin.run_id=? AND pin.release_id=? AND pin.artifact_id=?""",
                    (source_manifest.run_id, target_release_id, artifact_id),
                ).fetchone()
                if row is None:
                    raise ReleaseAccessError("artifact is not in the source run retention snapshot")
                digest = str(row["sha256"])
                size_bytes = int(row["size_bytes"])
                if (
                    str(row["mapped_sha256"]) != digest
                    or int(row["mapped_size_bytes"]) != size_bytes
                ):
                    raise CacheIntegrityError("pinned artifact mapping changed")
                expected_relative = self._relative_path(digest).as_posix()
                if str(row["relative_path"]) != expected_relative:
                    raise CacheIntegrityError("content path metadata conflict")
                path = self.cache_root / expected_relative
                content = self._verified_read(path, digest, size_bytes)
                current_access = self._current_access(connection, target_release_id)

                if access_purpose is RunPurpose.NEW_RUN:
                    root_heads = connection.execute(
                        "SELECT * FROM release_heads WHERE release_id=?", (root_release_id,)
                    ).fetchone()
                    if root_heads is not None:
                        self._assert_observation_head_is_tail(
                            connection,
                            release_id=root_release_id,
                            observation_type="artifact_fetch",
                            observation_id=root_heads["current_fetch_observation_id"],
                        )
                    if root_heads is None or not (
                        root_heads["current_fetch_observation_id"] == pin["fetch_observation_id"]
                        and root_heads["current_status_observation_id"]
                        == pin["status_observation_id"]
                        and root_heads["current_admission_observation_id"]
                        == pin["admission_observation_id"]
                        and current_access.authorized
                    ):
                        raise ReleaseAccessError(
                            "ordinary access lost current fetch/status/admission authorization"
                        )
                    pinned_releases = connection.execute(
                        """SELECT pin_release.release_id,
                                  pin_release.status_observation_id,
                                  heads.current_status_observation_id,
                                  status.validation_result, status.status
                           FROM pin_releases AS pin_release
                           JOIN release_heads AS heads USING(release_id)
                           JOIN release_status_observations AS status
                             ON status.observation_id=heads.current_status_observation_id
                           WHERE pin_release.run_id=?""",
                        (source_manifest.run_id,),
                    ).fetchall()
                    expected_count = int(
                        connection.execute(
                            "SELECT COUNT(*) FROM pin_releases WHERE run_id=?",
                            (source_manifest.run_id,),
                        ).fetchone()[0]
                    )
                    for item in pinned_releases:
                        self._assert_observation_head_is_tail(
                            connection,
                            release_id=str(item["release_id"]),
                            observation_type="release_status",
                            observation_id=item["current_status_observation_id"],
                        )
                    if len(pinned_releases) != expected_count or any(
                        item["status_observation_id"] != item["current_status_observation_id"]
                        or str(item["validation_result"]) != SchemaValidationResult.PASSED.value
                        or str(item["status"]) != ProviderReleaseStatus.PUBLISHED.value
                        for item in pinned_releases
                    ):
                        raise ReleaseAccessError(
                            "ordinary access lost a retained Release publication status"
                        )
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
                return ArtifactRead(
                    content=content,
                    artifact=CachedArtifact(
                        target_release_id, artifact_id, digest, size_bytes, path
                    ),
                    purpose=access_purpose,
                    source_run_id=source_manifest.run_id,
                    source_manifest_hash=manifest_hash,
                    source_manifest_profile_version=(
                        STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION
                    ),
                    pinned_release_status_observation_id=str(row["status_observation_id"]),
                    pinned_root_admission_observation_id=str(pin["admission_observation_id"]),
                    current_release_access=current_access,
                )

    def quota_report(self, *, verify_integrity: bool = True) -> CacheQuotaReport:
        """Inventory the soft limit without deleting any current or historical bytes."""

        if not isinstance(verify_integrity, bool):
            raise TypeError("verify_integrity must be a boolean")
        self._assert_safe_cache_path(self.cache_root)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT object.sha256, object.size_bytes, object.relative_path,
                          object.sha256 IN (
                              SELECT sha256 FROM pin_artifacts
                              UNION SELECT manifest_sha256 FROM pin_releases
                          ) AS is_pinned
                   FROM cache_objects AS object"""
            ).fetchall()
            registered_bytes = sum(int(row["size_bytes"]) for row in rows)
            pinned_bytes = int(
                connection.execute(
                    """SELECT COALESCE(SUM(size_bytes), 0) FROM cache_objects
                       WHERE sha256 IN (
                           SELECT sha256 FROM pin_artifacts
                           UNION SELECT manifest_sha256 FROM pin_releases
                       )"""
                ).fetchone()[0]
            )

        issues: list[CacheScanIssue] = []
        physical: dict[str, tuple[Path, int, int]] = {}

        def record_walk_error(error: OSError) -> None:
            filename = error.filename or str(self.cache_root)
            try:
                relative = Path(filename).relative_to(self.cache_root).as_posix()
            except ValueError:
                relative = str(filename)
            issues.append(CacheScanIssue(CacheIssueKind.SCAN_FAILURE, relative, str(error)))

        for directory, subdirectories, filenames in os.walk(
            self.cache_root, onerror=record_walk_error
        ):
            directory_path = Path(directory)
            self._assert_safe_cache_path(directory_path)
            for subdirectory in tuple(subdirectories):
                child = directory_path / subdirectory
                if _is_link_or_junction(child):
                    issues.append(
                        CacheScanIssue(
                            CacheIssueKind.SCAN_FAILURE,
                            child.relative_to(self.cache_root).as_posix(),
                            "cache directory is a symlink or junction",
                        )
                    )
                    subdirectories.remove(subdirectory)
            for filename in filenames:
                path = directory_path / filename
                relative = path.relative_to(self.cache_root).as_posix()
                if _is_link_or_junction(path):
                    issues.append(
                        CacheScanIssue(
                            CacheIssueKind.SCAN_FAILURE,
                            relative,
                            "cache file is a symlink or junction",
                        )
                    )
                    continue
                try:
                    metadata = path.stat()
                    physical[relative] = (path, metadata.st_size, metadata.st_nlink)
                except OSError as exc:
                    issues.append(CacheScanIssue(CacheIssueKind.SCAN_FAILURE, relative, str(exc)))

        registered_paths: set[str] = set()
        for row in rows:
            digest = str(row["sha256"])
            relative = str(row["relative_path"])
            is_pinned = bool(row["is_pinned"])
            registered_paths.add(relative)
            expected_relative = self._relative_path(digest).as_posix()
            if relative != expected_relative:
                issues.append(
                    CacheScanIssue(
                        CacheIssueKind.METADATA,
                        relative,
                        f"registered path does not match digest {digest}",
                        is_pinned,
                    )
                )
            entry = physical.get(relative)
            if entry is None:
                issues.append(
                    CacheScanIssue(
                        CacheIssueKind.MISSING,
                        relative,
                        f"registered object {digest}",
                        is_pinned,
                    )
                )
                continue
            path, actual_size, link_count = entry
            if link_count > 1:
                issues.append(
                    CacheScanIssue(
                        CacheIssueKind.METADATA,
                        relative,
                        f"cache file has {link_count} hard links",
                        is_pinned,
                    )
                )
            if verify_integrity:
                try:
                    content = path.read_bytes()
                except OSError as exc:
                    issues.append(
                        CacheScanIssue(CacheIssueKind.SCAN_FAILURE, relative, str(exc), is_pinned)
                    )
                    continue
                if (
                    actual_size != int(row["size_bytes"])
                    or len(content) != int(row["size_bytes"])
                    or sha256(content).hexdigest() != digest
                ):
                    issues.append(
                        CacheScanIssue(
                            CacheIssueKind.CORRUPT,
                            relative,
                            f"registered object failed size/hash validation: {digest}",
                            is_pinned,
                        )
                    )

        for relative, (_path, _size, link_count) in physical.items():
            if relative not in registered_paths and link_count > 1:
                issues.append(
                    CacheScanIssue(
                        CacheIssueKind.METADATA,
                        relative,
                        f"orphan cache file has {link_count} hard links",
                    )
                )
        physical_bytes = sum(size for _path, size, _links in physical.values())
        orphan_bytes = sum(
            size
            for relative, (_path, size, _links) in physical.items()
            if relative not in registered_paths
        )
        return CacheQuotaReport(
            soft_limit_bytes=self.soft_limit_bytes,
            physical_bytes=physical_bytes,
            registered_bytes=registered_bytes,
            orphan_bytes=orphan_bytes,
            pinned_bytes=pinned_bytes,
            integrity_checked=verify_integrity,
            issues=tuple(issues),
        )
