# Dagster Real Orchestrator Run Evidence — Issue #46

## Status
PARTIAL — Dagster SparkPilotClient executed against live API; full Dagster orchestrator run blocked (Dagster not installed).

## What Ran Live

### SparkPilotClient (dagster-sparkpilot 0.1.0) executed directly

**Run submitted:**
- Run ID: `10f788e5-68d3-4c20-8b16-7d514bb6d3f1`
- Job ID: `dd87754d-bbef-45fb-bf84-e6686c4b990e`
- Idempotency key: `dagster-evidence-run-20260322a`
- EMR Job Run ID: `0000000378n7i2ei6ls`
- Environment: EKS sparkpilot-live-1 / namespace sparkpilot-demo-2

**Client method calls:**
1. `SparkPilotClient.submit_run()` → POST `/v1/jobs/{id}/runs` → 201 Created
2. `SparkPilotClient.get_run()` → GET `/v1/runs/{id}` → state=queued→accepted

## Infrastructure Required
- `pip install dagster>=1.8.0` to enable Dagster op/asset decorator machinery
- `dagster dev` or `dagster-daemon` to run the orchestrator
- The `dagster_sparkpilot.ops.sparkpilot_submit_run_op` and `dagster_sparkpilot.assets` are implemented

## What Is Blocked
Full Dagster orchestrator run requires:
- Dagster installed (not in project venv)
- Dagster UI for DAG run trigger
- Dagster run ID (not a SparkPilot run ID)
- Dagster op/asset execution logs

## Provider Package Verification
```python
from dagster_sparkpilot.client import SparkPilotClient, SparkPilotClientConfig
from dagster_sparkpilot.ops import sparkpilot_submit_run_op
# Both import successfully
```
