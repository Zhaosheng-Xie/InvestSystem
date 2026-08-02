"""Fail-closed approval boundary for versioned strategy rule bundles.

Rule bundle documents are data, not authority.  In particular, a document may
describe itself as ``approved`` without gaining any capability.  The only
granting operation in this module is an exact lookup in an injected immutable
approval registry over strategy ID, bundle ID, bundle version, and the
canonical SHA-256 of the complete document.

The checked-in production registry is intentionally empty until a concrete
business rule bundle is separately approved.  This module defines no event,
gate, valuation, position, or execution semantics.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from ..canonical import JsonValue, freeze_json, normalize_utc
from ..models import CanonicalModel, HashDigest, RuleStatus

RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION = "0.1.0-draft"
RULE_APPROVAL_RECORD_SCHEMA_VERSION = "0.1.0-draft"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _require_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-128 ASCII ID characters "
            "([A-Za-z0-9._:-]) and start with an alphanumeric character"
        )
    return value


def _require_version(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _SEMVER_RE.fullmatch(value) is None:
        raise ValueError(f"{field_name} must be a semantic version")
    return value


def _coerce_rule_status(value: RuleStatus | str) -> RuleStatus:
    try:
        return value if isinstance(value, RuleStatus) else RuleStatus(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in RuleStatus)
        raise ValueError(f"declared_status must be one of: {allowed}") from exc


class RuleApprovalError(ValueError):
    """A stable fail-closed rejection from the rule approval boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class RuleApprovalScope(StrEnum):
    """Capabilities an owner approval may grant in the current contract."""

    STAGE2B_SYNTHETIC_VALIDATION = "stage2b_synthetic_validation"


@dataclass(frozen=True, slots=True)
class RuleBundleDocument(CanonicalModel):
    """Immutable rule document whose complete canonical bytes define identity."""

    schema_version: str
    strategy_id: str
    bundle_id: str
    bundle_version: str
    declared_status: RuleStatus
    rules: Mapping[str, JsonValue]

    def __post_init__(self) -> None:
        if self.schema_version != RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION!r}")
        _require_id("strategy_id", self.strategy_id)
        _require_id("bundle_id", self.bundle_id)
        _require_version("bundle_version", self.bundle_version)
        object.__setattr__(self, "declared_status", _coerce_rule_status(self.declared_status))

        frozen_rules = freeze_json(self.rules, path="$.rules")
        if not isinstance(frozen_rules, Mapping):
            raise TypeError("rules must be a mapping")
        if not frozen_rules:
            raise ValueError("rules must not be empty")
        object.__setattr__(self, "rules", frozen_rules)

    def bundle_hash(self) -> HashDigest:
        """Return the identity hash of the complete canonical document."""

        return HashDigest(algorithm="sha256", value=self.canonical_sha256())


