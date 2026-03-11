# CUR-Aligned Chargeback Progress (R03)

## Implemented
- New persistence models:
  - `CostAllocation`
  - `TeamBudget`
- Team budget APIs:
  - `POST /v1/team-budgets`
  - `GET /v1/team-budgets/{team}`
- Showback API:
  - `GET /v1/costs?team=<team>&period=YYYY-MM`
- Budget preflight integration:
  - `team_budget` check with pass/warning/fail based on configured thresholds and current-period spend.
- Cost allocation generation:
  - `_record_usage_if_needed` now writes `CostAllocation` (estimated path) per terminal run.
- CUR reconciliation worker:
  - `process_cur_reconciliation_once`
  - Worker CLI mode: `python -m sparkpilot.workers cur-reconciliation --once`
- EMR run tag propagation for attribution:
  - run/environment/team/project/cost-center/namespace/virtual-cluster tags added on `start_job_run`.
- Chargeback label propagation for Spark pods:
  - driver/executor labels (`sparkpilot-team`, `sparkpilot-project`, `sparkpilot-cost-center`, `sparkpilot-run-id`) are injected into Spark submit parameters for EKS attribution surfaces.
- Cost center policy surface:
  - `SPARKPILOT_COST_CENTER_POLICY_JSON` supports explicit mapping by namespace, virtual cluster id, team, and default fallback.
  - Example:
    ```json
    {
      "by_namespace": {"sparkpilot-finops-team": "cc-finops"},
      "by_virtual_cluster_id": {"vc-0123456789abcdef0": "cc-platform"},
      "by_team": {"<tenant-id>": "cc-shared"},
      "default": "cc-unmapped"
    }
    ```

## Automated Validation
- New tests in `tests/test_finops.py`:
  - budget endpoints + preflight fail threshold
  - showback endpoint payload
  - CUR reconciliation updates actual cost via Athena mock
- Full suite:
  - `python -m pytest -q tests -p no:cacheprovider` -> `75 passed`

## Real AWS Validation (March 3, 2026)
Artifacts:
- `artifacts/r03-realaws-20260303-122036/athena-workgroups.json`
- `artifacts/r03-realaws-20260303-122036/glue-databases.json`
- `artifacts/r03-realaws-20260303-122036/summary.json`
- `artifacts/r03-realaws-20260303-122036/showback-backfill-summary.json`

Observed account state:
- Athena workgroup present: `primary`
- Glue databases: none
- CUR catalog/table prerequisites are not present in this account yet; reconciliation worker returns `changed=0` until CUR Athena sources are configured.

Showback evidence:
- Backfilled one allocation from a real usage record in the live e2e database.
- `/v1/costs` returned team-period allocation data (`items=1`).

## Real AWS Athena/S3 Reconciliation Proof (March 3, 2026)
Artifacts:
- `artifacts/r03-realaws-cur-int-20260303-131710/athena-setup.json`
- `artifacts/r03-realaws-cur-int-20260303-131710/reconciliation-summary.json`

Validated flow:
- Created real Athena external table on S3 with CUR-compatible columns:
  - `resource_tags_user_sparkpilot_run_id`
  - `line_item_unblended_cost`
- Inserted run-linked cost row in S3 and queried via Athena.
- Ran `process_cur_reconciliation_once` against the real Athena dataset.
- Observed reconciliation update:
  - `changed=1`
  - `actual_cost_usd_micros=12345`
  - reconciliation audit event persisted.

## Remaining to close R03
- Wire billing-managed CUR delivery/catalog and run the same reconciliation path against production CUR tables.
