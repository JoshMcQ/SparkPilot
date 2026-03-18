# Tenant Isolation Boundaries and Security Assumptions

This document defines what SparkPilot enforces, what customer infrastructure must enforce, and how to review deployments before production use.

## Scope

SparkPilot provides control-plane isolation and policy guardrails for multi-tenant Spark workload operations.
It does not replace account-level, network-level, and data-plane security controls owned by the customer.

## SparkPilot-Enforced Controls

- Authenticated API access using bearer-token validation.
- Role-aware authorization checks (`admin`, `operator`, `user`) on environment, run, team, and budget APIs.
- Team-to-environment scope enforcement for non-admin users.
- Per-request audit events for critical control-plane mutations.
- Environment and run preflight checks prior to dispatch.
- Idempotency enforcement for create-style mutation APIs that require replay safety.

## Customer-Required Controls

- AWS account boundary design (single-account or multi-account tenant segmentation).
- IAM trust policy hardening for execution roles and assumed roles.
- EKS namespace, RBAC, network policy, and node-isolation controls.
- KMS key policy and encryption-at-rest controls for data and logs.
- CloudWatch/S3 retention and access controls for operational artifacts.
- CUR and cost-allocation tag governance for reliable chargeback.

## Non-Goals and Explicit Limits

- Kubernetes namespaces alone are not a hard security boundary.
- SparkPilot does not enforce data lake ACLs (Lake Formation/IAM policy remains customer-owned).
- SparkPilot does not guarantee workload runtime isolation beyond customer-provided EKS/IAM/network controls.
- SparkPilot does not replace customer SIEM/compliance evidence pipelines.

## Shared Responsibility Checklist

Use this checklist before enabling tenant self-serve access:

1. Confirm customer role trust policy only allows intended principals.
2. Confirm EKS namespace and RBAC mapping is tenant-scoped.
3. Confirm network policies and egress controls are applied.
4. Confirm KMS encryption and key policies for logs/artifacts.
5. Confirm CloudTrail/CloudWatch audit visibility for SparkPilot mutations.
6. Confirm team-environment scopes and budgets are configured in Access UI.
7. Confirm preflight checks pass for each production environment.
8. Confirm run cancellation, retry, and diagnostics paths are operational.

## Operational Review Inputs

- `docs/deployment.md`
- `docs/setup/choose-mode.md`
- `docs/runbooks.md`
- `docs/validation/byoc-lite-multi-tenant-isolation.md`
