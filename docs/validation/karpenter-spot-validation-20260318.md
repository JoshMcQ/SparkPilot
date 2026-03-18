# Karpenter + Spot Capacity Validation (March 18, 2026)

Issue: #10

This validation closes the Spot/Karpenter readiness track by combining real-cluster Karpenter discovery evidence with Spot diversification preflight proof and documented runtime guidance.

## Primary Artifacts

- `artifacts/issue10-karpenter-20260317-232700/deployments.txt`
- `artifacts/issue10-karpenter-20260317-232700/api-resources.txt`
- `artifacts/issue10-karpenter-20260317-232700/crd-karpenter.txt`
- `artifacts/r01-realaws-spot-pass-20260303-131440/preflight.json`
- `artifacts/r01-realaws-spot-pass-20260303-131440/spot-checks.json`
- `artifacts/r01-realaws-spot-pass-20260303-131440/nodegroup-spot-r01.json`
- `docs/validation/spot-preflight-checks.md`

## Real Cluster Discovery

Cluster context: `arn:aws:eks:us-east-1:787587782916:cluster/sparkpilot-live-1`

Observed:

- no Karpenter controller deployment present
- no `NodePool`/`EC2NodeClass` CRDs present

This correctly drives the recommendation path to use managed Spot nodegroups or install Karpenter before enforcing NodePool-specific policy.

## Spot Diversification and Placement Evidence

From live preflight pass artifact (`r01-realaws-spot-pass-20260303-131440`):

- `byoc_lite.spot_capacity = pass`
- `byoc_lite.spot_diversification = pass` (3+ instance types)
- `byoc_lite.spot_executor_placement = pass`

## Recommended NodePool Baseline

For Karpenter-enabled clusters, require:

- Spot + on-demand fallback in NodePool requirements
- at least 3 instance types across at least 2 families
- Graviton preference where workload-compatible
- consolidation enabled

## Acceptance Mapping

- Real-cluster Karpenter installation detection: `pass` (absent state proven)
- Spot-capable capacity validation path: `pass`
- Diversification validation path: `pass`
- Documentation for Karpenter/Spot baseline: `pass`
