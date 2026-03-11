#!/usr/bin/env python
from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
import sys
import time
import uuid
from typing import Any

import httpx
import jwt

from sparkpilot.oidc import fetch_client_credentials_token


TERMINAL_STATES = {"succeeded", "failed", "cancelled", "timed_out"}


class SmokeFailure(RuntimeError):
    def __init__(self, *, classification: str, stage: str, message: str):
        super().__init__(message)
        self.classification = classification
        self.stage = stage


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
        raise SmokeFailure(
            classification="api_auth",
            stage="oidc_token",
            message="Missing required OIDC settings: " + ", ".join(missing),
        )
    try:
        token = fetch_client_credentials_token(
            issuer=args.oidc_issuer,
            audience=args.oidc_audience,
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            token_endpoint=args.oidc_token_endpoint or None,
            scope=args.oidc_scope or None,
        )
    except Exception as exc:  # noqa: BLE001
        raise SmokeFailure(
            classification="api_auth",
            stage="oidc_token",
            message=f"Failed to fetch OIDC token: {exc}",
        ) from None
    return token.access_token


def _request_json(
    client: httpx.Client,
    *,
    method: str,
    path: str,
    stage: str,
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
        classification = "api_auth" if response.status_code in {401, 403} else "api_request"
        raise SmokeFailure(
            classification=classification,
            stage=stage,
            message=f"{method} {path} failed ({response.status_code}): {response.text}",
        )
    return response.json()


def _token_subject(access_token: str) -> str:
    payload = jwt.decode(
        access_token,
        options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
    )
    if not isinstance(payload, dict):
        raise SmokeFailure(
            classification="api_auth",
            stage="oidc_token_claims",
            message="OIDC access token payload is not a JSON object.",
        )
    subject = str(payload.get("sub") or "").strip()
    if not subject:
        raise SmokeFailure(
            classification="api_auth",
            stage="oidc_token_claims",
            message="OIDC access token is missing 'sub' claim.",
        )
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
        raise SmokeFailure(
            classification="api_auth" if response.status_code in {401, 403} else "api_request",
            stage="bootstrap_admin",
            message=(
                "Failed to create bootstrap admin identity: "
                f"{response.status_code} {response.text}"
            ),
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
            stage="wait_operation",
            access_token=access_token,
        )
        state = op.get("state")
        if state == "ready":
            return op
        if state == "failed":
            raise SmokeFailure(
                classification="infra_startup",
                stage="wait_operation",
                message=f"Provisioning operation failed: {op.get('message')}",
            )
        time.sleep(poll_seconds)
    raise SmokeFailure(
        classification="infra_startup",
        stage="wait_operation",
        message=f"Timed out waiting for operation {operation_id} to become ready.",
    )


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
            stage="wait_run",
            access_token=access_token,
        )
        state = run.get("state")
        if state in TERMINAL_STATES:
            return run
        time.sleep(poll_seconds)
    raise SmokeFailure(
        classification="run_state_timeout",
        stage="wait_run",
        message=f"Timed out waiting for run {run_id} to reach a terminal state.",
    )


def _record_timing(timings: dict[str, float], key: str, started_at: float) -> None:
    timings[key] = round(time.perf_counter() - started_at, 3)


