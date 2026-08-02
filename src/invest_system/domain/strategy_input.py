"""Provider-neutral provenance for InvestSystem-owned synthetic validation input.

Synthetic fixtures exercise strategy plumbing without claiming to be KB facts,
Published Releases, strategy evidence, or execution authority.  The wrapper is
deliberately distinct from :class:`VerifiedKnowledgeInput`: once a provider-
neutral payload has been projected, its validation-only provenance must not be
lost merely because every individual fact still looks structurally valid.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from invest_system.models import CanonicalModel, HashDigest, VerifiedKnowledgeInput

SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION = "0.1.0-draft"

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SEMVER_RE = re.compile(
    r"^(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)\."
    r"(?:0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_SYNTHETIC_PREFIX = "synthetic_"


class StrategyInputProvenance(StrEnum):
    """Input authorities understood by the Stage 2B-0 strategy boundary."""

    INVEST_SYSTEM_SYNTHETIC = "invest_system_synthetic"


@dataclass(frozen=True, slots=True)
class SyntheticValidationInput(CanonicalModel):
    """An immutable, non-authoritative wrapper around a synthetic input payload.

    ``fixture_payload_hash`` is the canonical SHA-256 of
    ``verified_knowledge_input``.  It is recomputed at construction so callers
    cannot relabel different bytes with an existing fixture identity.

    The fixed boolean fields are part of the canonical representation.  They
    make validation artifacts unmistakable even after serialization and
    prevent a caller from opting into Published Release, strategy-evidence, or
    position authority through constructor arguments.
    """

    fixture_id: str
    fixture_version: str
    fixture_payload_hash: HashDigest
    verified_knowledge_input: VerifiedKnowledgeInput
    schema_version: str = field(
        default=SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION,
        init=False,
    )
    provenance: StrategyInputProvenance = field(
        default=StrategyInputProvenance.INVEST_SYSTEM_SYNTHETIC,
        init=False,
    )
    synthetic: bool = field(default=True, init=False)
    validation_only: bool = field(default=True, init=False)
    not_a_published_release: bool = field(default=True, init=False)
    not_strategy_evidence: bool = field(default=True, init=False)
    authorizes_positions: bool = field(default=False, init=False)
    authorizes_orders: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.fixture_id, str) or _ID_RE.fullmatch(self.fixture_id) is None:
            raise ValueError("fixture_id must be a valid 1-128 character ASCII ID")
        if not self.fixture_id.startswith(_SYNTHETIC_PREFIX) or len(self.fixture_id) == len(
            _SYNTHETIC_PREFIX
        ):
            raise ValueError("fixture_id must use the synthetic_ namespace")
        if (
            not isinstance(self.fixture_version, str)
            or _SEMVER_RE.fullmatch(self.fixture_version) is None
        ):
            raise ValueError("fixture_version must be a semantic version")
        if not isinstance(self.fixture_payload_hash, HashDigest):
            raise TypeError("fixture_payload_hash must be a HashDigest")
        if not isinstance(self.verified_knowledge_input, VerifiedKnowledgeInput):
            raise TypeError("verified_knowledge_input must be a VerifiedKnowledgeInput")

        payload = self.verified_knowledge_input
        if not payload.input_id.startswith(_SYNTHETIC_PREFIX) or len(payload.input_id) == len(
            _SYNTHETIC_PREFIX
        ):
            raise ValueError("synthetic validation input_id must use the synthetic_ namespace")
        release_prefix = "synthetic_release_"
        if not payload.strategy_input_ref.dataset_release_id.startswith(release_prefix) or len(
            payload.strategy_input_ref.dataset_release_id
        ) == len(release_prefix):
            raise ValueError(
                "synthetic validation dataset_release_id must use the synthetic_release_ namespace"
            )

        for fact in payload.facts:
            if fact.metadata.get("synthetic") is not True:
                raise ValueError(f"fact {fact.fact_id!r} is missing synthetic=true provenance")
            if fact.metadata.get("not_a_published_release") is not True:
                raise ValueError(
                    f"fact {fact.fact_id!r} is missing not_a_published_release=true provenance"
                )

        expected_hash = payload.canonical_sha256()
        if self.fixture_payload_hash.value != expected_hash:
            raise ValueError(
                "fixture_payload_hash does not match the canonical verified_knowledge_input"
            )

    @classmethod
    def from_verified_input(
        cls,
        *,
        fixture_id: str,
        fixture_version: str,
        verified_knowledge_input: VerifiedKnowledgeInput,
    ) -> SyntheticValidationInput:
        """Build a wrapper with a content-derived fixture payload identity."""

        if not isinstance(verified_knowledge_input, VerifiedKnowledgeInput):
            raise TypeError("verified_knowledge_input must be a VerifiedKnowledgeInput")
        return cls(
            fixture_id=fixture_id,
            fixture_version=fixture_version,
            fixture_payload_hash=HashDigest(
                algorithm="sha256",
                value=verified_knowledge_input.canonical_sha256(),
            ),
            verified_knowledge_input=verified_knowledge_input,
        )
