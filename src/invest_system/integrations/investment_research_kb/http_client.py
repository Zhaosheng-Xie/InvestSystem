"""Minimal read-only HTTP client for exact KB Release transport operations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from ...consumption import DeliveryTransport
from .contracts import ContractValidationError, load_strict_json_bytes
from .provider_canonical import canonical_json_bytes, manifest_sha256
from .transport import require_supported_kb_transport
from .transport_contracts import (
    HTTP_ENVELOPE_ID,
    HTTP_ERROR_ID,
    RELEASE_STATUS_HISTORY_ID,
    KBTransportContractCatalog,
)

_DATASET_RELEASE_ID = "urn:investment-research-kb:contract:dataset-release:v1"
_RELEASE_MANIFEST_ID = "urn:investment-research-kb:contract:release-manifest:v1"
_RELEASE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,127}$")
_ARTIFACT_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DEFAULT_MAX_ARTIFACT_BYTES = 512 * 1024**2


class KBHTTPClientError(RuntimeError):
    """Base class for sanitized transport failures."""


class KBHTTPConfigurationError(KBHTTPClientError):
    pass


class KBHTTPTransportError(KBHTTPClientError):
    pass


class KBHTTPContractError(KBHTTPClientError):
    pass


class KBHTTPResponseError(KBHTTPClientError):
    def __init__(self, *, status_code: int, code: str, request_id: str | None) -> None:
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        super().__init__(f"KB HTTP {status_code}: {code} (request_id={request_id!r})")


@dataclass(frozen=True, slots=True)
class KBHTTPRequest:
    method: str
    url: str
    headers: MappingProxyType[str, str]
    timeout_seconds: float
    max_response_bytes: int


@dataclass(frozen=True, slots=True)
class KBHTTPRawResponse:
    status_code: int
    headers: MappingProxyType[str, str]
    body: bytes


class KBHTTPExecutor(Protocol):
    def execute(self, request: KBHTTPRequest) -> KBHTTPRawResponse: ...


class UrllibKBHTTPExecutor:
    """Small standard-library executor with bounded reads and no retries."""

    def execute(self, request: KBHTTPRequest) -> KBHTTPRawResponse:
        wire_request = Request(
            request.url,
            method=request.method,
            headers=dict(request.headers),
        )
        try:
            with urlopen(wire_request, timeout=request.timeout_seconds) as response:  # noqa: S310
                body = response.read(request.max_response_bytes + 1)
                status = response.status
                headers = {key.lower(): value for key, value in response.headers.items()}
        except HTTPError as exc:
            body = exc.read(request.max_response_bytes + 1)
            status = exc.code
            headers = {key.lower(): value for key, value in exc.headers.items()}
        except (URLError, TimeoutError, OSError) as exc:
            raise KBHTTPTransportError(
                "KB HTTP request failed before a response was verified"
            ) from exc
        if len(body) > request.max_response_bytes:
            raise KBHTTPTransportError("KB HTTP response exceeded the configured byte limit")
        return KBHTTPRawResponse(
            status_code=status,
            headers=MappingProxyType(headers),
            body=body,
        )


@dataclass(frozen=True, slots=True)
class VerifiedHTTPDocument:
    operation: str
    request_path: str
    release_id: str
    request_id: str
    knowledge_cutoff: str | None
    response_sha256: str
    response_bytes: bytes
    data: dict[str, Any]
    authority_eligible: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedHTTPArtifact:
    request_path: str
    release_id: str
    artifact_id: str
    media_type: str
    size_bytes: int
    sha256: str
    content: bytes
    authority_eligible: bool = False


@dataclass(frozen=True, slots=True)
class VerifiedHTTPReleaseBundle:
    release: VerifiedHTTPDocument
    manifest: VerifiedHTTPDocument
    status: VerifiedHTTPDocument


def _exact_release_id(value: str) -> str:
    if not isinstance(value, str) or _RELEASE_ID_RE.fullmatch(value) is None or value == "latest":
        raise ValueError("release_id must be an exact provider Release ID, not 'latest'")
    return value


def _artifact_id(value: str) -> str:
    if not isinstance(value, str) or _ARTIFACT_ID_RE.fullmatch(value) is None:
        raise ValueError("artifact_id violates the pinned provider identifier contract")
    return value


def _lower_headers(headers: MappingProxyType[str, str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in headers.items():
        lowered = key.lower()
        if lowered in result:
            raise KBHTTPContractError("duplicate HTTP header after case folding")
        result[lowered] = value
    return result


def _hash_value(value: object, *, field: str) -> str:
    if not isinstance(value, dict) or set(value) != {"algorithm", "value"}:
        raise KBHTTPContractError(f"{field} is not a SHA-256 object")
    digest = value.get("value")
    if (
        value.get("algorithm") != "sha256"
        or not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
    ):
        raise KBHTTPContractError(f"{field} is not a SHA-256 object")
    return digest


def _verify_status_chain(data: dict[str, Any], release_id: str) -> None:
    events = data.get("events")
    if not isinstance(events, list) or not events:
        raise KBHTTPContractError("status history is empty")
    previous_hash: str | None = None
    for expected_sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            raise KBHTTPContractError("status history contains a non-object event")
        if event.get("release_id") != release_id or event.get("sequence") != expected_sequence:
            raise KBHTTPContractError("status event identity or sequence differs")
        previous = event.get("previous_event_hash")
        linked = None if previous is None else _hash_value(previous, field="previous_event_hash")
        if linked != previous_hash:
            raise KBHTTPContractError("status previous-event hash differs")
        declared = _hash_value(event.get("event_hash"), field="event_hash")
        unsigned = {key: value for key, value in event.items() if key != "event_hash"}
        if sha256(canonical_json_bytes(unsigned)).hexdigest() != declared:
            raise KBHTTPContractError("status event self-hash differs")
        previous_hash = declared
    if data.get("current_status_event") != events[-1]:
        raise KBHTTPContractError("current status event is not the complete-chain head")


class KBReadOnlyHTTPClient:
    """Read-only exact-Release client enabled only by a verified contract catalog."""

    __slots__ = (
        "_base_url",
        "_catalog",
        "_executor",
        "_max_artifact_bytes",
        "_max_json_bytes",
        "_timeout_seconds",
        "_token",
    )

    def __init__(
        self,
        *,
        base_url: str,
        bearer_token: str,
        catalog: KBTransportContractCatalog,
        executor: KBHTTPExecutor | None = None,
        timeout_seconds: float = 10.0,
        max_json_bytes: int = 8 * 1024**2,
        max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
        allow_loopback_http: bool = False,
    ) -> None:
        require_supported_kb_transport(
            DeliveryTransport.READ_ONLY_HTTP_API,
            contract_catalog=catalog,
        )
        parsed = urlsplit(base_url)
        loopback = parsed.hostname in {"127.0.0.1", "::1", "localhost"}
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or (
                parsed.scheme != "https"
                and not (allow_loopback_http and loopback and parsed.scheme == "http")
            )
        ):
            raise KBHTTPConfigurationError(
                "base_url must be an HTTPS origin; explicit HTTP is limited to loopback"
            )
        if not isinstance(bearer_token, str) or not bearer_token.strip():
            raise KBHTTPConfigurationError("bearer_token must be non-empty")
        if not isinstance(catalog, KBTransportContractCatalog):
            raise TypeError("catalog must be a verified KBTransportContractCatalog")
        if (
            not isinstance(timeout_seconds, (int, float))
            or isinstance(timeout_seconds, bool)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be positive")
        for field, value in (
            ("max_json_bytes", max_json_bytes),
            ("max_artifact_bytes", max_artifact_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{field} must be a positive integer")
        self._base_url = base_url.rstrip("/")
        self._token = bearer_token
        self._catalog = catalog
        self._executor = executor or UrllibKBHTTPExecutor()
        self._timeout_seconds = float(timeout_seconds)
        self._max_json_bytes = max_json_bytes
        self._max_artifact_bytes = max_artifact_bytes

    def __repr__(self) -> str:
        return f"{type(self).__name__}(base_url={self._base_url!r}, bearer_token=<redacted>)"

    def _request(self, path: str, *, max_bytes: int) -> KBHTTPRawResponse:
        request = KBHTTPRequest(
            method="GET",
            url=f"{self._base_url}{path}",
            headers=MappingProxyType(
                {
                    "Accept": "application/json, application/octet-stream",
                    "Authorization": f"Bearer {self._token}",
                }
            ),
            timeout_seconds=self._timeout_seconds,
            max_response_bytes=max_bytes,
        )
        response = self._executor.execute(request)
        if not isinstance(response, KBHTTPRawResponse):
            raise KBHTTPTransportError("KB HTTP executor returned an invalid response type")
        if (
            isinstance(response.status_code, bool)
            or not isinstance(response.status_code, int)
            or response.status_code < 100
            or response.status_code > 599
            or not isinstance(response.body, bytes)
        ):
            raise KBHTTPTransportError("KB HTTP executor returned invalid response fields")
        if len(response.body) > max_bytes:
            raise KBHTTPTransportError("KB HTTP response exceeded the configured byte limit")
        return response

    def _error(self, response: KBHTTPRawResponse) -> KBHTTPResponseError:
        try:
            headers = _lower_headers(response.headers)
            content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                raise KBHTTPContractError("KB error response Content-Type is not application/json")
            payload = load_strict_json_bytes(response.body, source="KB HTTP error")
            self._catalog.validate_instance(HTTP_ERROR_ID, payload)
            error = payload["error"]
            return KBHTTPResponseError(
                status_code=response.status_code,
                code=error["code"],
                request_id=error["request_id"],
            )
        except (ContractValidationError, ValueError, KeyError, TypeError) as exc:
            raise KBHTTPContractError(
                f"KB HTTP {response.status_code} error body violates the pinned contract"
            ) from exc

    def _json_document(
        self,
        *,
        path: str,
        release_id: str,
        operation: str,
        data_contract_id: str,
    ) -> VerifiedHTTPDocument:
        response = self._request(path, max_bytes=self._max_json_bytes)
        if response.status_code != 200:
            raise self._error(response)
        headers = _lower_headers(response.headers)
        content_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise KBHTTPContractError("KB success response Content-Type is not application/json")
        try:
            payload = load_strict_json_bytes(response.body, source=operation)
            self._catalog.validate_instance(HTTP_ENVELOPE_ID, payload)
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
                raise KBHTTPContractError("KB success data must be an object")
            self._catalog.validate_instance(data_contract_id, payload["data"])
        except (ContractValidationError, ValueError) as exc:
            if isinstance(exc, KBHTTPContractError):
                raise
            raise KBHTTPContractError(
                f"KB {operation} response violates the pinned contract"
            ) from exc
        meta = payload["meta"]
        if meta.get("release_id") != release_id or payload["data"].get("release_id") != release_id:
            raise KBHTTPContractError("KB response exact Release identity differs")
        data_cutoff = payload["data"].get("knowledge_cutoff")
        if data_cutoff is not None and meta.get("knowledge_cutoff") != data_cutoff:
            raise KBHTTPContractError("KB response knowledge cutoff differs")
        return VerifiedHTTPDocument(
            operation=operation,
            request_path=path,
            release_id=release_id,
            request_id=meta["request_id"],
            knowledge_cutoff=meta["knowledge_cutoff"],
            response_sha256=sha256(response.body).hexdigest(),
            response_bytes=response.body,
            data=payload["data"],
        )

    def get_release(self, release_id: str) -> VerifiedHTTPDocument:
        exact = _exact_release_id(release_id)
        path = f"/api/v1/dataset-releases/{quote(exact, safe='')}"
        return self._json_document(
            path=path,
            release_id=exact,
            operation="get_dataset_release",
            data_contract_id=_DATASET_RELEASE_ID,
        )

    def get_manifest(self, release_id: str) -> VerifiedHTTPDocument:
        exact = _exact_release_id(release_id)
        path = f"/api/v1/dataset-releases/{quote(exact, safe='')}/manifest"
        return self._json_document(
            path=path,
            release_id=exact,
            operation="get_dataset_release_manifest",
            data_contract_id=_RELEASE_MANIFEST_ID,
        )

    def get_status_history(self, release_id: str) -> VerifiedHTTPDocument:
        exact = _exact_release_id(release_id)
        path = f"/api/v1/dataset-releases/{quote(exact, safe='')}/status"
        document = self._json_document(
            path=path,
            release_id=exact,
            operation="get_dataset_release_status_history",
            data_contract_id=RELEASE_STATUS_HISTORY_ID,
        )
        _verify_status_chain(document.data, exact)
        return document

    def get_release_bundle(self, release_id: str) -> VerifiedHTTPReleaseBundle:
        exact = _exact_release_id(release_id)
        release = self.get_release(exact)
        manifest = self.get_manifest(exact)
        status = self.get_status_history(exact)
        manifest_hash = _hash_value(manifest.data.get("manifest_hash"), field="manifest_hash")
        manifest_ref = release.data.get("manifest_ref")
        if not isinstance(manifest_ref, dict):
            raise KBHTTPContractError("Release manifest_ref is not an object")
        current = release.data.get("current_status")
        head = status.data.get("current_status_event")
        if not isinstance(current, dict) or not isinstance(head, dict):
            raise KBHTTPContractError("Release current status closure is incomplete")
        if (
            manifest_sha256(manifest.data) != manifest_hash
            or _hash_value(manifest_ref.get("hash"), field="manifest_ref.hash") != manifest_hash
            or release.knowledge_cutoff != manifest.knowledge_cutoff
            or release.knowledge_cutoff != status.knowledge_cutoff
            or release.data.get("knowledge_cutoff") != manifest.data.get("knowledge_cutoff")
            or current.get("event_hash") != head.get("event_hash")
            or current.get("sequence") != head.get("sequence")
            or current.get("status") != head.get("status")
        ):
            raise KBHTTPContractError("HTTP Release/Manifest/status identity closure differs")
        return VerifiedHTTPReleaseBundle(release=release, manifest=manifest, status=status)

    def download_artifact(
        self,
        release_id: str,
        artifact_id: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> VerifiedHTTPArtifact:
        exact = _exact_release_id(release_id)
        artifact = _artifact_id(artifact_id)
        if _SHA256_RE.fullmatch(expected_sha256) is None:
            raise ValueError("expected_sha256 must be lowercase SHA-256")
        if (
            isinstance(expected_size_bytes, bool)
            or not isinstance(expected_size_bytes, int)
            or expected_size_bytes < 0
        ):
            raise ValueError("expected_size_bytes must be a non-negative integer")
        if expected_size_bytes > self._max_artifact_bytes:
            raise KBHTTPConfigurationError("expected artifact exceeds configured byte limit")
        path = (
            f"/api/v1/dataset-releases/{quote(exact, safe='')}/artifacts/{quote(artifact, safe='')}"
        )
        response = self._request(path, max_bytes=self._max_artifact_bytes)
        if response.status_code != 200:
            raise self._error(response)
        headers = _lower_headers(response.headers)
        try:
            content_length = int(headers["content-length"])
        except (KeyError, ValueError) as exc:
            raise KBHTTPContractError("artifact Content-Length is missing or invalid") from exc
        digest = sha256(response.body).hexdigest()
        if (
            content_length != len(response.body)
            or len(response.body) != expected_size_bytes
            or digest != expected_sha256
            or headers.get("etag") != f'"{digest}"'
            or headers.get("x-artifact-sha256") != digest
            or headers.get("x-dataset-release-id") != exact
            or headers.get("x-artifact-id") != artifact
        ):
            raise KBHTTPContractError("artifact headers, bytes, and Manifest expectation differ")
        media_type = headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not media_type:
            raise KBHTTPContractError("artifact Content-Type is missing")
        return VerifiedHTTPArtifact(
            request_path=path,
            release_id=exact,
            artifact_id=artifact,
            media_type=media_type,
            size_bytes=len(response.body),
            sha256=digest,
            content=response.body,
        )
