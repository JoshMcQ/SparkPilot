#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import sys
import time
import uuid

import httpx
import jwt

from sparkpilot.oidc import fetch_client_credentials_token


TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _parse_conf(items: list[str]) -> dict[str, str]:
    conf: dict[str, str] = {}
    for item in items:
        key, sep, value = item.partition("=")
        if not sep or not key or not value:
            raise ValueError(f"Invalid --conf value '{item}'. Expected key=value.")
        conf[key] = value
    return conf


def _oidc_access_token(args: argparse.Namespace) -> str:
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
        raise ValueError("Missing required OIDC settings: " + ", ".join(missing))
    token = fetch_client_credentials_token(
        issuer=args.oidc_issuer,
        audience=args.oidc_audience,
        client_id=args.oidc_client_id,
        client_secret=args.oidc_client_secret,
        token_endpoint=args.oidc_token_endpoint or None,
        scope=args.oidc_scope or None,
    )
    return token.access_token


def _request_json(
    client: httpx.Client,
    *,
    method: str,
    path: str,
    access_token: str,
    body: dict | None = None,
    params: dict | None = None,
    idempotent: bool = False,
) -> dict:
    headers = {"Authorization": f"Bearer {access_token}"}
    if idempotent:
        headers["Idempotency-Key"] = uuid.uuid4().hex
    response = client.request(method, path, headers=headers, json=body, params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed ({response.status_code}): {response.text}")
    return response.json()


def _token_subject(access_token: str) -> str:
    payload = jwt.decode(
        access_token,
        options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
    )
    if not isinstance(payload, dict):
        raise RuntimeError("OIDC access token payload is not a JSON object.")
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise RuntimeError("OIDC access token is missing 'sub' claim.")
    return subject


def _ensure_bootstrap_admin(
    client: httpx.Client,
    *,
    access_token: str,
    bootstrap_secret: str,
) -> None:
    if not bootstrap_secret.strip():
        return
    subject = _token_subject(access_token)
    response = client.post(
        "/v1/user-identities",
        json={"actor": subject, "role": "admin", "active": True},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Bootstrap-Secret": bootstrap_secret.strip(),
        },
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            "Failed to create bootstrap admin identity: "
            f"{response.status_code} {response.text}"
        )


