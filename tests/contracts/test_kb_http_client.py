from __future__ import annotations

import copy
from collections import deque
from types import MappingProxyType
from typing import Any

import pytest

from invest_system.integrations.investment_research_kb import (
    KBHTTPContractError,
    KBHTTPRawResponse,
    KBHTTPRequest,
    KBHTTPResponseError,
    KBReadOnlyHTTPClient,
    KBTransportContractCatalog,
    reconstruct_official_export_fixture,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes,
)


class QueueExecutor:
    def __init__(self, responses: list[KBHTTPRawResponse]) -> None:
        self.responses = deque(responses)
        self.requests: list[KBHTTPRequest] = []

    def execute(self, request: KBHTTPRequest) -> KBHTTPRawResponse:
        self.requests.append(request)
        return self.responses.popleft()


def _response(
    status_code: int,
    body: object | bytes,
    *,
    headers: dict[str, str] | None = None,
) -> KBHTTPRawResponse:
    content = body if isinstance(body, bytes) else canonical_json_bytes(body) + b"\n"
    values = headers or {"content-type": "application/json"}
    return KBHTTPRawResponse(
        status_code=status_code,
        headers=MappingProxyType(values),
        body=content,
    )


def _client(
    catalog: KBTransportContractCatalog,
    executor: QueueExecutor,
    *,
    token: str = "offline-fixture-secret",
) -> KBReadOnlyHTTPClient:
    return KBReadOnlyHTTPClient(
        base_url="https://kb.invalid",
        bearer_token=token,
        catalog=catalog,
        executor=executor,
    )


def _envelope(data: dict[str, Any], *, request_id: str) -> dict[str, Any]:
    return {
        "meta": {
            "request_id": request_id,
            "api_version": "v1",
            "schema_version": "1.0.0",
            "generated_at": "2026-08-01T00:04:00.000000Z",
            "as_of": None,
            "knowledge_cutoff": "2026-08-01T00:00:00.000000Z",
            "release_id": "rel_stage6b_transport_fixture",
            "next_cursor": None,
        },
        "data": data,
    }


