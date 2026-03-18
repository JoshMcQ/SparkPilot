# SparkPilot External Brief (Customers and Investors)

Last updated: March 16, 2026

## 1) What SparkPilot Is

SparkPilot is an AWS-first control plane for data compute workloads, starting with Spark on EMR. It sits before job dispatch and enforces workload contracts: identity, policy, cost, and runtime readiness checks that must pass before compute spend starts.

In practical terms, SparkPilot gives platform teams:
- Governed self-service for data engineers
- Pre-dispatch reliability and IAM validation
- Team-scoped access control and audit trails
- Per-run cost attribution with CUR reconciliation paths

The core positioning is simple: most tools optimize during or after a run, while SparkPilot focuses on preventing bad runs before they start.

## 2) Problem and Market Gap

Today, teams typically choose between:
- Direct EMR API/CLI use from orchestration tools (fast, low governance)
- Building an internal platform (high control, high engineering cost)
- Adopting managed platforms with a different control and billing model

The recurring failure mode is not just runtime inefficiency. It is dispatching work that should have been blocked:
- Broken IAM trust or pass-role chains
- Namespace and environment readiness issues
- Out-of-policy Spark configuration
- Budget and governance boundary violations

SparkPilot targets this pre-dispatch gap with enforceable checks, deterministic state handling, and auditability.

## 3) Product Scope Today

### Available product surface

- API control plane for tenants, teams, environments, jobs, runs, budgets, and audit
- Preflight checks across IAM, OIDC association, namespace validity, release posture, Spot readiness, and policy-like controls
- Run lifecycle orchestration with retries, cancellation, timeout handling, and reconciliation
- RBAC model (admin/operator/user) with team and environment scope controls
- Run diagnostics and log retrieval paths
- Cost and usage attribution model with CUR reconciliation implementation
- Airflow and Dagster integration packages (implemented, not yet broadly field-validated)
- Web UI for operations, runs, cost views, and access administration

### Validation status (external-facing truth)

SparkPilot has real AWS proof for the core loop, but not broad production validation yet.

- Real AWS evidence exists for:
  - BYOC-Lite provisioning flow
  - Real run dispatch/reconcile/log retrieval
  - Multi-tenant run evidence set in a non-production account
- Many subsystems remain validated primarily by tests/mocks and need further live validation:
  - CUR reconciliation edge cases
  - Real IdP interoperability matrix
  - Real Airflow/Dagster scheduler execution at runtime
  - Full-BYOC live infrastructure provisioning matrix

SparkPilot is at the transition point from "engineering-proven architecture" to "operationally proven product."

## 4) Why This Is Compelling

### For platform and data teams

- Reduce failed or non-compliant dispatches before compute starts
- Standardize environment and run governance without forcing a full internal platform build
- Keep data plane and compute in customer AWS boundaries

### For finance and leadership

- Build a deterministic control layer around expensive compute workflows
- Move from after-the-fact cost discussion toward enforceable guardrails at submission time
- Create traceability from actor to run to cost and audit events

### For strategic buyers/investors

- Clear product wedge: pre-dispatch governance for data workloads
- Expansion path across AWS backends (EMR Serverless, EMR on EC2, Databricks on AWS)
- Architecture already separated enough to support additional execution backends without a rewrite

## 5) Business Model and Go-to-Market Direction

Initial commercial motion is design-partner driven with platform teams running Spark workloads on AWS.

Target customer profile:
- Mid-market and enterprise teams with recurring Spark workloads
- Existing EMR on EKS or adjacent AWS data platform footprint
- Strong need for governed self-service and spend accountability

Initial packaging direction:
- Control plane subscription with environment and usage tiers
- Design-partner onboarding with explicit live-success criteria
- Land via one workload, expand through team scope and policy coverage

## 6) 6-12 Month Product Direction

Priority sequencing:
1. Complete real-AWS validation gaps (second-operator loop, misconfiguration matrix, CUR proof, real IdP and orchestrator validation)
2. Productize workload contracts with configurable policy engine (not only hardcoded checks)
3. Expand backend coverage within AWS:
   - EMR Serverless
   - EMR on EC2
   - Databricks on AWS

This sequence de-risks adoption first, then expands TAM.

## 7) Risk Posture (Explicit)

SparkPilot is not presented as fully production-mature today. The key open risk is validation breadth, not architecture direction.

Primary near-term risks:
- Live-AWS evidence coverage across critical failure paths
- External IdP interoperability in production constraints
- Orchestrator runtime validation in real schedulers
- CUR real-data reconciliation edge-case behavior

Mitigation is active and tracked in GitHub with live-evidence closure gates.

## 8) Current Ask

### For customers (design partners)

- Run one governed workload end-to-end in non-production AWS
- Validate pre-dispatch controls, lifecycle handling, and cost visibility against your operational requirements

### For investors/strategic partners

- Evaluate SparkPilot as a pre-dispatch governance layer category play
- Engage on validation acceleration and GTM scale, not core architecture feasibility

