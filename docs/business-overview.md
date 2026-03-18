# SparkPilot — Complete Business Overview

*Last updated: March 15, 2026*
*This document is brutally honest. It distinguishes what exists, what has been tested once, what has only been tested against mocks, and what is not built yet.*

---

## Part 1: What This Is

### One-liner

SparkPilot is a pre-dispatch governance and cost control layer for data compute workloads on AWS — starting with Apache Spark on EMR.

### The pitch (30 seconds)

> Every company running Spark on AWS faces the same fork: let data engineers call EMR directly with no guardrails, or spend 6+ months building an internal platform you maintain forever. SparkPilot is the third option — a control plane that gates every job before it runs, tracks every dollar after it finishes, and gives platform teams governed self-service without building it themselves. Your data and compute never leave your AWS account.

### The pitch reframed as workload contracts (for executives / finance)

> You can't deploy code that fails CI checks. You shouldn't run compute that will fail or break budgets. SparkPilot enforces workload contracts — enforceable pre-dispatch agreements that a job will be allowed, will likely succeed, and will stay within a defined cost and governance envelope. It's CI/CD gates for data compute.

---

## Part 2: The Problem

### What people do today

| Approach | What happens | What goes wrong |
|---|---|---|
| **Direct boto3/CLI scripts** | Data engineers call `emr-containers:StartJobRun` from Airflow DAGs. | No lifecycle tracking, no preflight, no audit trail. IAM misconfiguration wastes compute. |
| **DIY internal platform** | Platform engineering team builds a wrapper API over EMR on EKS. | Takes 4–8 months. Team maintains IAM/OIDC edge cases forever. |
| **Databricks** | Pay for managed runtime. | No true BYOC — Databricks bills compute + software together. Data leaves your account boundary. |
| **EMR Serverless** | Simpler, but no Kubernetes, no cluster-level governance, no multi-tenant namespace isolation. | Different operating model, no cross-team cost attribution. |
| **Nothing** | Airflow talks directly to EMR with no visibility, no retries, no cost attribution. | Teams have no idea what they're spending. Failures are discovered after the fact. |

### Why existing tools don't solve it

Every player in the competitive landscape operates *after* the job has started or *after* it ran:

| Category | Examples | What they do | What they don't do |
|---|---|---|---|
| **Runtime optimizers** | Pepperdata, Ocean for Apache Spark (Flexera/Spot) | Squeeze waste out of running jobs by tuning CPU/memory in real-time. Spot instance management. | Can't help if IAM is misconfigured and the job fails in 30 seconds. Can't enforce budgets. |
| **Between-run autotuners** | Sync Computing (acquired by Capital One → Slingshot) | Analyze last Spark event log, recommend better cluster config for next run. | Recommendations, not hard gates. No governance, no audit trail. |
| **Post-run observability** | Unravel Data | Dashboards and diagnostics after the fact. | Past tense. Can't prevent the bad run. |
| **FinOps platforms** | Kubecost, Finout, nOps, Zesty | Show what you spent and where. | Also past tense. Tell you that you overspent, not stop you before you do. |
| **Native AWS** | AWS Budgets, EMR Studio | Budget alerts (8–12 hour refresh lag), notebook IDE. | AWS Budgets update ~3×/day — you can burn thousands before it notices. EMR Studio is not a governance plane. |

### The gap nobody occupies

**Pre-dispatch.** Before the job starts. Before compute is consumed. Before money is spent. Before the IAM trust policy failure burns 10 minutes of startup cost. Before the team blows its monthly budget at 2 AM.

That's where SparkPilot sits.

---

## Part 3: What the Product Does (Verified Against Code)

### Service inventory with honest validation status

Every capability listed below was verified by reading the actual source code. Validation status is categorized as:
- **Tested on real AWS once** = Ran against real AWS infrastructure in account 787587782916 on March 3, 2026. One time. One account. One day. This is not production validation.
- **Tested against mocks** = Unit/integration tests pass (188 total) using SQLite in-memory DB, mocked AWS clients, stubbed OIDC. Never touched real AWS for this feature.
- **Code exists, untested** = Implementation is written but has no tests or only trivial coverage.
- **Not built** = Referenced in plans/docs but no code exists.

