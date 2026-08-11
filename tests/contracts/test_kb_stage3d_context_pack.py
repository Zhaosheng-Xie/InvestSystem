from __future__ import annotations

import copy
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import cast

import pytest

from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    KBTransportContractCatalog,
    Stage3DArtifactExpectation,
    Stage3DExpectation,
    Stage3DValidationError,
    VerifiedHTTPArtifact,
    VerifiedHTTPDocument,
    VerifiedHTTPReleaseBundle,
    validate_stage3d_http_context_pack,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes,
)
from invest_system.models import GateOutcome, HashDigest, StrategyInputRef


@dataclass
class OfflineStage3DClient:
    bundles: dict[str, VerifiedHTTPReleaseBundle]
    artifacts: dict[tuple[str, str], VerifiedHTTPArtifact]
    context_query: VerifiedHTTPDocument

    def get_release_bundle(self, release_id: str) -> VerifiedHTTPReleaseBundle:
        return self.bundles[release_id]

    def download_artifact(
        self,
        release_id: str,
        artifact_id: str,
        *,
        expected_sha256: str,
        expected_size_bytes: int,
    ) -> VerifiedHTTPArtifact:
        artifact = self.artifacts[(release_id, artifact_id)]
        assert artifact.sha256 == expected_sha256
        assert artifact.size_bytes == expected_size_bytes
        return artifact

    def get_context_pack(
        self,
        context_pack_id: str,
        *,
        release_id: str,
    ) -> VerifiedHTTPDocument:
        assert self.context_query.data["context_pack_id"] == context_pack_id
        assert self.context_query.release_id == release_id
        return self.context_query


def _document(
    *,
    operation: str,
    release_id: str,
    knowledge_cutoff: str,
    data: dict[str, object],
) -> VerifiedHTTPDocument:
    content = canonical_json_bytes(data) + b"\n"
    return VerifiedHTTPDocument(
        operation=operation,
        request_path=f"offline/{operation}",
        release_id=release_id,
        request_id=f"req_{operation}",
        knowledge_cutoff=knowledge_cutoff,
        response_sha256=sha256(content).hexdigest(),
        response_bytes=content,
        data=data,
    )


def _artifact_expectation(item: dict[str, object]) -> Stage3DArtifactExpectation:
    return Stage3DArtifactExpectation(
        artifact_id=cast(str, item["artifact_id"]),
        sha256=cast(dict[str, str], item["artifact_hash"])["value"],
        size_bytes=cast(int, item["size_bytes"]),
        content_type=cast(str, item["media_type"]),
        item_type=cast(str, item["item_type"]),
        schema_id=cast(str, item["record_schema_id"]),
        schema_version=cast(str, item["record_schema_version"]),
        record_schema_hash=cast(dict[str, str], item["record_schema_hash"])["value"],
    )


