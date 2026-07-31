"""InvestSystem-owned SQLite metadata and immutable Release artifact cache.

Provider status and local admission are deliberately separate axes.  A normal
run can read only after one ``BEGIN IMMEDIATE`` transaction has admitted the
latest provider observation and pinned the exact caller-declared artifact set.
Audit replay uses a separate request type and never changes the original run
manifest or its run mode.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from .canonical import canonical_json_bytes, format_utc
from .clock import Clock, SystemClock, read_clock
from .models import StrategyInputRef, StrategyRunManifest

STORAGE_SCHEMA_VERSION = 1
DEFAULT_CACHE_SOFT_LIMIT_BYTES = 20 * 1024**3
STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION = "investsystem-canonical-json-v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class StorageError(RuntimeError):
    """Base class for fail-closed storage errors."""


class StorageSchemaError(StorageError):
    """The SQLite schema is unknown, incomplete, or unsafe to adopt."""


class CacheIntegrityError(StorageError):
    """Declared, persisted, or read-back content has conflicting identity."""


class ReleaseAccessError(StorageError):
    """Provider status, admission, purpose, or pin policy denies access."""


class ImmutableMappingError(StorageError):
    """An immutable observation, artifact, or run identifier was remapped."""


class ReleaseStatus(StrEnum):
    """Provider-reported Release status; local confirmation is not represented here."""

    PUBLISHED = "published"
    WITHDRAWN = "withdrawn"


class AdmissionStatus(StrEnum):
    """InvestSystem-local authorization for one exact provider observation."""

    AUTHORIZED = "authorized"
    UNCONFIRMED = "unconfirmed"
    DENIED = "denied"


class RunPurpose(StrEnum):
    """Storage access purpose, separate from ``StrategyRunManifest.run_mode``."""

    NEW_RUN = "new_run"
    AUDIT_REPLAY = "audit_replay"


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
        """Compatibility alias for total successfully scanned physical usage."""

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
    provider_status: ReleaseStatus | None
    provider_status_observation_id: str | None
    admission_status: AdmissionStatus | None
    admission_observation_id: str | None
    admission_provider_status_observation_id: str | None

    @property
    def authorized(self) -> bool:
        return (
            self.provider_status is ReleaseStatus.PUBLISHED
            and self.admission_status is AdmissionStatus.AUTHORIZED
            and self.provider_status_observation_id == self.admission_provider_status_observation_id
        )


@dataclass(frozen=True, slots=True)
class ArtifactRead:
    """Pinned bytes plus their purpose, source identity, and current status context."""

    content: bytes
    artifact: CachedArtifact
    purpose: RunPurpose
    source_run_id: str
    source_manifest_hash: str
    source_manifest_profile_version: str
    source_status_observation_id: str
    source_admission_observation_id: str
    current_access: ReleaseAccessContext


def _require_id(name: str, value: str, *, exact_release: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a valid 1-128 character identifier")
    if exact_release and value.casefold() == "latest":
        raise ValueError(f"{name} must be exact, not 'latest'")
    return value


def _require_digest(value: str, *, field_name: str = "expected_sha256") -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be 64 lowercase hexadecimal characters")
    return value


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction is not None and is_junction())


_TABLE_SQL = {
    "releases": """CREATE TABLE releases (
        release_id TEXT NOT NULL PRIMARY KEY,
        current_status_observation_id TEXT UNIQUE,
        current_admission_observation_id TEXT UNIQUE,
        created_at TEXT NOT NULL,
        FOREIGN KEY (current_status_observation_id)
            REFERENCES release_status_observations(status_observation_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (current_admission_observation_id)
            REFERENCES release_admission_observations(admission_observation_id)
            ON DELETE RESTRICT
    )""",
    "release_status_observations": """CREATE TABLE release_status_observations (
        status_observation_id TEXT NOT NULL PRIMARY KEY,
        release_id TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('published', 'withdrawn')),
        input_ref_schema_version TEXT NOT NULL,
        dataset_release_id TEXT NOT NULL,
        knowledge_cutoff TEXT NOT NULL,
        release_manifest_schema_version TEXT NOT NULL,
        manifest_hash_algorithm TEXT NOT NULL CHECK (manifest_hash_algorithm = 'sha256'),
        manifest_hash_value TEXT NOT NULL CHECK (
            length(manifest_hash_value) = 64
            AND manifest_hash_value NOT GLOB '*[^0-9a-f]*'
        ),
        observed_at TEXT NOT NULL,
        reason TEXT,
        UNIQUE (release_id, status_observation_id),
        CHECK (dataset_release_id = release_id),
        CHECK (status != 'withdrawn' OR reason IS NOT NULL),
        FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE RESTRICT
    )""",
    "release_admission_observations": """CREATE TABLE release_admission_observations (
        admission_observation_id TEXT NOT NULL PRIMARY KEY,
        release_id TEXT NOT NULL,
        status_observation_id TEXT NOT NULL,
        admission_status TEXT NOT NULL CHECK (
            admission_status IN ('authorized', 'unconfirmed', 'denied')
        ),
        observed_at TEXT NOT NULL,
        reason TEXT,
        UNIQUE (release_id, status_observation_id, admission_observation_id),
        FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE RESTRICT,
        FOREIGN KEY (release_id, status_observation_id)
            REFERENCES release_status_observations(release_id, status_observation_id)
            ON DELETE RESTRICT
    )""",
    "cache_objects": """CREATE TABLE cache_objects (
        sha256 TEXT NOT NULL PRIMARY KEY CHECK (
            length(sha256) = 64 AND sha256 NOT GLOB '*[^0-9a-f]*'
        ),
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        relative_path TEXT NOT NULL UNIQUE,
        stored_at TEXT NOT NULL
    )""",
    "release_artifacts": """CREATE TABLE release_artifacts (
        release_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        PRIMARY KEY (release_id, artifact_id),
        UNIQUE (release_id, artifact_id, sha256),
        FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE RESTRICT,
        FOREIGN KEY (sha256) REFERENCES cache_objects(sha256) ON DELETE RESTRICT
    )""",
    "release_pins": """CREATE TABLE release_pins (
        run_id TEXT NOT NULL PRIMARY KEY,
        release_id TEXT NOT NULL,
        run_manifest_canonical BLOB NOT NULL CHECK (
            typeof(run_manifest_canonical) = 'blob' AND length(run_manifest_canonical) > 0
        ),
        run_manifest_hash_algorithm TEXT NOT NULL CHECK (
            run_manifest_hash_algorithm = 'sha256'
        ),
        run_manifest_hash_value TEXT NOT NULL CHECK (
            length(run_manifest_hash_value) = 64
            AND run_manifest_hash_value NOT GLOB '*[^0-9a-f]*'
        ),
        canonical_profile_version TEXT NOT NULL CHECK (
            canonical_profile_version = 'investsystem-canonical-json-v1'
        ),
        source_run_mode TEXT NOT NULL CHECK (
            source_run_mode IN ('research', 'backtest', 'paper', 'shadow')
        ),
        input_ref_schema_version TEXT NOT NULL,
        dataset_release_id TEXT NOT NULL,
        knowledge_cutoff TEXT NOT NULL,
        release_manifest_schema_version TEXT NOT NULL,
        input_manifest_hash_algorithm TEXT NOT NULL CHECK (
            input_manifest_hash_algorithm = 'sha256'
        ),
        input_manifest_hash_value TEXT NOT NULL CHECK (
            length(input_manifest_hash_value) = 64
            AND input_manifest_hash_value NOT GLOB '*[^0-9a-f]*'
        ),
        receipt_hash_algorithm TEXT NOT NULL CHECK (receipt_hash_algorithm = 'sha256'),
        receipt_hash_value TEXT NOT NULL CHECK (
            length(receipt_hash_value) = 64
            AND receipt_hash_value NOT GLOB '*[^0-9a-f]*'
        ),
        status_observation_id TEXT NOT NULL,
        admission_observation_id TEXT NOT NULL,
        pinned_at TEXT NOT NULL,
        UNIQUE (run_id, release_id),
        CHECK (dataset_release_id = release_id),
        FOREIGN KEY (release_id) REFERENCES releases(release_id) ON DELETE RESTRICT,
        FOREIGN KEY (release_id, status_observation_id, admission_observation_id)
            REFERENCES release_admission_observations(
                release_id, status_observation_id, admission_observation_id
            ) ON DELETE RESTRICT
    )""",
    "pin_artifacts": """CREATE TABLE pin_artifacts (
        run_id TEXT NOT NULL,
        release_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        sha256 TEXT NOT NULL,
        size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
        PRIMARY KEY (run_id, artifact_id),
        FOREIGN KEY (run_id, release_id) REFERENCES release_pins(run_id, release_id)
            ON DELETE RESTRICT,
        FOREIGN KEY (release_id, artifact_id, sha256)
            REFERENCES release_artifacts(release_id, artifact_id, sha256) ON DELETE RESTRICT,
        FOREIGN KEY (sha256) REFERENCES cache_objects(sha256) ON DELETE RESTRICT
    )""",
}

_INDEX_SQL = {
    "status_observations_release_idx": """CREATE INDEX status_observations_release_idx
        ON release_status_observations(release_id)""",
    "admission_observations_release_idx": """CREATE INDEX admission_observations_release_idx
        ON release_admission_observations(release_id)""",
    "release_artifacts_sha_idx": """CREATE INDEX release_artifacts_sha_idx
        ON release_artifacts(sha256)""",
    "release_pins_release_idx": """CREATE INDEX release_pins_release_idx
        ON release_pins(release_id)""",
    "pin_artifacts_sha_idx": """CREATE INDEX pin_artifacts_sha_idx
        ON pin_artifacts(sha256)""",
}

# (column name, declared type, not-null flag, primary-key ordinal)
_COLUMN_SPECS: dict[str, tuple[tuple[str, str, int, int], ...]] = {
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

_INDEX_SPECS = {
    "status_observations_release_idx": ("release_status_observations", ("release_id",)),
    "admission_observations_release_idx": (
        "release_admission_observations",
        ("release_id",),
    ),
    "release_artifacts_sha_idx": ("release_artifacts", ("sha256",)),
    "release_pins_release_idx": ("release_pins", ("release_id",)),
    "pin_artifacts_sha_idx": ("pin_artifacts", ("sha256",)),
}

_FOREIGN_KEY_SPECS: dict[
    str,
    set[tuple[str, tuple[str, ...], tuple[str, ...], str, str, str]],
] = {
    "releases": {
        (
            "release_status_observations",
            ("current_status_observation_id",),
            ("status_observation_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "release_admission_observations",
            ("current_admission_observation_id",),
            ("admission_observation_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
    },
    "release_status_observations": {
        (
            "releases",
            ("release_id",),
            ("release_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        )
    },
    "release_admission_observations": {
        (
            "releases",
            ("release_id",),
            ("release_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "release_status_observations",
            ("release_id", "status_observation_id"),
            ("release_id", "status_observation_id"),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
    },
    "cache_objects": set(),
    "release_artifacts": {
        (
            "releases",
            ("release_id",),
            ("release_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "cache_objects",
            ("sha256",),
            ("sha256",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
    },
    "release_pins": {
        (
            "releases",
            ("release_id",),
            ("release_id",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "release_admission_observations",
            ("release_id", "status_observation_id", "admission_observation_id"),
            ("release_id", "status_observation_id", "admission_observation_id"),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
    },
    "pin_artifacts": {
        (
            "release_pins",
            ("run_id", "release_id"),
            ("run_id", "release_id"),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "release_artifacts",
            ("release_id", "artifact_id", "sha256"),
            ("release_id", "artifact_id", "sha256"),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
        (
            "cache_objects",
            ("sha256",),
            ("sha256",),
            "NO ACTION",
            "RESTRICT",
            "NONE",
        ),
    },
}

_UNIQUE_INDEX_SPECS: dict[str, set[tuple[str, tuple[str, ...]]]] = {
    "releases": {
        ("pk", ("release_id",)),
        ("u", ("current_status_observation_id",)),
        ("u", ("current_admission_observation_id",)),
    },
    "release_status_observations": {
        ("pk", ("status_observation_id",)),
        ("u", ("release_id", "status_observation_id")),
    },
    "release_admission_observations": {
        ("pk", ("admission_observation_id",)),
        ("u", ("release_id", "status_observation_id", "admission_observation_id")),
    },
    "cache_objects": {
        ("pk", ("sha256",)),
        ("u", ("relative_path",)),
    },
    "release_artifacts": {
        ("pk", ("release_id", "artifact_id")),
        ("u", ("release_id", "artifact_id", "sha256")),
    },
    "release_pins": {
        ("pk", ("run_id",)),
        ("u", ("run_id", "release_id")),
    },
    "pin_artifacts": {("pk", ("run_id", "artifact_id"))},
}


class ReleaseCacheStore:
    """Persist status/admission observations and immutable SHA-256 addressed bytes."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        cache_root: str | Path,
        soft_limit_bytes: int = DEFAULT_CACHE_SOFT_LIMIT_BYTES,
        clock: Clock | None = None,
    ) -> None:
        if isinstance(soft_limit_bytes, bool) or not isinstance(soft_limit_bytes, int):
            raise TypeError("soft_limit_bytes must be an integer")
        if soft_limit_bytes < 0:
            raise ValueError("soft_limit_bytes must be non-negative")
        self.database_path = Path(database_path).resolve()
        requested_cache_root = Path(cache_root).absolute()
        if _is_link_or_junction(requested_cache_root):
            raise ValueError("cache_root must not be a symlink or junction")
        self.cache_root = requested_cache_root.resolve()
        if self.database_path == self.cache_root or self.database_path.is_relative_to(
            self.cache_root
        ):
            raise ValueError("database_path must not be inside cache_root")
        self.soft_limit_bytes = soft_limit_bytes
        self.clock = clock or SystemClock()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
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

    def _initialize(self) -> None:
        with self._connection() as connection:
            # The schema version and object inventory are protected by the same
            # writer lock as migration, so simultaneous first-open calls serialize.
            connection.execute("BEGIN IMMEDIATE")
            try:
                version = int(connection.execute("PRAGMA user_version").fetchone()[0])
                if version == 0:
                    if self._user_table_names(connection):
                        raise StorageSchemaError(
                            "refusing to adopt an unversioned non-empty database"
                        )
                    for statement in _TABLE_SQL.values():
                        connection.execute(statement)
                    for statement in _INDEX_SQL.values():
                        connection.execute(statement)
                    connection.execute(f"PRAGMA user_version = {STORAGE_SCHEMA_VERSION}")
                elif version != STORAGE_SCHEMA_VERSION:
                    raise StorageSchemaError(
                        f"unsupported storage schema {version}; expected {STORAGE_SCHEMA_VERSION}"
                    )
                self._verify_schema(connection)
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    @staticmethod
    def _user_table_names(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _pragma_rows(connection: sqlite3.Connection, pragma: str, name: str) -> list[sqlite3.Row]:
        if _ID_RE.fullmatch(name) is None:
            raise StorageSchemaError("unsafe schema identifier")
        return connection.execute(f'PRAGMA {pragma}("{name}")').fetchall()

    @classmethod
    def _verify_schema(cls, connection: sqlite3.Connection) -> None:
        if cls._user_table_names(connection) != set(_TABLE_SQL):
            raise StorageSchemaError("storage schema has missing or unknown user tables")

        extra_objects = connection.execute(
            "SELECT type, name FROM sqlite_schema "
            "WHERE type IN ('view', 'trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if extra_objects:
            raise StorageSchemaError("storage schema has unknown views or triggers")

        for table, expected in _COLUMN_SPECS.items():
            rows = cls._pragma_rows(connection, "table_xinfo", table)
            actual = tuple(
                (
                    str(row["name"]),
                    str(row["type"]).upper(),
                    int(row["notnull"]),
                    int(row["pk"]),
                )
                for row in rows
                if int(row["hidden"]) == 0
            )
            if actual != expected or any(row["dflt_value"] is not None for row in rows):
                raise StorageSchemaError(f"storage table metadata mismatch: {table}")

        explicit_indexes = {
            str(row["name"])
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'index' AND sql IS NOT NULL"
            )
        }
        if explicit_indexes != set(_INDEX_SPECS):
            raise StorageSchemaError("storage schema has missing or unknown user indexes")
        for index, (expected_table, expected_columns) in _INDEX_SPECS.items():
            entries = {
                str(row["name"]): row
                for row in cls._pragma_rows(connection, "index_list", expected_table)
            }
            metadata = entries.get(index)
            if (
                metadata is None
                or int(metadata["unique"]) != 0
                or str(metadata["origin"]) != "c"
                or int(metadata["partial"]) != 0
            ):
                raise StorageSchemaError(f"storage index metadata mismatch: {index}")
            key_rows = tuple(
                row
                for row in cls._pragma_rows(connection, "index_xinfo", index)
                if int(row["key"]) == 1
            )
            columns = tuple(str(row["name"]) for row in key_rows)
            if columns != expected_columns or any(
                int(row["desc"]) != 0 or str(row["coll"]) != "BINARY" for row in key_rows
            ):
                raise StorageSchemaError(f"storage index columns mismatch: {index}")

        for table, expected_foreign_keys in _FOREIGN_KEY_SPECS.items():
            grouped: dict[int, list[sqlite3.Row]] = {}
            for row in cls._pragma_rows(connection, "foreign_key_list", table):
                grouped.setdefault(int(row["id"]), []).append(row)
            actual_foreign_keys = set()
            for rows in grouped.values():
                ordered = sorted(rows, key=lambda row: int(row["seq"]))
                first = ordered[0]
                actual_foreign_keys.add(
                    (
                        str(first["table"]),
                        tuple(str(row["from"]) for row in ordered),
                        tuple(str(row["to"]) for row in ordered),
                        str(first["on_update"]),
                        str(first["on_delete"]),
                        str(first["match"]),
                    )
                )
            if actual_foreign_keys != expected_foreign_keys:
                raise StorageSchemaError(f"storage foreign-key mismatch: {table}")

        for table, expected_unique_indexes in _UNIQUE_INDEX_SPECS.items():
            actual_unique_indexes: set[tuple[str, tuple[str, ...]]] = set()
            for row in cls._pragma_rows(connection, "index_list", table):
                origin = str(row["origin"])
                if origin not in {"pk", "u"}:
                    continue
                if int(row["unique"]) != 1 or int(row["partial"]) != 0:
                    raise StorageSchemaError(f"storage unique-index metadata mismatch: {table}")
                key_rows = tuple(
                    column
                    for column in cls._pragma_rows(connection, "index_xinfo", str(row["name"]))
                    if int(column["key"]) == 1
                )
                if any(
                    int(column["desc"]) != 0 or str(column["coll"]) != "BINARY"
                    for column in key_rows
                ):
                    raise StorageSchemaError(f"storage unique-index columns mismatch: {table}")
                columns = tuple(str(column["name"]) for column in key_rows)
                actual_unique_indexes.add((origin, columns))
            if actual_unique_indexes != expected_unique_indexes:
                raise StorageSchemaError(f"storage unique/primary constraint mismatch: {table}")

        quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick_check != "ok":
            raise StorageSchemaError(f"SQLite quick_check failed: {quick_check}")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise StorageSchemaError("SQLite foreign_key_check failed")
        cls._verify_check_constraints(connection)

    @staticmethod
    def _expect_constraint_failure(
        connection: sqlite3.Connection,
        *,
        label: str,
        statement: str,
        parameters: tuple[object, ...],
    ) -> None:
        connection.execute("SAVEPOINT schema_constraint_case")
        try:
            try:
                connection.execute(statement, parameters)
            except sqlite3.IntegrityError:
                pass
            else:
                raise StorageSchemaError(f"storage CHECK constraint missing: {label}")
        finally:
            connection.execute("ROLLBACK TO schema_constraint_case")
            connection.execute("RELEASE schema_constraint_case")

    @classmethod
    def _verify_check_constraints(cls, connection: sqlite3.Connection) -> None:
        """Behaviorally verify CHECKs that SQLite does not expose through PRAGMA."""

        token = uuid4().hex
        release_id = f"schema_probe_release_{token}"
        status_id = f"schema_probe_status_{token}"
        admission_id = f"schema_probe_admission_{token}"
        run_id = f"schema_probe_run_{token}"
        artifact_id = f"schema_probe_artifact_{token}"
        object_hash = sha256(token.encode()).hexdigest()
        manifest_hash = sha256(f"manifest:{token}".encode()).hexdigest()
        input_hash = sha256(f"input:{token}".encode()).hexdigest()
        receipt_hash = sha256(f"receipt:{token}".encode()).hexdigest()
        now = "2000-01-01T00:00:00.000000Z"
        identity = ("0.1.0", release_id, now, "0.1.0", "sha256", input_hash)

        connection.execute("SAVEPOINT schema_constraint_probe")
        try:
            connection.execute("INSERT INTO releases VALUES (?, NULL, NULL, ?)", (release_id, now))
            connection.execute(
                """INSERT INTO release_status_observations
                   VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, NULL)""",
                (status_id, release_id, *identity, now),
            )
            connection.execute(
                "UPDATE releases SET current_status_observation_id = ? WHERE release_id = ?",
                (status_id, release_id),
            )
            connection.execute(
                """INSERT INTO release_admission_observations
                   VALUES (?, ?, ?, 'authorized', ?, NULL)""",
                (admission_id, release_id, status_id, now),
            )
            connection.execute(
                "UPDATE releases SET current_admission_observation_id = ? WHERE release_id = ?",
                (admission_id, release_id),
            )
            relative = f"sha256/{object_hash[:2]}/{object_hash}"
            connection.execute(
                "INSERT INTO cache_objects VALUES (?, 1, ?, ?)",
                (object_hash, relative, now),
            )
            connection.execute(
                "INSERT INTO release_artifacts VALUES (?, ?, ?)",
                (release_id, artifact_id, object_hash),
            )
            connection.execute(
                """INSERT INTO release_pins VALUES (
                    ?, ?, X'7B7D', 'sha256', ?, ?, 'research', ?, ?, ?, ?,
                    'sha256', ?, 'sha256', ?, ?, ?, ?
                )""",
                (
                    run_id,
                    release_id,
                    manifest_hash,
                    STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                    identity[0],
                    release_id,
                    now,
                    identity[3],
                    input_hash,
                    receipt_hash,
                    status_id,
                    admission_id,
                    now,
                ),
            )

            status_parameters = (
                f"bad_status_{token}",
                release_id,
                *identity,
                now,
                None,
            )
            cls._expect_constraint_failure(
                connection,
                label="provider status enum",
                statement="INSERT INTO release_status_observations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                parameters=(
                    status_parameters[0],
                    status_parameters[1],
                    "invalid",
                    *status_parameters[2:],
                ),
            )
            cls._expect_constraint_failure(
                connection,
                label="withdrawn reason",
                statement="INSERT INTO release_status_observations VALUES (?, ?, 'withdrawn', ?, ?, ?, ?, ?, ?, ?, NULL)",
                parameters=(f"bad_withdrawn_{token}", release_id, *identity, now),
            )
            cls._expect_constraint_failure(
                connection,
                label="status manifest digest",
                statement="INSERT INTO release_status_observations VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, NULL)",
                parameters=(
                    f"bad_status_hash_{token}",
                    release_id,
                    identity[0],
                    release_id,
                    now,
                    identity[3],
                    "sha256",
                    "bad",
                    now,
                ),
            )
            cls._expect_constraint_failure(
                connection,
                label="status manifest hash algorithm",
                statement="INSERT INTO release_status_observations VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, NULL)",
                parameters=(
                    f"bad_status_algorithm_{token}",
                    release_id,
                    identity[0],
                    release_id,
                    now,
                    identity[3],
                    "sha1",
                    input_hash,
                    now,
                ),
            )
            cls._expect_constraint_failure(
                connection,
                label="status dataset identity",
                statement="INSERT INTO release_status_observations VALUES (?, ?, 'published', ?, ?, ?, ?, ?, ?, ?, NULL)",
                parameters=(
                    f"bad_status_dataset_{token}",
                    release_id,
                    identity[0],
                    f"other_release_{token}",
                    now,
                    identity[3],
                    "sha256",
                    input_hash,
                    now,
                ),
            )
            cls._expect_constraint_failure(
                connection,
                label="admission enum",
                statement="INSERT INTO release_admission_observations VALUES (?, ?, ?, ?, ?, NULL)",
                parameters=(f"bad_admission_{token}", release_id, status_id, "invalid", now),
            )
            cls._expect_constraint_failure(
                connection,
                label="cache digest",
                statement="INSERT INTO cache_objects VALUES ('bad', 1, ?, ?)",
                parameters=(f"bad/path/{token}", now),
            )
            negative_hash = sha256(f"negative:{token}".encode()).hexdigest()
            cls._expect_constraint_failure(
                connection,
                label="cache size",
                statement="INSERT INTO cache_objects VALUES (?, -1, ?, ?)",
                parameters=(negative_hash, f"bad/negative/{token}", now),
            )
            cls._expect_constraint_failure(
                connection,
                label="source run mode",
                statement="""INSERT INTO release_pins VALUES (
                    ?, ?, X'7B7D', 'sha256', ?, ?, 'audit_replay', ?, ?, ?, ?,
                    'sha256', ?, 'sha256', ?, ?, ?, ?
                )""",
                parameters=(
                    f"bad_mode_{token}",
                    release_id,
                    manifest_hash,
                    STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                    identity[0],
                    release_id,
                    now,
                    identity[3],
                    input_hash,
                    receipt_hash,
                    status_id,
                    admission_id,
                    now,
                ),
            )
            base_pin_values: list[object] = [
                f"bad_pin_{token}",
                release_id,
                b"{}",
                "sha256",
                manifest_hash,
                STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                "research",
                identity[0],
                release_id,
                now,
                identity[3],
                "sha256",
                input_hash,
                "sha256",
                receipt_hash,
                status_id,
                admission_id,
                now,
            ]
            invalid_pin_fields: tuple[tuple[str, int, object], ...] = (
                ("manifest canonical type", 2, "{}"),
                ("manifest canonical empty", 2, b""),
                ("manifest hash algorithm", 3, "sha1"),
                ("manifest hash value", 4, "bad"),
                ("canonical profile", 5, "unknown-profile"),
                ("source mode", 6, "audit_replay"),
                ("pin dataset identity", 8, f"other_release_{token}"),
                ("input manifest hash algorithm", 11, "sha1"),
                ("input manifest hash value", 12, "bad"),
                ("receipt hash algorithm", 13, "sha1"),
                ("receipt hash value", 14, "bad"),
            )
            for case_number, (label, value_index, invalid_value) in enumerate(invalid_pin_fields):
                values = list(base_pin_values)
                values[0] = f"bad_pin_{case_number}_{token}"
                values[value_index] = invalid_value
                cls._expect_constraint_failure(
                    connection,
                    label=label,
                    statement=(
                        "INSERT INTO release_pins VALUES "
                        "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                    ),
                    parameters=tuple(values),
                )
            cls._expect_constraint_failure(
                connection,
                label="pinned artifact size",
                statement="INSERT INTO pin_artifacts VALUES (?, ?, ?, ?, -1)",
                parameters=(run_id, release_id, artifact_id, object_hash),
            )
        finally:
            connection.execute("ROLLBACK TO schema_constraint_probe")
            connection.execute("RELEASE schema_constraint_probe")

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
        path = self.cache_root / self._relative_path(digest)
        self._assert_safe_cache_path(path)
        return path

    def _verified_read(self, path: Path, digest: str, size_bytes: int) -> bytes:
        self._assert_safe_cache_path(path)
        try:
            link_count = path.stat().st_nlink
            if link_count > 1:
                raise CacheIntegrityError(
                    f"cached object has multiple hard links and is not independently owned: {digest}"
                )
            content = path.read_bytes()
        except OSError as exc:
            raise CacheIntegrityError(f"cached object unavailable: {digest}") from exc
        actual = sha256(content).hexdigest()
        if len(content) != size_bytes or actual != digest:
            raise CacheIntegrityError(f"cached object failed size/hash validation: {digest}")
        return content

    def _atomic_write(self, content: bytes, digest: str) -> Path:
        target = self._object_path(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        self._assert_safe_cache_path(target)
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
    def _current_access(connection: sqlite3.Connection, release_id: str) -> ReleaseAccessContext:
        row = connection.execute(
            """SELECT status.status AS provider_status,
                      status.status_observation_id,
                      admission.admission_status,
                      admission.admission_observation_id,
                      admission.status_observation_id AS admission_status_observation_id
               FROM releases
               LEFT JOIN release_status_observations AS status
                 ON status.status_observation_id = releases.current_status_observation_id
               LEFT JOIN release_admission_observations AS admission
                 ON admission.admission_observation_id = releases.current_admission_observation_id
               WHERE releases.release_id = ?""",
            (release_id,),
        ).fetchone()
        if row is None:
            return ReleaseAccessContext(None, None, None, None, None)
        return ReleaseAccessContext(
            ReleaseStatus(row["provider_status"]) if row["provider_status"] else None,
            row["status_observation_id"],
            AdmissionStatus(row["admission_status"]) if row["admission_status"] else None,
            row["admission_observation_id"],
            row["admission_status_observation_id"],
        )

    @staticmethod
    def _input_ref_values(input_ref: StrategyInputRef) -> tuple[str, ...]:
        return (
            input_ref.schema_version,
            input_ref.dataset_release_id,
            format_utc(input_ref.knowledge_cutoff),
            input_ref.release_manifest_schema_version,
            input_ref.manifest_hash.algorithm,
            input_ref.manifest_hash.value,
        )

    def record_release_status(
        self,
        release_id: str,
        *,
        status: ReleaseStatus | str,
        status_observation_id: str,
        strategy_input_ref: StrategyInputRef,
        reason: str | None = None,
    ) -> bool:
        """Append one immutable provider observation and invalidate prior admission."""

        release_id = _require_id("release_id", release_id, exact_release=True)
        status_observation_id = _require_id("status_observation_id", status_observation_id)
        if not isinstance(strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if strategy_input_ref.dataset_release_id != release_id:
            raise ValueError("strategy_input_ref release does not match release_id")
        input_identity = self._input_ref_values(strategy_input_ref)
        try:
            provider_status = ReleaseStatus(status)
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown provider release status") from exc
        normalized_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None
        if provider_status is ReleaseStatus.WITHDRAWN and normalized_reason is None:
            raise ValueError("withdrawn status requires a reason")

        with self._write() as connection:
            existing = connection.execute(
                """SELECT * FROM release_status_observations
                   WHERE status_observation_id = ?""",
                (status_observation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["release_id"] != release_id
                    or existing["status"] != provider_status.value
                    or existing["input_ref_schema_version"] != strategy_input_ref.schema_version
                    or existing["dataset_release_id"] != strategy_input_ref.dataset_release_id
                    or existing["knowledge_cutoff"]
                    != format_utc(strategy_input_ref.knowledge_cutoff)
                    or existing["release_manifest_schema_version"]
                    != strategy_input_ref.release_manifest_schema_version
                    or existing["manifest_hash_algorithm"]
                    != strategy_input_ref.manifest_hash.algorithm
                    or existing["manifest_hash_value"] != strategy_input_ref.manifest_hash.value
                    or existing["reason"] != normalized_reason
                ):
                    raise ImmutableMappingError("provider status observation was remapped")
                return False

            current = self._current_access(connection, release_id)
            if current.provider_status is ReleaseStatus.WITHDRAWN:
                raise ReleaseAccessError("withdrawn provider status is irreversible")
            frozen_identity = connection.execute(
                """SELECT input_ref_schema_version, dataset_release_id, knowledge_cutoff,
                          release_manifest_schema_version, manifest_hash_algorithm,
                          manifest_hash_value
                   FROM releases
                   JOIN release_status_observations AS status
                     ON status.status_observation_id = releases.current_status_observation_id
                   WHERE releases.release_id = ?""",
                (release_id,),
            ).fetchone()
            if frozen_identity is not None and tuple(frozen_identity) != input_identity:
                raise ImmutableMappingError("release input identity is immutable")
            now = self._now()
            if current.provider_status_observation_id is None:
                connection.execute(
                    "INSERT OR IGNORE INTO releases VALUES (?, NULL, NULL, ?)",
                    (release_id, now),
                )
            connection.execute(
                """INSERT INTO release_status_observations
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    status_observation_id,
                    release_id,
                    provider_status.value,
                    *input_identity,
                    now,
                    normalized_reason,
                ),
            )
            connection.execute(
                """UPDATE releases
                   SET current_status_observation_id = ?, current_admission_observation_id = NULL
                   WHERE release_id = ?""",
                (status_observation_id, release_id),
            )
            return True

    def record_release_admission(
        self,
        release_id: str,
        *,
        status_observation_id: str,
        admission_observation_id: str,
        admission_status: AdmissionStatus | str,
        reason: str | None = None,
    ) -> bool:
        """Record a local decision for the exact latest provider observation."""

        release_id = _require_id("release_id", release_id, exact_release=True)
        status_observation_id = _require_id("status_observation_id", status_observation_id)
        admission_observation_id = _require_id("admission_observation_id", admission_observation_id)
        try:
            local_status = AdmissionStatus(admission_status)
        except (TypeError, ValueError) as exc:
            raise ValueError("unknown admission status") from exc
        normalized_reason = reason.strip() if isinstance(reason, str) and reason.strip() else None

        with self._write() as connection:
            existing = connection.execute(
                """SELECT release_id, status_observation_id, admission_status, reason
                   FROM release_admission_observations
                   WHERE admission_observation_id = ?""",
                (admission_observation_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["release_id"] != release_id
                    or existing["status_observation_id"] != status_observation_id
                    or existing["admission_status"] != local_status.value
                    or existing["reason"] != normalized_reason
                ):
                    raise ImmutableMappingError("admission observation was remapped")
                return False

            current = self._current_access(connection, release_id)
            if current.provider_status is None:
                raise ReleaseAccessError("provider status is not recorded")
            if current.provider_status is ReleaseStatus.WITHDRAWN:
                raise ReleaseAccessError("withdrawn release cannot be admitted")
            if current.provider_status_observation_id != status_observation_id:
                raise ReleaseAccessError(
                    "admission does not target the latest provider observation"
                )
            connection.execute(
                """INSERT INTO release_admission_observations
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    admission_observation_id,
                    release_id,
                    status_observation_id,
                    local_status.value,
                    self._now(),
                    normalized_reason,
                ),
            )
            connection.execute(
                "UPDATE releases SET current_admission_observation_id = ? WHERE release_id = ?",
                (admission_observation_id, release_id),
            )
            return True

    def quota_report(self, *, verify_integrity: bool = True) -> CacheQuotaReport:
        """Report soft-limit usage and explicit missing/corrupt/scan anomalies.

        ``verify_integrity=False`` performs capacity inventory without hashing file
        contents; missing, metadata, and scan failures are still reported.
        """

        # Revalidate before any database inventory or filesystem walk.  This
        # catches cache_root itself, or one of its ancestors, being replaced by
        # a symlink/junction after store initialization.
        self._assert_safe_cache_path(self.cache_root)
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT cache_objects.sha256, cache_objects.size_bytes,
                          cache_objects.relative_path,
                          EXISTS (
                              SELECT 1 FROM pin_artifacts
                              WHERE pin_artifacts.sha256 = cache_objects.sha256
                          ) AS is_pinned
                   FROM cache_objects"""
            ).fetchall()
            registered_bytes = sum(int(row["size_bytes"]) for row in rows)
            pinned_bytes = int(
                connection.execute(
                    """SELECT COALESCE(SUM(size_bytes), 0) FROM cache_objects
                       WHERE sha256 IN (SELECT DISTINCT sha256 FROM pin_artifacts)"""
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
            # Close the check/use gap as far as pathlib/os.walk permits: never
            # stat or hash entries from a directory whose resolution changed
            # after the entry check above.
            self._assert_safe_cache_path(Path(directory))
            for subdirectory in tuple(subdirectories):
                child = Path(directory) / subdirectory
                if _is_link_or_junction(child):
                    relative = child.relative_to(self.cache_root).as_posix()
                    issues.append(
                        CacheScanIssue(
                            CacheIssueKind.SCAN_FAILURE,
                            relative,
                            "cache directory is a symlink or junction",
                        )
                    )
                    subdirectories.remove(subdirectory)
            for filename in filenames:
                path = Path(directory) / filename
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
        physical_bytes = sum(size for _path, size, _link_count in physical.values())
        orphan_bytes = sum(
            size
            for relative, (_path, size, _link_count) in physical.items()
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

    def put_artifact(
        self,
        *,
        release_id: str,
        artifact_id: str,
        content: bytes,
        expected_sha256: str,
    ) -> CachedArtifact:
        """Validate and atomically store one immutable artifact mapping."""

        release_id = _require_id("release_id", release_id, exact_release=True)
        artifact_id = _require_id("artifact_id", artifact_id)
        expected_sha256 = _require_digest(expected_sha256)
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        actual = sha256(content).hexdigest()
        if actual != expected_sha256:
            raise CacheIntegrityError(
                f"artifact hash mismatch: expected {expected_sha256}, got {actual}"
            )

        relative = self._relative_path(expected_sha256).as_posix()
        target = self._object_path(expected_sha256)
        with self._write() as connection:
            current = self._current_access(connection, release_id)
            if current.provider_status is None:
                raise ReleaseAccessError("provider status is not recorded")
            if current.provider_status is ReleaseStatus.WITHDRAWN:
                raise ReleaseAccessError("withdrawn release cannot accept artifacts")
            link = connection.execute(
                "SELECT sha256 FROM release_artifacts WHERE release_id = ? AND artifact_id = ?",
                (release_id, artifact_id),
            ).fetchone()
            if link is not None and link["sha256"] != expected_sha256:
                raise ImmutableMappingError("artifact identifier already maps to different bytes")

            cache_object = connection.execute(
                "SELECT size_bytes, relative_path FROM cache_objects WHERE sha256 = ?",
                (expected_sha256,),
            ).fetchone()
            if cache_object is not None:
                if (
                    cache_object["size_bytes"] != len(content)
                    or cache_object["relative_path"] != relative
                ):
                    raise CacheIntegrityError("content metadata conflict")
                self._verified_read(target, expected_sha256, len(content))
            else:
                if target.exists():
                    self._verified_read(target, expected_sha256, len(content))
                else:
                    self._atomic_write(content, expected_sha256)
                connection.execute(
                    "INSERT INTO cache_objects VALUES (?, ?, ?, ?)",
                    (expected_sha256, len(content), relative, self._now()),
                )
            if link is None:
                connection.execute(
                    "INSERT INTO release_artifacts VALUES (?, ?, ?)",
                    (release_id, artifact_id, expected_sha256),
                )
        return CachedArtifact(release_id, artifact_id, expected_sha256, len(content), target)

    @staticmethod
    def _manifest_values(manifest: StrategyRunManifest) -> tuple[bytes, str]:
        canonical = canonical_json_bytes(manifest)
        return canonical, sha256(canonical).hexdigest()

    @staticmethod
    def _artifact_ids(values: Iterable[str]) -> tuple[str, ...]:
        if isinstance(values, (str, bytes)):
            raise TypeError("artifact_ids must be an iterable of identifiers")
        identifiers = tuple(_require_id("artifact_id", value) for value in values)
        if not identifiers:
            raise ValueError("artifact_ids must not be empty")
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("artifact_ids must not contain duplicates")
        return tuple(sorted(identifiers))

    def pin_run(
        self,
        manifest: StrategyRunManifest,
        *,
        artifact_ids: Iterable[str],
    ) -> bool:
        """Atomically admit a run and pin its exact caller-declared artifact subset.

        Stage 1 trusts ``artifact_ids`` supplied by the caller.  Stage 2 will
        reconcile those identifiers item-by-item with the consumption receipt.
        """

        if not isinstance(manifest, StrategyRunManifest):
            raise TypeError("manifest must be a StrategyRunManifest")
        identifiers = self._artifact_ids(artifact_ids)
        admission_observation_id = _require_id(
            "release_admission_observation_id",
            manifest.release_admission_observation_id,
        )
        release_id = manifest.strategy_input_ref.dataset_release_id
        canonical, manifest_hash = self._manifest_values(manifest)
        input_ref = manifest.strategy_input_ref

        with self._write() as connection:
            existing = connection.execute(
                "SELECT * FROM release_pins WHERE run_id = ?", (manifest.run_id,)
            ).fetchone()
            if existing is not None:
                pinned_ids = tuple(
                    str(row[0])
                    for row in connection.execute(
                        "SELECT artifact_id FROM pin_artifacts "
                        "WHERE run_id = ? ORDER BY artifact_id",
                        (manifest.run_id,),
                    )
                )
                if (
                    bytes(existing["run_manifest_canonical"]) != canonical
                    or existing["run_manifest_hash_value"] != manifest_hash
                    or existing["canonical_profile_version"]
                    != STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION
                    or existing["admission_observation_id"] != admission_observation_id
                    or pinned_ids != identifiers
                ):
                    raise ImmutableMappingError("run_id already pins different inputs")
                return False

            current = self._current_access(connection, release_id)
            if current.provider_status is not ReleaseStatus.PUBLISHED:
                raise ReleaseAccessError("run admission requires latest provider status published")
            if current.provider_status_observation_id != manifest.release_status_observation_id:
                raise ReleaseAccessError("manifest does not cite latest provider observation")
            status_identity = connection.execute(
                """SELECT input_ref_schema_version, dataset_release_id, knowledge_cutoff,
                          release_manifest_schema_version, manifest_hash_algorithm,
                          manifest_hash_value
                   FROM release_status_observations
                   WHERE status_observation_id = ?""",
                (manifest.release_status_observation_id,),
            ).fetchone()
            expected_status_identity = (
                input_ref.schema_version,
                input_ref.dataset_release_id,
                format_utc(input_ref.knowledge_cutoff),
                input_ref.release_manifest_schema_version,
                input_ref.manifest_hash.algorithm,
                input_ref.manifest_hash.value,
            )
            if status_identity is None or tuple(status_identity) != expected_status_identity:
                raise ReleaseAccessError(
                    "provider observation does not bind the manifest input identity"
                )
            if current.admission_observation_id != admission_observation_id:
                raise ReleaseAccessError("run does not cite the current local admission")
            if not current.authorized:
                raise ReleaseAccessError("current local admission is not authorized")

            placeholders = ", ".join("?" for _identifier in identifiers)
            rows = connection.execute(
                f"""SELECT release_artifacts.artifact_id, release_artifacts.sha256,
                           cache_objects.size_bytes, cache_objects.relative_path
                    FROM release_artifacts JOIN cache_objects USING (sha256)
                    WHERE release_id = ? AND artifact_id IN ({placeholders})
                    ORDER BY artifact_id""",
                (release_id, *identifiers),
            ).fetchall()
            if tuple(str(row["artifact_id"]) for row in rows) != identifiers:
                raise ReleaseAccessError("one or more declared run artifacts are not cached")
            for row in rows:
                expected_relative = self._relative_path(str(row["sha256"])).as_posix()
                if row["relative_path"] != expected_relative:
                    raise CacheIntegrityError("content path metadata conflict")
                self._verified_read(
                    self.cache_root / expected_relative,
                    str(row["sha256"]),
                    int(row["size_bytes"]),
                )

            connection.execute(
                """INSERT INTO release_pins VALUES (
                    ?, ?, ?, 'sha256', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )""",
                (
                    manifest.run_id,
                    release_id,
                    canonical,
                    manifest_hash,
                    STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION,
                    manifest.run_mode.value,
                    input_ref.schema_version,
                    input_ref.dataset_release_id,
                    format_utc(input_ref.knowledge_cutoff),
                    input_ref.release_manifest_schema_version,
                    input_ref.manifest_hash.algorithm,
                    input_ref.manifest_hash.value,
                    manifest.artifact_consumption_receipt_hash.algorithm,
                    manifest.artifact_consumption_receipt_hash.value,
                    manifest.release_status_observation_id,
                    admission_observation_id,
                    self._now(),
                ),
            )
            for row in rows:
                connection.execute(
                    "INSERT INTO pin_artifacts VALUES (?, ?, ?, ?, ?)",
                    (
                        manifest.run_id,
                        release_id,
                        row["artifact_id"],
                        row["sha256"],
                        row["size_bytes"],
                    ),
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
        audit_request: AuditReplayRequest | None = None,
    ) -> ArtifactRead:
        """Read one pinned artifact and return explicit access/audit context."""

        artifact_id = _require_id("artifact_id", artifact_id)
        access_purpose = self._purpose(purpose)
        if not isinstance(source_manifest, StrategyRunManifest):
            raise TypeError("source_manifest must be the original StrategyRunManifest")
        canonical, manifest_hash = self._manifest_values(source_manifest)
        release_id = source_manifest.strategy_input_ref.dataset_release_id

        if access_purpose is RunPurpose.AUDIT_REPLAY:
            if not isinstance(audit_request, AuditReplayRequest):
                raise ReleaseAccessError("audit replay requires an AuditReplayRequest")
            if (
                audit_request.source_run_id != source_manifest.run_id
                or audit_request.source_manifest_hash != manifest_hash
            ):
                raise ReleaseAccessError("audit request does not identify the source manifest")
        elif audit_request is not None:
            raise ReleaseAccessError("AuditReplayRequest cannot authorize an ordinary run")

        with self._connection() as connection:
            connection.execute("BEGIN")
            try:
                pin = connection.execute(
                    "SELECT * FROM release_pins WHERE run_id = ?", (source_manifest.run_id,)
                ).fetchone()
                if pin is None:
                    raise ReleaseAccessError("source run is not admitted and pinned")
                expected = {
                    "release_id": release_id,
                    "run_manifest_hash_algorithm": "sha256",
                    "run_manifest_hash_value": manifest_hash,
                    "canonical_profile_version": (STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION),
                    "source_run_mode": source_manifest.run_mode.value,
                    "input_ref_schema_version": source_manifest.strategy_input_ref.schema_version,
                    "dataset_release_id": release_id,
                    "knowledge_cutoff": format_utc(
                        source_manifest.strategy_input_ref.knowledge_cutoff
                    ),
                    "release_manifest_schema_version": (
                        source_manifest.strategy_input_ref.release_manifest_schema_version
                    ),
                    "input_manifest_hash_algorithm": (
                        source_manifest.strategy_input_ref.manifest_hash.algorithm
                    ),
                    "input_manifest_hash_value": (
                        source_manifest.strategy_input_ref.manifest_hash.value
                    ),
                    "receipt_hash_algorithm": (
                        source_manifest.artifact_consumption_receipt_hash.algorithm
                    ),
                    "receipt_hash_value": (source_manifest.artifact_consumption_receipt_hash.value),
                    "status_observation_id": (source_manifest.release_status_observation_id),
                    "admission_observation_id": (source_manifest.release_admission_observation_id),
                }
                if bytes(pin["run_manifest_canonical"]) != canonical or any(
                    pin[name] != value for name, value in expected.items()
                ):
                    raise CacheIntegrityError("source manifest does not match persisted pin")

                row = connection.execute(
                    """SELECT pin_artifacts.sha256, pin_artifacts.size_bytes,
                              cache_objects.relative_path,
                              release_artifacts.sha256 AS mapped_sha256
                       FROM pin_artifacts JOIN cache_objects USING (sha256)
                       JOIN release_artifacts
                         ON release_artifacts.release_id = pin_artifacts.release_id
                        AND release_artifacts.artifact_id = pin_artifacts.artifact_id
                       WHERE pin_artifacts.run_id = ? AND pin_artifacts.artifact_id = ?""",
                    (source_manifest.run_id, artifact_id),
                ).fetchone()
                if row is None:
                    raise ReleaseAccessError("artifact is not in the source run snapshot")
                digest = str(row["sha256"])
                if row["mapped_sha256"] != digest:
                    raise CacheIntegrityError("pinned artifact mapping changed")
                size_bytes = int(row["size_bytes"])
                expected_relative = self._relative_path(digest).as_posix()
                if row["relative_path"] != expected_relative:
                    raise CacheIntegrityError("content path metadata conflict")
                path = self.cache_root / expected_relative
                content = self._verified_read(path, digest, size_bytes)
                current_access = self._current_access(connection, release_id)
                if access_purpose is RunPurpose.NEW_RUN and (
                    not current_access.authorized
                    or current_access.provider_status_observation_id != pin["status_observation_id"]
                    or current_access.admission_observation_id != pin["admission_observation_id"]
                ):
                    raise ReleaseAccessError(
                        "ordinary run access lost current provider/admission authorization"
                    )
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()
                return ArtifactRead(
                    content=content,
                    artifact=CachedArtifact(release_id, artifact_id, digest, size_bytes, path),
                    purpose=access_purpose,
                    source_run_id=source_manifest.run_id,
                    source_manifest_hash=manifest_hash,
                    source_manifest_profile_version=(
                        STRATEGY_RUN_MANIFEST_CANONICAL_PROFILE_VERSION
                    ),
                    source_status_observation_id=pin["status_observation_id"],
                    source_admission_observation_id=pin["admission_observation_id"],
                    current_access=current_access,
                )
