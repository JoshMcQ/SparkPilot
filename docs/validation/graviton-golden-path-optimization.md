# Graviton / ARM Optimization Validation

## Scope
Validation evidence for roadmap item `R02`.

## Implemented
- Environment architecture preference:
  - `EnvironmentCreateRequest.instance_architecture` (`x86_64`, `arm64`, `mixed`)
  - persisted in `environments.instance_architecture`
- Golden path architecture behavior:
  - arm64 paths inject arch selectors for driver/executor pod placement.
- Preflight compatibility check:
  - `config.graviton_release_support`
  - fails arm64 if release is not Graviton-capable, warns for mixed when unknown.
- Usage cost estimate differential by architecture:
  - arm64 discounted relative to x86 baseline.

## Test coverage
- `tests/test_api.py::test_create_golden_path_and_submit_run_with_golden_path`
- `tests/test_api.py::test_preflight_fails_arm64_when_release_not_graviton_capable`
- `tests/test_api.py::test_usage_cost_applies_arm64_discount`

Suite result:
- `python -m pytest -q tests -p no:cacheprovider` -> `57 passed`

## Real AWS evidence (March 3, 2026)
- Artifacts:
  - `artifacts/r02-realaws-20260303-115758/preflight-arm64.json`
  - `artifacts/r02-realaws-20260303-115758/preflight-x86.json`
  - `artifacts/r02-realaws-20260303-115758/summary.json`
- Summary:
  - `arm_graviton_check=pass`
  - `x86_graviton_check=pass`
