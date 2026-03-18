# Second-Operator Real-AWS End-to-End Pilot (March 18, 2026)

Issue: #65

This run captures a non-author/operator execution of the full BYOC-lite loop against live AWS with `SPARKPILOT_DRY_RUN_MODE=false`.

## Primary Artifact

- `artifacts/issue65-second-operator-20260317-230206/summary.json`

## Runtime IDs

- `tenant_id`: `ad7ead0a-b02b-4f46-9eb3-2b28c5062a46`
- `environment_id`: `871beffd-7513-48c1-8047-cce837afe9ef`
- `operation_id`: `0ba5114e-7f2c-42fe-a4c4-c07da1705d46`
- `job_id`: `8ff9ec49-d8f9-4fb0-ae4e-295f25b2ded6`
- `run_id`: `71f150ce-37da-4940-95db-e43f10222a09`
- EMR JobRun ID: `0000000377usjctefps`

## Outcome

- Provisioning reached `operation_state=ready`.
- Preflight reached `preflight_ready=true`.
- Run reached terminal `final_run_state=succeeded`.
- CloudWatch log capture returned `log_line_count=198`.

## Blocker Observed and Follow-Up

An initial run using a brand-new namespace failed at provisioning with:

- `LimitExceeded` on `iam:UpdateAssumeRolePolicy`
- Message: `Cannot exceed quota for ACLSizePerRole: 2048`

Failure artifact:

- `artifacts/issue65-second-operator-20260317-230121/summary.json`

Related follow-up track:

- #20 (execution-role trust policy automation/remediation path)

## Acceptance Mapping

- End-to-end flow by non-author operator: `pass`
- Evidence with concrete runtime IDs: `pass`
- Blockers documented with follow-up: `pass`
