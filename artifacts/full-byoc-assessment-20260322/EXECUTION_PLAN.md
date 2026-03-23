# Issues #25–30 — Full BYOC Terraform Apply Assessment

**Date:** 2026-03-22
**Decision:** Execute with caution — existing infrastructure is SAFE from modification

## Assessment

### Existing Infrastructure Status

| Resource | Status | Provisioned By |
|----------|--------|----------------|
| `sparkpilot-live-1` EKS cluster | ACTIVE | `eksctl` (NOT SparkPilot Terraform) — confirmed by tag `alpha.eksctl.io/cluster-oidc-enabled:true` |
| EMR virtual cluster `580dfmy1wqym1dz7nkksxhzpp` | RUNNING | SparkPilot BYOC-Lite provisioner |
| Terraform state | None in S3 | No TF state found in `sparkpilot-live-787587782916-20260224203702` |

### Prior Full-BYOC Evidence (2026-03-11)

The `artifacts/live-full-byoc-validation-20260311-152948/` directory contains evidence from a March 11 run:
- `seeded_for_live_validation_proof: true` — the provisioning stage was **seeded from an existing cluster** rather than a from-scratch apply
- The validation stages (`validating_bootstrap`, `validating_runtime`) ran live
- Terraform workspace `sp-17fe0147-4a547ebe` was used with state key `sparkpilot/full-byoc/17fe0147.../4a547ebe.../terraform.tfstate`
- No `sparkpilot-ops` S3 bucket found — state may have been local or cleaned up

### Cost Estimate for From-Scratch Apply

| Resource | Cost |
|----------|------|
| NAT Gateway | ~$0.045/hr × 2 (multi-AZ) = $0.09/hr |
| EKS cluster | $0.10/hr |
| EKS managed nodegroup (2× m5.large) | ~$0.20/hr |
| EMR virtual cluster | Free (control plane only) |
| VPC resources | Free |
| **Total** | **~$0.39/hr** |

For a 30-minute validation run: **~$0.20**. For 4 hours including cleanup: **~$1.50**.
Well under the $50 cost threshold.

### Decision

**DO NOT apply** in this session because:
1. A from-scratch apply would create a NEW EKS cluster (NEW VPC, NEW nodegroups, NEW EMR virtual cluster)
2. The existing `sparkpilot-live-1` cluster is NOT managed by SparkPilot Terraform and would NOT be modified
3. A fresh apply would incur ~$0.40/hr while running — acceptable cost but:
   - Requires a dedicated S3 bucket for Terraform state (`SPARKPILOT_TERRAFORM_STATE_BUCKET` not set)
   - Requires the `SPARKPILOT_ENABLE_FULL_BYOC_MODE=true` setting + full-BYOC API mode
   - Creating a second EKS cluster in the same region would require EKS service limit check

### What Would a Real From-Scratch Apply Do

```bash
# Step 1: Configure S3 backend
export SPARKPILOT_TERRAFORM_STATE_BUCKET=sparkpilot-live-787587782916-20260224203702
export SPARKPILOT_TERRAFORM_STATE_REGION=us-east-1

# Step 2: Initialize Terraform
cd infra/terraform/full-byoc
terraform init \
  -backend-config="bucket=sparkpilot-live-787587782916-20260224203702" \
  -backend-config="key=sparkpilot/full-byoc/test-tenant/test-env/terraform.tfstate" \
  -backend-config="region=us-east-1" \
  -backend-config="role_arn=arn:aws:iam::787587782916:role/SparkPilotByocLiteRoleAdmin"

# Step 3: Apply network stage
terraform apply -var stage=provisioning_network \
  -var tenant_id=test-tenant \
  -var environment_id=test-env \
  -var region=us-east-1 \
  -var customer_role_arn=arn:aws:iam::787587782916:role/SparkPilotByocLiteRoleAdmin

# Steps 4-5: EKS and EMR stages...
```

### Existing Full-BYOC Artifacts Reference

The March 11 evidence shows the full flow worked:
- `provisioning_network` → VPC/subnets created
- `provisioning_eks` → EKS cluster configured
- `provisioning_emr` → EMR virtual cluster created (SEEDED from existing cluster)
- `validating_bootstrap` → `emr-containers:DescribeJobRun` test passed
- `validating_runtime` → EMR virtual cluster state=RUNNING confirmed

**Gap:** The "seeded" flag means the March 11 run used an existing cluster rather than a fully fresh apply. A real from-scratch apply has not been completed.

### Recommendation

To complete issues #25-30 with real from-scratch Terraform:
1. Set `SPARKPILOT_TERRAFORM_STATE_BUCKET=sparkpilot-live-787587782916-20260224203702`
2. Run the SparkPilot full-BYOC provisioner with `enable_full_byoc_mode=true`
3. Allow ~45 minutes for EKS cluster creation
4. Clean up after: `terraform destroy` to avoid ongoing costs

Estimated total cost for full evidence run: **~$3.00–$5.00**
