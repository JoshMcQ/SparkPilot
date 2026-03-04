#!/usr/bin/env python
"""Run enterprise E2E matrix scenarios against a live SparkPilot API."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import os
from pathlib import Path
import sys

from sparkpilot.oidc import fetch_client_credentials_token
from sparkpilot.e2e_matrix import MatrixRunOptions, SparkPilotApiClient, load_matrix_config, run_matrix


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Execute an enterprise scenario matrix against SparkPilot and write "
            "evidence artifacts for each scenario."
        )
    )
    parser.add_argument("--manifest", required=True, help="Path to JSON matrix manifest.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--oidc-issuer", default=os.getenv("OIDC_ISSUER", ""))
    parser.add_argument("--oidc-audience", default=os.getenv("OIDC_AUDIENCE", ""))
    parser.add_argument("--oidc-client-id", default=os.getenv("OIDC_CLIENT_ID", ""))
    parser.add_argument("--oidc-client-secret", default=os.getenv("OIDC_CLIENT_SECRET", ""))
    parser.add_argument("--oidc-token-endpoint", default=os.getenv("OIDC_TOKEN_ENDPOINT", ""))
    parser.add_argument("--oidc-scope", default=os.getenv("OIDC_SCOPE", ""))
    parser.add_argument("--actor", default="enterprise-matrix-runner")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--wait-timeout-seconds", type=int, default=3600)
    parser.add_argument("--max-estimated-cost-usd", type=float, default=None)
    parser.add_argument("--allow-over-budget", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--logs-limit", type=int, default=200)
    parser.add_argument(
        "--artifacts-dir",
        default="artifacts",
        help="Base artifact directory. A timestamped subdirectory is created for each run.",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    if not manifest_path.exists():
        print(f"Manifest not found: {manifest_path}", file=sys.stderr)
        return 2

    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    artifacts_dir = (Path(args.artifacts_dir) / f"enterprise-matrix-{timestamp}").resolve()

    missing = []
    if not args.oidc_issuer:
        missing.append("--oidc-issuer or OIDC_ISSUER")
    if not args.oidc_audience:
        missing.append("--oidc-audience or OIDC_AUDIENCE")
    if not args.oidc_client_id:
        missing.append("--oidc-client-id or OIDC_CLIENT_ID")
    if not args.oidc_client_secret:
        missing.append("--oidc-client-secret or OIDC_CLIENT_SECRET")
    if missing:
        print("Missing required OIDC settings: " + ", ".join(missing), file=sys.stderr)
        return 2

    try:
        config = load_matrix_config(manifest_path)
        token = fetch_client_credentials_token(
            issuer=args.oidc_issuer,
            audience=args.oidc_audience,
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            token_endpoint=args.oidc_token_endpoint or None,
            scope=args.oidc_scope or None,
        )
        client = SparkPilotApiClient(base_url=args.base_url, access_token=token.access_token)
        options = MatrixRunOptions(
            default_actor=args.actor,
            poll_seconds=args.poll_seconds,
            wait_timeout_seconds=args.wait_timeout_seconds,
            max_estimated_cost_usd=args.max_estimated_cost_usd,
            allow_over_budget=args.allow_over_budget,
            fail_fast=args.fail_fast,
            logs_limit=args.logs_limit,
        )
        summary = run_matrix(
            client=client,
            config=config,
            options=options,
            artifacts_dir=artifacts_dir,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Matrix execution failed: {exc}", file=sys.stderr)
        return 1

    failed = int(summary.get("failed_scenarios", 0))
    print(f"Artifacts: {artifacts_dir}")
    print(
        "Summary: "
        f"matrix={summary.get('matrix_name')} "
        f"executed={summary.get('total_scenarios_executed')} "
        f"passed={summary.get('passed_scenarios')} "
        f"failed={failed}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
