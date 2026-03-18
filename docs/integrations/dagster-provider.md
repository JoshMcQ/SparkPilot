# Dagster Provider: SparkPilot

Date: March 11, 2026

## Package

- Package path: `providers/dagster`
- Package name: `dagster-sparkpilot`
- Import root: `dagster_sparkpilot`

## Included Components

- `SparkPilotClient`
  - OIDC client-credentials token retrieval with optional issuer discovery.
  - Token caching and automatic refresh on `401`.
  - Retry/backoff for transient transport and API status failures.
  - API lifecycle methods: submit run, get run, wait for terminal, cancel run.
- `sparkpilot_resource`
  - Dagster resource config schema for SparkPilot connectivity and auth.
  - Lazy `SparkPilotClient` initialization per process.
- Dagster ops
  - `sparkpilot_submit_run_op`
  - `sparkpilot_wait_for_run_op`
  - `sparkpilot_cancel_run_op`
- Dagster assets
  - `sparkpilot_submit_asset`
  - `sparkpilot_wait_asset`
  - `sparkpilot_cancel_asset`
  - `sparkpilot_run_lifecycle_asset` (submit + wait)

## Error Mapping

- Transient SparkPilot errors map to Dagster retry semantics (`RetryRequested`).
- Permanent SparkPilot errors map to Dagster failure semantics (`Failure`).
- Terminal run failures (`failed`, `cancelled`, `timed_out`) raise `SparkPilotRunFailedError`.

## Config Requirements

Required resource config:

- `base_url`
- `oidc_issuer`
- `oidc_audience`
- `oidc_client_id`
- `oidc_client_secret`

Optional resource config:

- `oidc_token_endpoint`
- `oidc_scope`
- `timeout_seconds` (default `30`)
- `request_retries` (default `2`)
- `request_backoff_seconds` (default `1.0`)

## Example Definitions

- `providers/dagster/examples/definitions.py`
  - `sparkpilot_submit_wait_job` for submit + wait flow
  - `sparkpilot_submit_cancel_job` for submit + cancel flow
  - `sparkpilot_run_lifecycle_asset` for asset materialization flow

## Local Development Runbook

1. Install package in editable mode:
   - `pip install -e providers/dagster`
2. Start SparkPilot local stack:
   - `docker compose up --build`
3. Start Dagster dev server:
   - `dagster dev -m providers.dagster.examples.definitions`
4. Launch `sparkpilot_submit_wait_job` with run config that includes:
   - `resources.sparkpilot.config` values for API + OIDC.
   - `ops.sparkpilot_submit_run_op.config.job_id`.
5. Inspect run metadata output for `id`, `status`, `duration_seconds`, and `log_url`.

## Troubleshooting

- `SparkPilot API request failed ... 401`:
  - Verify `oidc_audience`, client id/secret, and token endpoint.
- `SparkPilot API request failed ... 403`:
  - Service principal lacks SparkPilot API authorization.
- `run_id is required ...`:
  - Provide `run_id` in wait/cancel op config or wire submit output.
- `Timed out waiting for run ...`:
  - Increase `timeout_seconds` or inspect SparkPilot run diagnostics.
- Retry exhaustion:
  - Increase `request_retries` and `request_backoff_seconds`.
