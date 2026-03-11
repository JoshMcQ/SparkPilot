# Live BYOC-lite Real AWS Proof (March 5, 2026)

This document records the March 5, 2026 live validation cycle executed against:

- EKS cluster: `sparkpilot-live-1` (`us-east-1`)
- Mode: `BYOC-lite`
- Cost controls: matrix estimate caps and explicit nodegroup scale-down at end

## Primary Success Artifact

- [artifacts/live-enterprise-matrix-20260305-044527/summary.json](../../artifacts/live-enterprise-matrix-20260305-044527/summary.json)

Key result:

- `failed_scenarios=0`
- `passed_scenarios=1`
- terminal run state: `succeeded`
- EMR job run id: `0000000375sa67p4h2n`

## What Was Validated

1. Real AWS provisioning path:
   - tenant create
   - environment create
   - EMR virtual cluster ready
2. Preflight gate execution with BYOC-lite checks and remediation messages.
3. Real run submission to EMR on EKS with CloudWatch log capture.
4. Run reconciliation to terminal `succeeded`.
5. Cost/showback surface generation for the run.

## Defects/Findings Captured During This Cycle

1. Fixed: EMR `StartJobRun` name length exceeded AWS max 64 chars.
   - Root cause: unbounded `job.name + run.id` construction.
   - Fix: deterministic length-safe name builder in [src/sparkpilot/aws_clients.py](/Users/JoshMcQueary/SparkPilot/src/sparkpilot/aws_clients.py).
   - Tests added in [tests/test_aws_clients.py](/Users/JoshMcQueary/SparkPilot/tests/test_aws_clients.py).
2. Operational failure mode validated: zero-capacity nodegroup produced scheduler `FailedScheduling`.
   - Remediated during run by temporary scale-up; reset to `desired=0` at end.
3. Workload packaging finding:
   - `local://` artifact entrypoint failed in this environment.
   - S3-hosted script entrypoint succeeded.

## Cleanup Confirmation

1. Test virtual cluster for the success run was deleted after evidence capture.
2. Nodegroup `sparkpilot-ng` restored to `min=0, desired=0, max=4`.
3. Execution-role trust policy restored to pre-run state snapshot.
