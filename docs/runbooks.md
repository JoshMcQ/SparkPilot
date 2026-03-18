# Runbooks

See also: [Troubleshooting matrix](./troubleshooting/matrix-remediation.md) for command-focused error remediation.

## Auth Troubleshooting

1. `Unable to locate credentials`:
   - Run `python -m awscli configure`.
   - Verify with `python -m awscli sts get-caller-identity`.
2. `ModuleNotFoundError: No module named 'awscli'`:
   - Run `python -m pip install awscli`.
3. `configure list` shows `<not set>`:
   - Re-run `python -m awscli configure` and enter key/secret/region/output.
4. `AccessDenied` from AWS APIs:
   - Confirm IAM policy permissions and role trust policy.
   - Confirm requested region matches configured region.

## Provisioning Stuck

1. Check `GET /v1/provisioning-operations/{id}` for failed step.
2. Inspect `logs_uri` from operation metadata.
3. Validate customer role ARN trust/external ID.
4. Retry with a new idempotency key only after root cause is fixed.

## Full-BYOC Validation IAM Requirements

Use this when `provisioning_mode=full` is in `validating_bootstrap` or `validating_runtime`.

Bootstrap validation checks require customer role permissions:

- `emr-containers:DescribeVirtualCluster`
- `eks:DescribeCluster`
- `iam:GetOpenIDConnectProvider`
- `iam:GetRole`

Runtime validation checks additionally require:

- `iam:SimulatePrincipalPolicy`
- simulated dispatch actions: `emr-containers:StartJobRun`, `emr-containers:DescribeJobRun`, `emr-containers:CancelJobRun`
- simulated pass-role capability: `iam:PassRole` on `SPARKPILOT_EMR_EXECUTION_ROLE_ARN`

Baseline policy fragment for the customer role:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SparkPilotValidationDescribe",
      "Effect": "Allow",
      "Action": [
        "emr-containers:DescribeVirtualCluster",
        "eks:DescribeCluster",
        "iam:GetOpenIDConnectProvider",
        "iam:GetRole",
        "iam:SimulatePrincipalPolicy"
      ],
      "Resource": "*"
    },
    {
      "Sid": "SparkPilotValidationPassRole",
      "Effect": "Allow",
      "Action": "iam:PassRole",
      "Resource": "arn:aws:iam::<account-id>:role/<execution-role-name>"
    }
  ]
}
```

Notes:

- `iam:SimulatePrincipalPolicy` is required because runtime validation verifies dispatch readiness before jobs run.
- Full Terraform provisioning stages require broader permissions than this section. This section only covers bootstrap/runtime validation checks.

## Run Stuck in Accepted/Running

1. Run reconciler once:
   - `python -m sparkpilot.workers reconciler --once`
2. Confirm `emr_job_run_id` is present on run.
3. Validate CloudWatch log group and stream prefix.
4. If cancellation requested, ensure cancel dispatch audit event exists.

## Costs Page Team Selector Semantics

1. The Costs page selector is team-entity based (`/v1/teams`), not tenant-id derived.
2. Team names are passed to `/v1/costs?team=<team-name>&period=<yyyy-mm>`.
3. If no teams exist, create teams in Access first; Costs should not infer pseudo-teams from environment tenant IDs.
4. Reconciliation status per run:
   - `Reconciled`: actual cost + `cur_reconciled_at` present
   - `CUR pending`: actual cost not yet available
   - `Estimated only`: fallback estimate with no reconciled actual

## DLQ Growth

1. Alert threshold: any DLQ depth > 0 for 5m.
2. Pull failed messages and categorize:
   - retriable infra issue
   - invalid customer config
   - code regression
3. Replay only after bug/config fix is validated in staging.

## Security Incident

1. Rotate control-plane IAM keys/roles if compromise suspected.
2. Review audit trail by actor/action window.
3. Correlate AWS request IDs and CloudTrail event IDs.
4. Freeze tenant provisioning if blast radius unclear.

## Enterprise Scenario Matrix

1. Use `docs/runbooks/enterprise-matrix-real-aws.md` for matrix execution.
2. Start with strict `--max-estimated-cost-usd`.
3. Attach `artifacts/enterprise-matrix-<timestamp>/summary.json` to issue evidence.

## CI Local Smoke

1. Use `docs/runbooks/ci-local-smoke.md` to reproduce `e2e-local-smoke` locally with the same retry/timeouts as CI.
2. Collect `output/ci/e2e-local-smoke*/local_stack_summary.json` and compose logs for diagnostics.

## Live Full-BYOC Validation Proof

Use this path to capture real AWS evidence for full-BYOC validation stages.

1. Ensure runtime env vars are set:
   - `SPARKPILOT_DRY_RUN_MODE=false`
   - `SPARKPILOT_ENABLE_FULL_BYOC_MODE=true`
   - `SPARKPILOT_EMR_EXECUTION_ROLE_ARN=<execution-role-arn>`
   - `SPARKPILOT_OIDC_ISSUER`, `SPARKPILOT_OIDC_AUDIENCE`, `SPARKPILOT_OIDC_JWKS_URI`
   - `SPARKPILOT_BOOTSTRAP_SECRET`, `SPARKPILOT_CORS_ORIGINS`
2. Run:
   - `python scripts/e2e/run_full_byoc_validation_live.py --customer-role-arn <customer-role-arn> --eks-cluster-arn <eks-cluster-arn> --emr-virtual-cluster-id <virtual-cluster-id> --region <aws-region>`
3. Attach:
   - `artifacts/live-full-byoc-validation-<timestamp>/summary.json`
   - `artifacts/live-full-byoc-validation-<timestamp>/checkpoint_events.json`
   - `artifacts/live-full-byoc-validation-<timestamp>/aws_context.json`
4. Reference latest captured proof:
   - `docs/validation/live-full-byoc-validation-proof-20260311.md`
