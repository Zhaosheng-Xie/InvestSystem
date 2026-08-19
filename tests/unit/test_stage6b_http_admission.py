from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType

import pytest

from invest_system.integrations.investment_research_kb import (
    KBHTTPRawResponse,
    KBHTTPRequest,
    KBHTTPTransportError,
    KBReadOnlyHTTPClient,
    load_kb_transport_contract_snapshot,
)
from invest_system.integrations.investment_research_kb.provider_canonical import (
    canonical_json_bytes as provider_canonical_json_bytes,
)
from invest_system.stage6b_http_admission import (
    execute_stage6b_public_https_validation_admission,
    fetch_stage6b_closure_status_evidence,
)
from invest_system.strategies.industrial_event.stage6b_admission import (
    STAGE6B_AUTHORITY_ORIGIN,
    Stage6BAdmissionError,
)
from invest_system.strategies.industrial_event.stage6b_validation_store import (
    Stage6BValidationStore,
)

from .test_stage6b_admission import _complete_admission, _fixture_response

TRANSPORT_ROOT = Path("contracts/providers/investment_research_kb/stage6b-transport-v1")


class SequenceClock:
    def __init__(self, values: Iterable[datetime]) -> None:
        self._values = iter(values)

    def __call__(self) -> datetime:
        return next(self._values)


class StatusExecutor:
    def __init__(self, body: bytes, *, database_path: Path | None = None) -> None:
        self.body = body
        self.database_path = database_path
        self.requests: list[KBHTTPRequest] = []

    def execute(self, request: KBHTTPRequest) -> KBHTTPRawResponse:
        self.requests.append(request)
        if self.database_path is not None:
            with sqlite3.connect(self.database_path, isolation_level=None) as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("ROLLBACK")
        return KBHTTPRawResponse(
            status_code=200,
            headers=MappingProxyType({"content-type": "application/json"}),
            body=self.body,
        )


class FailingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, request: KBHTTPRequest) -> KBHTTPRawResponse:
        self.calls += 1
        raise KBHTTPTransportError("sanitized transport failure")


def _client(repository_root: Path, executor: object, *, base_url: str) -> KBReadOnlyHTTPClient:
    catalog = load_kb_transport_contract_snapshot(repository_root / TRANSPORT_ROOT)
    return KBReadOnlyHTTPClient(
        base_url=base_url,
        bearer_token="unit-test-token-never-persisted",
        catalog=catalog,
        executor=executor,  # type: ignore[arg-type]
    )


def test_public_https_adapter_fetches_before_transaction_and_seals_zero_authority(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    response = _fixture_response(repository_root)
    body = provider_canonical_json_bytes(response)
    store = Stage6BValidationStore(tmp_path / "stage6b-http")
    executor = StatusExecutor(body, database_path=store.database_path)
    client = _client(repository_root, executor, base_url=STAGE6B_AUTHORITY_ORIGIN)
    clock = SequenceClock(
        (
            datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 4, 31, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 4, 32, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 4, 33, tzinfo=UTC),
            datetime(2026, 8, 1, 0, 4, 40, tzinfo=UTC),
        )
    )

    result = execute_stage6b_public_https_validation_admission(
        client,
        store,
        request=values["request"],
        preregistration=values["preregistration"],
        receipt=values["receipt"],
        closure=values["closure"],
        fetch_observation=values["fetch_observation"],
        manifest_payloads=values["manifest_payloads"],
        artifact_payloads=values["artifact_payloads"],
        strategy_version="0.1.0",
        random_seed=0,
        clock=clock,
    )

    assert result.seal == store.read_validation_seal(values["request"].run_id)
    assert result.response_sha256_by_release == (
        (values["request"].strategy_input_ref.dataset_release_id, sha256(body).hexdigest()),
    )
    assert result.public_https_calls == len(executor.requests) == 1
    assert executor.requests[0].url == (
        f"{STAGE6B_AUTHORITY_ORIGIN}/api/v1/dataset-releases/rel_stage6b_transport_fixture/status"
    )
    assert "unit-test-token-never-persisted" not in repr(client)
    assert result.validation_only is True
    assert result.authority_eligible is False
    assert result.strategy_evaluator_calls == 0


def test_wrong_origin_is_blocked_before_http_and_transport_failure_creates_no_seal(
    repository_root: Path,
    tmp_path: Path,
) -> None:
    values = _complete_admission(repository_root)
    response = _fixture_response(repository_root)
    executor = StatusExecutor(provider_canonical_json_bytes(response))
    wrong_origin = _client(repository_root, executor, base_url="https://example.com")
    with pytest.raises(Stage6BAdmissionError, match="PRECHECK_BLOCKED"):
        fetch_stage6b_closure_status_evidence(
            wrong_origin,
            request=values["request"],
            closure=values["closure"],
            clock=SequenceClock((datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),)),
        )
    assert executor.requests == []

    store = Stage6BValidationStore(tmp_path / "stage6b-http-failure")
    failing = FailingExecutor()
    client = _client(repository_root, failing, base_url=STAGE6B_AUTHORITY_ORIGIN)
    with pytest.raises(Stage6BAdmissionError, match="STATUS_UNCONFIRMED"):
        execute_stage6b_public_https_validation_admission(
            client,
            store,
            request=values["request"],
            preregistration=values["preregistration"],
            receipt=values["receipt"],
            closure=values["closure"],
            fetch_observation=values["fetch_observation"],
            manifest_payloads=values["manifest_payloads"],
            artifact_payloads=values["artifact_payloads"],
            strategy_version="0.1.0",
            random_seed=0,
            clock=SequenceClock((datetime(2026, 8, 1, 0, 4, 30, tzinfo=UTC),)),
        )
    assert failing.calls == 1
    assert store.authoritative_row_counts()["stage6b_validation_seals"] == 0
