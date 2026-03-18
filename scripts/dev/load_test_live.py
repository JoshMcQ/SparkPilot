#!/usr/bin/env python3
"""
Live load test for SparkPilot API.

Usage:
  python scripts/dev/load_test_live.py \
    --base-url https://api.sparkpilot.example.com \
    --token <bearer-token> \
    --job-id <job-id> \
    --teams 5 \
    --runs-per-team 10
"""
from __future__ import annotations

import argparse
import statistics
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import httpx


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SparkPilot live load test")
    parser.add_argument("--base-url", required=True, help="Base URL of the SparkPilot API")
    parser.add_argument("--token", required=True, help="Bearer token for authentication")
    parser.add_argument("--job-id", required=True, help="Job ID to submit runs against")
    parser.add_argument("--teams", type=int, default=5, help="Number of teams (default: 5)")
    parser.add_argument("--runs-per-team", type=int, default=10, help="Runs per team (default: 10)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Per-request timeout in seconds (default: 30)")
    return parser.parse_args()


def _submit_run(
    base_url: str,
    token: str,
    job_id: str,
    idempotency_key: str,
    actor: str,
    timeout: float,
) -> dict[str, Any]:
    """Submit a single run and return timing + result info."""
    url = f"{base_url.rstrip('/')}/v1/jobs/{job_id}/runs"
    headers = {
        "Authorization": f"Bearer {token}",
        "Idempotency-Key": idempotency_key,
        "X-Actor": actor,
        "Content-Type": "application/json",
    }
    payload = {
        "requested_resources": {
            "driver_vcpu": 1,
            "driver_memory_gb": 4,
            "executor_vcpu": 1,
            "executor_memory_gb": 4,
            "executor_instances": 1,
        }
    }

    start = time.monotonic()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "status_code": resp.status_code,
            "elapsed_ms": elapsed_ms,
            "run_id": resp.json().get("id") if resp.status_code in {200, 201} else None,
            "error": None,
        }
    except Exception as exc:
        elapsed_ms = (time.monotonic() - start) * 1000
        return {
            "status_code": None,
            "elapsed_ms": elapsed_ms,
            "run_id": None,
            "error": str(exc),
        }


def _print_summary(results: list[dict[str, Any]], total_elapsed: float, teams: int, runs_per_team: int) -> None:
    total = len(results)
    successes = [r for r in results if r["status_code"] in {200, 201}]
    failures = [r for r in results if r not in successes]
    latencies = [r["elapsed_ms"] for r in successes]

    print("\n" + "=" * 60)
    print("SparkPilot Live Load Test Results")
    print("=" * 60)
    print(f"Teams:              {teams}")
    print(f"Runs per team:      {runs_per_team}")
    print(f"Total submissions:  {total}")
    print(f"Successful:         {len(successes)}")
    print(f"Failed:             {len(failures)}")
    print(f"Total elapsed:      {total_elapsed:.2f}s")
    print(f"Throughput:         {total / total_elapsed:.1f} submissions/sec")

    if latencies:
        latencies_sorted = sorted(latencies)
        p50 = statistics.median(latencies)
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
        p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]
        print(f"\nLatency (submission only):")
        print(f"  p50:  {p50:.0f}ms  (target: <200ms)")
        print(f"  p95:  {p95:.0f}ms  (target: <500ms)")
        print(f"  p99:  {p99:.0f}ms")
        print(f"  min:  {min(latencies):.0f}ms")
        print(f"  max:  {max(latencies):.0f}ms")

        p50_ok = "PASS" if p50 < 200 else "FAIL"
        p95_ok = "PASS" if p95 < 500 else "FAIL"
        print(f"\nBaseline checks:")
        print(f"  p50 < 200ms: {p50_ok}")
        print(f"  p95 < 500ms: {p95_ok}")

    if failures:
        print(f"\nFailures ({len(failures)}):")
        for f in failures[:10]:
            print(f"  status={f['status_code']} error={f['error']}")
        if len(failures) > 10:
            print(f"  ... and {len(failures) - 10} more")

    run_ids = {r["run_id"] for r in successes if r["run_id"]}
    print(f"\nUnique run IDs created: {len(run_ids)}")
    print("=" * 60)


def main() -> None:
    args = _parse_args()
    total_runs = args.teams * args.runs_per_team

    print(f"Starting live load test against {args.base_url}")
    print(f"Job ID: {args.job_id}")
    print(f"Teams: {args.teams}, Runs/team: {args.runs_per_team}, Total: {total_runs}")
    print(f"Workers: {total_runs} threads, per-request timeout: {args.timeout}s")
    print()

    results: list[dict] = []
    lock = threading.Lock()

    def submit(team_idx: int, run_idx: int) -> dict:
        key = f"live-lt-team{team_idx}-run{run_idx}-{uuid.uuid4().hex[:8]}"
        actor = f"team-{team_idx}-load-tester"
        return _submit_run(args.base_url, args.token, args.job_id, key, actor, args.timeout)

    start_time = time.monotonic()
    with ThreadPoolExecutor(max_workers=total_runs) as executor:
        futures = [
            executor.submit(submit, team_idx, run_idx)
            for team_idx in range(args.teams)
            for run_idx in range(args.runs_per_team)
        ]
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as exc:
                result = {"status_code": None, "elapsed_ms": 0, "run_id": None, "error": str(exc)}
            with lock:
                results.append(result)
            print(
                f"  [{len(results)}/{total_runs}] "
                f"status={result['status_code']} "
                f"elapsed={result['elapsed_ms']:.0f}ms "
                f"run_id={result['run_id'] or 'N/A'}"
            )

    total_elapsed = time.monotonic() - start_time
    _print_summary(results, total_elapsed, args.teams, args.runs_per_team)


if __name__ == "__main__":
    main()
