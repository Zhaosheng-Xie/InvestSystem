"""Deterministic, self-excluding replay identities.

The replay envelope contains only inputs that may affect deterministic strategy
semantics.  Volatile audit identities such as run IDs, decision IDs, transport
observation IDs, endpoints, and persistence times are intentionally absent.
The resulting hash is stored outside the envelope, so its computation can never
accidentally include itself.
"""

from __future__ import annotations

import hmac
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from invest_system.canonical import JsonValue, freeze_json, normalize_utc
from invest_system.models import (
    CanonicalModel,
    HashDigest,
    RuleStatus,
    RunMode,
    StrategyRunManifest,
)

from .rule_approval import RuleBundleDocument
from .strategy_input import SyntheticValidationInput

REPLAY_ENVELOPE_SCHEMA_VERSION = "0.1.0-draft"
REPLAY_CANONICAL_PROFILE_VERSION = "investsystem-replay-v1"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

# These fields belong to audit storage or carry the replay digest itself.  A
# semantic payload containing one of them would silently reintroduce volatile
# identity into the replay hash, so fail closed even when the key is nested.
_RESERVED_SEMANTIC_KEYS = frozenset(
    {
        "artifact_fetch_observation_id",
        "decision_id",
        "endpoint",
        "observed_at",
        "persisted_at",
        "release_admission_observation_id",
        "release_status_observation_id",
        "replay_hash",
        "run_id",
    }
)


def _coerce_enum[EnumT: StrEnum](field_name: str, enum_type: type[EnumT], value: Any) -> EnumT:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(repr(member.value) for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}") from exc


def _assert_no_reserved_semantic_keys(value: Any, *, path: str = "$.semantic_output") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in _RESERVED_SEMANTIC_KEYS:
                raise ValueError(f"reserved replay key {key!r} is forbidden at {path}")
            _assert_no_reserved_semantic_keys(item, path=f"{path}.{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            _assert_no_reserved_semantic_keys(item, path=f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class ReplayEnvelope(CanonicalModel):
    """The complete deterministic projection used to calculate a replay hash."""

    input_envelope_hash: HashDigest
    verified_input_hash: HashDigest
    rule_bundle_hash: HashDigest
    strategy_id: str
    strategy_version: str
    code_commit: str
    rule_bundle_version: str
    rule_status: RuleStatus
    config_hash: HashDigest
    random_seed: int
    run_mode: RunMode
    runtime_environment_lock_hash: HashDigest
    evaluated_at: datetime
    semantic_output: Mapping[str, JsonValue]
    schema_version: str = field(default=REPLAY_ENVELOPE_SCHEMA_VERSION, init=False)
    canonical_profile_version: str = field(
        default=REPLAY_CANONICAL_PROFILE_VERSION,
        init=False,
    )

    def __post_init__(self) -> None:
        for field_name in (
            "input_envelope_hash",
            "verified_input_hash",
            "rule_bundle_hash",
            "config_hash",
            "runtime_environment_lock_hash",
        ):
            if not isinstance(getattr(self, field_name), HashDigest):
                raise TypeError(f"{field_name} must be a HashDigest")
        if not isinstance(self.strategy_id, str) or _ID_RE.fullmatch(self.strategy_id) is None:
            raise ValueError("strategy_id must be a valid 1-128 character ASCII ID")
        for field_name in ("strategy_version", "rule_bundle_version"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or _SEMVER_RE.fullmatch(value) is None:
                raise ValueError(f"{field_name} must be a semantic version")
        if (
            not isinstance(self.code_commit, str)
            or _GIT_COMMIT_RE.fullmatch(self.code_commit) is None
        ):
            raise ValueError("code_commit must be a full 40- or 64-character lowercase hex ID")
        object.__setattr__(
            self,
            "rule_status",
            _coerce_enum("rule_status", RuleStatus, self.rule_status),
        )
        if isinstance(self.random_seed, bool) or not isinstance(self.random_seed, int):
            raise TypeError("random_seed must be an integer")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")
        object.__setattr__(self, "run_mode", _coerce_enum("run_mode", RunMode, self.run_mode))
        object.__setattr__(
            self,
            "evaluated_at",
            normalize_utc(self.evaluated_at, field_name="evaluated_at"),
        )
        if not isinstance(self.semantic_output, Mapping):
            raise TypeError("semantic_output must be a mapping")
        _assert_no_reserved_semantic_keys(self.semantic_output)
        frozen = freeze_json(self.semantic_output, path="$.semantic_output")
        if not isinstance(frozen, Mapping):
            raise TypeError("semantic_output must freeze to a mapping")
        object.__setattr__(self, "semantic_output", frozen)

    @classmethod
    def from_synthetic_validation(
        cls,
        *,
        manifest: StrategyRunManifest,
        strategy_input: SyntheticValidationInput,
        rule_bundle: RuleBundleDocument,
        evaluated_at: datetime,
        semantic_output: Mapping[str, JsonValue],
    ) -> ReplayEnvelope:
        """Derive every content hash and deliberately ignore audit-only IDs."""

        if not isinstance(manifest, StrategyRunManifest):
            raise TypeError("manifest must be a StrategyRunManifest")
        if not isinstance(strategy_input, SyntheticValidationInput):
            raise TypeError("strategy_input must be a SyntheticValidationInput")
        if not isinstance(rule_bundle, RuleBundleDocument):
            raise TypeError("rule_bundle must be a RuleBundleDocument")
        if manifest.run_mode is not RunMode.RESEARCH:
            raise ValueError("synthetic validation replay requires research run_mode")
        if (
            strategy_input.verified_knowledge_input.strategy_input_ref
            != manifest.strategy_input_ref
        ):
            raise ValueError("strategy input reference must match the run Manifest")
        if rule_bundle.strategy_id != manifest.strategy_id:
            raise ValueError("rule bundle strategy_id must match the run Manifest")
        if rule_bundle.bundle_version != manifest.rule_bundle_version:
            raise ValueError("rule bundle version must match the run Manifest")
        if rule_bundle.declared_status is not manifest.rule_status:
            raise ValueError("rule bundle status must match the run Manifest")
        return cls(
            input_envelope_hash=HashDigest(
                algorithm="sha256",
                value=strategy_input.canonical_sha256(),
            ),
            verified_input_hash=strategy_input.fixture_payload_hash,
            rule_bundle_hash=rule_bundle.bundle_hash(),
            strategy_id=manifest.strategy_id,
            strategy_version=manifest.strategy_version,
            code_commit=manifest.code_commit,
            rule_bundle_version=manifest.rule_bundle_version,
            rule_status=manifest.rule_status,
            config_hash=manifest.config_hash,
            random_seed=manifest.random_seed,
            run_mode=manifest.run_mode,
            runtime_environment_lock_hash=manifest.runtime_environment_lock_hash,
            evaluated_at=evaluated_at,
            semantic_output=semantic_output,
        )


def compute_replay_hash(envelope: ReplayEnvelope) -> HashDigest:
    """Hash an envelope that cannot contain its own replay digest."""

    if not isinstance(envelope, ReplayEnvelope):
        raise TypeError("envelope must be a ReplayEnvelope")
    return HashDigest(algorithm="sha256", value=envelope.canonical_sha256())


def verify_replay_hash(envelope: ReplayEnvelope, expected: HashDigest) -> bool:
    """Constant-time comparison for a persisted replay digest."""

    if not isinstance(expected, HashDigest):
        raise TypeError("expected must be a HashDigest")
    actual = compute_replay_hash(envelope)
    return hmac.compare_digest(actual.value, expected.value)