#### Core Control Plane (9,048 lines Python)

| # | Service | What it does | Validation status |
|---|---|---|---|
| 1 | **REST API** | FastAPI service (861 lines). Manages tenants, teams, environments, jobs, runs, golden paths, budgets, cost showback. 25+ endpoints with OIDC auth on every route. | Tested against mocks (2,234 lines of API tests). One live test run on real AWS. |
| 2 | **Preflight Gating** | 20+ automated checks run before every job dispatch: IAM simulation, execution role trust, OIDC association, namespace validation, Spot capacity/diversification, budget thresholds, EMR release currency, Graviton compatibility, Spark conf policy. Hard-blocks bad runs. | Preflight engine (1,089 lines across preflight.py + preflight_byoc.py). Tested against mocks. Run once on real AWS — all checks passed on a correctly configured environment. **Never tested against a misconfigured environment on real AWS.** |
| 3 | **Run Lifecycle State Machine** | Full state machine: queued → dispatching → accepted → running → succeeded/failed/cancelled/timed_out. Deterministic stale detection, timeout cancellation, transient retry with configurable max attempts, cancellation propagation to EMR. | Scheduler (165 lines) + reconciler (217 lines). State transitions tested in unit tests. Dispatched and reconciled real EMR runs once. |
| 4 | **Multi-Tenant RBAC** | Tenant → Team → Environment hierarchy. Three roles (admin/operator/user). Team-environment scope memberships. Users only see their own runs; operators see scoped environments; admins see everything. OIDC bearer token auth. | 496 lines of RBAC tests verify cross-team isolation, role permission boundaries, scope filtering. **All against mocks — never tested with real OIDC provider.** |
| 5 | **Audit Trail** | Every mutation writes an AuditEvent: actor, source IP, entity type/id, AWS request ID, CloudTrail event ID. Covers create, cancel, dispatch, reconcile, preflight pass/fail. | Audit writes verified in test suite. **Never correlated with actual CloudTrail in a real account.** |
| 6 | **Run Diagnostics** | Pattern-matching against CloudWatch logs for 6 failure categories: OOM, shuffle fetch failure, S3 access denied, schema mismatch, timeout, Spot interruption. Actionable remediation text for each. | 288 lines of diagnostic tests with parameterized patterns. Tested against mocked CloudWatch log lines. **Never diagnosed a real failed Spark job's logs.** |
| 7 | **Cost Attribution & Showback** | Per-run usage recording (vCPU-seconds, memory-GB-seconds, estimated cost). Architecture-aware pricing with ARM discount. Team-level showback API with estimated vs. actual vs. effective cost. | 484 lines of FinOps tests. **Pricing engine uses linear algebra against mocked EC2 pricing API responses. Never validated against real AWS Pricing API data.** |
| 8 | **Team Budget Guardrails** | Monthly budgets per team with configurable warn/block thresholds. Preflight blocks new runs when spend exceeds block threshold. | Budget CRUD + preflight integration tested in unit tests. **Never enforced a real budget breach on real AWS.** |
| 9 | **CUR Reconciliation** | Athena-based reconciliation against AWS Cost and Usage Report. Replaces estimated cost with actual billed cost. Spot vs. on-demand breakdown, savings attribution. SQL injection prevention, Athena polling. | 602 lines of FinOps code. Tested against mocked Athena client. **Never run against a real CUR table. Edge cases (Savings Plans, RI amortization, EMR uplift vs. EC2 base) are unknown.** |
| 10 | **Run Logs** | CloudWatch log retrieval via assumed-role session in customer's account. | Tested once on real AWS (real CloudWatch logs retrieved). |
| 11 | **Idempotent Mutations** | Every create operation (tenant, environment, job, run, cancel) is idempotency-key gated with DB-level reservation locking. Fingerprint-based replay detection. | Tested in unit tests. Guarantees retry safety from Airflow/Dagster. **Never stress-tested with concurrent requests.** |
| 12 | **Golden Path Templates** | Pre-configured Spark job profiles (small/medium/large/GPU) with resource specs, Spot config, instance type recommendations. CRUD API + environment-scoped or global. Seeding for defaults. | Code exists (226 lines). Tested in unit tests. Profiles are usable templates, not dynamic recommendations. |
| 13 | **EMR Release Sync** | Background worker syncs EMR release labels from AWS. Preflight checks release currency (current/deprecated/end-of-life) and Graviton support. | Worker + sync logic (101 lines). **Never synced against real EMR API.** |
| 14 | **Environment Provisioning (BYOC-Lite)** | Customer provides EKS cluster + namespace. SparkPilot validates prerequisites (OIDC, trust policy, permissions), creates EMR virtual cluster, marks environment ready. | Provisioning worker (840 lines). Successfully provisioned one real environment on real AWS. |
| 15 | **Environment Provisioning (Full BYOC)** | SparkPilot provisions customer VPC + EKS + EMR via Terraform. Staged pipeline with checkpoint/resume. | Terraform orchestrator (248 lines) + provisioning stages + TF modules exist. Tested in dry-run mode only (495 lines of TF orchestrator tests). **Never created real infrastructure.** |

