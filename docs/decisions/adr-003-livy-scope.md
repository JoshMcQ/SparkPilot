# ADR-003: Apache Livy on EMR on EKS — Product Scope Decision

**Status:** Accepted
**Date:** 2026-03-17
**Deciders:** SparkPilot product and engineering leadership
**Issues:** #56

---

## Problem

Amazon EMR on EKS supports Apache Livy as a REST-based interface for programmatic and interactive Spark submission. Should SparkPilot support Livy-based job submission as an alternative or complement to the EMR on EKS `StartJobRun` API?

---

## Decision

**DEFERRED — not in v1.x scope.**

SparkPilot v1.x dispatches exclusively via the EMR on EKS API (`StartJobRun` / `CancelJobRun`). Livy provides a fundamentally different session-based submission model and introduces security and operational complexity that is out of scope for v1.x.

---

## Rationale

### Architectural mismatch

SparkPilot's dispatch model is serverless: the control plane calls the EMR on EKS API, which provisions ephemeral pods through the EKS control plane. There is no persistent intermediary process.

Livy introduces a persistent Livy server process that acts as a gateway between clients and Spark sessions. This is architecturally incompatible with SparkPilot's current model in several ways:

- SparkPilot manages run lifecycle through EMR on EKS run state (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`). Livy sessions have their own state machine (`not_started`, `starting`, `idle`, `busy`, `shutting_down`, `dead`). Reconciling these two state machines is non-trivial.
- SparkPilot's `CancelJobRun` integration maps directly to EMR on EKS API calls. Cancelling a Livy session requires a separate REST call to the Livy server, which must be reachable from the SparkPilot control plane.
- Livy supports both batch jobs and interactive sessions (REPLs). SparkPilot's lifecycle model is designed for batch jobs; interactive sessions have no natural "run ended" event from the platform's perspective.

### Security implications

Livy requires a **running server with persistent network exposure**. This introduces a meaningful attack surface that SparkPilot's current architecture avoids:

- The Livy server must be reachable on a network port (typically 8998) from any client submitting jobs. In a multi-tenant environment, this requires careful network policy configuration to prevent cross-tenant access.
- SparkPilot's current model makes no outbound connections to customer infrastructure at job submission time — all dispatch goes through the AWS EMR control plane API. Adding Livy would require SparkPilot to make inbound connections to customer-managed network endpoints.
- Livy supports multiple authentication mechanisms (simple auth, Kerberos, LDAP). SparkPilot would need to manage and securely store credentials for each Livy server — a new credential management surface that does not exist today.
- The Livy server must be kept running, patched, and monitored. Customers would need to manage Livy server lifecycle (updates, restarts, HA) alongside the EMR on EKS cluster — additional operational burden.

### RBAC and multi-tenancy implications

Livy sessions use a **shared long-running driver pod**. Multiple users submitting code to the same Livy session run in the same JVM with the same IAM execution role. Per-user isolation requires Livy proxying (e.g., via Apache Knox or a custom proxy), which is complex to configure correctly and easy to misconfigure in ways that allow privilege escalation.

SparkPilot's current model provides strong per-run isolation: each job run gets its own driver pod with its own IAM role binding. Livy sessions erode this isolation boundary by design.

### Scope and focus

Livy is primarily used for interactive notebook-style workloads (Zeppelin, Jupyter) and programmatic session reuse. SparkPilot's primary buyer persona is data platform engineers running **batch Spark workloads** — discrete jobs with defined inputs, outputs, and completion events. Livy's session model optimizes for a different workload pattern.

---

## Customer Guidance

Teams needing Livy-style interactive Spark access should use **Amazon EMR Studio**, which provides a managed Livy endpoint with built-in authentication, notebook integration, and IAM-based access control. EMR Studio handles Livy server lifecycle, network configuration, and Kerberos/IAM authentication — removing the operational burden that makes self-managed Livy complex.

SparkPilot is the right tool for batch job lifecycle management. EMR Studio is the right tool for interactive notebook development.

For teams using SparkPilot for batch jobs and EMR Studio for interactive development, the two tools are complementary and share the same EMR on EKS virtual cluster.

---

## Future Consideration

If customer demand materializes for Livy-backed submission within SparkPilot, the recommended implementation path is:

1. Define a `engine: livy_on_eks` environment configuration that includes Livy server endpoint and authentication configuration.
2. Implement a Livy engine adapter that wraps `POST /batches` and `DELETE /batches/{batchId}` behind SparkPilot's existing `start_run` / `cancel_run` interface.
3. Map Livy batch state to SparkPilot run state machine (not Livy session state — batch mode avoids the shared-driver isolation problem).
4. Handle credential storage for Livy auth using SparkPilot's secrets management layer (to be designed).

This would preserve batch isolation while enabling Livy as an alternative dispatch mechanism for customers with existing Livy infrastructure investments.

**Trigger for revisit:** Two or more enterprise customers with documented existing Livy infrastructure requiring SparkPilot integration for batch workload management.

---

## Acceptance Criteria

- [x] Decision is documented as deferred with clear rationale
- [x] Security implications (persistent attack surface, network exposure) are documented
- [x] RBAC and multi-tenancy implications (shared driver pod isolation) are documented
- [x] Customer guidance directs interactive workloads to EMR Studio
- [x] Future implementation path (`engine: livy_on_eks`) is sketched for revisit
