# SparkPilot Execution Tracker (Day 0-30)

## Current Status

- Product MVP scaffold is implemented and tests pass (`4 passed`).
- Dry-run workflow passes end-to-end: tenant -> environment -> job -> run -> logs -> usage.
- AWS CLI is installed.
- Current blocker for live BYOC runs: AWS credentials and first customer-account role setup.

## 30-Day Outcome Targets

1. Run first real Spark job in a customer AWS account through SparkPilot.
2. Complete two design partner POCs with written success criteria.
3. Close first paying design partner at `>= $3,000/month` (target `$5,000/month`).

## Scope Guardrails

Do now:
- EMR-on-EKS only
- AWS only
- Provisioning reliability
- Observability and diagnostics
- IAM hardening + security docs
- GTM pipeline and demos

Defer until post-revenue:
- Multi-cloud
- SSO/SAML/OIDC
- Advanced cost optimization features

## Workstreams

## A. Product and Reliability

| Item | Owner | Target Date | Status | Evidence |
|---|---|---|---|---|
| BYOC-Lite environment mode (`full` vs `byoc_lite`) | Eng | Week 1 | Completed | code + tests |
| BYOC-Lite API contract updates | Eng | Week 1 | Completed | schema + API |
| BYOC-Lite provisioning path (`validating_runtime -> ready`) | Eng | Week 1 | Completed | `test_byoc_lite_environment_flow` |
| Live AWS integration test script | Eng | Week 1 | Not started | script output |
| Job failure diagnostics surfaced in UI | Eng | Week 2 | Not started | screenshot |
| Reliability run: 5+ jobs / env / 2 weeks | Eng | Week 3-4 | Not started | run report |

## B. Security and Compliance Readiness

| Item | Owner | Target Date | Status | Evidence |
|---|---|---|---|---|
| BYOC-Lite least-privilege CloudFormation template | Eng | Week 1 | Completed | `customer-bootstrap-byoc-lite.yaml` |
| Annotated IAM permission inventory | Eng | Week 1 | Not started | security doc |
| 2-page security one-pager PDF | Eng + Founder | Week 2 | In progress | template drafted |
| Incident response one-pager | Eng + Founder | Week 2 | Not started | doc link |
| Security review dry run with advisor | Founder | Week 2 | Not started | notes |

## C. GTM and Design Partner Sales

| Item | Owner | Target Date | Status | Evidence |
|---|---|---|---|---|
| ICP list (50 accounts) | Founder | Week 1 | Not started | CRM sheet |
| 10 outbound messages/day | Founder | Week 1-4 | Not started | outreach log |
| 8 qualified discovery calls by day 30 | Founder | Week 2-4 | Not started | call notes |
| Demo environment with real AWS job run | Eng + Founder | Week 2 | Not started | demo recording |
| 2-week POC criteria signed before kickoff | Founder | Week 2-4 | Not started | signed doc |
| First paid design partner (`>= $3k/mo`) | Founder | Week 4 | Not started | signed order form |

## Weekly GTM Metrics (Hard Thresholds)

1. Qualified conversations: `>= 8` cumulative by day 30.
2. Demo -> POC conversion: `>= 30%`.
3. Days from POC yes -> first run in customer account: `<= 5 business days`.

If any metric misses threshold by week-end, log a corrective action in Jira the same day.

## Day-14 Kill Check

1. Outbound volume:
   - Healthy: 60-80 messages sent
   - Kill zone: < 40 sent
2. Response rate:
   - Healthy: >= 10%
   - Kill zone: < 5%
3. Discovery calls booked:
   - Healthy: >= 4 by day 14
   - Kill zone: 0-1
4. Problem confirmation:
   - Healthy: >= 50% of calls confirm strong Spark ops pain
   - Kill zone: < 25%

Decision at day 14:
- Low execution -> execution fix.
- High execution + weak signal -> channel/ICP pivot experiments.

## POC Go/No-Go Criteria

All five must pass:

1. Environment provisioning to `ready` within 30 minutes.
2. Representative customer Spark workload succeeds with expected S3 output.
3. Status/logs/diagnostics available through SparkPilot without AWS console dependency.
4. 5+ runs over 2 weeks with `>= 90%` first-attempt success (excluding customer code bugs).
5. Security review has no unresolved blockers.

## Standard Responses to Common Objections

1. Databricks comparison:
`Run us in parallel on one workload; we keep data in your VPC and remove Databricks margin.`
2. IAM concerns:
`Use BYOC-Lite: 15 resource-scoped actions across 3 services with tagged scope.`
3. Startup risk:
`Your data plane stays in your account; if we disappear, your data and infra remain yours.`
4. Build in-house question:
`You can, but this replaces months of platform work with a managed layer now.`
5. SOC2 concern:
`Pre-SOC2 design partner package includes architecture, IAM inventory, audit trail, and incident process.`

## Daily Execution Cadence

1. 10-minute engineering review:
   - Blockers
   - Today's highest-risk task
   - Evidence that must be captured
2. 20-minute GTM review:
   - New outreach sent
   - Calls booked
   - POC stage movement
3. End-of-day log:
   - What shipped
   - What was validated
   - What proof artifact was created

