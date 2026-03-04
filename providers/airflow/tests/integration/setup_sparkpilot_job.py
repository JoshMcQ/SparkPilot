"""Integration-harness setup script for local docker-compose only.

This script assumes a non-production SparkPilot instance in dry-run mode.
Do not run this against live environments.
"""

from __future__ import annotations

import os
import time

import httpx
import jwt


def _discover_token_endpoint(*, issuer: str, timeout_seconds: float = 10.0) -> str:
    response = httpx.get(
        f"{issuer.rstrip('/')}/.well-known/openid-configuration",
        timeout=timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OIDC discovery response must be a JSON object.")
    endpoint = str(payload.get("token_endpoint") or "").strip()
    if not endpoint:
        raise RuntimeError("OIDC discovery response missing token_endpoint.")
    return endpoint


def _oidc_access_token() -> str:
    issuer = os.getenv("OIDC_ISSUER", "").strip()
    audience = os.getenv("OIDC_AUDIENCE", "").strip()
    client_id = os.getenv("OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("OIDC_CLIENT_SECRET", "").strip()
    token_endpoint = os.getenv("OIDC_TOKEN_ENDPOINT", "").strip()
    scope = os.getenv("OIDC_SCOPE", "").strip()

    missing = []
    if not issuer:
        missing.append("OIDC_ISSUER")
    if not audience:
        missing.append("OIDC_AUDIENCE")
    if not client_id:
        missing.append("OIDC_CLIENT_ID")
    if not client_secret:
        missing.append("OIDC_CLIENT_SECRET")
    if missing:
        raise RuntimeError("Missing required OIDC env vars: " + ", ".join(missing))

    endpoint = token_endpoint or _discover_token_endpoint(issuer=issuer)
    body: dict[str, str] = {
        "grant_type": "client_credentials",
        "audience": audience,
    }
    if scope:
        body["scope"] = scope
    response = httpx.post(
        endpoint,
        data=body,
        auth=(client_id, client_secret),
        headers={"Accept": "application/json"},
        timeout=10.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("OIDC token response must be a JSON object.")
    access_token = str(payload.get("access_token") or "").strip()
    if not access_token:
        raise RuntimeError("OIDC token response missing access_token.")
    return access_token


def _post(
    client: httpx.Client,
    *,
    path: str,
    access_token: str,
    idempotency_key: str,
    payload: dict[str, object],
) -> dict[str, object]:
    response = client.post(
        path,
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Idempotency-Key": idempotency_key,
        },
    )
    response.raise_for_status()
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


def _ensure_bootstrap_admin(client: httpx.Client, *, access_token: str) -> None:
    bootstrap_secret = (
        os.getenv("BOOTSTRAP_SECRET", "").strip()
        or os.getenv("SPARKPILOT_BOOTSTRAP_SECRET", "").strip()
    )
    if not bootstrap_secret:
        raise RuntimeError("Missing BOOTSTRAP_SECRET/SPARKPILOT_BOOTSTRAP_SECRET for first-user bootstrap.")
    subject = _token_subject(access_token)
    response = client.post(
        "/v1/user-identities",
        json={"actor": subject, "role": "admin", "active": True},
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-Bootstrap-Secret": bootstrap_secret,
        },
    )
    if response.status_code not in {200, 201}:
        raise RuntimeError(
            "Failed to ensure bootstrap admin identity: "
            f"{response.status_code} {response.text}"
        )


def _create_tenant(
    client: httpx.Client, *, access_token: str, suffix: str
) -> dict[str, object]:
    return _post(
        client,
        path="/v1/tenants",
        access_token=access_token,
        idempotency_key=f"tenant-airflow-it-{suffix}",
        payload={"name": f"Airflow Integration Tenant {suffix}"},
    )


def _create_environment(
    client: httpx.Client,
    *,
    tenant_id: str,
    access_token: str,
    suffix: str,
) -> dict[str, object]:
    return _post(
        client,
        path="/v1/environments",
        access_token=access_token,
        idempotency_key=f"env-airflow-it-{suffix}",
        payload={
            "tenant_id": tenant_id,
            "provisioning_mode": "byoc_lite",
            "region": "us-east-1",
            "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
            "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/airflow-it",
            "eks_namespace": f"sparkpilot-airflow-{suffix}",
        },
    )


def _wait_for_environment_ready(
    client: httpx.Client,
    *,
    environment_id: str,
    access_token: str,
    timeout_seconds: int = 180,
) -> dict[str, object]:
    deadline = time.time() + timeout_seconds
    while True:
        env_response = client.get(
            f"/v1/environments/{environment_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        env_response.raise_for_status()
        env = env_response.json()
        if env.get("status") == "ready":
            return env
        if time.time() >= deadline:
            raise RuntimeError(
                f"Timed out waiting for environment {environment_id} to reach ready state."
            )
        time.sleep(2)


def _create_job(
    client: httpx.Client,
    *,
    environment_id: str,
    access_token: str,
    suffix: str,
) -> dict[str, object]:
    return _post(
        client,
        path="/v1/jobs",
        access_token=access_token,
        idempotency_key=f"job-airflow-it-{suffix}",
        payload={
            "environment_id": environment_id,
            "name": f"airflow-it-job-{suffix}",
            "artifact_uri": "s3://bucket/job.py",
            "artifact_digest": "sha256:airflow-integration",
            "entrypoint": "main",
        },
    )


def main() -> int:
    base_url = os.getenv("SPARKPILOT_BASE_URL", "http://sparkpilot-api:8000").rstrip("/")
    access_token = _oidc_access_token()
    suffix = str(int(time.time()))

    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        _ensure_bootstrap_admin(client, access_token=access_token)
        tenant = _create_tenant(client, access_token=access_token, suffix=suffix)
        environment_op = _create_environment(
            client,
            tenant_id=str(tenant["id"]),
            access_token=access_token,
            suffix=suffix,
        )
        environment_id = str(environment_op["environment_id"])
        _wait_for_environment_ready(
            client,
            environment_id=environment_id,
            access_token=access_token,
        )
        job = _create_job(
            client,
            environment_id=environment_id,
            access_token=access_token,
            suffix=suffix,
        )
    print(f"SPARKPILOT_EXAMPLE_JOB_ID={job['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
