### #10 [R10] Karpenter Integration for Dynamic Spot Node Provisioning
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


### #11 Validate private EKS networking scenarios (private endpoint, private subnets, NAT)
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

### #12 Add support and validation for long-running Structured Streaming jobs
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

### #15 Establish production deployment baseline for API/workers/database/observability
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

### #26 Full BYOC 1C: Implement provisioning_network stage
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

### #27 Full BYOC 1D: Implement provisioning_eks and provisioning_emr stages
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

### #28 Full BYOC 1E: Failure classification, compensation, and cleanup workflow
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

### #29 Full BYOC 1F: Security hardening and full-BYOC permission baseline
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

### #30 Full BYOC 1G: Real-AWS full-BYOC validation matrix and reproducible smoke flow
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

### #33 [R03] Upgrade Cost Tracking to CUR-Aligned Chargeback
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


### #36 [R06] Build Apache Airflow Provider Package
Roadmap ID: R06

## Problem Statement
Airflow is a primary orchestrator and SparkPilot lacks first-class provider primitives.

## Why It Matters
Without native operators/sensors/hooks, users must write fragile custom API calls in DAGs.

## Acceptance Criteria
- [ ] Publishable package apache-airflow-providers-sparkpilot
- [ ] SparkPilotSubmitRunOperator submits and polls run
- [ ] SparkPilotRunSensor waits for terminal state
- [ ] SparkPilotHook supports URL/token via Airflow connections
- [ ] Support golden path and raw config modes
- [ ] Push run metadata to XCom (id/status/cost/duration/log URL)
- [ ] Transient errors retry; permanent errors fail task
- [ ] Support deferrable operator pattern
- [ ] Include example DAG in docs
- [ ] Add unit tests with mocked SparkPilot API
- [ ] Add docker-compose integration test with real SparkPilot + Airflow

## Out of Scope
- Managed Airflow hosting

## Test Strategy
- Unit tests for hook/operator/sensor/trigger
- Integration run with docker-compose

