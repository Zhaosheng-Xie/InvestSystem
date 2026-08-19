from __future__ import annotations

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
from invest_system.models import HashDigest
from invest_system.stage6b_live_validation import (
    Stage6BLiveValidationError,
    prepare_stage6b_live_validation,
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
    assert prepared.stage3d_validation.authority_eligible is False
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
    assert len(prepared.stage3d_validation.receipt.artifacts) == 4
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
