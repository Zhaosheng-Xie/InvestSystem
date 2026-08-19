"""Isolated validation-only persistence for the approved Stage 6B seal.

The store is intentionally separate from InvestSystem's formal SQLite state.
It accepts only a fully reconciled :class:`Stage6BHistoricalAdmissionEnvelope`,
stages immutable bytes in its own CAS before opening the write transaction,
and writes the admission seal last in one ``BEGIN IMMEDIATE`` transaction.
It performs no network I/O and exposes no strategy-evaluator seam.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_json_bytes, format_utc, normalize_utc
from invest_system.models import CanonicalModel, HashDigest
from invest_system.retention import ArtifactPayload, ReleaseManifestPayload

from .stage6b_admission import (
    STAGE6B_ADMISSION_SCHEMA_VERSION,
    STAGE6B_CONFIRMATION_TTL,
    STAGE6B_MAX_CLOCK_SKEW,
    STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE,
    STAGE6B_TRANSACTION_PROFILE,
    Stage6BAdmissionStatus,
    Stage6BHistoricalAdmissionEnvelope,
    Stage6BStatusResponsePayload,
)

STAGE6B_VALIDATION_STORAGE_SCHEMA_VERSION = "stage6b-validation-v1"
STAGE6B_VALIDATION_SEAL_SCHEMA_VERSION = "1.0.0"
_REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

type FailureHook = Callable[[str], None]


class Stage6BValidationStoreError(RuntimeError):
    """Stable fail-closed validation-store error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _digest(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _identity_hash(payload: Mapping[str, Any]) -> HashDigest:
    return _digest(sha256(canonical_json_bytes(payload)).hexdigest())


def _strict_bool(field_name: str, value: bool, *, expected: bool) -> None:
    if type(value) is not bool or value is not expected:
        raise ValueError(f"{field_name} must be {expected!r}")


@dataclass(frozen=True, slots=True)
class Stage6BHistoricalRunAdmissionSeal(CanonicalModel):
    """The only visible completion marker emitted by the validation store."""

    schema_version: str
    seal_id: str
    run_id: str
    request_hash: HashDigest
    envelope_hash: HashDigest
    manifest_hash: HashDigest
    confirmation_id: str
    confirmation_hash: HashDigest
    closure_hash: HashDigest
    commit_generation: int
    transaction_id: str
    committed_at: datetime
    status: Stage6BAdmissionStatus
    transaction_profile: str
    validation_only: bool
    authority_eligible: bool
    strategy_evaluator_calls: int
    seal_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != STAGE6B_VALIDATION_SEAL_SCHEMA_VERSION:
            raise ValueError("unsupported Stage 6B seal schema_version")
        for field_name in ("seal_id", "run_id", "confirmation_id", "transaction_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{field_name} must be non-empty")
        for field_name in (
            "request_hash",
            "envelope_hash",
            "manifest_hash",
            "confirmation_hash",
            "closure_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        if isinstance(self.commit_generation, bool) or not isinstance(self.commit_generation, int):
            raise TypeError("commit_generation must be an integer")
        if self.commit_generation < 1:
            raise ValueError("commit_generation must be positive")
        object.__setattr__(
            self,
            "committed_at",
            normalize_utc(self.committed_at, field_name="committed_at"),
        )
        if self.status is not Stage6BAdmissionStatus.SEALED_VALIDATION_ONLY:
            raise ValueError("validation seal status differs")
        if self.transaction_profile != STAGE6B_TRANSACTION_PROFILE:
            raise ValueError("validation seal transaction profile differs")
        _strict_bool("validation_only", self.validation_only, expected=True)
        _strict_bool("authority_eligible", self.authority_eligible, expected=False)
        if self.strategy_evaluator_calls != 0:
            raise ValueError("strategy_evaluator_calls must be zero")
        expected = _identity_hash(self.identity_payload())
        if not isinstance(self.seal_hash, HashDigest) or self.seal_hash != expected:
            raise ValueError("seal_hash differs")

    def identity_payload(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_json_value().items() if key != "seal_hash"}

    @classmethod
    def create(
        cls,
        *,
        envelope: Stage6BHistoricalAdmissionEnvelope,
        commit_generation: int,
        transaction_id: str,
        committed_at: datetime,
    ) -> Stage6BHistoricalRunAdmissionSeal:
        manifest_hash = _digest(sha256(envelope.manifest.to_canonical_bytes()).hexdigest())
        seal_seed = sha256(
            canonical_json_bytes(
                {
                    "run_id": envelope.request.run_id,
                    "envelope_hash": envelope.envelope_hash,
                    "generation": commit_generation,
                    "transaction_id": transaction_id,
                }
            )
        ).hexdigest()
        payload = {
            "schema_version": STAGE6B_VALIDATION_SEAL_SCHEMA_VERSION,
            "seal_id": f"stage6b_seal_{seal_seed[:24]}",
            "run_id": envelope.request.run_id,
            "request_hash": envelope.request.request_hash,
            "envelope_hash": envelope.envelope_hash,
            "manifest_hash": manifest_hash,
            "confirmation_id": envelope.confirmation.confirmation_id,
            "confirmation_hash": envelope.confirmation.confirmation_hash,
            "closure_hash": envelope.closure.closure_hash,
            "commit_generation": commit_generation,
            "transaction_id": transaction_id,
            "committed_at": normalize_utc(committed_at, field_name="committed_at"),
            "status": Stage6BAdmissionStatus.SEALED_VALIDATION_ONLY,
            "transaction_profile": STAGE6B_TRANSACTION_PROFILE,
            "validation_only": True,
            "authority_eligible": False,
            "strategy_evaluator_calls": 0,
        }
        return cls(
            schema_version=STAGE6B_VALIDATION_SEAL_SCHEMA_VERSION,
            seal_id=str(payload["seal_id"]),
            run_id=envelope.request.run_id,
            request_hash=envelope.request.request_hash,
            envelope_hash=envelope.envelope_hash,
            manifest_hash=manifest_hash,
            confirmation_id=envelope.confirmation.confirmation_id,
            confirmation_hash=envelope.confirmation.confirmation_hash,
            closure_hash=envelope.closure.closure_hash,
            commit_generation=commit_generation,
            transaction_id=transaction_id,
            committed_at=normalize_utc(committed_at, field_name="committed_at"),
            status=Stage6BAdmissionStatus.SEALED_VALIDATION_ONLY,
            transaction_profile=STAGE6B_TRANSACTION_PROFILE,
            validation_only=True,
            authority_eligible=False,
            strategy_evaluator_calls=0,
            seal_hash=_identity_hash(payload),
        )


_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS stage6b_validation_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_documents (
    document_kind TEXT NOT NULL,
    document_id TEXT NOT NULL,
    canonical_sha256 TEXT NOT NULL CHECK(length(canonical_sha256)=64),
    canonical_bytes BLOB NOT NULL,
    persisted_at TEXT NOT NULL,
    PRIMARY KEY(document_kind, document_id)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_links (
    parent_kind TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    role TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal>=0),
    target_id TEXT NOT NULL,
    target_sha256 TEXT NOT NULL CHECK(length(target_sha256)=64),
    PRIMARY KEY(parent_kind, parent_id, role, ordinal)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_cas_objects (
    object_sha256 TEXT PRIMARY KEY CHECK(length(object_sha256)=64),
    size_bytes INTEGER NOT NULL CHECK(size_bytes>=0),
    cache_key TEXT NOT NULL UNIQUE
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_cas_links (
    run_id TEXT NOT NULL,
    role TEXT NOT NULL,
    release_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    object_sha256 TEXT NOT NULL CHECK(length(object_sha256)=64),
    PRIMARY KEY(run_id, role, release_id, artifact_id)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_release_heads (
    run_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    status_observation_id TEXT NOT NULL,
    status_event_hash TEXT NOT NULL CHECK(length(status_event_hash)=64),
    response_bytes_hash TEXT NOT NULL CHECK(length(response_bytes_hash)=64),
    PRIMARY KEY(run_id, release_id)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_pin_releases (
    run_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    PRIMARY KEY(run_id, release_id)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_pin_artifacts (
    run_id TEXT NOT NULL,
    release_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL CHECK(length(artifact_sha256)=64),
    PRIMARY KEY(run_id, release_id, artifact_id)
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_generations (
    commit_generation INTEGER PRIMARY KEY CHECK(commit_generation>=1),
    transaction_id TEXT NOT NULL UNIQUE,
    run_id TEXT NOT NULL UNIQUE,
    committed_at TEXT NOT NULL
) STRICT;
CREATE TABLE IF NOT EXISTS stage6b_validation_seals (
    run_id TEXT PRIMARY KEY,
    seal_id TEXT NOT NULL UNIQUE,
    seal_sha256 TEXT NOT NULL UNIQUE CHECK(length(seal_sha256)=64),
    envelope_sha256 TEXT NOT NULL CHECK(length(envelope_sha256)=64),
    canonical_bytes BLOB NOT NULL
) STRICT;
"""

_APPEND_ONLY_TABLES = (
    "stage6b_validation_documents",
    "stage6b_validation_links",
    "stage6b_validation_cas_objects",
    "stage6b_validation_cas_links",
    "stage6b_validation_release_heads",
    "stage6b_validation_pin_releases",
    "stage6b_validation_pin_artifacts",
    "stage6b_validation_generations",
    "stage6b_validation_seals",
)


def _trigger_sql(table: str, operation: str) -> str:
    trigger = f"stage6b_prevent_{operation.lower()}_{table}"
    return (
        f"CREATE TRIGGER IF NOT EXISTS {trigger} BEFORE {operation} ON {table} "
        f"BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"
    )


def _parse_hash(value: Any, *, field_name: str) -> HashDigest:
    if not isinstance(value, dict) or set(value) != {"algorithm", "value"}:
        raise ValueError(f"{field_name} must be a SHA-256 object")
    return HashDigest(algorithm=value["algorithm"], value=value["value"])


def _parse_utc(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError(f"{field_name} must be canonical UTC")
    parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    if format_utc(parsed) != value:
        raise ValueError(f"{field_name} must be canonical UTC")
    return parsed


def _seal_from_bytes(value: bytes) -> Stage6BHistoricalRunAdmissionSeal:
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise ValueError("seal document must be an object")
    expected_keys = {
        "schema_version",
        "seal_id",
        "run_id",
        "request_hash",
        "envelope_hash",
        "manifest_hash",
        "confirmation_id",
        "confirmation_hash",
        "closure_hash",
        "commit_generation",
        "transaction_id",
        "committed_at",
        "status",
        "transaction_profile",
        "validation_only",
        "authority_eligible",
        "strategy_evaluator_calls",
        "seal_hash",
    }
    if set(parsed) != expected_keys:
        raise ValueError("seal document fields differ")
    return Stage6BHistoricalRunAdmissionSeal(
        schema_version=parsed["schema_version"],
        seal_id=parsed["seal_id"],
        run_id=parsed["run_id"],
        request_hash=_parse_hash(parsed["request_hash"], field_name="request_hash"),
        envelope_hash=_parse_hash(parsed["envelope_hash"], field_name="envelope_hash"),
        manifest_hash=_parse_hash(parsed["manifest_hash"], field_name="manifest_hash"),
        confirmation_id=parsed["confirmation_id"],
        confirmation_hash=_parse_hash(parsed["confirmation_hash"], field_name="confirmation_hash"),
        closure_hash=_parse_hash(parsed["closure_hash"], field_name="closure_hash"),
        commit_generation=parsed["commit_generation"],
        transaction_id=parsed["transaction_id"],
        committed_at=_parse_utc(parsed["committed_at"], field_name="committed_at"),
        status=Stage6BAdmissionStatus(parsed["status"]),
        transaction_profile=parsed["transaction_profile"],
        validation_only=parsed["validation_only"],
        authority_eligible=parsed["authority_eligible"],
        strategy_evaluator_calls=parsed["strategy_evaluator_calls"],
        seal_hash=_parse_hash(parsed["seal_hash"], field_name="seal_hash"),
    )


class Stage6BValidationStore:
    """Validation-only CAS and seal store rooted outside formal state paths."""

    def __init__(
        self,
        validation_root: Path,
        *,
        _failure_hook: FailureHook | None = None,
    ) -> None:
        if not isinstance(validation_root, Path):
            raise TypeError("validation_root must be a pathlib.Path")
        root = validation_root.resolve()
        repository = _REPOSITORY_ROOT
        prohibited = {
            repository,
            (repository / "var").resolve(),
            (repository / "var" / "state").resolve(),
            (repository / "var" / "cache").resolve(),
        }
        if root in prohibited or (repository / "var").resolve() in root.parents:
            raise Stage6BValidationStoreError(
                "PRECHECK_BLOCKED",
                "Stage 6B validation_root must not reuse formal var/state or var/cache",
            )
        self.validation_root = root
        self.database_path = root / "state" / "stage6b-validation.sqlite3"
        self.cache_root = root / "cache" / "stage6b-validation"
        self._failure_hook = _failure_hook
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, isolation_level=None, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA synchronous=FULL")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(_SCHEMA_SQL)
            connection.execute(
                "INSERT OR IGNORE INTO stage6b_validation_meta VALUES (?, ?)",
                ("schema_version", STAGE6B_VALIDATION_STORAGE_SCHEMA_VERSION),
            )
            row = connection.execute(
                "SELECT value FROM stage6b_validation_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None or row["value"] != STAGE6B_VALIDATION_STORAGE_SCHEMA_VERSION:
                raise Stage6BValidationStoreError(
                    "PRECHECK_BLOCKED", "validation storage schema differs"
                )
            for table in _APPEND_ONLY_TABLES:
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(_trigger_sql(table, operation))

    def _fail_after(self, step: str) -> None:
        if self._failure_hook is not None:
            self._failure_hook(step)

    def _cas_path(self, object_sha256: str) -> Path:
        return self.cache_root / "objects" / "sha256" / object_sha256[:2] / object_sha256

    def _stage_cas(self, content: bytes, *, expected_sha256: str) -> str:
        if sha256(content).hexdigest() != expected_sha256:
            raise Stage6BValidationStoreError("RECONCILIATION_BLOCKED", "CAS payload hash differs")
        target = self._cas_path(expected_sha256)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != expected_sha256:
                raise Stage6BValidationStoreError(
                    "IMMUTABLE_IDENTITY_CONFLICT", "existing CAS bytes differ"
                )
            return target.relative_to(self.cache_root).as_posix()
        descriptor, temporary_name = tempfile.mkstemp(
            prefix="stage6b-", suffix=".tmp", dir=target.parent
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            temporary = Path(temporary_name)
            if target.exists():
                if sha256(target.read_bytes()).hexdigest() != expected_sha256:
                    raise Stage6BValidationStoreError(
                        "IMMUTABLE_IDENTITY_CONFLICT", "concurrent CAS bytes differ"
                    )
            else:
                os.replace(temporary, target)
            if temporary.exists():
                temporary.unlink()
        finally:
            temporary = Path(temporary_name)
            if temporary.exists():
                temporary.unlink()
        return target.relative_to(self.cache_root).as_posix()

    @staticmethod
    def _document_identity(value: CanonicalModel) -> tuple[str, bytes]:
        canonical = value.to_canonical_bytes()
        return sha256(canonical).hexdigest(), canonical

    @staticmethod
    def _insert_document(
        connection: sqlite3.Connection,
        *,
        kind: str,
        document_id: str,
        value: CanonicalModel | Mapping[str, Any],
        persisted_at: str,
    ) -> str:
        canonical = (
            value.to_canonical_bytes()
            if isinstance(value, CanonicalModel)
            else canonical_json_bytes(value)
        )
        document_hash = sha256(canonical).hexdigest()
        row = connection.execute(
            """SELECT canonical_sha256, canonical_bytes
               FROM stage6b_validation_documents
               WHERE document_kind=? AND document_id=?""",
            (kind, document_id),
        ).fetchone()
        if row is not None:
            if (
                row["canonical_sha256"] != document_hash
                or bytes(row["canonical_bytes"]) != canonical
            ):
                raise Stage6BValidationStoreError(
                    "IMMUTABLE_IDENTITY_CONFLICT", f"{kind}/{document_id} was remapped"
                )
            return document_hash
        connection.execute(
            "INSERT INTO stage6b_validation_documents VALUES (?, ?, ?, ?, ?)",
            (kind, document_id, document_hash, canonical, persisted_at),
        )
        return document_hash

    @staticmethod
    def _insert_links_exact(
        connection: sqlite3.Connection,
        *,
        parent_kind: str,
        parent_id: str,
        links: Iterable[tuple[str, int, str, str]],
    ) -> None:
        expected = tuple(links)
        for role, ordinal, target_id, target_hash in expected:
            try:
                connection.execute(
                    "INSERT INTO stage6b_validation_links VALUES (?, ?, ?, ?, ?, ?)",
                    (parent_kind, parent_id, role, ordinal, target_id, target_hash),
                )
            except sqlite3.IntegrityError:
                row = connection.execute(
                    """SELECT target_id, target_sha256
                       FROM stage6b_validation_links
                       WHERE parent_kind=? AND parent_id=? AND role=? AND ordinal=?""",
                    (parent_kind, parent_id, role, ordinal),
                ).fetchone()
                if row is None or (row["target_id"], row["target_sha256"]) != (
                    target_id,
                    target_hash,
                ):
                    raise Stage6BValidationStoreError(
                        "IMMUTABLE_IDENTITY_CONFLICT", "canonical child link differs"
                    ) from None
        actual = tuple(
            tuple(row)
            for row in connection.execute(
                """SELECT role, ordinal, target_id, target_sha256
                   FROM stage6b_validation_links
                   WHERE parent_kind=? AND parent_id=?
                   ORDER BY role, ordinal""",
                (parent_kind, parent_id),
            )
        )
        if actual != tuple(sorted(expected)):
            raise Stage6BValidationStoreError(
                "IMMUTABLE_IDENTITY_CONFLICT", "canonical child set differs"
            )

    @staticmethod
    def _insert_exact_row(
        connection: sqlite3.Connection,
        *,
        table: str,
        columns: tuple[str, ...],
        values: tuple[Any, ...],
        key_columns: tuple[str, ...],
    ) -> None:
        where = " AND ".join(f"{column}=?" for column in key_columns)
        key_values = tuple(values[columns.index(column)] for column in key_columns)
        row = connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {where}", key_values
        ).fetchone()
        if row is not None:
            if tuple(row) != values:
                raise Stage6BValidationStoreError(
                    "IMMUTABLE_IDENTITY_CONFLICT", f"{table} row differs"
                )
            return
        placeholders = ", ".join("?" for _ in values)
        connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", values
        )

    def _prepare_payloads(
        self,
        envelope: Stage6BHistoricalAdmissionEnvelope,
        *,
        manifest_payloads: Iterable[ReleaseManifestPayload],
        artifact_payloads: Iterable[ArtifactPayload],
        status_payloads: Mapping[str, Stage6BStatusResponsePayload],
    ) -> dict[tuple[str, str, str], tuple[str, int, str]]:
        manifests = tuple(manifest_payloads)
        artifacts = tuple(artifact_payloads)
        manifest_by_release = {item.release_id: item for item in manifests}
        artifact_by_key = {(item.release_id, item.artifact_id): item for item in artifacts}
        closure_release_ids = tuple(node.release_id for node in envelope.closure.releases)
        closure_artifact_keys = tuple(
            sorted(
                (node.release_id, artifact.artifact_id)
                for node in envelope.closure.releases
                for artifact in node.artifacts
            )
        )
        if len(manifest_by_release) != len(manifests) or tuple(sorted(manifest_by_release)) != (
            closure_release_ids
        ):
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "manifest payload set differs from closure"
            )
        if len(artifact_by_key) != len(artifacts) or tuple(sorted(artifact_by_key)) != (
            closure_artifact_keys
        ):
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "artifact payload set differs from closure"
            )
        if tuple(sorted(status_payloads)) != closure_release_ids:
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "status payload set differs from closure"
            )
        root = envelope.closure.release(envelope.request.strategy_input_ref.dataset_release_id)
        root_receipt = tuple(
            (
                item.artifact_id,
                item.item_type,
                item.artifact_hash,
                item.size_bytes,
                item.record_count,
            )
            for item in envelope.receipt.artifacts
        )
        root_closure = tuple(
            (
                item.artifact_id,
                item.item_type,
                item.artifact_hash,
                item.size_bytes,
                item.record_count,
            )
            for item in root.artifacts
        )
        if root_receipt != root_closure:
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "root receipt artifacts differ from closure"
            )
        staged: dict[tuple[str, str, str], tuple[str, int, str]] = {}
        evidence_by_release = {item.release_id: item for item in envelope.status_evidences}
        for node in envelope.closure.releases:
            manifest = manifest_by_release[node.release_id]
            manifest_hash = sha256(manifest.content).hexdigest()
            if manifest_hash != node.manifest_document_hash.value or len(manifest.content) != (
                node.manifest_size_bytes
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "manifest payload bytes differ from closure"
                )
            staged[("manifest", node.release_id, "")] = (
                manifest_hash,
                len(manifest.content),
                self._stage_cas(manifest.content, expected_sha256=manifest_hash),
            )
            for descriptor in node.artifacts:
                artifact = artifact_by_key[(node.release_id, descriptor.artifact_id)]
                artifact_hash = sha256(artifact.content).hexdigest()
                if artifact_hash != descriptor.artifact_hash.value or len(artifact.content) != (
                    descriptor.size_bytes
                ):
                    raise Stage6BValidationStoreError(
                        "RECONCILIATION_BLOCKED", "artifact payload bytes differ from closure"
                    )
                staged[("artifact", node.release_id, descriptor.artifact_id)] = (
                    artifact_hash,
                    len(artifact.content),
                    self._stage_cas(artifact.content, expected_sha256=artifact_hash),
                )
            status = status_payloads[node.release_id]
            evidence = evidence_by_release[node.release_id]
            if status.release_id != node.release_id or (
                status.response_bytes_hash != evidence.response_bytes_hash
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "status payload differs from evidence"
                )
            staged[("status_response", node.release_id, "")] = (
                status.response_bytes_hash.value,
                len(status.content),
                self._stage_cas(status.content, expected_sha256=status.response_bytes_hash.value),
            )
        self._fail_after("cas_prepared")
        return staged

    @staticmethod
    def _validate_commit_time(
        envelope: Stage6BHistoricalAdmissionEnvelope, committed_at: datetime
    ) -> datetime:
        committed = normalize_utc(committed_at, field_name="committed_at")
        confirmation = envelope.confirmation
        if confirmation.expires_at - confirmation.confirmed_at != STAGE6B_CONFIRMATION_TTL or (
            committed < confirmation.confirmed_at or committed > confirmation.expires_at
        ):
            raise Stage6BValidationStoreError(
                "STATUS_UNCONFIRMED", "confirmation is not consumable at commit time"
            )
        if any(
            committed - item.provider_snapshot_at > STAGE6B_PROVIDER_SNAPSHOT_MAX_AGE
            or item.provider_snapshot_at - committed > STAGE6B_MAX_CLOCK_SKEW
            for item in confirmation.items
        ):
            raise Stage6BValidationStoreError(
                "STATUS_UNCONFIRMED", "provider status snapshot is stale at commit time"
            )
        return committed

    def commit_validation_admission(
        self,
        envelope: Stage6BHistoricalAdmissionEnvelope,
        *,
        manifest_payloads: Iterable[ReleaseManifestPayload],
        artifact_payloads: Iterable[ArtifactPayload],
        status_payloads: Mapping[str, Stage6BStatusResponsePayload],
        committed_at: datetime,
    ) -> Stage6BHistoricalRunAdmissionSeal:
        """Commit one exact validation-only admission, writing the seal last."""

        if not isinstance(envelope, Stage6BHistoricalAdmissionEnvelope):
            raise TypeError("envelope must be a Stage6BHistoricalAdmissionEnvelope")
        if envelope.schema_version != STAGE6B_ADMISSION_SCHEMA_VERSION or (
            envelope.storage_schema_version != STAGE6B_VALIDATION_STORAGE_SCHEMA_VERSION
        ):
            raise Stage6BValidationStoreError(
                "PRECHECK_BLOCKED", "admission envelope storage profile differs"
            )
        if sha256(canonical_json_bytes(envelope.identity_payload())).hexdigest() != (
            envelope.envelope_hash.value
        ):
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "admission envelope self hash differs"
            )
        committed = self._validate_commit_time(envelope, committed_at)
        try:
            staged = self._prepare_payloads(
                envelope,
                manifest_payloads=manifest_payloads,
                artifact_payloads=artifact_payloads,
                status_payloads=status_payloads,
            )
        except Stage6BValidationStoreError:
            raise
        except OSError as exc:
            raise Stage6BValidationStoreError(
                "ATOMIC_COMMIT_BLOCKED", "validation CAS preparation failed"
            ) from exc
        run_id = envelope.request.run_id
        persisted_at = format_utc(committed)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT envelope_sha256, canonical_bytes FROM stage6b_validation_seals WHERE run_id=?",
                (run_id,),
            ).fetchone()
            if existing is not None:
                if existing["envelope_sha256"] != envelope.envelope_hash.value:
                    raise Stage6BValidationStoreError(
                        "IMMUTABLE_IDENTITY_CONFLICT", "run_id is already sealed differently"
                    )
                seal = _seal_from_bytes(bytes(existing["canonical_bytes"]))
                connection.execute("COMMIT")
                self._verify_seal_files(seal)
                return seal

            generation = int(
                connection.execute(
                    "SELECT COALESCE(MAX(commit_generation), 0) + 1 FROM stage6b_validation_generations"
                ).fetchone()[0]
            )
            transaction_seed = sha256(
                canonical_json_bytes(
                    {
                        "run_id": run_id,
                        "envelope_hash": envelope.envelope_hash,
                        "generation": generation,
                        "committed_at": committed,
                    }
                )
            ).hexdigest()
            transaction_id = f"stage6b_tx_{transaction_seed[:24]}"

            for node in envelope.closure.releases:
                self._insert_document(
                    connection,
                    kind="release_identity",
                    document_id=node.release_id,
                    value=node.strategy_input_ref,
                    persisted_at=persisted_at,
                )
                manifest_object = staged[("manifest", node.release_id, "")]
                self._insert_document(
                    connection,
                    kind="release_manifest_index",
                    document_id=node.release_id,
                    value={
                        "release_id": node.release_id,
                        "semantic_manifest_hash": node.manifest_hash,
                        "document_hash": node.manifest_document_hash,
                        "size_bytes": node.manifest_size_bytes,
                        "cas_object_hash": manifest_object[0],
                    },
                    persisted_at=persisted_at,
                )
                for descriptor in node.artifacts:
                    self._insert_document(
                        connection,
                        kind="release_artifact_index",
                        document_id=f"{node.release_id}:{descriptor.artifact_id}",
                        value={
                            "release_id": node.release_id,
                            "artifact": descriptor,
                            "cas_object_hash": staged[
                                ("artifact", node.release_id, descriptor.artifact_id)
                            ][0],
                        },
                        persisted_at=persisted_at,
                    )
            self._fail_after("release_identities")

            self._insert_document(
                connection,
                kind="request",
                document_id=envelope.request.request_id,
                value=envelope.request,
                persisted_at=persisted_at,
            )
            self._insert_document(
                connection,
                kind="receipt",
                document_id=envelope.receipt.receipt_hash.value,
                value=envelope.receipt,
                persisted_at=persisted_at,
            )
            self._insert_document(
                connection,
                kind="closure",
                document_id=envelope.closure.closure_hash.value,
                value=envelope.closure,
                persisted_at=persisted_at,
            )
            receipt_links = tuple(
                (
                    "artifact",
                    index,
                    item.artifact_id,
                    sha256(item.to_canonical_bytes()).hexdigest(),
                )
                for index, item in enumerate(envelope.receipt.artifacts)
            )
            self._insert_links_exact(
                connection,
                parent_kind="receipt",
                parent_id=envelope.receipt.receipt_hash.value,
                links=receipt_links,
            )
            closure_links: list[tuple[str, int, str, str]] = []
            for index, node in enumerate(envelope.closure.releases):
                closure_links.append(
                    (
                        "release",
                        index,
                        node.release_id,
                        sha256(node.to_canonical_bytes()).hexdigest(),
                    )
                )
                for dependency_index, dependency in enumerate(node.dependency_release_ids):
                    closure_links.append(
                        (
                            f"dependency:{node.release_id}",
                            dependency_index,
                            dependency,
                            sha256(dependency.encode()).hexdigest(),
                        )
                    )
                for artifact_index, descriptor in enumerate(node.artifacts):
                    closure_links.append(
                        (
                            f"artifact:{node.release_id}",
                            artifact_index,
                            descriptor.artifact_id,
                            sha256(descriptor.to_canonical_bytes()).hexdigest(),
                        )
                    )
            self._insert_links_exact(
                connection,
                parent_kind="closure",
                parent_id=envelope.closure.closure_hash.value,
                links=closure_links,
            )
            self._fail_after("receipt_closure")

            observations: tuple[CanonicalModel, ...] = (
                envelope.fetch_observation,
                *envelope.status_observations,
                envelope.admission_observation,
            )
            for observation in observations:
                self._insert_document(
                    connection,
                    kind="observation",
                    document_id=str(observation.to_json_value()["observation_id"]),
                    value=observation,
                    persisted_at=persisted_at,
                )
            for evidence in envelope.status_evidences:
                self._insert_document(
                    connection,
                    kind="status_evidence",
                    document_id=evidence.evidence_id,
                    value=evidence,
                    persisted_at=persisted_at,
                )
                self._insert_exact_row(
                    connection,
                    table="stage6b_validation_release_heads",
                    columns=(
                        "run_id",
                        "release_id",
                        "status_observation_id",
                        "status_event_hash",
                        "response_bytes_hash",
                    ),
                    values=(
                        run_id,
                        evidence.release_id,
                        evidence.status_observation_id,
                        evidence.status_event_hash.value,
                        evidence.response_bytes_hash.value,
                    ),
                    key_columns=("run_id", "release_id"),
                )
            self._fail_after("observations")

            self._insert_document(
                connection,
                kind="preregistration",
                document_id=envelope.preregistration.preregistration_id,
                value=envelope.preregistration,
                persisted_at=persisted_at,
            )
            self._fail_after("preregistration")
            self._insert_document(
                connection,
                kind="strategy_run_manifest",
                document_id=run_id,
                value=envelope.manifest,
                persisted_at=persisted_at,
            )
            self._fail_after("manifest")
            self._insert_document(
                connection,
                kind="confirmation",
                document_id=envelope.confirmation.confirmation_id,
                value=envelope.confirmation,
                persisted_at=persisted_at,
            )
            self._insert_links_exact(
                connection,
                parent_kind="confirmation",
                parent_id=envelope.confirmation.confirmation_id,
                links=tuple(
                    (
                        "item",
                        index,
                        item.release_id,
                        item.evidence_hash.value,
                    )
                    for index, item in enumerate(envelope.confirmation.items)
                ),
            )
            self._fail_after("confirmation")

            for (role, release_id, artifact_id), (object_hash, size, cache_key) in staged.items():
                self._insert_exact_row(
                    connection,
                    table="stage6b_validation_cas_objects",
                    columns=("object_sha256", "size_bytes", "cache_key"),
                    values=(object_hash, size, cache_key),
                    key_columns=("object_sha256",),
                )
                self._insert_exact_row(
                    connection,
                    table="stage6b_validation_cas_links",
                    columns=("run_id", "role", "release_id", "artifact_id", "object_sha256"),
                    values=(run_id, role, release_id, artifact_id, object_hash),
                    key_columns=("run_id", "role", "release_id", "artifact_id"),
                )
            for node in envelope.closure.releases:
                self._insert_exact_row(
                    connection,
                    table="stage6b_validation_pin_releases",
                    columns=("run_id", "release_id"),
                    values=(run_id, node.release_id),
                    key_columns=("run_id", "release_id"),
                )
                for descriptor in node.artifacts:
                    self._insert_exact_row(
                        connection,
                        table="stage6b_validation_pin_artifacts",
                        columns=("run_id", "release_id", "artifact_id", "artifact_sha256"),
                        values=(
                            run_id,
                            node.release_id,
                            descriptor.artifact_id,
                            descriptor.artifact_hash.value,
                        ),
                        key_columns=("run_id", "release_id", "artifact_id"),
                    )
            self._fail_after("pins")

            self._insert_document(
                connection,
                kind="admission_envelope",
                document_id=envelope.envelope_hash.value,
                value=envelope,
                persisted_at=persisted_at,
            )
            self._insert_links_exact(
                connection,
                parent_kind="admission_envelope",
                parent_id=envelope.envelope_hash.value,
                links=(
                    (
                        "request",
                        0,
                        envelope.request.request_id,
                        envelope.request.request_hash.value,
                    ),
                    (
                        "receipt",
                        0,
                        envelope.receipt.receipt_hash.value,
                        envelope.receipt.receipt_hash.value,
                    ),
                    (
                        "closure",
                        0,
                        envelope.closure.closure_hash.value,
                        envelope.closure.closure_hash.value,
                    ),
                    (
                        "manifest",
                        0,
                        run_id,
                        sha256(envelope.manifest.to_canonical_bytes()).hexdigest(),
                    ),
                    (
                        "confirmation",
                        0,
                        envelope.confirmation.confirmation_id,
                        envelope.confirmation.confirmation_hash.value,
                    ),
                ),
            )
            self._fail_after("envelope")

            self._insert_exact_row(
                connection,
                table="stage6b_validation_generations",
                columns=("commit_generation", "transaction_id", "run_id", "committed_at"),
                values=(generation, transaction_id, run_id, persisted_at),
                key_columns=("run_id",),
            )
            seal = Stage6BHistoricalRunAdmissionSeal.create(
                envelope=envelope,
                commit_generation=generation,
                transaction_id=transaction_id,
                committed_at=committed,
            )
            self._fail_after("before_seal")
            connection.execute(
                "INSERT INTO stage6b_validation_seals VALUES (?, ?, ?, ?, ?)",
                (
                    run_id,
                    seal.seal_id,
                    seal.seal_hash.value,
                    envelope.envelope_hash.value,
                    seal.to_canonical_bytes(),
                ),
            )
            connection.execute("COMMIT")
        except Stage6BValidationStoreError:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise Stage6BValidationStoreError(
                "ATOMIC_COMMIT_BLOCKED", "validation admission transaction failed"
            ) from exc
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        self._verify_seal_files(seal)
        return seal

    def _verify_seal_files(self, seal: Stage6BHistoricalRunAdmissionSeal) -> None:
        with self._connect() as connection:
            schema_row = connection.execute(
                "SELECT value FROM stage6b_validation_meta WHERE key='schema_version'"
            ).fetchone()
            if schema_row is None or (
                schema_row["value"] != STAGE6B_VALIDATION_STORAGE_SCHEMA_VERSION
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "validation storage schema differs"
                )
            row = connection.execute(
                "SELECT seal_sha256, envelope_sha256, canonical_bytes FROM stage6b_validation_seals WHERE run_id=?",
                (seal.run_id,),
            ).fetchone()
            if (
                row is None
                or row["seal_sha256"] != seal.seal_hash.value
                or (row["envelope_sha256"] != seal.envelope_hash.value)
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "stored seal identity differs"
                )
            stored = _seal_from_bytes(bytes(row["canonical_bytes"]))
            if stored != seal:
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "stored seal bytes differ"
                )
            envelope_row = connection.execute(
                """SELECT canonical_sha256, canonical_bytes
                   FROM stage6b_validation_documents
                   WHERE document_kind='admission_envelope' AND document_id=?""",
                (seal.envelope_hash.value,),
            ).fetchone()
            if envelope_row is None:
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed admission envelope is missing"
                )
            try:
                envelope_document = json.loads(bytes(envelope_row["canonical_bytes"]))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed admission envelope is invalid JSON"
                ) from exc
            if not isinstance(envelope_document, dict) or (
                envelope_document.get("envelope_hash", {}).get("value") != seal.envelope_hash.value
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed admission envelope identity differs"
                )
            for document in connection.execute(
                "SELECT canonical_sha256, canonical_bytes FROM stage6b_validation_documents"
            ):
                if (
                    sha256(bytes(document["canonical_bytes"])).hexdigest()
                    != document["canonical_sha256"]
                ):
                    raise Stage6BValidationStoreError(
                        "RECONCILIATION_BLOCKED", "stored canonical document was tampered"
                    )
            try:
                request = envelope_document["request"]
                receipt = envelope_document["receipt"]
                closure = envelope_document["closure"]
                manifest = envelope_document["manifest"]
                confirmation = envelope_document["confirmation"]
                status_evidences = envelope_document["status_evidences"]
                release_nodes = closure["releases"]
                receipt_items = receipt["artifacts"]
                confirmation_items = confirmation["items"]
            except (KeyError, TypeError) as exc:
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed admission envelope structure differs"
                ) from exc
            if not all(
                isinstance(value, (dict, list))
                for value in (
                    request,
                    receipt,
                    closure,
                    manifest,
                    confirmation,
                    status_evidences,
                    release_nodes,
                    receipt_items,
                    confirmation_items,
                )
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed admission envelope types differ"
                )
            assert isinstance(request, dict)
            assert isinstance(receipt, dict)
            assert isinstance(closure, dict)
            assert isinstance(manifest, dict)
            assert isinstance(confirmation, dict)
            assert isinstance(status_evidences, list)
            assert isinstance(release_nodes, list)
            assert isinstance(receipt_items, list)
            assert isinstance(confirmation_items, list)
            manifest_hash = sha256(canonical_json_bytes(manifest)).hexdigest()
            if manifest_hash != seal.manifest_hash.value or (
                confirmation.get("confirmation_hash", {}).get("value")
                != seal.confirmation_hash.value
                or closure.get("closure_hash", {}).get("value") != seal.closure_hash.value
                or request.get("request_hash", {}).get("value") != seal.request_hash.value
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed parent identity differs"
                )

            receipt_id = str(receipt["receipt_hash"]["value"])
            expected_receipt_links = tuple(
                sorted(
                    (
                        "artifact",
                        index,
                        str(item["artifact_id"]),
                        sha256(canonical_json_bytes(item)).hexdigest(),
                    )
                    for index, item in enumerate(receipt_items)
                )
            )
            expected_closure_links: list[tuple[str, int, str, str]] = []
            expected_release_ids: list[str] = []
            expected_artifact_pins: list[tuple[str, str, str]] = []
            expected_cas_links: list[tuple[str, str, str, str]] = []
            for release_index, node in enumerate(release_nodes):
                release_id = str(node["strategy_input_ref"]["dataset_release_id"])
                expected_release_ids.append(release_id)
                expected_closure_links.append(
                    (
                        "release",
                        release_index,
                        release_id,
                        sha256(canonical_json_bytes(node)).hexdigest(),
                    )
                )
                for dependency_index, dependency in enumerate(node["dependency_release_ids"]):
                    expected_closure_links.append(
                        (
                            f"dependency:{release_id}",
                            dependency_index,
                            str(dependency),
                            sha256(str(dependency).encode()).hexdigest(),
                        )
                    )
                expected_cas_links.append(
                    (
                        "manifest",
                        release_id,
                        "",
                        str(node["manifest_document_hash"]["value"]),
                    )
                )
                for artifact_index, artifact in enumerate(node["artifacts"]):
                    artifact_id = str(artifact["artifact_id"])
                    artifact_hash = str(artifact["artifact_hash"]["value"])
                    expected_closure_links.append(
                        (
                            f"artifact:{release_id}",
                            artifact_index,
                            artifact_id,
                            sha256(canonical_json_bytes(artifact)).hexdigest(),
                        )
                    )
                    expected_artifact_pins.append((release_id, artifact_id, artifact_hash))
                    expected_cas_links.append(("artifact", release_id, artifact_id, artifact_hash))
            evidence_by_release = {
                str(item["strategy_input_ref"]["dataset_release_id"]): item
                for item in status_evidences
            }
            if set(evidence_by_release) != set(expected_release_ids):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed status evidence set differs"
                )
            for release_id in expected_release_ids:
                expected_cas_links.append(
                    (
                        "status_response",
                        release_id,
                        "",
                        str(evidence_by_release[release_id]["response_bytes_hash"]["value"]),
                    )
                )
            expected_confirmation_links = tuple(
                (
                    "item",
                    index,
                    str(item["strategy_input_ref"]["dataset_release_id"]),
                    str(item["evidence_hash"]["value"]),
                )
                for index, item in enumerate(confirmation_items)
            )
            expected_envelope_links = tuple(
                sorted(
                    (
                        (
                            "request",
                            0,
                            str(request["request_id"]),
                            str(request["request_hash"]["value"]),
                        ),
                        (
                            "receipt",
                            0,
                            receipt_id,
                            receipt_id,
                        ),
                        (
                            "closure",
                            0,
                            str(closure["closure_hash"]["value"]),
                            str(closure["closure_hash"]["value"]),
                        ),
                        ("manifest", 0, seal.run_id, manifest_hash),
                        (
                            "confirmation",
                            0,
                            str(confirmation["confirmation_id"]),
                            str(confirmation["confirmation_hash"]["value"]),
                        ),
                    )
                )
            )

            def actual_links(parent_kind: str, parent_id: str) -> tuple[tuple[Any, ...], ...]:
                return tuple(
                    tuple(link)
                    for link in connection.execute(
                        """SELECT role, ordinal, target_id, target_sha256
                           FROM stage6b_validation_links
                           WHERE parent_kind=? AND parent_id=?
                           ORDER BY role, ordinal""",
                        (parent_kind, parent_id),
                    )
                )

            if (
                actual_links("receipt", receipt_id) != expected_receipt_links
                or actual_links("closure", seal.closure_hash.value)
                != tuple(sorted(expected_closure_links))
                or actual_links("confirmation", seal.confirmation_id) != expected_confirmation_links
                or actual_links("admission_envelope", seal.envelope_hash.value)
                != expected_envelope_links
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed canonical child indexes differ"
                )
            for item in connection.execute(
                """SELECT object.object_sha256, object.size_bytes, object.cache_key
                   FROM stage6b_validation_cas_objects AS object
                   JOIN stage6b_validation_cas_links AS link
                     ON link.object_sha256=object.object_sha256
                   WHERE link.run_id=?""",
                (seal.run_id,),
            ):
                path = self.cache_root / item["cache_key"]
                if (
                    not path.is_file()
                    or path.stat().st_size != item["size_bytes"]
                    or (sha256(path.read_bytes()).hexdigest() != item["object_sha256"])
                ):
                    raise Stage6BValidationStoreError(
                        "RECONCILIATION_BLOCKED", "sealed CAS object was tampered or lost"
                    )
            release_ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT release_id FROM stage6b_validation_pin_releases WHERE run_id=? ORDER BY release_id",
                    (seal.run_id,),
                )
            )
            head_ids = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT release_id FROM stage6b_validation_release_heads WHERE run_id=? ORDER BY release_id",
                    (seal.run_id,),
                )
            )
            confirmation_ids = tuple(
                row[0]
                for row in connection.execute(
                    """SELECT target_id FROM stage6b_validation_links
                       WHERE parent_kind='confirmation' AND parent_id=? AND role='item'
                       ORDER BY ordinal""",
                    (seal.confirmation_id,),
                )
            )
            if not release_ids or release_ids != head_ids or release_ids != confirmation_ids:
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed full-closure indexes differ"
                )
            artifact_pins = tuple(
                tuple(row)
                for row in connection.execute(
                    """SELECT release_id, artifact_id, artifact_sha256
                       FROM stage6b_validation_pin_artifacts
                       WHERE run_id=? ORDER BY release_id, artifact_id""",
                    (seal.run_id,),
                )
            )
            cas_links = tuple(
                tuple(row)
                for row in connection.execute(
                    """SELECT role, release_id, artifact_id, object_sha256
                       FROM stage6b_validation_cas_links
                       WHERE run_id=? ORDER BY role, release_id, artifact_id""",
                    (seal.run_id,),
                )
            )
            if artifact_pins != tuple(sorted(expected_artifact_pins)) or cas_links != tuple(
                sorted(expected_cas_links)
            ):
                raise Stage6BValidationStoreError(
                    "RECONCILIATION_BLOCKED", "sealed pin or CAS indexes differ"
                )

    def read_validation_seal(self, run_id: str) -> Stage6BHistoricalRunAdmissionSeal:
        """Read and reverify one immutable validation seal without writing state."""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT canonical_bytes FROM stage6b_validation_seals WHERE run_id=?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise KeyError(run_id)
        try:
            seal = _seal_from_bytes(bytes(row["canonical_bytes"]))
            self._verify_seal_files(seal)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            raise Stage6BValidationStoreError(
                "RECONCILIATION_BLOCKED", "stored seal cannot be verified"
            ) from exc
        return seal

    def authoritative_row_counts(self) -> Mapping[str, int]:
        """Expose deterministic validation diagnostics; never a strategy authority."""

        with self._connect() as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in _APPEND_ONLY_TABLES
            }