@dataclass(frozen=True, slots=True)
class RuleApprovalRecord(CanonicalModel):
    """Trusted registry record binding one approval to one exact document."""

    approval_id: str
    strategy_id: str
    bundle_id: str
    bundle_version: str
    bundle_hash: HashDigest
    approved_by: str
    approved_at: datetime
    approval_scope: RuleApprovalScope
    approval_source_ref: str
    schema_version: str = field(default=RULE_APPROVAL_RECORD_SCHEMA_VERSION, init=False)

    def __post_init__(self) -> None:
        _require_id("approval_id", self.approval_id)
        _require_id("strategy_id", self.strategy_id)
        _require_id("bundle_id", self.bundle_id)
        _require_version("bundle_version", self.bundle_version)
        if not isinstance(self.bundle_hash, HashDigest):
            raise TypeError("bundle_hash must be a HashDigest")
        _require_id("approved_by", self.approved_by)
        object.__setattr__(
            self,
            "approved_at",
            normalize_utc(self.approved_at, field_name="approved_at"),
        )
        try:
            scope = (
                self.approval_scope
                if isinstance(self.approval_scope, RuleApprovalScope)
                else RuleApprovalScope(self.approval_scope)
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("approval_scope is not supported") from exc
        object.__setattr__(self, "approval_scope", scope)
        _require_id("approval_source_ref", self.approval_source_ref)


_CAPABILITY_ISSUER = object()


@dataclass(frozen=True, slots=True, init=False)
class ApprovedRuleCapability(CanonicalModel):
    """Opaque proof that the current registry authorized an exact bundle."""

    approval_id: str
    strategy_id: str
    bundle_id: str
    bundle_version: str
    bundle_hash: HashDigest
    approval_record_hash: HashDigest
    approval_scope: RuleApprovalScope
    rule_status: RuleStatus

    def __init__(self, *, _issuer: object, approval: RuleApprovalRecord) -> None:
        if _issuer is not _CAPABILITY_ISSUER:
            raise RuleApprovalError(
                "RULE_CAPABILITY_ISSUER_INVALID",
                "approved capabilities can only be issued by RuleApprovalRegistry",
            )
        object.__setattr__(self, "approval_id", approval.approval_id)
        object.__setattr__(self, "strategy_id", approval.strategy_id)
        object.__setattr__(self, "bundle_id", approval.bundle_id)
        object.__setattr__(self, "bundle_version", approval.bundle_version)
        object.__setattr__(self, "bundle_hash", approval.bundle_hash)
        object.__setattr__(
            self,
            "approval_record_hash",
            HashDigest(algorithm="sha256", value=approval.canonical_sha256()),
        )
        object.__setattr__(self, "approval_scope", approval.approval_scope)
        object.__setattr__(self, "rule_status", RuleStatus.APPROVED)


class RuleApprovalRegistry:
    """Immutable, exact-match registry that is the sole capability issuer."""

    __slots__ = ("_by_identity", "_records")

    _by_identity: Mapping[tuple[str, str, str], RuleApprovalRecord]
    _records: tuple[RuleApprovalRecord, ...]

    def __init__(self, approvals: Iterable[RuleApprovalRecord] = ()) -> None:
        records = tuple(approvals)
        by_identity: dict[tuple[str, str, str], RuleApprovalRecord] = {}
        approval_ids: set[str] = set()
        for approval in records:
            if not isinstance(approval, RuleApprovalRecord):
                raise TypeError("approvals must contain only RuleApprovalRecord values")
            identity = (
                approval.strategy_id,
                approval.bundle_id,
                approval.bundle_version,
            )
            if identity in by_identity:
                raise RuleApprovalError(
                    "RULE_APPROVAL_REGISTRY_AMBIGUOUS",
                    "an approval identity may bind exactly one document hash",
                )
            if approval.approval_id in approval_ids:
                raise RuleApprovalError(
                    "RULE_APPROVAL_ID_REUSED",
                    "an approval_id may identify exactly one approval record",
                )
            by_identity[identity] = approval
            approval_ids.add(approval.approval_id)
        self._records = records
        self._by_identity = MappingProxyType(by_identity)

    @property
    def records(self) -> tuple[RuleApprovalRecord, ...]:
        """Return the immutable registry snapshot."""

        return self._records

    def require(self, document: RuleBundleDocument) -> ApprovedRuleCapability:
        """Issue a capability only for an exact approved document identity."""

        if not isinstance(document, RuleBundleDocument):
            raise TypeError("document must be a RuleBundleDocument")
        if document.declared_status is not RuleStatus.APPROVED:
            raise RuleApprovalError(
                "RULE_BUNDLE_STATUS_NOT_APPROVED",
                "the exact rule bundle document must declare approved status",
            )
        identity = (document.strategy_id, document.bundle_id, document.bundle_version)
        approval = self._by_identity.get(identity)
        if approval is None:
            raise RuleApprovalError(
                "RULE_BUNDLE_IDENTITY_NOT_APPROVED",
                "strategy ID, bundle ID, and bundle version are not approved",
            )
        if approval.bundle_hash != document.bundle_hash():
            raise RuleApprovalError(
                "RULE_BUNDLE_HASH_NOT_APPROVED",
                "the canonical rule bundle hash is not approved for this identity",
            )
        return ApprovedRuleCapability(_issuer=_CAPABILITY_ISSUER, approval=approval)


# No business rule bundle has been approved yet.  Adding an entry is a separate,
# reviewable governance change; a document's declared_status never mutates this.
CURRENT_RULE_APPROVAL_REGISTRY = RuleApprovalRegistry()


def require_approved_rule_bundle(
    document: RuleBundleDocument,
    *,
    registry: RuleApprovalRegistry = CURRENT_RULE_APPROVAL_REGISTRY,
) -> ApprovedRuleCapability:
    """Resolve approval through the supplied authoritative registry snapshot."""

    if not isinstance(registry, RuleApprovalRegistry):
        raise TypeError("registry must be a RuleApprovalRegistry")
    return registry.require(document)
