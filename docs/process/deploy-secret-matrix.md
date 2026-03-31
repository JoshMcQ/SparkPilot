# Deploy Secret Matrix

Required GitHub secrets and vars per environment. All three deploy jobs run `scripts/ci/deploy_preflight.sh` before AWS auth. If `AWS_{ENV}_DEPLOY_ROLE_ARN` is not set, the job skips gracefully (exit 0). If the role ARN is set but other required secrets are missing, the job fails early and prints the exact missing key names.

## Required Secrets

| Secret Name                        | dev | staging | prod | Notes |
|------------------------------------|-----|---------|------|-------|
| `AWS_DEV_DEPLOY_ROLE_ARN`          | ✅  |         |      | OIDC role; triggers deploy-dev |
| `AWS_STAGING_DEPLOY_ROLE_ARN`      |     | ✅      |      | OIDC role; triggers deploy-staging |
| `AWS_PROD_DEPLOY_ROLE_ARN`         |     |         | ✅   | OIDC role; triggers deploy-prod |
| `{ENV}_TF_STATE_BUCKET`            | ✅  | ✅      | ✅   | S3 bucket for Terraform state |
| `{ENV}_TF_LOCK_TABLE`              | ✅  | ✅      | ✅   | DynamoDB table for state locking |
| `{ENV}_VPC_ID`                     | ✅  | ✅      | ✅   | VPC ID for the control plane |
| `{ENV}_PRIVATE_SUBNET_IDS_JSON`    | ✅  | ✅      | ✅   | JSON array of private subnet IDs |
| `{ENV}_DB_PASSWORD`                | ✅  | ✅      | ✅   | RDS PostgreSQL password |
| `{ENV}_OIDC_ISSUER`                | ✅  | ✅      | ✅   | OIDC issuer URL |
| `{ENV}_OIDC_AUDIENCE`              | ✅  | ✅      | ✅   | OIDC audience/client ID |
| `{ENV}_OIDC_JWKS_URI`              | ✅  | ✅      | ✅   | OIDC JWKS URI |
| `{ENV}_BOOTSTRAP_SECRET`           | ✅  | ✅      | ✅   | API bootstrap secret |
| `{ENV}_EMR_EXECUTION_ROLE_ARN`     | ✅  | ✅      | ✅   | EMR execution role ARN |
| `{ENV}_ACM_CERTIFICATE_ARN`        | opt | opt     | opt  | ACM cert for HTTPS ALB listener |

## Optional Secrets

| Secret Name                        | Notes |
|------------------------------------|-------|
| `{ENV}_ASSUME_ROLE_EXTERNAL_ID`    | ExternalId for cross-account assume-role |

## Optional Vars (GitHub environment variables)

| Var Name                           | Default | Notes |
|------------------------------------|---------|-------|
| `{ENV}_DRY_RUN_MODE`               | `false` | Skip real AWS calls during Terraform apply |
| `{ENV}_ENABLE_FULL_BYOC_MODE`      | `false` | Enable full BYOC provisioner |
| `{ENV}_ALLOW_UNSAFE_RDS_CONFIGURATION` | `false` | Skip RDS multi-AZ enforcement |
| `{ENV}_RDS_DELETION_PROTECTION`    | (empty) | `true`/`false` override |
| `{ENV}_RDS_SKIP_FINAL_SNAPSHOT`    | (empty) | `true` to skip final snapshot |
| `{ENV}_RDS_FINAL_SNAPSHOT_IDENTIFIER` | (empty) | Custom final snapshot ID |
| `{ENV}_MANAGE_VPC_ENDPOINTS`       | `false` | staging only — manage VPC endpoints |
| `{ENV}_CUR_ATHENA_DATABASE`        | (empty) | CUR Athena database |
| `{ENV}_CUR_ATHENA_TABLE`           | (empty) | CUR Athena table |
| `{ENV}_CUR_ATHENA_WORKGROUP`       | `primary` | Athena workgroup |
| `{ENV}_CUR_ATHENA_OUTPUT_LOCATION` | (empty) | Athena query output S3 location |
| `{ENV}_CUR_RUN_ID_COLUMN`          | `resource_tags_user_sparkpilot_run_id` | CUR tag column |
| `{ENV}_CUR_COST_COLUMN`            | `line_item_unblended_cost` | CUR cost column |
| `{ENV}_COST_CENTER_POLICY_JSON`    | (empty) | JSON cost center policy |
| `{ENV}_ENABLE_ECS_EXEC`            | `false` | Enable ECS Exec for debugging |
| `{ENV}_PUBLIC_SUBNET_IDS_JSON`     | `[]` | Public subnet IDs (ALB) |

## How Skip Works

When `AWS_{ENV}_DEPLOY_ROLE_ARN` is not set in the GitHub environment:

1. `deploy_preflight.sh` prints: `INFO: {env} deploy skipped — AWS_{ENV}_DEPLOY_ROLE_ARN is not set.`
2. Sets `skip=true` in `$GITHUB_OUTPUT` and exits 0.
3. All subsequent steps in the job have `if: steps.preflight.outputs.skip != 'true'` and are skipped.
4. The job completes successfully — the pipeline stays green.

This is the intended behavior when a target environment (e.g., prod) has not yet been provisioned.

## How Partial Configuration Fails

When `AWS_{ENV}_DEPLOY_ROLE_ARN` is set but other required secrets are missing:

1. `deploy_preflight.sh` checks all required secrets.
2. Prints each missing key name (no values are printed).
3. Exits with code 1 — the job fails at the preflight step with an actionable error.

Example preflight failure output:
```
::error::prod deploy preflight FAILED — role ARN is set but 3 required secret(s) are missing:
  missing: PROD_TF_STATE_BUCKET
  missing: PROD_VPC_ID
  missing: PROD_DB_PASSWORD

Add the above secrets to the 'prod' GitHub environment and re-run.
```
