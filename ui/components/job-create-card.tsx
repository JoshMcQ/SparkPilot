"use client";

import { useState } from "react";
import {
  Environment,
  Job,
  JobCreateRequest,
  createJob,
} from "@/lib/api";
import { envLabel, friendlyError } from "@/lib/format";

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

type JobCreateForm = {
  environment_id: string;
  name: string;
  artifact_uri: string;
  artifact_digest: string;
  entrypoint: string;
  args_text: string;
  spark_conf_text: string;
  retry_max_attempts: string;
  timeout_seconds: string;
};

export function JobCreateCard({
  environments,
  onJobCreated,
}: {
  environments: Environment[];
  onJobCreated: (job: Job) => void;
}) {
  const [form, setForm] = useState<JobCreateForm>({
    environment_id: environments[0]?.id ?? "",
    name: "",
    artifact_uri: "",
    artifact_digest: "sha256:placeholder",
    entrypoint: "",
    args_text: "",
    spark_conf_text: "",
    retry_max_attempts: "1",
    timeout_seconds: "1200",
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleCreate() {
    setError(null);
    setSuccess(null);

    const envId = form.environment_id.trim();
    const name = form.name.trim();
    const uri = form.artifact_uri.trim();
    const digest = form.artifact_digest.trim();
    const main = form.entrypoint.trim();
    if (!envId || !name || !uri || !digest || !main) {
      setError("Environment, name, artifact URI, artifact digest, and entrypoint are required.");
      return;
    }
    const retry = Number.parseInt(form.retry_max_attempts, 10);
    const timeout = Number.parseInt(form.timeout_seconds, 10);
    if (Number.isNaN(retry) || retry <= 0) {
      setError("Retry max attempts must be a positive integer.");
      return;
    }
    if (Number.isNaN(timeout) || timeout < 60) {
      setError("Job timeout must be an integer >= 60 seconds.");
      return;
    }
    const parsedConf = parseSparkConf(form.spark_conf_text);
    if (parsedConf.error) {
      setError(parsedConf.error);
      return;
    }
    setBusy(true);
    try {
      const created = await createJob({
        environment_id: envId,
        name,
        artifact_uri: uri,
        artifact_digest: digest,
        entrypoint: main,
        args: parseTextLines(form.args_text),
        spark_conf: parsedConf.conf,
        retry_max_attempts: retry,
        timeout_seconds: timeout,
      });
      setSuccess(`Job "${created.name}" created successfully.`);
      onJobCreated(created);
      setForm((prev) => ({ ...prev, name: "", artifact_uri: "", entrypoint: "", args_text: "", spark_conf_text: "" }));
    } catch (err: unknown) {
      setError(friendlyError(err, "Job creation failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="card">
      <summary className="card-summary">
        <h3>Create Job Template</h3>
        <span className="subtle">Define reusable job definitions with artifact references and Spark configuration.</span>
      </summary>
      <div className="form-grid">
        <label>
          Environment
          <select
            value={form.environment_id}
            onChange={(e) => setForm((prev) => ({ ...prev, environment_id: e.target.value }))}
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
          Job Name
          <input value={form.name} onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))} placeholder="my-spark-job" />
        </label>
        <label>
          Artifact URI
          <input value={form.artifact_uri} onChange={(e) => setForm((prev) => ({ ...prev, artifact_uri: e.target.value }))} placeholder="s3://bucket/job.py" />
        </label>
        <label>
          Artifact Digest
          <input value={form.artifact_digest} onChange={(e) => setForm((prev) => ({ ...prev, artifact_digest: e.target.value }))} />
        </label>
        <label>
          Entrypoint
          <input value={form.entrypoint} onChange={(e) => setForm((prev) => ({ ...prev, entrypoint: e.target.value }))} placeholder="main" />
        </label>
        <label>
          Retry Max Attempts
          <input type="number" min={1} value={form.retry_max_attempts} onChange={(e) => setForm((prev) => ({ ...prev, retry_max_attempts: e.target.value }))} />
        </label>
        <label>
          Timeout (seconds)
          <input type="number" min={60} value={form.timeout_seconds} onChange={(e) => setForm((prev) => ({ ...prev, timeout_seconds: e.target.value }))} />
        </label>
        <label>
          Args (one per line)
          <textarea value={form.args_text} onChange={(e) => setForm((prev) => ({ ...prev, args_text: e.target.value }))} />
        </label>
        <label>
          Spark Conf (key=value per line)
          <textarea value={form.spark_conf_text} onChange={(e) => setForm((prev) => ({ ...prev, spark_conf_text: e.target.value }))} />
        </label>
      </div>
      <div className="button-row">
        <button type="button" className="button" disabled={busy} onClick={handleCreate}>
          {busy ? "Creating..." : "Create Job"}
        </button>
      </div>
      {error ? <div className="error-text">{error}</div> : null}
      {success ? <div className="success-text">{success}</div> : null}
    </details>
  );
}
