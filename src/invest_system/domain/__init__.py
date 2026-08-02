"""Provider-neutral Stage 2B-0 strategy-domain contracts."""

from .replay import (
    REPLAY_CANONICAL_PROFILE_VERSION,
    REPLAY_ENVELOPE_SCHEMA_VERSION,
    ReplayEnvelope,
    compute_replay_hash,
    verify_replay_hash,
)
from .rule_approval import (
    CURRENT_RULE_APPROVAL_REGISTRY,
    RULE_APPROVAL_RECORD_SCHEMA_VERSION,
    RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION,
    ApprovedRuleCapability,
    RuleApprovalError,
    RuleApprovalRecord,
    RuleApprovalRegistry,
    RuleApprovalScope,
    RuleBundleDocument,
    require_approved_rule_bundle,
)
from .strategy_input import (
    SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION,
    StrategyInputProvenance,
    SyntheticValidationInput,
)

__all__ = [
    "CURRENT_RULE_APPROVAL_REGISTRY",
    "REPLAY_CANONICAL_PROFILE_VERSION",
    "REPLAY_ENVELOPE_SCHEMA_VERSION",
    "RULE_APPROVAL_RECORD_SCHEMA_VERSION",
    "RULE_BUNDLE_DOCUMENT_SCHEMA_VERSION",
    "SYNTHETIC_VALIDATION_INPUT_SCHEMA_VERSION",
    "ApprovedRuleCapability",
    "ReplayEnvelope",
    "RuleApprovalError",
    "RuleApprovalRecord",
    "RuleApprovalRegistry",
    "RuleApprovalScope",
    "RuleBundleDocument",
    "StrategyInputProvenance",
    "SyntheticValidationInput",
    "compute_replay_hash",
    "require_approved_rule_bundle",
    "verify_replay_hash",
]
