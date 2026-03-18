# Structured Streaming Lifecycle Validation (Issue #12)

## Purpose
Validate SparkPilot behavior for long-running Structured Streaming workloads:

- sustained healthy `running` state with heartbeat updates
- deterministic cancellation flow
- log accessibility during runtime
- restart semantics by submitting a new run after cancellation

## Reference Workload

- Script: `scripts/e2e/reference_structured_streaming_job.py`
- Behavior: infinite `rate` source + console sink; run is expected to remain active until cancelled.

## Validation Flow

1. Submit the streaming job with a high timeout (for example `timeout_seconds=21600`).
2. Confirm run transitions to `running`.
3. Poll `GET /v1/runs/{id}` for a sustained interval and verify:
   - `state` remains `running`
   - `last_heartbeat_at` continues to refresh
4. Call `GET /v1/runs/{id}/logs` while the run is still `running` and verify logs are returned.
5. Cancel the run via `POST /v1/runs/{id}/cancel`.
6. Reconcile until terminal state is `cancelled`.
7. Submit a new run for the same job to validate restart semantics.

## Notes

- For local dry-run mode, deterministic lifecycle behavior is validated by tests and mocked EMR transitions.
- For real AWS environments, use this flow with EMR on EKS and CloudWatch log access enabled.

## Real AWS Proof (March 18, 2026)

Artifact:

- `artifacts/issue12-structured-streaming-20260317-232119/summary.json`

Run identifiers:

- environment: `871beffd-7513-48c1-8047-cce837afe9ef`
- job: `7ab7ca9f-770a-4fd8-b933-e37a0042660e`
- run1: `86b58f70-c6be-434f-b58e-80921f94494a` (EMR JobRun `0000000377uuo8q2jfv`)
- run2: `b4bae50f-53f7-4aa3-93cb-c148db0d078d` (EMR JobRun `0000000377uutqsebdc`)

Observed outcomes:

- run1 reached active lifecycle (`accepted` -> `running`) and logs were readable during runtime (`log_line_count_while_running=200`).
- cancellation moved run1 to deterministic terminal state `cancelled`.
- restart semantics validated by submitting run2 after run1 cancellation; run2 entered active lifecycle and also converged to `cancelled` after explicit cancel.
