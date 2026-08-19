"""KB-provider adapter for Stage 6B published-status evidence.

This outer adapter reverifies the pinned provider response bytes and projects
them into the provider-neutral Stage 6B contracts.  Network access remains in
the read-only HTTP client and strategy code never imports this module.
"""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Any

from invest_system.canonical import canonical_json_bytes, format_utc, normalize_utc
from invest_system.consumption import (
    CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
    ProviderReleaseStatus,
    ReleaseStatusObservation,
    SchemaValidationResult,
)
from invest_system.models import HashDigest, StrategyInputRef
from invest_system.strategies.industrial_event.stage6b_admission import (
    _STATUS_EVIDENCE_ISSUER,
    STAGE6B_STATUS_PATH_TEMPLATE,
    Stage6BAdmissionError,
    Stage6BStatusEvidence,
    Stage6BStatusEvidenceProjection,
    Stage6BStatusResponsePayload,
)

from .http_client import VerifiedHTTPDocument
from .provider_canonical import canonical_json_bytes as provider_canonical_json_bytes


def _digest(value: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=value)


def _parse_canonical_utc(value: Any, *, field_name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not UTC")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as exc:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not UTC") from exc
    if format_utc(parsed) != value:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", f"{field_name} is not canonical UTC")
    return parsed


def _hash_value(value: Any, *, field_name: str) -> HashDigest:
    if not isinstance(value, dict) or set(value) != {"algorithm", "value"}:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", f"{field_name} is not a SHA-256 object"
        )
    try:
        return HashDigest(algorithm=value["algorithm"], value=value["value"])
    except (TypeError, ValueError) as exc:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", f"{field_name} is not a SHA-256 object"
        ) from exc


def project_stage6b_status_evidence(
    document: VerifiedHTTPDocument,
    *,
    strategy_input_ref: StrategyInputRef,
    checked_at: datetime,
    status_observation_id: str,
) -> Stage6BStatusEvidenceProjection:
    """Reverify one KB response and project an opaque Stage 6B evidence receipt."""

    if not isinstance(document, VerifiedHTTPDocument):
        raise TypeError("document must be a VerifiedHTTPDocument")
    if not isinstance(strategy_input_ref, StrategyInputRef):
        raise TypeError("strategy_input_ref must be a StrategyInputRef")
    release_id = strategy_input_ref.dataset_release_id
    if (
        document.operation != "get_dataset_release_status_history"
        or document.release_id != release_id
        or document.request_path != STAGE6B_STATUS_PATH_TEMPLATE.format(release_id=release_id)
        or document.authority_eligible
    ):
        raise Stage6BAdmissionError(
            "STATUS_DOCUMENT_IDENTITY_MISMATCH",
            "verified HTTP document is not the exact zero-authority status response",
        )
    try:
        raw = json.loads(document.response_bytes)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", "status response is not UTF-8 JSON"
        ) from exc
    if not isinstance(raw, dict) or set(raw) != {"meta", "data"}:
        raise Stage6BAdmissionError("STATUS_RESPONSE_INVALID", "status response envelope differs")
    meta = raw["meta"]
    data = raw["data"]
    if not isinstance(meta, dict) or not isinstance(data, dict) or data != document.data:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_INVALID", "status response data differs from verified document"
        )
    response_hash = sha256(document.response_bytes).hexdigest()
    if response_hash != document.response_sha256:
        raise Stage6BAdmissionError(
            "STATUS_RESPONSE_HASH_MISMATCH", "status response bytes changed"
        )
    if (
        meta.get("release_id") != release_id
        or meta.get("request_id") != document.request_id
        or data.get("release_id") != release_id
        or meta.get("knowledge_cutoff") != format_utc(strategy_input_ref.knowledge_cutoff)
        or document.knowledge_cutoff != meta.get("knowledge_cutoff")
    ):
        raise Stage6BAdmissionError(
            "STATUS_DOCUMENT_IDENTITY_MISMATCH", "status response five-field identity differs"
        )
    events = data.get("events")
    head = data.get("current_status_event")
    if not isinstance(events, list) or not events or not isinstance(head, dict):
        raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status history is incomplete")
    previous_hash: str | None = None
    for sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status event is not an object")
        if event.get("release_id") != release_id or event.get("sequence") != sequence:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status sequence differs")
        previous = event.get("previous_event_hash")
        linked = (
            None
            if previous is None
            else _hash_value(previous, field_name="previous_event_hash").value
        )
        if linked != previous_hash:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status link differs")
        event_hash = _hash_value(event.get("event_hash"), field_name="event_hash")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if sha256(provider_canonical_json_bytes(unsigned)).hexdigest() != event_hash.value:
            raise Stage6BAdmissionError("STATUS_CHAIN_INVALID", "status self-hash differs")
        previous_hash = event_hash.value
    if head != events[-1] or head.get("status") != ProviderReleaseStatus.PUBLISHED.value:
        raise Stage6BAdmissionError("STATUS_NOT_PUBLISHED", "current status head must be published")
    checked = normalize_utc(checked_at, field_name="checked_at")
    provider_snapshot_at = _parse_canonical_utc(
        meta.get("generated_at"), field_name="meta.generated_at"
    )
    status_recorded_at = _parse_canonical_utc(
        head.get("recorded_at"), field_name="current_status_event.recorded_at"
    )
    status_event_hash = _hash_value(head.get("event_hash"), field_name="event_hash")
    evidence_identity = sha256(
        canonical_json_bytes(
            {
                "release_id": release_id,
                "status_observation_id": status_observation_id,
                "response_bytes_hash": response_hash,
                "checked_at": checked,
            }
        )
    ).hexdigest()
    evidence = Stage6BStatusEvidence(
        _issuer=_STATUS_EVIDENCE_ISSUER,
        evidence_id=f"status_evidence_{evidence_identity[:24]}",
        strategy_input_ref=strategy_input_ref,
        status_observation_id=status_observation_id,
        response_bytes_hash=_digest(response_hash),
        status_event_id=head["event_id"],
        status_event_hash=status_event_hash,
        status_sequence=head["sequence"],
        status_recorded_at=status_recorded_at,
        provider_snapshot_at=provider_snapshot_at,
        checked_at=checked,
    )
    previous = head.get("previous_event_hash")
    observation = ReleaseStatusObservation(
        schema_version=CONSUMPTION_OBSERVATION_SCHEMA_VERSION,
        observation_id=status_observation_id,
        release_id=release_id,
        strategy_input_ref=strategy_input_ref,
        observed_at=checked,
        schema_validation_result=SchemaValidationResult.PASSED,
        status=ProviderReleaseStatus.PUBLISHED,
        status_event_id=head["event_id"],
        status_event_hash=status_event_hash,
        previous_status_event_hash=(
            None if previous is None else _hash_value(previous, field_name="previous_event_hash")
        ),
        status_sequence=head["sequence"],
        status_recorded_at=status_recorded_at,
    )
    return Stage6BStatusEvidenceProjection(
        evidence=evidence,
        payload=Stage6BStatusResponsePayload(
            release_id=release_id,
            content=document.response_bytes,
            response_bytes_hash=_digest(response_hash),
        ),
        observation=observation,
    )