def _offline_case(
    catalog: KBTransportContractCatalog,
) -> tuple[OfflineStage3DClient, Stage3DExpectation]:
    fixture = catalog.base_catalog.stage6_fixture
    strategy_raw = fixture["expected_strategy_input_ref"]
    context_release_id = strategy_raw["dataset_release_id"]
    context_release = next(
        value
        for value in fixture["releases"]
        if value["dataset_release"]["release_id"] == context_release_id
    )
    context_pack = next(
        value
        for value in context_release["artifacts"].values()
        if isinstance(value, dict) and "context_pack_hash" in value
    )
    evidence_release_id = context_pack["source_releases"][0]["release_id"]
    evidence_release = next(
        value
        for value in fixture["releases"]
        if value["dataset_release"]["release_id"] == evidence_release_id
    )
    releases = {
        context_release_id: context_release,
        evidence_release_id: evidence_release,
    }
    bundles: dict[str, VerifiedHTTPReleaseBundle] = {}
    artifacts: dict[tuple[str, str], VerifiedHTTPArtifact] = {}
    for release_id, release in releases.items():
        dataset = release["dataset_release"]
        manifest = release["manifest"]
        cutoff = dataset["knowledge_cutoff"]
        head = copy.deepcopy(dataset["current_status"])
        head["release_id"] = release_id
        head["previous_event_hash"] = {
            "algorithm": "sha256",
            "value": "1" * 64,
        }
        bundles[release_id] = VerifiedHTTPReleaseBundle(
            release=_document(
                operation="release",
                release_id=release_id,
                knowledge_cutoff=cutoff,
                data=dataset,
            ),
            manifest=_document(
                operation="manifest",
                release_id=release_id,
                knowledge_cutoff=cutoff,
                data=manifest,
            ),
            status=_document(
                operation="status",
                release_id=release_id,
                knowledge_cutoff=cutoff,
                data={"current_status_event": head},
            ),
        )
        for item in manifest["release_items"]:
            artifact_id = item["artifact_id"]
            value = release["artifacts"][artifact_id]
            if item["item_type"] == "schema":
                contract = next(
                    contract
                    for contract in catalog.base_catalog.schema_contracts
                    if contract.contract_id == item["record_schema_id"]
                )
                content = catalog.base_catalog.read_vendor_bytes(contract.relative_path)
            else:
                content = canonical_json_bytes(value) + b"\n"
            artifacts[(release_id, artifact_id)] = VerifiedHTTPArtifact(
                request_path=f"offline/{release_id}/{artifact_id}",
                release_id=release_id,
                artifact_id=artifact_id,
                media_type=item["media_type"],
                size_bytes=len(content),
                sha256=sha256(content).hexdigest(),
                content=content,
            )
    context_items = {
        item["item_type"]: item for item in context_release["manifest"]["release_items"]
    }
    evidence_items = {
        item["item_type"]: item for item in evidence_release["manifest"]["release_items"]
    }
    strategy_input_ref = StrategyInputRef(
        schema_version=strategy_raw["schema_version"],
        dataset_release_id=strategy_raw["dataset_release_id"],
        knowledge_cutoff=datetime.fromisoformat(
            strategy_raw["knowledge_cutoff"].replace("Z", "+00:00")
        ),
        release_manifest_schema_version=strategy_raw["release_manifest_schema_version"],
        manifest_hash=HashDigest(**strategy_raw["manifest_hash"]),
    )
    expectation = Stage3DExpectation(
        handoff_sha256="2" * 64,
        base_url="https://kb.invalid",
        context_release_id=context_release_id,
        context_pack_id=context_pack["context_pack_id"],
        context_pack_hash=context_pack["context_pack_hash"]["value"],
        source_graph_hash=context_pack["source_graph_hash"]["value"],
        knowledge_cutoff=strategy_input_ref.knowledge_cutoff,
        manifest_hash=strategy_input_ref.manifest_hash.value,
        strategy_input_ref=strategy_input_ref,
        context_artifact=_artifact_expectation(context_items["context_pack"]),
        context_schema_artifact=_artifact_expectation(context_items["schema"]),
        evidence_release_id=evidence_release_id,
        evidence_manifest_hash=evidence_release["manifest"]["manifest_hash"]["value"],
        evidence_artifact=_artifact_expectation(evidence_items["evidence_bundle"]),
        evidence_schema_artifact=_artifact_expectation(evidence_items["schema"]),
    )
    query = _document(
        operation="context_query",
        release_id=context_release_id,
        knowledge_cutoff=context_pack["knowledge_cutoff"],
        data=context_pack,
    )
    return OfflineStage3DClient(bundles, artifacts, query), expectation


def test_stage3d_offline_transport_projection_remains_zero_authority(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    offline, expectation = _offline_case(kb_transport_catalog)

    result = validate_stage3d_http_context_pack(
        client=cast(KBReadOnlyHTTPClient, offline),
        catalog=kb_transport_catalog,
        expectation=expectation,
        observed_at=datetime(2026, 8, 1, tzinfo=UTC),
        code_commit="a" * 40,
        config_hash=HashDigest(algorithm="sha256", value="3" * 64),
        runtime_environment_lock_hash=HashDigest(algorithm="sha256", value="4" * 64),
    )

    assert result.smoke.outcome is GateOutcome.ABSTAIN
    assert "real_strategy_rules_not_authorized_for_stage3d_smoke" in result.smoke.reason_codes
    assert result.authority_eligible is False
    assert result.run_release_status_confirmation_issued is False
    assert result.persists_state is False
    assert result.manifest.synthetic is False
    assert result.manifest.validation_only is True
    assert result.manifest.not_a_published_release is False
    assert result.manifest.authorizes_positions is False
    assert result.manifest.authorizes_orders is False
    assert result.admission_observation.admission_status.value == "unconfirmed"
    assert result.provider_input.context_pack_hash.value == expectation.context_pack_hash
    assert len(result.receipt.artifacts) == 4
    assert {item.artifact_id for item in result.receipt.artifacts} == set(result.artifact_sha256)


def test_stage3d_context_query_must_equal_downloaded_artifact(
    kb_transport_catalog: KBTransportContractCatalog,
) -> None:
    offline, expectation = _offline_case(kb_transport_catalog)
    offline.context_query.data["pack_key"] = "different-pack"

    with pytest.raises(Stage3DValidationError, match="CONTEXT_QUERY_MISMATCH"):
        validate_stage3d_http_context_pack(
            client=cast(KBReadOnlyHTTPClient, offline),
            catalog=kb_transport_catalog,
            expectation=expectation,
            observed_at=datetime(2026, 8, 1, tzinfo=UTC),
            code_commit="a" * 40,
            config_hash=HashDigest(algorithm="sha256", value="3" * 64),
            runtime_environment_lock_hash=HashDigest(algorithm="sha256", value="4" * 64),
        )
