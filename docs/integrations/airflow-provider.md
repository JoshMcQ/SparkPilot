# Airflow Provider: SparkPilot

Date: March 3, 2026

## Package

- Provider package path: `providers/airflow`
- Package name: `apache-airflow-providers-sparkpilot`
- Entry point: `apache_airflow_provider -> airflow.providers.sparkpilot.get_provider_info:get_provider_info`

## Included Primitives

- `SparkPilotHook`
  - Resolves SparkPilot URL/token/actor from Airflow connection extras.
  - Supports transient/permanent error classification.
- `SparkPilotSubmitRunOperator`
  - Submits a SparkPilot run in `golden_path` mode or raw config mode.
  - Uses `run_timeout_seconds` for SparkPilot run timeout and `timeout_seconds`/`wait_timeout_seconds` for Airflow wait timeout.
  - Supports synchronous polling and deferrable trigger pattern.
  - Returns XCom metadata: `id`, `status`, `cost_usd_micros`, `duration_seconds`, `log_url`.
- `SparkPilotCancelRunOperator`
  - Requests cancellation of an in-progress SparkPilot run.
  - Succeeds silently if the run is already in a terminal state.
  - Supports optional `wait_for_completion` polling until terminal state.
  - Returns XCom metadata: `id`, `status`, `duration_seconds`, `log_url`.
- `SparkPilotRunSensor`
  - Waits for terminal run states and pushes terminal metadata to XCom.
- `SparkPilotRunTrigger`
  - Async trigger for deferrable wait.
  - Event contract includes `status` and `transient` fields; non-success events are retryable only when `transient=true`.

## Connection Setup

Create Airflow connection `sparkpilot_default` with extras:

```json
{
  "sparkpilot_url": "http://sparkpilot-api:8000",
  "token": "<required-bearer-token>",
  "actor": "airflow"
}
```

`token` is required by default. If you intentionally need anonymous access for a local test harness, set `allow_unauthenticated=True` on the hook/operator.

## Example DAG

- `providers/airflow/examples/dags/example_sparkpilot_dag.py`

## Docker-Compose Integration Harness

- Compose file: `providers/airflow/docker-compose.integration.yml`
- Uses PostgreSQL for concurrent API/worker writes in integration runs.
- SparkPilot API/worker images include `psycopg[binary]` at build time (no runtime pip installs per container).
- Host integration test (opt-in): `tests/test_airflow_provider_integration.py`
- Run manually:

```bash
SPARKPILOT_RUN_AIRFLOW_COMPOSE=1 python -m pytest -q tests/test_airflow_provider_integration.py -p no:cacheprovider
```
