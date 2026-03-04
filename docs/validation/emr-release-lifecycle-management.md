# EMR Release Lifecycle Management Validation

## Scope
Validation evidence for roadmap item `R04`.

## Implemented
- `EmrRelease` model for release catalog + lifecycle status.
- Sync routine: `sync_emr_releases_once`.
- Worker mode: `python -m sparkpilot.workers emr-release-sync --once`.
- API endpoint: `GET /v1/emr-releases`.
- Preflight check: `config.emr_release_currency` (pass/warning/fail based on lifecycle).

## Real AWS evidence (March 3, 2026)
- AWS source query:
  - `aws emr list-release-labels --region us-east-1 --max-results 50`
- Artifacts:
  - `artifacts/r04-realaws-20260303-115025/emr-list-release-labels.json`
  - `artifacts/r04-realaws-20260303-115025/sync-summary.json`
  - `artifacts/r04-realaws-20260303-115025/api-emr-releases.json`

## Test coverage
- `tests/test_api.py::test_emr_release_sync_and_list_endpoint`
- `tests/test_api.py::test_preflight_warns_for_deprecated_release_label`
- `tests/test_aws_clients.py::test_list_release_labels_uses_pagination`

Suite result:
- `python -m pytest -q tests -p no:cacheprovider` -> `55 passed`