#### Orchestrator Integrations (2,135 lines Python)

| # | Provider | What it includes | Validation status |
|---|---|---|---|
| 16 | **Airflow Provider** | Hook (370 lines): OIDC client-credentials auth, retry/backoff, idempotency keys. Operator (249 lines): submit run, optionally wait or defer. Sensor (74 lines): poke for terminal state. Trigger (214 lines): async deferrable trigger for Airflow 2.x. Example DAG included. | 472 lines of tests against Airflow compat stubs. **Never run against a real Airflow instance. Never tested the deferrable trigger in a real Airflow scheduler. Never published to PyPI.** |
| 17 | **Dagster Provider** | Client (263 lines): OIDC auth, retry/backoff. Resource (74 lines): lazy client creation. Ops (392 lines): submit/wait/cancel ops with config schemas. Assets (65 lines): submit/wait/cancel/lifecycle assets. | 161 lines of tests against Dagster compat stubs. **Never run against a real Dagster instance. Never published to PyPI.** |

#### UI (Next.js, ~3,200 lines TypeScript)

| Page/Component | What it does | Validation status |
|---|---|---|
| **Dashboard** | Environment count, total runs, in-flight runs, CTAs. | Renders. Works against local API. |
| **Environments** | List/detail/create. Preflight check display. BYOC-Lite form with validation. | Renders. Created one real environment through it. |
| **Runs** | List with 8-sec auto-refresh, job creation, run submission with preflight gate, cancellation, log viewer, diagnostics panel. | Renders. Submitted/monitored one real run. |
| **Costs** | Team selector, billing period picker, usage + showback tables, bar chart (pure CSS). | Renders. **Never displayed real cost data.** |
| **Access** | Admin panel for user identities, teams, team-environment scopes. | Renders. Used to bootstrap one admin identity. |
| **Auth** | OIDC Authorization Code + PKCE flow, manual Bearer token paste, JWT decode display. | OIDC flow works against local mock OIDC server. **Never tested against a real IdP (Okta, Auth0, Cognito).** |
| **API Proxy** | All `/api/sparkpilot/*` routes proxied to Python backend. | Works locally. |

#### Infrastructure (Terraform + CloudFormation)

| Component | What it does | Validation status |
|---|---|---|
| **Control Plane TF** (945 lines) | ECS Fargate deployment: ALB, RDS PostgreSQL, SQS queues, KMS, CloudWatch, IAM roles, 3 worker services. | Written with production safety checks. **Never deployed.** |
| **Full BYOC TF** (173 lines + community EKS module) | Staged provisioning: network → EKS → EMR with cross-account assume-role. | Code exists. **Never applied against real AWS.** |
| **CloudFormation Bootstrap** (2 templates) | Customer IAM role setup for Full BYOC and BYOC-Lite. Least-privilege with condition keys. | Templates exist. **BYOC-Lite template used once in real account.** |

