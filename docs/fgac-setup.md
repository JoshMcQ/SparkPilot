# Lake Formation FGAC Setup Guide

SparkPilot supports AWS Lake Formation Fine-Grained Access Control (FGAC) for
EMR-on-EKS environments. When enabled, SparkPilot validates FGAC prerequisites
in the preflight system and records the active Lake Formation permission context
in the audit trail for each run.

## Prerequisites

| Requirement | Details |
|-------------|---------|
| EMR Release | `emr-7.7.0` or later (Lake Formation FGAC requires EMR 7.7+) |
| Service-Linked Role | `AWSServiceRoleForLakeFormationDataAccess` must exist in the account |
| Execution Role | Must have Lake Formation data permissions granted |
| SparkPilot Permissions | `lakeformation:ListPermissions`, `iam:GetRole` for the SparkPilot service role |

## Enabling FGAC

### 1. Create the environment with FGAC enabled

```bash
curl -X POST /v1/environments \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "tenant_id": "your-tenant-id",
    "region": "us-east-1",
    "customer_role_arn": "arn:aws:iam::123456789012:role/customer-role",
    "eks_cluster_arn": "arn:aws:eks:us-east-1:123456789012:cluster/my-cluster",
    "eks_namespace": "spark",
    "provisioning_mode": "byoc_lite",
    "lake_formation_enabled": true,
    "lf_catalog_id": "123456789012",
    "lf_data_access_scope": {
      "databases": ["analytics_db", "data_lake"],
      "description": "Production analytics data scope"
    }
  }'
```

### 2. Create the Lake Formation service-linked role (if not exists)

```bash
aws iam create-service-linked-role \
  --aws-service-name lakeformation.amazonaws.com
```

### 3. Grant Lake Formation permissions to the execution role

```bash
aws lakeformation grant-permissions \
  --principal DataLakePrincipal={DataLakePrincipalIdentifier=arn:aws:iam::123456789012:role/emr-execution-role} \
  --resource '{"Database": {"Name": "analytics_db"}}' \
  --permissions SELECT DESCRIBE
```

### 4. Verify with preflight

```bash
curl /v1/environments/{env_id}/preflight \
  -H "Authorization: Bearer $TOKEN"
```

Expected preflight checks when FGAC is enabled:

| Check Code | Description |
|-----------|-------------|
| `fgac.emr_release` | Verifies EMR release supports FGAC (>= 7.7.0) |
| `fgac.service_linked_role` | Verifies LF service-linked role exists |
| `fgac.lf_permissions` | Verifies execution role has LF data permissions |

## Golden Path Data Access Scope

Golden paths can declare an approved data access scope to document what data
resources the path is designed to access:

```bash
curl -X POST /v1/golden-paths \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "name": "analytics-etl",
    "description": "ETL pipeline for analytics data",
    "driver_resources": {"vcpu": 2, "memory_gb": 8},
    "executor_resources": {"vcpu": 4, "memory_gb": 16},
    "executor_count": 10,
    "data_access_scope": {
      "databases": ["analytics_db"],
      "tables": ["analytics_db.events", "analytics_db.users"],
      "description": "Read access to analytics events and user profiles"
    }
  }'
```

## Audit Trail

When FGAC is enabled, SparkPilot records a `run.lf_permission_context` audit
event at run creation time. This captures:

- Active Lake Formation permissions for the execution role
- Catalog ID
- Databases and tables accessible
- Timestamp of the permission check

Query audit events:

```bash
curl /v1/audit-events?action=run.lf_permission_context \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

### Preflight fails: "does not support Lake Formation FGAC"

Upgrade your EMR release label to `emr-7.7.0` or later:

```
SPARKPILOT_EMR_RELEASE_LABEL=emr-7.7.0
```

### Preflight fails: "service-linked role not found"

Create the SLR:

```bash
aws iam create-service-linked-role \
  --aws-service-name lakeformation.amazonaws.com
```

### Preflight fails: "no Lake Formation data permissions"

Grant permissions to the execution role via the Lake Formation console or CLI.
Ensure the SparkPilot service role has `lakeformation:ListPermissions` to verify
grants.
