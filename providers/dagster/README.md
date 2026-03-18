# Dagster Integration: SparkPilot

`dagster-sparkpilot` provides Dagster-native primitives for SparkPilot run lifecycle orchestration:

- OIDC-authenticated API client with retry/backoff and transient/permanent error mapping.
- Dagster resource for centralized SparkPilot connectivity config.
- Ops and assets for submit, wait/poll, and cancel.
- Example Dagster definitions for end-to-end run lifecycle execution.

## Install

```bash
pip install dagster-sparkpilot
```

For local development from this repository:

```bash
pip install -e providers/dagster
```

## SparkPilot Resource Config

Configure the `sparkpilot` resource with:

- `base_url` (required): SparkPilot API URL, for example `http://sparkpilot-api:8000`
- `oidc_issuer` (required): OIDC issuer URL
- `oidc_audience` (required): audience accepted by SparkPilot API
- `oidc_client_id` (required): client credentials id
- `oidc_client_secret` (required): client credentials secret
- `oidc_token_endpoint` (optional): explicit token endpoint; if omitted discovery is used
- `oidc_scope` (optional): scope string for token request
- `timeout_seconds` (default `30`)
- `request_retries` (default `2`)
- `request_backoff_seconds` (default `1.0`)

Example resource config:

```yaml
resources:
  sparkpilot:
    config:
      base_url: "http://sparkpilot-api:8000"
      oidc_issuer: "https://issuer.example.com"
      oidc_audience: "sparkpilot-api"
      oidc_client_id: "dagster-client"
      oidc_client_secret: {"env": "SPARKPILOT_OIDC_CLIENT_SECRET"}
      request_retries: 3
      request_backoff_seconds: 2.0
```

## Ops

- `sparkpilot_submit_run_op`
  - Config includes `job_id`, optional `golden_path`, `args`, `spark_conf`, `requested_resources`, `run_timeout_seconds`, `idempotency_key`.
  - Returns normalized run metadata with `id`, `status`, `duration_seconds`, `cost_usd_micros`, `log_url`.
- `sparkpilot_wait_for_run_op`
  - Polls until terminal state.
  - Accepts run id from config or upstream submit metadata.
- `sparkpilot_cancel_run_op`
  - Requests cancel and optionally waits for terminal state.
  - Accepts run id from config or upstream submit metadata.

## Assets

- `sparkpilot_submit_asset`
- `sparkpilot_wait_asset`
- `sparkpilot_cancel_asset`
- `sparkpilot_run_lifecycle_asset` (submit + wait in one asset)

## Example Definitions

See `examples/definitions.py` for:

- `sparkpilot_submit_wait_job`: submit and wait for terminal completion.
- `sparkpilot_submit_cancel_job`: submit and request cancellation.
- `sparkpilot_run_lifecycle_asset`: end-to-end asset-based lifecycle.

## Local Run

1. Start local SparkPilot stack (`docker compose up --build` from repo root).
2. Export resource secrets (`SPARKPILOT_OIDC_CLIENT_SECRET`, etc.).
3. Run Dagster with your definitions module:

```bash
dagster dev -m providers.dagster.examples.definitions
```

4. Materialize `sparkpilot_run_lifecycle_asset` or launch one of the sample jobs.

## Troubleshooting

- `401 Unauthorized`:
  - OIDC client id/secret mismatch, expired secret, or wrong audience.
  - Verify token endpoint and `oidc_audience`.
- `403 Forbidden`:
  - Token is valid but not authorized for the SparkPilot API scope/policies.
- `404 Not Found` for run or job:
  - Check `job_id`/`run_id` correctness and tenant isolation context.
- Retry exhaustion / transient errors:
  - Increase `request_retries` and `request_backoff_seconds`.
  - Validate connectivity between Dagster runtime and SparkPilot API/OIDC issuer.
- Run terminal failure (`failed`, `cancelled`, `timed_out`):
  - Inspect run diagnostics/log URI from returned metadata.
