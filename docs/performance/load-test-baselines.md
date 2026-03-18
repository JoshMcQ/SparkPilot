# SparkPilot Load Test Baselines

## Overview

This document describes the load and concurrency correctness test methodology for SparkPilot,
baseline performance targets, and instructions for running and interpreting results.

---

## Test Methodology

SparkPilot has two complementary load test artifacts:

| Artifact | Purpose | Location |
|---|---|---|
| `tests/test_load_concurrent_submissions.py` | In-process concurrency correctness test (no real AWS) | `tests/` |
| `scripts/dev/load_test_live.py` | Live API throughput test against a real deployment | `scripts/dev/` |

### In-Process Concurrency Test (`test_load_concurrent_submissions.py`)

Uses an in-memory SQLite database and `fastapi.testclient.TestClient` (ASGI, no network).
Spawns real Python threads to exercise concurrent write paths.

**What it verifies:**
- 50 concurrent run submissions (10 threads × 5 teams) complete without DB integrity errors
- Idempotency keys prevent duplicate run creation under serial and concurrent (racing) conditions
- All unique submissions receive a valid run ID in the response
- Throughput is logged for trend tracking

**Not tested here:** real EMR/AWS dispatch, true network latency, OS-level socket concurrency.

### Live Load Test (`scripts/dev/load_test_live.py`)

Sends real HTTP requests to a running SparkPilot instance. Requires a pre-created job ID and
a valid bearer token. Reports per-request latencies and checks them against the baseline targets.

---

## Baseline Targets

| Metric | Target | Notes |
|---|---|---|
| Run submission p50 latency | < 200ms | Measured from client send to response received |
| Run submission p95 latency | < 500ms | Under concurrent load (50 parallel submissions) |
| Time-to-dispatch (queued → accepted) | < 30s | Depends on scheduler poll interval (default: 15s) |
| Throughput | ≥ 10 submissions/sec | In-process SQLite; higher expected with PostgreSQL |

These targets apply to a single-region deployment with PostgreSQL and default scheduler settings.
SQLite (dev/test mode) will show lower throughput due to write serialization.

---

## How to Run

### In-Process Correctness Test

```bash
# From the repo root
python -m pytest tests/test_load_concurrent_submissions.py -v -s
```

The `-s` flag enables stdout so throughput numbers are printed.

Expected output includes lines like:
```
Load test: 50 submissions in 1.23s → 40.7 submissions/sec
Throughput test: 20 submissions in 0.61s → 32.8 submissions/sec
```

### Live Load Test

Prerequisites:
- A running SparkPilot API (staging or production)
- A valid bearer token with at least `user` role
- An existing job ID in the target environment

```bash
python scripts/dev/load_test_live.py \
  --base-url https://api.sparkpilot.example.com \
  --token <bearer-token> \
  --job-id <job-id> \
  --teams 5 \
  --runs-per-team 10
```

Optional arguments:
- `--teams N` — number of simulated teams (default: 5)
- `--runs-per-team N` — runs submitted per team (default: 10)
- `--timeout N` — per-request timeout in seconds (default: 30)

---

## How to Interpret Results

### Latency

The live test reports p50, p95, and p99 latencies for the run submission endpoint
(`POST /v1/jobs/{job_id}/runs`). This measures wall-clock time from the client's perspective
including network round-trip, API handler, DB write, and idempotency check.

- **p50 < 200ms** — healthy; the common case is fast
- **p95 < 500ms** — acceptable; tail latency stays bounded under load
- **p99 > 1000ms** — investigate DB lock contention, connection pool exhaustion, or scheduler backpressure

### Throughput

Throughput drops significantly if:
- The DB connection pool is exhausted (increase `pool_size` in SQLAlchemy config)
- SQLite is used in production (use PostgreSQL)
- The API instance is CPU-constrained (scale horizontally or vertically)

### Idempotency

The test confirms that racing requests with the same `Idempotency-Key` produce exactly one
run record in the database. If this assertion fails, there is a race in the idempotency
record creation path — check `src/sparkpilot/idempotency.py` and DB unique constraints.

### Time-to-Dispatch

Time-to-dispatch is governed by the scheduler poll interval (`SPARKPILOT_POLL_INTERVAL_SECONDS`,
default 15s). The < 30s target allows for one missed poll cycle. To reduce dispatch latency:
- Lower `SPARKPILOT_POLL_INTERVAL_SECONDS` (minimum recommended: 5s)
- Increase scheduler worker concurrency

---

## Updating Baselines

After any significant infrastructure change (instance type, DB tier, region), re-run the live
load test and update the baseline numbers in this file. Include the test date, deployment details
(instance type, DB size, region), and the new measured p50/p95 values.

| Date | Environment | p50 | p95 | Throughput |
|---|---|---|---|---|
| 2026-03-17 | dev/SQLite (in-process) | N/A | N/A | ~30-50 sub/sec |
