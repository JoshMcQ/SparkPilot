# Live Full-BYOC Validation Proof (March 11, 2026)

This record captures a non-prod real AWS full-mode provisioning operation that executed the full-BYOC validation stages (`validating_bootstrap`, `validating_runtime`) with real AWS API checks and checkpoint evidence.

## Primary Artifacts

- [artifacts/live-full-byoc-validation-20260311-152948/summary.json](../../artifacts/live-full-byoc-validation-20260311-152948/summary.json)
- [artifacts/live-full-byoc-validation-20260311-152948/checkpoint_events.json](../../artifacts/live-full-byoc-validation-20260311-152948/checkpoint_events.json)
- [artifacts/live-full-byoc-validation-20260311-152948/aws_context.json](../../artifacts/live-full-byoc-validation-20260311-152948/aws_context.json)
- [artifacts/live-full-byoc-validation-20260311-152948/cleanup.json](../../artifacts/live-full-byoc-validation-20260311-152948/cleanup.json)

## Run Context

- AWS account: `787587782916`
- Region: `us-east-1`
- Provisioning mode: `full`
- Customer role: `arn:aws:iam::787587782916:role/SparkPilotByocLiteRoleAdmin`
- EKS cluster: `arn:aws:eks:us-east-1:787587782916:cluster/sparkpilot-live-1`
- EMR virtual cluster: `ioumxnbq2vyd1u748l5lgwyyv`
- Execution role: `arn:aws:iam::787587782916:role/SparkPilotEmrExecutionRole`

## Evidence Highlights

1. Operation completed with `environment_status=ready` and `operation_state=ready`.
2. Checkpoint attempt counts include:
   - `validating_bootstrap=1`
   - `validating_runtime=1`
3. Bootstrap validation evidence includes:
   - EMR virtual cluster reference checks
   - OIDC association validation
   - execution-role trust policy validation
4. Runtime validation evidence includes:
   - virtual cluster `RUNNING` state validation
   - runtime preflight readiness checks
   - dispatch permissions simulation and `iam:PassRole` readiness checks

## Cleanup

The proof-run virtual cluster was deleted after evidence capture.

- `state_after_delete`: `TERMINATED`
- Evidence: `cleanup.json` in the artifact directory above.

## Notes

This proof run intentionally seeded the full-BYOC checkpoint at `provisioning_emr` to execute live bootstrap/runtime validation checks without reprovisioning network/EKS infrastructure during evidence collection.
