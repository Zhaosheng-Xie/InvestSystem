from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any, cast

import pytest

from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    KBTransportContractCatalog,
    Stage3DExpectation,
    VerifiedHTTPArtifact,
    VerifiedHTTPDocument,
    VerifiedHTTPReleaseBundle,
)
from invest_system.integrations.investment_research_kb.stage6b_handoff import (
    Stage6BProducerHandoff,
)
from invest_system.models import HashDigest
from invest_system.stage6b_live_validation import (
    Stage6BLiveValidationError,
    prepare_stage6b_live_validation,
    prepare_stage6b_producer_handoff_validation,
    read_stage6b_credential_env,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    STAGE6B_AUTHORITY_ORIGIN,
)

_STAGE3D_TEST_SUPPORT = import_module("tests.contracts.test_kb_stage3d_context_pack")


@dataclass
class OfflineStage6BLiveClient:
    delegate: Any
    catalog: KBTransportContractCatalog
    bundle_calls: int = 0
    artifact_calls: int = 0
    context_calls: int = 0

    @property
    def base_url(self) -> str:
        return STAGE6B_AUTHORITY_ORIGIN

    @property
    def contract_source_commit(self) -> str:
        return self.catalog.source_commit

    @property
    def contract_snapshot_lock_sha256(self) -> str:
        return self.catalog.snapshot_lock_sha256

    def get_release_bundle(self, release_id: str) -> VerifiedHTTPReleaseBundle:
        self.bundle_calls += 1
        return cast(VerifiedHTTPReleaseBundle, self.delegate.get_release_bundle(release_id))

    def download_artifact(
        self,
        release_id: str,
        artifact_id: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> VerifiedHTTPArtifact:
        self.artifact_calls += 1
        return cast(
            VerifiedHTTPArtifact,
            self.delegate.download_artifact(
                release_id,
                artifact_id,
                expected_sha256=expected_sha256,
                expected_size_bytes=expected_size_bytes,
            ),
        )

    def get_context_pack(
        self,
        context_pack_id: str,
        *,
        release_id: str,
    ) -> VerifiedHTTPDocument:
        self.context_calls += 1
        return cast(
            VerifiedHTTPDocument,
            self.delegate.get_context_pack(context_pack_id, release_id=release_id),
        )


def _expectation_and_client(
    catalog: KBTransportContractCatalog,
) -> tuple[OfflineStage6BLiveClient, Stage3DExpectation]:
    offline, expectation = _STAGE3D_TEST_SUPPORT._offline_case(catalog)
    return OfflineStage6BLiveClient(offline, catalog), replace(
        expectation,
        handoff_sha256="2" * 64,
        base_url=STAGE6B_AUTHORITY_ORIGIN,
    )


def _producer_artifact(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_id": item["artifact_id"],
        "content_type": item["media_type"],
        "item_type": item["item_type"],
        "logical_path": item["logical_path"],
        "observed_content_type": item["media_type"],
        "record_schema_id": item["record_schema_id"],
        "record_schema_sha256": item["record_schema_hash"]["value"],
        "record_schema_version": item["record_schema_version"],
        "response_headers_verified": True,
        "sha256": item["artifact_hash"]["value"],
        "size_bytes": item["size_bytes"],
    }


def _producer_release(bundle: VerifiedHTTPReleaseBundle) -> dict[str, Any]:
    head = dict(cast(dict[str, Any], bundle.status.data["current_status_event"]))
    return {
        "artifacts": [
            _producer_artifact(item)
            for item in cast(list[dict[str, Any]], bundle.manifest.data["release_items"])
        ],
        "current_status": "published",
        "knowledge_cutoff": bundle.manifest.data["knowledge_cutoff"],
        "manifest": {
            "artifact_count": len(cast(list[Any], bundle.manifest.data["release_items"])),
            "response_sha256": bundle.manifest.response_sha256,
            "schema_version": bundle.manifest.data["schema_version"],
            "sha256": cast(dict[str, str], bundle.manifest.data["manifest_hash"])["value"],
        },
        "release_id": bundle.release.release_id,
        "release_response_sha256": bundle.release.response_sha256,
        "status": {
            "head": {
                "authority": "release_status_chain",
                "event_hash": head["event_hash"],
                "event_id": head["event_id"],
                "recorded_at": head["recorded_at"],
                "sequence": head["sequence"],
                "status": head["status"],
            },
            "response_sha256": bundle.status.response_sha256,
        },
    }


def _producer_handoff(
    *,
    offline: OfflineStage6BLiveClient,
    expectation: Stage3DExpectation,
    tmp_path: Path,
) -> tuple[Stage6BProducerHandoff, bytes]:
    root_bundle = offline.get_release_bundle(expectation.context_release_id)
    source_bundle = offline.get_release_bundle(expectation.evidence_release_id)
    report = tmp_path / "producer-report.json"
    report.write_bytes(b'{"acceptance":"passed"}\n')
    credential = tmp_path / "stage6b.env"
    credential.write_text("placeholder", encoding="utf-8")
    source_manifest_hash = cast(dict[str, str], source_bundle.manifest.data["manifest_hash"])[
        "value"
    ]
    handoff_value = {
        "allowed_http_surfaces": [
            "GET /api/v1/dataset-releases/{release_id}",
            "GET /api/v1/dataset-releases/{release_id}/manifest",
            "GET /api/v1/dataset-releases/{release_id}/status",
            "GET /api/v1/dataset-releases/{release_id}/artifacts/{artifact_id}",
        ],
        "authority_eligible": False,
        "credential": {
            "env_file_absolute_path": str(credential.resolve()),
            "expires_at_utc": "2026-08-21T00:00:00Z",
            "plaintext_token_embedded_in_handoff": False,
            "principal": "invest-system-stage6b-test",
            "scopes": ["export:read", "research:read"],
            "token_id": "token_test",
        },
        "forbidden_or_out_of_scope": ["context-pack-query"],
        "generated_at": "2026-08-20T00:00:00Z",
        "handoff_json_absolute_path": str((tmp_path / "handoff.json").resolve()),
        "handoff_schema_version": "1.0.0",
        "production_base_url": STAGE6B_AUTHORITY_ORIGIN,
        "purpose": "invest-system-stage6b-real-https-validation-only-admission",
        "root_release": _producer_release(root_bundle),
        "source_closure": {
            "closed": True,
            "relations": [
                {
                    "declared_by_artifact_id": expectation.context_artifact.artifact_id,
                    "from_release_id": expectation.context_release_id,
                    "knowledge_cutoff": source_bundle.manifest.data["knowledge_cutoff"],
                    "relation": "declares_source_release",
                    "source_manifest_sha256": source_manifest_hash,
                    "to_release_id": expectation.evidence_release_id,
                }
            ],
            "root_release_id": expectation.context_release_id,
            "transitive_source_release_ids": [expectation.evidence_release_id],
        },
        "source_releases": [_producer_release(source_bundle)],
        "transport_contract": {
            "snapshot_lock_sha256": offline.contract_snapshot_lock_sha256,
            "source_commit": offline.contract_source_commit,
        },
        "validation_evidence": {
            "all_release_manifest_status_artifact_checks_passed": True,
            "evidence_scope_endpoint_http_status": 403,
            "unauthenticated_release_http_status": 401,
            "validation_report_absolute_path": str(report.resolve()),
            "validation_report_sha256": sha256(report.read_bytes()).hexdigest(),
        },
    }
    content = json.dumps(
        handoff_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    parsed = Stage6BProducerHandoff.from_bytes(content, expected_sha256=sha256(content).hexdigest())
    parsed.verify_external_paths(credential_env_path=credential)
    return parsed, content


def test_stage6b_live_preparation_reuses_validated_context_and_builds_root_only_receipt(
    repository_root: Path,
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    offline, expectation = _expectation_and_client(kb_transport_catalog)

    prepared = prepare_stage6b_live_validation(
        repository_root=repository_root,
        client=cast(KBReadOnlyHTTPClient, offline),
        catalog=kb_transport_catalog,
        expectation=expectation,
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        code_commit="a" * 40,
        runtime_environment_lock_hash=HashDigest(algorithm="sha256", value="3" * 64),
        semantic_config_hash=HashDigest(algorithm="sha256", value="4" * 64),
    )

    assert prepared.validation_only is True
    assert prepared.authority_eligible is False
    assert prepared.authority_eligible is False
    assert prepared.request.strategy_input_ref == expectation.strategy_input_ref
    assert prepared.receipt.strategy_input_ref == expectation.strategy_input_ref
    assert tuple(item.artifact_id for item in prepared.receipt.artifacts) == tuple(
        sorted(
            (
                expectation.context_artifact.artifact_id,
                expectation.context_schema_artifact.artifact_id,
            )
        )
    )
    assert len(prepared.content_artifact_sha256) == 4
    assert tuple(node.release_id for node in prepared.closure.releases) == tuple(
        sorted((expectation.context_release_id, expectation.evidence_release_id))
    )
    root = next(
        node
        for node in prepared.closure.releases
        if node.release_id == expectation.context_release_id
    )
    assert root.dependency_release_ids == (expectation.evidence_release_id,)
    assert len(prepared.manifest_payloads) == 2
    assert len(prepared.artifact_payloads) == 4
    for node in prepared.closure.releases:
        manifest = next(
            item for item in prepared.manifest_payloads if item.release_id == node.release_id
        )
        assert sha256(manifest.content).hexdigest() == node.manifest_document_hash.value
        for descriptor in node.artifacts:
            payload = next(
                item
                for item in prepared.artifact_payloads
                if item.release_id == node.release_id and item.artifact_id == descriptor.artifact_id
            )
            assert sha256(payload.content).hexdigest() == descriptor.artifact_hash.value
    assert offline.bundle_calls == 4
    assert offline.artifact_calls == 8
    assert offline.context_calls == 1


def test_stage6b_live_preparation_rejects_non_authority_origin_before_http(
    repository_root: Path,
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    offline, expectation = _expectation_and_client(kb_transport_catalog)
    expectation = replace(expectation, base_url="https://not-approved.invalid")

    with pytest.raises(Stage6BLiveValidationError, match="AUTHORITY_ORIGIN_MISMATCH"):
        prepare_stage6b_live_validation(
            repository_root=repository_root,
            client=cast(KBReadOnlyHTTPClient, offline),
            catalog=kb_transport_catalog,
            expectation=expectation,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            code_commit="a" * 40,
            runtime_environment_lock_hash=HashDigest(algorithm="sha256", value="3" * 64),
            semantic_config_hash=HashDigest(algorithm="sha256", value="4" * 64),
        )

    assert offline.bundle_calls == 0
    assert offline.artifact_calls == 0
    assert offline.context_calls == 0


def test_stage6b_producer_handoff_preparation_uses_only_allowed_http_surfaces(
    repository_root: Path,
    kb_transport_catalog: KBTransportContractCatalog,
    tmp_path: Path,
) -> None:
    offline, expectation = _expectation_and_client(kb_transport_catalog)
    handoff, _ = _producer_handoff(
        offline=offline,
        expectation=expectation,
        tmp_path=tmp_path,
    )
    offline.bundle_calls = 0
    offline.artifact_calls = 0
    offline.context_calls = 0

    prepared = prepare_stage6b_producer_handoff_validation(
        repository_root=repository_root,
        client=cast(KBReadOnlyHTTPClient, offline),
        handoff=handoff,
        observed_at=datetime(2026, 8, 20, tzinfo=UTC),
        code_commit="a" * 40,
        runtime_environment_lock_hash=HashDigest(algorithm="sha256", value="3" * 64),
        semantic_config_hash=HashDigest(algorithm="sha256", value="4" * 64),
    )

    assert prepared.validation_only is True
    assert prepared.authority_eligible is False
    assert prepared.request.strategy_input_ref == handoff.root_release.strategy_input_ref()
    assert len(prepared.receipt.artifacts) == 2
    assert len(prepared.closure.releases) == 2
    assert len(prepared.artifact_payloads) == 4
    assert len(prepared.content_response_sha256) == 6
    assert len(prepared.content_artifact_sha256) == 4
    assert offline.bundle_calls == 2
    assert offline.artifact_calls == 4
    assert offline.context_calls == 0


def test_stage6b_credential_env_is_closed_world_and_never_echoes_token(
    tmp_path: Path,
) -> None:
    token = "secret-token-must-not-appear"
    valid = tmp_path / "valid.env"
    valid.write_text(
        f'KB_BASE_URL="{STAGE6B_AUTHORITY_ORIGIN}"\nKB_BEARER_TOKEN="{token}"\n',
        encoding="utf-8",
    )
    assert read_stage6b_credential_env(valid) == (STAGE6B_AUTHORITY_ORIGIN, token)

    invalid = tmp_path / "invalid.env"
    invalid.write_text(
        f"KB_BASE_URL={STAGE6B_AUTHORITY_ORIGIN}\nKB_BEARER_TOKEN={token}\nUNEXPECTED={token}\n",
        encoding="utf-8",
    )
    with pytest.raises(Stage6BLiveValidationError) as caught:
        read_stage6b_credential_env(invalid)
    assert token not in str(caught.value)
