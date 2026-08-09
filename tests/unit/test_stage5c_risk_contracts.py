from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import localcontext
from pathlib import Path

import pytest

from invest_system.models import HashDigest
from invest_system.strategies.industrial_event.stage5_execution_contracts import (
    MarketRegime,
    RecoveryApprovalDecision,
    RiskClusterAssignment,
    RiskClusterExposure,
    RiskClusterSnapshot,
    RiskClusterType,
    SyntheticAccountSnapshot,
    SyntheticRecoveryRecord,
    bind_stage5c_artifact,
)
from invest_system.strategies.industrial_event.stage5_market_execution import (
    Stage5ExecutionStatus,
)
from invest_system.strategies.industrial_event.stage5_portfolio_risk import (
    PortfolioRiskEvaluation,
    evaluate_stage5_portfolio_target,
)
from unit import test_stage5_market_execution as stage5b_support
from unit import test_stage5_portfolio_ledger as stage5c_support

STOPPED_AT = datetime(2025, 1, 16, 2, 0, tzinfo=UTC)
OWNER_APPROVED_AT = datetime(2025, 1, 17, 1, 0, tzinfo=UTC)
RECOVERY_AT = datetime(2025, 1, 17, 1, 30, tzinfo=UTC)
CURRENT_HEAD = HashDigest(algorithm="sha256", value="a" * 64)


def _hash(character: str) -> HashDigest:
    return HashDigest(algorithm="sha256", value=character * 64)


def _recovery_record(
    *,
    decision: RecoveryApprovalDecision = RecoveryApprovalDecision.APPROVED,
    strategy_id: str = "industrial_bottleneck_event",
    account_fixture_id: str = "anonymous_account_001",
    account_head: HashDigest = CURRENT_HEAD,
    effective_at: datetime = RECOVERY_AT,
) -> SyntheticRecoveryRecord:
    return bind_stage5c_artifact(
        SyntheticRecoveryRecord(
            identity=stage5b_support._identity(
                "synthetic_recovery_record_stage5c",
                as_of=effective_at,
            ),
            strategy_id=strategy_id,
            account_fixture_id=account_fixture_id,
            prior_stopped_ledger_event_id="ledger_stopped_001",
            prior_stopped_ledger_event_hash=_hash("b"),
            prior_stopped_ledger_head_hash=_hash("c"),
            recovery_ledger_event_id="ledger_recovery_001",
            recovery_ledger_event_hash=_hash("d"),
            account_ledger_head_hash=account_head,
            attribution_ref="synthetic_drawdown_attribution_001",
            attribution_hash=_hash("e"),
            rule_check_ref="synthetic_recovery_rule_check_001",
            rule_check_hash=_hash("f"),
            owner_approval_ref="synthetic_owner_recovery_approval_001",
            owner_approval_hash=_hash("1"),
            owner_approval_decision=decision,
            prior_stopped_at=STOPPED_AT,
            owner_approval_at=OWNER_APPROVED_AT,
            effective_at=effective_at,
        )
    )


def _risk(
    repository_root: Path,
    *,
    account: SyntheticAccountSnapshot,
    clusters: RiskClusterSnapshot | None = None,
) -> PortfolioRiskEvaluation:
    _, rules = stage5c_support._rules(repository_root)
    raw = stage5b_support._case(repository_root)
    return evaluate_stage5_portfolio_target(
        raw,
        account,
        clusters or stage5c_support._clusters(),
        stage5c_support._regime(MarketRegime.NORMAL),
        stage5c_support._stress(),
        stage5c_support._sizing(raw),
        stage5b_support._identity(
            "stage5c_risk_contract_target",
            as_of=stage5b_support.APPROVED_AT,
        ),
        rules,
    )


