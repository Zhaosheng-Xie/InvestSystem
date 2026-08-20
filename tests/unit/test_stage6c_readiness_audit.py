from __future__ import annotations

import json
import re
from collections import Counter
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.storage import STORAGE_SCHEMA_VERSION

AUDIT_PATH = Path("docs/validation/stage6c-formal-execution-readiness-audit-v0.1.md")
MACHINE_PATH = Path("docs/validation/machine/stage6c-formal-execution-readiness-audit-v0.1.json")
AUDIT_SHA256 = "9a688aa35df347ce7c9cf4e24e212c7e07f83dc761bc0b980b5f30576a13ca4b"
MACHINE_SHA256 = "68104028854a4b28c8f2aa0eec4f59e7901b8b26ca8ffc5eb497e6b4c76695b5"
EXPECTED_COUNTS = {
    "READY": 9,
    "MISSING": 22,
    "BLOCKED": 1,
    "NOT_REQUIRED_WITH_JUSTIFICATION": 2,
}


def _machine(repository_root: Path) -> dict[str, Any]:
    value = json.loads((repository_root / MACHINE_PATH).read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_stage6c_readiness_audit_has_exact_document_and_machine_identity(
    repository_root: Path,
) -> None:
    audit = repository_root / AUDIT_PATH
    machine = repository_root / MACHINE_PATH
    value = _machine(repository_root)

    assert sha256(audit.read_bytes()).hexdigest() == AUDIT_SHA256
    assert sha256(machine.read_bytes()).hexdigest() == MACHINE_SHA256
    assert value["schema_version"] == "1.0.0"
    assert value["baseline_commit"] == "4b786142fc3c584868f011d39fcf03f3bc2859a8"
    assert value["document_binding"] == {
        "path": AUDIT_PATH.as_posix(),
        "sha256": AUDIT_SHA256,
    }
    assert value["overall_status"] == "BLOCKED_FOR_FORMAL_STAGE6C_EXECUTION"
    assert value["decision"] == "NO_GO_FOR_FORMAL_STAGE6C_EXECUTION"


def test_stage6c_readiness_items_and_markdown_counts_are_closed_world(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    items = value["items"]
    expected_ids = [f"R-{number:02d}" for number in range(1, 35)]
    counts = Counter(item["status"] for item in items)
    audit_text = (repository_root / AUDIT_PATH).read_text(encoding="utf-8")
    markdown_items = re.findall(
        r"^\| `(R-\d{2})` \| `(READY|MISSING|BLOCKED|NOT_REQUIRED_WITH_JUSTIFICATION)` \|",
        audit_text,
        flags=re.MULTILINE,
    )

    assert [item["id"] for item in items] == expected_ids
    assert counts == EXPECTED_COUNTS
    assert value["status_counts"] == {**EXPECTED_COUNTS, "total": 34}
    assert [item_id for item_id, _ in markdown_items] == expected_ids
    assert Counter(status for _, status in markdown_items) == EXPECTED_COUNTS
    assert items[-1]["status"] == "BLOCKED"


def test_stage6c_readiness_audit_is_zero_authority_and_cannot_issue_runtime(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    machine_text = (repository_root / MACHINE_PATH).read_text(encoding="utf-8").lower()

    assert value["authority_eligible"] is False
    assert value["authorizations"]
    assert all(flag is False for flag in value["authorizations"].values())
    assert "formal_stage6c_execution" not in value["allowed_next_actions"]
    assert "holdout_read" not in value["allowed_next_actions"]
    assert "bearer" not in machine_text
    assert "investmentresearchkb/tmp" not in machine_text
    assert "investmentresearchkb\\tmp" not in machine_text
    assert "sqlite" not in machine_text or "kb sqlite" in machine_text


def test_stage6c_readiness_evidence_exists_and_formal_storage_is_still_absent(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    storage_text = (repository_root / "src/invest_system/storage.py").read_text(encoding="utf-8")

    assert all((repository_root / path).is_file() for path in value["evidence_paths"])
    assert STORAGE_SCHEMA_VERSION == 3
    assert "stage6_formal" not in storage_text.lower()
    assert "historical_run_admission_seals" not in storage_text.lower()


def test_stage6c_readiness_critical_path_preserves_provider_boundary(
    repository_root: Path,
) -> None:
    value = _machine(repository_root)
    boundary = value["responsibility_boundary"]

    assert "strategy logic" in value["critical_path"][0]
    assert "outcome-blind" in value["critical_path"][1]
    assert "facts" in boundary["kb"]
    assert "candidate inventory" in boundary["investsystem"].lower()
    assert any("No KB SQLite" in limitation for limitation in value["audit_limitations"])
