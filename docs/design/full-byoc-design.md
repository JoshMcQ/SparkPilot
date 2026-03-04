# Full BYOC Design and Decision Record

## Status

- Proposed: March 2, 2026
- Scope: design only, no runtime implementation in this document
- Parent issues: #1, #17

## Problem Statement

`provisioning_mode=full` is currently simulated and has not been implemented or validated on real AWS.
SparkPilot needs a concrete, reviewable design for provisioning customer-owned VPC/EKS/EMR infrastructure
with deterministic retries, clear failure behavior, and strict account-boundary controls.

## Decision Summary

1. Provisioning orchestrator: **Terraform**, executed by SparkPilot workers using assumed-role sessions.
2. State and retries: SparkPilot remains the workflow orchestrator; Terraform handles resource diff/apply.
3. Rollback model: default to **forward recovery**; use targeted compensating cleanup for resources created in the same operation.
4. Security boundary: all data-plane infrastructure remains in customer AWS account; SparkPilot only assumes explicit customer role(s) with ExternalId conditions and tagged sessions.

## Why Terraform

### Selected: Terraform

- Fits current repository direction (`infra/terraform/control-plane` already exists).
- Strong plan/apply model for drift visibility and controlled retries.
- Mature module ecosystem for VPC + EKS patterns.
- Works well with per-environment remote state and explicit locking.

### Not Selected: CloudFormation

- Pro: native AWS service integration, no extra binary.
- Con: rollback semantics can be hard to control in partial-failure scenarios across non-stack operations.
- Con: weaker workflow fit for staged operations spanning multiple stacks plus custom checks.

### Not Selected: CDK

- Pro: expressive code-defined infrastructure.
- Con: introduces compile/synth layer and language/runtime coupling for provisioning workers.
- Con: additional operational complexity compared with plain Terraform plan/apply in CI-style execution.

## Target Architecture (Full BYOC)

### Control Plane

- API persists environment + provisioning operation records.
- `provisioner` worker drives staged execution and retries.
- `scheduler` and `reconciler` remain responsible for run lifecycle after environment is `ready`.

### Data Plane (Customer Account)

- VPC (private subnets, route tables, NAT or endpoints per topology).
- EKS cluster + node groups (or compatible capacity provider settings).
- OIDC provider association.
- EMR on EKS virtual cluster mapped to SparkPilot-managed namespace.
- Job execution role with IRSA trust to EKS OIDC.
- Log and artifact destinations (CloudWatch/S3) with least privilege.

### Terraform State Layout

- Backend: customer account S3 bucket + DynamoDB lock table.
- Key pattern: `sparkpilot/full-byoc/<tenant_id>/<environment_id>/terraform.tfstate`.
- State ownership: customer account.
- SparkPilot access: temporary assumed-role credentials only.

## Provisioning State Model

SparkPilot remains source of truth for operation status. Terraform is a stage executor.

### Operation Stages

1. `validating_bootstrap`
2. `provisioning_network`
3. `provisioning_eks`
4. `provisioning_emr`
5. `validating_runtime`
6. terminal: `ready` or `failed`

### Persistence Requirements

Add per-operation checkpoint metadata (stored in DB) for deterministic resume:

- `terraform_workspace`
- `terraform_state_key`
- `last_successful_stage`
- `attempt_count_by_stage`
- `artifacts` (plan path, apply logs, request ids)
- `created_resource_refs` (resource IDs/ARNs used for cleanup decisions)

### Retry Rules

- Retries are stage-scoped and idempotent.
- If a stage fails with retryable error class, retry same stage with exponential backoff.
- If a stage fails with non-retryable policy/config error, fail operation immediately with remediation.
- Stage transition only occurs after successful apply + post-stage verification.

## Failure Model and Rollback Strategy

### Error Classes

1. **Precondition failures**: missing role trust, invalid config, unsupported region.
2. **Transient AWS failures**: throttling, temporary API/network errors.
3. **Permanent apply failures**: invalid resource settings, quotas, conflicts.
4. **Post-apply validation failures**: resources created but health checks fail.

### Rollback Policy

- Default: preserve created infrastructure for forensic debugging and deterministic resume.
- Compensating cleanup runs only when:
  - resources were created in this operation attempt, and
  - cleanup is low-risk/idempotent, and
  - deleting does not remove pre-existing customer resources.

### Stage-Specific Behavior

- `provisioning_network` failure:
  - If VPC/subnets were newly created in this operation, cleanup can be attempted.
  - If existing customer VPC was targeted, never delete; return actionable remediation.
