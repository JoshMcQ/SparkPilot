# IAM Credential Chain Validation

## Overview

SparkPilot validates the runtime IAM credential chain to ensure:

1. **No static credentials** — runtime services use IAM task roles (ECS) or
   instance profiles (EC2), never long-lived access keys.
2. **Runtime identity** — `sts:GetCallerIdentity` resolves to the expected
   control-plane principal.
3. **Cross-account AssumeRole** — the control-plane can assume customer roles
   for provisioning and dispatch.

## API Endpoints

### Global Runtime Identity Check

```bash
GET /v1/iam-validation
```

Returns current runtime identity, static credential detection, and overall
chain validity without assuming any customer role.

### Environment-Scoped Chain Validation

```bash
GET /v1/environments/{environment_id}/iam-validation
```

Performs full chain validation including AssumeRole into the environment's
`customer_role_arn`.

### Response Format

```json
{
  "checks": [
    {"name": "runtime_identity", "passed": true, "message": "..."},
    {"name": "no_static_credentials", "passed": true, "message": "..."},
    {"name": "assume_role_chain", "passed": true, "message": "..."}
  ],
  "overall_valid": true,
  "runtime_identity": {
    "arn": "arn:aws:sts::123456789012:assumed-role/SparkPilotTaskRole/session",
    "credential_source": "task_role"
  },
  "assume_role": {
    "assumed_role_arn": "arn:aws:sts::987654321098:assumed-role/CustomerRole/session",
    "success": true
  }
}
```

## Preflight Checks

The following preflight checks run automatically for each environment:

| Check Code | Description |
|:---|:---|
| `iam.runtime_identity` | Runtime IAM identity resolves via GetCallerIdentity |
| `iam.no_static_credentials` | Warning if static AWS\_ACCESS\_KEY\_ID detected |
| `iam.assume_role_chain` | AssumeRole into customer\_role\_arn succeeds |

## Failure Scenarios

### Broken Trust Policy

```
Error: Access denied assuming arn:aws:iam::987654321098:role/CustomerRole
Remediation: Update the customer role trust policy to allow the SparkPilot
control-plane role to assume it. Check ExternalId constraints.
```

### Wrong External ID

```
Error: Access denied: The external ID does not match
Remediation: Update trust policy conditions.ExternalId to match.
```

### Denied sts:AssumeRole

```
Error: is not authorized to perform: sts:AssumeRole
Remediation: Grant sts:AssumeRole permission to the SparkPilot runtime role.
```

## Security Requirements

- Control-plane containers must **not** have `AWS_ACCESS_KEY_ID` /
  `AWS_SECRET_ACCESS_KEY` environment variables set.
- Credentials must come from ECS task role, EKS IRSA, or EC2 instance profile.
- CloudTrail logs should show `AssumeRole` calls with the expected principal.
