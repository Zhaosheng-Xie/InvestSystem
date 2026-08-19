"""Strict consumer for the KB producer's Stage 6B validation handoff."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from invest_system.canonical import normalize_utc
from invest_system.integrations.investment_research_kb.contracts import (
    load_strict_json_bytes,
)
from invest_system.integrations.investment_research_kb.transport_contracts import (
    TRANSPORT_SNAPSHOT_LOCK_SHA256,
    TRANSPORT_SOURCE_COMMIT,
)
from invest_system.models import HashDigest, StrategyInputRef

STAGE6B_PRODUCER_HANDOFF_SCHEMA_VERSION = "1.0.0"
STAGE6B_PRODUCER_HANDOFF_PURPOSE = "invest-system-stage6b-real-https-validation-only-admission"

_TOP_LEVEL_KEYS = {
    "allowed_http_surfaces",
    "authority_eligible",
    "credential",
    "forbidden_or_out_of_scope",
    "generated_at",
    "handoff_json_absolute_path",
    "handoff_schema_version",
    "production_base_url",
    "purpose",
    "root_release",
    "source_closure",
    "source_releases",
    "transport_contract",
    "validation_evidence",
}
_RELEASE_KEYS = {
    "artifacts",
    "current_status",
    "knowledge_cutoff",
    "manifest",
    "release_id",
    "release_response_sha256",
    "status",
}
_ARTIFACT_KEYS = {
    "artifact_id",
    "content_type",
    "item_type",
    "logical_path",
    "observed_content_type",
    "record_schema_id",
    "record_schema_sha256",
    "record_schema_version",
    "response_headers_verified",
    "sha256",
    "size_bytes",
}
_ALLOWED_SURFACES = {
    "GET /api/v1/dataset-releases/{release_id}",
    "GET /api/v1/dataset-releases/{release_id}/manifest",
    "GET /api/v1/dataset-releases/{release_id}/status",
    "GET /api/v1/dataset-releases/{release_id}/artifacts/{artifact_id}",
}


class Stage6BProducerHandoffError(ValueError):
    """Stable fail-closed producer-handoff error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise Stage6BProducerHandoffError(code, message)


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must be an object")
    return cast(dict[str, Any], value)


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must be an array")
    return cast(list[Any], value)


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must be non-empty text")
    return cast(str, value)


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must be a non-negative integer")
    return cast(int, value)


def _sha256_text(value: object, *, field: str) -> str:
    text = _text(value, field=field)
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must be lowercase SHA-256")
    return text


