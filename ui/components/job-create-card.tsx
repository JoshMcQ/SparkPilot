"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Environment,
  Job,
  JobCreateRequest,
  createJob,
} from "@/lib/api";
import { envLabel, friendlyError } from "@/lib/format";

function parseTextLinesWithNumbers(text: string): Array<{ value: string; line: number }> {
  return text
    .split(/\r?\n/)
    .map((line, idx) => ({ value: line.trim(), line: idx + 1 }))
    .filter((row) => row.value.length > 0);
}

function parseArgs(text: string): string[] {
  return parseTextLinesWithNumbers(text).map((row) => row.value);
}

function parseSparkConf(text: string): { conf: Record<string, string>; errors: string[] } {
  const conf: Record<string, string> = {};
  const errors: string[] = [];
  const lines = parseTextLinesWithNumbers(text);
  for (const row of lines) {
    const idx = row.value.indexOf("=");
    if (idx <= 0 || idx === row.value.length - 1) {
      errors.push(`Line ${row.line}: "${row.value}" must use key=value format.`);
      continue;
    }
    const key = row.value.slice(0, idx).trim();
    const value = row.value.slice(idx + 1).trim();
    if (!key || !value) {
      errors.push(`Line ${row.line}: "${row.value}" must include both key and value.`);
      continue;
    }
    conf[key] = value;
  }
  return { conf, errors };
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

function defaultForm(environments: Environment[]): JobCreateForm {
  return {
    environment_id: environments[0]?.id ?? "",
    name: "",
    artifact_uri: "",
    artifact_digest: "sha256:placeholder",
    entrypoint: "main",
    args_text: "",
    spark_conf_text: "",
    retry_max_attempts: "1",
    timeout_seconds: "1200",
  };
}

function buildPayloadFromForm(form: JobCreateForm): JobCreateRequest {
  const retry = Number.parseInt(form.retry_max_attempts, 10);
  const timeout = Number.parseInt(form.timeout_seconds, 10);
  return {
    environment_id: form.environment_id.trim(),
    name: form.name.trim(),
    artifact_uri: form.artifact_uri.trim(),
    artifact_digest: form.artifact_digest.trim(),
    entrypoint: form.entrypoint.trim(),
    args: parseArgs(form.args_text),
    spark_conf: parseSparkConf(form.spark_conf_text).conf,
    retry_max_attempts: retry,
    timeout_seconds: timeout,
  };
}

function parseJobPayload(value: unknown): JobCreateRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("JSON payload must be an object.");
  }
  const row = value as Record<string, unknown>;
  const payload: JobCreateRequest = {
    environment_id: String(row.environment_id ?? "").trim(),
    name: String(row.name ?? "").trim(),
    artifact_uri: String(row.artifact_uri ?? "").trim(),
    artifact_digest: String(row.artifact_digest ?? "").trim(),
    entrypoint: String(row.entrypoint ?? "").trim(),
    args: [],
    spark_conf: {},
    retry_max_attempts: Number.parseInt(String(row.retry_max_attempts ?? ""), 10),
    timeout_seconds: Number.parseInt(String(row.timeout_seconds ?? ""), 10),
  };

  if (!payload.environment_id) throw new Error("environment_id is required.");
  if (!payload.name) throw new Error("name is required.");
  if (!payload.artifact_uri) throw new Error("artifact_uri is required.");
  if (!payload.artifact_digest) throw new Error("artifact_digest is required.");
  if (!payload.entrypoint) throw new Error("entrypoint is required.");
  if (Number.isNaN(payload.retry_max_attempts) || payload.retry_max_attempts <= 0) {
    throw new Error("retry_max_attempts must be a positive integer.");
  }
  if (Number.isNaN(payload.timeout_seconds) || payload.timeout_seconds < 60) {
    throw new Error("timeout_seconds must be an integer >= 60.");
  }

  if (row.args != null) {
    if (!Array.isArray(row.args) || row.args.some((item) => typeof item !== "string")) {
      throw new Error("args must be an array of strings.");
    }
    payload.args = row.args;
  }
  if (row.spark_conf != null) {
    if (!row.spark_conf || typeof row.spark_conf !== "object" || Array.isArray(row.spark_conf)) {
      throw new Error("spark_conf must be an object.");
    }
    const conf = row.spark_conf as Record<string, unknown>;
    for (const [key, val] of Object.entries(conf)) {
      payload.spark_conf[key] = String(val);
    }
  }
  return payload;
}

