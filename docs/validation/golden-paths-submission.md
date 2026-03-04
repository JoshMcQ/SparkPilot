# Golden Path Submission: Before vs After

## Context
This example shows how a Spark job submission looks with raw EMR on EKS APIs versus SparkPilot golden-path submission.

## Before: Raw EMR on EKS submission
You must build and maintain the full payload surface (execution role, release label, Spark submit parameters, logging configuration).

```json
{
  "virtualClusterId": "vc-1234567890",
  "name": "daily-aggregation",
  "executionRoleArn": "arn:aws:iam::123456789012:role/SparkPilotEmrExecutionRole",
  "releaseLabel": "emr-7.10.0-latest",
  "jobDriver": {
    "sparkSubmitJobDriver": {
      "entryPoint": "s3://acme/jobs/daily.py",
      "entryPointArguments": ["--date", "2026-03-03"],
      "sparkSubmitParameters": "--conf spark.executor.instances=2 --conf spark.kubernetes.executor.node.selector.eks.amazonaws.com/capacityType=SPOT"
    }
  },
  "configurationOverrides": {
    "monitoringConfiguration": {
      "cloudWatchMonitoringConfiguration": {
        "logGroupName": "/sparkpilot/runs/env-123",
        "logStreamNamePrefix": "run-123/attempt-1"
      }
    }
  }
}
```

## After: SparkPilot golden-path submission
Platform team defines the profile once (`medium-spot-graviton`), and engineers submit by reference.

```http
POST /v1/jobs/{job_id}/runs
Idempotency-Key: run-20260303-1
Authorization: Bearer <oidc-access-token>
Content-Type: application/json
```

```json
{
  "golden_path": "medium-spot-graviton",
  "args": ["--date", "2026-03-03"]
}
```

## Result
- Spark config and resource shape are standardized by the golden path.
- Spot/architecture defaults are centrally maintained.
- Per-run overrides are reduced to intentional parameters (for example job args).
- Custom Spark config policy checks block unsafe Kubernetes auth/service-account overrides.
