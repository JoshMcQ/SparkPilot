# Why Not EMR Serverless?

## Executive summary
EMR Serverless and EMR on EKS solve different operating models. SparkPilot is for teams that want Kubernetes-based control, multi-tenant cluster governance, and deeper platform controls on EMR on EKS.

## Side-by-side
| Topic | EMR Serverless | EMR on EKS + SparkPilot |
|---|---|---|
| Infrastructure operations | Minimal infra management | Requires EKS ownership, but more control |
| Spot strategy | No direct node-level Spot scheduling control | Spot-aware cluster policy and executor placement validation |
| Kubernetes standardization | Not Kubernetes-native | Native Kubernetes control plane and policies |
| Multi-tenant cluster controls | Limited to service boundaries | Namespace/team/environment controls and roadmap RBAC/policy engine |
| Interactive endpoints | Different workflow model | EMR on EKS managed endpoints in roadmap (`R08`) |
| Lake Formation FGAC | Depends on service capabilities/config | Explicit roadmap for FGAC validation and guardrails (`R09`) |
| Custom container/governance patterns | More constrained | EKS-native patterns (Karpenter, queueing, policy controls) |

## Where EMR Serverless wins
- Fastest time-to-first-job.
- No EKS lifecycle ownership.
- Strong fit for small/infrequent workloads where deep cluster governance is unnecessary.

## Where EMR on EKS + SparkPilot wins
- You need Kubernetes governance parity with other workloads.
- You require shared-cluster multi-tenancy controls and explicit guardrails.
- You want platform-level preflight, audit, and FinOps workflows around Spark job dispatch.

## Decision guidance
Choose EMR Serverless if:
- Your top requirement is zero cluster operations and minimal setup.
- Workloads are low volume or bursty and governance needs are modest.

Choose EMR on EKS + SparkPilot if:
- You run sustained multi-team Spark workloads on shared EKS.
- You need guardrails, policy surfaces, and cost-governed self-service beyond raw job submission.

## Positioning rule
This is not a "winner takes all" comparison. The practical recommendation is workload fit:
- Serverless for speed and simplicity.
- EKS + SparkPilot for control, governance, and extensibility.