## Dependencies
- R18 (#31)
- R05 (#34)
- R12 (#35)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #37 [R19] End-to-End Test Environment
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


### #38 [R09] Lake Formation FGAC Integration
Roadmap ID: R09

## Problem Statement
Regulated buyers require fine-grained data controls for EMR-on-EKS workloads.

## Why It Matters
FGAC readiness is a common enterprise security gate.

## Acceptance Criteria
- [ ] Add environment-level FGAC opt-in config
- [ ] Preflight enforces EMR release 7.7+ for FGAC
- [ ] Preflight validates Lake Formation permissions for execution role
- [ ] Preflight validates required LF service-linked role exists
- [ ] Document FGAC setup requirements
- [ ] Allow golden paths to declare approved data access scope
- [ ] Audit trail records active LF permission context for each run
- [ ] Add unit tests for FGAC preflight
- [ ] Add integration test with real LF-protected table

## Out of Scope
- Automatic governance grant provisioning for all catalogs

## Test Strategy
- Unit tests for FGAC validations
- Integration test against LF-protected table

## Dependencies
- R18 (#31)
- R05 (#34)
- R12 (#35)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #39 [R13] Policy Engine for Run Guardrails
Roadmap ID: R13

## Problem Statement
Quotas alone are insufficient for enterprise guardrails.

## Why It Matters
Enterprises need policy-enforced runtime governance beyond simple quota caps.

## Acceptance Criteria
- [ ] Add Policy model (scope, rule type, config, enforcement)
- [ ] Implement built-in rule types (runtime/vcpu/memory/tags/golden-path/release/instance-type)
- [ ] Evaluate policies during preflight before quota checks
- [ ] Return clear remediation on violations
- [ ] Add admin API for policy CRUD
- [ ] Audit every policy evaluation result
- [ ] Add unit tests for each policy type
- [ ] Add integration test where policy blocks violating run

## Out of Scope
- General-purpose policy DSL

## Test Strategy
- Unit tests per rule type
- API tests for policy CRUD/evaluation
- Integration block/warn behavior test

## Dependencies
- R18 (#31)
- R12 (#35)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #41 [R08] Interactive Endpoints Support (EMR Studio)
Roadmap ID: R08

## Problem Statement
SparkPilot currently lacks first-class managed interactive endpoint support.

## Why It Matters
Interactive workflows expand TAM beyond batch-only users.

## Acceptance Criteria
- [ ] Add InteractiveEndpoint model
- [ ] Add EmrEksClient create/describe/delete/list managed endpoint methods
- [ ] Support idle-timeout auto-termination
- [ ] Support per-user/per-team endpoint provisioning with separate roles
- [ ] Add endpoint API routes for create/list/delete
- [ ] Add endpoint preflight checks (IAM/namespace/ALB controller)
- [ ] Track interactive endpoint cost by connected time
- [ ] Audit endpoint create/delete/connect events
- [ ] Add endpoint lifecycle unit tests
- [ ] Add real-EKS managed-endpoint integration test

## Out of Scope
- Notebook authoring UX

## Test Strategy
- Client/service unit tests
- API contract tests
- Real-AWS endpoint lifecycle evidence

## Dependencies
- R18 (#31)
- R12 (#35)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #42 [R11] YuniKorn Queue Management for Multi-Tenant Scheduling
Roadmap ID: R11

## Problem Statement
Shared-cluster fairness controls are limited without queue-aware scheduling.

## Why It Matters
Multi-team scheduling fairness becomes critical as concurrency grows.

## Acceptance Criteria
- [ ] Detect YuniKorn installation on target cluster
- [ ] Optionally create namespace-scoped YuniKorn queue during provisioning
- [ ] Support queue guaranteed/max resources and priority
- [ ] Validate queue capacity in preflight before accepting run
- [ ] Add API endpoint for queue utilization per environment
- [ ] Document YuniKorn setup guidance
- [ ] Add unit tests for queue management
- [ ] Add integration test with YuniKorn on EKS

## Out of Scope
- Supporting every batch scheduler

## Test Strategy
- Unit tests for queue config/validation
- API tests for utilization endpoint
- Integration test on YuniKorn-enabled cluster

## Dependencies
- R18 (#31)
- R12 (#35)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #46 [R07] Build Dagster Integration (dagster-sparkpilot)
Roadmap ID: R07

## Problem Statement
Dagster users lack first-class SparkPilot integration primitives.

## Why It Matters
Supporting major orchestrators broadens adoption and reduces integration friction.

## Acceptance Criteria
- [ ] Publish Python package dagster-sparkpilot
- [ ] Add SparkPilotResource for API interaction
- [ ] Add sparkpilot_run_op for submit + wait flow
- [ ] Support golden path references
- [ ] Emit Dagster asset metadata (run id/cost/duration/log URL)
- [ ] Add unit tests with mocked SparkPilot API
- [ ] Publish example Dagster job in docs

## Out of Scope
- Dagster cloud deployment automation

## Test Strategy
- Resource/op unit tests
- Example pipeline execution test

## Dependencies
- R18 (#31)
- R05 (#34)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #47 [R15] Spark UI Proxy and History Server Integration
Roadmap ID: R15

## Problem Statement
Engineers need stage/task visibility beyond raw logs.

## Why It Matters
Spark UI access is standard for debugging and performance analysis.

## Acceptance Criteria
- [ ] Add environment config for Spark event-log S3 location
- [ ] Add run record link to Spark History Server UI
- [ ] Optionally host Spark History Server proxy in SparkPilot
- [ ] Document EMR-on-EKS Spark event logging setup

## Out of Scope
- Replacing Spark History Server internals

## Test Strategy
- API model tests for event-log metadata
- Integration validation of history-link behavior

## Dependencies
- R18 (#31)
- R14 (#43)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #48 [R20] Load Testing for Multi-Tenant Scenarios
Roadmap ID: R20

## Problem Statement
Performance baselines are unknown for high-concurrency multi-tenant workloads.

## Why It Matters
Enterprise readiness requires measured latency/throughput and bottleneck visibility.

## Acceptance Criteria
- [ ] Build load test simulating 50 concurrent run submissions across 5 teams
- [ ] Verify preflight throughput, quota correctness under concurrency, cost tracking accuracy, and audit completeness
- [ ] Measure API latency p50/p95/p99, time-to-dispatch, reconciler lag
- [ ] Document performance baselines

## Out of Scope
- Global-scale chaos experiments

## Test Strategy
- Repeatable load scenarios
- Metric collection and report artifact publication

## Dependencies
- R18 (#31)
- R19 (#37)

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence artifacts linked in an issue comment.
- [ ] Unit tests added/updated where applicable.
- [ ] Integration or real-AWS validation linked where required.
- [ ] Documentation updates linked where applicable.


### #51 [R22] Add EMR on EKS Job Template Management (Create/List/Describe/Delete)
Roadmap ID: R22

## Problem Statement
EMR on EKS JobTemplate APIs are not exposed in SparkPilot, forcing repeated run payload assembly and reducing standardization.

## Why It Matters
Job templates are a native EMR control-plane primitive and improve reuse, consistency, and policyability across teams.

## Acceptance Criteria
- [ ] Add SparkPilot model and API support for EMR Job Templates (create/list/describe/delete)
- [ ] Allow run submission to reference a template plus parameter overrides
- [ ] Tag templates with tenant/environment ownership metadata
- [ ] Integrate template validation into preflight and policy checks
- [ ] Add unit tests for CRUD + submit-with-template behavior
- [ ] Add integration test against real EMR on EKS JobTemplate APIs

## Out of Scope
- Unrelated EMR control-plane features not required by this scope.

## Test Strategy
- Unit tests for new API/service behavior.
- Integration tests for real AWS API paths where applicable.
- Evidence artifacts linked in issue comments.

## Dependencies
- R18
- R05
- R13

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Tests and evidence linked.
- [ ] Documentation/runbooks updated.


### #52 [R23] Adopt EKS Pod Identity and Cluster Access Entries for BYOC-Lite bootstrap
Roadmap ID: R23

## Problem Statement
Current BYOC-Lite onboarding still depends primarily on legacy IRSA/auth-configmap style bootstrap paths.

## Why It Matters
EMR on EKS docs now document Pod Identity and EKS access entries; aligning reduces manual RBAC/auth drift and improves security posture.

## Acceptance Criteria
- [ ] Preflight detects Pod Identity readiness and EKS access-entry mode
- [ ] Bootstrap flow supports Pod Identity path in addition to IRSA fallback
- [ ] Audit events capture which identity path was used (Pod Identity vs IRSA)
- [ ] Runbooks updated with Pod Identity-first setup steps
- [ ] Unit tests for Pod Identity detection and remediation output
- [ ] Integration test in real EKS cluster configured with access entries

## Out of Scope
- Unrelated EMR control-plane features not required by this scope.

## Test Strategy
- Unit tests for new API/service behavior.
- Integration tests for real AWS API paths where applicable.
- Evidence artifacts linked in issue comments.

## Dependencies
- R18
- R12

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Tests and evidence linked.
- [ ] Documentation/runbooks updated.


### #53 [R24] Add EMR on EKS Security Configuration Support (encryption and auth controls)
Roadmap ID: R24

## Problem Statement
SparkPilot currently does not manage or validate EMR on EKS SecurityConfiguration resources.

## Why It Matters
Enterprise deployments require explicit encryption/auth configuration and traceable enforcement.

## Acceptance Criteria
- [ ] Add support for Create/List/Describe security configurations via EMR Containers APIs
- [ ] Allow environment/run-level association to a security configuration
- [ ] Preflight validates referenced security configuration exists and is policy-compliant
- [ ] Policy engine supports allowed/disallowed security configuration rules
- [ ] Unit tests for validation and API wiring
- [ ] Integration test with real EMR SecurityConfiguration resources

## Out of Scope
- Unrelated EMR control-plane features not required by this scope.

## Test Strategy
- Unit tests for new API/service behavior.
- Integration tests for real AWS API paths where applicable.
- Evidence artifacts linked in issue comments.

## Dependencies
- R18
- R13

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Tests and evidence linked.
- [ ] Documentation/runbooks updated.


### #54 [R25] Define and Implement Flink-on-EMR-on-EKS Product Scope
Roadmap ID: R25

## Problem Statement
EMR on EKS surface now includes extensive Flink-native capabilities, but SparkPilot roadmap is Spark-centric only.

## Why It Matters
Audit found significant uncovered EMR capability area; an explicit product decision is needed to avoid implicit scope drift.

## Acceptance Criteria
- [ ] Publish decision record: Spark-only vs Spark+Flink support boundaries
- [ ] If in-scope, add minimal Flink job submission lifecycle support and observability hooks
- [ ] If out-of-scope, document rationale and customer guidance
- [ ] Map dependencies with streaming and policy tracks
- [ ] Add unit tests for chosen implementation path
- [ ] Add real-AWS validation for whichever path is selected

## Out of Scope
- Unrelated EMR control-plane features not required by this scope.

## Test Strategy
- Unit tests for new API/service behavior.
- Integration tests for real AWS API paths where applicable.
- Evidence artifacts linked in issue comments.

## Dependencies
- R18
- R12
- R19

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Tests and evidence linked.
- [ ] Documentation/runbooks updated.


### #55 [R26] Evaluate and integrate EMR on EKS Vertical Autoscaling operator patterns
Roadmap ID: R26

## Problem Statement
EMR on EKS docs include Vertical Autoscaling (VAS) operator workflows, but SparkPilot has no support/decision path for VAS-aware scheduling and telemetry.

## Why It Matters
Audit R18 identified this as uncovered feature surface requiring explicit product handling.

## Acceptance Criteria
- [ ] Publish design decision for VAS support level
- [ ] If in-scope, add preflight checks for VAS prerequisites
- [ ] Add observability hooks for VAS events and scaling decisions
- [ ] Document supported vs unsupported VAS modes
- [ ] Add unit tests and at least one real-AWS validation scenario

## Out of Scope
- Unrelated EMR features outside this specific scope.

## Test Strategy
- Unit tests where code is added.
- Real-AWS validation evidence for any runtime-impacting behavior.

## Dependencies
- R18
- R20

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence and docs linked in issue comments.


### #56 [R27] Decide and track Apache Livy support strategy for EMR on EKS
Roadmap ID: R27

## Problem Statement
EMR on EKS supports Apache Livy pathways, but SparkPilot currently has no product stance or integration design for Livy-based submission.

## Why It Matters
Audit R18 identified this as uncovered feature surface requiring explicit product handling.

## Acceptance Criteria
- [ ] Publish product decision: support/defer Livy
- [ ] If supporting, define minimal API and auth model
- [ ] Document security and RBAC implications
- [ ] Link decision to orchestration integrations roadmap
- [ ] Add tests/docs for chosen path

## Out of Scope
- Unrelated EMR features outside this specific scope.

## Test Strategy
- Unit tests where code is added.
- Real-AWS validation evidence for any runtime-impacting behavior.

## Dependencies
- R18
- R06
- R07

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence and docs linked in issue comments.


### #57 [R28] Add S3 Express One Zone workload guidance and guardrails for EMR on EKS
Roadmap ID: R28

## Problem Statement
EMR on EKS docs include S3 Express One Zone patterns, but SparkPilot has no explicit validation/guidance for compatibility and cost/perf tradeoffs.

## Why It Matters
Audit R18 identified this as uncovered feature surface requiring explicit product handling.

## Acceptance Criteria
- [ ] Document when to use S3 Express for Spark workloads
- [ ] Add preflight warning/validation hooks for unsupported configs
- [ ] Provide golden-path guidance for compatible use cases
- [ ] Add test coverage for config validation paths

## Out of Scope
- Unrelated EMR features outside this specific scope.

## Test Strategy
- Unit tests where code is added.
- Real-AWS validation evidence for any runtime-impacting behavior.

## Dependencies
- R18
- R05
- R02

## Definition of Done
- [ ] Acceptance criteria complete.
- [ ] Evidence and docs linked in issue comments.


