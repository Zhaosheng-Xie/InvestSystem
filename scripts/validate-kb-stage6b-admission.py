"""Preflight or execute one Stage 6B validation-only public-HTTPS seal.

The bearer token is accepted only through an external credential file and is
never included in output, persisted payloads, or command-line arguments.
Network access and the isolated validation store are both opt-in through
``--execute``.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    Stage3DExpectation,
    load_kb_transport_contract_snapshot,
)
from invest_system.models import HashDigest
from invest_system.stage6b_live_validation import (
    execute_stage6b_live_validation,
    prepare_stage6b_live_validation,
    read_stage6b_credential_env,
)
from invest_system.strategies.industrial_event.stage6b_validation_store import (
    Stage6BValidationStore,
)

_GIT_COMMIT_RE = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preflight or execute one isolated Stage 6B public-HTTPS validation seal"
    )
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--credential-env", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--observed-at")
    parser.add_argument("--validation-root", type=Path)
    parser.add_argument("--strategy-version", default="0.1.0")
    parser.add_argument("--random-seed", default=0, type=int)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="perform real HTTPS reads and publish an isolated validation-only seal",
    )
    return parser.parse_args()


def _timestamp(value: str | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("observed-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SystemExit("observed-at must include a UTC offset")
    return parsed.astimezone(UTC)


def _file_hash(path: Path) -> HashDigest:
    return HashDigest(algorithm="sha256", value=sha256(path.read_bytes()).hexdigest())


def _preflight_output(expectation: Stage3DExpectation) -> dict[str, object]:
    return {
        "acceptance": "preflight_passed",
        "network_requests": 0,
        "seal_created": False,
        "authority_eligible": False,
        "strategy_evaluator_calls": 0,
        "handoff_sha256": expectation.handoff_sha256,
        "base_url": expectation.base_url,
        "context_release_id": expectation.context_release_id,
        "evidence_release_id": expectation.evidence_release_id,
        "knowledge_cutoff": expectation.strategy_input_ref.to_json_value()["knowledge_cutoff"],
        "strategy_input_ref": expectation.strategy_input_ref.to_json_value(),
        "note": "strict handoff and credential preflight only; no HTTPS or state write",
    }


def main() -> int:
    args = _arguments()
    repository_root = Path(__file__).resolve().parents[1]
    expectation = Stage3DExpectation.from_handoff_bytes(
        args.handoff.read_bytes(),
        expected_sha256=args.handoff_sha256,
    )
    if args.base_url != expectation.base_url:
        raise SystemExit("base URL differs from the hash-locked handoff")
    if _GIT_COMMIT_RE.fullmatch(args.code_commit) is None:
        raise SystemExit("code-commit must be a full lowercase Git identity")
    credential_base_url, token = read_stage6b_credential_env(args.credential_env)
    try:
        if credential_base_url != args.base_url:
            raise SystemExit("credential base URL differs")
        if not args.execute:
            print(
                json.dumps(
                    _preflight_output(expectation), ensure_ascii=False, sort_keys=True, indent=2
                )
            )
            return 0
        if args.validation_root is None:
            raise SystemExit("--validation-root is required with --execute")
        catalog = load_kb_transport_contract_snapshot(
            repository_root
            / "contracts"
            / "providers"
            / "investment_research_kb"
            / "stage6b-transport-v1"
        )
        client = KBReadOnlyHTTPClient(
            base_url=args.base_url,
            bearer_token=token,
            catalog=catalog,
        )
        observed_at = _timestamp(args.observed_at)
        prepared = prepare_stage6b_live_validation(
            repository_root=repository_root,
            client=client,
            catalog=catalog,
            expectation=expectation,
            observed_at=observed_at,
            code_commit=args.code_commit,
            runtime_environment_lock_hash=_file_hash(repository_root / "requirements.lock"),
            semantic_config_hash=_file_hash(repository_root / "config" / "default.toml"),
        )
        store = Stage6BValidationStore(args.validation_root)
        result = execute_stage6b_live_validation(
            client=client,
            store=store,
            prepared=prepared,
            strategy_version=args.strategy_version,
            random_seed=args.random_seed,
            clock=lambda: datetime.now(UTC),
        )
        output = {
            "acceptance": "passed",
            "authority_eligible": result.authority_eligible,
            "validation_only": result.validation_only,
            "strategy_evaluator_calls": result.admission.strategy_evaluator_calls,
            "validation_only_confirmation_issued": True,
            "fresh_status_https_calls": result.admission.public_https_calls,
            "handoff_sha256": result.handoff_sha256,
            "base_url": args.base_url,
            "contract_source_commit": catalog.source_commit,
            "contract_snapshot_lock_sha256": catalog.snapshot_lock_sha256,
            "knowledge_cutoff": prepared.request.strategy_input_ref.to_json_value()[
                "knowledge_cutoff"
            ],
            "strategy_input_ref": prepared.request.strategy_input_ref.to_json_value(),
            "receipt_hash": prepared.receipt.receipt_hash.value,
            "closure_hash": prepared.closure.closure_hash.value,
            "content_response_sha256": dict(result.content_response_sha256),
            "content_artifact_sha256": dict(result.content_artifact_sha256),
            "fresh_status_response_sha256": dict(result.admission.response_sha256_by_release),
            "validation_seal": {
                "run_id": result.admission.seal.run_id,
                "seal_id": result.admission.seal.seal_id,
                "seal_hash": result.admission.seal.seal_hash.value,
                "envelope_hash": result.admission.seal.envelope_hash.value,
                "confirmation_hash": result.admission.seal.confirmation_hash.value,
                "commit_generation": result.admission.seal.commit_generation,
                "committed_at": result.admission.seal.to_json_value()["committed_at"],
                "status": result.admission.seal.status.value,
                "validation_only": result.admission.seal.validation_only,
                "authority_eligible": result.admission.seal.authority_eligible,
            },
            "isolated_store": {
                "storage_schema_version": "stage6b-validation-v1",
                "formal_state_modified": False,
                "formal_cache_modified": False,
            },
            "note": (
                "validation-only Stage 6B seal; no historical evaluator, holdout, "
                "position, order, broker, KB write, or funds authority"
            ),
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    finally:
        token = ""  # noqa: F841 - release the only local bearer-token reference


if __name__ == "__main__":
    raise SystemExit(main())
