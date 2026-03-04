"use client";

import { useEffect, useState } from "react";
import { createJob, fetchEnvironmentPreflight, fetchRunLogs, fetchRuns, Run, submitRun } from "@/lib/api";

function badgeClass(status: string): string {
  return `badge ${status}`;
}

export default function RunsPage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string[]>([]);
  const [logsHint, setLogsHint] = useState<string>("Select a run to view logs.");
  const [error, setError] = useState<string | null>(null);
  const [environmentId, setEnvironmentId] = useState<string>("");
  const [jobId, setJobId] = useState<string>("");
  const [preflightReady, setPreflightReady] = useState<boolean | null>(null);
  const [preflightSummary, setPreflightSummary] = useState<string[]>([]);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitBusy, setSubmitBusy] = useState<boolean>(false);
  const [driverVcpu, setDriverVcpu] = useState<string>("1");
  const [driverMemoryGb, setDriverMemoryGb] = useState<string>("2");
  const [executorVcpu, setExecutorVcpu] = useState<string>("1");
  const [executorMemoryGb, setExecutorMemoryGb] = useState<string>("2");
  const [executorInstances, setExecutorInstances] = useState<string>("1");
  const [timeoutSeconds, setTimeoutSeconds] = useState<string>("1800");
  const [jobEnvironmentId, setJobEnvironmentId] = useState<string>("");
  const [jobName, setJobName] = useState<string>("");
  const [artifactUri, setArtifactUri] = useState<string>("");
  const [artifactDigest, setArtifactDigest] = useState<string>("sha256:placeholder");
  const [entrypoint, setEntrypoint] = useState<string>("");
  const [jobArgsText, setJobArgsText] = useState<string>("");
  const [jobConfText, setJobConfText] = useState<string>("");
  const [retryMaxAttempts, setRetryMaxAttempts] = useState<string>("1");
  const [jobTimeoutSeconds, setJobTimeoutSeconds] = useState<string>("1200");
  const [jobCreateError, setJobCreateError] = useState<string | null>(null);
  const [jobCreateSuccess, setJobCreateSuccess] = useState<string | null>(null);
  const [jobCreateBusy, setJobCreateBusy] = useState<boolean>(false);

  useEffect(() => {
    reloadRuns();
  }, []);

  async function reloadRuns() {
    try {
      const data = await fetchRuns();
      setRuns(data);
      setError(null);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Run fetch failed");
    }
  }

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

  async function checkPreflight() {
    setPreflightError(null);
    setSubmitError(null);
    setPreflightReady(null);
    setPreflightSummary([]);
    if (!environmentId) {
      setPreflightError("Environment ID is required before preflight.");
      return;
    }
    try {
      const preflight = await fetchEnvironmentPreflight(environmentId);
      setPreflightReady(preflight.ready);
      setPreflightSummary(
        preflight.checks.map((item) => `[${item.status}] ${item.code}: ${item.message}`)
      );
    } catch (err: unknown) {
      setPreflightError(err instanceof Error ? err.message : "Preflight failed");
    }
  }

  async function submitRunRequest() {
    setSubmitError(null);
    if (!jobId) {
      setSubmitError("Job ID is required.");
      return;
    }
    if (preflightReady !== true) {
      setSubmitError("Run submission requires a successful preflight check.");
      return;
    }
    const resources = {
      driverVcpu: Number.parseInt(driverVcpu, 10),
      driverMemoryGb: Number.parseInt(driverMemoryGb, 10),
      executorVcpu: Number.parseInt(executorVcpu, 10),
      executorMemoryGb: Number.parseInt(executorMemoryGb, 10),
      executorInstances: Number.parseInt(executorInstances, 10),
      timeoutSeconds: Number.parseInt(timeoutSeconds, 10),
    };
    if (
      Object.values(resources).some((value) => Number.isNaN(value) || value <= 0)
    ) {
      setSubmitError("All resource fields and timeout must be positive integers.");
      return;
    }
    setSubmitBusy(true);
    try {
      await submitRun(jobId, {
        requested_resources: {
          driver_vcpu: resources.driverVcpu,
          driver_memory_gb: resources.driverMemoryGb,
          executor_vcpu: resources.executorVcpu,
          executor_memory_gb: resources.executorMemoryGb,
          executor_instances: resources.executorInstances,
        },
        timeout_seconds: resources.timeoutSeconds,
      });
      await reloadRuns();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : "Run submit failed");
    } finally {
      setSubmitBusy(false);
    }
  }

  function parseTextLines(text: string): string[] {
    return text
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0);
  }

  function parseSparkConf(text: string): { conf: Record<string, string>; error: string | null } {
    const conf: Record<string, string> = {};
    const lines = parseTextLines(text);
    for (const line of lines) {
      const idx = line.indexOf("=");
      if (idx <= 0 || idx === line.length - 1) {
        return { conf: {}, error: `Invalid spark_conf entry "${line}". Use key=value per line.` };
      }
      const key = line.slice(0, idx).trim();
      const value = line.slice(idx + 1).trim();
      if (!key || !value) {
        return { conf: {}, error: `Invalid spark_conf entry "${line}". Use key=value per line.` };
      }
      conf[key] = value;
    }
    return { conf, error: null };
  }

  async function createJobTemplate() {
    setJobCreateError(null);
    setJobCreateSuccess(null);
    const envId = jobEnvironmentId.trim();
    const name = jobName.trim();
    const uri = artifactUri.trim();
    const digest = artifactDigest.trim();
    const main = entrypoint.trim();

    if (!envId) {
      setJobCreateError("Environment ID is required.");
      return;
    }
    if (!name) {
      setJobCreateError("Job name is required.");
      return;
    }
    if (!uri) {
      setJobCreateError("Artifact URI is required.");
      return;
    }
    if (!digest) {
      setJobCreateError("Artifact digest is required.");
      return;
    }
    if (!main) {
      setJobCreateError("Entrypoint is required.");
      return;
    }

    const retry = Number.parseInt(retryMaxAttempts, 10);
    const timeout = Number.parseInt(jobTimeoutSeconds, 10);
    if (Number.isNaN(retry) || retry <= 0) {
      setJobCreateError("Retry max attempts must be a positive integer.");
      return;
    }
    if (Number.isNaN(timeout) || timeout < 60) {
      setJobCreateError("Job timeout must be an integer >= 60 seconds.");
      return;
    }

    const parsedConf = parseSparkConf(jobConfText);
    if (parsedConf.error) {
      setJobCreateError(parsedConf.error);
      return;
    }

    setJobCreateBusy(true);
    try {
      const created = await createJob({
        environment_id: envId,
        name,
        artifact_uri: uri,
        artifact_digest: digest,
        entrypoint: main,
        args: parseTextLines(jobArgsText),
        spark_conf: parsedConf.conf,
        retry_max_attempts: retry,
        timeout_seconds: timeout,
      });
      setJobCreateSuccess(`Job created: ${created.id}`);
      setJobId(created.id);
      if (!environmentId) {
        setEnvironmentId(created.environment_id);
      }
    } catch (err: unknown) {
      setJobCreateError(err instanceof Error ? err.message : "Job create failed");
    } finally {
      setJobCreateBusy(false);
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

      <div className="card">
        <h3>Job Create</h3>
        <div className="subtle">
          Create reusable job templates for a target environment. Use one `arg` or `spark_conf` entry per line.
        </div>
        <div className="form-grid">
          <label>
            Environment ID
            <input value={jobEnvironmentId} onChange={(event) => setJobEnvironmentId(event.target.value)} />
          </label>
          <label>
            Job Name
            <input value={jobName} onChange={(event) => setJobName(event.target.value)} />
          </label>
          <label>
            Artifact URI
            <input value={artifactUri} onChange={(event) => setArtifactUri(event.target.value)} />
          </label>
          <label>
            Artifact Digest
            <input value={artifactDigest} onChange={(event) => setArtifactDigest(event.target.value)} />
          </label>
          <label>
            Entrypoint
            <input value={entrypoint} onChange={(event) => setEntrypoint(event.target.value)} />
          </label>
          <label>
            Retry Max Attempts
            <input
              type="number"
              min={1}
              value={retryMaxAttempts}
              onChange={(event) => setRetryMaxAttempts(event.target.value)}
            />
          </label>
          <label>
            Timeout (seconds)
            <input
              type="number"
              min={60}
              value={jobTimeoutSeconds}
              onChange={(event) => setJobTimeoutSeconds(event.target.value)}
            />
          </label>
          <label>
            Args (one per line)
            <textarea value={jobArgsText} onChange={(event) => setJobArgsText(event.target.value)} />
          </label>
          <label>
            Spark Conf (key=value per line)
            <textarea value={jobConfText} onChange={(event) => setJobConfText(event.target.value)} />
          </label>
        </div>
        <div className="button-row">
          <button type="button" className="button" disabled={jobCreateBusy} onClick={createJobTemplate}>
            {jobCreateBusy ? "Creating..." : "Create Job"}
          </button>
        </div>
        {jobCreateError ? <div className="error-text">{jobCreateError}</div> : null}
        {jobCreateSuccess ? <div className="success-text">{jobCreateSuccess}</div> : null}
      </div>

      <div className="card">
        <h3>Run Submit (preflight-gated)</h3>
        <div className="form-grid">
          <label>
            Environment ID
            <input value={environmentId} onChange={(event) => setEnvironmentId(event.target.value)} />
          </label>
          <label>
            Job ID
            <input value={jobId} onChange={(event) => setJobId(event.target.value)} />
          </label>
          <label>
            Driver vCPU
            <input
              type="number"
              min={1}
              value={driverVcpu}
              onChange={(event) => setDriverVcpu(event.target.value)}
            />
          </label>
          <label>
            Driver Memory (GB)
            <input
              type="number"
              min={1}
              value={driverMemoryGb}
              onChange={(event) => setDriverMemoryGb(event.target.value)}
            />
          </label>
          <label>
            Executor vCPU
            <input
              type="number"
              min={1}
              value={executorVcpu}
              onChange={(event) => setExecutorVcpu(event.target.value)}
            />
          </label>
          <label>
            Executor Memory (GB)
            <input
              type="number"
              min={1}
              value={executorMemoryGb}
              onChange={(event) => setExecutorMemoryGb(event.target.value)}
            />
          </label>
          <label>
            Executor Instances
            <input
              type="number"
              min={1}
              value={executorInstances}
              onChange={(event) => setExecutorInstances(event.target.value)}
            />
          </label>
          <label>
            Timeout (seconds)
            <input
              type="number"
              min={1}
              value={timeoutSeconds}
              onChange={(event) => setTimeoutSeconds(event.target.value)}
            />
          </label>
        </div>
        <div className="button-row">
          <button type="button" className="button" onClick={checkPreflight}>
            Check Preflight
          </button>
          <button type="button" className="button" disabled={submitBusy || preflightReady !== true} onClick={submitRunRequest}>
            {submitBusy ? "Submitting..." : "Submit Run"}
          </button>
        </div>
        {preflightError ? <div className="error-text">{preflightError}</div> : null}
        {submitError ? <div className="error-text">{submitError}</div> : null}
        {preflightReady !== null ? (
          <div className="subtle">
            Preflight status: <span className={badgeClass(preflightReady ? "ready" : "failed")}>{preflightReady ? "ready" : "failed"}</span>
          </div>
        ) : null}
        {preflightSummary.length > 0 ? (
          <ul className="preflight-list">
            {preflightSummary.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        ) : null}
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
