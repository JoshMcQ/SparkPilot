from __future__ import annotations

from datetime import UTC, datetime
import json
import uuid

import httpx
import typer

from sparkpilot.oidc import OIDCValidationError, fetch_client_credentials_token

app = typer.Typer(help="SparkPilot CLI")


def _client(base_url: str) -> httpx.Client:
    return httpx.Client(base_url=base_url.rstrip("/"), timeout=30.0)


def _print_json(payload: object) -> None:
    typer.echo(json.dumps(payload, indent=2, default=str))


def _idem(value: str | None) -> str:
    return value or uuid.uuid4().hex


_TOKEN_CACHE: dict[str, tuple[str, float]] = {}


def _env(*names: str) -> str:
    import os

    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return ""


def _oidc_access_token() -> str:
    issuer = _env("OIDC_ISSUER", "SPARKPILOT_OIDC_ISSUER")
    audience = _env("OIDC_AUDIENCE", "SPARKPILOT_OIDC_AUDIENCE")
    client_id = _env("OIDC_CLIENT_ID", "SPARKPILOT_OIDC_CLIENT_ID")
    client_secret = _env("OIDC_CLIENT_SECRET", "SPARKPILOT_OIDC_CLIENT_SECRET")
    token_endpoint = _env("OIDC_TOKEN_ENDPOINT", "SPARKPILOT_OIDC_TOKEN_ENDPOINT")
    scope = _env("OIDC_SCOPE", "SPARKPILOT_OIDC_SCOPE")

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
        raise typer.BadParameter(
            "Missing required OIDC CLI env vars: " + ", ".join(missing)
        )

    cache_key = "|".join([issuer, audience, client_id, token_endpoint, scope])
    cached = _TOKEN_CACHE.get(cache_key)
    if cached:
        token_value, expires_at = cached
        if expires_at > datetime.now(UTC).timestamp() + 30:
            return token_value

    try:
        token = fetch_client_credentials_token(
            issuer=issuer,
            audience=audience,
            client_id=client_id,
            client_secret=client_secret,
            token_endpoint=token_endpoint or None,
            scope=scope or None,
        )
    except OIDCValidationError as exc:
        raise typer.BadParameter(f"OIDC token acquisition failed: {exc}") from exc
    except httpx.HTTPError as exc:
        raise typer.BadParameter(f"OIDC token endpoint request failed: {exc}") from exc
    _TOKEN_CACHE[cache_key] = (token.access_token, token.expires_at_epoch_seconds)
    return token.access_token


def _headers(
    idempotency_key: str | None = None,
    *,
    include_idempotency: bool = False,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {_oidc_access_token()}",
    }
    if include_idempotency:
        headers["Idempotency-Key"] = _idem(idempotency_key)
    return headers


