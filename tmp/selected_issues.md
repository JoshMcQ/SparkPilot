## #1 Full BYOC design spike: architecture, tool selection, and failure model
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/1

Problem
Full BYOC behavior is still simulated in code and has never been validated end-to-end on real AWS.

Scope (design spike only)
- Produce a design doc that selects orchestration approach (Terraform vs CloudFormation vs CDK).
- Define state management model for long-running provisioning and retries.
- Define partial-failure and rollback strategy across VPC, EKS, IAM, and EMR APIs.
- Define account-boundary and security assumptions for customer-owned infrastructure.

Out of Scope
- Implementing VPC/EKS provisioning adapters.
- Shipping runtime code for Full BYOC provisioning.

Acceptance Criteria
- Design doc is reviewed and approved.
- Implementation child issues are created only after the design decision is finalized.
- Child issues include explicit interfaces, failure modes, and test strategy.

---

## #10 [R10] Karpenter Integration for Dynamic Spot Node Provisioning
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/10

Roadmap ID: R10

## Problem Statement
Spot strategy needs operational integration with Karpenter for dynamic, diversified capacity provisioning.

## Why It Matters
Without Karpenter-aware validation and guidance, Spot reliability and savings are inconsistent.

## Acceptance Criteria
- [ ] Preflight check validates Karpenter is installed on the target EKS cluster.
- [ ] Preflight check validates a Karpenter NodePool exists that supports Spot instances.
- [ ] Preflight check validates NodePool instance type diversification (3+ types across 2+ families).
- [ ] Optional: SparkPilot can create/manage a dedicated Karpenter NodePool for Spark workloads during environment provisioning.
- [ ] NodePool config includes Spot + on-demand fallback, Graviton preference, and consolidation policy.
- [ ] Documentation for recommended Karpenter NodePool config for EMR-on-EKS.
- [ ] Unit tests for Karpenter validation.
- [ ] Integration test with real Karpenter installation.

## Out of Scope
- Replacing Karpenter itself.
- Managing unrelated Kubernetes workloads.

## Test Strategy
- Unit tests for Karpenter install and NodePool validation paths.
- Integration test on Karpenter-enabled cluster.
- Real-AWS preflight evidence with remediation output.

