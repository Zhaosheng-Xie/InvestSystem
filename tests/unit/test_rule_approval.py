from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

import pytest

from invest_system.canonical import CanonicalJsonError, JsonValue
from invest_system.domain.rule_approval import (
    CURRENT_RULE_APPROVAL_REGISTRY,
    RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
    ApprovedRuleCapability,
    RuleApprovalError,
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
    require_approved_rule_bundle,
)
from invest_system.models import HashDigest, RuleStatus


def make_document(
    *,
    strategy_id: str = "industrial_bottleneck_event",
    bundle_id: str = "synthetic_stage2b_approval_boundary",
    bundle_version: str = "0.1.0",
    declared_status: RuleStatus = RuleStatus.APPROVED,
    rules: Mapping[str, JsonValue] | None = None,
) -> RuleBundleDocument:
    rule_content: Mapping[str, JsonValue] = (
        rules
        if rules is not None
        else {
            "business_semantics": False,
            "scope": "stage2b_rule_approval_boundary_only",
            "synthetic": True,
        }
    )
    return RuleBundleDocument(
        schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
        strategy_id=strategy_id,
        bundle_id=bundle_id,
        bundle_version=bundle_version,
        declared_status=declared_status,
        rules=rule_content,
    )


def make_approval(document: RuleBundleDocument) -> RuleApprovalRecord:
    return RuleApprovalRecord(
        approval_id="synthetic_test_approval_001",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=document.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="synthetic_test_authorization_001",
    )


def test_rule_bundle_uses_complete_canonical_json_and_hash_identity() -> None:
    mutable_rules: dict[str, JsonValue] = {
        "zeta": ("fixed", {"second": 2, "first": 1}),
        "alpha": {"synthetic": True, "business_semantics": False},
    }
    first = make_document(rules=mutable_rules)
    second = make_document(
        rules={
            "alpha": {"business_semantics": False, "synthetic": True},
            "zeta": ("fixed", {"first": 1, "second": 2}),
        }
    )

    mutable_rules["alpha"] = {"mutated_after_construction": True}

    assert first.to_canonical_bytes() == second.to_canonical_bytes()
    assert first.bundle_hash() == second.bundle_hash()
    assert first.to_canonical_json().startswith('{"bundle_id"')
    assert "mutated_after_construction" not in first.to_canonical_json()


def test_rule_bundle_canonical_profile_rejects_float_rules() -> None:
    with pytest.raises(CanonicalJsonError, match="floating-point values are forbidden"):
        RuleBundleDocument(
            schema_version=RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
            strategy_id="industrial_bottleneck_event",
            bundle_id="synthetic_stage2b_approval_boundary",
            bundle_version="0.1.0",
            declared_status=RuleStatus.HYPOTHESIS,
            rules={"unapproved_threshold": 0.1},  # type: ignore[dict-item]
        )


def test_exact_registry_match_is_the_only_path_to_approved_capability() -> None:
    document = make_document(declared_status=RuleStatus.APPROVED)
    approval = make_approval(document)
    registry = RuleApprovalRegistry((approval,))

    capability = require_approved_rule_bundle(document, registry=registry)

    assert capability.rule_status is RuleStatus.APPROVED
    assert capability.approval_id == approval.approval_id
    assert capability.strategy_id == document.strategy_id
    assert capability.bundle_id == document.bundle_id
    assert capability.bundle_version == document.bundle_version
    assert capability.bundle_hash == document.bundle_hash()
    assert capability.approval_scope is RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION
    assert capability.approval_record_hash == HashDigest(
        algorithm="sha256",
        value=approval.canonical_sha256(),
    )


def test_registry_cannot_upgrade_a_document_that_still_declares_draft() -> None:
    draft = make_document(declared_status=RuleStatus.DRAFT)
    registry = RuleApprovalRegistry((make_approval(draft),))

    with pytest.raises(RuleApprovalError) as captured:
        registry.require(draft)

    assert captured.value.code == "RULE_BUNDLE_STATUS_NOT_APPROVED"


def test_document_self_claim_and_current_empty_registry_fail_closed() -> None:
    self_claimed = make_document(declared_status=RuleStatus.APPROVED)

    assert CURRENT_RULE_APPROVAL_REGISTRY.records == ()
    with pytest.raises(RuleApprovalError) as captured:
        require_approved_rule_bundle(self_claimed)

    assert captured.value.code == "RULE_BUNDLE_IDENTITY_NOT_APPROVED"


def test_unknown_hash_fails_even_when_every_textual_identity_matches() -> None:
    approved_document = make_document(rules={"revision": "approved_exact_bytes"})
    registry = RuleApprovalRegistry((make_approval(approved_document),))
    changed_document = make_document(rules={"revision": "unknown_changed_bytes"})

    with pytest.raises(RuleApprovalError) as captured:
        registry.require(changed_document)

    assert captured.value.code == "RULE_BUNDLE_HASH_NOT_APPROVED"


@pytest.mark.parametrize(
    "changed_document",
    [
        make_document(strategy_id="different_strategy"),
        make_document(bundle_id="different_bundle"),
        make_document(bundle_version="0.1.1"),
    ],
)
def test_strategy_bundle_and_version_must_all_match_exactly(
    changed_document: RuleBundleDocument,
) -> None:
    approved_document = make_document()
    registry = RuleApprovalRegistry((make_approval(approved_document),))

    with pytest.raises(RuleApprovalError) as captured:
        registry.require(changed_document)

    assert captured.value.code == "RULE_BUNDLE_IDENTITY_NOT_APPROVED"


def test_registry_rejects_ambiguous_hashes_for_one_logical_version() -> None:
    document = make_document()
    exact = make_approval(document)
    conflicting = RuleApprovalRecord(
        approval_id="synthetic_test_approval_002",
        strategy_id=document.strategy_id,
        bundle_id=document.bundle_id,
        bundle_version=document.bundle_version,
        bundle_hash=HashDigest(algorithm="sha256", value="f" * 64),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="synthetic_test_authorization_002",
    )

    with pytest.raises(RuleApprovalError) as captured:
        RuleApprovalRegistry((exact, conflicting))

    assert captured.value.code == "RULE_APPROVAL_REGISTRY_AMBIGUOUS"


def test_registry_rejects_a_reused_approval_identifier() -> None:
    first_document = make_document(bundle_id="first_bundle")
    second_document = make_document(bundle_id="second_bundle")
    first = make_approval(first_document)
    second = RuleApprovalRecord(
        approval_id=first.approval_id,
        strategy_id=second_document.strategy_id,
        bundle_id=second_document.bundle_id,
        bundle_version=second_document.bundle_version,
        bundle_hash=second_document.bundle_hash(),
        approved_by="repository_owner",
        approved_at=datetime(2026, 8, 2, 9, tzinfo=UTC),
        approval_scope=RuleApprovalScope.STAGE2B_SYNTHETIC_VALIDATION,
        approval_source_ref="synthetic_test_authorization_003",
    )

    with pytest.raises(RuleApprovalError) as captured:
        RuleApprovalRegistry((first, second))

    assert captured.value.code == "RULE_APPROVAL_ID_REUSED"


def test_capability_constructor_rejects_non_registry_issuers() -> None:
    approval = make_approval(make_document())

    with pytest.raises(RuleApprovalError) as captured:
        ApprovedRuleCapability(_issuer=object(), approval=approval)

    assert captured.value.code == "RULE_CAPABILITY_ISSUER_INVALID"
