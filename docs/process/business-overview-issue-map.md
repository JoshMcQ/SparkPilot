# Business Overview Issue Map

Last updated: March 16, 2026

## Purpose

This map links the strategic and validation gaps from [business-overview.md](../business-overview.md) to executable GitHub issues.

Closure rule for every mapped issue:
- Keep issue open until explicit live-AWS evidence is attached.
- Evidence must include artifacts and concrete runtime identifiers where applicable (`operation_id`, `environment_id`, `run_id`, `EMR JobRun ID`, query IDs, scheduler run IDs).

## A) Immediate Trust Gaps (Part 9: "What Needs to Happen")

| Business Gap | Primary Issue(s) | Parent/Anchor |
|---|---|---|
| Second operator must run end-to-end on real AWS | #65 | #37 |
| Misconfigured environment preflight must fail deterministically in real AWS | #66 | #37 |
| CUR reconciliation must run against real CUR tables | #67 | #33 |
| Airflow provider must work in real scheduler runtime | #68 | #36 |
| OIDC must work with real IdP(s) | #69 | #35 |
| Isolation boundaries must be explicit and reviewable | #70 | #35, #15 |
| Baseline product value metrics from real runs | #71 | #37, #33, #39 |

## B) Security and Auth Hardening

| Gap | Issue(s) | Parent/Anchor |
|---|---|---|
| Remove localStorage bearer token risk + tighten CSP | #58 | #35, #15 |
| CSP `connect-src` allowlist for external OIDC issuer/token origins | #59 | #35, #15 |
| Throttle JWKS forced refresh on invalid signatures | #60 | #15, #35 |
| OpenAPI docs must expose bearer security scheme (`/docs` Authorize button) | Pending GH issue (local fix in `src/sparkpilot/api.py`) | #35, #37 |
| Local auth bootstrap commands must avoid clipboard token corruption path | Pending GH issue (script/UX hardening follow-up) | #37 |

## C) Dagster Integration Hardening

| Gap | Issue(s) | Parent/Anchor |
|---|---|---|
| Stop broad fallback masking runtime/import failures | #61 | #46 |
| Map discovery/token HTTP failures to domain errors | #62 | #46 |
| Strict client interface validation + dedupe config normalization | #63 | #46 |

## D) Productization and Maintainability

| Gap | Issue(s) | Parent/Anchor |
|---|---|---|
| CSS architecture maintainability split | #64 | #7 |
| Configurable policy engine for workload contracts | #39 | Core strategic gap |

## E) Backend Expansion (Part 7 Roadmap)

| Expansion Track | Issue(s) | Notes |
|---|---|---|
| EMR Serverless backend | #72 | AWS TAM expansion with lower customer K8s burden |
| EMR on EC2 backend | #73 | Follow-on AWS backend expansion |
| Databricks on AWS backend | #74 | Large Spark workload surface on AWS |

## F) Existing Roadmap Backlog Still Open

These remain active and should be sequenced against the new map above:
- Full BYOC progression: #25, #26, #27, #28, #29, #30
- Platform and reliability tracks: #33, #34, #35, #36, #37
- Enterprise and scale tracks: #38, #39, #41, #42, #46, #47, #48, #51, #52, #53, #54, #55, #56, #57

## G) UI Workflow and Operator UX Gaps (Live Testing)

| Gap | Issue(s) | Notes |
|---|---|---|
| Retry/delete lifecycle controls for failed environments | #77 | Needed for iterative real-AWS validation loops |
| Environment create should show live provisioning progress | #78 | Avoid manual refresh loops |
| Run submission must only allow `ready` environments | #79 | Prevent avoidable preflight failures |
| Run diagnostics should expose explicit selected-run context | #80 | Reduce ambiguity in diagnostics flow |
| Access page workflow and validation clarity | #81 | Lower operator onboarding friction |
| Job template args/spark_conf multiline UX | #82 | Fix editing ergonomics and parse clarity |
| Run-submit spacing/readability polish | #83 | Improve high-frequency action area |
| Mock OIDC key rotation token invalidation recovery UX | #84 | Clear refresh path after OIDC restart |

## Recommended Execution Order

1. Trust proof first: #65, #66, #67, #68, #69
2. Security hardening in parallel: #58, #59, #60
3. Product-core gap: #39
4. Metric proof and packaging: #70, #71
5. Expansion after proof: #72, #73, #74
