"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  type DiagnosticItem,
  Environment,
  Job,
  type QueueUtilizationResponse,
  Run,
  cancelRun,
  fetchEnvironments,
  fetchJobs,
  fetchQueueUtilization,
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
const LOG_TAIL_LINES = 500;

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
  const [logsLoading, setLogsLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [polling, setPolling] = useState(false);
  const [cancelRunId, setCancelRunId] = useState<string | null>(null);
  const [diagRunId, setDiagRunId] = useState<string | null>(null);
  const [diagSelectRunId, setDiagSelectRunId] = useState<string>("");
  const [diagnostics, setDiagnostics] = useState<DiagnosticItem[]>([]);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);
  const [diagCategory, setDiagCategory] = useState<string>("all");
  const [diagPg, setDiagPg] = useState<PaginationState>({ page: 0, pageSize: 10 });
  const [queueUtilizationByEnvironmentId, setQueueUtilizationByEnvironmentId] = useState<Record<string, QueueUtilizationResponse>>({});
  const [error, setError] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 25 });

  const envMap = useMemo(() => new Map(environments.map((e) => [e.id, e])), [environments]);
  const jobMap = useMemo(() => new Map(jobs.map((j) => [j.id, j])), [jobs]);
  const queuePositionByRunId = useMemo(() => {
    const map: Record<string, number> = {};
    const byEnvironment = new Map<string, Run[]>();
    for (const run of runs) {
      if (!["queued", "dispatching", "accepted"].includes(run.state)) {
        continue;
      }
      const rows = byEnvironment.get(run.environment_id) ?? [];
      rows.push(run);
      byEnvironment.set(run.environment_id, rows);
    }
    for (const rows of byEnvironment.values()) {
      rows
        .slice()
        .sort((a, b) => {
          const aTs = Date.parse(a.created_at ?? "");
          const bTs = Date.parse(b.created_at ?? "");
          return (Number.isNaN(aTs) ? 0 : aTs) - (Number.isNaN(bTs) ? 0 : bTs);
        })
        .forEach((run, idx) => {
          map[run.id] = idx + 1;
        });
    }
    return map;
  }, [runs]);

  function envDisplay(id: string): string {
    const env = envMap.get(id);
    if (!env) return shortId(id);
    return `${env.region} / ${env.eks_namespace ?? env.provisioning_mode}`;
  }

  function jobDisplay(id: string): string {
    const job = jobMap.get(id);
    return job?.name ?? shortId(id);
  }

  function queueHint(run: Run): string {
    const util = queueUtilizationByEnvironmentId[run.environment_id];
    if (run.error_message?.trim()) {
      return run.error_message;
    }
    if (!["queued", "dispatching", "accepted", "running"].includes(run.state)) {
      if (run.state === "succeeded") {
        return "Completed successfully.";
      }
      if (run.state === "cancelled") {
        return "Cancelled before completion.";
      }
      if (run.state === "failed") {
        return "Failed. Open diagnostics for root-cause details.";
      }
      if (run.state === "timed_out") {
        return "Timed out before completion.";
      }
      return `Terminal state: ${run.state}.`;
    }
    if (!util) {
      return run.state === "queued" ? "Queued: capacity telemetry loading..." : `${run.state}: capacity telemetry loading...`;
    }
    const capacitySummary = util.max_vcpu
      ? `${util.used_vcpu}/${util.max_vcpu} vCPU in use`
      : `${util.used_vcpu} vCPU in use`;
    if (util.max_vcpu && util.used_vcpu >= util.max_vcpu && run.state !== "running") {
      return `Capacity blocked: ${capacitySummary}.`;
    }
    if (run.state === "queued") {
      const position = queuePositionByRunId[run.id];
      return `Queued${position ? ` (position ${position})` : ""}: ${util.active_run_count} active run(s), ${capacitySummary}.`;
    }
    if (run.state === "accepted") {
      return `Accepted by EMR, waiting for cluster resources. ${capacitySummary}.`;
    }
    if (run.state === "dispatching") {
      return `Dispatching request to EMR on EKS. ${capacitySummary}.`;
    }
    return `Running. ${capacitySummary}.`;
  }

  const refreshQueueUtilizationForActiveRuns = useCallback(async (runRows: Run[]) => {
    const envIds = Array.from(
      new Set(
        runRows
          .filter((run) => ["queued", "dispatching", "accepted", "running"].includes(run.state))
          .map((run) => run.environment_id)
      )
    );
    if (envIds.length === 0) {
      return;
    }
    await Promise.all(
      envIds.map(async (environmentId) => {
        try {
          const row = await fetchQueueUtilization(environmentId);
          setQueueUtilizationByEnvironmentId((current) => ({ ...current, [environmentId]: row }));
        } catch {
          // Keep existing queue telemetry when refresh fails.
        }
      })
    );
  }, []);

  const refreshAll = useCallback(async () => {
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
      await refreshQueueUtilizationForActiveRuns(runsPayload);
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to load run data"));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [refreshQueueUtilizationForActiveRuns]);

  const reloadRuns = useCallback(async () => {
    try {
      const data = await fetchRuns();
      setRuns(data);
      await refreshQueueUtilizationForActiveRuns(data);
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to reload runs"));
    }
  }, [refreshQueueUtilizationForActiveRuns]);

  async function loadLogs(run: Run) {
    setSelectedRunId(run.id);
    setError(null);
    setLogs([]);
    setLogsLoading(true);
    if (!run.log_group || !run.log_stream_prefix) {
      setLogsHint("Logs unavailable - no CloudWatch log pointers were recorded for this run.");
      setLogsLoading(false);
      return;
    }
    try {
      const payload = await fetchRunLogs(run.id, { limit: LOG_TAIL_LINES });
      setLogs(payload.lines);
      setLogsHint(payload.lines.length > 0 ? "" : "No log lines available yet. The run may still be starting.");
    } catch (err: unknown) {
      setError(friendlyError(err, "Log fetch failed"));
      setLogs([]);
      setLogsHint("Log fetch failed. Check API connectivity and CloudWatch permissions.");
    } finally {
      setLogsLoading(false);
    }
  }

  const refreshSelectedRunLogs = useCallback(async (runId: string) => {
    const run = runs.find((item) => item.id === runId);
    if (!run || !run.log_group || !run.log_stream_prefix) {
      return;
    }
    try {
      const payload = await fetchRunLogs(run.id, { limit: LOG_TAIL_LINES });
      setLogs(payload.lines);
      setLogsHint(payload.lines.length > 0 ? "" : "No log lines available yet. The run may still be starting.");
    } catch {
      // Keep current log lines if background refresh fails; manual Logs click still surfaces errors.
    }
  }, [runs]);

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
    setDiagSelectRunId(run.id);
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

  async function loadDiagnosticsById(runId: string) {
    const run = runs.find((item) => item.id === runId);
    if (!run) {
      setDiagRunId(null);
      setDiagnostics([]);
      setDiagError("Selected run is no longer available. Refresh and try again.");
      return;
    }
    await loadDiagnostics(run);
  }

  // Initial load
  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

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
  }, [reloadRuns]);

  useEffect(() => {
    if (runs.length === 0) {
      setDiagSelectRunId("");
      setDiagRunId(null);
      setDiagnostics([]);
      setDiagError(null);
      return;
    }
    setDiagSelectRunId((current) => {
      if (current && runs.some((run) => run.id === current)) {
        return current;
      }
      return runs[0].id;
    });
    if (diagRunId && !runs.some((run) => run.id === diagRunId)) {
      setDiagRunId(null);
      setDiagnostics([]);
      setDiagError(null);
    }
  }, [runs, diagRunId]);

  useEffect(() => {
    if (!selectedRunId || document.visibilityState !== "visible") {
      return;
    }
    void refreshSelectedRunLogs(selectedRunId);
  }, [runs, selectedRunId, refreshSelectedRunLogs]);

  const selectedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) ?? null : null;
  const diagRun = diagRunId ? runs.find((r) => r.id === diagRunId) ?? null : null;
  const visibleRuns = paginate(runs, pg);

  return (
    <section className="stack">
      <div className="card">
        <h3>Run Operations</h3>
        <div className="subtle">Create jobs, submit runs through the preflight gate, and inspect CloudWatch log streams.</div>
      </div>

      <div className="card">
        <h3>Guided Demo Setup</h3>
        <ol className="guided-steps">
          <li>Create or confirm a ready environment on the Environments page.</li>
          <li>Create a job template (Form or JSON mode) with artifact URI and Spark config.</li>
          <li>Submit run from a ready environment, run preflight, then submit.</li>
          <li>Use Logs + Diagnostics + Queue/Capacity hints to verify progress.</li>
        </ol>
        <div className="subtle">
          Tip: JSON mode supports copy/paste of known-good payloads for fast repeatable demos.
        </div>
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
          {refreshing ? "Syncing..." : `Auto-refresh every ${AUTO_REFRESH_MS / 1000}s`}
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
                <th className="col-hide-mobile">Queue / Capacity</th>
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
                  <td className="col-hide-mobile">
                    <span className="queue-hint">{queueHint(run)}</span>
                  </td>
                  <td>
                    <div className="row-actions row-actions-logs">
                      <button type="button" className="button button-sm" onClick={() => void loadLogs(run)}>
                        Logs
                      </button>
                      <button
                        type="button"
                        className="button button-sm button-secondary"
                        onClick={() => {
                          setDiagSelectRunId(run.id);
                          void loadDiagnostics(run);
                        }}
                      >
                        Diag
                      </button>
                    </div>
                  </td>
                  <td>
                    <div className="row-actions row-actions-main">
                      {CANCELLABLE_STATES.has(run.state) ? (
                        <button
                          type="button"
                          className="button button-sm button-secondary"
                          disabled={!canCancel(run) || cancelRunId === run.id}
                          onClick={() => void requestCancel(run)}
                        >
                          {cancelRunId === run.id ? "Cancelling..." : run.cancellation_requested ? "Requested" : "Cancel"}
                        </button>
                      ) : (
                        <span className="subtle row-action-empty">No actions available</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {runs.length === 0 ? (
                <tr>
                  <td colSpan={10} className="subtle">
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
              {jobDisplay(selectedRun.job_id)} | <ShortId value={selectedRun.id} />
            </span>
          ) : null}
        </h3>
        {selectedRun ? (
          <div className="subtle">
            Log group: {selectedRun.log_group ?? "n/a"} | Stream prefix: {selectedRun.log_stream_prefix ?? "n/a"}
            {CANCELLABLE_STATES.has(selectedRun.state) ? (
              <span style={{ marginLeft: 8 }}>Live tail every {AUTO_REFRESH_MS / 1000}s</span>
            ) : null}
            {selectedRun.error_message ? (
              <span className="error-text" style={{ marginLeft: 8 }}>Error: {selectedRun.error_message}</span>
            ) : null}
          </div>
        ) : null}
        <div className="logs">{logsLoading ? "Loading logs..." : logs.length > 0 ? logs.join("\n") : logsHint}</div>
      </div>

      <div className="card">
        <h3>
          Run Diagnostics
          {diagRun ? (
            <span className="subtle" style={{ fontWeight: 400, marginLeft: 8 }}>
              {jobDisplay(diagRun.job_id)} | <ShortId value={diagRun.id} />
            </span>
          ) : null}
        </h3>
        {runs.length > 0 ? (
          <div className="diagnostics-toolbar">
            <label className="filter-label">
              Run
              <select
                value={diagSelectRunId}
                onChange={(event) => setDiagSelectRunId(event.target.value)}
              >
                {runs.map((run) => (
                  <option key={run.id} value={run.id}>
                    {jobDisplay(run.job_id)} | {shortId(run.id)} | {run.state}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className="button button-sm"
              disabled={!diagSelectRunId || diagLoading}
              onClick={() => void loadDiagnosticsById(diagSelectRunId)}
            >
              {diagLoading ? "Loading..." : "Load Diagnostics"}
            </button>
          </div>
        ) : null}

        {diagLoading ? (
          <div className="loading-state"><span className="subtle">Loading diagnostics...</span></div>
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
          <div className="empty-state"><span className="subtle">Choose a run and click Load Diagnostics to view findings.</span></div>
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
                          <td className="col-hide-mobile">{d.remediation ?? "-"}</td>
                          <td className="col-hide-mobile">
                            {d.log_snippet ? <code className="log-snippet">{d.log_snippet}</code> : "-"}
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
