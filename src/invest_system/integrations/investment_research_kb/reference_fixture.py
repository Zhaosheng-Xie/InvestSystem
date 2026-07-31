"""Black-box verifier for the pinned public Stage 6 reference fixture.

The fixture is provider-published synthetic contract evidence. This module
validates those public bytes and maps only the deliberately narrow Context Pack
shape exercised by the fixture. It is not an HTTP client, an export-package
implementation, a current-status proof, an admission decision, or a production
strategy adapter.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any, NoReturn

from ...consumption import (
    ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactReceiptItem,
)
from ...models import (
    VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
    HashDigest,
    StrategyInputRef,
    VerifiedFact,
    VerifiedKnowledgeInput,
)
from .contracts import ContractValidationError, KBContractCatalog, SchemaContract
from .provider_canonical import (
    CANONICALIZATION_PROFILE,
    canonical_json_bytes,
    manifest_sha256,
)

CONSUMER_CONTRACT_VERSION = "1.0.0"
CONTEXT_PACK_PROJECTION_VERSION = "1.0.0"

_DATASET_RELEASE_ID = "urn:investment-research-kb:contract:dataset-release:v1"
_RELEASE_MANIFEST_ID = "urn:investment-research-kb:contract:release-manifest:v1"
_CHANGE_RECORD_ID = "urn:investment-research-kb:contract:change-record:v1"
_STRATEGY_INPUT_REF_ID = "urn:investment-research-kb:contract:strategy-input-ref:v1"
_CONTEXT_PACK_ID = "urn:investment-research-kb:contract:context-pack:v1"
_EVIDENCE_BUNDLE_ID = "urn:investment-research-kb:contract:evidence-bundle:v1"


class ReferenceValidationCode(StrEnum):
    """Stable fail-closed codes for the public reference verification slice."""

    FIXTURE_STRUCTURE = "fixture_structure"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    RELEASE_IDENTITY_MISMATCH = "release_identity_mismatch"
    RELEASE_NOT_PUBLISHED = "release_not_published"
    MANIFEST_HASH_MISMATCH = "manifest_hash_mismatch"
    ARTIFACT_INVENTORY_MISMATCH = "artifact_inventory_mismatch"
    ARTIFACT_SIZE_MISMATCH = "artifact_size_mismatch"
    ARTIFACT_HASH_MISMATCH = "artifact_hash_mismatch"
    ARTIFACT_SCHEMA_MISMATCH = "artifact_schema_mismatch"
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    RECORD_COUNT_MISMATCH = "record_count_mismatch"
    CHANGE_STREAM_MISMATCH = "change_stream_mismatch"
    INPUT_REF_MISMATCH = "input_ref_mismatch"
    SOURCE_RELEASE_MISMATCH = "source_release_mismatch"
    EVIDENCE_CHAIN_MISMATCH = "evidence_chain_mismatch"
    PIT_VIOLATION = "pit_violation"
    PROJECTION_UNSUPPORTED = "projection_unsupported"


class ReferenceFixtureError(ValueError):
    """A pinned public fixture failed deterministic consumer validation."""

    def __init__(self, code: ReferenceValidationCode, message: str) -> None:
        self.code = code
        super().__init__(f"{code.value}: {message}")


@dataclass(frozen=True, slots=True)
class ValidatedArtifact:
    artifact_id: str
    item_type: str
    record_schema_id: str
    record_schema_version: str
    record_schema_hash: HashDigest
    artifact_hash: HashDigest
    logical_content_hash: HashDigest
    size_bytes: int
    record_count: int | None
    content: bytes


@dataclass(frozen=True, slots=True)
class ValidatedRelease:
    release_id: str
    created_at: datetime
    knowledge_cutoff: datetime
    supersedes_release_id: str | None
    manifest_hash: HashDigest
    status_event_id: str
    status_event_hash: HashDigest
    status_sequence: int
    status_recorded_at: datetime
    artifacts: tuple[ValidatedArtifact, ...]


@dataclass(frozen=True, slots=True)
class ValidatedChange:
    change_id: str
    cursor: str
    release_id: str
    status_event_id: str
    status_event_hash: HashDigest
    status_sequence: int


@dataclass(frozen=True, slots=True)
class ReferenceFixtureResult:
    strategy_input_ref: StrategyInputRef
    receipt: ArtifactConsumptionReceipt
    verified_knowledge_input: VerifiedKnowledgeInput
    releases: tuple[ValidatedRelease, ...]
    changes: tuple[ValidatedChange, ...]


@dataclass(frozen=True, slots=True)
class _ProjectionEvidence:
    verified_at: datetime
    event_at: datetime | None
    source_published_at: datetime | None
    first_seen_at: datetime


def _fail(code: ReferenceValidationCode, message: str) -> NoReturn:
    raise ReferenceFixtureError(code, message)


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, f"{field} must be an object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, f"{field} must be text")
    return value


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool):
        _fail(
            ReferenceValidationCode.FIXTURE_STRUCTURE,
            f"{field} must be a non-negative integer",
        )
    if not isinstance(value, int):
        _fail(
            ReferenceValidationCode.FIXTURE_STRUCTURE,
            f"{field} must be a non-negative integer",
        )
    if value < 0:
        _fail(
            ReferenceValidationCode.FIXTURE_STRUCTURE,
            f"{field} must be a non-negative integer",
        )
    return value


def _digest(value: object, *, field: str) -> HashDigest:
    digest = _object(value, field=field)
    if set(digest) != {"algorithm", "value"}:
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, f"{field} must be a hash object")
    try:
        return HashDigest(algorithm=digest["algorithm"], value=digest["value"])
    except (TypeError, ValueError) as exc:
        raise ReferenceFixtureError(
            ReferenceValidationCode.FIXTURE_STRUCTURE,
            f"{field} is not lowercase SHA-256",
        ) from exc


def _utc(value: object, *, field: str) -> datetime:
    text = _text(value, field=field)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReferenceFixtureError(
            ReferenceValidationCode.FIXTURE_STRUCTURE,
            f"{field} is not a UTC timestamp",
        ) from exc


def _optional_utc(value: object, *, field: str) -> datetime | None:
    if value is None:
        return None
    return _utc(value, field=field)


def _validate(
    catalog: KBContractCatalog,
    contract_id: str,
    instance: object,
    *,
    field: str,
) -> None:
    try:
        catalog.validate_instance(contract_id, instance)
    except ContractValidationError as exc:
        raise ReferenceFixtureError(
            ReferenceValidationCode.SCHEMA_VALIDATION_FAILED,
            f"{field} does not satisfy {contract_id}",
        ) from exc


def _schema_contract(catalog: KBContractCatalog, contract_id: str) -> SchemaContract:
    for contract in catalog.schema_contracts:
        if contract.contract_id == contract_id:
            return contract
    _fail(
        ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
        f"schema is not pinned: {contract_id}",
    )


def _verify_semantic_content_hash(
    value: Mapping[str, Any],
    *,
    schema_id: str,
    artifact_id: str,
) -> None:
    hash_field = {
        _CONTEXT_PACK_ID: "context_pack_hash",
        _EVIDENCE_BUNDLE_ID: "bundle_hash",
    }.get(schema_id)
    if hash_field is None:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            f"reference fixture does not support semantic Schema {schema_id}",
        )
    declared = _digest(value.get(hash_field), field=f"{artifact_id}.{hash_field}")
    unsigned = {key: nested for key, nested in value.items() if key != hash_field}
    actual = sha256(canonical_json_bytes(unsigned)).hexdigest()
    if actual != declared.value:
        _fail(
            ReferenceValidationCode.CONTENT_HASH_MISMATCH,
            f"artifact {artifact_id} has an invalid {hash_field}",
        )


def _artifact_bytes(
    catalog: KBContractCatalog,
    item: Mapping[str, Any],
    fixture_value: object,
) -> bytes:
    if item.get("item_type") == "schema":
        pointer = _object(fixture_value, field="schema artifact pointer")
        if set(pointer) != {"fixture_contract_file"}:
            _fail(
                ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
                "schema artifact must point to one pinned contract file",
            )
        filename = _text(pointer["fixture_contract_file"], field="fixture_contract_file")
        path = PurePosixPath(filename)
        if len(path.parts) != 1 or path.name != filename:
            _fail(
                ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
                "schema artifact pointer must be a basename",
            )
        contract = _schema_contract(catalog, _text(item.get("record_schema_id"), field="schema"))
        if PurePosixPath(contract.relative_path).name != filename:
            _fail(
                ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
                "schema artifact points to a different contract",
            )
        return catalog.read_vendor_bytes(contract.relative_path)
    return canonical_json_bytes(fixture_value) + b"\n"


def _validate_artifacts(
    catalog: KBContractCatalog,
    manifest: Mapping[str, Any],
    fixture_artifacts: Mapping[str, Any],
) -> tuple[ValidatedArtifact, ...]:
    items = _array(manifest.get("release_items"), field="manifest.release_items")
    identifiers = [
        _text(_object(item, field="release item").get("artifact_id"), field="id") for item in items
    ]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(fixture_artifacts):
        _fail(
            ReferenceValidationCode.ARTIFACT_INVENTORY_MISMATCH,
            "Manifest and fixture artifact inventories differ",
        )

    validated: list[ValidatedArtifact] = []
    for raw_item in items:
        item = _object(raw_item, field="release item")
        artifact_id = _text(item["artifact_id"], field="artifact_id")
        item_type = _text(item["item_type"], field="item_type")
        schema_id = _text(item["record_schema_id"], field="record_schema_id")
        schema_version = _text(item["record_schema_version"], field="record_schema_version")
        schema_hash = _digest(item["record_schema_hash"], field="record_schema_hash")
        schema_contract = _schema_contract(catalog, schema_id)
        if (
            schema_version != schema_contract.schema_version
            or schema_hash.value != schema_contract.canonical_sha256
        ):
            _fail(
                ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
                f"artifact {artifact_id} schema identity differs from the official lock",
            )

        if item.get("format") != "json" or item.get("sort_keys") != []:
            _fail(
                ReferenceValidationCode.PROJECTION_UNSUPPORTED,
                f"reference fixture only supports single-record JSON artifact {artifact_id}",
            )
        if item_type == "schema":
            if item.get("media_type") != "application/schema+json":
                _fail(
                    ReferenceValidationCode.ARTIFACT_SCHEMA_MISMATCH,
                    f"schema artifact {artifact_id} has the wrong media type",
                )
        else:
            expected_item_type = {
                _CONTEXT_PACK_ID: "context_pack",
                _EVIDENCE_BUNDLE_ID: "evidence_bundle",
            }.get(schema_id)
            if expected_item_type != item_type or item.get("media_type") != "application/json":
                _fail(
                    ReferenceValidationCode.PROJECTION_UNSUPPORTED,
                    f"artifact {artifact_id} is outside the reference fixture profile",
                )

        fixture_value = fixture_artifacts[artifact_id]
        content = _artifact_bytes(catalog, item, fixture_value)
        expected_size = _integer(item["size_bytes"], field="size_bytes")
        artifact_hash = _digest(item["artifact_hash"], field="artifact_hash")
        logical_hash = _digest(item["logical_content_hash"], field="logical_content_hash")
        if len(content) != expected_size:
            _fail(
                ReferenceValidationCode.ARTIFACT_SIZE_MISMATCH,
                f"artifact {artifact_id} size differs from Manifest",
            )
        actual_hash = sha256(content).hexdigest()
        if actual_hash != artifact_hash.value or actual_hash != logical_hash.value:
            _fail(
                ReferenceValidationCode.ARTIFACT_HASH_MISMATCH,
                f"artifact {artifact_id} bytes differ from Manifest",
            )

        record_count = item["record_count"]
        if item_type == "schema":
            if record_count is not None:
                _fail(
                    ReferenceValidationCode.RECORD_COUNT_MISMATCH,
                    f"schema artifact {artifact_id} must have null record_count",
                )
        else:
            if record_count != 1:
                _fail(
                    ReferenceValidationCode.RECORD_COUNT_MISMATCH,
                    f"fixture JSON artifact {artifact_id} must contain one record",
                )
            _validate(catalog, schema_id, fixture_value, field=f"artifact {artifact_id}")
            _verify_semantic_content_hash(
                _object(fixture_value, field=f"artifact {artifact_id}"),
                schema_id=schema_id,
                artifact_id=artifact_id,
            )

        validated.append(
            ValidatedArtifact(
                artifact_id=artifact_id,
                item_type=item_type,
                record_schema_id=schema_id,
                record_schema_version=schema_version,
                record_schema_hash=schema_hash,
                artifact_hash=artifact_hash,
                logical_content_hash=logical_hash,
                size_bytes=expected_size,
                record_count=record_count,
                content=content,
            )
        )
    return tuple(sorted(validated, key=lambda artifact: artifact.artifact_id))


def _validate_release(
    catalog: KBContractCatalog,
    raw_release: object,
) -> tuple[ValidatedRelease, dict[str, Any], dict[str, Any]]:
    release = _object(raw_release, field="release")
    if set(release) != {"dataset_release", "manifest", "artifacts"}:
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, "release keys differ")
    dataset = _object(release["dataset_release"], field="dataset_release")
    manifest = _object(release["manifest"], field="manifest")
    fixture_artifacts = _object(release["artifacts"], field="artifacts")
    _validate(catalog, _DATASET_RELEASE_ID, dataset, field="dataset_release")
    _validate(catalog, _RELEASE_MANIFEST_ID, manifest, field="manifest")

    release_id = _text(dataset["release_id"], field="release_id")
    if release_id != manifest.get("release_id"):
        _fail(
            ReferenceValidationCode.RELEASE_IDENTITY_MISMATCH,
            "dataset Release and Manifest release IDs differ",
        )
    created_at_text = _text(dataset["created_at"], field="created_at")
    supersedes_release_id = dataset["supersedes_release_id"]
    if created_at_text != manifest.get("created_at") or supersedes_release_id != manifest.get(
        "supersedes_release_id"
    ):
        _fail(
            ReferenceValidationCode.RELEASE_IDENTITY_MISMATCH,
            "dataset Release and Manifest lineage fields differ",
        )
    if supersedes_release_id is not None:
        supersedes_release_id = _text(
            supersedes_release_id,
            field="supersedes_release_id",
        )
    cutoff_text = _text(dataset["knowledge_cutoff"], field="knowledge_cutoff")
    if cutoff_text != manifest.get("knowledge_cutoff"):
        _fail(
            ReferenceValidationCode.RELEASE_IDENTITY_MISMATCH,
            "dataset Release and Manifest knowledge cutoffs differ",
        )
    if manifest.get("canonicalization_profile") != CANONICALIZATION_PROFILE:
        _fail(
            ReferenceValidationCode.MANIFEST_HASH_MISMATCH,
            "unsupported Manifest canonicalization profile",
        )

    manifest_hash = _digest(manifest["manifest_hash"], field="manifest_hash")
    if manifest_sha256(manifest) != manifest_hash.value:
        _fail(ReferenceValidationCode.MANIFEST_HASH_MISMATCH, "Manifest self-hash differs")
    manifest_ref = _object(dataset["manifest_ref"], field="dataset_release.manifest_ref")
    if _digest(manifest_ref["hash"], field="manifest_ref.hash") != manifest_hash:
        _fail(
            ReferenceValidationCode.RELEASE_IDENTITY_MISMATCH,
            "dataset Release Manifest reference differs",
        )

    current_status = _object(dataset["current_status"], field="current_status")
    if current_status.get("status") != "published":
        _fail(
            ReferenceValidationCode.RELEASE_NOT_PUBLISHED,
            f"release {release_id} is not currently published",
        )
    status_event_id = _text(current_status["event_id"], field="status event ID")
    status_event_hash = _digest(current_status["event_hash"], field="status event hash")
    status_sequence = _integer(current_status["sequence"], field="status sequence")
    status_recorded_at = _utc(
        current_status["recorded_at"],
        field="status recorded_at",
    )
    artifacts = _validate_artifacts(catalog, manifest, fixture_artifacts)
    knowledge_cutoff = _utc(cutoff_text, field="knowledge_cutoff")
    for artifact in artifacts:
        if artifact.item_type == "schema":
            continue
        value = fixture_artifacts[artifact.artifact_id]
        semantic = _object(value, field=f"artifact {artifact.artifact_id}")
        if semantic.get("knowledge_cutoff") != cutoff_text:
            _fail(
                ReferenceValidationCode.PIT_VIOLATION,
                f"artifact {artifact.artifact_id} has a different knowledge cutoff",
            )
        _assert_pit(
            semantic,
            cutoff=knowledge_cutoff,
            path=f"artifact[{artifact.artifact_id}]",
        )
    return (
        ValidatedRelease(
            release_id=release_id,
            created_at=_utc(created_at_text, field="created_at"),
            knowledge_cutoff=knowledge_cutoff,
            supersedes_release_id=supersedes_release_id,
            manifest_hash=manifest_hash,
            status_event_id=status_event_id,
            status_event_hash=status_event_hash,
            status_sequence=status_sequence,
            status_recorded_at=status_recorded_at,
            artifacts=artifacts,
        ),
        manifest,
        fixture_artifacts,
    )


def _strategy_input_ref(raw: object) -> StrategyInputRef:
    value = _object(raw, field="expected_strategy_input_ref")
    return StrategyInputRef(
        schema_version=_text(value["schema_version"], field="schema_version"),
        dataset_release_id=_text(value["dataset_release_id"], field="dataset_release_id"),
        knowledge_cutoff=_utc(value["knowledge_cutoff"], field="knowledge_cutoff"),
        release_manifest_schema_version=_text(
            value["release_manifest_schema_version"],
            field="release_manifest_schema_version",
        ),
        manifest_hash=_digest(value["manifest_hash"], field="manifest_hash"),
    )


def _validate_changes(
    catalog: KBContractCatalog,
    raw_changes: object,
    releases: Mapping[str, ValidatedRelease],
) -> tuple[ValidatedChange, ...]:
    changes: list[ValidatedChange] = []
    seen_changes: set[str] = set()
    seen_cursors: set[str] = set()
    seen_releases: set[str] = set()
    for raw_change in _array(raw_changes, field="changes"):
        change = _object(raw_change, field="change")
        _validate(catalog, _CHANGE_RECORD_ID, change, field="change")
        change_id = _text(change["change_id"], field="change_id")
        cursor = _text(change["cursor"], field="cursor")
        release_id = _text(change["release_id"], field="release_id")
        if change_id in seen_changes or cursor in seen_cursors or release_id in seen_releases:
            _fail(
                ReferenceValidationCode.CHANGE_STREAM_MISMATCH,
                "change IDs, cursors, and fixture Release events must be unique",
            )
        release = releases.get(release_id)
        if release is None:
            _fail(
                ReferenceValidationCode.CHANGE_STREAM_MISMATCH,
                "change refers to an unknown Release",
            )
        status = _object(change["status_event"], field="change.status_event")
        event_hash = _digest(status["event_hash"], field="status_event.event_hash")
        sequence = _integer(status["sequence"], field="status_event.sequence")
        if (
            change.get("change_type") != "dataset_release.published"
            or status.get("status") != "published"
            or status.get("event_id") != release.status_event_id
            or event_hash != release.status_event_hash
            or sequence != release.status_sequence
            or change.get("knowledge_cutoff")
            != release.knowledge_cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
            or change.get("supersedes_release_id") != release.supersedes_release_id
            or _utc(change.get("recorded_at"), field="change.recorded_at")
            != release.status_recorded_at
            or _digest(change["manifest_ref"]["hash"], field="change.manifest_ref.hash")
            != release.manifest_hash
        ):
            _fail(
                ReferenceValidationCode.CHANGE_STREAM_MISMATCH,
                f"change does not bind the validated Release {release_id}",
            )
        seen_changes.add(change_id)
        seen_cursors.add(cursor)
        seen_releases.add(release_id)
        changes.append(
            ValidatedChange(
                change_id=change_id,
                cursor=cursor,
                release_id=release_id,
                status_event_id=release.status_event_id,
                status_event_hash=event_hash,
                status_sequence=sequence,
            )
        )
    if seen_releases != set(releases):
        _fail(
            ReferenceValidationCode.CHANGE_STREAM_MISMATCH,
            "change stream does not cover every fixture Release",
        )
    return tuple(changes)


def _assert_pit(value: object, *, cutoff: datetime, path: str = "context_pack") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "available_at" and _utc(nested, field=f"{path}.available_at") > cutoff:
                _fail(ReferenceValidationCode.PIT_VIOLATION, f"future information at {path}")
            _assert_pit(nested, cutoff=cutoff, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _assert_pit(nested, cutoff=cutoff, path=f"{path}[{index}]")


def _index_objects(values: object, *, key: str, field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for index, raw_value in enumerate(_array(values, field=field)):
        value = _object(raw_value, field=f"{field}[{index}]")
        identifier = _text(value.get(key), field=f"{field}[{index}].{key}")
        if identifier in indexed:
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"{field} contains duplicate {key}",
            )
        indexed[identifier] = value
    return indexed


def _bind_source_release(
    raw_reference: object,
    releases: Mapping[str, ValidatedRelease],
) -> ValidatedRelease:
    reference = _object(raw_reference, field="source_release")
    release_id = _text(reference.get("release_id"), field="source_release.release_id")
    release = releases.get(release_id)
    if release is None:
        _fail(
            ReferenceValidationCode.SOURCE_RELEASE_MISMATCH,
            f"Context Pack points to unknown Release {release_id}",
        )
    cutoff = reference.get("knowledge_cutoff")
    manifest_hash = reference.get("manifest_hash")
    if (
        cutoff is None
        or manifest_hash is None
        or _utc(cutoff, field="source_release.knowledge_cutoff") != release.knowledge_cutoff
        or _digest(manifest_hash, field="source_release.manifest_hash") != release.manifest_hash
    ):
        _fail(
            ReferenceValidationCode.SOURCE_RELEASE_MISMATCH,
            f"Context Pack does not bind exact Release {release_id}",
        )
    return release


def _validate_source_release_chain(
    context_pack: Mapping[str, Any],
    context_manifest: Mapping[str, Any],
    context_release: ValidatedRelease,
    releases: Mapping[str, ValidatedRelease],
    fixture_artifacts: Mapping[str, Mapping[str, Any]],
) -> tuple[ValidatedRelease, Mapping[str, Any]]:
    build = _object(context_manifest.get("context_pack_build"), field="context_pack_build")
    for field in (
        "context_pack_id",
        "pack_key",
        "version",
        "supersedes_context_pack_id",
    ):
        if build.get(field) != context_pack.get(field):
            _fail(
                ReferenceValidationCode.SOURCE_RELEASE_MISMATCH,
                f"Context Pack and Manifest build disagree on {field}",
            )

    source_references = _array(context_pack.get("source_releases"), field="source_releases")
    if len(source_references) != 1:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            "reference projection requires exactly one source Release",
        )
    build_reference = _object(
        build.get("source_release"), field="context_pack_build.source_release"
    )
    context_reference = _object(source_references[0], field="source_releases[0]")
    if build_reference != context_reference:
        _fail(
            ReferenceValidationCode.SOURCE_RELEASE_MISMATCH,
            "Context Pack and Manifest build point to different source Releases",
        )
    source_release = _bind_source_release(context_reference, releases)
    if source_release.release_id == context_release.release_id:
        _fail(
            ReferenceValidationCode.SOURCE_RELEASE_MISMATCH,
            "Context Pack cannot use its own Release as the fixture evidence source",
        )
    if source_release.knowledge_cutoff > context_release.knowledge_cutoff:
        _fail(
            ReferenceValidationCode.PIT_VIOLATION,
            "Context Pack source Release has a later knowledge cutoff",
        )

    evidence_artifacts = [
        artifact
        for artifact in source_release.artifacts
        if artifact.item_type == "evidence_bundle"
        and artifact.record_schema_id == _EVIDENCE_BUNDLE_ID
    ]
    if len(evidence_artifacts) != 1:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            "source Release must contain exactly one supported Evidence Bundle",
        )
    evidence_value = fixture_artifacts[source_release.release_id][evidence_artifacts[0].artifact_id]
    return source_release, _object(evidence_value, field="evidence bundle")


def _validated_span_review_time(
    span: Mapping[str, Any],
    *,
    source_cutoff: datetime,
) -> datetime:
    available_at = _utc(span.get("available_at"), field="span.available_at")
    review = _object(span.get("review"), field="span.review")
    reviewed_at = _utc(review.get("reviewed_at"), field="span.review.reviewed_at")
    if not available_at <= reviewed_at <= source_cutoff:
        _fail(
            ReferenceValidationCode.PIT_VIOLATION,
            "Evidence span review time is outside its source Release PIT window",
        )
    return reviewed_at


def _validated_fact_times(
    fact: Mapping[str, Any],
    *,
    source_cutoff: datetime,
) -> tuple[datetime, datetime, datetime]:
    available_at = _utc(fact.get("available_at"), field="fact.available_at")
    review = _object(fact.get("review"), field="fact.review")
    reviewed_at = _utc(review.get("reviewed_at"), field="fact.review.reviewed_at")
    knowledge_published_at = _utc(
        fact.get("knowledge_published_at"),
        field="fact.knowledge_published_at",
    )
    publication = _object(fact.get("publication"), field="fact.publication")
    recorded_at = _utc(
        publication.get("recorded_at"),
        field="fact.publication.recorded_at",
    )
    if not (available_at <= reviewed_at <= knowledge_published_at <= recorded_at <= source_cutoff):
        _fail(
            ReferenceValidationCode.PIT_VIOLATION,
            "Published Fact times are inconsistent with its source Release cutoff",
        )
    return available_at, reviewed_at, recorded_at


def _validated_document_times(
    document: Mapping[str, Any],
    *,
    source_cutoff: datetime,
) -> tuple[datetime | None, datetime, datetime, datetime]:
    source_published_at = _optional_utc(
        document.get("source_published_at"),
        field="document.source_published_at",
    )
    first_seen_at = _utc(document.get("first_seen_at"), field="document.first_seen_at")
    fetched_at = _utc(document.get("fetched_at"), field="document.fetched_at")
    available_at = _utc(document.get("available_at"), field="document.available_at")
    observed_times = (first_seen_at, fetched_at, available_at)
    if any(timestamp > source_cutoff for timestamp in observed_times) or (
        source_published_at is not None
        and (source_published_at > source_cutoff or source_published_at > available_at)
    ):
        _fail(
            ReferenceValidationCode.PIT_VIOLATION,
            "Evidence document times exceed its source Release cutoff",
        )
    return source_published_at, first_seen_at, fetched_at, available_at


def _validate_closed_evidence_chain(
    context_pack: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    *,
    source_release: ValidatedRelease,
    context_release: ValidatedRelease,
) -> dict[str, _ProjectionEvidence]:
    if _array(evidence_bundle.get("candidate_events"), field="candidate_events"):
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            "reference projection does not silently drop candidate events",
        )

    graph = _object(context_pack.get("industry_graph"), field="industry_graph")
    nodes = _index_objects(
        graph.get("nodes"),
        key="industry_node_id",
        field="industry_graph.nodes",
    )
    _index_objects(
        graph.get("nodes"),
        key="node_key",
        field="industry_graph.nodes",
    )
    edges = _index_objects(
        graph.get("edges"),
        key="industry_edge_version_id",
        field="industry_graph.edges",
    )
    evidence_refs = _index_objects(
        graph.get("evidence_refs"),
        key="industry_evidence_ref_id",
        field="industry_graph.evidence_refs",
    )
    documents = _index_objects(
        evidence_bundle.get("document_versions"),
        key="document_version_id",
        field="evidence_bundle.document_versions",
    )
    spans = _index_objects(
        evidence_bundle.get("evidence_spans"),
        key="evidence_span_id",
        field="evidence_bundle.evidence_spans",
    )
    facts = _index_objects(
        evidence_bundle.get("facts"),
        key="fact_id",
        field="evidence_bundle.facts",
    )
    links = _index_objects(
        evidence_bundle.get("evidence_links"),
        key="evidence_link_id",
        field="evidence_bundle.evidence_links",
    )
    sources = _index_objects(
        context_pack.get("sources"),
        key="document_version_id",
        field="sources",
    )
    document_times = {
        document_id: _validated_document_times(
            document,
            source_cutoff=source_release.knowledge_cutoff,
        )
        for document_id, document in documents.items()
    }

    for document_id, source in sources.items():
        document = documents.get(document_id)
        if document is None or any(
            source.get(field) != document.get(field)
            for field in ("provider", "title", "source_url", "available_at", "content_hash")
        ):
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"Context Pack source does not bind Evidence document {document_id}",
            )
        for span_id in _array(source.get("evidence_span_ids"), field="source.evidence_span_ids"):
            span = spans.get(_text(span_id, field="source evidence span ID"))
            if span is None or span.get("document_version_id") != document_id:
                _fail(
                    ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                    f"source {document_id} points to a foreign evidence span",
                )

    used_nodes: set[str] = set()
    used_refs: set[str] = set()
    used_links: set[str] = set()
    used_spans: set[str] = set()
    used_facts: set[str] = set()
    projection_evidence: dict[str, _ProjectionEvidence] = {}
    for edge_version_id, edge in edges.items():
        from_id = _text(edge.get("from_industry_node_id"), field="edge.from node ID")
        to_id = _text(edge.get("to_industry_node_id"), field="edge.to node ID")
        from_node = nodes.get(from_id)
        to_node = nodes.get(to_id)
        if (
            from_node is None
            or to_node is None
            or edge.get("from_node_key") != from_node.get("node_key")
            or edge.get("to_node_key") != to_node.get("node_key")
        ):
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"edge {edge_version_id} does not bind its endpoint nodes",
            )
        used_nodes.update((from_id, to_id))
        edge_available_at = _utc(edge.get("available_at"), field="edge.available_at")
        endpoint_times = (
            _utc(from_node.get("available_at"), field="from_node.available_at"),
            _utc(to_node.get("available_at"), field="to_node.available_at"),
        )
        if any(timestamp > edge_available_at for timestamp in endpoint_times):
            _fail(
                ReferenceValidationCode.PIT_VIOLATION,
                f"edge {edge_version_id} predates one of its endpoint nodes",
            )

        edge_fact_ids: set[str] = set()
        edge_document_ids: set[str] = set()
        for raw_ref_id in _array(edge.get("evidence_ref_ids"), field="edge.evidence_ref_ids"):
            ref_id = _text(raw_ref_id, field="edge evidence ref ID")
            reference = evidence_refs.get(ref_id)
            if (
                reference is None
                or reference.get("target_kind") != "edge"
                or reference.get("target_version_id") != edge_version_id
                or reference.get("stance") != "supports"
            ):
                _fail(
                    ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                    f"edge {edge_version_id} has an invalid evidence reference",
                )
            fact_id = _text(reference.get("fact_id"), field="evidence reference fact ID")
            link_id = _text(
                reference.get("evidence_link_id"),
                field="evidence reference link ID",
            )
            span_id = _text(
                reference.get("evidence_span_id"),
                field="evidence reference span ID",
            )
            link = links.get(link_id)
            span = spans.get(span_id)
            fact = facts.get(fact_id)
            if (
                link is None
                or span is None
                or fact is None
                or link.get("target_kind") != "fact"
                or link.get("target_id") != fact_id
                or link.get("evidence_span_id") != span_id
                or link.get("stance") != reference.get("stance")
                or span.get("document_version_id") not in sources
                or link_id not in fact.get("evidence_link_ids", [])
                or _object(fact.get("review"), field="fact.review").get("status") != "approved"
                or _object(fact.get("publication"), field="fact.publication").get("status")
                != "published"
                or _object(span.get("review"), field="span.review").get("status") != "approved"
            ):
                _fail(
                    ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                    f"evidence reference {ref_id} does not close through a published Fact",
                )
            span_reviewed_at = _validated_span_review_time(
                span,
                source_cutoff=source_release.knowledge_cutoff,
            )
            fact_available_at, _, fact_recorded_at = _validated_fact_times(
                fact,
                source_cutoff=source_release.knowledge_cutoff,
            )
            reference_available_at = _utc(
                reference.get("available_at"),
                field="evidence_reference.available_at",
            )
            if not (
                span_reviewed_at
                <= fact_available_at
                <= fact_recorded_at
                <= reference_available_at
                <= edge_available_at
                <= context_release.knowledge_cutoff
            ):
                _fail(
                    ReferenceValidationCode.PIT_VIOLATION,
                    f"edge {edge_version_id} becomes available before its evidence chain",
                )
            document_id = _text(
                span.get("document_version_id"),
                field="span.document_version_id",
            )
            (
                document_source_published_at,
                document_first_seen_at,
                document_fetched_at,
                document_available_at,
            ) = document_times[document_id]
            span_available_at = _utc(span.get("available_at"), field="span.available_at")
            document_dependencies = (
                document_first_seen_at,
                document_fetched_at,
                document_available_at,
            )
            if any(timestamp > span_available_at for timestamp in document_dependencies) or (
                document_source_published_at is not None
                and document_source_published_at > span_available_at
            ):
                _fail(
                    ReferenceValidationCode.PIT_VIOLATION,
                    f"span {span_id} predates its source document availability",
                )
            used_refs.add(ref_id)
            used_links.add(link_id)
            used_spans.add(span_id)
            used_facts.add(fact_id)
            edge_fact_ids.add(fact_id)
            edge_document_ids.add(document_id)

        attributes = _object(edge.get("attributes"), field="edge.attributes")
        if (
            len(edge_fact_ids) != 1
            or len(edge_document_ids) != 1
            or attributes.get("fact_id") not in edge_fact_ids
        ):
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"edge {edge_version_id} is not bound to one fixture Fact and document",
            )
        fact = facts[next(iter(edge_fact_ids))]
        from_node = nodes[from_id]
        fact_object = _object(fact.get("object"), field="fact.object")
        edge_semantics = {key: value for key, value in attributes.items() if key != "fact_id"}
        from_attributes = _object(from_node.get("attributes"), field="from_node.attributes")
        if (
            fact.get("predicate") != edge.get("relation_type")
            or fact_object != edge_semantics
            or fact.get("company_id") != from_attributes.get("company_id")
            or edge.get("edge_key") != f"fact:{fact.get('fact_key')}"
        ):
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"edge {edge_version_id} conflicts with its provider Fact semantics",
            )
        document_id = next(iter(edge_document_ids))
        source_published_at, first_seen_at, _, _ = document_times[document_id]
        fact_reviewed_at = _validated_fact_times(
            fact,
            source_cutoff=source_release.knowledge_cutoff,
        )[1]
        projection_evidence[edge_version_id] = _ProjectionEvidence(
            verified_at=fact_reviewed_at,
            event_at=_optional_utc(fact.get("event_at"), field="fact.event_at"),
            source_published_at=source_published_at,
            first_seen_at=first_seen_at,
        )

    if not edges or not nodes or not evidence_refs:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            "reference projection requires the non-empty official graph shape",
        )
    if (
        used_nodes != set(nodes)
        or used_refs != set(evidence_refs)
        or used_links != set(links)
        or used_spans != set(spans)
        or used_facts != set(facts)
        or set(sources) != set(documents)
    ):
        _fail(
            ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
            "fixture contains unlinked evidence or graph objects",
        )
    return projection_evidence


def _project_context_pack(
    context_pack: Mapping[str, Any],
    strategy_input_ref: StrategyInputRef,
    receipt: ArtifactConsumptionReceipt,
    projection_evidence: Mapping[str, _ProjectionEvidence],
) -> VerifiedKnowledgeInput:
    unsupported_collections = (
        "terminology",
        "company_mappings",
        "key_metrics",
        "known_events",
        "known_counterexamples",
        "missing_items",
    )
    nonempty = [name for name in unsupported_collections if context_pack.get(name)]
    if nonempty:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            f"reference projection does not silently drop: {', '.join(nonempty)}",
        )
    cutoff = strategy_input_ref.knowledge_cutoff
    _assert_pit(context_pack, cutoff=cutoff)
    graph = _object(context_pack.get("industry_graph"), field="industry_graph")
    for node in _array(graph.get("nodes"), field="industry_graph.nodes"):
        value = _object(node, field="industry node")
        if value.get("review_status") != "approved" or value.get("conflict_status") != "none":
            _fail(
                ReferenceValidationCode.PROJECTION_UNSUPPORTED,
                "reference projection requires approved, conflict-free nodes",
            )

    facts: list[VerifiedFact] = []
    for raw_edge in _array(graph.get("edges"), field="industry_graph.edges"):
        edge = _object(raw_edge, field="industry edge")
        if edge.get("review_status") != "approved" or edge.get("conflict_status") != "none":
            _fail(
                ReferenceValidationCode.PROJECTION_UNSUPPORTED,
                "reference projection requires approved, conflict-free edges",
            )
        edge_version_id = _text(edge["industry_edge_version_id"], field="edge version ID")
        evidence = projection_evidence.get(edge_version_id)
        if evidence is None:
            _fail(
                ReferenceValidationCode.EVIDENCE_CHAIN_MISMATCH,
                f"edge {edge_version_id} has no validated projection evidence",
            )
        available_at = _utc(edge["available_at"], field="edge.available_at")
        facts.append(
            VerifiedFact(
                fact_id=edge_version_id,
                subject_id=_text(edge["from_industry_node_id"], field="from node ID"),
                predicate=_text(edge["relation_type"], field="relation type"),
                value={
                    "object_id": _text(edge["to_industry_node_id"], field="to node ID"),
                    "object_key": _text(edge["to_node_key"], field="to node key"),
                    "attributes": deepcopy(_object(edge["attributes"], field="edge attributes")),
                },
                verified_at=evidence.verified_at,
                available_at=available_at,
                evidence_ids=tuple(sorted(_array(edge["evidence_ref_ids"], field="evidence refs"))),
                metadata={
                    "provider_contract_version": "1.0.0",
                    "projection_version": CONTEXT_PACK_PROJECTION_VERSION,
                    "provider_object_kind": "industry_edge",
                    "edge_key": _text(edge["edge_key"], field="edge key"),
                    "content_hash": deepcopy(edge["content_hash"]),
                    "review_status": "approved",
                    "conflict_status": "none",
                },
                event_at=evidence.event_at,
                source_published_at=evidence.source_published_at,
                first_seen_at=evidence.first_seen_at,
            )
        )
    facts.sort(key=lambda fact: fact.fact_id)
    identity = sha256(
        (
            receipt.receipt_hash.value
            + ":"
            + CONTEXT_PACK_PROJECTION_VERSION
            + ":context-pack-industry-edges"
        ).encode("ascii")
    ).hexdigest()
    return VerifiedKnowledgeInput(
        schema_version=VERIFIED_KNOWLEDGE_INPUT_SCHEMA_VERSION,
        input_id=f"vki_{identity[:32]}",
        strategy_input_ref=strategy_input_ref,
        facts=tuple(facts),
    )


def _verify_stage6_reference_document(
    catalog: KBContractCatalog,
    document: Mapping[str, Any],
) -> ReferenceFixtureResult:
    """Validate a detached fixture document for failure-injection tests."""

    if not isinstance(catalog, KBContractCatalog):
        raise TypeError("catalog must be a verified KBContractCatalog")
    fixture = deepcopy(dict(document))
    if set(fixture) != {
        "schema_version",
        "purpose",
        "releases",
        "changes",
        "expected_strategy_input_ref",
    }:
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, "fixture keys differ")
    if fixture["schema_version"] != "1.0.0":
        _fail(ReferenceValidationCode.FIXTURE_STRUCTURE, "fixture version is unsupported")

    expected_ref_value = _object(
        fixture["expected_strategy_input_ref"],
        field="expected_strategy_input_ref",
    )
    _validate(
        catalog,
        _STRATEGY_INPUT_REF_ID,
        expected_ref_value,
        field="expected_strategy_input_ref",
    )
    input_ref = _strategy_input_ref(expected_ref_value)

    validated_releases: list[ValidatedRelease] = []
    manifests: dict[str, dict[str, Any]] = {}
    fixture_artifacts: dict[str, dict[str, Any]] = {}
    for raw_release in _array(fixture["releases"], field="releases"):
        release, manifest, artifacts = _validate_release(catalog, raw_release)
        if release.release_id in manifests:
            _fail(
                ReferenceValidationCode.RELEASE_IDENTITY_MISMATCH,
                "fixture contains duplicate Release IDs",
            )
        validated_releases.append(release)
        manifests[release.release_id] = manifest
        fixture_artifacts[release.release_id] = artifacts
    release_by_id = {release.release_id: release for release in validated_releases}
    context_release = release_by_id.get(input_ref.dataset_release_id)
    if context_release is None:
        _fail(ReferenceValidationCode.INPUT_REF_MISMATCH, "input Release is absent")
    if (
        input_ref.knowledge_cutoff != context_release.knowledge_cutoff
        or input_ref.manifest_hash != context_release.manifest_hash
        or input_ref.schema_version != "1.0.0"
        or input_ref.release_manifest_schema_version != "1.0.0"
    ):
        _fail(
            ReferenceValidationCode.INPUT_REF_MISMATCH,
            "five-field StrategyInputRef differs from the validated Release",
        )

    changes = _validate_changes(catalog, fixture["changes"], release_by_id)
    context_items = tuple(
        ArtifactReceiptItem(
            artifact_id=artifact.artifact_id,
            item_type=artifact.item_type,
            artifact_hash=artifact.artifact_hash,
            size_bytes=artifact.size_bytes,
            record_count=artifact.record_count,
        )
        for artifact in context_release.artifacts
    )
    receipt = ArtifactConsumptionReceipt.create(
        schema_version=ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
        consumer_contract_version=CONSUMER_CONTRACT_VERSION,
        strategy_input_ref=input_ref,
        artifacts=context_items,
    )

    context_candidates = [
        artifact
        for artifact in context_release.artifacts
        if artifact.record_schema_id == _CONTEXT_PACK_ID and artifact.item_type == "context_pack"
    ]
    if len(context_candidates) != 1:
        _fail(
            ReferenceValidationCode.PROJECTION_UNSUPPORTED,
            "input Release must contain exactly one supported Context Pack",
        )
    context_value = fixture_artifacts[context_release.release_id][context_candidates[0].artifact_id]
    context_pack = _object(context_value, field="context pack")
    source_release, evidence_bundle = _validate_source_release_chain(
        context_pack,
        manifests[context_release.release_id],
        context_release,
        release_by_id,
        fixture_artifacts,
    )
    projection_evidence = _validate_closed_evidence_chain(
        context_pack,
        evidence_bundle,
        source_release=source_release,
        context_release=context_release,
    )
    verified_input = _project_context_pack(
        context_pack,
        input_ref,
        receipt,
        projection_evidence,
    )
    return ReferenceFixtureResult(
        strategy_input_ref=input_ref,
        receipt=receipt,
        verified_knowledge_input=verified_input,
        releases=tuple(sorted(validated_releases, key=lambda release: release.release_id)),
        changes=changes,
    )


def verify_stage6_reference_fixture(catalog: KBContractCatalog) -> ReferenceFixtureResult:
    """Validate and project only the catalog's hash-locked public fixture.

    The embedded ``published`` state is contract-test data.  This function does
    not establish that a real Release remains published or authorize a new run.
    """

    if not isinstance(catalog, KBContractCatalog):
        raise TypeError("catalog must be a verified KBContractCatalog")
    return _verify_stage6_reference_document(catalog, catalog.stage6_fixture)
