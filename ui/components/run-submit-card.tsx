"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Environment,
  Job,
  PreflightCheck,
  Run,
  RunSubmitRequest,
  fetchEnvironmentPreflight,
  submitRun,
} from "@/lib/api";
import { badgeClass } from "@/lib/badge";
import { envLabel, friendlyError } from "@/lib/format";

type RunSubmitFormState = {
  environment_id: string;
  job_id: string;
  driver_vcpu: string;
  driver_memory_gb: string;
  executor_vcpu: string;
  executor_memory_gb: string;
  executor_instances: string;
  timeout_seconds: string;
};

type JsonRunPayload = {
  environment_id: string;
  job_id: string;
  requested_resources: {
    driver_vcpu: number;
    driver_memory_gb: number;
    executor_vcpu: number;
    executor_memory_gb: number;
    executor_instances: number;
  };
  timeout_seconds?: number;
  args?: string[];
  spark_conf?: Record<string, string>;
};

function defaultForm(environments: Environment[]): RunSubmitFormState {
  return {
    environment_id: environments[0]?.id ?? "",
    job_id: "",
    driver_vcpu: "1",
    driver_memory_gb: "2",
    executor_vcpu: "1",
    executor_memory_gb: "2",
    executor_instances: "1",
    timeout_seconds: "1800",
  };
}

function parsePositiveInt(raw: string, field: string): number {
  const value = Number.parseInt(raw, 10);
  if (Number.isNaN(value) || value <= 0) {
    throw new Error(`${field} must be a positive integer.`);
  }
  return value;
}

function jsonParseError(err: unknown): string {
  if (!(err instanceof Error)) {
    return "Invalid JSON payload.";
  }
  const positionMatch = err.message.match(/position\s+(\d+)/i);
  if (positionMatch?.[1]) {
    return `Invalid JSON near character ${positionMatch[1]}. ${err.message}`;
  }
  return `Invalid JSON payload. ${err.message}`;
}

function buildJsonFromForm(form: RunSubmitFormState): JsonRunPayload {
  return {
    environment_id: form.environment_id,
    job_id: form.job_id,
    requested_resources: {
      driver_vcpu: Number.parseInt(form.driver_vcpu, 10),
      driver_memory_gb: Number.parseInt(form.driver_memory_gb, 10),
      executor_vcpu: Number.parseInt(form.executor_vcpu, 10),
      executor_memory_gb: Number.parseInt(form.executor_memory_gb, 10),
      executor_instances: Number.parseInt(form.executor_instances, 10),
    },
    timeout_seconds: Number.parseInt(form.timeout_seconds, 10),
  };
}

function validateJsonPayload(value: unknown): JsonRunPayload {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("JSON payload must be an object.");
  }
  const row = value as Record<string, unknown>;
  const environment_id = String(row.environment_id ?? "").trim();
  const job_id = String(row.job_id ?? "").trim();
  if (!environment_id) {
    throw new Error("environment_id is required.");
  }
  if (!job_id) {
    throw new Error("job_id is required.");
  }
  const rr = row.requested_resources;
  if (!rr || typeof rr !== "object" || Array.isArray(rr)) {
    throw new Error("requested_resources object is required.");
  }
  const resources = rr as Record<string, unknown>;
  const payload: JsonRunPayload = {
    environment_id,
    job_id,
    requested_resources: {
      driver_vcpu: parsePositiveInt(String(resources.driver_vcpu ?? ""), "requested_resources.driver_vcpu"),
      driver_memory_gb: parsePositiveInt(String(resources.driver_memory_gb ?? ""), "requested_resources.driver_memory_gb"),
      executor_vcpu: parsePositiveInt(String(resources.executor_vcpu ?? ""), "requested_resources.executor_vcpu"),
      executor_memory_gb: parsePositiveInt(String(resources.executor_memory_gb ?? ""), "requested_resources.executor_memory_gb"),
      executor_instances: parsePositiveInt(String(resources.executor_instances ?? ""), "requested_resources.executor_instances"),
    },
  };
  if (row.timeout_seconds != null) {
    payload.timeout_seconds = parsePositiveInt(String(row.timeout_seconds), "timeout_seconds");
  }
  if (row.args != null) {
    if (!Array.isArray(row.args) || row.args.some((item) => typeof item !== "string")) {
      throw new Error("args must be an array of strings when provided.");
    }
    payload.args = row.args;
  }
  if (row.spark_conf != null) {
    if (!row.spark_conf || typeof row.spark_conf !== "object" || Array.isArray(row.spark_conf)) {
      throw new Error("spark_conf must be an object when provided.");
    }
    const conf = row.spark_conf as Record<string, unknown>;
    payload.spark_conf = {};
    for (const [key, val] of Object.entries(conf)) {
      payload.spark_conf[key] = String(val);
    }
  }
  return payload;
}

