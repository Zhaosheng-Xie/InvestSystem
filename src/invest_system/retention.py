"""Provider-neutral retention contracts for verified KB Release closures.

The contracts in this module describe which exact Release manifests and
artifacts InvestSystem must retain for a consumed root Release.  They do not
know how a provider exposes that information and do not perform transport or
storage work.

``ArtifactPayload`` and ``ReleaseManifestPayload`` deliberately are not
canonical models: bytes are transport inputs whose integrity is checked
against the canonical retention descriptors by the storage boundary.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Any

from .canonical import canonical_json_bytes
from .models import CanonicalModel, HashDigest, StrategyInputRef

RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION = "0.1.0-draft"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


def _require_id(field_name: str, value: str, *, exact_release: bool = False) -> str:
    if not isinstance(value, str) or _ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-128 ASCII ID characters "
            "([A-Za-z0-9._:-]) and start with an alphanumeric character"
        )
    if exact_release and value.casefold() == "latest":
        raise ValueError(f"{field_name} must be an exact ID, not 'latest'")
    return value


def _require_provider_id(field_name: str, value: str) -> str:
    if not isinstance(value, str) or _PROVIDER_ID_RE.fullmatch(value) is None:
        raise ValueError(
            f"{field_name} must be 1-256 provider ID characters "
            "([A-Za-z0-9._:/-]) and start with an alphanumeric character"
        )
    return value


def _require_non_negative_int(field_name: str, value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _ordered_tuple[T](field_name: str, values: Iterable[T]) -> tuple[T, ...]:
    if not isinstance(values, (list, tuple)):
        raise TypeError(f"{field_name} must be an ordered list or tuple")
    return tuple(values)


@dataclass(frozen=True, slots=True)
class ArtifactPayload:
    """Exact artifact bytes passed to storage; intentionally non-canonical."""

    release_id: str
    artifact_id: str
    content: bytes

    def __post_init__(self) -> None:
        _require_id("release_id", self.release_id, exact_release=True)
        _require_provider_id("artifact_id", self.artifact_id)
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")


@dataclass(frozen=True, slots=True)
class ReleaseManifestPayload:
    """Exact sealed provider Manifest bytes; intentionally non-canonical."""

    release_id: str
    content: bytes

    def __post_init__(self) -> None:
        _require_id("release_id", self.release_id, exact_release=True)
        if not isinstance(self.content, bytes):
            raise TypeError("content must be bytes")
        if not self.content:
            raise ValueError("Release Manifest content must not be empty")


@dataclass(frozen=True, slots=True)
class RetentionArtifact(CanonicalModel):
    """One immutable artifact descriptor required by a Release closure."""

    artifact_id: str
    item_type: str
    artifact_hash: HashDigest
    size_bytes: int
    record_count: int | None

    def __post_init__(self) -> None:
        _require_provider_id("artifact_id", self.artifact_id)
        _require_id("item_type", self.item_type)
        if not isinstance(self.artifact_hash, HashDigest):
            raise TypeError("artifact_hash must be a HashDigest")
        _require_non_negative_int("size_bytes", self.size_bytes)
        if self.record_count is not None:
            _require_non_negative_int("record_count", self.record_count)


def _normalize_artifacts(values: Iterable[RetentionArtifact]) -> tuple[RetentionArtifact, ...]:
    artifacts = _ordered_tuple("artifacts", values)
    if not artifacts:
        raise ValueError("artifacts must not be empty")
    if any(not isinstance(artifact, RetentionArtifact) for artifact in artifacts):
        raise TypeError("artifacts must contain only RetentionArtifact values")
    artifact_ids = tuple(artifact.artifact_id for artifact in artifacts)
    if len(artifact_ids) != len(set(artifact_ids)):
        raise ValueError("artifacts must not contain duplicate artifact_id values")
    return tuple(sorted(artifacts, key=lambda artifact: artifact.artifact_id))


def _normalize_dependencies(values: Iterable[str]) -> tuple[str, ...]:
    dependencies = _ordered_tuple("dependency_release_ids", values)
    normalized = tuple(
        _require_id("dependency_release_ids", release_id, exact_release=True)
        for release_id in dependencies
    )
    if len(normalized) != len(set(normalized)):
        raise ValueError("dependency_release_ids must not contain duplicate release IDs")
    return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class ReleaseRetentionNode(CanonicalModel):
    """One Release identity, its artifacts, and its direct source dependencies."""

    strategy_input_ref: StrategyInputRef
    manifest_document_hash: HashDigest
    manifest_size_bytes: int
    artifacts: tuple[RetentionArtifact, ...]
    dependency_release_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_input_ref, StrategyInputRef):
            raise TypeError("strategy_input_ref must be a StrategyInputRef")
        if not isinstance(self.manifest_document_hash, HashDigest):
            raise TypeError("manifest_document_hash must be a HashDigest")
        _require_non_negative_int("manifest_size_bytes", self.manifest_size_bytes)
        if self.manifest_size_bytes == 0:
            raise ValueError("manifest_size_bytes must be positive")
        artifacts = _normalize_artifacts(self.artifacts)
        dependencies = _normalize_dependencies(self.dependency_release_ids)
        if self.release_id in dependencies:
            raise ValueError("a Release must not depend on itself")
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "dependency_release_ids", dependencies)

    @property
    def release_id(self) -> str:
        """Exact Release ID, exposed as a convenience for graph and storage code."""

        return self.strategy_input_ref.dataset_release_id

    @property
    def knowledge_cutoff(self) -> datetime:
        """Release knowledge cutoff, preserved from the full five-field reference."""

        return self.strategy_input_ref.knowledge_cutoff

    @property
    def release_manifest_schema_version(self) -> str:
        return self.strategy_input_ref.release_manifest_schema_version

    @property
    def manifest_hash(self) -> HashDigest:
        return self.strategy_input_ref.manifest_hash


def _normalize_releases(
    values: Iterable[ReleaseRetentionNode],
) -> tuple[ReleaseRetentionNode, ...]:
    releases = _ordered_tuple("releases", values)
    if not releases:
        raise ValueError("releases must not be empty")
    if any(not isinstance(release, ReleaseRetentionNode) for release in releases):
        raise TypeError("releases must contain only ReleaseRetentionNode values")
    release_ids = tuple(release.release_id for release in releases)
    if len(release_ids) != len(set(release_ids)):
        raise ValueError("releases must not contain duplicate release_id values")
    return tuple(sorted(releases, key=lambda release: release.release_id))


def _validate_release_graph(
    root_release_id: str,
    releases: tuple[ReleaseRetentionNode, ...],
) -> None:
    by_id = {release.release_id: release for release in releases}
    if root_release_id not in by_id:
        raise ValueError("root_strategy_input_ref Release is absent from releases")

    for release in releases:
        for dependency_id in release.dependency_release_ids:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                raise ValueError(
                    f"dependency Release {dependency_id!r} referenced by "
                    f"{release.release_id!r} is absent from releases"
                )
            if dependency.knowledge_cutoff > release.knowledge_cutoff:
                raise ValueError("dependency knowledge_cutoff must be <= its parent Release cutoff")

    reachable: set[str] = set()
    pending = [root_release_id]
    while pending:
        release_id = pending.pop()
        if release_id in reachable:
            continue
        reachable.add(release_id)
        pending.extend(by_id[release_id].dependency_release_ids)
    if reachable != set(by_id):
        unreachable = ", ".join(sorted(set(by_id) - reachable))
        raise ValueError(
            f"every Release must be reachable from the root; unreachable: {unreachable}"
        )

    # Kahn's algorithm avoids recursion limits for large, adversarial closures.
    indegree = {release_id: 0 for release_id in by_id}
    for release in releases:
        for dependency_id in release.dependency_release_ids:
            indegree[dependency_id] += 1
    ready = [release_id for release_id, degree in indegree.items() if degree == 0]
    visited_count = 0
    while ready:
        release_id = ready.pop()
        visited_count += 1
        for dependency_id in by_id[release_id].dependency_release_ids:
            indegree[dependency_id] -= 1
            if indegree[dependency_id] == 0:
                ready.append(dependency_id)
    if visited_count != len(by_id):
        raise ValueError("Release dependency graph must not contain a cycle")


def _closure_identity_payload(
    *,
    schema_version: str,
    root_strategy_input_ref: StrategyInputRef,
    releases: tuple[ReleaseRetentionNode, ...],
) -> dict[str, Any]:
    """Build the explicit closure payload whose identity excludes ``closure_hash``."""

    return {
        "schema_version": schema_version,
        "root_strategy_input_ref": root_strategy_input_ref.to_json_value(),
        "releases": [release.to_json_value() for release in releases],
    }


@dataclass(frozen=True, slots=True)
class ReleaseRetentionClosure(CanonicalModel):
    """Canonical transitive Release/artifact retention closure for one root input."""

    schema_version: str
    root_strategy_input_ref: StrategyInputRef
    releases: tuple[ReleaseRetentionNode, ...]
    closure_hash: HashDigest

    def __post_init__(self) -> None:
        if self.schema_version != RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION!r}")
        if not isinstance(self.root_strategy_input_ref, StrategyInputRef):
            raise TypeError("root_strategy_input_ref must be a StrategyInputRef")
        releases = _normalize_releases(self.releases)
        object.__setattr__(self, "releases", releases)
        root_release_id = self.root_strategy_input_ref.dataset_release_id
        _validate_release_graph(root_release_id, releases)
        root = next(release for release in releases if release.release_id == root_release_id)
        if root.strategy_input_ref != self.root_strategy_input_ref:
            raise ValueError("root Release node must match all five root_strategy_input_ref fields")
        if not isinstance(self.closure_hash, HashDigest):
            raise TypeError("closure_hash must be a HashDigest")
        expected = sha256(canonical_json_bytes(self.identity_payload())).hexdigest()
        if self.closure_hash.value != expected:
            raise ValueError("closure_hash does not match the canonical identity payload")

    @classmethod
    def create(
        cls,
        *,
        root_strategy_input_ref: StrategyInputRef,
        releases: Iterable[ReleaseRetentionNode],
        schema_version: str = RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION,
    ) -> ReleaseRetentionClosure:
        """Normalize, validate, and hash an exact transitive retention closure."""

        if schema_version != RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {RELEASE_RETENTION_CLOSURE_SCHEMA_VERSION!r}")
        if not isinstance(root_strategy_input_ref, StrategyInputRef):
            raise TypeError("root_strategy_input_ref must be a StrategyInputRef")
        normalized = _normalize_releases(releases)
        _validate_release_graph(root_strategy_input_ref.dataset_release_id, normalized)
        root = next(
            release
            for release in normalized
            if release.release_id == root_strategy_input_ref.dataset_release_id
        )
        if root.strategy_input_ref != root_strategy_input_ref:
            raise ValueError("root Release node must match all five root_strategy_input_ref fields")
        payload = _closure_identity_payload(
            schema_version=schema_version,
            root_strategy_input_ref=root_strategy_input_ref,
            releases=normalized,
        )
        closure_hash = HashDigest(
            algorithm="sha256",
            value=sha256(canonical_json_bytes(payload)).hexdigest(),
        )
        return cls(
            schema_version=schema_version,
            root_strategy_input_ref=root_strategy_input_ref,
            releases=normalized,
            closure_hash=closure_hash,
        )

    def identity_payload(self) -> dict[str, Any]:
        """Return exactly the canonical payload covered by ``closure_hash``."""

        return _closure_identity_payload(
            schema_version=self.schema_version,
            root_strategy_input_ref=self.root_strategy_input_ref,
            releases=self.releases,
        )

    def release(self, release_id: str) -> ReleaseRetentionNode:
        """Return one exact node, raising ``KeyError`` when it is outside the closure."""

        _require_id("release_id", release_id, exact_release=True)
        for release in self.releases:
            if release.release_id == release_id:
                return release
        raise KeyError(release_id)
