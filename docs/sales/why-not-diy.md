# Why Not DIY (Spark on AWS)

## Executive summary
AWS gives strong primitives for Spark on EKS, but it does not give you an opinionated multi-tenant control plane. SparkPilot adds preflight safety, standardized run submission, auditability, and cost attribution so platform teams stop operating an internal ticket queue.

## What AWS gives you
- EMR on EKS APIs and release labels.
- EKS + IAM building blocks (roles, OIDC, namespaces, node groups).
- Terraform/CDK building blocks.
- Reference documentation and blog architectures.

## What SparkPilot adds
- Run-ready preflight checks before dispatch (configuration, IAM/trust, OIDC, dispatch permissions, namespace/bootstrap checks, Spot readiness checks).
- Stable run lifecycle API (`queued -> accepted -> running -> terminal`) with retries/cancellation and reconciliation.
- Per-run logs/usage surfaces in one API/UI path.
- Tenant/environment scoping and audit events for every critical action.
- Golden-path standardization surface (tracked roadmap) to replace ad-hoc Spark config support.
- Productized FinOps path (tracked roadmap) for CUR-aligned showback and budget guardrails.

## Feature callouts often missing in DIY plans

- Preflight checks before dispatch (IAM, OIDC, trust, namespace, policy).
- Cost and job tracking with CUR-aligned reconciliation path.
- Control-plane auditability for critical API mutations.
- Golden-path templates and guardrails for repeatable submissions.
- Spot readiness and capacity troubleshooting guidance.
- Interactive endpoint management surface (tracked roadmap item R08).
- Lake Formation FGAC integration path (tracked roadmap item R09).
- Karpenter/queue-aware scaling alignment (tracked roadmap item R10 + R11).

## Build vs buy (realistic estimate)
If you build a Spark control plane in-house, typical effort is 6+ months of platform engineering:
- 4-8 weeks: provisioning orchestration + IAM/OIDC/trust hardening.
- 4-6 weeks: run state machine, retries, timeout/cancel paths, reconciliation.
- 3-5 weeks: observability + diagnostics + log normalization.
- 3-6 weeks: tenancy, RBAC, policy/guardrails, audit trail depth.
- 2-4 weeks: FinOps attribution and budget controls.
- Ongoing: AWS release drift, reliability fixes, and operator support load.

SparkPilot compresses this by shipping the control-plane layer as product work, while your team stays focused on data workloads.

## Chargeback note (verifiable)
AWS publishes a CUR + Kubecost pattern for Kubernetes/EMR cost allocation. SparkPilot roadmap item `R03` is explicitly aligned to that pattern (estimated vs reconciled actual cost, namespace/team attribution, showback APIs).

## Decision guidance
Choose DIY when:
- You already have a staffed internal platform team and want to own long-term maintenance.
- Governance requirements are highly custom and cannot be satisfied by product roadmap timelines.

Choose SparkPilot when:
- You need a self-serve Spark platform quickly.
- You want standardized guardrails, auditability, and cost controls without building/operating all control-plane components yourself.
