"use client";

import { useEffect, useState } from "react";
import { fetchRunLogs, fetchRuns, Run } from "@/lib/api";

function badgeClass(status: string): string {
  return `badge ${status}`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsHint, setLogsHint] = useState<string>("Select a run to view logs.");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchRuns()
      .then(setRuns)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Run fetch failed");
      });
  }, []);

  async function loadLogs(run: Run) {
    setSelectedRunId(run.id);
    setError(null);
    setLogs([]);
    if (!run.log_group || !run.log_stream_prefix) {
      setLogsHint("Logs unavailable for this run: no CloudWatch log pointers were recorded.");
      return;
    }
    try {
      const payload = await fetchRunLogs(run.id);
      setLogs(payload.lines);
      setLogsHint(payload.lines.length > 0 ? "" : "No log lines available yet for this run.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Log fetch failed");
      setLogs([]);
      setLogsHint("Log fetch failed. Check API/CloudWatch permissions and retry.");
    }
  }

  const selectedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) ?? null : null;

  return (
    <section className="stack">
      <div className="card">
        <h3>Run Operations</h3>
        <div className="subtle">
          Queue, dispatch, reconcile, and view deterministic run log streams.
        </div>
      </div>

      {error ? <div className="card">{error}</div> : null}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Run ID</th>
              <th>Environment</th>
              <th>Status</th>
              <th>EMR Job Run</th>
              <th>Started</th>
              <th>Ended</th>
              <th>Logs</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id}>
                <td>{run.id}</td>
                <td>{run.environment_id}</td>
                <td>
                  <span className={badgeClass(run.state)}>{run.state}</span>
                </td>
                <td>{run.emr_job_run_id ?? "-"}</td>
                <td>{run.started_at ?? "-"}</td>
                <td>{run.ended_at ?? "-"}</td>
                <td>
                  <button type="button" className="button" onClick={() => loadLogs(run)}>
                    View
                  </button>
                </td>
              </tr>
            ))}
            {runs.length === 0 ? (
              <tr>
                <td colSpan={7} className="subtle">
                  No runs available.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="card">
        <h3>Run Logs {selectedRunId ? `(${selectedRunId})` : ""}</h3>
        {selectedRun ? (
          <div className="subtle">
            log_group={selectedRun.log_group ?? "-"} | stream_prefix={selectedRun.log_stream_prefix ?? "-"}
            {selectedRun.error_message ? ` | error=${selectedRun.error_message}` : ""}
          </div>
        ) : null}
        <div className="logs">
          {logs.length > 0 ? logs.join("\n") : logsHint}
        </div>
      </div>
    </section>
  );
}
