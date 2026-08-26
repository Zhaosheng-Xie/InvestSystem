from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from invest_system.canonical import canonical_sha256

V01_DOCUMENT_PATH = Path(
    "docs/validation/stage6-minimum-public-data-consumption-contract-draft-v0.1.md"
)
V01_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.1-draft.json"
)
V02_DOCUMENT_PATH = Path("docs/validation/stage6-minimum-public-data-consumption-contract-v0.2.md")
V02_MACHINE_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.2.0.json"
)
V02_APPROVAL_PATH = Path(
    "docs/validation/machine/stage6-minimum-public-data-consumption-contract-v0.2.0.approval.json"
)

V01_DOCUMENT_SHA256 = "205a0c7d403d9fbadd988f2c3081882cb61594a5e4c36a6d4cc6db559e253182"
V01_MACHINE_SHA256 = "65b9288b7bf2279b061174869181b6e92c85f76db567c6297ff67996e49a1359"
V02_DOCUMENT_SHA256 = "ea82f2e17b99ecaec0cafde7ce5fe0fdb5d6d6855f6348891369cd0b2f02db43"
V02_MACHINE_SHA256 = "a7fd65c0d955d4e3610dcbefbaf6a2ec600689986aee0aa80123d167f8c88f6a"
V02_CONTRACT_HASH = "4063575384771228433fb8849c0fedd9fac2ba78f704ce5551bb4e23fe8c3557"
APPROVED_DECISIONS_HASH = "211f046282cb31f046db2fa382af38457810cbb03c20dfd60fb41162c84c5da4"
APPROVAL_RAW_SHA256 = "ab40ae5392a8c9d22e507c59066d20d84df7cec78ffcc77ff4aac4ce4a616b31"
APPROVAL_RECORD_HASH = "4331087874dcbee885f71b2eb0fef5611dd6d24772a95cce10b3d7514fa603ec"


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _canonical_without(value: dict[str, Any], field: str) -> str:
    return canonical_sha256({key: item for key, item in value.items() if key != field})


