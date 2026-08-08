"""Operator-run Stage 3B/3C read-only HTTP compatibility smoke.

The bearer token is accepted only through ``INVEST_SYSTEM_KB_BEARER_TOKEN``.
This script consumes the checked-in InvestSystem contract snapshot and never
imports or locates an InvestmentResearchKB checkout.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from invest_system.integrations.investment_research_kb import (
    KBReadOnlyHTTPClient,
    load_kb_transport_contract_snapshot,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one exact KB Release over read-only HTTP"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--allow-loopback-http", action="store_true")
    parser.add_argument("--artifact-id")
    parser.add_argument("--artifact-sha256")
    parser.add_argument("--artifact-size", type=int)
    return parser.parse_args()


def main() -> int:
    args = _arguments()
    token = os.environ.get("INVEST_SYSTEM_KB_BEARER_TOKEN")
    if not token:
        raise SystemExit("INVEST_SYSTEM_KB_BEARER_TOKEN is required")
    artifact_values = (args.artifact_id, args.artifact_sha256, args.artifact_size)
    if any(value is not None for value in artifact_values) and not all(
        value is not None for value in artifact_values
    ):
        raise SystemExit("artifact ID, SHA-256, and size must be supplied together")

    root = Path(__file__).resolve().parents[1]
    catalog = load_kb_transport_contract_snapshot(
        root / "contracts" / "providers" / "investment_research_kb" / "stage6b-transport-v1"
    )
    client = KBReadOnlyHTTPClient(
        base_url=args.base_url,
        bearer_token=token,
        catalog=catalog,
        allow_loopback_http=args.allow_loopback_http,
    )
    bundle = client.get_release_bundle(args.release_id)
    output: dict[str, object] = {
        "contract_source_commit": catalog.source_commit,
        "contract_snapshot_lock_sha256": catalog.snapshot_lock_sha256,
        "release_id": bundle.release.release_id,
        "knowledge_cutoff": bundle.release.knowledge_cutoff,
        "release_response_sha256": bundle.release.response_sha256,
        "manifest_response_sha256": bundle.manifest.response_sha256,
        "status_response_sha256": bundle.status.response_sha256,
        "current_status": bundle.status.data["current_status_event"]["status"],
        "authority_eligible": False,
        "note": "compatibility smoke only; no RunReleaseStatusConfirmation was issued",
    }
    if all(value is not None for value in artifact_values):
        artifact = client.download_artifact(
            args.release_id,
            args.artifact_id,
            expected_sha256=args.artifact_sha256,
            expected_size_bytes=args.artifact_size,
        )
        output["artifact"] = {
            "artifact_id": artifact.artifact_id,
            "size_bytes": artifact.size_bytes,
            "sha256": artifact.sha256,
        }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