def _write_summary(path: str, summary: dict[str, Any]) -> None:
    destination = str(path or "").strip()
    if not destination:
        return
    with open(destination, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")


def _classify_exception(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, SmokeFailure):
        return exc.classification, exc.stage
    return "unexpected", "unknown"


def _classify_terminal_run_state(state: str) -> tuple[str, str]:
    normalized = str(state or "").strip().lower()
    if normalized == "timed_out":
        return "run_state_timeout", "wait_run"
    return "api_request", "run_terminal_state"


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
    parser.add_argument("--summary-path", default="", help="Optional JSON summary output path.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    started_at_perf = time.perf_counter()
    timings: dict[str, float] = {}
    summary: dict[str, Any] = {
        "summary_version": 2,
        "base_url": args.base_url,
        "started_at": _now_iso(),
        "timings_seconds": timings,
        "classification": "in_progress",
        "stage": "starting",
    }

    exit_code = 1
    try:
        step_started = time.perf_counter()
        spark_conf = _parse_conf(args.conf)
        _record_timing(timings, "parse_config", step_started)

        step_started = time.perf_counter()
        access_token = _oidc_access_token(args)
        _record_timing(timings, "fetch_oidc_token", step_started)

        with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
            step_started = time.perf_counter()
            _ensure_bootstrap_admin(
                client,
                access_token=access_token,
                bootstrap_secret=args.bootstrap_secret,
            )
            _record_timing(timings, "bootstrap_admin", step_started)

            step_started = time.perf_counter()
            tenant = _request_json(
                client,
                method="POST",
                path="/v1/tenants",
                stage="create_tenant",
                access_token=access_token,
                body={"name": args.tenant_name},
                idempotent=True,
            )
            _record_timing(timings, "create_tenant", step_started)
            summary["tenant_id"] = tenant["id"]

            step_started = time.perf_counter()
            op = _request_json(
                client,
                method="POST",
                path="/v1/environments",
                stage="create_environment",
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
            _record_timing(timings, "create_environment", step_started)
            summary["environment_id"] = op["environment_id"]
            summary["operation_id"] = op["id"]

            step_started = time.perf_counter()
            op_ready = _wait_for_operation_ready(
                client,
                operation_id=op["id"],
                access_token=access_token,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.wait_timeout_seconds,
            )
            _record_timing(timings, "wait_provisioning_operation", step_started)
            summary["operation_state"] = op_ready["state"]

            step_started = time.perf_counter()
            preflight = _request_json(
                client,
                method="GET",
                path=f"/v1/environments/{op['environment_id']}/preflight",
                stage="fetch_preflight",
                access_token=access_token,
            )
            _record_timing(timings, "fetch_preflight", step_started)
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
                raise SmokeFailure(
                    classification="infra_startup",
                    stage="preflight",
                    message="Preflight failed. Aborting run submission.",
                )

            step_started = time.perf_counter()
            job = _request_json(
                client,
                method="POST",
                path="/v1/jobs",
                stage="create_job",
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
            _record_timing(timings, "create_job", step_started)
            summary["job_id"] = job["id"]

            step_started = time.perf_counter()
            run = _request_json(
                client,
                method="POST",
                path=f"/v1/jobs/{job['id']}/runs",
                stage="submit_run",
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
            _record_timing(timings, "submit_run", step_started)
            summary["run_id"] = run["id"]
            summary["initial_run_state"] = run["state"]

            step_started = time.perf_counter()
            final_run = _wait_for_run_terminal(
                client,
                run_id=run["id"],
                access_token=access_token,
                poll_seconds=args.poll_seconds,
                timeout_seconds=args.wait_timeout_seconds,
            )
            _record_timing(timings, "wait_run_terminal", step_started)
            summary["final_run_state"] = final_run["state"]
            summary["emr_job_run_id"] = final_run.get("emr_job_run_id")
            summary["run_error"] = final_run.get("error_message")
            if final_run["state"] != "succeeded":
                classification, stage = _classify_terminal_run_state(str(final_run["state"]))
                raise SmokeFailure(
                    classification=classification,
                    stage=stage,
                    message=f"Run ended in non-success terminal state: {final_run['state']}",
                )

            step_started = time.perf_counter()
            logs = _request_json(
                client,
                method="GET",
                path=f"/v1/runs/{run['id']}/logs",
                stage="fetch_logs",
                access_token=access_token,
                params={"limit": args.log_limit},
            )
            _record_timing(timings, "fetch_logs", step_started)
            summary["log_group"] = logs.get("log_group")
            summary["log_stream_prefix"] = logs.get("log_stream_prefix")
            summary["log_line_count"] = len(logs.get("lines", []))

        summary["classification"] = "success"
        summary["stage"] = "completed"
        exit_code = 0
    except Exception as exc:  # noqa: BLE001
        classification, stage = _classify_exception(exc)
        summary["classification"] = classification
        summary["stage"] = stage
        summary["error"] = str(exc)
    finally:
        summary["completed_at"] = _now_iso()
        summary["duration_seconds"] = round(time.perf_counter() - started_at_perf, 3)
        _write_summary(args.summary_path, summary)
        if exit_code == 0:
            print(json.dumps(summary, indent=2))
        else:
            print(json.dumps(summary, indent=2), file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
