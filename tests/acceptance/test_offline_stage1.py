from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_synthetic_contract_harness_cold_starts_without_kb_or_external_io(
    tmp_path: Path,
) -> None:
    script = r"""
import os
import socket
import sqlite3
import sys
from datetime import UTC, datetime

assert "invest_system" not in sys.modules

def deny_external_io(*_args, **_kwargs):
    raise AssertionError("Stage 1 synthetic execution attempted external I/O")

socket.create_connection = deny_external_io
socket.getaddrinfo = deny_external_io
socket.socket.connect = deny_external_io
socket.socket.connect_ex = deny_external_io
sqlite3.connect = deny_external_io

from invest_system import (
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyInputRef,
    StrategyRunManifest,
)

digest = lambda character: HashDigest(algorithm="sha256", value=character * 64)
cutoff = datetime(2026, 7, 30, 8, tzinfo=UTC)
reference = StrategyInputRef(
    schema_version="1.0.0",
    dataset_release_id="synthetic_release_stage1_001",
    knowledge_cutoff=cutoff,
    release_manifest_schema_version="1.0.0",
    manifest_hash=digest("a"),
)
manifest = StrategyRunManifest(
    strategy_run_manifest_schema_version="0.2.0-draft",
    run_id="synthetic_cold_start_001",
    created_at=cutoff,
    strategy_id="industrial_bottleneck_event",
    strategy_version="0.1.0-draft",
    code_commit="0" * 40,
    rule_bundle_id="synthetic_stage1_rule_bundle",
    rule_bundle_version="0.1.0-draft",
    rule_bundle_hash=digest("f"),
    rule_status=RuleStatus.DRAFT,
    rule_approval_id=None,
    rule_approval_record_hash=None,
    rule_approval_scope=None,
    config_hash=digest("b"),
    strategy_input_ref=reference,
    input_envelope_hash=digest("7"),
    strategy_case_envelope_hash=digest("6"),
    strategy_case_input_hash=digest("8"),
    synthetic_fixture_id="synthetic_fixture_stage1_001",
    synthetic_fixture_version="0.1.0-draft",
    synthetic_fixture_payload_hash=digest("9"),
    input_path="synthetic_validation",
    synthetic=True,
    validation_only=True,
    not_a_published_release=True,
    not_strategy_evidence=True,
    authorizes_positions=False,
    authorizes_orders=False,
    artifact_consumption_receipt_hash=digest("c"),
    artifact_fetch_observation_id="synthetic_fetch_001",
    release_status_observation_id="synthetic_status_001",
    release_admission_observation_id="synthetic_admission_001",
    random_seed=0,
    run_mode=RunMode.RESEARCH,
    runtime_environment_lock_hash=digest("d"),
)

assert manifest.to_canonical_bytes()
assert manifest.canonical_sha256()
assert not any(
    module == "investment_research_kb" or module.startswith("investment_research_kb.")
    for module in sys.modules
)
assert os.listdir() == []
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)

    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", script],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    assert list(tmp_path.iterdir()) == []