function jsonParseError(err: unknown, input?: string): string {
  if (!(err instanceof Error)) {
    return "Invalid JSON payload.";
  }
  const positionMatch = err.message.match(/position\s+(\d+)/i);
  if (positionMatch?.[1]) {
    const position = Number.parseInt(positionMatch[1], 10);
    if (Number.isFinite(position) && input != null) {
      const before = input.slice(0, position);
      const line = before.split(/\r?\n/).length;
      const column = position - (before.lastIndexOf("\n") + 1) + 1;
      return `Invalid JSON at line ${line}, column ${column} (character ${position}).`;
    }
    return `Invalid JSON near character ${positionMatch[1]}.`;
  }
  return err.message;
}

export function JobCreateCard({
  environments,
  onJobCreated,
}: {
  environments: Environment[];
  onJobCreated: (job: Job) => void;
}) {
  const [form, setForm] = useState<JobCreateForm>(defaultForm(environments));
  const [editorMode, setEditorMode] = useState<"form" | "json">("form");
  const [jsonInput, setJsonInput] = useState<string>(() => JSON.stringify(buildPayloadFromForm(defaultForm(environments)), null, 2));
  const [jsonError, setJsonError] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const parsedSparkConf = useMemo(() => parseSparkConf(form.spark_conf_text), [form.spark_conf_text]);

  useEffect(() => {
    if (environments.length === 0) {
      return;
    }
    setForm((prev) => {
      if (!prev.environment_id || !environments.some((env) => env.id === prev.environment_id)) {
        const next = { ...prev, environment_id: environments[0].id };
        setJsonInput(JSON.stringify(buildPayloadFromForm(next), null, 2));
        return next;
      }
      return prev;
    });
  }, [environments]);

  function syncJsonFromForm(nextForm: JobCreateForm): void {
    setJsonInput(JSON.stringify(buildPayloadFromForm(nextForm), null, 2));
    setJsonError(null);
  }

  function applyJsonToForm(): void {
    setJsonError(null);
    try {
      const payload = parseJobPayload(JSON.parse(jsonInput) as unknown);
      const argsText = payload.args.join("\n");
      const confText = Object.entries(payload.spark_conf).map(([k, v]) => `${k}=${v}`).join("\n");
      setForm({
        environment_id: payload.environment_id,
        name: payload.name,
        artifact_uri: payload.artifact_uri,
        artifact_digest: payload.artifact_digest,
        entrypoint: payload.entrypoint,
        args_text: argsText,
        spark_conf_text: confText,
        retry_max_attempts: String(payload.retry_max_attempts),
        timeout_seconds: String(payload.timeout_seconds),
      });
    } catch (err: unknown) {
      setJsonError(err instanceof Error ? err.message : "Unable to apply JSON payload.");
    }
  }

  async function handleCreate() {
    setError(null);
    setSuccess(null);
    setJsonError(null);

    let payload: JobCreateRequest;
    if (editorMode === "json") {
      try {
        payload = parseJobPayload(JSON.parse(jsonInput) as unknown);
      } catch (err: unknown) {
        const detail = jsonParseError(err, jsonInput);
        setJsonError(detail);
        setError("Fix JSON payload errors before creating job.");
        return;
      }
    } else {
      const missing: string[] = [];
      if (!form.environment_id.trim()) missing.push("Environment");
      if (!form.name.trim()) missing.push("Job Name");
      if (!form.artifact_uri.trim()) missing.push("Artifact URI");
      if (!form.artifact_digest.trim()) missing.push("Artifact Digest");
      if (!form.entrypoint.trim()) missing.push("Entrypoint");
      if (missing.length > 0) {
        setError(`Missing required field(s): ${missing.join(", ")}.`);
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
      if (parsedSparkConf.errors.length > 0) {
        setError(parsedSparkConf.errors[0]);
        return;
      }
      payload = {
        environment_id: form.environment_id.trim(),
        name: form.name.trim(),
        artifact_uri: form.artifact_uri.trim(),
        artifact_digest: form.artifact_digest.trim(),
        entrypoint: form.entrypoint.trim(),
        args: parseArgs(form.args_text),
        spark_conf: parsedSparkConf.conf,
        retry_max_attempts: retry,
        timeout_seconds: timeout,
      };
    }

    setBusy(true);
    try {
      const created = await createJob(payload);
      setSuccess(`Job "${created.name}" created successfully.`);
      onJobCreated(created);
      const reset = {
        ...form,
        name: "",
        artifact_uri: "",
        args_text: "",
        spark_conf_text: "",
      };
      setForm(reset);
      syncJsonFromForm(reset);
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

      {editorMode === "form" ? (
        <div className="form-grid job-template-grid">
          <label>
            Environment
            <select
              value={form.environment_id}
              onChange={(e) => {
                const next = { ...form, environment_id: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
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
            Job Name
            <input value={form.name} onChange={(e) => {
              const next = { ...form, name: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} placeholder="my-spark-job" />
          </label>
          <label>
            Artifact URI
            <input value={form.artifact_uri} onChange={(e) => {
              const next = { ...form, artifact_uri: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} placeholder="s3://bucket/job.py" />
          </label>
          <label>
            Artifact Digest
            <input value={form.artifact_digest} onChange={(e) => {
              const next = { ...form, artifact_digest: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} />
          </label>
          <label>
            Entrypoint
            <input value={form.entrypoint} onChange={(e) => {
              const next = { ...form, entrypoint: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} placeholder="main" />
          </label>
          <label>
            Retry Max Attempts
            <input type="number" min={1} value={form.retry_max_attempts} onChange={(e) => {
              const next = { ...form, retry_max_attempts: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} />
          </label>
          <label>
            Timeout (seconds)
            <input type="number" min={60} value={form.timeout_seconds} onChange={(e) => {
              const next = { ...form, timeout_seconds: e.target.value };
              setForm(next);
              syncJsonFromForm(next);
            }} />
          </label>
          <label className="multiline-field">
            Args (one per line)
            <textarea
              value={form.args_text}
              onChange={(e) => {
                const next = { ...form, args_text: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }}
              placeholder={"--date=2026-03-16\n--input=s3://bucket/path/"}
              rows={8}
            />
          </label>
          <label className="multiline-field">
            Spark Conf (key=value per line)
            <textarea
              value={form.spark_conf_text}
              onChange={(e) => {
                const next = { ...form, spark_conf_text: e.target.value };
                setForm(next);
                syncJsonFromForm(next);
              }}
              placeholder={"spark.executor.instances=2\nspark.sql.shuffle.partitions=200"}
              rows={8}
            />
          </label>
          {parsedSparkConf.errors.length > 0 ? (
            <div className="error-text">
              {parsedSparkConf.errors[0]}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="json-panel json-editor-shell stack">
          <div className="json-editor-header">
            <div>
              <div className="json-editor-title">Job Template JSON</div>
              <div className="json-editor-note">
                Paste, edit, and round-trip template payloads for reproducible operations.
              </div>
            </div>
            <div className={`json-editor-status ${jsonError ? "error" : "ok"}`}>
              {jsonError ? "Validation error" : "Valid JSON"}
            </div>
          </div>
          <div className="button-row">
            <button type="button" className="button button-sm button-secondary" onClick={() => syncJsonFromForm(form)}>
              Export From Form
            </button>
            <button type="button" className="button button-sm button-secondary" onClick={applyJsonToForm}>
              Apply JSON To Form
            </button>
          </div>
          <label className="multiline-field json-editor-field">
            <span className="json-editor-label">Payload</span>
            <textarea
              className="json-textarea"
              value={jsonInput}
              onChange={(event) => {
                setJsonInput(event.target.value);
                setJsonError(null);
              }}
              rows={20}
            />
          </label>
          <div className="subtle">
            Required keys: <code>environment_id</code>, <code>name</code>, <code>artifact_uri</code>, <code>artifact_digest</code>, <code>entrypoint</code>.
          </div>
          {jsonError ? <div className="error-text">{jsonError}</div> : null}
        </div>
      )}

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