def _recovered_account(
    record: SyntheticRecoveryRecord,
    *,
    ledger_head: HashDigest | None = CURRENT_HEAD,
) -> SyntheticAccountSnapshot:
    return bind_stage5c_artifact(
        replace(
            stage5c_support._buy_account(),
            prior_stopped=True,
            ledger_head_hash=ledger_head,
            synthetic_recovery_record=record,
        )
    )


def test_risk_cluster_snapshot_allows_multiple_unique_clusters_per_type(
    repository_root: Path,
) -> None:
    base_clusters = stage5c_support._clusters()
    extra_assignment = RiskClusterAssignment(
        RiskClusterType.CUSTOMER,
        "cluster_customer_secondary",
    )
    clusters = bind_stage5c_artifact(
        replace(
            base_clusters,
            assignments=base_clusters.assignments + (extra_assignment,),
        )
    )
    base_account = stage5c_support._buy_account()
    account = bind_stage5c_artifact(
        replace(
            base_account,
            risk_cluster_exposures=base_account.risk_cluster_exposures
            + (
                RiskClusterExposure(
                    RiskClusterType.CUSTOMER,
                    "cluster_customer_secondary",
                    "20000",
                    "0",
                ),
            ),
        )
    )

    result = _risk(repository_root, account=account, clusters=clusters)

    assert result.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
    assert result.target is not None
    assert result.target.target_quantity == 0
    assert "cluster:customer:cluster_customer_secondary" in (result.target.binding_constraint_ids)


def test_every_extra_assigned_cluster_requires_an_exposure(repository_root: Path) -> None:
    base_clusters = stage5c_support._clusters()
    clusters = bind_stage5c_artifact(
        replace(
            base_clusters,
            assignments=base_clusters.assignments
            + (
                RiskClusterAssignment(
                    RiskClusterType.CUSTOMER,
                    "cluster_customer_secondary",
                ),
            ),
        )
    )

    result = _risk(
        repository_root,
        account=stage5c_support._buy_account(),
        clusters=clusters,
    )

    assert result.status is Stage5ExecutionStatus.ABSTAIN
    assert result.reason_codes == ("REQUIRED_RISK_CLUSTER_EXPOSURE_MISSING",)


def test_risk_cluster_assignments_require_all_types_and_unique_pairs() -> None:
    base = stage5c_support._clusters()
    with pytest.raises(ValueError, match="all five required"):
        RiskClusterSnapshot(
            identity=base.identity,
            strategy_id=base.strategy_id,
            security_id=base.security_id,
            company_id=base.company_id,
            assignments=base.assignments[:-1],
        )
    with pytest.raises(ValueError, match=r"\(type, id\) assignments must be unique"):
        RiskClusterSnapshot(
            identity=base.identity,
            strategy_id=base.strategy_id,
            security_id=base.security_id,
            company_id=base.company_id,
            assignments=base.assignments + (base.assignments[0],),
        )


def test_valid_typed_recovery_record_reopens_only_synthetic_new_risk(
    repository_root: Path,
) -> None:
    account = _recovered_account(_recovery_record())

    result = _risk(repository_root, account=account)

    assert result.status is Stage5ExecutionStatus.TARGET_READY
    assert result.target is not None
    assert result.target.target_quantity == 300
    assert result.reason_codes == ("PORTFOLIO_TARGET_READY",)


@pytest.mark.parametrize(
    ("account_factory", "expected_reason"),
    (
        (
            lambda: bind_stage5c_artifact(
                replace(stage5c_support._buy_account(), prior_stopped=True)
            ),
            "STOPPED_STATE_RECOVERY_RECORD_MISSING",
        ),
        (
            lambda: _recovered_account(_recovery_record(), ledger_head=None),
            "STOPPED_STATE_LEDGER_HEAD_MISSING",
        ),
        (
            lambda: _recovered_account(
                _recovery_record(decision=RecoveryApprovalDecision.REJECTED)
            ),
            "STOPPED_STATE_OWNER_RECOVERY_APPROVAL_MISSING",
        ),
    ),
)
def test_stopped_account_recovery_failures_keep_new_risk_at_zero(
    repository_root: Path,
    account_factory: Callable[[], SyntheticAccountSnapshot],
    expected_reason: str,
) -> None:
    result = _risk(repository_root, account=account_factory())

    if expected_reason == "STOPPED_STATE_LEDGER_HEAD_MISSING":
        assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
        assert result.target is None
    else:
        assert result.status is Stage5ExecutionStatus.SYNTHETIC_REJECTED
        assert result.target is not None
        assert result.target.target_quantity == 0
    assert result.reason_codes == (expected_reason,)