export function RunSubmitCard({
  environments,
  jobs,
  onRunSubmitted,
}: {
  environments: Environment[];
  jobs: Job[];
  onRunSubmitted: (run: Run) => void;
}) {
  const [form, setForm] = useState<RunSubmitFormState>(defaultForm(environments));
  const [editorMode, setEditorMode] = useState<"form" | "json">("form");
  const [showNonReady, setShowNonReady] = useState(false);
  const [jsonInput, setJsonInput] = useState<string>(() => JSON.stringify(buildJsonFromForm(defaultForm(environments)), null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const [preflightReady, setPreflightReady] = useState<boolean | null>(null);
  const [preflightChecks, setPreflightChecks] = useState<PreflightCheck[]>([]);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitBusy, setSubmitBusy] = useState(false);

  const readyEnvironmentIds = useMemo(
    () => new Set(environments.filter((env) => env.status === "ready").map((env) => env.id)),
    [environments]
  );

  const selectableEnvironments = useMemo(
    () => (showNonReady ? environments : environments.filter((env) => env.status === "ready")),
    [environments, showNonReady]
  );

  const jobsFiltered = useMemo(() => {
    if (!form.environment_id) return [];
    return jobs.filter((j) => j.environment_id === form.environment_id);
  }, [jobs, form.environment_id]);

  const preflightFailChecks = useMemo(
    () => preflightChecks.filter((check) => check.status === "fail"),
    [preflightChecks]
  );

  const preflightWarningChecks = useMemo(
    () => preflightChecks.filter((check) => check.status === "warning"),
    [preflightChecks]
  );

  useEffect(() => {
    if (environments.length === 0) {
      return;
    }
    const currentReady = readyEnvironmentIds.has(form.environment_id);
    if (currentReady) {
      return;
    }
    const fallbackReady = environments.find((env) => env.status === "ready");
    if (!fallbackReady) {
      return;
    }
    const nextForm = { ...form, environment_id: fallbackReady.id, job_id: "" };
    setForm(nextForm);
    syncJsonFromForm(nextForm);
    setPreflightReady(null);
    setPreflightChecks([]);
  }, [environments, form, readyEnvironmentIds]);

  function syncJsonFromForm(nextForm: RunSubmitFormState): void {
    setJsonInput(JSON.stringify(buildJsonFromForm(nextForm), null, 2));
    setJsonError(null);
  }

  function applyJsonToForm(): void {
    setJsonError(null);
    try {
      const parsed = JSON.parse(jsonInput) as unknown;
      const payload = validateJsonPayload(parsed);
      const nextForm: RunSubmitFormState = {
        environment_id: payload.environment_id,
        job_id: payload.job_id,
        driver_vcpu: String(payload.requested_resources.driver_vcpu),
        driver_memory_gb: String(payload.requested_resources.driver_memory_gb),
        executor_vcpu: String(payload.requested_resources.executor_vcpu),
        executor_memory_gb: String(payload.requested_resources.executor_memory_gb),
        executor_instances: String(payload.requested_resources.executor_instances),
        timeout_seconds: String(payload.timeout_seconds ?? 1800),
      };
      setForm(nextForm);
      setPreflightReady(null);
      setPreflightChecks([]);
    } catch (err: unknown) {
      setJsonError(err instanceof Error ? err.message : "Unable to apply JSON payload.");
    }
  }

  function currentEnvironmentIdForChecks(): string {
    if (editorMode === "form") {
      return form.environment_id;
    }
    try {
      const payload = validateJsonPayload(JSON.parse(jsonInput) as unknown);
      return payload.environment_id;
    } catch {
      return "";
    }
  }

  async function checkPreflight() {
    setPreflightError(null);
    setSubmitError(null);
    setPreflightReady(null);
    setPreflightChecks([]);
    setJsonError(null);

    const environmentId = currentEnvironmentIdForChecks();
    if (!environmentId) {
      setPreflightError("Select an environment (or set environment_id in JSON) before running preflight.");
      return;
    }
    if (!readyEnvironmentIds.has(environmentId)) {
      setPreflightError("Selected environment is not ready. Wait for ready status before preflight.");
      return;
    }
    try {
      const preflight = await fetchEnvironmentPreflight(environmentId);
      setPreflightReady(preflight.ready);
      setPreflightChecks(preflight.checks);
    } catch (err: unknown) {
      setPreflightError(friendlyError(err, "Preflight check failed"));
    }
  }

  async function handleSubmit() {
    setSubmitError(null);
    setJsonError(null);

    if (preflightReady !== true) {
      setSubmitError("A successful preflight check is required before submission.");
      return;
    }

    let jobId = "";
    let request: RunSubmitRequest;
    let environmentId = "";

    if (editorMode === "form") {
      if (!form.job_id) {
        setSubmitError("Select a job before submitting.");
        return;
      }
      if (!readyEnvironmentIds.has(form.environment_id)) {
        setSubmitError("Only ready environments can be used for run submission.");
        return;
      }
      try {
        request = {
          requested_resources: {
            driver_vcpu: parsePositiveInt(form.driver_vcpu, "Driver vCPU"),
            driver_memory_gb: parsePositiveInt(form.driver_memory_gb, "Driver memory"),
            executor_vcpu: parsePositiveInt(form.executor_vcpu, "Executor vCPU"),
            executor_memory_gb: parsePositiveInt(form.executor_memory_gb, "Executor memory"),
            executor_instances: parsePositiveInt(form.executor_instances, "Executor instances"),
          },
          timeout_seconds: parsePositiveInt(form.timeout_seconds, "Timeout seconds"),
        };
      } catch (err: unknown) {
        setSubmitError(err instanceof Error ? err.message : "Invalid run configuration.");
        return;
      }
      jobId = form.job_id;
      environmentId = form.environment_id;
    } else {
      let payload: JsonRunPayload;
      try {
        payload = validateJsonPayload(JSON.parse(jsonInput) as unknown);
      } catch (err: unknown) {
        setJsonError(err instanceof Error ? err.message : jsonParseError(err));
        setSubmitError("Fix JSON payload errors before submitting.");
        return;
      }
      if (!readyEnvironmentIds.has(payload.environment_id)) {
        setSubmitError("JSON payload references an environment that is not ready.");
        return;
      }
      const job = jobs.find((item) => item.id === payload.job_id);
      if (!job) {
        setSubmitError("JSON payload job_id does not exist.");
        return;
      }
      if (job.environment_id !== payload.environment_id) {
        setSubmitError("JSON payload job_id does not belong to environment_id.");
        return;
      }
      jobId = payload.job_id;
      environmentId = payload.environment_id;
      request = {
        requested_resources: payload.requested_resources,
        timeout_seconds: payload.timeout_seconds,
        args: payload.args,
        spark_conf: payload.spark_conf,
      };
    }

    const selectedJob = jobs.find((item) => item.id === jobId);
    if (!selectedJob) {
      setSubmitError("Selected job no longer exists. Refresh and try again.");
      return;
    }
    if (selectedJob.environment_id !== environmentId) {
      setSubmitError("Selected job does not belong to the selected environment.");
      return;
    }

    setSubmitBusy(true);
    try {
      const run = await submitRun(jobId, request);
      onRunSubmitted(run);
    } catch (err: unknown) {
      setSubmitError(friendlyError(err, "Run submission failed"));
    } finally {
      setSubmitBusy(false);
    }
  }

  return (
    <div className="card">
      <div className="card-header-row">
        <h3>Submit Run</h3>
        <div className="button-row">
          <button
            type="button"
            className={`button button-sm ${editorMode === "form" ? "" : "button-secondary"}`}
            onClick={() => setEditorMode("form")}
          >
            Form Mode
          </button>
          <button
            type="button"
            className={`button button-sm ${editorMode === "json" ? "" : "button-secondary"}`}
            onClick={() => {
              setEditorMode("json");
              syncJsonFromForm(form);
            }}
          >
            JSON Mode
          </button>
        </div>
      </div>
      <div className="subtle">
        Select an environment and job, run preflight checks, then submit. JSON mode supports direct payload paste.
      </div>

      {editorMode === "form" ? (
        <>
          <div className="checkbox-toggle-row">
            <label className="checkbox-field checkbox-field-toggle">
              <input
                type="checkbox"
                checked={showNonReady}
                onChange={(event) => setShowNonReady(event.target.checked)}
              />
              <span className="checkbox-switch" aria-hidden="true" />
              <span className="checkbox-copy">
                <span className="checkbox-title">Show non-ready environments</span>
                <span className="subtle checkbox-hint">
                  Visible for context only. Non-ready environments stay disabled until they reach ready status.
                </span>
              </span>
            </label>
          </div>

          <div className="form-grid run-submit-grid">
            <label>
              Environment
              <select
                value={form.environment_id}
                onChange={(e) => {
                  const next = { ...form, environment_id: e.target.value, job_id: "" };
                  setForm(next);
                  syncJsonFromForm(next);
                  setPreflightReady(null);
                  setPreflightChecks([]);
                }}
              >
                <option value="">Select environment</option>
                {selectableEnvironments.map((env) => {
                  const ready = env.status === "ready";
                  return (
                    <option key={env.id} value={env.id} disabled={!ready}>
                      {envLabel(env)}{ready ? "" : ` [${env.status}]`}
                    </option>
                  );
                })}
              </select>
            </label>
            <label>
              Job
              <select
                value={form.job_id}
                onChange={(e) => {
                  const next = { ...form, job_id: e.target.value };
                  setForm(next);
                  syncJsonFromForm(next);
                }}
              >
                <option value="">Select job</option>
                {jobsFiltered.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Driver vCPU
              <input type="number" min={1} value={form.driver_vcpu} onChange={(e) => {
                const next = { ...form, driver_vcpu: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
            <label>
              Driver Memory (GB)
              <input type="number" min={1} value={form.driver_memory_gb} onChange={(e) => {
                const next = { ...form, driver_memory_gb: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
            <label>
              Executor vCPU
              <input type="number" min={1} value={form.executor_vcpu} onChange={(e) => {
                const next = { ...form, executor_vcpu: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
            <label>
              Executor Memory (GB)
              <input type="number" min={1} value={form.executor_memory_gb} onChange={(e) => {
                const next = { ...form, executor_memory_gb: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
            <label>
              Executor Instances
              <input type="number" min={1} value={form.executor_instances} onChange={(e) => {
                const next = { ...form, executor_instances: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
            <label>
              Timeout (seconds)
              <input type="number" min={1} value={form.timeout_seconds} onChange={(e) => {
                const next = { ...form, timeout_seconds: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }} />
            </label>
          </div>
        </>
      ) : (
        <div className="json-panel stack">
          <div className="button-row">
            <button type="button" className="button button-sm button-secondary" onClick={() => syncJsonFromForm(form)}>
              Export From Form
            </button>
            <button type="button" className="button button-sm button-secondary" onClick={applyJsonToForm}>
              Apply JSON To Form
            </button>
          </div>
          <label className="multiline-field">
            Run Payload JSON
            <textarea
              className="json-textarea"
              value={jsonInput}
              onChange={(event) => {
                setJsonInput(event.target.value);
                setJsonError(null);
              }}
              rows={18}
            />
          </label>
          <div className="subtle">
            Required keys: <code>environment_id</code>, <code>job_id</code>, <code>requested_resources</code>.
          </div>
          {jsonError ? <div className="error-text">{jsonError}</div> : null}
        </div>
      )}

      <div className="button-row">
        <button type="button" className="button" onClick={checkPreflight}>
          Check Preflight
        </button>
        <button type="button" className="button" disabled={submitBusy || preflightReady !== true} onClick={handleSubmit}>
          {submitBusy ? "Submitting..." : "Submit Run"}
        </button>
      </div>

      {preflightError ? <div className="error-text">{preflightError}</div> : null}
      {submitError ? <div className="error-text">{submitError}</div> : null}

      <div className={preflightReady === false ? "json-panel error-card" : "json-panel"}>
        {preflightReady === null ? (
          <div className="subtle">
            Run <strong>Check Preflight</strong> before submission. Submit stays disabled until all blocking checks pass.
          </div>
        ) : (
          <>
            <div className="subtle run-preflight-status">
              Preflight:
              <span className={badgeClass(preflightReady ? "ready" : "failed")}>
                {preflightReady ? "ready" : "not ready"}
              </span>
            </div>
            {preflightReady ? (
              <div className="success-text">All blocking checks passed. Submission is enabled.</div>
            ) : (
              <div className="error-text">Submission blocked: resolve failing preflight checks, then run preflight again.</div>
            )}

            {preflightChecks.length > 0 ? (
              <ul className="preflight-list">
                {[...preflightFailChecks, ...preflightWarningChecks, ...preflightChecks.filter((c) => c.status === "pass")].map((check, idx) => (
                  <li key={`${check.code}-${idx}`}>
                    [{check.status}] {check.code}: {check.message}
                    {check.remediation ? <div className="subtle">Remediation: {check.remediation}</div> : null}
                  </li>
                ))}
              </ul>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
