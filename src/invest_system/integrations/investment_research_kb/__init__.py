"""Read-only integration boundary for pinned public KB contracts.

This package never imports the provider package or discovers a sibling
checkout. Callers must supply an InvestSystem-owned, hash-verified snapshot.
"""

from .contracts import (
    ContractSnapshotError,
    ContractValidationError,
    KBContractCatalog,
    SnapshotIntegrityError,
    StrictJsonError,
    load_kb_contract_snapshot,
    load_strict_json_bytes,
)
from .provider_canonical import (
    CANONICALIZATION_PROFILE,
    ProviderCanonicalError,
    canonical_json_bytes,
    canonical_jsonl_bytes,
    manifest_sha256,
    sealed_manifest_bytes,
)
from .reference_fixture import (
    CONSUMER_CONTRACT_VERSION,
    CONTEXT_PACK_PROJECTION_VERSION,
    ReferenceFixtureError,
    ReferenceFixtureResult,
    ReferenceValidationCode,
    ValidatedArtifact,
    ValidatedChange,
    ValidatedRelease,
    verify_stage6_reference_fixture,
)

__all__ = [
    "CANONICALIZATION_PROFILE",
    "CONSUMER_CONTRACT_VERSION",
    "CONTEXT_PACK_PROJECTION_VERSION",
    "ContractSnapshotError",
    "ContractValidationError",
    "KBContractCatalog",
    "ProviderCanonicalError",
    "ReferenceFixtureError",
    "ReferenceFixtureResult",
    "ReferenceValidationCode",
    "SnapshotIntegrityError",
    "StrictJsonError",
    "ValidatedArtifact",
    "ValidatedChange",
    "ValidatedRelease",
    "canonical_json_bytes",
    "canonical_jsonl_bytes",
    "load_kb_contract_snapshot",
    "load_strict_json_bytes",
    "manifest_sha256",
    "sealed_manifest_bytes",
    "verify_stage6_reference_fixture",
]