- `provisioning_eks` failure:
  - Retry on transient control-plane creation errors.
  - Avoid blind cluster deletion unless cluster tagged as SparkPilot-created in same operation.
- `provisioning_emr` failure:
  - Remove partially created virtual cluster if created in current attempt.
  - Preserve namespace and IAM bindings unless explicitly SparkPilot-created and tagged.
- `validating_runtime` failure:
  - Keep infra; fail with explicit checks + remediation commands.

## Security and Account-Boundary Model

### Trust Boundary

- Customer owns and pays for all data-plane resources.
- SparkPilot control plane never uses long-lived customer keys.
- All customer-account actions require `AssumeRole` with ExternalId.

### Required Roles

1. Customer bootstrap role:
  - Assumable by SparkPilot control-plane principal.
  - Scoped permissions for provisioning stages.
2. EMR execution role:
  - IRSA trust bound to namespace/service-account.
  - Used at job runtime; not used for infrastructure provisioning.

### Enforcement Controls

- Session tagging: `tenant_id`, `environment_id`, `operation_id`.
- Explicit deny on destructive actions outside tagged SparkPilot-managed resources.
- CloudTrail correlation via request IDs recorded in audit events.
- No cross-account data path except API calls and control metadata.

## Proposed Interfaces (Implementation Direction)

This design intentionally keeps external REST/CLI interfaces stable where possible.
Internal interfaces to add during implementation:

- `TerraformOrchestrator.plan(stage, context) -> PlanResult`
- `TerraformOrchestrator.apply(stage, context) -> ApplyResult`
- `TerraformOrchestrator.destroy(stage, context) -> DestroyResult`
- `FullByocProvisioningContext` persisted per operation with checkpoint metadata.
- `ProvisioningErrorClassifier` mapping AWS/Terraform errors to retry classes + remediation.

## Phased Implementation Plan

### Phase A: Core Terraform Runner and State Checkpointing

- Build orchestrator wrapper and stage context persistence.
- Implement `validating_bootstrap` + `provisioning_network`.
- Add operation artifact capture (plan/apply logs and resource refs).

### Phase B: EKS and EMR Stages

- Implement `provisioning_eks` with OIDC + node readiness checks.
- Implement `provisioning_emr` and namespace/RBAC bootstrap.
- Add stage-level retry classification.

### Phase C: Runtime Validation and Guardrails

- Implement `validating_runtime` checks for STS, EKS, IAM trust, EMR API readiness.
- Add actionable remediation messages for common failures.
- Add optional cleanup endpoint for operator-controlled rollback.

### Phase D: Reliability and Hardening

- Chaos-style transient failure testing.
- Drift detection and resume behavior.
- Multi-tenant concurrency and isolation verification.

## Test Strategy

### Unit

- Error classifier mappings.
- Stage transition rules and retry counters.
- Context persistence and resume behavior.

### Integration (mock AWS)

- Terraform wrapper behavior for plan/apply/destroy exit codes.
- Worker checkpoint updates across retries.
- Cleanup gating based on `created_resource_refs`.

### Real AWS Validation

- Fresh account bootstrap + first full environment bring-up.
- Intentional faults at each stage (quota, IAM deny, invalid subnet config).
- Resume after worker crash between stages.
- Cleanup behavior on failed and successful operations.

### Exit Criteria

- At least one complete full-BYOC provisioning flow reaches `ready`.
- Deterministic behavior for staged retries and remediation output.
- No unbounded destructive rollback on customer pre-existing resources.

## Risks and Mitigations

1. Terraform state drift:
   - Mitigation: locked remote state, explicit plan review artifacts, drift checks before apply.
2. Overbroad IAM privileges:
   - Mitigation: staged least-privilege policies and explicit deny boundaries.
3. Long provisioning times and flaky cloud APIs:
   - Mitigation: per-stage timeouts, retry classifier, resumable checkpoints.
4. Cleanup deleting customer-owned resources:
   - Mitigation: strict tag ownership checks and opt-in cleanup controls.

## Open Review Questions

1. Should production require a human approval gate before `provisioning_eks` apply?
2. Is default forward-recovery acceptable, or should auto-cleanup be enabled for dev/test only?
3. Should SparkPilot support importing pre-existing EKS clusters into `full` mode, or keep that as `byoc_lite` only?
4. What hard timeout should be enforced per stage in production?

## Approval Record

- Reviewer: `TBD`
- Decision date: `TBD`
- Outcome: `Pending`
