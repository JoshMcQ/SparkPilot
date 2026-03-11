"use client";

import { useEffect, useMemo, useState } from "react";
import {
  type DiagnosticItem,
  Environment,
  Job,
  Run,
  cancelRun,
  fetchEnvironments,
  fetchJobs,
  fetchRunDiagnostics,
  fetchRunLogs,
  fetchRuns,
} from "@/lib/api";
import { shortId, compactTime, friendlyError } from "@/lib/format";
import { badgeClass } from "@/lib/badge";
import { JobCreateCard } from "@/components/job-create-card";
import { RunSubmitCard } from "@/components/run-submit-card";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";

const AUTO_REFRESH_MS = 8_000;
const CANCELLABLE_STATES = new Set(["accepted", "running", "dispatching", "queued"]);

function canCancel(run: Run): boolean {
  return CANCELLABLE_STATES.has(run.state) && !run.cancellation_requested;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsHint, setLogsHint] = useState<string>("Select a run to view logs.");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [polling, setPolling] = useState(false);
  const [cancelRunId, setCancelRunId] = useState<string | null>(null);
  const [diagRunId, setDiagRunId] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[]>([]);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);
  const [diagCategory, setDiagCategory] = useState<string>("all");
  const [diagPg, setDiagPg] = useState<PaginationState>({ page: 0, pageSize: 10 });
  const [error, setError] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 25 });

  const envMap = useMemo(() => new Map(environments.map((e) => [e.id, e])), [environments]);
  const jobMap = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs]);

  function envDisplay(id: string): string {
    const env = envMap.get(id);
    if (!env) return shortId(id);
    return `${env.region} / ${env.eks_namespace ?? env.provisioning_mode}`;
  }

  function jobDisplay(id: string): string {
    const job = jobMap.get(id);
    return job?.name ?? shortId(id);
  }

  async function refreshAll() {
    setRefreshing(true);
    try {
      const [runsPayload, envPayload, jobPayload] = await Promise.all([
        fetchRuns(),
        fetchEnvironments(),
        fetchJobs(),
      ]);
      setRuns(runsPayload);
      setEnvironments(envPayload);
      setJobs(jobPayload);
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to load run data"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function reloadRuns() {
    try {
      const data = await fetchRuns();
      setRuns(data);
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to reload runs"));
    }
  }

  async function loadLogs(run: Run) {
    setSelectedRunId(run.id);
    setError(null);
    setLogs([]);
    if (!run.log_group || !run.log_stream_prefix) {
      setLogsHint("Logs unavailable - no CloudWatch log pointers were recorded for this run.");
      return;
    }
    try {
      const payload = await fetchRunLogs(run.id);
      setLogs(payload.lines);
      setLogsHint(payload.lines.length > 0 ? "" : "No log lines available yet. The run may still be starting.");
    } catch (err: unknown) {
      setError(friendlyError(err, "Log fetch failed"));
      setLogs([]);
      setLogsHint("Log fetch failed. Check API connectivity and CloudWatch permissions.");
    }
  }

  async function requestCancel(run: Run) {
    setCancelRunId(run.id);
    setError(null);
    try {
      const updated = await cancelRun(run.id);
      setRuns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      if (selectedRunId === updated.id) {
        await loadLogs(updated);
      }
      await reloadRuns();
    } catch (err: unknown) {
      setError(friendlyError(err, "Run cancellation failed"));
    } finally {
      setCancelRunId(null);
    }
  }

  async function loadDiagnostics(run: Run) {
    setDiagRunId(run.id);
    setDiagnostics([]);
    setDiagError(null);
    setDiagCategory("all");
    setDiagPg({ page: 0, pageSize: 10 });
    setDiagLoading(true);
    try {
      const resp = await fetchRunDiagnostics(run.id);
      setDiagnostics(resp.items);
    } catch (err: unknown) {
      setDiagError(friendlyError(err, "Diagnostics fetch failed"));
      setDiagnostics([]);
    } finally {
      setDiagLoading(false);
    }
  }

  // Initial load
  useEffect(() => {
    void refreshAll();
  }, []);

  // Auto-refresh: poll every 8 seconds, pause when tab is hidden
  useEffect(() => {
    setPolling(true);

    const tick = () => {
      if (document.visibilityState === "visible") {
        void reloadRuns();
      }
    };

    const interval = setInterval(tick, AUTO_REFRESH_MS);

    const onVisibilityChange = () => {
      setPolling(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      setPolling(false);
    };
  }, []);

  const selectedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) ?? null : null;
  const diagRun = diagRunId ? runs.find((r) => r.id === diagRunId) ?? null : null;
  const visibleRuns = paginate(runs, pg);

  return (
    <section className="stack">
      <div className="card">
        <h3>Run Operations</h3>
        <div className="subtle">Create jobs, submit runs through the preflight gate, and inspect CloudWatch log streams.</div>
      </div>

      <JobCreateCard
        environments={environments}
        onJobCreated={(job) => {
          setJobs((prev) => [job, ...prev]);
        }}
      />

      <RunSubmitCard
        environments={environments}
        jobs={jobs}
        onRunSubmitted={() => void reloadRuns()}
      />

      {error ? (
        <div className="card error-card">
          <strong>Error</strong>
          <div>{error}</div>
        </div>
      ) : null}

      <div className="card-header-row">
        <h3>Recent Runs</h3>
        {polling ? (
          <span className="badge badge-live" title={`Auto-refreshing every ${AUTO_REFRESH_MS / 1000}s`}>
            Live
          </span>
        ) : null}
        <div className="subtle">
          {refreshing ? "Syncing…" : `Auto-refresh every ${AUTO_REFRESH_MS / 1000}s`}
        </div>
        <button type="button" className="button" onClick={() => void reloadRuns()}>
          Refresh
        </button>
      </div>

      {loading ? (
        <div className="card">
          <div className="subtle">Loading run history...</div>
        </div>
      ) : (
        <>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Job</th>
                <th>Environment</th>
                <th>Status</th>
                <th className="col-hide-mobile">EMR Job Run</th>
                <th className="col-hide-mobile">Started</th>
                <th className="col-hide-mobile">Ended</th>
                <th>Logs</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {visibleRuns.map((run) => (
                <tr key={run.id} className={selectedRunId === run.id ? "row-selected" : ""}>
                  <td><ShortId value={run.id} /></td>
                  <td title={run.job_id}>{jobDisplay(run.job_id)}</td>
                  <td title={run.environment_id}>{envDisplay(run.environment_id)}</td>
                  <td>
                    <span className={badgeClass(run.state)}>{run.state}</span>
                  </td>
                  <td className="col-hide-mobile"><ShortId value={run.emr_job_run_id} /></td>
                  <td className="col-hide-mobile">{compactTime(run.started_at)}</td>
                  <td className="col-hide-mobile">{compactTime(run.ended_at)}</td>
                  <td>
                    <button type="button" className="button button-sm" onClick={() => void loadLogs(run)}>
                      Logs
                    </button>
                    <button type="button" className="button button-sm button-secondary" style={{ marginLeft: 4 }} onClick={() => void loadDiagnostics(run)}>
                      Diag
                    </button>
                  </td>
                  <td>
                    {CANCELLABLE_STATES.has(run.state) ? (
                      <button
                        type="button"
                        className="button button-sm button-secondary"
                        disabled={!canCancel(run) || cancelRunId === run.id}
                        onClick={() => void requestCancel(run)}
                      >
                        {cancelRunId === run.id ? "Cancelling…" : run.cancellation_requested ? "Requested" : "Cancel"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="subtle">
                    No runs yet. Create a job and submit a run above.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <PaginationControls total={runs.length} state={pg} onChange={setPg} />
        </>
      )}

      <div className="card">
        <h3>
          Run Logs
          {selectedRun ? (
            <span className="subtle" style={{ fontWeight: 400, marginLeft: 8 }}>
              {jobDisplay(selectedRun.job_id)} · <ShortId value={selectedRun.id} />
            </span>
          ) : null}
        </h3>
        {selectedRun ? (
          <div className="subtle">
            Log group: {selectedRun.log_group ?? "n/a"} · Stream prefix: {selectedRun.log_stream_prefix ?? "n/a"}
            {selectedRun.error_message ? (
              <span className="error-text" style={{ marginLeft: 8 }}>Error: {selectedRun.error_message}</span>
            ) : null}
          </div>
        ) : null}
        <div className="logs">{logs.length > 0 ? logs.join("\n") : logsHint}</div>
      </div>

      <div className="card">
        <h3>
          Run Diagnostics
          {diagRun ? (
            <span className="subtle" style={{ fontWeight: 400, marginLeft: 8 }}>
              {jobDisplay(diagRun.job_id)} · <ShortId value={diagRun.id} />
            </span>
          ) : null}
        </h3>

        {diagLoading ? (
          <div className="loading-state"><span className="subtle">Loading diagnostics…</span></div>
        ) : diagError ? (
          <div className="error-state">
            <span className="error-text">{diagError}</span>
            {diagRun ? (
              <button type="button" className="button button-sm" style={{ marginLeft: 8 }} onClick={() => void loadDiagnostics(diagRun)}>
                Retry
              </button>
            ) : null}
          </div>
        ) : diagRunId && diagnostics.length === 0 ? (
          <div className="empty-state"><span className="subtle">No diagnostic findings for this run.</span></div>
        ) : !diagRunId ? (
          <div className="empty-state"><span className="subtle">Select a run and click Diag to view diagnostic findings.</span></div>
        ) : (
          (() => {
            const categories = Array.from(new Set(diagnostics.map((d) => d.category))).sort();
            const filtered = diagCategory === "all" ? diagnostics : diagnostics.filter((d) => d.category === diagCategory);
            const visible = paginate(filtered, diagPg);
            return (
              <>
                <div className="filter-row" style={{ marginTop: 8 }}>
                  <label className="filter-label">
                    Category
                    <select
                      value={diagCategory}
                      onChange={(e) => { setDiagCategory(e.target.value); setDiagPg((p) => ({ ...p, page: 0 })); }}
                    >
                      <option value="all">All ({diagnostics.length})</option>
                      {categories.map((cat) => (
                        <option key={cat} value={cat}>
                          {cat} ({diagnostics.filter((d) => d.category === cat).length})
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <div className="table-wrap" style={{ marginTop: 8 }}>
                  <table>
                    <thead>
                      <tr>
                        <th>Category</th>
                        <th>Description</th>
                        <th className="col-hide-mobile">Remediation</th>
                        <th className="col-hide-mobile">Log Snippet</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visible.map((d) => (
                        <tr key={d.id}>
                          <td><span className={badgeClass(d.category)}>{d.category}</span></td>
                          <td>{d.description}</td>
                          <td className="col-hide-mobile">{d.remediation ?? "—"}</td>
                          <td className="col-hide-mobile">
                            {d.log_snippet ? <code className="log-snippet">{d.log_snippet}</code> : "—"}
                          </td>
                        </tr>
                      ))}
                      {filtered.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="subtle">No findings match this filter.</td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
                <PaginationControls total={filtered.length} state={diagPg} onChange={setDiagPg} />
              </>
            );
          })()
        )}
      </div>
    </section>
  );
}
