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

