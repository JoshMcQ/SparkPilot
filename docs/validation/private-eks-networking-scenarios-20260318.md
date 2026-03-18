# Private EKS Networking Validation (March 18, 2026)

Issue: #11

This record captures a successful real-AWS end-to-end run on the live EKS target while documenting network topology assumptions and failure signatures for private-access scenarios.

## Primary Artifacts

- `artifacts/issue65-second-operator-20260317-230206/summary.json`
- `artifacts/issue11-private-network-20260317-231436/cluster.json`
- `artifacts/issue11-private-network-20260317-231436/subnets.json`
- `artifacts/issue11-private-network-20260317-231436/vpc-endpoints.json`
- `artifacts/issue11-private-network-20260317-231436/main-route-table.json`

## E2E Runtime Evidence

Successful run context (same cluster/network surface):

- `environment_id`: `871beffd-7513-48c1-8047-cce837afe9ef`
- `operation_id`: `0ba5114e-7f2c-42fe-a4c4-c07da1705d46`
- `run_id`: `71f150ce-37da-4940-95db-e43f10222a09`
- EMR JobRun ID: `0000000377usjctefps`
- terminal state: `succeeded`

## Network Topology Snapshot

- EKS `endpointPrivateAccess=true`
- EKS `endpointPublicAccess=true`
- VPC: `vpc-0fe2e97a951e3a126`
- Cluster/nodegroup subnets: 5 subnets in `us-east-1a/b/c/d/f`

Main route table (`rtb-0cd9a4e6c9a839427`) includes:

- local VPC route `172.31.0.0/16 -> local`
- default route `0.0.0.0/0 -> igw-08ca15003a88fc74a`

## Private-Network Assumptions and Requirements

For private-subnet-only nodegroups (no direct IGW route), successful BYOC-lite runtime requires one of:

1. NAT egress for STS, ECR, S3, and CloudWatch Logs APIs.
2. Equivalent VPC endpoints for required AWS services plus route/security-group correctness.

At minimum, validate reachability for:

- STS (`AssumeRole` / simulation path)
- EKS control-plane describe APIs
- EMR on EKS (`emr-containers`)
- CloudWatch Logs
- S3 artifact access

## Common Failure Signatures and Remediation

- OIDC/trust failures:
  - signature: explicit `byoc_lite.oidc_association` or trust-policy failures in preflight
  - remediation: associate OIDC provider and fix execution-role trust
- PassRole/dispatch auth failures:
  - signature: `byoc_lite.customer_role_dispatch` / `byoc_lite.iam_pass_role` fail
  - remediation: grant dispatch actions + `iam:PassRole` on execution role
- Namespace/virtual cluster wiring failures:
  - signature: provisioning `failed` with actionable namespace/virtual-cluster message
  - remediation: align namespace ownership and virtual-cluster mapping, then retry

## Acceptance Mapping

- One successful real-AWS E2E run on target network surface: `pass`
- VPC endpoint/NAT requirements documented: `pass`
- Common network/auth failure signatures mapped to actionable remediation: `pass`