@pytest.mark.parametrize(
    ("account_factory", "expected_reason"),
    (
        (
            lambda: _recovered_account(
                _recovery_record(account_head=_hash("2")),
                ledger_head=CURRENT_HEAD,
            ),
            "RECOVERY_RECORD_SCOPE_OR_LEDGER_HEAD_MISMATCH",
        ),
        (
            lambda: _recovered_account(
                _recovery_record(strategy_id="theme_rotation"),
            ),
            "RECOVERY_RECORD_SCOPE_OR_LEDGER_HEAD_MISMATCH",
        ),
        (
            lambda: _recovered_account(
                _recovery_record(effective_at=stage5b_support.APPROVED_AT + timedelta(minutes=1)),
            ),
            "RECOVERY_RECORD_FROM_FUTURE_OR_TIME_SCOPE_INVALID",
        ),
    ),
)
def test_recovery_scope_head_and_time_mismatch_precheck_block(
    repository_root: Path,
    account_factory: Callable[[], SyntheticAccountSnapshot],
    expected_reason: str,
) -> None:
    result = _risk(repository_root, account=account_factory())

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.target is None
    assert result.reason_codes == (expected_reason,)


def test_nested_recovery_record_hash_drift_is_detected(repository_root: Path) -> None:
    record = _recovery_record()
    drifted_record = replace(record, attribution_ref="synthetic_drifted_attribution")
    account = _recovered_account(drifted_record)

    result = _risk(repository_root, account=account)

    assert result.status is Stage5ExecutionStatus.PRECHECK_BLOCKED
    assert result.reason_codes == ("RECOVERY_RECORD_HASH_DRIFT",)


def test_recovery_record_rejects_knowledge_known_after_effective_time() -> None:
    record = _recovery_record()

    with pytest.raises(ValueError, match="knowledge_cutoff must not postdate effective_at"):
        replace(
            record,
            identity=replace(
                record.identity,
                knowledge_cutoff=record.effective_at + timedelta(seconds=1),
            ),
        )


def test_legacy_recovery_hash_and_boolean_are_rejected() -> None:
    with pytest.raises(ValueError, match="legacy recovery hash/boolean"):
        replace(
            stage5c_support._buy_account(),
            prior_stopped=True,
            synthetic_recovery_record_hash=_hash("3"),
            synthetic_recovery_approved=True,
        )


def test_portfolio_risk_uses_pinned_decimal_context(repository_root: Path) -> None:
    _, rules = stage5c_support._rules(repository_root)
    raw = stage5b_support._case(repository_root)
    account = stage5c_support._buy_account()
    clusters = stage5c_support._clusters()
    regime = stage5c_support._regime(MarketRegime.NORMAL)
    stress = stage5c_support._stress()
    sizing = stage5c_support._sizing(raw)
    identity = stage5b_support._identity(
        "stage5c_decimal_context_target",
        as_of=stage5b_support.APPROVED_AT,
    )
    expected = evaluate_stage5_portfolio_target(
        raw,
        account,
        clusters,
        regime,
        stress,
        sizing,
        identity,
        rules,
    )

    with localcontext() as hostile_context:
        hostile_context.prec = 6
        actual = evaluate_stage5_portfolio_target(
            raw,
            account,
            clusters,
            regime,
            stress,
            sizing,
            identity,
            rules,
        )

    assert actual == expected
