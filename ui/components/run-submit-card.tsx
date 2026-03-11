"use client";

import { useMemo, useState } from "react";
import {
  Environment,
  Job,
  Run,
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

export function RunSubmitCard({
  environments,
  jobs,
  onRunSubmitted,
}: {
  environments: Environment[];
  jobs: Job[];
  onRunSubmitted: (run: Run) => void;
}) {
  const [form, setForm] = useState<RunSubmitFormState>({
    environment_id: environments[0]?.id ?? "",
    job_id: "",
    driver_vcpu: "1",
    driver_memory_gb: "2",
    executor_vcpu: "1",
    executor_memory_gb: "2",
    executor_instances: "1",
    timeout_seconds: "1800",
  });

  const [preflightReady, setPreflightReady] = useState<boolean | null>(null);
  const [preflightSummary, setPreflightSummary] = useState<string[]>([]);
  const [preflightError, setPreflightError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitBusy, setSubmitBusy] = useState(false);

  const jobsFiltered = useMemo(() => {
    if (!form.environment_id) return jobs;
    return jobs.filter((j) => j.environment_id === form.environment_id);
  }, [jobs, form.environment_id]);

  async function checkPreflight() {
    setPreflightError(null);
    setSubmitError(null);
    setPreflightReady(null);
    setPreflightSummary([]);
    if (!form.environment_id) {
      setPreflightError("Select an environment before running preflight.");
      return;
    }
    try {
      const preflight = await fetchEnvironmentPreflight(form.environment_id);
      setPreflightReady(preflight.ready);
      setPreflightSummary(
        preflight.checks.map((c) => `[${c.status}] ${c.code}: ${c.message}`)
      );
    } catch (err: unknown) {
      setPreflightError(friendlyError(err, "Preflight check failed"));
    }
  }

  async function handleSubmit() {
    setSubmitError(null);
    if (!form.job_id) {
      setSubmitError("Select a job before submitting.");
      return;
    }
    if (preflightReady !== true) {
      setSubmitError("A successful preflight check is required before submission.");
      return;
    }
    const nums = {
      driver_vcpu: Number.parseInt(form.driver_vcpu, 10),
      driver_memory_gb: Number.parseInt(form.driver_memory_gb, 10),
      executor_vcpu: Number.parseInt(form.executor_vcpu, 10),
      executor_memory_gb: Number.parseInt(form.executor_memory_gb, 10),
      executor_instances: Number.parseInt(form.executor_instances, 10),
      timeout_seconds: Number.parseInt(form.timeout_seconds, 10),
    };
    if (Object.values(nums).some((v) => Number.isNaN(v) || v <= 0)) {
      setSubmitError("All resource fields and timeout must be positive integers.");
      return;
    }
    setSubmitBusy(true);
    try {
      const run = await submitRun(form.job_id, {
        requested_resources: {
          driver_vcpu: nums.driver_vcpu,
          driver_memory_gb: nums.driver_memory_gb,
          executor_vcpu: nums.executor_vcpu,
          executor_memory_gb: nums.executor_memory_gb,
          executor_instances: nums.executor_instances,
        },
        timeout_seconds: nums.timeout_seconds,
      });
      onRunSubmitted(run);
    } catch (err: unknown) {
      setSubmitError(friendlyError(err, "Run submission failed"));
    } finally {
      setSubmitBusy(false);
    }
  }

  return (
    <div className="card">
      <h3>Submit Run</h3>
      <div className="subtle">Select an environment and job, run preflight checks, then submit.</div>
      <div className="form-grid">
        <label>
          Environment
          <select
            value={form.environment_id}
            onChange={(e) => {
              setForm((prev) => ({ ...prev, environment_id: e.target.value, job_id: "" }));
              setPreflightReady(null);
              setPreflightSummary([]);
            }}
          >
            <option value="">Select environment</option>
            {environments.map((env) => (
              <option key={env.id} value={env.id}>
                {envLabel(env)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Job
          <select value={form.job_id} onChange={(e) => setForm((prev) => ({ ...prev, job_id: e.target.value }))}>
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
          <input type="number" min={1} value={form.driver_vcpu} onChange={(e) => setForm((prev) => ({ ...prev, driver_vcpu: e.target.value }))} />
        </label>
        <label>
          Driver Memory (GB)
          <input type="number" min={1} value={form.driver_memory_gb} onChange={(e) => setForm((prev) => ({ ...prev, driver_memory_gb: e.target.value }))} />
        </label>
        <label>
          Executor vCPU
          <input type="number" min={1} value={form.executor_vcpu} onChange={(e) => setForm((prev) => ({ ...prev, executor_vcpu: e.target.value }))} />
        </label>
        <label>
          Executor Memory (GB)
          <input type="number" min={1} value={form.executor_memory_gb} onChange={(e) => setForm((prev) => ({ ...prev, executor_memory_gb: e.target.value }))} />
        </label>
        <label>
          Executor Instances
          <input type="number" min={1} value={form.executor_instances} onChange={(e) => setForm((prev) => ({ ...prev, executor_instances: e.target.value }))} />
        </label>
        <label>
          Timeout (seconds)
          <input type="number" min={1} value={form.timeout_seconds} onChange={(e) => setForm((prev) => ({ ...prev, timeout_seconds: e.target.value }))} />
        </label>
      </div>
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
      {preflightReady !== null ? (
        <div className="subtle">
          Preflight:{" "}
          <span className={badgeClass(preflightReady ? "ready" : "failed")}>
            {preflightReady ? "ready" : "not ready"}
          </span>
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
  );
}
