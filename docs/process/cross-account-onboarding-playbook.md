# Cross-Account Onboarding Playbook (AWS Pattern Baseline)

Date: 2026-03-18

## Goal
Define the SparkPilot customer onboarding pattern for cross-account access using AWS STS AssumeRole + external ID guardrails.

## AWS-Recommended Baseline

Primary references:
- STS AssumeRole API: https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRole.html
- AWS Security Blog (External ID / confused deputy mitigation): https://aws.amazon.com/blogs/security/how-to-use-external-id-when-granting-access-to-your-aws-resources/
- AWS APN Blog (secure external ID usage): https://aws.amazon.com/blogs/apn/securely-using-external-id-for-accessing-aws-accounts-owned-by-others/

## Onboarding Flow (customer-facing)

1. **Customer enters AWS account metadata**
   - account ID, preferred region, EKS cluster ARN, namespace intent.

2. **SparkPilot generates unique external ID**
   - one external ID per customer tenant.
   - stored tenant-scoped; never shared between customers.

3. **Customer creates cross-account role in target account**
   - trust policy principal: SparkPilot control account role ARN.
   - trust policy condition: `sts:ExternalId == <tenant-specific-external-id>`.
   - permissions policy: least-privilege action set for BYOC-Lite diagnostics/dispatch.

4. **Customer submits role ARN to SparkPilot**
   - SparkPilot performs STS assume-role probe (`GetCallerIdentity`).
   - if denied, return exact remediation commands/policy statements.

5. **Preflight verification chain**
   - STS identity
   - IAM simulation (`StartJobRun`, `DescribeJobRun`, `CancelJobRun`, `eks:DescribeCluster`, `iam:PassRole`)
   - EKS cluster/OIDC verification
   - IRSA trust statement verification / auto-remediation path (if enabled)

6. **Environment activation**
   - provisioning mode transitions to ready only when hard-fail checks clear.

## Guided Setup Wizard Specification (for UI implementation)

Wizard steps:
1. **Account Link** — collect account ID + role ARN and show external ID copy block.
2. **Trust Policy Check** — validate AssumeRole and external-id condition.
3. **Cluster Check** — validate EKS cluster/OIDC and namespace formatting.
4. **Dispatch Permissions Check** — simulation for job dispatch + PassRole.
5. **Finalize** — persist config and mark environment ready.

Each step must provide:
- pass/fail status
- exact AWS CLI remediation command
- copyable JSON policy patch when applicable

## Current Status

- SparkPilot already implements the downstream preflight checks/remediation logic.
- Missing piece is a dedicated backend onboarding state machine + API endpoints for stepwise wizard progression and persisted onboarding session state.

## Security Constraints

- External ID required for third-party role assumption.
- Least privilege mandatory.
- No long-lived customer secrets stored.
- All assume-role and onboarding mutations captured in audit logs.