@app.command("tenant-create")
def tenant_create(
    name: str = typer.Option(..., "--name"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    with _client(base_url) as c:
        r = c.post(
            "/v1/tenants",
            json={"name": name},
            headers=_headers(idempotency_key, include_idempotency=True),
        )
        r.raise_for_status()
        _print_json(r.json())


@app.command("env-create")
def env_create(
    tenant_id: str = typer.Option(..., "--tenant-id"),
    customer_role_arn: str = typer.Option(..., "--customer-role-arn"),
    provisioning_mode: str = typer.Option("full", "--provisioning-mode"),
    eks_cluster_arn: str | None = typer.Option(None, "--eks-cluster-arn"),
    eks_namespace: str | None = typer.Option(None, "--eks-namespace"),
    region: str = typer.Option("us-east-1", "--region"),
    warm_pool_enabled: bool = typer.Option(False, "--warm-pool-enabled"),
    max_concurrent_runs: int = typer.Option(10, "--max-concurrent-runs"),
    max_vcpu: int = typer.Option(256, "--max-vcpu"),
    max_run_seconds: int = typer.Option(7200, "--max-run-seconds"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    payload = {
        "tenant_id": tenant_id,
        "provisioning_mode": provisioning_mode,
        "region": region,
        "customer_role_arn": customer_role_arn,
        "eks_cluster_arn": eks_cluster_arn,
        "eks_namespace": eks_namespace,
        "warm_pool_enabled": warm_pool_enabled,
        "quotas": {
            "max_concurrent_runs": max_concurrent_runs,
            "max_vcpu": max_vcpu,
            "max_run_seconds": max_run_seconds,
        },
    }
    with _client(base_url) as c:
        r = c.post(
            "/v1/environments",
            json=payload,
            headers=_headers(idempotency_key, include_idempotency=True),
        )
        r.raise_for_status()
        _print_json(r.json())


@app.command("env-list")
def env_list(
    tenant_id: str | None = typer.Option(None, "--tenant-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    params = {"tenant_id": tenant_id} if tenant_id else None
    with _client(base_url) as c:
        r = c.get("/v1/environments", params=params, headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("env-get")
def env_get(
    environment_id: str = typer.Option(..., "--environment-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    with _client(base_url) as c:
        r = c.get(f"/v1/environments/{environment_id}", headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("env-preflight")
def env_preflight(
    environment_id: str = typer.Option(..., "--environment-id"),
    run_id: str | None = typer.Option(None, "--run-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    params = {"run_id": run_id} if run_id else None
    with _client(base_url) as c:
        r = c.get(f"/v1/environments/{environment_id}/preflight", params=params, headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("op-get")
def op_get(
    operation_id: str = typer.Option(..., "--operation-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    with _client(base_url) as c:
        r = c.get(f"/v1/provisioning-operations/{operation_id}", headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("job-create")
def job_create(
    environment_id: str = typer.Option(..., "--environment-id"),
    name: str = typer.Option(..., "--name"),
    artifact_uri: str = typer.Option(..., "--artifact-uri"),
    artifact_digest: str = typer.Option(..., "--artifact-digest"),
    entrypoint: str = typer.Option(..., "--entrypoint"),
    args: list[str] = typer.Option([], "--arg"),
    spark_conf: list[str] = typer.Option([], "--conf", help="k=v"),
    retry_max_attempts: int = typer.Option(1, "--retry-max-attempts"),
    timeout_seconds: int = typer.Option(7200, "--timeout-seconds"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    conf_dict: dict[str, str] = {}
    for item in spark_conf:
        key, _, value = item.partition("=")
        if not key or not value:
            raise typer.BadParameter(f"Invalid --conf value: {item}. Use key=value format.")
        conf_dict[key] = value
    payload = {
        "environment_id": environment_id,
        "name": name,
        "artifact_uri": artifact_uri,
        "artifact_digest": artifact_digest,
        "entrypoint": entrypoint,
        "args": args,
        "spark_conf": conf_dict,
        "retry_max_attempts": retry_max_attempts,
        "timeout_seconds": timeout_seconds,
    }
    with _client(base_url) as c:
        r = c.post(
            "/v1/jobs",
            json=payload,
            headers=_headers(idempotency_key, include_idempotency=True),
        )
        r.raise_for_status()
        _print_json(r.json())


@app.command("run-submit")
def run_submit(
    job_id: str = typer.Option(..., "--job-id"),
    args: list[str] = typer.Option([], "--arg"),
    spark_conf: list[str] = typer.Option([], "--conf", help="k=v"),
    driver_vcpu: int = typer.Option(1, "--driver-vcpu"),
    driver_memory_gb: int = typer.Option(4, "--driver-memory-gb"),
    executor_vcpu: int = typer.Option(2, "--executor-vcpu"),
    executor_memory_gb: int = typer.Option(8, "--executor-memory-gb"),
    executor_instances: int = typer.Option(2, "--executor-instances"),
    timeout_seconds: int | None = typer.Option(None, "--timeout-seconds"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    conf_dict: dict[str, str] = {}
    for item in spark_conf:
        key, _, value = item.partition("=")
        if not key or not value:
            raise typer.BadParameter(f"Invalid --conf value: {item}. Use key=value format.")
        conf_dict[key] = value
    payload = {
        "args": args or None,
        "spark_conf": conf_dict or None,
        "requested_resources": {
            "driver_vcpu": driver_vcpu,
            "driver_memory_gb": driver_memory_gb,
            "executor_vcpu": executor_vcpu,
            "executor_memory_gb": executor_memory_gb,
            "executor_instances": executor_instances,
        },
        "timeout_seconds": timeout_seconds,
    }
    with _client(base_url) as c:
        r = c.post(
            f"/v1/jobs/{job_id}/runs",
            json=payload,
            headers=_headers(idempotency_key, include_idempotency=True),
        )
        r.raise_for_status()
        _print_json(r.json())


@app.command("run-list")
def run_list(
    tenant_id: str | None = typer.Option(None, "--tenant-id"),
    state: str | None = typer.Option(None, "--state"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    params = {}
    if tenant_id:
        params["tenant_id"] = tenant_id
    if state:
        params["state"] = state
    with _client(base_url) as c:
        r = c.get("/v1/runs", params=params, headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("run-get")
def run_get(
    run_id: str = typer.Option(..., "--run-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    with _client(base_url) as c:
        r = c.get(f"/v1/runs/{run_id}", headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("run-cancel")
def run_cancel(
    run_id: str = typer.Option(..., "--run-id"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
    idempotency_key: str | None = typer.Option(None, "--idempotency-key"),
) -> None:
    with _client(base_url) as c:
        r = c.post(
            f"/v1/runs/{run_id}/cancel",
            headers=_headers(idempotency_key, include_idempotency=True),
        )
        r.raise_for_status()
        _print_json(r.json())


@app.command("run-logs")
def run_logs(
    run_id: str = typer.Option(..., "--run-id"),
    limit: int = typer.Option(200, "--limit"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    with _client(base_url) as c:
        r = c.get(f"/v1/runs/{run_id}/logs", params={"limit": limit}, headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


@app.command("usage-get")
def usage_get(
    tenant_id: str = typer.Option(..., "--tenant-id"),
    from_ts: str | None = typer.Option(None, "--from-ts", help="ISO timestamp"),
    to_ts: str | None = typer.Option(None, "--to-ts", help="ISO timestamp"),
    base_url: str = typer.Option("http://localhost:8000", "--base-url"),
) -> None:
    def _parse(ts: str | None) -> str | None:
        if not ts:
            return None
        value = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()

    params = {"tenant_id": tenant_id}
    parsed_from = _parse(from_ts)
    parsed_to = _parse(to_ts)
    if parsed_from:
        params["from_ts"] = parsed_from
    if parsed_to:
        params["to_ts"] = parsed_to
    with _client(base_url) as c:
        r = c.get("/v1/usage", params=params, headers=_headers())
        r.raise_for_status()
        _print_json(r.json())


if __name__ == "__main__":
    app()
