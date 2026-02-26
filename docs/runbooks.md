# Runbooks

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

## Run Stuck in Accepted/Running

1. Run reconciler once:
   - `python -m sparkpilot.workers reconciler --once`
2. Confirm `emr_job_run_id` is present on run.
3. Validate CloudWatch log group and stream prefix.
4. If cancellation requested, ensure cancel dispatch audit event exists.

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