def _wait_for_operation_ready(
    client: httpx.Client,
    *,
    operation_id: str,
    access_token: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        op = _request_json(
            client,
            method="GET",
            path=f"/v1/provisioning-operations/{operation_id}",
            access_token=access_token,
        )
        state = op.get("state")
        if state == "ready":
            return op
        if state == "failed":
            raise RuntimeError(f"Provisioning operation failed: {op.get('message')}")
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for operation {operation_id} to become ready.")


def _wait_for_run_terminal(
    client: httpx.Client,
    *,
    run_id: str,
    access_token: str,
    poll_seconds: int,
    timeout_seconds: int,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        run = _request_json(
            client,
            method="GET",
            path=f"/v1/runs/{run_id}",
            access_token=access_token,
        )
        state = run.get("state")
        if state in TERMINAL_STATES:
            return run
        time.sleep(poll_seconds)
    raise TimeoutError(f"Timed out waiting for run {run_id} to reach a terminal state.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an app-level BYOC-Lite smoke flow against SparkPilot API.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--oidc-issuer", default=os.getenv("OIDC_ISSUER", ""))
    parser.add_argument("--oidc-audience", default=os.getenv("OIDC_AUDIENCE", ""))
    parser.add_argument("--oidc-client-id", default=os.getenv("OIDC_CLIENT_ID", ""))
    parser.add_argument("--oidc-client-secret", default=os.getenv("OIDC_CLIENT_SECRET", ""))
    parser.add_argument("--oidc-token-endpoint", default=os.getenv("OIDC_TOKEN_ENDPOINT", ""))
    parser.add_argument("--oidc-scope", default=os.getenv("OIDC_SCOPE", ""))
    parser.add_argument("--bootstrap-secret", default=os.getenv("BOOTSTRAP_SECRET", ""))
    parser.add_argument("--tenant-name", default=f"Smoke Tenant {_now_iso()}")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--customer-role-arn", required=True)
    parser.add_argument("--eks-cluster-arn", required=True)
    parser.add_argument("--eks-namespace", required=True)
    parser.add_argument("--job-name", default=f"live-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}")
    parser.add_argument("--artifact-uri", required=True)
    parser.add_argument("--artifact-digest", default="sha256:smoke")
    parser.add_argument("--entrypoint", required=True)
    parser.add_argument("--arg", action="append", default=[])
    parser.add_argument("--conf", action="append", default=[], help="key=value")
    parser.add_argument("--driver-vcpu", type=int, default=1)
    parser.add_argument("--driver-memory-gb", type=int, default=2)
    parser.add_argument("--executor-vcpu", type=int, default=1)
    parser.add_argument("--executor-memory-gb", type=int, default=2)
    parser.add_argument("--executor-instances", type=int, default=1)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--wait-timeout-seconds", type=int, default=1800)
    parser.add_argument("--log-limit", type=int, default=200)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    try:
        spark_conf = _parse_conf(args.conf)
        access_token = _oidc_access_token(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    summary: dict[str, object] = {
        "base_url": args.base_url,
        "started_at": _now_iso(),
    }

    try:
        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
            _ensure_bootstrap_admin(
                client,
                access_token=access_token,
                bootstrap_secret=args.bootstrap_secret,
            )
            tenant = _request_json(
                client,
                method="POST",
                path="/v1/tenants",
                access_token=access_token,
                body={"name": args.tenant_name},
                idempotent=True,
            )
            summary["tenant_id"] = tenant["id"]

            op = _request_json(
                client,
                method="POST",
                path="/v1/environments",
                access_token=access_token,
                body={
                    "tenant_id": tenant["id"],
                    "provisioning_mode": "byoc_lite",
                    "region": args.region,
                    "customer_role_arn": args.customer_role_arn,
                    "eks_cluster_arn": args.eks_cluster_arn,
                    "eks_namespace": args.eks_namespace,
                    "quotas": {"max_concurrent_runs": 10, "max_vcpu": 256, "max_run_seconds": args.timeout_seconds},
                },
                idempotent=True,
            )
            summary["environment_id"] = op["environment_id"]
            summary["operation_id"] = op["id"]

            op_ready = _wait_for_operation_ready(
                client,
                operation_id=op["id"],
                access_token=access_token,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.wait_timeout_seconds,
            )
            summary["operation_state"] = op_ready["state"]

            preflight = _request_json(
                client,
                method="GET",
                path=f"/v1/environments/{op['environment_id']}/preflight",
                access_token=access_token,
            )
            summary["preflight_ready"] = preflight["ready"]
            summary["preflight_summary"] = [
                {
                    "code": item["code"],
                    "status": item["status"],
                    "message": item["message"],
                }
                for item in preflight["checks"]
            ]
            if not preflight["ready"]:
                print(json.dumps(summary, indent=2), file=sys.stderr)
                raise RuntimeError("Preflight failed. Aborting run submission.")

            job = _request_json(
                client,
                method="POST",
                path="/v1/jobs",
                access_token=access_token,
                body={
                    "environment_id": op["environment_id"],
                    "name": args.job_name,
                    "artifact_uri": args.artifact_uri,
                    "artifact_digest": args.artifact_digest,
                    "entrypoint": args.entrypoint,
                    "args": args.arg,
                    "spark_conf": spark_conf,
                    "retry_max_attempts": 1,
                    "timeout_seconds": args.timeout_seconds,
                },
                idempotent=True,
            )
            summary["job_id"] = job["id"]

            run = _request_json(
                client,
                method="POST",
                path=f"/v1/jobs/{job['id']}/runs",
                access_token=access_token,
                body={
                    "requested_resources": {
                        "driver_vcpu": args.driver_vcpu,
                        "driver_memory_gb": args.driver_memory_gb,
                        "executor_vcpu": args.executor_vcpu,
                        "executor_memory_gb": args.executor_memory_gb,
                        "executor_instances": args.executor_instances,
                    },
                    "timeout_seconds": args.timeout_seconds,
                },
                idempotent=True,
            )
            summary["run_id"] = run["id"]
            summary["initial_run_state"] = run["state"]

            final_run = _wait_for_run_terminal(
                client,
                run_id=run["id"],
                access_token=access_token,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.wait_timeout_seconds,
            )
            summary["final_run_state"] = final_run["state"]
            summary["emr_job_run_id"] = final_run.get("emr_job_run_id")
            summary["run_error"] = final_run.get("error_message")

            logs = _request_json(
                client,
                method="GET",
                path=f"/v1/runs/{run['id']}/logs",
                access_token=access_token,
                params={"limit": args.log_limit},
            )
            summary["log_group"] = logs.get("log_group")
            summary["log_stream_prefix"] = logs.get("log_stream_prefix")
            summary["log_line_count"] = len(logs.get("lines", []))

        summary["completed_at"] = _now_iso()
        print(json.dumps(summary, indent=2))
        return 0 if summary.get("final_run_state") == "succeeded" else 1
    except Exception as exc:  # noqa: BLE001
        summary["completed_at"] = _now_iso()
        summary["error"] = str(exc)
        print(json.dumps(summary, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
