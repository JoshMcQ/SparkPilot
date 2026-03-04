# BYOC-Lite Multi-Tenant Isolation Invariants (Issue #14)

Date: March 2, 2026

## Scope

This document captures control-plane isolation invariants validated by automated tests for concurrent multi-tenant workloads.

## Isolation Invariants

1. Run listing isolation:
   - `GET /v1/runs?tenant_id=<tenant>` only returns runs owned by that tenant.
2. Run metadata isolation:
   - each run retains its own `environment_id`, log group, and log stream prefix.
   - one tenant's run metadata never references another tenant's environment.
3. Log proxy role isolation:
   - `GET /v1/runs/{id}/logs` resolves `role_arn` from the run's own environment.
   - log group/stream passed to CloudWatch proxy matches the requesting run only.
4. Audit tenant attribution:
   - `run.dispatched` audit events record the correct `tenant_id` per run.

## Automated Coverage

Implemented in:

- `tests/test_api.py::test_multi_tenant_concurrent_runs_enforce_isolation_invariants`

Test characteristics:

- creates two tenants and two environments with distinct role ARNs.
- submits one run per tenant before scheduling (same scheduler cycle).
- asserts run-list filtering, metadata separation, log-proxy call separation, and audit tenant attribution.

Run command:

```powershell
python -m pytest -q tests/test_api.py -k multi_tenant_concurrent_runs_enforce_isolation_invariants -p no:cacheprovider
```

Current result: pass.

## Real-AWS Evidence Update (March 3, 2026)

Artifacts under `artifacts/e2e-20260301-203939/`:

- `p14-setup.json`
- `p14-provisioning-final.json`
- `p14-env-adopted-vc.json`
- `p14-nodegroup-poll.json`
- `p14-run3-poll-history.json`
- `p14-run3-a-logs.txt`
- `p14-run3-b-logs.txt`
- `p14-real-concurrency-summary.json`
- `issue14-real-aws-evidence-note.md`

Observed on real AWS:

- Two tenant-isolated runs were concurrently in `running` state (`concurrent_running_samples=161`).
- Distinct run metadata, EMR job IDs, log groups, and stream prefixes were preserved per tenant/environment.
- Driver logs show namespace isolation (`sparkpilot-smoke-*` vs `sparkpilot-ui-*`) with no cross-namespace leakage.

Outstanding blocker:

- Runs did not reach terminal success due repeated executor scheduling starvation (`Initial job has not accepted any resources`), so issue #14 remains open pending terminal-pass evidence.

## Terminal-Pass Evidence (March 3, 2026)

A follow-up real-AWS run closed the remaining gap:

- run A `07090210-fea0-48c5-b405-81cae667aff5`: platform `succeeded`, EMR `COMPLETED`
- run B `b725a5fc-6a4f-48c6-a72b-6b5a1093cede`: platform `succeeded`, EMR `COMPLETED`

Evidence:

- `artifacts/e2e-20260301-203939/p14-run4-summary.json`
- `artifacts/e2e-20260301-203939/p14-run4-final.json`
- `artifacts/e2e-20260301-203939/p14-run4-emr-a.json`
- `artifacts/e2e-20260301-203939/p14-run4-emr-b.json`
- `artifacts/e2e-20260301-203939/p14-run4-runs-tenant-a.json`
- `artifacts/e2e-20260301-203939/p14-run4-runs-tenant-b.json`
- `artifacts/e2e-20260301-203939/p14-run4-usage-tenant-a.json`
- `artifacts/e2e-20260301-203939/p14-run4-usage-tenant-b.json`
