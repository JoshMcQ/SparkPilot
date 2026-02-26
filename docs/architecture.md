# SparkPilot Architecture

## Control Plane

- FastAPI API (`src/sparkpilot/api.py`)
- Workers (`src/sparkpilot/workers.py`)
  - `provisioner`: environment operation state machine
  - `scheduler`: queued run dispatch to EMR on EKS
  - `reconciler`: EMR state convergence and usage recording
- Postgres/SQLite metadata layer
- Idempotency records for mutating requests
- Audit event stream

## Data Plane (Customer AWS Account)

- VPC + private EKS endpoint
- Managed node groups
- EMR virtual cluster per SparkPilot environment namespace
- IRSA job execution roles
- CloudWatch log destinations

Provisioning modes:

- `full`: SparkPilot provisions tenant runtime infrastructure.
- `byoc_lite`: customer provides existing EKS cluster ARN + namespace; SparkPilot manages EMR virtual cluster and runs.

Known-good endpoint profile validated during provisioning:

- `ec2`, `ecr.api`, `ecr.dkr`, `s3`, `logs`, `sts`, `eks`, `eks-auth`, `elasticloadbalancing`

## State Machines

Provisioning operation:

`queued -> validating_bootstrap -> provisioning_network -> provisioning_eks -> provisioning_emr -> validating_runtime -> ready|failed`

Run lifecycle:

`queued -> dispatching -> accepted -> running -> succeeded|failed|cancelled|timed_out`

## Idempotency

- `Idempotency-Key` required on mutating endpoints.
- Request body fingerprint is persisted with key+scope.
- Replays return original response.
- Mismatched body with same key returns `409`.

## Quotas

Environment quotas:

- `max_concurrent_runs`
- `max_vcpu`
- `max_run_seconds`

Quota checks run before creating a new run.

## Logging

- Deterministic log group: `/{prefix}/{environment_id}`
- Deterministic stream prefix: `{run_id}/attempt-{attempt}`
- `GET /v1/runs/{run_id}/logs` proxies CloudWatch log output server-side.
