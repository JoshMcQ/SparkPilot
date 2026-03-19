# Issue #21 — OIDC Detection + Remediation Notes

Date: 2026-03-18

## Detection Path

- Check code: `byoc_lite.oidc_association`
- Backend call path:
  - `services/preflight_byoc.py::_add_byoc_lite_oidc_association_check`
  - `aws_clients.py::EmrEksClient.check_oidc_provider_association`
- Detection behavior (default): **detect + instruct only**
  - Uses `eks:DescribeCluster` to resolve OIDC issuer/provider ARN
  - Uses `iam:GetOpenIDConnectProvider` to verify provider exists
  - Does **not** mutate IAM by default

## Remediation Behavior

When provider is missing:
- Preflight emits `fail` with explicit command:
  - `eksctl utils associate-iam-oidc-provider --cluster <cluster> --region <region> --approve`
- Details include automation mode metadata:
  - `automation_mode=detect_only`

Optional automation mode is reserved behind:
- `SPARKPILOT_PREFLIGHT_AUTOFIX_OIDC_PROVIDER=true`

## Required Permissions

Minimum permissions for detection:
- `eks:DescribeCluster`
- `iam:GetOpenIDConnectProvider`

If optional automation is enabled later, also require:
- `iam:CreateOpenIDConnectProvider`

## UI Diagnostics Linkage

The UI preflight diagnostics panel surfaces `byoc_lite.oidc_association` directly:
- File: `ui/components/run-submit-card.tsx`
- Behavior: failed checks render with remediation text before run submission is enabled.
