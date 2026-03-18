# CUR Reconciliation Live Athena Validation (March 18, 2026)

Issue: #67

This validation executed reconciliation against a live Athena table on S3 using CUR-compatible columns and a mixed pricing sample (On-Demand, Spot, Savings Plans covered usage, Reserved).

## Primary Artifacts

- `artifacts/issue67-cur-20260317-231046/summary.json`
- `artifacts/issue67-cur-20260317-231046/athena_queries.json`

## Athena Context

- AWS account: `787587782916`
- Region: `us-east-1`
- Database: `sparkpilot_issue67_20260317231046`
- Table: `cur_live_20260317231046`
- Query output: `s3://sparkpilot-live-787587782916-20260224203702/issue67/20260317-231046/athena-results/`

## Query Execution IDs

- create database: `e09aaf9c-5968-494e-beff-b9de1c929c89`
- drop table: `c8267c97-db6f-495a-81b3-afc59d00174e`
- create table: `25f44d23-536a-4dae-8e3e-97cceb40d0bf`
- row-count probe: `e0a4f076-a5e8-44b5-91d0-d23f404e4a5f`
- edge-case mix summary: `96435093-0831-42ed-8aaf-cf64e302fe12`
- reconciliation worker query: `5168189d-7026-4aca-9cb2-2ab227f34f3b`

## Reconciliation Result

- Rows in Athena dataset: `4`
- Reconciliation changed rows: `4`
- Audit event recorded with:
  - `action=cost.cur_reconciliation`
  - `query_execution_id=5168189d-7026-4aca-9cb2-2ab227f34f3b`

## Before/After Allocation Snapshot

Runs reconciled:

- `8d1d5d68-9e6a-4f66-b51b-2b8fa8e31851`: `15000` micros
- `79c5a1e4-5eb8-4ab1-a69d-b6ea17d5f3fa`: `10000` micros
- `d3d8cc0f-f5cd-42a8-8cf9-9ef7b91688d9`: `8000` micros
- `b4b7bcbf-a7f3-4db5-b623-3f8ebf4e0f3e`: `4000` micros

Each run moved from `actual_cost_usd_micros=null` to populated actual cost with `cur_reconciled_at` timestamp.

## Variance Threshold

- Threshold: `<= 1` micro
- Observed max variance: `0` micros
- Threshold status: `pass`

## Acceptance Mapping

- Real Athena reconciliation run with concrete query IDs: `pass`
- Edge-case pricing mix included and summarized: `pass`
- Before/after allocation evidence with run IDs: `pass`
- Variance threshold documented and met: `pass`
