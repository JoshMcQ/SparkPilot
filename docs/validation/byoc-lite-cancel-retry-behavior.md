# BYOC-Lite Cancellation and Dispatch Retry Validation (Issue #13)

Date: March 2, 2026

## Scope

This note documents deterministic behavior added for:

- transient dispatch retry scheduling
- non-transient dispatch failure handling
- cancellation semantics from `queued`, `accepted`, and `running`

## Dispatch Retry Semantics

- Retry applies only to transient dispatch errors.
- Transient classification uses AWS error codes and network-style timeout tokens.
- When retry is scheduled:
  - run state returns to `queued`
  - `attempt` increments by 1
  - audit event `run.dispatch_retry_scheduled` is written
- When retries are exhausted or error is non-transient:
  - run transitions to `failed`
  - audit event `run.dispatch_failed` is written

## Cancellation Semantics

- `queued` and `dispatching`: cancellation is immediate (`state=cancelled`).
- `accepted` and `running`: `cancellation_requested=true`, reconciler dispatches EMR cancel and converges to terminal state.
- audit event `run.cancel.dispatched` confirms cancel dispatch from reconciler path.

## Automated Test Coverage

Validated with:

- `test_scheduler_retries_transient_dispatch_failure`
- `test_scheduler_fails_non_transient_dispatch_without_retry`
- `test_scheduler_exhausts_transient_dispatch_retries`
- `test_cancel_run_from_queued_is_immediate`
- `test_cancel_run_from_accepted_transitions_to_cancelled`
- `test_cancel_run_from_running_transitions_to_cancelled`

Command:

```powershell
python -m pytest -q tests -p no:cacheprovider
```

Result: `37 passed`.
