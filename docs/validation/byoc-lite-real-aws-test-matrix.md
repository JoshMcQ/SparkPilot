# BYOC-Lite Real-AWS Test Matrix (March 2, 2026)

This matrix captures executed BYOC-Lite validation scenarios across regions,
namespaces, and node-profile conditions. Evidence is stored under:

- `artifacts/e2e-20260301-203939/`
- `artifacts/e2e-20260301-203939/m9-matrix-evidence.json`

## Scope Coverage

- Regions: `us-east-1`, `us-west-2`
- Namespaces: multiple (`sparkpilot-auto-*`, `sparkpilot-ui-*`, `sparkpilot-matrix-west-*`)
- Node profile conditions:
  - `sparkpilot-ng desired=2` (capacity pressure case)
  - `sparkpilot-ng desired=3` (post-scale success case)

## Matrix

| Scenario | Region | Namespace | Node Profile | Result | Evidence | Linked Issue |
|---|---|---|---|---|---|---|
| M9-E1-CAPACITY-FAIL | `us-east-1` | `sparkpilot-auto-20260302-221746` | desired=2 | `failed` | `p8c-smoke-output.json`, `resume-scale-verify.json` | [#15](https://github.com/JoshMcQ/SparkPilot/issues/15) |
| M9-E1-CAPACITY-SUCCESS | `us-east-1` | `sparkpilot-auto-20260302-221746` | desired=3 | `succeeded` | `p8d-run-final.json`, `p8d-emr-describe.json`, `p8d-run-logs.json`, `p8d-s3-output.txt` | - |
| M9-E1-NS-COLLISION | `us-east-1` | `sparkpilot-ui-20260301-203939` | n/a | `failed_expected` | `p6b-collision-op-final.json` | [#19](https://github.com/JoshMcQ/SparkPilot/issues/19) |
| M9-W2-RUNTIME-CLUSTER-NOT-FOUND | `us-west-2` | `sparkpilot-matrix-west-20260301-203939` | n/a | `failed_expected` | `m9-west-op-initial.json`, `m9-west-op-poll-history.json`, `m9-west-op-final.json`, `m9-west-env-final.json` | [#9](https://github.com/JoshMcQ/SparkPilot/issues/9) |

## Scenario Assumptions

### M9-E1-CAPACITY-FAIL
- EKS cluster: `sparkpilot-live-1`
- Nodegroup profile at run start: desired=2
- Expectation: capacity pressure can stall executor scheduling and trigger stale failure.

### M9-E1-CAPACITY-SUCCESS
- Same cluster/namespace/inputs as prior scenario.
- Nodegroup scaled up during execution to relieve CPU pressure.
- Expectation: run reaches terminal `succeeded` with logs + S3 output.

### M9-E1-NS-COLLISION
- Existing virtual cluster already bound to namespace.
- Expectation: deterministic provisioning failure with remediation guidance.

### M9-W2-RUNTIME-CLUSTER-NOT-FOUND
- BYOC-Lite env region and EKS ARN set to `us-west-2` test path.
- Cluster name intentionally absent in that region.
- Expectation: deterministic runtime AWS error surfaced in operation message.

## Repeatable Baseline Smoke Commands

Use the validated smoke entrypoint from issue #16:

```powershell
python scripts/smoke/live_byoc_lite.py `
  --base-url http://127.0.0.1:8000 `
  --customer-role-arn <customer-role-arn> `
  --eks-cluster-arn <eks-cluster-arn> `
  --eks-namespace <unique-namespace> `
  --artifact-uri s3://<bucket>/jobs/sparkpilot_demo_job.py `
  --entrypoint sparkpilot_demo_job.py `
  --arg s3://<bucket>/input/events.json `
  --arg s3://<bucket>/output/<run-prefix>/
```

Baseline repeatability requirements:

- Use a unique namespace (or retire prior virtual cluster) per provisioning attempt.
- Ensure EMR identity mapping is present for namespace.
- Ensure node profile has sufficient CPU for driver + executor pods.