def test_v02_approval_preserves_v01_and_has_exact_content_identity(
    repository_root: Path,
) -> None:
    assert sha256((repository_root / V01_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        V01_DOCUMENT_SHA256
    )
    assert sha256((repository_root / V01_MACHINE_PATH).read_bytes()).hexdigest() == (
        V01_MACHINE_SHA256
    )
    assert sha256((repository_root / V02_DOCUMENT_PATH).read_bytes()).hexdigest() == (
        V02_DOCUMENT_SHA256
    )
    assert sha256((repository_root / V02_MACHINE_PATH).read_bytes()).hexdigest() == (
        V02_MACHINE_SHA256
    )
    assert sha256((repository_root / V02_APPROVAL_PATH).read_bytes()).hexdigest() == (
        APPROVAL_RAW_SHA256
    )

    contract = _json(repository_root / V02_MACHINE_PATH)
    approval = _json(repository_root / V02_APPROVAL_PATH)
    assert contract["contract_hash"] == V02_CONTRACT_HASH
    assert _canonical_without(contract, "contract_hash") == V02_CONTRACT_HASH
    assert approval["approval_record_hash"] == APPROVAL_RECORD_HASH
    assert _canonical_without(approval, "approval_record_hash") == APPROVAL_RECORD_HASH
    assert approval["contract"]["raw_sha256"] == V02_MACHINE_SHA256
    assert approval["document"]["sha256"] == V02_DOCUMENT_SHA256


def test_all_ten_owner_decisions_are_approved_atomically_and_resolvable(
    repository_root: Path,
) -> None:
    contract = _json(repository_root / V02_MACHINE_PATH)
    approval = _json(repository_root / V02_APPROVAL_PATH)
    expected_ids = [f"S6DATA-{number:02d}" for number in range(1, 11)]
    decisions = contract["approved_decisions"]

    assert [item["id"] for item in decisions] == expected_ids
    assert {item["status"] for item in decisions} == {"approved"}
    assert contract["owner_approval"]["decision_ids"] == expected_ids
    assert contract["owner_approval"]["all_decisions_approved_atomically"] is True
    assert approval["approved_decision_ids"] == expected_ids
    assert approval["approved_atomically"] is True
    assert canonical_sha256(decisions) == APPROVED_DECISIONS_HASH
    assert approval["approved_decisions_hash"] == APPROVED_DECISIONS_HASH

    document = (repository_root / V02_DOCUMENT_PATH).read_text(encoding="utf-8")
    checked = re.findall(r"^- \[x\] `(S6DATA-\d{2})`：", document, flags=re.MULTILINE)
    assert checked == expected_ids


def test_h00985_beta_and_adv_semantics_are_exact_without_fallback(
    repository_root: Path,
) -> None:
    contract = _json(repository_root / V02_MACHINE_PATH)
    beta = contract["beta120"]
    adv = contract["adv20"]

    assert beta["benchmark_id"] == "H00985"
    assert beta["benchmark_provider"] == "CSI"
    assert beta["benchmark_return_type"] == "gross_total_return"
    assert beta["window"] == "PREVIOUS_EXACTLY_120_EXCHANGE_SESSIONS"
    assert beta["estimator"] == "OLS_SLOPE_WITH_INTERCEPT"
    assert beta["missing_or_unknown_state"] == "INCOMPLETE_NOT_IMPUTED"
    assert beta["silent_fallback_forbidden"] is True
    assert beta["fallback_benchmark"] is None
    assert adv["window"] == "PREVIOUS_EXACTLY_20_EXCHANGE_SESSIONS"
    assert adv["denominator_sessions"] == 20
    assert adv["missing_or_unknown_state"] == "INCOMPLETE_NOT_ZERO"

    serialized = json.dumps(contract, ensure_ascii=False)
    for forbidden in ("000985", "N00985", "H00300"):
        assert forbidden not in serialized


def test_release_universe_action_and_delivery_boundaries_are_closed_world(
    repository_root: Path,
) -> None:
    contract = _json(repository_root / V02_MACHINE_PATH)
    architecture = contract["release_architecture"]
    universe = contract["target_universe"]
    gates = contract["hard_data_delivery_gates"]

    assert architecture["exactly_one_strategy_input_ref"] is True
    assert architecture["root_release_family"] == ("historical-stage6-public-input-2019-2025.v1")
    assert architecture["source_families"] == [
        "historical-public-evidence-2019-2025.v1",
        "historical-security-market-reference-2019-2025.v1",
        "historical-public-financials-2019-2025.v1",
    ]
    assert architecture["common_reference_factors_location"] == (
        "MERGED_INTO_SECURITY_MARKET_REFERENCE"
    )
    assert universe["exchanges"] == ["SSE", "SZSE"]
    assert universe["bse"] == "DEFERRED"
    assert universe["retain_st_star_st"] is True
    assert universe["retain_delisted_failed"] is True
    assert contract["corporate_action_minimum"] == [
        "CASH_DIVIDEND",
        "SHARE_DISTRIBUTION",
        "SPLIT_OR_CONSOLIDATION",
        "RIGHTS_OR_ALLOTMENT",
        "DELISTING_OR_CASH_OUT",
    ]
    assert {
        gates[key]
        for key in (
            "release_manifest_schema_dependency_identity",
            "calendar_market_rule_session_intervals",
            "security_entity_lifecycle_identified",
        )
    } == {"100_PERCENT"}


def test_transport_repin_and_zero_authority_cannot_be_laundered_into_runtime(
    repository_root: Path,
) -> None:
    contract = _json(repository_root / V02_MACHINE_PATH)
    approval = _json(repository_root / V02_APPROVAL_PATH)
    transport = contract["transport_and_repin"]

    assert transport["transport_protocol"] == "v1"
    assert transport["transport_v2_only_if_transport_semantics_change"] is True
    assert transport["repin_after_root_rc_and_producer_validation"] is True
    assert transport["repin_before_real_handoff_token"] is True
    assert contract["date_scope"]["contains_2026_holdout"] is False
    assert all(value is False for value in contract["observed_inputs"].values())
    assert all(value is False for value in contract["authorization_boundary"].values())
    assert all(value is False for value in approval["authorization_boundary"].values())


def test_v02_is_fully_materialized_governance_not_runtime_delta(
    repository_root: Path,
) -> None:
    contract = _json(repository_root / V02_MACHINE_PATH)

    assert contract["declared_status"] == "approved"
    assert contract["approved_scope"] == ("stage6_historical_public_data_requirements_governance")
    assert len(contract["p0_required_domains"]) == 16
    assert len(contract["artifact_schemas"]) == 11
    assert len(contract["provider_neutral_contract_fields"]) == 23
    assert len(contract["kb_next_implementation_order"]) == 12
    assert "delta" not in contract
    assert "merge_at_runtime" not in contract
