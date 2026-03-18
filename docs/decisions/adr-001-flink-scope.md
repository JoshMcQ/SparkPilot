# ADR-001: Flink on EMR on EKS — Product Scope Decision

**Status:** Accepted
**Date:** 2026-03-17
**Deciders:** SparkPilot product and engineering leadership
**Issues:** #54

---

## Problem

Amazon EMR on EKS supports Apache Flink natively as a managed runtime. Should SparkPilot extend its platform support to include Flink job lifecycle management alongside Spark?

---

## Decision

**OUT OF SCOPE for SparkPilot v1.x.**

SparkPilot will remain Spark-only for the v1.x release line. The platform's value proposition is opinionated Spark operations: preflight validation, cost attribution, golden-path resource profiles, and lifecycle management for discrete batch jobs submitted via the EMR on EKS API. Flink is explicitly excluded from this scope.

---

## Rationale

Flink has a fundamentally different operational model from Spark across every dimension that SparkPilot manages:

**Job model.** Flink jobs are primarily streaming applications with potentially unbounded execution. Spark jobs, even structured streaming jobs, are submitted as discrete job runs with a defined start and end event. SparkPilot's lifecycle state machine (PENDING → RUNNING → COMPLETED/FAILED) is designed around discrete runs.

**Lifecycle.** Flink applications are long-running processes; a "job" may run for days, weeks, or indefinitely. SparkPilot's reconciliation workers, heartbeat tracking, and run duration attribution assume finite runs. Supporting Flink would require a parallel reconciliation path with savepoint awareness and restart semantics.

**Resource management model.** Flink uses TaskManagers with slot-based parallelism; Spark uses dynamic executor allocation against Kubernetes node pools. SparkPilot's golden-path profiles (driver/executor resource presets) are specific to Spark's executor model and do not translate to Flink TaskManager sizing.

**Cost attribution.** SparkPilot's FinOps model attributes cost per run using start/end timestamps and instance-hour billing. Flink streaming jobs have no natural "run ended" event for unbounded streams. Cost attribution for long-running Flink applications requires a fundamentally different model (e.g., continuous metering vs. run-scoped attribution).

**Observability.** SparkPilot integrates with the Spark History Server and EMR on EKS job metrics. Flink exposes metrics via the Flink Web UI and Flink REST API — a distinct integration surface requiring separate telemetry pipelines.

**Orchestrator providers.** The Airflow and Dagster provider operators are built around `StartJobRun` / `CancelJobRun` API semantics. Flink job management on EMR on EKS uses a different API surface and would require separate operator primitives.

Supporting Flink would not extend SparkPilot — it would require building a parallel product track alongside it. This scope expansion would dilute focus without serving the primary buyer persona: data platform engineers running batch and micro-batch Spark workloads on EMR on EKS.

---

## Customer Guidance

Customers running Flink on EMR on EKS should:

1. Use the **EMR on EKS console or API directly** to submit and manage Flink jobs (`StartJobRun` with `releaseLabel` referencing a Flink release).
2. Wrap Flink job submission in their orchestrator (Apache Airflow, Dagster, Prefect) **without SparkPilot**. The EMR on EKS Airflow operator supports Flink job types natively.
3. For monitoring, use the **Flink Web UI** exposed through the EMR on EKS Flink application endpoint, or forward Flink metrics to CloudWatch using the EMR metrics integration.

SparkPilot will not attempt to intercept, manage, or validate Flink job submissions. Flink jobs submitted to the same EMR virtual cluster as Spark jobs are not visible to or managed by SparkPilot.

---

## Future Consideration

If explicit customer demand materializes for managed Flink lifecycle within SparkPilot, revisit as a **separate product initiative** — not an extension of SparkPilot v1.x. Any future Flink support should be tracked as a distinct product track with its own lifecycle model, cost attribution design, and provider primitives. This ADR does not preclude a future `SparkPilot Streaming` or similar product line.

**Trigger for revisit:** Three or more enterprise customers explicitly requesting Flink lifecycle management through SparkPilot with documented use cases.

---

## Acceptance Criteria

- [x] Decision is documented and rationale is clear
- [x] Customer guidance is provided for teams running Flink on EMR on EKS
- [x] Future revisit criteria are defined
