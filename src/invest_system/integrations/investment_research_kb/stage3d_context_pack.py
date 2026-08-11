"""Stage 3D public-HTTPS Context Pack validation and zero-authority smoke.

The module consumes only already-pinned public contracts and the read-only HTTP
client.  It never imports provider code, reads provider storage, persists state,
or applies the synthetic-only Stage 4 business capability to a real Release.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any, NoReturn

from invest_system.canonical import canonical_json_bytes, normalize_utc
from invest_system.consumption import (
    ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ArtifactConsumptionReceipt,
    ArtifactFetchObservation,
    ArtifactReceiptItem,
    DeliveryTransport,
    ProviderReleaseStatus,
    ReleaseAdmissionObservation,
    ReleaseAdmissionStatus,
    ReleaseStatusObservation,
    SchemaValidationResult,
)
from invest_system.models import (
    STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
    CanonicalModel,
    GateOutcome,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
)

from .contracts import ContractValidationError, load_strict_json_bytes
from .http_client import KBReadOnlyHTTPClient, VerifiedHTTPArtifact, VerifiedHTTPReleaseBundle
from .provider_canonical import canonical_json_bytes as provider_canonical_json_bytes
from .provider_canonical import manifest_sha256
from .reference_fixture import CONSUMER_CONTRACT_VERSION
from .transport_contracts import (
    TRANSPORT_SNAPSHOT_LOCK_SHA256,
    TRANSPORT_SOURCE_COMMIT,
    KBTransportContractCatalog,
)

CONTEXT_PACK_SCHEMA_ID = "urn:investment-research-kb:contract:context-pack:v1"
EVIDENCE_BUNDLE_SCHEMA_ID = "urn:investment-research-kb:contract:evidence-bundle:v1"
CONTEXT_PACK_SCHEMA_CANONICAL_SHA256 = (
    "a6432ef884861eae5652faa59b0593841e1f1e68d67b7b615510271820d16e68"
)
EVIDENCE_BUNDLE_SCHEMA_CANONICAL_SHA256 = (
    "660a2c3ce25a3bb4d541c8a532c9ff062a702f40d495753031ce87feae9b0658"
)
STAGE3D_PROVIDER_INPUT_SCHEMA_VERSION = "0.1.0"
STAGE3D_SMOKE_SCHEMA_VERSION = "0.1.0"
STAGE3D_STRATEGY_VERSION = "0.1.0-stage3d"
STAGE3D_RULE_PROFILE = {
    "schema_version": STAGE3D_SMOKE_SCHEMA_VERSION,
    "purpose": "provider_neutral_context_pack_entry_smoke",
    "positive_investment_conclusion_required": False,
    "declared_missing_information_requires_abstain": True,
    "real_strategy_rules_authorized": False,
    "authority_eligible": False,
}


class Stage3DValidationError(ValueError):
    """Stable fail-closed Stage 3D validation error."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> NoReturn:
    raise Stage3DValidationError(code, message)


