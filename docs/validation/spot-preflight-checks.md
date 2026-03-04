# R01: Spot Preflight Validation

Date: March 3, 2026

## Summary

Spot readiness preflight checks are implemented and validated with real AWS evidence for both warning and pass paths.

## Checks Implemented

- `byoc_lite.spot_capacity`
- `byoc_lite.spot_diversification`
- `byoc_lite.spot_executor_placement`

## Real AWS Evidence

Warning-path evidence (ON_DEMAND baseline):

- `artifacts/r01-realaws-direct-20260303-114200/preflight.json`
- `artifacts/r01-realaws-direct-20260303-114200/nodegroup.json`

Pass-path evidence (Spot-capable nodegroup with 3 instance types):

- `artifacts/r01-realaws-spot-pass-20260303-131440/preflight.json`
- `artifacts/r01-realaws-spot-pass-20260303-131440/spot-checks.json`
- `artifacts/r01-realaws-spot-pass-20260303-131440/nodegroup-spot-r01.json`

Observed pass statuses:

- `byoc_lite.spot_capacity = pass`
- `byoc_lite.spot_diversification = pass`
- `byoc_lite.spot_executor_placement = pass`

## Test Evidence

- Unit/integration coverage in `tests/test_api.py` and `tests/test_aws_clients.py`.
- Full suite: `python -m pytest -q tests -p no:cacheprovider` -> `75 passed`.
