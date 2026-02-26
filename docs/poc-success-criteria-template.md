# SparkPilot POC Success Criteria (Template)

Account:
POC start date:
POC end date:
POC duration: 2 weeks
Customer technical lead (required):
Customer executive sponsor (recommended):
SparkPilot owner:

## Objective

Validate that SparkPilot can provision and operate Spark workloads in the customer's AWS account with acceptable reliability and observability.

## Success Criteria

| # | Criterion | Target | Result | Pass/Fail | Evidence |
|---|---|---|---|---|---|
| 1 | Environment provisioning | `POST /v1/environments` reaches `ready` within 30 minutes |  |  |  |
| 2 | Job execution | Representative customer Spark workload succeeds and writes expected output to customer S3 |  |  |  |
| 3 | Observability | Status, driver/executor logs, and diagnostics available in SparkPilot UI/API without AWS console |  |  |  |
| 4 | Reliability | 5+ jobs over POC, `>= 90%` first-attempt success (excluding customer code bugs) |  |  |  |
| 5 | Security review | Security team has no unresolved blocking objections |  |  |  |

## Go/No-Go Rule

- `Go`: all 5 criteria pass.
- `No-Go`: any criterion fails.

## Participation Requirements

1. Technical lead is mandatory and owns deployment, test execution, and feedback.
2. Executive sponsor should join kickoff and debrief and own purchase decision if POC succeeds.
3. A shared support channel (email or Slack) is established before day 1.

## Notes and Remediation

- If any criterion fails, include root cause and concrete remediation plan with owner/date.