## Dependencies
- R18 (#31)
- R01 (#32)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests and integration evidence linked.
- [ ] Documentation updates linked.


---

## #11 Validate private EKS networking scenarios (private endpoint, private subnets, NAT)
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/11

Problem
Current validation does not cover private cluster endpoint or restricted network topologies.

Scope
- Test BYOC-Lite provisioning and run execution against private-endpoint EKS.
- Validate S3/CloudWatch/STS connectivity paths in private subnet deployments.
- Document networking prerequisites and failure modes.

Acceptance Criteria
- One successful private-network E2E run is documented.
- Required VPC endpoints/NAT assumptions are captured.
- Common network failures map to actionable error messages.

---

## #12 Add support and validation for long-running Structured Streaming jobs
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/12

Problem
Only batch-style smoke jobs were validated; long-running streaming lifecycle is untested.

Scope
- Validate run lifecycle for streaming workloads (start, health, cancellation, restart semantics).
- Ensure heartbeat/status model supports long-lived runs.
- Provide one reference streaming workload for verification.

Acceptance Criteria
- Streaming run stays healthy over a sustained interval.
- Cancellation behaves deterministically and updates state.
- Logs and metrics remain accessible during long runtime.

---

## #13 Test and harden cancellation and retry behavior under transient AWS failures
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/13

Problem
Retry and cancellation paths have not been validated against real transient errors.

Scope
- Simulate or induce throttling/network/transient AWS failures in dispatch and reconcile paths.
- Verify retry policy behavior and terminal state correctness.
- Validate cancellation at queued, accepted, and running states.

Acceptance Criteria
- Retry behavior is deterministic and documented.
- Cancellation works from each lifecycle phase with correct final state.
- Automated tests cover transient failure branches.

---

## #15 Establish production deployment baseline for API/workers/database/observability
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/15

Problem
System currently runs locally only; no production deployment baseline exists.

Scope
- Define deployable architecture for API, scheduler/reconciler workers, and persistent database.
- Add secrets management, health checks, structured logging, and baseline monitoring.
- Provide deployment documentation and minimal runbooks.

Acceptance Criteria
- A non-local environment can run end-to-end reliably.
- Core service SLIs are observable.
- Recovery steps are documented for common failures.

---

## #17 Full BYOC design doc and decision record (Issue #1A)
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/17

Goal
Produce the design doc required to unblock full BYOC implementation.

Deliverables
- Decision on provisioning orchestrator (Terraform/CloudFormation/CDK) with tradeoffs.
- State machine and persistence model for long-running infrastructure operations.
- Failure model and rollback behavior for partial failures across VPC/EKS/IAM/EMR.
- Security model for customer account boundaries and minimum role permissions.
- Proposed phased implementation plan and test strategy.

Acceptance Criteria
- Design doc reviewed by lead and approved.
- Follow-on implementation issues created from approved design.

---

## #25 Full BYOC 1B: Terraform orchestrator and operation checkpointing
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/25

Parent: #1

Goal
Introduce an internal Terraform orchestration layer and persist resumable stage checkpoints.

Interfaces
- new module: src/sparkpilot/terraform_orchestrator.py
- new types: ProvisioningStageContext, TerraformPlanResult, TerraformApplyResult
- process_provisioning_once integration for full-BYOC staged execution

Failure modes
- Terraform binary/version mismatch
- backend state lock timeout
- non-zero plan/apply exit with structured diagnostics capture

Test strategy
- unit tests for command construction and parse
- integration tests for checkpoint persistence + resume
- API contract tests for operation state transitions

---

## #26 Full BYOC 1C: Implement provisioning_network stage
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/26

Parent: #1

Goal
Provision VPC/subnet/network baseline for full BYOC with explicit ownership tagging.

Interfaces
- FullByocProvisioner.provision_network(context) -> StageResult
- checkpoint metadata includes created_resource_refs for network resources

Failure modes
- CIDR overlap / subnet create failures
- NAT or endpoint provisioning errors
- permission denied on network APIs

Test strategy
- unit tests for network inputs and tag ownership rules
- integration tests for retryable vs permanent classification
- real-AWS validation in disposable account

---

## #27 Full BYOC 1D: Implement provisioning_eks and provisioning_emr stages
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/27

Parent: #1

Goal
Provision EKS and EMR virtual cluster stages with deterministic readiness checks.

Interfaces
- FullByocProvisioner.provision_eks(context) -> StageResult
- FullByocProvisioner.provision_emr(context) -> StageResult
- AWS client helpers for readiness polling, OIDC association verification, namespace/RBAC verification

Failure modes
- EKS create timeout
- missing OIDC association
- EMR VC create failures (namespace access, trust issues)

Test strategy
- unit tests for readiness/OIDC/trust checks
- integration tests for staged retry + idempotent re-entry
- real-AWS success + known-failure signature tests

---

## #28 Full BYOC 1E: Failure classification, compensation, and cleanup workflow
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/28

Parent: #1

Goal
Harden partial-failure behavior and add controlled cleanup operations.

Interfaces
- ProvisioningErrorClassifier.classify(error) -> RetryDecision
- cleanup operation path (proposed endpoint: POST /v1/environments/{id}/cleanup)
- cleanup checkpoints with operation locking

Failure modes
- cleanup on untagged customer-owned resources
- provisioning/cleanup race
- partial cleanup with inconsistent metadata

Test strategy
- classifier unit tests
- integration tests for cleanup idempotency and locking
- transient failure injection during cleanup

---

## #29 Full BYOC 1F: Security hardening and full-BYOC permission baseline
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/29

Parent: #1

Goal
Finalize full-BYOC role model and least-privilege policy baseline.

Interfaces
- policy artifacts for full-BYOC customer bootstrap
- full-BYOC preflight checks for required IAM actions and trust conditions

Failure modes
- missing iam:PassRole
- ExternalId mismatch in trust
- overbroad grants violating guardrails

Test strategy
- policy simulation/trust parsing tests
- preflight fail-fast remediation tests
- security checklist run before GA enablement

---

## #30 Full BYOC 1G: Real-AWS full-BYOC validation matrix and reproducible smoke flow
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/30

Parent: #1

Goal
Execute and document full-BYOC real-AWS validation scenarios.

Interfaces
- validation docs under docs/validation/
- smoke scripts under scripts/smoke/ for full-BYOC happy + negative paths

Failure modes
- stage failures without actionable remediation
- non-deterministic retry causing duplicate infra
- cross-tenant contamination in tags/state

Test strategy
- happy path at least one region
- negative path per stage with reproducible commands
- resume/retry/cancel checks under worker restart

---

## #33 [R03] Upgrade Cost Tracking to CUR-Aligned Chargeback
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/33

Roadmap ID: R03

## Problem Statement
Current run-cost estimate is not CUR-reconciled and not sufficient for enterprise chargeback.

## Why It Matters
FinOps teams require actual-vs-estimated cost attribution and budget enforcement.

## Acceptance Criteria
- [ ] Add CostAllocation model aligned to CUR line items
- [ ] Integrate CUR data via Athena queries
- [ ] Map namespace/virtual cluster to cost center
- [ ] Propagate team/project tags to EMR job runs and EC2 resources
- [ ] Add showback API endpoint for team/period breakdown
- [ ] Add TeamBudget model with warn/block thresholds
- [ ] Integrate budget checks into preflight
- [ ] Add CUR reconciliation worker
- [ ] Add unit tests for allocation/budgets/reconciliation
- [ ] Add integration test with real CUR data in S3

## Out of Scope
- Cross-cloud billing normalization

## Test Strategy
- Unit tests for cost and budget rules
- Integration test against Athena/CUR dataset

## Dependencies
- R18 (#31)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


---

## #34 [R05] Pod Template and Spark Config Golden Paths
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/34

Roadmap ID: R05

## Problem Statement
Users must handcraft Spark config and pod templates for common jobs.

## Why It Matters
Golden paths enable safe self-serve defaults and remove ticket-queue bottlenecks.

## Acceptance Criteria
- [ ] Add GoldenPath model with config/template/resource fields
- [ ] Seed default small/medium/large/gpu golden paths
- [ ] Include Spark overrides, pod templates, Spot+arch selectors, and quotas in each path
- [ ] Accept golden_path on run submission
- [ ] Allow environment-specific custom golden paths
- [ ] Validate custom Spark config against policy in preflight
- [ ] Add API endpoints for list/create/get golden paths
- [ ] Add unit tests for selection/merge/policy validation
- [ ] Publish docs showing raw API vs golden-path submission

## Out of Scope
- Non-EMR engines

## Test Strategy
- Unit tests for merge precedence and policy checks
- API contract tests for golden-path endpoints
- Real-AWS smoke run using seeded path

## Dependencies
- R18 (#31)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


---

## #37 [R19] End-to-End Test Environment
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/37

Roadmap ID: R19

## Problem Statement
Roadmap features need reproducible infra and CI-backed real validation.

## Why It Matters
Without a test environment, feature claims are not repeatable or trustworthy.

## Acceptance Criteria
- [ ] Provision test EKS with Karpenter, optional YuniKorn, Spot, Graviton, EMR virtual cluster, IAM, log groups
- [ ] Run integration tests in CI against on-demand environment
- [ ] Include sample Spark jobs (PySpark/Scala) and sample S3 data
- [ ] Cover API submit, Airflow submit, cost tracking, audit trail, and preflight blocking scenarios
- [ ] Add teardown script for full cleanup
- [ ] Add cost budget alert for daily infra threshold

## Out of Scope
- Always-on benchmark clusters

## Test Strategy
- Provisioning smoke test
- CI integration runs with artifacts
- Teardown verification

## Dependencies
- R18 (#31)
- R06 (#36)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


---

## #45 [R17] Objection Doc: Why Not EMR Serverless
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/45

Roadmap ID: R17

## Problem Statement
Buyers compare EMR Serverless vs EMR-on-EKS in nearly every evaluation.

## Why It Matters
A balanced comparison helps qualify opportunities and reduce friction.

## Acceptance Criteria
- [ ] Create one-page comparison: EMR Serverless vs EMR-on-EKS with SparkPilot
- [ ] Cover key differences: Spot, K8s governance, multi-tenant sharing, interactive endpoints, FGAC, custom images, Karpenter scaling
- [ ] Explicitly acknowledge where Serverless wins
- [ ] Provide choose-Serverless-if vs choose-EKS+SparkPilot-if guidance
- [ ] Avoid negative framing/trash-talking

## Out of Scope
- Absolute one-size-fits-all recommendation

## Test Strategy
- Technical claim verification
- Neutrality/tone review

## Dependencies
- R18 (#31)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


---

## #65 [Validation] Second-operator real-AWS end-to-end pilot
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/65

Problem
- The system has only been executed end-to-end by the primary developer.
- Product credibility depends on a non-author operator reproducing value in real AWS.

Scope
- Have a second engineer/operator execute full flow in non-prod AWS:
  - auth/bootstrap
  - tenant/team setup
  - environment create/provision
  - job create/submit
  - run monitor/cancel
  - logs/diagnostics/cost view
- Capture complete evidence pack and failure notes.

Acceptance Criteria
- End-to-end flow completes by a non-author operator without tribal knowledge.
- Evidence artifacts are linked (with operation_id/run_id/EMR JobRun IDs).
- Any blockers are documented with follow-up issues.

Related
- Parent: #37
- Also informs: #15

Definition of Done
- Keep issue open until explicit non-prod live-AWS evidence is attached.

---

## #67 [FinOps] Validate CUR reconciliation against real CUR tables
State: open
URL: https://github.com/JoshMcQ/SparkPilot/issues/67

Problem
- CUR reconciliation logic has only been verified against mocked Athena/CUR responses.
- FinOps value claim requires validation against real CUR tables and billing edge cases.

Scope
- Validate reconciliation against a real CUR dataset in Athena.
- Test edge cases: Savings Plans amortization, RI effects, Spot/On-Demand mix, delayed CUR partitions.
- Define acceptable variance thresholds and reconciliation windows.

Acceptance Criteria
- Real CUR reconciliation run produces expected actual/effective cost records.
- Variance thresholds are documented and met (or gaps tracked with follow-up issues).
- Evidence includes Athena query IDs, sample run IDs, and before/after allocation snapshots.

Related
- Parent: #33

Definition of Done
- Keep issue open until explicit non-prod live-AWS evidence is attached.

---


