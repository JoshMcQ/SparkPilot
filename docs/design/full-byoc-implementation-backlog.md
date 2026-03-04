# Full BYOC Implementation Backlog (Post-Design Approval)

This document defines child implementation slices for issue #1 after design approval.
Each slice includes explicit interfaces, failure modes, and test strategy.

## Issue 1B: Terraform Orchestrator and Operation Checkpointing

### Goal

Introduce an internal Terraform orchestration layer and persist resumable stage checkpoints.

### Interfaces

- New module: `src/sparkpilot/terraform_orchestrator.py`
- New types:
  - `ProvisioningStageContext`
  - `TerraformPlanResult`
  - `TerraformApplyResult`
- Service integration:
  - `process_provisioning_once` calls orchestrator per stage instead of simulated full-mode path.

### Failure Modes

- Terraform binary missing or version mismatch.
- Backend state lock acquisition timeout.
- Non-zero plan/apply exit with structured diagnostics capture.

### Tests

- Unit tests for command construction and parsing plan/apply results.
- Integration tests for stage checkpoint persistence and resume logic.
- Contract tests verifying operation state transitions remain API-compatible.

## Issue 1C: Network Provisioning Stage (`provisioning_network`)

### Goal

Provision VPC/subnet/network baseline for full BYOC with explicit ownership tagging.

### Interfaces

- Stage handler:
  - `FullByocProvisioner.provision_network(context) -> StageResult`
- DB checkpoint metadata additions:
  - `created_resource_refs` includes VPC/subnet/route resources.

### Failure Modes

- CIDR overlap or subnet creation failures.
- NAT/VPC endpoint provisioning errors.
- Permission denied on network resource creation.

### Tests

- Unit tests for network input validation and tags.
- Mocked integration tests for retryable vs permanent failure classification.
- Real-AWS validation in disposable account path.

## Issue 1D: EKS and EMR Provisioning (`provisioning_eks`, `provisioning_emr`)

### Goal

Provision cluster and EMR virtual cluster path with deterministic readiness checks.

### Interfaces

- Stage handlers:
  - `FullByocProvisioner.provision_eks(context) -> StageResult`
  - `FullByocProvisioner.provision_emr(context) -> StageResult`
- AWS client additions for:
  - cluster readiness polling
  - OIDC association verification
  - namespace/RBAC binding verification

### Failure Modes

- EKS control plane create timeout.
- OIDC association missing.
- EMR virtual cluster create failures (namespace access, invalid role trust).

### Tests

- Unit tests for readiness and OIDC/trust checks.
- Integration tests for stage retries and idempotent re-entry.
- Real-AWS tests for successful provision + known failure signatures.

## Issue 1E: Failure Classification, Compensation, and Operator Cleanup

### Goal

Harden partial-failure behavior and introduce controlled cleanup operations.

### Interfaces

- New classifier:
  - `ProvisioningErrorClassifier.classify(error) -> RetryDecision`
- New API endpoint (proposed):
  - `POST /v1/environments/{id}/cleanup` (operator initiated)
- New operation subtype:
  - cleanup operation with its own stage checkpoints.

### Failure Modes

- Cleanup attempted on untagged customer-owned resources.
- Concurrent provisioning and cleanup race.
- Partial cleanup resulting in inconsistent state metadata.

### Tests

- Unit tests for classifier mappings and cleanup guardrails.
- Integration tests for cleanup idempotency and locking behavior.
- Real-AWS fault injection tests for transient API errors during cleanup.

## Issue 1F: Security Hardening and Permission Baseline

### Goal

Finalize full-BYOC role model and least-privilege policy set with auditable assumptions.

### Interfaces

- Policy artifacts:
  - `infra/cloudformation/customer-bootstrap-full-byoc.yaml` (or Terraform equivalent)
- Service preflight extensions for full-BYOC:
  - explicit checks for required IAM actions and trust conditions.

### Failure Modes

- Missing `iam:PassRole` for execution/runtime roles.
- ExternalId mismatch in trust policy.
- Overbroad policy grants violating security guardrails.

### Tests

- Unit tests for policy simulation and trust parsing.
- Integration tests for preflight fail-fast remediation messages.
- Security review checklist execution before enabling GA.

## Issue 1G: Real-AWS Full BYOC Validation Matrix

### Goal

Execute and document end-to-end validation scenarios for full BYOC.

### Interfaces

- Validation artifacts under `docs/validation/`.
- Smoke script(s) under `scripts/smoke/` for full-BYOC happy path and failure path drills.

### Failure Modes

- Stage-specific AWS failures not mapped to actionable user-facing messages.
- Non-deterministic retries leading to duplicate infrastructure.
- Cross-tenant contamination in state or tags.

### Tests

- Happy path in at least one region.
- Negative path for each stage with reproducible commands.
- Resume/retry/cancellation checks under worker restart conditions.

## Sequencing Recommendation

1. 1B
2. 1C
3. 1D
4. 1E
5. 1F
6. 1G

This sequence enforces foundational orchestration/state correctness before reliability and security hardening.
