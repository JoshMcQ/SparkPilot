# Canonical Proof Ledger (2026-04-13)

This file is the canonical claim-to-evidence index for public product-surface statements.
Older or conflicting artifacts are superseded by the latest evidence rows below.

## Claim Index

| Claim surface | Status label | Latest evidence artifact | Runtime identifiers | Captured date | Supersedes |
|---|---|---|---|---|---|
| Airflow orchestrator integration executes real scheduler DAG submit + wait terminal | Available now | `artifacts/live-airflow-provider-execution-20260413-223625/` | Airflow DAG run `proof_20260413T223725Z`, SparkPilot run `611af475-1886-4980-9c7b-21fbab2df85c`, EMR job run `jr-0bb0616e5f08` | 2026-04-13 | `artifacts/live-airflow-provider-execution-20260322/` |
| Dagster orchestrator integration executes submit + wait terminal in real Dagster run | Available now | `artifacts/live-dagster-execution-20260413-225533/` | Dagster run `cd1a8c85-38dd-4c19-b191-2c31ef193761`, SparkPilot run `269683ca-a127-4191-99ce-dd1c8053b6fd`, EMR job run `jr-1cbcd5ceb1be` | 2026-04-13 | `artifacts/live-dagster-execution-20260322/` |
| Full-BYOC validation rerun against non-prod environment | In beta | `artifacts/live-full-byoc-validation-20260413-225740/` | Environment `5fa6536e-4533-43f9-905c-dce028494066`, operation `f31a8a0d-48b9-49b8-830f-aa7f7129a5a7` | 2026-04-13 | `artifacts/live-full-byoc-validation-20260311-152948/` |
| Full-BYOC blocker detail (cluster missing) | In beta | `artifacts/live-full-byoc-validation-20260413-225740/EVIDENCE_SUMMARY.md` | `eks:DescribeCluster` -> `ResourceNotFoundException` (`sparkpilot-staging-live-1`) | 2026-04-13 | n/a |
| Lake Formation FGAC checks and permission context capture | In beta | `artifacts/live-lake-formation-fgac-20260322/` | see `permissions_check.json`, `lf_permissions_grant.json` | 2026-03-22 | n/a |
| YuniKorn queue enforcement with two queue assignments | Coming soon | `artifacts/live-yunikorn-assessment-20260413-225810/` | blocker: no reachable EKS cluster, no Helm binary in execution env | 2026-04-13 | `artifacts/live-yunikorn-assessment-20260322/` |
| Interactive endpoint and notebook-style workflows | Coming soon | `artifacts/live-interactive-endpoint-20260322/` | endpoint create/describe API evidence only | 2026-03-22 | n/a |
| Databricks on AWS dispatch path | Coming soon | no new runtime proof in this cycle | n/a | 2026-04-13 | n/a |
| Apache Iceberg managed governance path | Coming soon | no runtime proof in this cycle | n/a | 2026-04-13 | n/a |
| Policy controls pre-dispatch enforcement | Coming soon | no runtime proof in this cycle | n/a | 2026-04-13 | n/a |
| Formal support SLA commitment language | Coming soon | no published support policy artifact | n/a | 2026-04-13 | n/a |

## Publishing Rules

1. Marketing text must follow this ledger.
2. If a row is blocked, claims must be downgraded to `In beta` or `Coming soon`.
3. `Available now` requires a latest artifact with runtime IDs and terminal outcomes.
4. Superseded artifacts remain for history but are not canonical proof.
