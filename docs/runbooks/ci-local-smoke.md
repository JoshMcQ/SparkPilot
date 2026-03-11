# CI Local Smoke Repro Runbook

Use this runbook to reproduce the `e2e-local-smoke` GitHub Actions job locally and collect the same diagnostics artifacts.

## Prerequisites

1. Docker Engine + Docker Compose v2.
2. Python environment with project dependencies installed:
   - `python -m pip install -e ".[dev]"`
3. Open ports `8000` and `8080` on the local machine.

## Reproduce CI Smoke Locally

From repository root:

```bash
export SMOKE_COMPOSE_BUILD=true
export SMOKE_ARTIFACT_DIR=output/ci/e2e-local-smoke-local
export SMOKE_STACK_STARTUP_ATTEMPTS=3
export SMOKE_STACK_RETRY_DELAY_SECONDS=5
export SMOKE_STACK_WAIT_TIMEOUT_SECONDS=300
export SMOKE_STACK_WAIT_POLL_SECONDS=5
export SMOKE_FLOW_ATTEMPTS=2
export SMOKE_FLOW_RETRY_DELAY_SECONDS=10
export SMOKE_FLOW_TIMEOUT_SECONDS=420
export SMOKE_PRESERVE_STACK_ON_FAILURE=true

bash scripts/smoke/run_local_stack_smoke.sh
```

On success, the smoke script tears down the stack and writes machine-readable summaries to `${SMOKE_ARTIFACT_DIR}`.
On failure with `SMOKE_PRESERVE_STACK_ON_FAILURE=true`, the stack is preserved for debugging.

## Artifacts Produced

- `local_stack_summary.json`:
  - overall status, classification, stage, retry/timing policy, and nested app-smoke summary
- `live_byoc_lite_summary.json` (or per-attempt files):
  - API-level smoke summary with classification and per-step timings
- `docker_compose_logs.txt`
- `docker_compose_ps.txt`
- `inspect_<service>.json` and `logs_<service>.txt` for key services

## Failure Classification Guide

- `infra_startup`:
  - stack startup or health-check readiness failed
  - check `docker_compose_ps.txt`, `docker_compose_logs.txt`, and API/OIDC container inspect files
- `api_auth`:
  - OIDC token bootstrap/auth failed (401/403 or token acquisition issue)
  - check OIDC service logs and `live_byoc_lite_summary.json` error/stage fields
- `run_state_timeout`:
  - run did not reach terminal success within bounded timeout
  - inspect worker logs (`logs_sparkpilot-scheduler.txt`, `logs_sparkpilot-reconciler.txt`)
- `api_request`:
  - non-auth API request failure, or a run that reaches a non-success terminal state (`failed` / `cancelled`)
  - inspect exact endpoint/stage in smoke summary

## Manual Debug Loop

1. Keep stack running:
   - `export SMOKE_PRESERVE_STACK_ON_FAILURE=true`
2. Re-run only the app-level smoke:
   - `python scripts/smoke/live_byoc_lite.py --help`
3. After debugging, clean up:
   - `docker compose down -v`
