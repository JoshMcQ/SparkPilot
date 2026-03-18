# SparkPilot Operational KPI Definitions

This document defines each KPI metric returned by `GET /v1/metrics/kpis`.

All metrics are computed over a configurable time window (default: last 30 days). The window is expressed as `window_start` (ISO 8601) in every response object.

---

## 1. Preflight Outcome Rates

**API key**: `preflight_outcome_rates`

**Definition**: Counts of runs that passed, failed, or triggered a dispatch retry during the preflight phase, expressed as absolute counts and percentages of all evaluated runs.

**Measurement methodology**: Queries `audit_events` for the following action values:
- `run.preflight_passed` — run cleared all preflight checks and was dispatched
- `run.preflight_failed` — run was blocked at preflight (e.g. budget exceeded, quota violation)
- `run.dispatch_retry_scheduled` — run passed preflight but dispatch failed transiently and was rescheduled

**Fields**:

| Field | Type | Description |
|---|---|---|
| `window_start` | ISO 8601 string | Start of the measurement window |
| `window_end` | ISO 8601 string | End of the measurement window (now) |
| `total_evaluated` | int | Total audit events across all three preflight actions |
| `preflight_pass_count` | int | Runs that cleared preflight |
| `preflight_block_count` | int | Runs blocked at preflight |
| `preflight_pass_rate_pct` | float | `pass / total * 100` |
| `preflight_block_rate_pct` | float | `block / total * 100` |

**Baseline target**: `preflight_pass_rate_pct >= 90%`

**How to interpret**: A high block rate indicates budget guardrails or quota limits are frequently hit. Investigate team budgets (`/v1/team-budgets`) and capacity configuration if the block rate climbs above 10%.

---

## 2. Dispatch Success Rate

**API key**: `dispatch_success_rate`

**Definition**: Fraction of submitted runs that reached the `succeeded` terminal state within the measurement window.

**Measurement methodology**: Counts rows in the `runs` table by `state` where `created_at >= window_start`.

**Fields**:

| Field | Type | Description |
|---|---|---|
| `window_start` | ISO 8601 string | Start of the measurement window |
| `window_end` | ISO 8601 string | End of the measurement window |
| `total_runs` | int | All runs submitted in the window |
| `succeeded` | int | Runs that reached `succeeded` state |
| `failed` | int | Runs that reached `failed` state |
| `success_rate_pct` | float | `succeeded / total * 100` |

**Baseline target**: `success_rate_pct >= 85%`

**How to interpret**: A success rate below 85% warrants investigation into driver failures, spot interruptions, or misconfigured job artifacts. Cross-reference with `terminal_outcome_distribution` to see whether failures, cancellations, or timeouts dominate.

---

## 3. Queue-to-Running Latency (P50 / P95)

**API key**: `queue_to_running_latency`

**Definition**: Distribution of the time between a run's creation (`created_at`) and when the Spark driver started (`started_at`). P50 and P95 percentiles are reported in seconds.

**Measurement methodology**: Joins `runs` rows where `started_at IS NOT NULL` and `created_at >= window_start`, computes `(started_at - created_at).total_seconds()`, then sorts the list and selects the 50th and 95th percentile values.

**Fields**:

| Field | Type | Description |
|---|---|---|
| `p50_seconds` | float or null | Median queue-to-running latency in seconds |
| `p95_seconds` | float or null | 95th-percentile queue-to-running latency |
| `sample_count` | int | Number of runs included in the calculation |

**Baseline target**: `p50_seconds <= 60`, `p95_seconds <= 300`

**How to interpret**: Elevated P95 latency indicates scheduling bottlenecks (e.g. warm-pool exhaustion, Kubernetes scheduling delays, EMR container startup). If P95 exceeds 5 minutes, review environment capacity, warm-pool configuration, and Yunikorn queue guarantees.

---

## 4. Budget Guardrail Trigger Frequency

**API key**: `budget_guardrail_triggers`

**Definition**: How frequently the budget guardrail system blocked or warned on run submissions within the measurement window.

**Measurement methodology**: Queries `audit_events` for:
- `run.budget_blocked` — run blocked because the team's monthly budget was at or above the block threshold
- `run.budget_warned` — run proceeded with a warning because the team's budget reached the warn threshold

**Fields**:

| Field | Type | Description |
|---|---|---|
| `window_start` | ISO 8601 string | Start of the measurement window |
| `budget_block_count` | int | Number of times a run was blocked by budget guardrail |
| `budget_warn_count` | int | Number of times a run triggered a budget warning |

**Baseline target**: `budget_block_count == 0` (no surprise blocks)

**How to interpret**: Any non-zero `budget_block_count` requires attention. Review the affected team's budget allocation (`/v1/team-budgets`) and consider increasing monthly budget or reducing run frequency. Elevated `budget_warn_count` is an early warning to act before blocks occur.

---

## 5. Terminal Outcome Distribution

**API key**: `terminal_outcome_distribution`

**Definition**: Breakdown of runs by their terminal state within the measurement window.

**Measurement methodology**: Counts `runs` rows by `state` for the four terminal states where `created_at >= window_start`.

**Fields**:

| Field | Type | Description |
|---|---|---|
| `window_start` | ISO 8601 string | Start of the measurement window |
| `succeeded` | int | Runs that completed successfully |
| `failed` | int | Runs that terminated with a failure |
| `cancelled` | int | Runs that were cancelled by a user or operator |
| `timed_out` | int | Runs that exceeded their configured timeout |

**Baseline target**: `succeeded / (succeeded + failed + cancelled + timed_out) >= 85%`

**How to interpret**: A high `timed_out` count suggests runs are configured with too short a timeout or are experiencing performance regressions. A high `failed` count warrants reviewing driver logs for recurring error patterns. Occasional `cancelled` counts are expected from normal operator interventions.

---

## Accessing the Endpoint

```
GET /v1/metrics/kpis
Authorization: Bearer <admin-token>
```

Requires `role == "admin"`. Returns a JSON object containing all five KPI sub-objects. Example response structure:

```json
{
  "preflight_outcome_rates": { ... },
  "dispatch_success_rate": { ... },
  "queue_to_running_latency": { ... },
  "budget_guardrail_triggers": { ... },
  "terminal_outcome_distribution": { ... }
}
```

The Python function `collect_all_kpis(db, since=since)` in `src/sparkpilot/metrics.py` can also be called directly in scripts or tests.