#### Tests (6,160 lines Python, 188 tests)

All tests run against SQLite in-memory with mocked AWS clients and a test OIDC harness that generates real RSA-signed JWTs. This is genuine test infrastructure, but it is not a substitute for real-world validation.

---

## Part 4: Data Model

```
Tenant
  └── Team
       └── TeamEnvironmentScope ──→ Environment
                                      ├── ProvisioningOperation
                                      ├── Job
                                      │    └── Run
                                      │         ├── RunDiagnostic
                                      │         ├── UsageRecord
                                      │         └── CostAllocation
                                      └── GoldenPath

UserIdentity (actor, role: admin|operator|user, tenant/team assignment)
TeamBudget (per-team monthly budget with warn/block thresholds)
EmrRelease (synced release labels with lifecycle status)
AuditEvent (every mutation, every actor, every source IP)
IdempotencyRecord (scope + key + fingerprint for replay safety)
```

The `engine` column on Environment defaults to `emr_on_eks`. This is the extension point for future backends (EMR Serverless, EMR on EC2, Databricks on AWS).

---

## Part 5: The Competitive Landscape

### Direct historical comp

**Data Mechanics** (YC S19, ~10 employees, Paris) — Built a managed Spark-on-Kubernetes platform deployed in customer cloud accounts. Acquired by NetApp in 2021, integrated as "Ocean for Apache Spark." Now owned by Flexera after their March 2025 acquisition of Spot from NetApp.

- **Their model**: BYOC, Spark on K8s, customer's cloud account — same deployment model as SparkPilot.
- **Their product**: Runtime optimization + infrastructure management. Intelligent Spot/on-demand mixing. Job right-sizing by continuously tuning Spark config. Makes Spark cheaper/faster *while it runs.*
- **What they don't do**: No preflight gating. No IAM validation before dispatch. No multi-tenant RBAC. No team budget enforcement. No audit trail. No orchestrator-native providers.
- **Implication for SparkPilot**: They validated the BYOC Spark-on-K8s market and got acquired with a small team. SparkPilot occupies a different functional position (governance/safety vs. runtime optimization). A customer could theoretically use both. But SparkPilot's path to replacing Data Mechanics starts with "smarter dispatch defaults" (golden paths, historical recommendations) rather than "dynamic executor resizing" (which requires a K8s operator running inside the cluster — fundamentally different engineering).

### Competitive map

| Player | Position in workflow | What they sell | BYOC | Pre-dispatch gate | Cost attribution | Audit/RBAC |
|---|---|---|---|---|---|---|
| **Data Mechanics / Ocean for Apache Spark (Flexera)** | During run | Runtime optimization, Spot management, auto-scaling | Yes | No | No | No |
| **Pepperdata** | During run | Real-time pod-level resource optimization | No (on-prem/cluster) | No | No | No |
| **Sync Computing → Capital One Slingshot** | Between runs | ML-powered config recommendations | N/A (SaaS) | No (recommendations) | No | No |
| **Unravel Data** | After run | Observability, diagnostics, dashboards | No (SaaS) | No | Limited | No |
| **Kubecost** (acquired by IBM) | After run | Kubernetes cost allocation | In-cluster | No | Yes (K8s level) | No |
| **Finout / nOps / Zesty** | After run | Cloud FinOps, spend visibility, commitment optimization | N/A (SaaS) | No | Yes (cloud level) | No |
| **AWS EMR Studio** | At run | Managed notebook/IDE for EMR | N/A (native) | No | No | Limited |
| **AWS Budgets** | After spend (8-12hr lag) | Budget alerts and actions | N/A (native) | No (too slow) | Account-level | No |
| **Databricks** | At run | Managed Spark/SQL/ML platform | Partial (BYOC available but Databricks bills compute) | Compute policies (cluster config limits) | Unity Catalog (data governance, not workload governance) | Workspace-level |
| **SparkPilot** | **Before dispatch** | Preflight gating, RBAC, budget enforcement, cost attribution, audit trail, orchestrator-native integrations | Yes (full BYOC) | **Yes (20+ checks)** | **Yes (CUR-reconciled per-run)** | **Yes (3 roles, team-env scopes)** |

