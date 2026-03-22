# Issue #46 — Dagster Real Orchestrator Run

**Date:** 2026-03-22
**Status:** PARTIAL — Dagster SparkPilotClient called live API; full Dagster orchestrator blocked

## What Ran Live

The `SparkPilotClient` from `dagster-sparkpilot 0.1.0` was called directly against the live SparkPilot API.

**Run ID:** `10f788e5-68d3-4c20-8b16-7d514bb6d3f1`
**EMR Job Run ID:** `0000000378n7i2ei6ls`
**Submitted via:** `SparkPilotClient.submit_run()` against `http://localhost:8000`
**State after dispatch:** `accepted` (dispatched to EMR on EKS)

## Blocker

Dagster is not installed (`pip show dagster` → not found). The `dagster_sparkpilot` package imports work but the `@op`, `@asset`, and `@resource` decorators require Dagster installed.

Full orchestrator run requires `pip install dagster>=1.8.0` and `dagster dev`.

## Files

| File | Description |
|------|-------------|
| `BLOCKER.md` | Infrastructure requirements for full Dagster execution |
| `EVIDENCE_SUMMARY.md` | This file |
