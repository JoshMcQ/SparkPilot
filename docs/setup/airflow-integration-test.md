# Airflow Integration Test Guide

This guide explains how to run the SparkPilot Airflow provider integration tests against a real Airflow 2.x deployment and a live SparkPilot API endpoint.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Apache Airflow 2.6+ | With Airflow REST API enabled (`[api] auth_backend = airflow.api.auth.backend.basic_auth`) |
| SparkPilot API endpoint | Must be reachable from the Airflow workers |
| Valid OIDC credentials | Client-credentials grant for the SparkPilot audience |
| `apache-airflow-providers-sparkpilot` | Installed in the Airflow environment |
| Python 3.11+ (local) | For running setup and validate scripts |
| `httpx`, `PyJWT` Python packages | For setup script |

---

## Environment Variables

### SparkPilot

| Variable | Required | Description |
|---|---|---|
| `SPARKPILOT_BASE_URL` | Yes | SparkPilot API base URL, e.g. `https://sparkpilot-api.example.com` |
| `SPARKPILOT_OIDC_ISSUER` | Yes | OIDC issuer URL, e.g. `https://auth.example.com` |
| `SPARKPILOT_OIDC_CLIENT_ID` | Yes | OIDC client id |
| `SPARKPILOT_OIDC_CLIENT_SECRET` | Yes | OIDC client secret |
| `SPARKPILOT_OIDC_AUDIENCE` | Yes | OIDC audience for the SparkPilot API |
| `SPARKPILOT_OIDC_TOKEN_ENDPOINT` | No | Explicit token endpoint; auto-discovered from issuer when omitted |
| `SPARKPILOT_BOOTSTRAP_SECRET` | Yes (first run) | Bootstrap secret for creating the first admin identity |

### Airflow Validation Script

| Variable | Required | Description |
|---|---|---|
| `AIRFLOW_API_BASE_URL` | Yes | Airflow REST API base URL, e.g. `http://airflow.example.com:8080` |
| `AIRFLOW_API_USERNAME` | No | Airflow basic-auth username (default: `admin`) |
| `AIRFLOW_API_PASSWORD` | Yes | Airflow basic-auth password |

---

## Step-by-Step Instructions

### Step 1 — Configure the SparkPilot Airflow connection

In Airflow, create a connection with id `sparkpilot_default` (Admin → Connections):

- **Connection type**: `sparkpilot` (or `generic`)
- **Host**: SparkPilot API hostname
- **Schema**: `https`
- **Port**: (if non-standard)
- **Login**: OIDC client id
- **Password**: OIDC client secret
- **Extra** (JSON):
  ```json
  {
    "oidc_issuer": "https://auth.example.com",
    "oidc_audience": "sparkpilot-api"
  }
  ```

### Step 2 — Create a test job

Run the setup script locally to create a tenant, environment, and test job:

```bash
export OIDC_ISSUER="$SPARKPILOT_OIDC_ISSUER"
export OIDC_AUDIENCE="$SPARKPILOT_OIDC_AUDIENCE"
export OIDC_CLIENT_ID="$SPARKPILOT_OIDC_CLIENT_ID"
export OIDC_CLIENT_SECRET="$SPARKPILOT_OIDC_CLIENT_SECRET"
export SPARKPILOT_BASE_URL="$SPARKPILOT_BASE_URL"
export BOOTSTRAP_SECRET="$SPARKPILOT_BOOTSTRAP_SECRET"

python providers/airflow/tests/integration/setup_sparkpilot_job.py
```

The script prints `SPARKPILOT_EXAMPLE_JOB_ID=<job_id>` to stdout. Export that variable:

```bash
export SPARKPILOT_EXAMPLE_JOB_ID=<job_id>
```

### Step 3 — Copy the DAG to Airflow

Copy `providers/airflow/tests/integration/airflow_integration_dag.py` to your Airflow DAGs folder. The file contains four DAGs:

| DAG id | Tests |
|---|---|
| `sparkpilot_integration_submit_wait` | Synchronous submit + wait |
| `sparkpilot_integration_deferrable` | Deferrable trigger path |
| `sparkpilot_integration_sensor` | Submit + SparkPilotRunSensor |
| `sparkpilot_integration_cancel` | Submit + SparkPilotCancelRunOperator |

### Step 4 — Trigger a DAG run

```bash
# Trigger via Airflow CLI
airflow dags trigger sparkpilot_integration_submit_wait \
  --conf '{"job_id": "'"$SPARKPILOT_EXAMPLE_JOB_ID"'"}'

# Or via the Airflow REST API
curl -X POST "$AIRFLOW_API_BASE_URL/api/v1/dags/sparkpilot_integration_submit_wait/dagRuns" \
  -u "$AIRFLOW_API_USERNAME:$AIRFLOW_API_PASSWORD" \
  -H "Content-Type: application/json" \
  -d '{"conf": {}}'
```

Note the `dag_run_id` returned by the trigger call.

### Step 5 — Validate the DAG run

```bash
export AIRFLOW_API_BASE_URL="http://airflow.example.com:8080"
export AIRFLOW_API_USERNAME="admin"
export AIRFLOW_API_PASSWORD="<password>"

python providers/airflow/tests/integration/validate_dag_run.py \
  --dag-id sparkpilot_integration_submit_wait \
  --run-id <dag_run_id> \
  --timeout 600
```

The script exits `0` on success and `1` on failure, printing:
- DAG run terminal state
- All task instance states
- XCom values (run id, state) for submit tasks

---

## Running All Four DAGs

To exercise the full provider surface, trigger all four DAGs and validate each:

```bash
for dag_id in \
    sparkpilot_integration_submit_wait \
    sparkpilot_integration_deferrable \
    sparkpilot_integration_sensor \
    sparkpilot_integration_cancel; do

  run_id=$(airflow dags trigger "$dag_id" --no-interactive 2>&1 | grep -oP '(?<=run_id: ).*')
  echo "Triggered $dag_id run_id=$run_id"

  python providers/airflow/tests/integration/validate_dag_run.py \
    --dag-id "$dag_id" \
    --run-id "$run_id" \
    --timeout 600

done
```

---

## Interpreting Results

| Exit code | Meaning |
|---|---|
| `0` | DAG run succeeded; all task instances succeeded; XCom values populated with run id and state |
| `1` | One or more failures — check the script output for details |

Common failure causes:

- **Connection error**: The `sparkpilot_default` connection in Airflow is missing or misconfigured
- **OIDC error**: Client credentials are incorrect or the OIDC token endpoint is unreachable
- **Run timeout**: The SparkPilot run took longer than `timeout_seconds` — increase the value or check cluster health
- **Cancellation failed**: The run may have reached a terminal state before the cancel request arrived — this is expected and the cancel operator handles it gracefully