### Key market signals

1. **Acquisition precedent**: NetApp bought Data Mechanics (~10 employees, ~2 years old) for Spark-on-K8s capability. IBM bought Kubecost for container cost management. Capital One bought Sync Computing for ML-powered optimization. Small teams with focused capabilities in this space get acquired.

2. **FinOps consolidation is active**: IBM acquired Apptio (IT financial management) then Kubecost (container costs). Flexera acquired Spot (cloud infrastructure optimization). The pattern is: large governance/FinOps platforms buy focused tools to fill gaps.

3. **The "governance layer" gap**: Runtime optimizers, FinOps dashboards, and managed platforms all exist. Nobody ships the pre-dispatch governance layer that spans identity + cost + policy + orchestration. That's the gap.

---

## Part 6: Strategic Positioning — Workload Contracts

### The concept

Instead of selling "Spark control plane," sell **Workload Contracts**: enforceable declarations of intent evaluated before any compute starts.

A workload contract says:
- "This run must complete within 90 minutes."
- "This team cannot spend more than $X this month on this workload class."
- "This run can only use approved Spark/EMR release families."
- "This run may use Spot, but only if capacity and diversification criteria are met."
- "This run's IAM trust chain must be valid before dispatch."
- "If risk is high, require approval."

This is not policy-as-code in the abstract. It is a **runtime admission agreement** for expensive data workloads that spans identity, cost, and reliability — evaluated at the moment of submission.

### Why this framing works

| Audience | What they hear |
|---|---|
| VP Engineering | "CI/CD gates for data compute. No job runs unless it passes checks." |
| Platform team lead | "Governed self-service. My team defines contracts. Data engineers submit against them. No more ticket queues." |
| Finance / FinOps | "Real-time budget enforcement (not 8-hour-delayed AWS Budgets). Per-team per-run cost attribution reconciled against actual CUR billing." |
| Security / compliance | "Audit trail for every mutation. RBAC with team-scoped permissions. IAM validation before dispatch." |
| Data engineer | "I pick a template, submit my job, and it either runs or tells me exactly why it can't and how to fix it." |

### How existing code maps to the contract lifecycle

| Contract phase | What it means | Existing code | Status |
|---|---|---|---|
| **Define** | Platform teams create rules for what's allowed | Planned policy engine (CRUD policies, conditions, actions) | **NOT BUILT.** This is the biggest gap. Preflight checks exist but are hardcoded, not user-configurable. |
| **Evaluate** | Every run submission checked against contracts | Preflight engine: 20+ checks across IAM, OIDC, Spot, budget, release, Graviton, Spark conf | Built. Tested once on real AWS. |
| **Enforce** | Block, warn, or require approval based on evaluation | State machine: queued → dispatching → terminal. Cancellation propagation. Timeout enforcement. | Built. Tested once on real AWS. |
| **Attribute** | Every run gets a cost, every team gets a bill | Usage recording, CUR reconciliation, showback API | Built. **CUR reconciliation never tested against real CUR.** |
| **Audit** | Every action recorded with actor, IP, timestamps | AuditEvent model on every mutation. AWS request ID / CloudTrail correlation fields. | Built. Tested in unit tests. |
| **Self-serve** | Data engineers pick templates, system enforces constraints | Golden path templates (small/medium/large/GPU). Run submission with preflight gate in UI. | Built. Templates are static, not dynamic recommendations. |

### The missing piece: Policy Engine

To make "workload contracts" real and sellable, the system needs configurable policies — not just hardcoded preflight checks. This means:

- `Policy` model (rules with conditions, evaluation logic, actions: block/warn/require-approval)
- CRUD API (`POST/GET/PATCH/DELETE /v1/policies`)
- Policy evaluation integrated into the preflight chain
- UI for defining policies and viewing contract compliance per run
- Remediation messages per policy violation

