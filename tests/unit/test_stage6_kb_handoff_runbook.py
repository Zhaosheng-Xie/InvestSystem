from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

DOCUMENT_PATH = Path("docs/validation/stage6-kb-historical-handoff-acceptance-runbook-v0.1.md")
MACHINE_PATH = Path(
    "docs/validation/machine/stage6-kb-historical-handoff-acceptance-runbook-v0.1.json"
)
DOCUMENT_SHA256 = "78cb24855224de4671f514c35a5352efc7d8f3008671be1dd621df736134f28f"
MACHINE_SHA256 = "6ce5c2226eacfb39e8645256595367ec350f014eac5316c5b35394e568ac3ce3"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_handoff_runbook_has_exact_document_and_machine_identity(
    repository_root: Path,
) -> None:
    document = repository_root / DOCUMENT_PATH
    machine = repository_root / MACHINE_PATH
    value = _json(machine)

    assert sha256(document.read_bytes()).hexdigest() == DOCUMENT_SHA256
    assert sha256(machine.read_bytes()).hexdigest() == MACHINE_SHA256
    assert value["schema_version"] == "1.0.0"
    assert value["baseline_commit"] == "8146c1ec076cbc76914692bd9320a7f466adca2c"
    assert value["document_binding"] == {
        "path": DOCUMENT_PATH.as_posix(),
        "sha256": DOCUMENT_SHA256,
    }
    assert value["status"] == "PREPARED_FOR_FUTURE_HANDOFF_NO_KB_DATA_CONSUMED"


def test_handoff_runbook_freezes_transport_domains_and_closed_results(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)

    assert value["transport_binding"] == {
        "source_commit": "aab36fe229104779b50ec71e2dc37a9fad81d285",
        "snapshot_lock_sha256": (
            "02e0505f727552f7632eee807fedd27e6ce6d8dbde05f4482e99641f42b91169"
        ),
    }
    assert value["development_date_range"] == {
        "start_inclusive": "2019-01-01",
        "end_inclusive": "2025-12-31",
    }
    assert value["result_statuses"] == [
        "HANDOFF_ACCEPTED_FOR_IS_CENSUS",
        "PARTIALLY_READY",
        "BLOCKED",
    ]
    domains = set(value["required_data_domains"])
    assert {
        "document_span_fact_event_evidence_closure",
        "company_security_historical_mapping",
        "trading_calendar_and_historical_market_rules",
        "unadjusted_daily_marks",
        "corporate_actions_and_cash_out",
        "pit_primary_industry",
        "pit_float_market_cap",
        "adv20_source_fields",
        "beta120_source_fields_or_generic_beta_artifact",
        "revision_correction_withdrawal_supersedes_lineage",
    } <= domains


def test_handoff_runbook_failure_reasons_match_document_and_are_unique(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    reasons = value["failure_reason_codes"]
    document = (repository_root / DOCUMENT_PATH).read_text(encoding="utf-8")
    documented = re.findall(r"^- `([A-Z0-9_]+)`$", document, flags=re.MULTILINE)

    assert len(reasons) == len(set(reasons)) == 24
    assert reasons == documented
    assert "HOLDOUT_BOUNDARY_VIOLATION" in reasons
    assert "PIT_ORDER_INVALID" in reasons
    assert "SURVIVOR_ONLY_OR_DELISTED_MISSING" in reasons
    assert "OUTCOME_FIELD_PRESENT" in reasons


def test_handoff_runbook_is_zero_authority_and_has_consumed_nothing(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    observed = value["observed_inputs"]
    boundary = value["authorization_boundary"]
    text = (repository_root / MACHINE_PATH).read_text(encoding="utf-8").lower()

    assert observed and all(item is False for item in observed.values())
    assert boundary and all(item is False for item in boundary.values())
    assert value["next_gate"] == (
        "OWNER_PROVIDES_EXACT_VERSIONED_KB_HANDOFF_AND_OPTIONAL_SHORT_LIVED_READ_CREDENTIALS"
    )
    assert "bearer" not in text
    assert "investmentresearchkb/tmp" not in text
    assert "investmentresearchkb\\tmp" not in text
    assert not (
        repository_root
        / "src/invest_system/integrations/investment_research_kb/stage6_historical_handoff.py"
    ).exists()


def test_handoff_runbook_rejects_holdout_and_outcome_content_by_construction(
    repository_root: Path,
) -> None:
    value = _json(repository_root / MACHINE_PATH)
    forbidden = set(value["forbidden_holdout_or_outcome_content"])

    assert {
        "2026_holdout_record",
        "2026_holdout_count",
        "2026_holdout_summary",
        "future_return",
        "nav",
        "pnl",
        "actual_exit_price",
        "completed_trade_flag",
        "champion_status",
        "p_value",
        "holm_result",
    } <= forbidden
    assert set(value["required_public_surfaces"]) == {
        "VERSIONED_READ_ONLY_HTTPS_PUBLISHED_RELEASE",
        "AUTHORIZED_IMMUTABLE_EXPORT_PACKAGE",
    }
    assert "KB_INTERNAL_PYTHON_PACKAGE" in value["forbidden_sources"]
    assert "KB_TMP_DIRECTORY" in value["forbidden_sources"]


def test_tzdata_is_a_direct_hash_locked_runtime_dependency(repository_root: Path) -> None:
    pyproject = (repository_root / "pyproject.toml").read_text(encoding="utf-8")
    runtime_lock = (repository_root / "requirements.lock").read_text(encoding="utf-8")
    dev_lock = (repository_root / "requirements-dev.lock").read_text(encoding="utf-8")
    expected = (
        "tzdata==2026.3 \\\n"
        "    --hash=sha256:4a1518b8993086a7982523e071643f3c0e5f213e75b21318e78bcabfff9d1415 \\\n"
        "    --hash=sha256:dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931"
    )

    assert '"tzdata>=2023.3,<2027"' in pyproject
    assert expected in runtime_lock
    assert expected in dev_lock
