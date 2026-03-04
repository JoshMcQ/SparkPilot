# Structured Run Diagnostics Validation

## Scope
Validation evidence for roadmap item `R14`.

## Implemented
- Pattern-based diagnostics extraction for terminal failed/timed-out/cancelled runs.
- Pattern categories:
  - `oom`
  - `shuffle_fetch_failure`
  - `s3_access_denied`
  - `schema_mismatch`
  - `timeout`
  - `spot_interruption`
- Persistent diagnostics model: `run_diagnostics`.
- Automatic extraction during reconciliation for terminal runs.
- API endpoint: `GET /v1/runs/{id}/diagnostics`.

## Test coverage
- `tests/test_diagnostics.py::test_diagnostic_pattern_matching` (parametrized fixture lines for all categories)
- `tests/test_diagnostics.py::test_reconciler_persists_diagnostics_and_api_exposes_them`

Suite result:
- `python -m pytest -q tests -p no:cacheprovider` -> `64 passed`

## Real AWS evidence (March 3, 2026)
- Database scope: `sparkpilot_e2e_20260301-203939.db`
- Artifact:
  - `artifacts/r14-realaws-20260303-120145/summary.json`
- Result:
  - `run_id=b9340884-19ba-443f-ad41-98e15942d683`
  - terminal state: `cancelled`
  - diagnostics persisted: `1`
  - detected category: `s3_access_denied`
