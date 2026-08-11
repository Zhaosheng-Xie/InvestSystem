"""Validate one formal KB Context Pack over public HTTPS for Stage 3D.

The credential file is read only inside this process.  The bearer token is
never accepted as a command-line argument and never enters output artifacts.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    Stage3DExpectation,
    load_kb_transport_contract_snapshot,
    validate_stage3d_http_context_pack,
)
from invest_system.models import HashDigest


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one formal KB Context Pack and Evidence closure over HTTPS"
    )
    parser.add_argument("--handoff", required=True, type=Path)
    parser.add_argument("--handoff-sha256", required=True)
    parser.add_argument("--credential-env", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--observed-at")
    return parser.parse_args()


def _credential_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise SystemExit("credential file contains an invalid line")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {"KB_BASE_URL", "KB_BEARER_TOKEN"} or key in values:
            raise SystemExit("credential file contains an unexpected or duplicate key")
        values[key] = value.strip().strip('"').strip("'")
    if set(values) != {"KB_BASE_URL", "KB_BEARER_TOKEN"} or not all(values.values()):
        raise SystemExit("credential file is incomplete")
    return values


def _observed_at(value: str | None) -> datetime:
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


def main() -> int:
    args = _arguments()
    root = Path(__file__).resolve().parents[1]
    handoff_bytes = args.handoff.read_bytes()
    expectation = Stage3DExpectation.from_handoff_bytes(
        handoff_bytes,
        expected_sha256=args.handoff_sha256,
    )
    if args.base_url != expectation.base_url:
        raise SystemExit("base URL differs from the hash-locked handoff")
    credentials = _credential_values(args.credential_env)
    token = credentials.pop("KB_BEARER_TOKEN")
    try:
        if credentials.pop("KB_BASE_URL") != args.base_url or credentials:
            raise SystemExit("credential base URL differs")
        catalog = load_kb_transport_contract_snapshot(
            root / "contracts" / "providers" / "investment_research_kb" / "stage6b-transport-v1"
        )
        client = KBReadOnlyHTTPClient(
            base_url=args.base_url,
            bearer_token=token,
            catalog=catalog,
        )
        result = validate_stage3d_http_context_pack(
            client=client,
            catalog=catalog,
            expectation=expectation,
            observed_at=_observed_at(args.observed_at),
            code_commit=args.code_commit,
            config_hash=_file_hash(root / "config" / "default.toml"),
            runtime_environment_lock_hash=_file_hash(root / "requirements.lock"),
        )
        output = {
            "acceptance": "passed",
            "authority_eligible": result.authority_eligible,
            "run_release_status_confirmation_issued": (
                result.run_release_status_confirmation_issued
            ),
            "persists_state": result.persists_state,
            "base_url": args.base_url,
            "handoff_sha256": expectation.handoff_sha256,
            "contract_source_commit": catalog.source_commit,
            "contract_snapshot_lock_sha256": catalog.snapshot_lock_sha256,
            "knowledge_cutoff": result.strategy_input_ref.to_json_value()["knowledge_cutoff"],
            "strategy_input_ref": result.strategy_input_ref.to_json_value(),
            "response_sha256": dict(result.response_sha256),
            "artifact_sha256": dict(result.artifact_sha256),
            "closure_counts": dict(result.closure_counts),
            "artifact_consumption_receipt_hash": result.receipt.receipt_hash.value,
            "provider_neutral_input_hash": result.provider_input.canonical_sha256(),
            "strategy_run_manifest": {
                "run_id": result.manifest.run_id,
                "canonical_sha256": result.manifest.canonical_sha256(),
                "code_commit": result.manifest.code_commit,
                "input_path": result.manifest.input_path,
                "validation_only": result.manifest.validation_only,
                "authorizes_positions": result.manifest.authorizes_positions,
                "authorizes_orders": result.manifest.authorizes_orders,
            },
            "observations": {
                "artifact_fetch_observation_id": result.fetch_observation.observation_id,
                "release_status_observation_id": result.status_observation.observation_id,
                "release_admission_observation_id": result.admission_observation.observation_id,
                "release_admission_status": result.admission_observation.admission_status.value,
            },
            "strategy_smoke": {
                "outcome": result.smoke.outcome.value,
                "reason_codes": list(result.smoke.reason_codes),
                "canonical_sha256": result.smoke.canonical_sha256(),
                "positive_investment_conclusion_required": (
                    result.smoke.positive_investment_conclusion_required
                ),
            },
            "note": (
                "formal Context Pack validation-only smoke; no current-status authority, "
                "business decision, position, order, or KB write"
            ),
        }
        print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    finally:
        token = ""  # noqa: F841 - explicitly release the only local token reference
        credentials.clear()


if __name__ == "__main__":
    raise SystemExit(main())
