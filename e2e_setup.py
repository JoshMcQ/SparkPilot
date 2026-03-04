"""Quick E2E setup: create tenant + environment + job with explicit OIDC auth."""

from __future__ import annotations

import argparse
import os
import time
from typing import Any

import httpx
import jwt

from sparkpilot.oidc import fetch_client_credentials_token


def _post(
    client: httpx.Client,
    *,
    path: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    idempotency_key: str,
) -> dict[str, Any]:
    response = client.post(
        path,
        json=payload,
        headers={**headers, "Idempotency-Key": idempotency_key},
    )
    print(f"[{path}] {response.status_code}")
    if response.status_code not in {200, 201}:
        print(response.text)
        raise RuntimeError(f"Request failed: {path} ({response.status_code})")
    return response.json()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SparkPilot E2E bootstrap helper.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--oidc-issuer", default=os.getenv("OIDC_ISSUER", ""))
    parser.add_argument("--oidc-audience", default=os.getenv("OIDC_AUDIENCE", ""))
    parser.add_argument("--oidc-client-id", default=os.getenv("OIDC_CLIENT_ID", ""))
    parser.add_argument("--oidc-client-secret", default=os.getenv("OIDC_CLIENT_SECRET", ""))
    parser.add_argument("--oidc-token-endpoint", default=os.getenv("OIDC_TOKEN_ENDPOINT", ""))
    parser.add_argument("--oidc-scope", default=os.getenv("OIDC_SCOPE", ""))
    parser.add_argument("--bootstrap-secret", default=os.getenv("BOOTSTRAP_SECRET", ""))
    parser.add_argument("--tenant-name", default="")
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--customer-role-arn", required=True)
    parser.add_argument(
        "--provisioning-mode",
        default="byoc_lite",
        choices=["byoc_lite", "full"],
    )
    parser.add_argument("--eks-cluster-arn", default="")
    parser.add_argument("--eks-namespace", default="")
    parser.add_argument("--job-name", default="SparkPi")
    parser.add_argument("--artifact-uri", default="local:///usr/lib/spark/examples/jars/spark-examples.jar")
    parser.add_argument("--artifact-digest", default="sha256:example")
    parser.add_argument("--entrypoint", default="org.apache.spark.examples.SparkPi")
    parser.add_argument("--arg", action="append", default=[], dest="job_args")
    return parser


def _oidc_token(args: argparse.Namespace) -> str:
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
        raise SystemExit("Missing required OIDC settings: " + ", ".join(missing))
    token = fetch_client_credentials_token(
        issuer=args.oidc_issuer,
        audience=args.oidc_audience,
        client_id=args.oidc_client_id,
        client_secret=args.oidc_client_secret,
        token_endpoint=args.oidc_token_endpoint or None,
        scope=args.oidc_scope or None,
    )
    return token.access_token


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


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.provisioning_mode == "byoc_lite":
        if not args.eks_cluster_arn:
            raise SystemExit("--eks-cluster-arn is required for provisioning_mode=byoc_lite.")
        if not args.eks_namespace:
            raise SystemExit("--eks-namespace is required for provisioning_mode=byoc_lite.")

    suffix = str(int(time.time()))
    tenant_name = args.tenant_name or f"Smoke Tenant {suffix}"
    access_token = _oidc_token(args)
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=30.0) as client:
        _ensure_bootstrap_admin(
            client,
            access_token=access_token,
            bootstrap_secret=args.bootstrap_secret,
        )
        tenant = _post(
            client,
            path="/v1/tenants",
            payload={"name": tenant_name},
            headers=headers,
            idempotency_key=f"tenant-{suffix}",
        )
        print(f"  tenant_id={tenant['id']}")

        environment_payload: dict[str, Any] = {
            "tenant_id": tenant["id"],
            "provisioning_mode": args.provisioning_mode,
            "region": args.region,
            "customer_role_arn": args.customer_role_arn,
            "quotas": {"max_concurrent_runs": 5, "max_vcpu": 128, "max_run_seconds": 7200},
        }
        if args.provisioning_mode == "byoc_lite":
            environment_payload["eks_cluster_arn"] = args.eks_cluster_arn
            environment_payload["eks_namespace"] = args.eks_namespace

        env_op = _post(
            client,
            path="/v1/environments",
            payload=environment_payload,
            headers=headers,
            idempotency_key=f"env-{suffix}",
        )
        env_id = env_op["environment_id"]
        print(f"  env_id={env_id}")

        job = _post(
            client,
            path="/v1/jobs",
            payload={
                "environment_id": env_id,
                "name": f"{args.job_name}-{suffix}",
                "artifact_uri": args.artifact_uri,
                "artifact_digest": args.artifact_digest,
                "entrypoint": args.entrypoint,
                "args": args.job_args or ["1000"],
                "spark_conf": {},
            },
            headers=headers,
            idempotency_key=f"job-{suffix}",
        )
        print(f"  job_id={job['id']}")

    print("\n--- IDs ---")
    print(f"TENANT_ID={tenant['id']}")
    print(f"ENV_ID={env_id}")
    print(f"JOB_ID={job['id']}")
    print("\nNext: run the provisioner, then submit a run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