def _utc(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage6BProducerHandoffError(
            "HANDOFF_STRUCTURE_INVALID", f"{field} must be ISO-8601"
        ) from exc
    if parsed.tzinfo is None:
        _fail("HANDOFF_STRUCTURE_INVALID", f"{field} must include an offset")
    return normalize_utc(parsed, field_name=field)


@dataclass(frozen=True, slots=True)
class Stage6BProducerArtifact:
    artifact_id: str
    sha256: str
    size_bytes: int
    content_type: str
    item_type: str
    schema_id: str
    schema_version: str
    record_schema_hash: str

    @classmethod
    def from_json(cls, value: object) -> Stage6BProducerArtifact:
        item = _object(value, field="artifact")
        if set(item) != _ARTIFACT_KEYS:
            _fail("ARTIFACT_CONTRACT_MISMATCH", "artifact field set differs")
        content_type = _text(item.get("content_type"), field="artifact.content_type")
        if item.get("observed_content_type") != content_type or (
            item.get("response_headers_verified") is not True
        ):
            _fail("ARTIFACT_CONTRACT_MISMATCH", "artifact HTTP evidence differs")
        return cls(
            artifact_id=_text(item.get("artifact_id"), field="artifact.artifact_id"),
            sha256=_sha256_text(item.get("sha256"), field="artifact.sha256"),
            size_bytes=_integer(item.get("size_bytes"), field="artifact.size_bytes"),
            content_type=content_type,
            item_type=_text(item.get("item_type"), field="artifact.item_type"),
            schema_id=_text(item.get("record_schema_id"), field="artifact.record_schema_id"),
            schema_version=_text(
                item.get("record_schema_version"), field="artifact.record_schema_version"
            ),
            record_schema_hash=_sha256_text(
                item.get("record_schema_sha256"), field="artifact.record_schema_sha256"
            ),
        )


@dataclass(frozen=True, slots=True)
class Stage6BProducerRelease:
    release_id: str
    knowledge_cutoff: datetime
    manifest_hash: str
    manifest_schema_version: str
    artifacts: tuple[Stage6BProducerArtifact, ...]
    status_event_id: str
    status_event_hash: str
    status_sequence: int
    status_recorded_at: datetime

    @classmethod
    def from_json(cls, value: object) -> Stage6BProducerRelease:
        item = _object(value, field="release")
        if set(item) != _RELEASE_KEYS:
            _fail("RELEASE_CONTRACT_MISMATCH", "Release field set differs")
        manifest = _object(item.get("manifest"), field="release.manifest")
        if set(manifest) != {"artifact_count", "response_sha256", "schema_version", "sha256"}:
            _fail("RELEASE_CONTRACT_MISMATCH", "Manifest evidence field set differs")
        status = _object(item.get("status"), field="release.status")
        if set(status) != {"head", "response_sha256"}:
            _fail("RELEASE_CONTRACT_MISMATCH", "status evidence field set differs")
        head = _object(status.get("head"), field="release.status.head")
        required_head = {"authority", "event_hash", "event_id", "recorded_at", "sequence", "status"}
        if (
            set(head) != required_head
            or head.get("status") != "published"
            or (item.get("current_status") != "published")
        ):
            _fail("RELEASE_NOT_PUBLISHED", "handoff Release head is not published")
        artifacts = tuple(
            Stage6BProducerArtifact.from_json(raw)
            for raw in _array(item.get("artifacts"), field="release.artifacts")
        )
        if not artifacts or len({artifact.artifact_id for artifact in artifacts}) != len(artifacts):
            _fail(
                "ARTIFACT_INVENTORY_MISMATCH", "Release artifact inventory is empty or duplicated"
            )
        if manifest.get("artifact_count") != len(artifacts):
            _fail("ARTIFACT_INVENTORY_MISMATCH", "Manifest artifact count differs")
        event_hash = _object(head.get("event_hash"), field="release.status.head.event_hash")
        if set(event_hash) != {"algorithm", "value"} or event_hash.get("algorithm") != "sha256":
            _fail("RELEASE_CONTRACT_MISMATCH", "status event hash differs")
        return cls(
            release_id=_text(item.get("release_id"), field="release.release_id"),
            knowledge_cutoff=_utc(item.get("knowledge_cutoff"), field="release.knowledge_cutoff"),
            manifest_hash=_sha256_text(manifest.get("sha256"), field="release.manifest.sha256"),
            manifest_schema_version=_text(
                manifest.get("schema_version"), field="release.manifest.schema_version"
            ),
            artifacts=tuple(sorted(artifacts, key=lambda artifact: artifact.artifact_id)),
            status_event_id=_text(head.get("event_id"), field="release.status.head.event_id"),
            status_event_hash=_sha256_text(
                event_hash.get("value"), field="release.status.head.event_hash.value"
            ),
            status_sequence=_integer(head.get("sequence"), field="release.status.head.sequence"),
            status_recorded_at=_utc(
                head.get("recorded_at"), field="release.status.head.recorded_at"
            ),
        )

    def strategy_input_ref(self) -> StrategyInputRef:
        return StrategyInputRef(
            schema_version="1.0.0",
            dataset_release_id=self.release_id,
            knowledge_cutoff=self.knowledge_cutoff,
            release_manifest_schema_version=self.manifest_schema_version,
            manifest_hash=HashDigest(algorithm="sha256", value=self.manifest_hash),
        )


@dataclass(frozen=True, slots=True)
class Stage6BProducerHandoff:
    handoff_sha256: str
    base_url: str
    generated_at: datetime
    credential_expires_at: datetime
    credential_env_path: Path
    validation_report_path: Path
    validation_report_sha256: str
    root_release: Stage6BProducerRelease
    source_releases: tuple[Stage6BProducerRelease, ...]

    @classmethod
    def from_bytes(cls, content: bytes, *, expected_sha256: str) -> Stage6BProducerHandoff:
        if sha256(content).hexdigest() != expected_sha256:
            _fail("HANDOFF_HASH_MISMATCH", "producer handoff bytes changed")
        raw = _object(load_strict_json_bytes(content, source="Stage 6B handoff"), field="handoff")
        if set(raw) != _TOP_LEVEL_KEYS:
            _fail("HANDOFF_STRUCTURE_INVALID", "top-level handoff field set differs")
        if raw.get("handoff_schema_version") != STAGE6B_PRODUCER_HANDOFF_SCHEMA_VERSION or (
            raw.get("purpose") != STAGE6B_PRODUCER_HANDOFF_PURPOSE
        ):
            _fail("HANDOFF_VERSION_UNSUPPORTED", "Stage 6B handoff identity differs")
        if raw.get("authority_eligible") is not False:
            _fail("AUTHORITY_BOUNDARY_INVALID", "handoff must remain authority-ineligible")
        transport = _object(raw.get("transport_contract"), field="transport_contract")
        if set(transport) != {"snapshot_lock_sha256", "source_commit"} or (
            transport.get("source_commit") != TRANSPORT_SOURCE_COMMIT
            or transport.get("snapshot_lock_sha256") != TRANSPORT_SNAPSHOT_LOCK_SHA256
        ):
            _fail("TRANSPORT_IDENTITY_MISMATCH", "handoff transport identity differs")
        surfaces = _array(raw.get("allowed_http_surfaces"), field="allowed_http_surfaces")
        if set(surfaces) != _ALLOWED_SURFACES or len(surfaces) != len(_ALLOWED_SURFACES):
            _fail("HTTP_SURFACE_MISMATCH", "handoff HTTP allowlist differs")
        credential = _object(raw.get("credential"), field="credential")
        if set(credential) != {
            "env_file_absolute_path",
            "expires_at_utc",
            "plaintext_token_embedded_in_handoff",
            "principal",
            "scopes",
            "token_id",
        }:
            _fail("CREDENTIAL_BOUNDARY_INVALID", "credential metadata field set differs")
        scopes = _array(credential.get("scopes"), field="credential.scopes")
        if credential.get("plaintext_token_embedded_in_handoff") is not False or set(scopes) != {
            "export:read",
            "research:read",
        }:
            _fail("CREDENTIAL_BOUNDARY_INVALID", "credential scope or plaintext boundary differs")
        root = Stage6BProducerRelease.from_json(raw.get("root_release"))
        sources = tuple(
            Stage6BProducerRelease.from_json(value)
            for value in _array(raw.get("source_releases"), field="source_releases")
        )
        if not sources or len({source.release_id for source in sources}) != len(sources):
            _fail("SOURCE_CLOSURE_MISMATCH", "source Release inventory differs")
        closure = _object(raw.get("source_closure"), field="source_closure")
        if (
            set(closure)
            != {
                "closed",
                "relations",
                "root_release_id",
                "transitive_source_release_ids",
            }
            or closure.get("closed") is not True
            or closure.get("root_release_id") != root.release_id
        ):
            _fail("SOURCE_CLOSURE_MISMATCH", "source closure root differs")
        source_ids = tuple(sorted(source.release_id for source in sources))
        if (
            tuple(sorted(_array(closure.get("transitive_source_release_ids"), field="source ids")))
            != source_ids
        ):
            _fail("SOURCE_CLOSURE_MISMATCH", "transitive source Release set differs")
        relations = _array(closure.get("relations"), field="source_closure.relations")
        relation_ids: set[str] = set()
        for raw_relation in relations:
            relation = _object(raw_relation, field="source relation")
            if (
                set(relation)
                != {
                    "declared_by_artifact_id",
                    "from_release_id",
                    "knowledge_cutoff",
                    "relation",
                    "source_manifest_sha256",
                    "to_release_id",
                }
                or relation.get("from_release_id") != root.release_id
                or (relation.get("relation") != "declares_source_release")
            ):
                _fail("SOURCE_CLOSURE_MISMATCH", "source relation differs")
            source_id = _text(relation.get("to_release_id"), field="source relation id")
            source = next((value for value in sources if value.release_id == source_id), None)
            if (
                source is None
                or relation.get("source_manifest_sha256") != source.manifest_hash
                or (
                    _utc(relation.get("knowledge_cutoff"), field="source relation cutoff")
                    != source.knowledge_cutoff
                )
            ):
                _fail("SOURCE_CLOSURE_MISMATCH", "source relation identity differs")
            relation_ids.add(source_id)
        if relation_ids != set(source_ids):
            _fail("SOURCE_CLOSURE_MISMATCH", "source relation coverage differs")
        validation = _object(raw.get("validation_evidence"), field="validation_evidence")
        if (
            set(validation)
            != {
                "all_release_manifest_status_artifact_checks_passed",
                "evidence_scope_endpoint_http_status",
                "unauthenticated_release_http_status",
                "validation_report_absolute_path",
                "validation_report_sha256",
            }
            or validation.get("all_release_manifest_status_artifact_checks_passed") is not True
            or (
                validation.get("evidence_scope_endpoint_http_status") != 403
                or validation.get("unauthenticated_release_http_status") != 401
            )
        ):
            _fail("PRODUCER_VALIDATION_INVALID", "producer validation evidence differs")
        return cls(
            handoff_sha256=expected_sha256,
            base_url=_text(raw.get("production_base_url"), field="production_base_url"),
            generated_at=_utc(raw.get("generated_at"), field="generated_at"),
            credential_expires_at=_utc(
                credential.get("expires_at_utc"), field="credential.expires_at_utc"
            ),
            credential_env_path=Path(
                _text(credential.get("env_file_absolute_path"), field="credential env path")
            ).resolve(),
            validation_report_path=Path(
                _text(
                    validation.get("validation_report_absolute_path"),
                    field="validation report path",
                )
            ).resolve(),
            validation_report_sha256=_sha256_text(
                validation.get("validation_report_sha256"),
                field="validation_report_sha256",
            ),
            root_release=root,
            source_releases=tuple(sorted(sources, key=lambda source: source.release_id)),
        )

    def verify_external_paths(self, *, credential_env_path: Path) -> None:
        if credential_env_path.resolve() != self.credential_env_path:
            _fail("CREDENTIAL_PATH_MISMATCH", "credential path differs from handoff")
        if (
            sha256(self.validation_report_path.read_bytes()).hexdigest()
            != self.validation_report_sha256
        ):
            _fail("PRODUCER_REPORT_HASH_MISMATCH", "producer validation report bytes changed")


__all__ = [
    "STAGE6B_PRODUCER_HANDOFF_PURPOSE",
    "STAGE6B_PRODUCER_HANDOFF_SCHEMA_VERSION",
    "Stage6BProducerArtifact",
    "Stage6BProducerHandoff",
    "Stage6BProducerHandoffError",
    "Stage6BProducerRelease",
]