This is the single most important feature that does not exist today.

---

## Part 7: Expansion Roadmap

### AWS-first, engine-second

The architecture supports multiple execution backends because the AWS-specific code is isolated behind a client abstraction (`EmrEksClient`). The core (models, API, RBAC, audit, idempotency, state machine, budget enforcement) is engine-agnostic.

### Expansion path (in priority order)

| Phase | Backend | Why | What transfers | What's new |
|---|---|---|---|---|
| **Current** | EMR on EKS (BYOC-Lite) | This is what exists and has been tested once. | Everything. | Nothing — validate what exists. |
| **Next** | EMR Serverless | Same AWS APIs, same CUR, same IAM. Reaches Spark-on-AWS users who don't want EKS. Major TAM expansion. No K8s complexity for the customer. | RBAC, audit, lifecycle, budget enforcement, CUR reconciliation, orchestrator integrations, UI. | New dispatch client (`emr-serverless:StartJobRun`). Simpler preflight (no OIDC/namespace/cluster checks). New warm pool / pre-initialized capacity guardrails. |
| **Then** | EMR on EC2 | Same AWS account model, same CUR, same IAM. Large installed base. | Same as above. | New dispatch surface. Cluster-level (not namespace-level) isolation model. |
| **Then** | Databricks on AWS | Largest Spark user base. Still AWS underneath — IAM applies, CUR works, STS assume-role works. | RBAC, audit, lifecycle, budget enforcement, CUR reconciliation (Databricks EC2 shows up in CUR), orchestrator integrations, UI. | New dispatch client (Databricks Jobs REST API). New preflight checks (workspace permissions, cluster policies, instance pool config). |
| **Future** | GCP (Dataproc) / Azure (HDInsight/Synapse) | Multi-cloud story for acquirer interest. | Core (models, API, RBAC, audit, state machine, UI, orchestrator integrations). | New IAM model, new billing integration, new dispatch surface per cloud. ~1,500–2,500 lines of new provider code each. Not trivial, but additive — not a rewrite. |

### What specifically transfers vs. what doesn't per new backend

**Transfers (no rewrite):**
- Data model (Tenant → Team → Environment → Job → Run) — engine-agnostic
- RBAC system — engine-agnostic
- Audit trail — engine-agnostic
- Idempotency system — engine-agnostic
- API layer — engine-agnostic
- State machine (queued → dispatching → accepted → running → terminal) — engine-agnostic
- UI — engine-agnostic
- Orchestrator integrations (Airflow/Dagster) — they talk to the SparkPilot API, not to AWS
- Budget enforcement — engine-agnostic (the ledger is internal)
- CUR reconciliation — works for any AWS-based backend (EMR, Databricks on AWS)

**Needs new provider implementation (~1,000–2,500 lines per backend):**
- Dispatch client (e.g., `DatabricksClient` alongside `EmrEksClient`)
- Provider-specific preflight checks (Databricks workspace permissions vs. IAM trust policies)
- Provider-specific billing integration for non-AWS clouds (GCP billing export vs. CUR)
- Bootstrap templates (CloudFormation/Terraform for customer account setup)

---

## Part 8: Things We Should Not Forget But Should Not Build Now

### Dynamic executor resizing
Data Mechanics/Ocean for Apache Spark does runtime optimization — dynamically tuning executor CPU/memory while jobs run, managing Spot interruptions mid-flight. This requires an agent running *inside* the K8s cluster, watching pod metrics in real-time. SparkPilot runs *outside* the cluster (dispatch via API, poll via API). Building a runtime optimizer is a fundamentally different product and at least a year of engineering. **Don't build it.**

What *is* in scope: smarter dispatch defaults based on historical run data. "Your last 10 runs used 40% of allocated memory — consider the medium template instead of large." That's lightweight and doesn't require cluster instrumentation. Golden path templates already point in this direction.

