# Apache Airflow Provider: SparkPilot

`apache-airflow-providers-sparkpilot` adds first-class Airflow primitives for SparkPilot:

- `SparkPilotHook` for API interaction through Airflow connections
- `SparkPilotSubmitRunOperator` for submitting SparkPilot runs
- `SparkPilotCancelRunOperator` for cancelling in-progress runs
- `SparkPilotRunSensor` for waiting on terminal run state
- `SparkPilotRunTrigger` for deferrable waiting

`SparkPilotSubmitRunOperator` timeout parameters:
- `run_timeout_seconds`: sent to SparkPilot run submission payload.
- `timeout_seconds` / `wait_timeout_seconds`: operator wait timeout.

Minimum supported Airflow version: `2.8.0`.

## Install

```bash
pip install apache-airflow-providers-sparkpilot
```

## Airflow Connection

Create a connection with type `sparkpilot` and provide URL/token in extras:

```json
{
  "sparkpilot_url": "http://sparkpilot-api:8000",
  "token": "",
  "actor": "airflow"
}
```

If `token` is empty, unauthenticated calls are used (suitable for local/dev setups).
The hook logs a warning when no token is configured.

## Example DAG

See `examples/dags/example_sparkpilot_dag.py`.
