from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from invest_system import (
    FixedClock,
    ReleaseAccessError,
    ReleaseCacheStore,
    StrategyRunManifest,
)
from invest_system.integrations.investment_research_kb.contracts import (
    load_kb_contract_snapshot,
)
from invest_system.integrations.investment_research_kb.reference_fixture import (
    verify_stage6_reference_fixture,
)


def _count(database: Path, table: str) -> int:
    with sqlite3.connect(database) as connection:
        return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def test_official_fixture_persists_exact_closure_but_never_authorizes_a_run(
    repository_root: Path,
    tmp_path: Path,
    strategy_run_manifest: StrategyRunManifest,
) -> None:
    """Contract-test ``published`` data is retention evidence, not current admission."""

    catalog = load_kb_contract_snapshot(
        repository_root / "contracts/providers/investment_research_kb/v1"
    )
    result = verify_stage6_reference_fixture(catalog)
    store = ReleaseCacheStore(
        database_path=tmp_path / "state" / "invest_system.sqlite3",
        cache_root=tmp_path / "cache",
        clock=FixedClock(datetime(2026, 8, 1, tzinfo=UTC)),
    )

    assert store.record_verified_consumption(
        result.receipt,
        result.retention_closure,
        result.artifact_payloads,
        result.manifest_payloads,
    )
    assert not store.record_verified_consumption(
        result.receipt,
        result.retention_closure,
        result.artifact_payloads,
        result.manifest_payloads,
    )
    assert len(result.receipt.artifacts) == 2
    assert sum(len(node.artifacts) for node in result.retention_closure.releases) == 4
    assert _count(store.database_path, "receipts") == 1
    assert _count(store.database_path, "closure_releases") == 2
    assert _count(store.database_path, "closure_artifacts") == 4
    assert _count(store.database_path, "release_manifests") == 2

    unadmitted = replace(
        strategy_run_manifest,
        run_id="stage2a_offline_fixture_is_not_authority",
        strategy_input_ref=result.strategy_input_ref,
        artifact_consumption_receipt_hash=result.receipt.receipt_hash,
    )
    with pytest.raises(ReleaseAccessError):
        store.pin_run(unadmitted)
    assert _count(store.database_path, "strategy_run_pins") == 0