### Predictive failure model
Use historical failure patterns to predict before dispatch whether a job with similar characteristics is likely to fail. The diagnostics engine already classifies 6 failure categories. The leap to "predict failure probability from historical runs" requires significant run volume to train on, a feature engineering pipeline, and a model that generalizes across customer workloads. This is a real product direction but requires data we don't have (hundreds/thousands of runs across customers). **Park it. Revisit when there's enough run volume.**

### Interactive endpoints (REPL/notebook sessions)
Different risk profile than batch. Users leave sessions alive, over-allocate, bypass batch governance. Needs new guardrails (idle timeout, session cost caps). **Build after batch governance is proven.**

### Naming
"SparkPilot" limits us if the product expands beyond Spark (which it will with Databricks, EMR Serverless). The name pins us to one engine. But right now nobody knows the name either way. **Rename when going to market on the second backend, not before.**

---

## Part 9: What Needs to Happen (In Order)

### Immediate (make what exists trustworthy)

| # | Action | Why |
|---|---|---|
| 1 | **Get a second person to use the system end-to-end on real AWS** | Proves the core loop works for someone other than the developer. Every strategic conversation is hypothetical until this happens. |
| 2 | **Run preflight against a *misconfigured* environment on real AWS** | Preflight has only been tested against a correctly configured environment. The entire value proposition is catching misconfigurations. If it doesn't catch a real one, the product story falls apart. |
| 3 | **Test CUR reconciliation against a real CUR table** | The FinOps story ("per-run actual cost reconciled against CUR") is only credible if it works against real CUR data with real edge cases. |
| 4 | **Test the Airflow provider against real Airflow** | The orchestrator integrations are the natural distribution channel. If the Airflow operator doesn't work in a real DAG with a real scheduler, it's not a distribution channel — it's a code artifact. |
| 5 | **Test against a real OIDC provider (Cognito, Auth0, Okta)** | Auth is OIDC-only. If it doesn't work against a real IdP, customers can't log in. |

### Next (make the product sellable)

| # | Action | Why |
|---|---|---|
| 6 | **Build the policy engine** | This is what makes "workload contracts" configurable, not hardcoded. Platform teams need to define their own rules. Without this, preflight checks are one-size-fits-all. |
| 7 | **Write the isolation boundaries document** | Enterprise security teams will ask what SparkPilot guarantees about tenant isolation. Kubernetes namespaces are not a security boundary. Be honest about what's enforced (logical RBAC) vs. what's not (no network policies, no node-level separation). This document unblocks security review conversations. |
| 8 | **Collect baseline metrics from real runs** | "X% of runs would have been blocked by preflight. $Y of compute would have been wasted." This is the proof that makes buying obvious. |

### Then (expand the market)

| # | Action | Why |
|---|---|---|
| 9 | **Add EMR Serverless as a dispatch backend** | Broadens from "companies running EMR on EKS" to "companies running Spark on any EMR mode." Largest TAM expansion within AWS with the least new code. |
| 10 | **Add EMR on EC2 as a dispatch backend** | Same AWS model, massive installed base. |
| 11 | **Add Databricks on AWS** | Largest Spark user base. Still AWS underneath. IAM, CUR, STS all transfer. |

---

## Part 10: Acquisition Thesis

Nobody acquires code. They acquire proven demand, or a team with IP they can't replicate quickly.

### The pattern that exists

| Acquirer | Target | What they bought | Why |
|---|---|---|---|
| NetApp | Data Mechanics | Spark-on-K8s managed platform + team | Bolt onto Spot Ocean for container workload management |
| IBM | Kubecost | Kubernetes cost allocation | Fill container FinOps gap in Apptio/Turbonomic portfolio |
| IBM | Apptio | IT financial management | Anchor FinOps suite |
| Capital One | Sync Computing | ML-powered Spark autotuning | Bolt onto Slingshot for Databricks/Snowflake optimization |
| Flexera | Spot (from NetApp) | Cloud infrastructure optimization (includes Ocean for Apache Spark) | Complete cloud FinOps portfolio |

### Who would want SparkPilot's capability