def _official_values(
    catalog: KBTransportContractCatalog,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    fixture = catalog.official_fixture
    sources = {
        item["path"]: item.get("value")
        for item in fixture["immutable_export_example"]["file_sources"]
    }
    release = sources["metadata/release.json"]
    manifest = sources["metadata/manifest.json"]
    status = fixture["http_examples"]["release_status_success"]["response"]["data"]
    assert isinstance(release, dict)
    assert isinstance(manifest, dict)
    assert isinstance(status, dict)
    return release, manifest, status


def _context_pack_build(manifest: dict[str, Any]) -> dict[str, Any]:
    digest = {"algorithm": "sha256", "value": "0" * 64}
    return {
        "context_pack_id": "ctx_stage3b_contract_test",
        "pack_key": "industrial-event/test",
        "version": "1.0.0",
        "supersedes_context_pack_id": None,
        "source_release": {
            "release_id": manifest["release_id"],
            "knowledge_cutoff": manifest["knowledge_cutoff"],
            "manifest_hash": manifest["manifest_hash"],
        },
        "compiler": {
            "compiler_id": "context-pack-compiler",
            "version": "1",
            "code_path": (
                "investment_research_kb.application.context_packs:"
                "ContextPackService.compile_from_release"
            ),
        },
        "config_files": [
            {"path": f"config/stage3b-{index}.json", "content_hash": digest} for index in range(7)
        ],
        "company_identities": [],
    }


def test_official_status_fixture_is_accepted_without_authority_escalation(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    example = kb_transport_catalog.official_fixture["http_examples"]["release_status_success"]
    executor = QueueExecutor([_response(200, example["response"])])
    client = _client(kb_transport_catalog, executor)

    result = client.get_status_history("rel_stage6b_transport_fixture")

    assert result.data["current_status_event"]["status"] == "published"
    assert result.authority_eligible is False
    assert result.response_sha256
    assert result.response_bytes
    assert executor.requests[0].url.endswith(
        "/api/v1/dataset-releases/rel_stage6b_transport_fixture/status"
    )
    assert executor.requests[0].headers["Authorization"] == ("Bearer offline-fixture-secret")
    assert "offline-fixture-secret" not in repr(client)


def test_manifest_context_pack_build_is_validated_by_pinned_openapi(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    _, manifest, _ = _official_values(kb_transport_catalog)
    manifest = copy.deepcopy(manifest)
    manifest["context_pack_build"] = _context_pack_build(manifest)
    executor = QueueExecutor([_response(200, _envelope(manifest, request_id="req-manifest"))])

    result = _client(kb_transport_catalog, executor).get_manifest(manifest["release_id"])

    assert result.data["context_pack_build"]["context_pack_id"] == ("ctx_stage3b_contract_test")
    assert result.authority_eligible is False


def test_manifest_context_pack_build_unknown_field_fails_closed(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    _, manifest, _ = _official_values(kb_transport_catalog)
    manifest = copy.deepcopy(manifest)
    build = _context_pack_build(manifest)
    build["uncontracted_field"] = True
    manifest["context_pack_build"] = build
    executor = QueueExecutor([_response(200, _envelope(manifest, request_id="req-manifest"))])

    with pytest.raises(KBHTTPContractError, match="pinned contract"):
        _client(kb_transport_catalog, executor).get_manifest(manifest["release_id"])


def test_latest_is_rejected_before_executor_io(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    executor = QueueExecutor([])
    client = _client(kb_transport_catalog, executor)

    with pytest.raises(ValueError, match="exact"):
        client.get_release("latest")
    assert executor.requests == []


def test_official_withdrawn_error_preserves_only_sanitized_fields(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    example = kb_transport_catalog.official_fixture["http_examples"]["withdrawn_artifact_error"]
    executor = QueueExecutor([_response(example["status_code"], example["response"])])
    token = "never-echo-this-token"
    client = _client(kb_transport_catalog, executor, token=token)

    with pytest.raises(KBHTTPResponseError) as caught:
        client.download_artifact(
            "rel_stage6b_transport_fixture",
            "stage6b-transport-fixture-v1",
            expected_sha256="9" * 64,
            expected_size_bytes=62,
        )
    assert caught.value.status_code == 410
    assert caught.value.code == "artifact_download_withdrawn"
    assert token not in str(caught.value)
    assert token not in repr(caught.value)


def test_http_release_bundle_closes_release_manifest_and_status(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    release, manifest, status = _official_values(kb_transport_catalog)
    executor = QueueExecutor(
        [
            _response(200, _envelope(release, request_id="req-release")),
            _response(200, _envelope(manifest, request_id="req-manifest")),
            _response(200, _envelope(status, request_id="req-status")),
        ]
    )
    result = _client(kb_transport_catalog, executor).get_release_bundle(
        "rel_stage6b_transport_fixture"
    )

    assert result.release.release_id == result.manifest.release_id == result.status.release_id
    assert all(
        document.authority_eligible is False
        for document in (result.release, result.manifest, result.status)
    )


def test_http_status_semantics_reject_a_non_head_current_event(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    example = copy.deepcopy(
        kb_transport_catalog.official_fixture["http_examples"]["release_status_success"]
    )
    example["response"]["data"]["current_status_event"] = example["response"]["data"]["events"][0]
    executor = QueueExecutor([_response(200, example["response"])])

    with pytest.raises(KBHTTPContractError, match="chain head"):
        _client(kb_transport_catalog, executor).get_status_history("rel_stage6b_transport_fixture")


def test_http_artifact_headers_bytes_and_manifest_expectation_must_agree(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    manifest, members = reconstruct_official_export_fixture(kb_transport_catalog)
    item = next(entry for entry in manifest["files"] if entry["role"] == "artifact")
    content = members[item["path"]]
    digest = item["sha256"]["value"]
    headers = {
        "content-type": item["media_type"],
        "content-length": str(len(content)),
        "etag": f'"{digest}"',
        "x-artifact-sha256": digest,
        "x-dataset-release-id": manifest["release"]["release_id"],
        "x-artifact-id": item["artifact_id"],
    }
    executor = QueueExecutor([_response(200, content, headers=headers)])
    result = _client(kb_transport_catalog, executor).download_artifact(
        manifest["release"]["release_id"],
        item["artifact_id"],
        expected_sha256=digest,
        expected_size_bytes=len(content),
    )
    assert result.content == content
    assert result.authority_eligible is False


def test_http_artifact_header_mismatch_fails_closed(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    content = b"fixture\n"
    executor = QueueExecutor(
        [
            _response(
                200,
                content,
                headers={
                    "content-type": "application/json",
                    "content-length": str(len(content)),
                    "etag": f'"{("0" * 64)}"',
                    "x-artifact-sha256": "0" * 64,
                    "x-dataset-release-id": "rel_stage6b_transport_fixture",
                    "x-artifact-id": "artifact",
                },
            )
        ]
    )
    client = _client(kb_transport_catalog, executor)

    with pytest.raises(KBHTTPContractError, match="differ"):
        client.download_artifact(
            "rel_stage6b_transport_fixture",
            "artifact",
            expected_sha256="0" * 64,
            expected_size_bytes=len(content),
        )
