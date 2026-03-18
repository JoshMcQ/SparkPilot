# ADR-002: Vertical Autoscaling (VPA) — Product Scope Decision

**Status:** Accepted
**Date:** 2026-03-17
**Deciders:** SparkPilot product and engineering leadership
**Issues:** #55

---

## Problem

Amazon EMR on EKS runs Spark pods on Kubernetes, and Kubernetes supports the Vertical Pod Autoscaler (VPA) for automatically right-sizing pod resource requests. Should SparkPilot integrate VPA-aware scheduling, read VPA recommendations, or influence VPA configuration as part of its preflight and golden-path systems?

---

## Decision

**ADVISORY ONLY for v1.x — no VPA-aware scheduling or recommendation integration.**

SparkPilot will not attempt to read VPA recommendations, configure VPA objects, or adjust scheduling decisions based on VPA state. SparkPilot's golden-path resource profiles remain the authoritative right-sizing mechanism in v1.x.

SparkPilot will add targeted observability hooks and a preflight compatibility warning to surface VPA-related issues without taking control of the VPA layer.

---

## Rationale

**VPA and running pods are incompatible.** Kubernetes VPA can only resize pod resources on pod restart. It cannot resize a running Spark driver or executor. Because Spark pods are short-lived (executor lifetimes are bounded by job duration), VPA recommendations apply to *future* pods, not the current run. This fundamentally limits VPA's utility in a Spark scheduling context.

**VPA and HPA conflict.** Running both VPA (vertical scaling) and Horizontal Pod Autoscaler (HPA) on the same workload is unsupported by Kubernetes for CPU/memory metrics. Some customer clusters use HPA for node-level autoscaling; SparkPilot should not create implicit conflicts by enabling VPA-aware behavior.

**Golden-path profiles already solve right-sizing.** SparkPilot's resource profiles provide opinionated, validated starting points for driver/executor sizing based on workload class (small, medium, large, memory-intensive). These profiles are calibrated against real workload patterns and provide better signal than generic VPA historical averaging for batch Spark jobs.

**Complexity without clear signal improvement.** Reading VPA recommendations requires watching VPA custom resources (`VerticalPodAutoscaler` CRDs) from the SparkPilot control plane. This adds a Kubernetes API dependency, requires RBAC grants to read VPA objects, and introduces coupling to a CRD that may not be installed in all customer clusters. The signal improvement over golden-path profiling is unclear for batch workloads.

---

## Observability Hooks

While SparkPilot will not control or read VPA recommendations, it will emit metadata to help operators compare allocated resources against VPA recommendations externally:

- **`requested_resources` in run metadata.** Each run record includes the driver and executor resource requests as submitted. Operators can compare these against VPA `status.recommendation` using their own tooling (CloudWatch Insights, Grafana, etc.).
- **VPA compatibility preflight warning.** A new preflight check (`_check_vpa_compat`) emits a WARNING (not a BLOCK) if VPA admission controller behavior is detected in combination with configuration patterns that may be adversely affected.

### Preflight check: `_check_vpa_compat`

Location: `src/sparkpilot/services/preflight.py`

The check function `_check_vpa_compat(env, spark_conf)` emits a `warning` (not `fail`) status if `spark.kubernetes.allocation.batch.size` is configured at a very low value alongside a VPA-affected environment. This is an observable signal — it does not block job submission.

The check is intentionally conservative (warning only) because:

1. Not all customer clusters have VPA installed.
2. VPA admission webhooks may or may not be active for the EMR on EKS namespace.
3. Low batch sizes are sometimes intentional (e.g., gradual executor ramp-up on constrained clusters).

The warning prompts operators to review their VPA admission controller configuration when they see unusual resource allocation behavior.

---

## Documentation

Customer-facing guidance will cover:

- VPA for Spark pods is most useful for improving *future run* resource requests, not the current run.
- If VPA is installed in the EMR on EKS namespace, set VPA mode to `Off` or `Initial` for Spark workloads; `Auto` mode can cause pod evictions during job execution.
- Use SparkPilot's golden-path profiles as the primary right-sizing mechanism. Treat VPA recommendations as a secondary signal for profile calibration over time.
- The `requested_resources` field in run metadata can be exported and compared against VPA recommendations in your monitoring stack.

---

## Future Consideration

If customer demand emerges for VPA-integrated scheduling (e.g., automatically applying VPA recommendations to golden-path profile overrides), revisit as a targeted enhancement in v2.x. Potential implementation path: SparkPilot reads `VerticalPodAutoscaler` status objects and surfaces recommendations in the environment detail view as advisory guidance, with operator opt-in to auto-apply.

---

## Acceptance Criteria

- [x] Decision is documented and rationale is clear
- [x] Observability hooks are defined (`requested_resources` in run metadata)
- [x] Preflight check `_check_vpa_compat` is specified and implemented as WARNING only
- [x] Customer-facing documentation guidance is included
