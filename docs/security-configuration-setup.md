# EMR on EKS Security Configuration Setup

## Overview

SparkPilot supports creating, listing, and describing EMR on EKS
SecurityConfiguration resources. These configurations define encryption (at-rest
and in-transit) and authorization settings (e.g., Lake Formation integration)
for Spark workloads.

## Features

| Feature | Description |
|---------|-------------|
| **Create** | Create a security configuration via `POST /v1/environments/{id}/security-configurations` |
| **List** | List configurations via `GET /v1/environments/{id}/security-configurations` |
| **Describe** | Describe a configuration via `GET /v1/environments/{id}/security-configurations/{config_id}` |
| **Environment Association** | Set `security_configuration_id` on environment creation |
| **Preflight Validation** | Preflight checks verify referenced security configuration exists |
| **Policy Enforcement** | Policy engine `allowed_security_configurations` rule restricts which configurations are allowed |

## Environment Association

When creating an environment, pass `security_configuration_id` to associate
it with a specific EMR security configuration:

```bash
curl -X POST /v1/environments \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "...",
    "region": "us-east-1",
    "customer_role_arn": "arn:aws:iam::123456789012:role/SparkPilotCustomerRole",
    "security_configuration_id": "sc-abc123def456"
  }'
```

## Policy Enforcement

Create a policy to restrict allowed security configurations:

```bash
curl -X POST /v1/policies \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Enforce approved security configs",
    "scope": "global",
    "rule_type": "allowed_security_configurations",
    "config": {
      "allowed": ["sc-approved-config-1", "sc-approved-config-2"],
      "require_security_configuration": true
    },
    "enforcement": "hard"
  }'
```

With `require_security_configuration: true`, environments **must** have a
security configuration set.

## Preflight Check

When an environment has `security_configuration_id` set, preflight includes:

- **`emr.security_configuration`**: Verifies the configuration exists via
  `DescribeSecurityConfiguration` API call.

## IAM Permissions

The customer role needs these additional permissions:

```json
{
  "Effect": "Allow",
  "Action": [
    "emr-containers:CreateSecurityConfiguration",
    "emr-containers:DescribeSecurityConfiguration",
    "emr-containers:ListSecurityConfigurations"
  ],
  "Resource": "*"
}
```

## Encryption Configuration

Example encryption configuration payload:

```json
{
  "encryptionConfiguration": {
    "inTransitEncryptionConfiguration": {
      "tlsCertificateConfiguration": {
        "certificateProviderType": "PEM",
        "publicCertificateSecretArn": "arn:aws:secretsmanager:..."
      }
    }
  }
}
```

## Authorization Configuration

Example Lake Formation authorization:

```json
{
  "authorizationConfiguration": {
    "lakeFormationConfiguration": {
      "authorizedSessionTagValue": "Amazon EMR",
      "secureNamespaceInfo": {
        "clusterId": "cluster-id",
        "namespace": "namespace"
      },
      "queryEngineRoleArn": "arn:aws:iam::123456789012:role/..."
    }
  }
}
```