| Potential acquirer | What they're missing | How SparkPilot fills it |
|---|---|---|
| **Flexera/Spot** | Governance layer for Ocean for Apache Spark — they do runtime optimization but no RBAC, no audit, no budget enforcement, no preflight | Pre-dispatch governance + cost attribution |
| **Databricks** | Unity Catalog does data governance, not workload governance. No pre-dispatch budget enforcement. No CUR-reconciled cost attribution per team. | Workload governance for managed Spark |
| **FinOps vendors (Finout, nOps, Zesty)** | They show what you spent — past tense. None do "stop you before you overspend." | Real-time budget enforcement + pre-dispatch gates |
| **Platform tools (Rafay, Humanitec)** | Internal developer platforms for K8s. No data workload governance. | Data compute governance module |
| **AWS** | EMR Studio is a notebook IDE, not a governance plane. EMR-on-EKS cost attribution is "challenging and non-trivial" by AWS's own docs. | Could be an EMR Studio add-on or AWS Marketplace listing |

### The pitch to an acquirer

Not "we built a Spark control plane."

**"We built the only pre-dispatch governance and cost control layer for data compute workloads on AWS, with real-time budget enforcement, CUR-reconciled cost attribution, multi-tenant RBAC, and native integrations into Airflow and Dagster. The architecture supports EMR on EKS, EMR Serverless, EMR on EC2, and Databricks on AWS. Spark is just the first workload."**

---

## Part 11: Codebase Summary

| Area | Lines | Key files |
|---|---|---|
| **Core Python services** | 9,048 | api.py (861), aws_clients.py (892), models.py (311), schemas.py (278), config.py (154), workers.py (59), services/ (3,867) |
| **Orchestrator providers** | 2,135 | Airflow (1,122 across hook/operator/sensor/trigger), Dagster (1,013 across client/resource/ops/assets) |
| **Tests** | 6,160 | 188 tests across 17 files. SQLite in-memory + mocked AWS + RSA-signed JWT test harness. |
| **UI** | ~3,200 | Next.js 14+ App Router. 6 pages, 7 components, 6 lib modules. OIDC PKCE flow. |
| **Infrastructure** | ~1,100+ | Terraform control-plane (945), Terraform full-BYOC (173 + community EKS module), 2 CloudFormation templates |
| **CLI** | 317 | Admin CLI for local development and smoke testing |
| **E2E Matrix Framework** | 860 | Scenario generation, cost estimation, coverage tracking |

**Total first-party code: ~22,000+ lines**

### Single artifact of proof

One set of live AWS artifacts from account 787587782916, dated March 1–3, 2026. Contains: STS caller identity, EKS node group metadata, EMR virtual cluster creation, multi-tenant concurrent run evidence (2 tenants, 6 runs, real EMR job run IDs, isolation assertions all pass), preflight snapshots, CloudWatch log captures.

This proves the core dispatch/reconcile loop works. It does not prove production readiness, scale, reliability, or that any of the edge cases (budget breach, IAM misconfiguration detection, CUR reconciliation, provider integrations) work in the real world.

---

## Part 12: The Honest Bottom Line

The code is well-structured and demonstrates real engineering thinking. It follows good patterns: state machines, idempotency with DB-level locking, audit trails on every mutation, error classification, retry logic, OIDC verification. The architecture is sound for expansion to multiple backends.

**It is not production-grade.** It has been tested once on real AWS, by one person, in one account, on one day. Most subsystems have only been validated against mocks. The Airflow and Dagster providers have never been run against real orchestrators. CUR reconciliation has never seen a real CUR table. The OIDC flow has never been tested against a real identity provider. No load testing, no multi-customer deployment, no CI/CD pipeline, no production monitoring.

The competitive position is genuinely unoccupied. No other product in this space gates at pre-dispatch with this combination of IAM validation, budget enforcement, and orchestrator-native integration. The "workload contracts" framing translates the existing engineering into a product story that executives, platform leads, and finance can understand.

The most urgent problem is not architecture, not positioning, not which backend to add next. **Nobody is using it.** Every strategic question — contracts, CI/CD gates, FinOps layer, acquisition — is hypothetical until someone other than the developer submits a run through this system and gets value from it.