def _object(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("STRUCTURE_INVALID", f"{field} must be an object")
    return value


def _array(value: object, *, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("STRUCTURE_INVALID", f"{field} must be an array")
    return value


def _text(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("STRUCTURE_INVALID", f"{field} must be non-empty text")
    return value


def _integer(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _fail("STRUCTURE_INVALID", f"{field} must be an integer")
    return value


def _digest(value: object, *, field: str) -> HashDigest:
    item = _object(value, field=field)
    if set(item) != {"algorithm", "value"}:
        _fail("HASH_INVALID", f"{field} must contain exactly algorithm and value")
    try:
        return HashDigest(algorithm=item["algorithm"], value=item["value"])
    except (TypeError, ValueError) as exc:
        raise Stage3DValidationError("HASH_INVALID", f"{field} is not SHA-256") from exc


def _utc(value: object, *, field: str) -> datetime:
    raw = _text(value, field=field)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage3DValidationError("PIT_INVALID", f"{field} is not UTC time") from exc
    return normalize_utc(parsed, field_name=field)


def _optional_utc(value: object, *, field: str) -> datetime | None:
    return None if value is None else _utc(value, field=field)


def _indexed(values: object, *, key: str, field: str) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(_array(values, field=field)):
        item = _object(raw, field=f"{field}[{index}]")
        identifier = _text(item.get(key), field=f"{field}[{index}].{key}")
        if identifier in result:
            _fail("REFERENCE_CLOSURE_INVALID", f"duplicate {field}.{key}: {identifier}")
        result[identifier] = item
    return result


def _semantic_hash(value: Mapping[str, Any], *, field: str) -> str:
    declared = _digest(value.get(field), field=field).value
    unsigned = {key: nested for key, nested in value.items() if key != field}
    actual = sha256(provider_canonical_json_bytes(unsigned)).hexdigest()
    if actual != declared:
        _fail("SEMANTIC_HASH_MISMATCH", f"{field} differs from canonical content")
    return declared


@dataclass(frozen=True, slots=True)
class Stage3DArtifactExpectation:
    artifact_id: str
    sha256: str
    size_bytes: int
    content_type: str
    item_type: str
    schema_id: str
    schema_version: str
    record_schema_hash: str

    @classmethod
    def from_handoff(cls, value: object) -> Stage3DArtifactExpectation:
        item = _object(value, field="handoff artifact")
        return cls(
            artifact_id=_text(item.get("artifact_id"), field="artifact_id"),
            sha256=_text(item.get("sha256"), field="artifact.sha256"),
            size_bytes=_integer(item.get("size_bytes"), field="artifact.size_bytes"),
            content_type=_text(item.get("content_type"), field="artifact.content_type"),
            item_type=_text(item.get("item_type"), field="artifact.item_type"),
            schema_id=_text(item.get("schema_id"), field="artifact.schema_id"),
            schema_version=_text(item.get("schema_version"), field="artifact.schema_version"),
            record_schema_hash=_digest(
                item.get("record_schema_hash"), field="artifact.record_schema_hash"
            ).value,
        )


@dataclass(frozen=True, slots=True)
class Stage3DExpectation:
    handoff_sha256: str
    base_url: str
    context_release_id: str
    context_pack_id: str
    context_pack_hash: str
    source_graph_hash: str
    knowledge_cutoff: datetime
    manifest_hash: str
    strategy_input_ref: StrategyInputRef
    context_artifact: Stage3DArtifactExpectation
    context_schema_artifact: Stage3DArtifactExpectation
    evidence_release_id: str
    evidence_manifest_hash: str
    evidence_artifact: Stage3DArtifactExpectation
    evidence_schema_artifact: Stage3DArtifactExpectation

    @classmethod
    def from_handoff_bytes(
        cls,
        content: bytes,
        *,
        expected_sha256: str,
    ) -> Stage3DExpectation:
        if sha256(content).hexdigest() != expected_sha256:
            _fail("HANDOFF_HASH_MISMATCH", "producer handoff bytes changed")
        raw = _object(load_strict_json_bytes(content, source="Stage 3D handoff"), field="handoff")
        if raw.get("handoff_schema_version") != "1.0.0":
            _fail("HANDOFF_VERSION_UNSUPPORTED", "handoff schema version differs")
        if raw.get("authority_eligible") is not False:
            _fail("AUTHORITY_BOUNDARY_INVALID", "handoff must remain authority-ineligible")
        if (
            raw.get("transport_contract_source_commit") != TRANSPORT_SOURCE_COMMIT
            or raw.get("transport_contract_snapshot_lock_sha256") != TRANSPORT_SNAPSHOT_LOCK_SHA256
            or raw.get("transport_compatible_with_is_snapshot") is not True
        ):
            _fail("TRANSPORT_IDENTITY_MISMATCH", "handoff transport identity differs")
        source_releases = _array(raw.get("source_releases"), field="source_releases")
        if len(source_releases) != 1:
            _fail("SOURCE_RELEASE_MISMATCH", "exactly one Evidence Release is required")
        source = _object(source_releases[0], field="source_releases[0]")
        artifacts = _array(source.get("load_bearing_artifacts"), field="load_bearing_artifacts")
        main = [
            item
            for item in artifacts
            if _object(item, field="artifact").get("item_type") != "schema"
        ]
        schemas = [
            item
            for item in artifacts
            if _object(item, field="artifact").get("item_type") == "schema"
        ]
        if len(main) != 1 or len(schemas) != 1:
            _fail("ARTIFACT_INVENTORY_MISMATCH", "Evidence handoff inventory differs")
        strategy = _object(raw.get("strategy_input_ref"), field="strategy_input_ref")
        strategy_ref = StrategyInputRef(
            schema_version=strategy["schema_version"],
            dataset_release_id=strategy["dataset_release_id"],
            knowledge_cutoff=_utc(strategy["knowledge_cutoff"], field="knowledge_cutoff"),
            release_manifest_schema_version=strategy["release_manifest_schema_version"],
            manifest_hash=_digest(strategy["manifest_hash"], field="manifest_hash"),
        )
        if (
            strategy_ref.dataset_release_id != raw.get("context_pack_release_id")
            or strategy_ref.knowledge_cutoff
            != _utc(raw.get("knowledge_cutoff"), field="knowledge_cutoff")
            or strategy_ref.manifest_hash
            != _digest(raw.get("manifest_hash"), field="manifest_hash")
        ):
            _fail("HANDOFF_IDENTITY_MISMATCH", "strategy_input_ref differs from handoff")
        return cls(
            handoff_sha256=expected_sha256,
            base_url=_text(raw.get("production_base_url"), field="production_base_url"),
            context_release_id=_text(
                raw.get("context_pack_release_id"), field="context_pack_release_id"
            ),
            context_pack_id=_text(raw.get("context_pack_id"), field="context_pack_id"),
            context_pack_hash=_digest(
                raw.get("context_pack_hash"), field="context_pack_hash"
            ).value,
            source_graph_hash=_digest(
                raw.get("source_graph_hash"), field="source_graph_hash"
            ).value,
            knowledge_cutoff=_utc(raw.get("knowledge_cutoff"), field="knowledge_cutoff"),
            manifest_hash=_digest(raw.get("manifest_hash"), field="manifest_hash").value,
            strategy_input_ref=strategy_ref,
            context_artifact=Stage3DArtifactExpectation.from_handoff(
                raw.get("context_pack_artifact")
            ),
            context_schema_artifact=Stage3DArtifactExpectation.from_handoff(
                raw.get("context_pack_schema_artifact")
            ),
            evidence_release_id=_text(source.get("release_id"), field="evidence release_id"),
            evidence_manifest_hash=_digest(
                source.get("manifest_hash"), field="evidence manifest_hash"
            ).value,
            evidence_artifact=Stage3DArtifactExpectation.from_handoff(main[0]),
            evidence_schema_artifact=Stage3DArtifactExpectation.from_handoff(schemas[0]),
        )


@dataclass(frozen=True, slots=True)
class Stage3DProviderNeutralInput(CanonicalModel):
    schema_version: str
    strategy_input_ref: StrategyInputRef
    context_pack_id: str
    context_pack_hash: HashDigest
    source_graph_hash: HashDigest
    evidence_release_ids: tuple[str, ...]
    evidence_bundle_hash: HashDigest
    company_mapping_ids: tuple[str, ...]
    known_event_ids: tuple[str, ...]
    known_counterexample_ids: tuple[str, ...]
    missing_item_ids: tuple[str, ...]
    conflicted_object_ids: tuple[str, ...]
    unrecoverable_field_paths: tuple[str, ...]
    document_version_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    candidate_event_ids: tuple[str, ...]
    provider_neutral: bool = True
    authority_eligible: bool = False


@dataclass(frozen=True, slots=True)
class Stage3DStrategySmoke(CanonicalModel):
    schema_version: str
    provider_input_hash: HashDigest
    outcome: GateOutcome
    reason_codes: tuple[str, ...]
    positive_investment_conclusion_required: bool = False
    authority_eligible: bool = False
    authorizes_positions: bool = False
    authorizes_orders: bool = False


@dataclass(frozen=True, slots=True)
class Stage3DValidationResult:
    strategy_input_ref: StrategyInputRef
    receipt: ArtifactConsumptionReceipt
    fetch_observation: ArtifactFetchObservation
    status_observation: ReleaseStatusObservation
    admission_observation: ReleaseAdmissionObservation
    provider_input: Stage3DProviderNeutralInput
    manifest: StrategyRunManifest
    smoke: Stage3DStrategySmoke
    response_sha256: Mapping[str, str]
    artifact_sha256: Mapping[str, str]
    closure_counts: Mapping[str, int]
    authority_eligible: bool = False
    run_release_status_confirmation_issued: bool = False
    persists_state: bool = False


def _manifest_item(manifest: Mapping[str, Any], artifact_id: str) -> dict[str, Any]:
    matches = [
        _object(raw, field="release item")
        for raw in _array(manifest.get("release_items"), field="release_items")
        if _object(raw, field="release item").get("artifact_id") == artifact_id
    ]
    if len(matches) != 1:
        _fail("ARTIFACT_INVENTORY_MISMATCH", f"Manifest item differs: {artifact_id}")
    return matches[0]


def _verify_artifact(
    catalog: KBTransportContractCatalog,
    manifest: Mapping[str, Any],
    artifact: VerifiedHTTPArtifact,
    expectation: Stage3DArtifactExpectation,
    *,
    canonical_schema_sha256: str,
) -> dict[str, Any]:
    item = _manifest_item(manifest, expectation.artifact_id)
    expected = {
        "artifact_id": expectation.artifact_id,
        "item_type": expectation.item_type,
        "media_type": expectation.content_type,
        "record_schema_id": expectation.schema_id,
        "record_schema_version": expectation.schema_version,
        "size_bytes": expectation.size_bytes,
    }
    if any(item.get(key) != value for key, value in expected.items()):
        _fail("ARTIFACT_MANIFEST_MISMATCH", f"Manifest identity differs: {artifact.artifact_id}")
    if (
        _digest(item.get("artifact_hash"), field="artifact_hash").value != expectation.sha256
        or _digest(item.get("logical_content_hash"), field="logical_content_hash").value
        != expectation.sha256
        or _digest(item.get("record_schema_hash"), field="record_schema_hash").value
        != canonical_schema_sha256
        or expectation.record_schema_hash != canonical_schema_sha256
        or artifact.sha256 != expectation.sha256
        or artifact.size_bytes != expectation.size_bytes
        or artifact.media_type != expectation.content_type
    ):
        _fail("ARTIFACT_HASH_MISMATCH", f"artifact identity differs: {artifact.artifact_id}")
    value = _object(
        load_strict_json_bytes(artifact.content, source=artifact.artifact_id),
        field=artifact.artifact_id,
    )
    if expectation.item_type == "schema":
        actual_schema_hash = sha256(provider_canonical_json_bytes(value)).hexdigest()
        if actual_schema_hash != canonical_schema_sha256:
            _fail("SCHEMA_IDENTITY_MISMATCH", "public schema semantics differ from pinned schema")
    else:
        try:
            catalog.validate_instance(expectation.schema_id, value)
        except ContractValidationError as exc:
            raise Stage3DValidationError(
                "SCHEMA_VALIDATION_FAILED",
                f"{artifact.artifact_id} violates the pinned data schema",
            ) from exc
    return value


def _release_identity(
    bundle: VerifiedHTTPReleaseBundle,
    *,
    release_id: str,
    manifest_hash: str,
    knowledge_cutoff: datetime,
) -> None:
    cutoff_text = knowledge_cutoff.isoformat(timespec="microseconds").replace("+00:00", "Z")
    head = _object(bundle.status.data.get("current_status_event"), field="status head")
    if (
        bundle.release.release_id != release_id
        or bundle.manifest.release_id != release_id
        or bundle.status.release_id != release_id
        or bundle.release.knowledge_cutoff != cutoff_text
        or bundle.manifest.knowledge_cutoff != cutoff_text
        or bundle.status.knowledge_cutoff != cutoff_text
        or head.get("status") != "published"
        or manifest_sha256(bundle.manifest.data) != manifest_hash
        or _digest(bundle.manifest.data.get("manifest_hash"), field="manifest_hash").value
        != manifest_hash
    ):
        _fail("RELEASE_IDENTITY_MISMATCH", f"Release closure differs: {release_id}")


def _validate_evidence_target_times(target: Mapping[str, Any], cutoff: datetime) -> None:
    available = _utc(target.get("available_at"), field="target.available_at")
    review = _object(target.get("review"), field="target.review")
    publication = _object(target.get("publication"), field="target.publication")
    reviewed = _utc(review.get("reviewed_at"), field="target.reviewed_at")
    published = _utc(target.get("knowledge_published_at"), field="target.knowledge_published_at")
    recorded = _utc(publication.get("recorded_at"), field="target.recorded_at")
    if (
        review.get("status") != "approved"
        or publication.get("status") != "published"
        or not available <= reviewed <= published <= recorded <= cutoff
    ):
        _fail("PIT_VIOLATION", "published evidence target time chain differs")


def _validate_documents_and_links(
    context_pack: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    *,
    source_cutoff: datetime,
) -> tuple[
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
    dict[str, dict[str, Any]],
]:
    documents = _indexed(
        evidence_bundle.get("document_versions"),
        key="document_version_id",
        field="document_versions",
    )
    spans = _indexed(
        evidence_bundle.get("evidence_spans"),
        key="evidence_span_id",
        field="evidence_spans",
    )
    facts = _indexed(evidence_bundle.get("facts"), key="fact_id", field="facts")
    events = _indexed(
        evidence_bundle.get("candidate_events"),
        key="candidate_event_id",
        field="candidate_events",
    )
    links = _indexed(
        evidence_bundle.get("evidence_links"),
        key="evidence_link_id",
        field="evidence_links",
    )
    sources = _indexed(
        context_pack.get("sources"),
        key="document_version_id",
        field="sources",
    )
    if set(sources) != set(documents):
        _fail("REFERENCE_CLOSURE_INVALID", "Context sources do not cover Evidence documents")
    spans_by_document: dict[str, set[str]] = {identifier: set() for identifier in documents}
    for document_id, document in documents.items():
        first_seen = _utc(document.get("first_seen_at"), field="document.first_seen_at")
        fetched = _utc(document.get("fetched_at"), field="document.fetched_at")
        available = _utc(document.get("available_at"), field="document.available_at")
        source_published = _optional_utc(
            document.get("source_published_at"), field="document.source_published_at"
        )
        if (
            document.get("authorization_status") != "approved"
            or any(value > source_cutoff for value in (first_seen, fetched, available))
            or (source_published is not None and source_published > available)
        ):
            _fail("PIT_VIOLATION", f"document time/authorization differs: {document_id}")
        source = sources[document_id]
        for key in ("provider", "title", "source_url", "available_at", "content_hash"):
            if source.get(key) != document.get(key):
                _fail("REFERENCE_CLOSURE_INVALID", f"source/document mismatch: {document_id}")
    for span_id, span in spans.items():
        document_id = _text(span.get("document_version_id"), field="span.document_version_id")
        if document_id not in documents:
            _fail("REFERENCE_CLOSURE_INVALID", f"span document missing: {span_id}")
        spans_by_document[document_id].add(span_id)
        available = _utc(span.get("available_at"), field="span.available_at")
        document = documents[document_id]
        document_dependencies = (
            _utc(document.get("first_seen_at"), field="document.first_seen_at"),
            _utc(document.get("fetched_at"), field="document.fetched_at"),
            _utc(document.get("available_at"), field="document.available_at"),
        )
        source_published = _optional_utc(
            document.get("source_published_at"), field="document.source_published_at"
        )
        review = _object(span.get("review"), field="span.review")
        reviewed = _utc(review.get("reviewed_at"), field="span.reviewed_at")
        if (
            review.get("status") != "approved"
            or any(timestamp > available for timestamp in document_dependencies)
            or (source_published is not None and source_published > available)
            or not available <= reviewed <= source_cutoff
        ):
            _fail("PIT_VIOLATION", f"span review time differs: {span_id}")
    for document_id, source in sources.items():
        if (
            set(_array(source.get("evidence_span_ids"), field="source.evidence_span_ids"))
            != spans_by_document[document_id]
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"source span closure differs: {document_id}")
    for target in (*facts.values(), *events.values()):
        _validate_evidence_target_times(target, source_cutoff)
    target_by_kind = {"fact": facts, "event": events}
    seen_target_links: dict[tuple[str, str], set[str]] = {}
    for link_id, link in links.items():
        kind = _text(link.get("target_kind"), field="link.target_kind")
        target_id = _text(link.get("target_id"), field="link.target_id")
        span_id = _text(link.get("evidence_span_id"), field="link.evidence_span_id")
        linked_target = target_by_kind.get(kind, {}).get(target_id)
        if (
            linked_target is None
            or span_id not in spans
            or link_id not in linked_target.get("evidence_link_ids", [])
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"evidence link target differs: {link_id}")
        seen_target_links.setdefault((kind, target_id), set()).add(link_id)
    for kind, values in target_by_kind.items():
        for target_id, target in values.items():
            if set(target.get("evidence_link_ids", [])) != seen_target_links.get(
                (kind, target_id), set()
            ):
                _fail("REFERENCE_CLOSURE_INVALID", f"target link closure differs: {target_id}")
    return documents, spans, facts, events, links


def _validate_graph_and_projection(
    context_pack: Mapping[str, Any],
    evidence_bundle: Mapping[str, Any],
    *,
    context_cutoff: datetime,
    source_cutoff: datetime,
    evidence_release_id: str,
    strategy_input_ref: StrategyInputRef,
) -> tuple[Stage3DProviderNeutralInput, dict[str, int]]:
    context_hash = _semantic_hash(context_pack, field="context_pack_hash")
    evidence_hash = _semantic_hash(evidence_bundle, field="bundle_hash")
    graph = _object(context_pack.get("industry_graph"), field="industry_graph")
    graph_hash = sha256(provider_canonical_json_bytes(graph)).hexdigest()
    if (
        _digest(context_pack.get("source_graph_hash"), field="source_graph_hash").value
        != graph_hash
    ):
        _fail("SEMANTIC_HASH_MISMATCH", "source_graph_hash differs")
    documents, spans, facts, events, links = _validate_documents_and_links(
        context_pack,
        evidence_bundle,
        source_cutoff=source_cutoff,
    )
    nodes = _indexed(graph.get("nodes"), key="industry_node_id", field="industry_graph.nodes")
    node_versions = _indexed(
        graph.get("nodes"),
        key="industry_node_version_id",
        field="industry_graph.nodes",
    )
    nodes_by_key = _indexed(graph.get("nodes"), key="node_key", field="industry_graph.nodes")
    edges = _indexed(
        graph.get("edges"),
        key="industry_edge_version_id",
        field="industry_graph.edges",
    )
    refs = _indexed(
        graph.get("evidence_refs"),
        key="industry_evidence_ref_id",
        field="industry_graph.evidence_refs",
    )
    refs_by_target: dict[tuple[str, str], set[str]] = {}
    used_links: set[str] = set()
    for ref_id, reference in refs.items():
        target_kind = _text(reference.get("target_kind"), field="reference.target_kind")
        target_id = _text(reference.get("target_version_id"), field="reference.target_version_id")
        graph_target = (
            node_versions.get(target_id) if target_kind == "node" else edges.get(target_id)
        )
        if graph_target is None:
            _fail("REFERENCE_CLOSURE_INVALID", f"graph reference target missing: {ref_id}")
        fact_id = reference.get("fact_id")
        event_id = reference.get("candidate_event_id")
        kind = "fact" if fact_id is not None else "event"
        evidence_id = _text(fact_id if fact_id is not None else event_id, field="reference target")
        evidence_target = facts.get(evidence_id) if kind == "fact" else events.get(evidence_id)
        link_id = _text(reference.get("evidence_link_id"), field="reference.evidence_link_id")
        span_id = _text(reference.get("evidence_span_id"), field="reference.evidence_span_id")
        link = links.get(link_id)
        if (
            evidence_target is None
            or link is None
            or link.get("target_kind") != kind
            or link.get("target_id") != evidence_id
            or link.get("evidence_span_id") != span_id
            or link.get("stance") != reference.get("stance")
            or span_id not in spans
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"graph evidence chain differs: {ref_id}")
        span = spans[span_id]
        evidence_recorded = _utc(
            _object(evidence_target.get("publication"), field="target publication").get(
                "recorded_at"
            ),
            field="target recorded_at",
        )
        span_reviewed = _utc(
            _object(span.get("review"), field="span review").get("reviewed_at"),
            field="span reviewed_at",
        )
        target_available = _utc(graph_target.get("available_at"), field="target.available_at")
        reference_available = _utc(reference.get("available_at"), field="reference.available_at")
        if not (
            span_reviewed
            <= evidence_recorded
            <= reference_available
            <= target_available
            <= context_cutoff
        ):
            _fail("PIT_VIOLATION", f"graph target time differs: {ref_id}")
        refs_by_target.setdefault((target_kind, target_id), set()).add(ref_id)
        used_links.add(link_id)
    for node in nodes.values():
        node_version = _text(node.get("industry_node_version_id"), field="node version")
        if set(node.get("evidence_ref_ids", [])) != refs_by_target.get(
            ("node", node_version), set()
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"node reference closure differs: {node_version}")
    for edge_id, edge in edges.items():
        if set(edge.get("evidence_ref_ids", [])) != refs_by_target.get(("edge", edge_id), set()):
            _fail("REFERENCE_CLOSURE_INVALID", f"edge reference closure differs: {edge_id}")
        from_node = nodes.get(
            _text(edge.get("from_industry_node_id"), field="edge.from_industry_node_id")
        )
        to_node = nodes.get(
            _text(edge.get("to_industry_node_id"), field="edge.to_industry_node_id")
        )
        if (
            from_node is None
            or to_node is None
            or edge.get("from_node_key") != from_node.get("node_key")
            or edge.get("to_node_key") != to_node.get("node_key")
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"edge endpoint closure differs: {edge_id}")
    known_events = _indexed(
        context_pack.get("known_events"),
        key="candidate_event_id",
        field="known_events",
    )
    for event_id, known in known_events.items():
        source = events.get(event_id)
        if source is None or any(
            known.get(field) != source.get(field)
            for field in (
                "event_type",
                "summary",
                "company_id",
                "attributes",
                "event_at",
                "effective_at",
                "available_at",
                "evidence_link_ids",
            )
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"known event differs: {event_id}")
        used_links.update(_array(known.get("evidence_link_ids"), field="known event links"))
    if set(known_events) != set(events) or used_links != set(links):
        _fail("REFERENCE_CLOSURE_INVALID", "Context Pack does not retain every Evidence target")
    mappings = _indexed(
        context_pack.get("company_mappings"), key="mapping_id", field="company_mappings"
    )
    for mapping_id, mapping in mappings.items():
        edge_id = _text(mapping.get("edge_version_id"), field="mapping.edge_version_id")
        mapping_edge = edges.get(edge_id)
        if (
            mapping.get("company_node_key") not in nodes_by_key
            or mapping.get("industry_node_key") not in nodes_by_key
            or mapping_edge is None
            or mapping.get("primary_fact_id") not in facts
            or not set(mapping.get("evidence_ref_ids", [])).issubset(refs)
        ):
            _fail("REFERENCE_CLOSURE_INVALID", f"company mapping differs: {mapping_id}")
    counterexamples = _array(context_pack.get("known_counterexamples"), field="counterexamples")
    counterexample_ids: list[str] = []
    for item in counterexamples:
        counterexample = _object(item, field="counterexample")
        ref_id = _text(counterexample.get("evidence_ref_id"), field="counterexample ref")
        edge_id = _text(counterexample.get("edge_version_id"), field="counterexample edge")
        if ref_id not in refs or edge_id not in edges:
            _fail("REFERENCE_CLOSURE_INVALID", "counterexample target differs")
        counterexample_ids.append(f"{edge_id}:{ref_id}")
    missing = _indexed(context_pack.get("missing_items"), key="item_id", field="missing_items")
    conflicted = tuple(
        sorted(
            [
                _text(item.get("industry_node_version_id"), field="node version")
                for item in nodes.values()
                if item.get("conflict_status") != "none"
            ]
            + [edge_id for edge_id, item in edges.items() if item.get("conflict_status") != "none"]
        )
    )
    unrecoverable = tuple(
        sorted(
            f"node:{node_id}:{field}"
            for node_id, item in nodes.items()
            for field in item.get("unrecoverable_fields", [])
        )
        + sorted(
            f"edge:{edge_id}:{field}"
            for edge_id, item in edges.items()
            for field in item.get("unrecoverable_fields", [])
        )
    )
    provider_input = Stage3DProviderNeutralInput(
        schema_version=STAGE3D_PROVIDER_INPUT_SCHEMA_VERSION,
        strategy_input_ref=strategy_input_ref,
        context_pack_id=_text(context_pack.get("context_pack_id"), field="context_pack_id"),
        context_pack_hash=HashDigest(algorithm="sha256", value=context_hash),
        source_graph_hash=HashDigest(algorithm="sha256", value=graph_hash),
        evidence_release_ids=(evidence_release_id,),
        evidence_bundle_hash=HashDigest(algorithm="sha256", value=evidence_hash),
        company_mapping_ids=tuple(sorted(mappings)),
        known_event_ids=tuple(sorted(known_events)),
        known_counterexample_ids=tuple(sorted(counterexample_ids)),
        missing_item_ids=tuple(sorted(missing)),
        conflicted_object_ids=conflicted,
        unrecoverable_field_paths=unrecoverable,
        document_version_ids=tuple(sorted(documents)),
        fact_ids=tuple(sorted(facts)),
        candidate_event_ids=tuple(sorted(events)),
    )
    counts = {
        "documents": len(documents),
        "evidence_spans": len(spans),
        "facts": len(facts),
        "candidate_events": len(events),
        "evidence_links": len(links),
        "industry_nodes": len(nodes),
        "industry_edges": len(edges),
        "industry_evidence_refs": len(refs),
        "company_mappings": len(mappings),
        "known_counterexamples": len(counterexamples),
        "missing_items": len(missing),
    }
    return provider_input, counts


def validate_stage3d_http_context_pack(
    *,
    client: KBReadOnlyHTTPClient,
    catalog: KBTransportContractCatalog,
    expectation: Stage3DExpectation,
    observed_at: datetime,
    code_commit: str,
    config_hash: HashDigest,
    runtime_environment_lock_hash: HashDigest,
) -> Stage3DValidationResult:
    """Validate the exact public releases and create a zero-authority IS smoke."""

    observed = normalize_utc(observed_at, field_name="observed_at")
    context_bundle = client.get_release_bundle(expectation.context_release_id)
    evidence_bundle_http = client.get_release_bundle(expectation.evidence_release_id)
    _release_identity(
        context_bundle,
        release_id=expectation.context_release_id,
        manifest_hash=expectation.manifest_hash,
        knowledge_cutoff=expectation.knowledge_cutoff,
    )
    _release_identity(
        evidence_bundle_http,
        release_id=expectation.evidence_release_id,
        manifest_hash=expectation.evidence_manifest_hash,
        knowledge_cutoff=expectation.knowledge_cutoff,
    )
    expected_context_ids = {
        expectation.context_artifact.artifact_id,
        expectation.context_schema_artifact.artifact_id,
    }
    expected_evidence_ids = {
        expectation.evidence_artifact.artifact_id,
        expectation.evidence_schema_artifact.artifact_id,
    }
    context_manifest_ids = {
        _text(_object(item, field="context item").get("artifact_id"), field="artifact_id")
        for item in _array(context_bundle.manifest.data.get("release_items"), field="release_items")
    }
    evidence_manifest_ids = {
        _text(_object(item, field="evidence item").get("artifact_id"), field="artifact_id")
        for item in _array(
            evidence_bundle_http.manifest.data.get("release_items"), field="release_items"
        )
    }
    if context_manifest_ids != expected_context_ids or not expected_evidence_ids.issubset(
        evidence_manifest_ids
    ):
        _fail("ARTIFACT_INVENTORY_MISMATCH", "Release artifact inventory differs")
    downloaded: dict[str, VerifiedHTTPArtifact] = {}
    for release_id, item in (
        (expectation.context_release_id, expectation.context_artifact),
        (expectation.context_release_id, expectation.context_schema_artifact),
        (expectation.evidence_release_id, expectation.evidence_artifact),
        (expectation.evidence_release_id, expectation.evidence_schema_artifact),
    ):
        downloaded[item.artifact_id] = client.download_artifact(
            release_id,
            item.artifact_id,
            expected_sha256=item.sha256,
            expected_size_bytes=item.size_bytes,
        )
    context_pack = _verify_artifact(
        catalog,
        context_bundle.manifest.data,
        downloaded[expectation.context_artifact.artifact_id],
        expectation.context_artifact,
        canonical_schema_sha256=CONTEXT_PACK_SCHEMA_CANONICAL_SHA256,
    )
    _verify_artifact(
        catalog,
        context_bundle.manifest.data,
        downloaded[expectation.context_schema_artifact.artifact_id],
        expectation.context_schema_artifact,
        canonical_schema_sha256=CONTEXT_PACK_SCHEMA_CANONICAL_SHA256,
    )
    evidence_bundle = _verify_artifact(
        catalog,
        evidence_bundle_http.manifest.data,
        downloaded[expectation.evidence_artifact.artifact_id],
        expectation.evidence_artifact,
        canonical_schema_sha256=EVIDENCE_BUNDLE_SCHEMA_CANONICAL_SHA256,
    )
    _verify_artifact(
        catalog,
        evidence_bundle_http.manifest.data,
        downloaded[expectation.evidence_schema_artifact.artifact_id],
        expectation.evidence_schema_artifact,
        canonical_schema_sha256=EVIDENCE_BUNDLE_SCHEMA_CANONICAL_SHA256,
    )
    query = client.get_context_pack(
        expectation.context_pack_id,
        release_id=expectation.context_release_id,
    )
    if query.data != context_pack:
        _fail("CONTEXT_QUERY_MISMATCH", "Context Pack query and artifact JSON differ")
    if (
        context_pack.get("schema_version") != "1.0.0"
        or context_pack.get("context_pack_id") != expectation.context_pack_id
        or _digest(context_pack.get("context_pack_hash"), field="context_pack_hash").value
        != expectation.context_pack_hash
        or _digest(context_pack.get("source_graph_hash"), field="source_graph_hash").value
        != expectation.source_graph_hash
        or _utc(context_pack.get("knowledge_cutoff"), field="context knowledge_cutoff")
        != expectation.knowledge_cutoff
        or _utc(evidence_bundle.get("knowledge_cutoff"), field="evidence knowledge_cutoff")
        != expectation.knowledge_cutoff
    ):
        _fail("CONTEXT_IDENTITY_MISMATCH", "Context Pack handoff identity differs")
    build = _object(
        context_bundle.manifest.data.get("context_pack_build"), field="context_pack_build"
    )
    for field in ("context_pack_id", "pack_key", "version", "supersedes_context_pack_id"):
        if build.get(field) != context_pack.get(field):
            _fail("SOURCE_RELEASE_MISMATCH", f"Manifest Context Pack build differs: {field}")
    source_releases = _array(context_pack.get("source_releases"), field="source_releases")
    if len(source_releases) != 1 or _object(
        build.get("source_release"), field="context_pack_build.source_release"
    ) != _object(source_releases[0], field="source_releases[0]"):
        _fail("SOURCE_RELEASE_MISMATCH", "Context Pack source Release differs")
    source = _object(source_releases[0], field="source_releases[0]")
    if (
        source.get("release_id") != expectation.evidence_release_id
        or _utc(source.get("knowledge_cutoff"), field="source knowledge_cutoff")
        != expectation.knowledge_cutoff
        or _digest(source.get("manifest_hash"), field="source manifest_hash").value
        != expectation.evidence_manifest_hash
    ):
        _fail("SOURCE_RELEASE_MISMATCH", "Context Pack exact source Release identity differs")
    projected, closure_counts = _validate_graph_and_projection(
        context_pack,
        evidence_bundle,
        context_cutoff=expectation.knowledge_cutoff,
        source_cutoff=expectation.knowledge_cutoff,
        evidence_release_id=expectation.evidence_release_id,
        strategy_input_ref=expectation.strategy_input_ref,
    )
    closure_counts["evidence_release_non_load_bearing_artifacts"] = len(
        evidence_manifest_ids - expected_evidence_ids
    )
    provider_input = projected
    receipt = ArtifactConsumptionReceipt.create(
        schema_version=ARTIFACT_CONSUMPTION_RECEIPT_SCHEMA_VERSION,
        consumer_contract_version=CONSUMER_CONTRACT_VERSION,
        strategy_input_ref=expectation.strategy_input_ref,
        artifacts=(
            ArtifactReceiptItem(
                artifact_id=expectation.context_artifact.artifact_id,
                item_type=expectation.context_artifact.item_type,
                artifact_hash=HashDigest(
                    algorithm="sha256", value=expectation.context_artifact.sha256
                ),
                size_bytes=expectation.context_artifact.size_bytes,
                record_count=1,
            ),
            ArtifactReceiptItem(
                artifact_id=expectation.context_schema_artifact.artifact_id,
                item_type=expectation.context_schema_artifact.item_type,
                artifact_hash=HashDigest(
                    algorithm="sha256", value=expectation.context_schema_artifact.sha256
                ),
                size_bytes=expectation.context_schema_artifact.size_bytes,
                record_count=None,
            ),
            ArtifactReceiptItem(
                artifact_id=expectation.evidence_artifact.artifact_id,
                item_type=expectation.evidence_artifact.item_type,
                artifact_hash=HashDigest(
                    algorithm="sha256", value=expectation.evidence_artifact.sha256
                ),
                size_bytes=expectation.evidence_artifact.size_bytes,
                record_count=1,
            ),
            ArtifactReceiptItem(
                artifact_id=expectation.evidence_schema_artifact.artifact_id,
                item_type=expectation.evidence_schema_artifact.item_type,
                artifact_hash=HashDigest(
                    algorithm="sha256", value=expectation.evidence_schema_artifact.sha256
                ),
                size_bytes=expectation.evidence_schema_artifact.size_bytes,
                record_count=None,
            ),
        ),
    )
    identity_material = ":".join(
        (
            observed.isoformat(),
            context_bundle.release.response_sha256,
            context_bundle.status.response_sha256,
            query.response_sha256,
        )
    )
    identity = sha256(identity_material.encode("ascii")).hexdigest()
    fetch_observation = ArtifactFetchObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=f"fetch_stage3d_{identity[:24]}",
        release_id=expectation.context_release_id,
        strategy_input_ref=expectation.strategy_input_ref,
        observed_at=observed,
        transport=DeliveryTransport.READ_ONLY_HTTP_API,
        source_endpoint=expectation.base_url,
        schema_validation_result=SchemaValidationResult.PASSED,
        receipt_hash=receipt.receipt_hash,
        artifact_ids=tuple(sorted(expected_context_ids)),
    )
    status_head = _object(
        context_bundle.status.data.get("current_status_event"), field="status head"
    )
    previous = status_head.get("previous_event_hash")
    status_observation = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=f"status_stage3d_{identity[:24]}",
        release_id=expectation.context_release_id,
        strategy_input_ref=expectation.strategy_input_ref,
        observed_at=observed,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.PUBLISHED,
        status_event_id=_text(status_head.get("event_id"), field="status event_id"),
        status_event_hash=_digest(status_head.get("event_hash"), field="status event_hash"),
        previous_status_event_hash=(
            _digest(previous, field="previous status hash") if previous is not None else None
        ),
        status_sequence=_integer(status_head.get("sequence"), field="status sequence"),
        status_recorded_at=_utc(status_head.get("recorded_at"), field="status recorded_at"),
    )
    admission_observation = ReleaseAdmissionObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=f"admission_stage3d_{identity[:24]}",
        release_id=expectation.context_release_id,
        strategy_input_ref=expectation.strategy_input_ref,
        observed_at=observed,
        status_observation_id=status_observation.observation_id,
        admission_status=ReleaseAdmissionStatus.UNCONFIRMED,
        failure_reasons=("run_release_status_confirmation_not_issued",),
    )
    reason_codes = ["real_strategy_rules_not_authorized_for_stage3d_smoke"]
    if provider_input.missing_item_ids:
        reason_codes.append("declared_missing_items_retained")
    if provider_input.conflicted_object_ids:
        reason_codes.append("provider_conflicts_retained")
    if provider_input.known_counterexample_ids:
        reason_codes.append("counterexamples_retained")
    if provider_input.unrecoverable_field_paths:
        reason_codes.append("unrecoverable_fields_retained")
    smoke = Stage3DStrategySmoke(
        schema_version=STAGE3D_SMOKE_SCHEMA_VERSION,
        provider_input_hash=HashDigest(algorithm="sha256", value=provider_input.canonical_sha256()),
        outcome=GateOutcome.ABSTAIN,
        reason_codes=tuple(reason_codes),
    )
    rule_profile_hash = HashDigest(
        algorithm="sha256", value=sha256(canonical_json_bytes(STAGE3D_RULE_PROFILE)).hexdigest()
    )
    manifest = StrategyRunManifest(
        strategy_run_manifest_schema_version=STRATEGY_RUN_MANIFEST_SCHEMA_VERSION,
        run_id=f"run_stage3d_{identity[:24]}",
        created_at=observed,
        strategy_id="industrial_bottleneck_event",
        strategy_version=STAGE3D_STRATEGY_VERSION,
        code_commit=code_commit,
        rule_bundle_id="stage3d_context_pack_mapping_smoke",
        rule_bundle_version=STAGE3D_SMOKE_SCHEMA_VERSION,
        rule_bundle_hash=rule_profile_hash,
        rule_status=RuleStatus.REQUIREMENTS_CONFIRMED,
        rule_approval_id=None,
        rule_approval_record_hash=None,
        rule_approval_scope=None,
        config_hash=config_hash,
        strategy_input_ref=expectation.strategy_input_ref,
        input_envelope_hash=smoke.provider_input_hash,
        strategy_case_envelope_hash=None,
        strategy_case_input_hash=None,
        synthetic_fixture_id=None,
        synthetic_fixture_version=None,
        synthetic_fixture_payload_hash=None,
        input_path="published_context_pack_http",
        synthetic=False,
        validation_only=True,
        not_a_published_release=False,
        not_strategy_evidence=False,
        authorizes_positions=False,
        authorizes_orders=False,
        artifact_consumption_receipt_hash=receipt.receipt_hash,
        artifact_fetch_observation_id=fetch_observation.observation_id,
        release_status_observation_id=status_observation.observation_id,
        release_admission_observation_id=admission_observation.observation_id,
        random_seed=0,
        run_mode=RunMode.RESEARCH,
        runtime_environment_lock_hash=runtime_environment_lock_hash,
    )
    response_sha256 = {
        "context_release": context_bundle.release.response_sha256,
        "context_manifest": context_bundle.manifest.response_sha256,
        "context_status": context_bundle.status.response_sha256,
        "context_query": query.response_sha256,
        "evidence_release": evidence_bundle_http.release.response_sha256,
        "evidence_manifest": evidence_bundle_http.manifest.response_sha256,
        "evidence_status": evidence_bundle_http.status.response_sha256,
    }
    return Stage3DValidationResult(
        strategy_input_ref=expectation.strategy_input_ref,
        receipt=receipt,
        fetch_observation=fetch_observation,
        status_observation=status_observation,
        admission_observation=admission_observation,
        provider_input=provider_input,
        manifest=manifest,
        smoke=smoke,
        response_sha256=response_sha256,
        artifact_sha256={key: value.sha256 for key, value in sorted(downloaded.items())},
        closure_counts=closure_counts,
    )
