Closing with acceptance criteria met.

Deployment baseline evidence:
- docs/deployment.md
- infra/terraform/control-plane/main.tf
- scripts/terraform/deploy_control_plane.sh
- scripts/smoke/control_plane_api.sh

Live-AWS operational evidence:
- docs/validation/live-byoc-lite-real-aws-proof-20260305.md
- docs/validation/second-operator-real-aws-pilot-20260318.md

Acceptance mapping:
- Non-local environment runs end-to-end reliably: pass
- Core service SLI/health and diagnostics surfaces documented: pass
- Recovery and deployment runbook paths documented: pass

Current validation snapshot: python -m pytest -q => 244 passed, 1 skipped (March 18, 2026).
