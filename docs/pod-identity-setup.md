# EKS Pod Identity & Access Entries Setup Guide

SparkPilot supports EKS Pod Identity as the preferred identity mechanism for
BYOC-Lite environments, with automatic IRSA fallback when Pod Identity is
not available.

## Identity Modes

| Mode | Description | Status |
|------|-------------|--------|
| `pod_identity` | Uses EKS Pod Identity associations | Preferred |
| `irsa` | Uses IAM Roles for Service Accounts (OIDC) | Fallback |

SparkPilot auto-detects the available identity mode during environment
provisioning and records it in the environment's `identity_mode` field.

## Pod Identity First Setup (Recommended)

### 1. Enable EKS Access Entries

```bash
aws eks update-cluster-config \
  --name my-cluster \
  --access-config authenticationMode=API_AND_CONFIG_MAP \
  --region us-east-1
```

### 2. Install the Pod Identity Agent

```bash
aws eks create-addon \
  --cluster-name my-cluster \
  --addon-name eks-pod-identity-agent \
  --region us-east-1
```

Verify:

```bash
aws eks describe-addon \
  --cluster-name my-cluster \
  --addon-name eks-pod-identity-agent \
  --region us-east-1
```

The addon status should be `ACTIVE`.

### 3. Create the EMR Execution Role (Pod Identity Path)

For Pod Identity, the execution role's trust policy uses the `pods.eks.amazonaws.com`
service principal:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ]
    }
  ]
}
```

### 4. Create the Environment

```bash
curl -X POST /v1/environments \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tenant_id": "your-tenant-id",
    "region": "us-east-1",
    "customer_role_arn": "arn:aws:iam::123456789012:role/customer-role",
    "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/my-cluster",
    "eks_namespace": "spark",
    "provisioning_mode": "byoc_lite"
  }'
```

SparkPilot will:
1. Detect the Pod Identity agent is installed
2. Set `identity_mode = "pod_identity"`
3. Record the identity path in audit events
4. Complete OIDC/trust setup for IRSA compatibility

### 5. Verify with Preflight

```bash
curl /v1/environments/{env_id}/preflight \
  -H "Authorization: Bearer $TOKEN"
```

Expected checks:

| Check Code | Description |
|-----------|-------------|
| `byoc_lite.pod_identity_readiness` | Verifies eks-pod-identity-agent addon is ACTIVE |
| `byoc_lite.access_entry_mode` | Verifies cluster supports access entries (API or API_AND_CONFIG_MAP) |

## IRSA Fallback Setup

If Pod Identity is not available, SparkPilot automatically falls back to IRSA:

### 1. Associate OIDC Provider

```bash
eksctl utils associate-iam-oidc-provider \
  --cluster my-cluster \
  --region us-east-1 \
  --approve
```

### 2. Configure Execution Role Trust Policy (IRSA)

The trust policy should include `sts:AssumeRoleWithWebIdentity` with the
cluster's OIDC provider as the `Federated` principal.

SparkPilot automatically updates the execution role trust policy during
BYOC-Lite provisioning to add the required EMR service account condition.

## Audit Events

SparkPilot records which identity path was used during provisioning:

| Action | Description |
|--------|-------------|
| `environment.byoc_lite_identity_detected` | Records the identity mode used (`pod_identity` or `irsa`) |

Query identity mode audit events:

```bash
curl "/v1/audit-events?action=environment.byoc_lite_identity_detected" \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

### Pod Identity agent not found

```
warning: EKS Pod Identity agent is not installed.
```

Install the addon or accept IRSA fallback:

```bash
aws eks create-addon \
  --cluster-name <name> \
  --addon-name eks-pod-identity-agent
```

### Access entries not supported

```
warning: EKS cluster authentication mode is CONFIG_MAP.
```

Update the cluster access configuration:

```bash
aws eks update-cluster-config \
  --name <name> \
  --access-config authenticationMode=API_AND_CONFIG_MAP
```

### Checking environment identity mode

```bash
curl /v1/environments/{env_id} \
  -H "Authorization: Bearer $TOKEN" | jq .identity_mode
```
