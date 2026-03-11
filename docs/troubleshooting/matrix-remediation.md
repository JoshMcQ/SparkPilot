# Troubleshooting Matrix

Use this table for common setup and runtime failures.

## Auth and Identity

1. Symptom: `401 Missing or invalid bearer token`
   - Command:
     ```powershell
     python -m scripts.e2e.run_enterprise_matrix --help
     ```
   - Remediation: provide valid OIDC issuer/audience/client credentials.
2. Symptom: `403 Unknown or inactive actor`
   - Command:
     ```powershell
     curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/v1/user-identities
     ```
   - Remediation: create/activate identity and verify tenant/team assignment.

## Environment and Provisioning

1. Symptom: environment never reaches `ready`
   - Command:
     ```powershell
     python -m sparkpilot.workers provisioning --once
     ```
   - Remediation: inspect provisioning operation `message` and `logs_uri`; correct IAM or cluster references.
2. Symptom: BYOC-lite preflight `config.eks_namespace` or OIDC trust failures
   - Command:
     ```powershell
     python -m awscli iam get-role --role-name SparkPilotByocLiteRoleAdmin
     ```
   - Remediation: fix namespace uniqueness and trust policy conditions.

## Run Dispatch and Reconcile

1. Symptom: run stuck in `accepted`
   - Command:
     ```powershell
     python -m sparkpilot.workers reconciler --once
     ```
   - Remediation: verify EMR job run ID, role permissions, and CloudWatch log pointers.
2. Symptom: run blocked by policy/budget
   - Command:
     ```powershell
     curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/v1/environments/<env-id>/preflight
     ```
   - Remediation: follow check-level remediation text and resubmit.

## Cost and Showback

1. Symptom: `/v1/costs` returns no rows
   - Command:
     ```powershell
     curl -H "Authorization: Bearer <token>" "http://127.0.0.1:8000/v1/costs?team=<tenant-id>&period=YYYY-MM"
     ```
   - Remediation: run at least one successful workload in the target billing period and verify CUR reconciliation job.
2. Symptom: estimated cost only, no actual CUR cost
   - Command:
     ```powershell
     python -m sparkpilot.workers finops --once
     ```
   - Remediation: validate Athena/CUR table access and billing-period alignment.
