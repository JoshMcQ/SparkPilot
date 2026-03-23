# Issue #72 — EMR Serverless Real StartJobRun Evidence

**Date:** 2026-03-22
**Status:** COMPLETE — SparkPi ran successfully on EMR Serverless (state=SUCCESS)

## Application

- **Application ID:** `00g4bj3mboofea09`
- **Name:** `sparkpilot-evidence-app`
- **ARN:** `arn:aws:emr-serverless:us-east-1:787587782916:/applications/00g4bj3mboofea09`
- **Release:** `emr-7.2.0`
- **Region:** `us-east-1`
- **Created by:** `arn:aws:iam::787587782916:user/sparkpilot-cli`
- **Lifecycle:** Created → STARTED → (jobs ran) → STOPPED → DELETED

## Job Runs

### Attempt 1 (failed — trust policy timing)
- **Job Run ID:** `00g4bj488809qo0b`
- **State:** FAILED
- **Reason:** `Could not assume runtime role arn:aws:iam::787587782916:role/SparkPilotEmrExecutionRole because it doesn't exist or isn't setup with the required trust relationship.`
- **Root cause:** The execution role trust policy was updated to include `emr-serverless.amazonaws.com` immediately before submission; IAM propagation hadn't completed.

### Attempt 2 (SUCCESS — primary evidence)
- **Job Run ID:** `00g4bj4lu4dmqg0b`
- **ARN:** `arn:aws:emr-serverless:us-east-1:787587782916:/applications/00g4bj3mboofea09/jobruns/00g4bj4lu4dmqg0b`
- **State:** SUCCESS
- **Duration:** 27 seconds
- **vCPU Hours:** 0.087
- **Memory GB Hours:** 0.347
- **SparkPi result:** `Pi is roughly 3.1438711438711437`

## Execution Role Fix

The `SparkPilotEmrExecutionRole` originally only trusted `emr-containers.amazonaws.com`.
Trust policy updated to add `emr-serverless.amazonaws.com` as principal:
```json
{
  "Effect": "Allow",
  "Principal": { "Service": "emr-serverless.amazonaws.com" },
  "Action": "sts:AssumeRole"
}
```

## S3 Logs

Logs stored at:
`s3://sparkpilot-live-787587782916-20260224203702/emr-serverless-logs/applications/00g4bj3mboofea09/jobs/00g4bj4lu4dmqg0b/`

Files:
- `SPARK_DRIVER/stdout.gz` — SparkPi result line
- `SPARK_DRIVER/stderr.gz` — Spark execution logs
- `SPARK_EXECUTOR/{1,2,3}/stderr.gz` and `stdout.gz`
- `sparklogs/eventlog_v2_00g4bj4lu4dmqg0b/` — Spark event log

## Cleanup

- Application stopped: YES
- Application deleted: YES
- EMR execution role trust policy: `emr-serverless.amazonaws.com` was added (intentional — improves role utility for future tests)

## Files

| File | Description |
|------|-------------|
| `application_state.json` | EMR Serverless application details (STARTED state) |
| `start_job_run_response.json` | StartJobRun API response for both attempts |
| `job_run_terminal_state.json` | GetJobRun response showing state=SUCCESS |
| `job_run_logs_tail.txt` | Driver stdout (Pi result) and stderr tail |
| `EVIDENCE_SUMMARY.md` | This file |
