"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { EnvironmentCreateRequest, createEnvironment, fetchEnvironment, fetchProvisioningOperation } from "@/lib/api";
import { shortId } from "@/lib/format";

type CreateValues = {
  tenantId: string;
  region: string;
  instanceArchitecture: "mixed" | "x86_64" | "arm64";
  customerRoleArn: string;
  eksClusterArn: string;
  eksNamespace: string;
  warmPoolEnabled: boolean;
  maxConcurrentRuns: string;
  maxVcpu: string;
  maxRunSeconds: string;
};

function defaultValues(): CreateValues {
  return {
    tenantId: "",
    region: "us-east-1",
    instanceArchitecture: "mixed",
    customerRoleArn: "",
    eksClusterArn: "",
    eksNamespace: "",
    warmPoolEnabled: false,
    maxConcurrentRuns: "10",
    maxVcpu: "256",
    maxRunSeconds: "7200",
  };
}

function parsePositiveInt(value: string, field: string): number {
  const parsed = Number.parseInt(value, 10);
  if (Number.isNaN(parsed) || parsed <= 0) {
    throw new Error(`${field} must be a positive integer.`);
  }
  return parsed;
}

function buildPayloadFromValues(values: CreateValues): EnvironmentCreateRequest {
  const maxConcurrentRuns = Number.parseInt(values.maxConcurrentRuns, 10);
  const maxVcpu = Number.parseInt(values.maxVcpu, 10);
  const maxRunSeconds = Number.parseInt(values.maxRunSeconds, 10);
  return {
    tenant_id: values.tenantId.trim(),
    provisioning_mode: "byoc_lite",
    region: values.region.trim() || "us-east-1",
    instance_architecture: values.instanceArchitecture,
    customer_role_arn: values.customerRoleArn.trim(),
    eks_cluster_arn: values.eksClusterArn.trim(),
    eks_namespace: values.eksNamespace.trim(),
    warm_pool_enabled: values.warmPoolEnabled,
    quotas: {
      max_concurrent_runs: Number.isNaN(maxConcurrentRuns) ? 0 : maxConcurrentRuns,
      max_vcpu: Number.isNaN(maxVcpu) ? 0 : maxVcpu,
      max_run_seconds: Number.isNaN(maxRunSeconds) ? 0 : maxRunSeconds,
    },
  };
}

function parseEnvironmentPayload(value: unknown): EnvironmentCreateRequest {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("JSON payload must be an object.");
  }
  const row = value as Record<string, unknown>;
  const mode = String(row.provisioning_mode ?? "byoc_lite").trim();
  if (mode !== "byoc_lite") {
    throw new Error("provisioning_mode must be byoc_lite in this UI.");
  }

  const quotas = row.quotas;
  if (!quotas || typeof quotas !== "object" || Array.isArray(quotas)) {
    throw new Error("quotas object is required.");
  }
  const quotaRow = quotas as Record<string, unknown>;

  const arch = String(row.instance_architecture ?? "mixed").trim();
  if (!["mixed", "x86_64", "arm64"].includes(arch)) {
    throw new Error("instance_architecture must be one of: mixed, x86_64, arm64.");
  }

  const payload: EnvironmentCreateRequest = {
    tenant_id: String(row.tenant_id ?? "").trim(),
    provisioning_mode: "byoc_lite",
    region: String(row.region ?? "").trim() || "us-east-1",
    instance_architecture: arch as CreateValues["instanceArchitecture"],
    customer_role_arn: String(row.customer_role_arn ?? "").trim(),
    eks_cluster_arn: String(row.eks_cluster_arn ?? "").trim(),
    eks_namespace: String(row.eks_namespace ?? "").trim(),
    warm_pool_enabled: Boolean(row.warm_pool_enabled ?? false),
    quotas: {
      max_concurrent_runs: parsePositiveInt(String(quotaRow.max_concurrent_runs ?? ""), "quotas.max_concurrent_runs"),
      max_vcpu: parsePositiveInt(String(quotaRow.max_vcpu ?? ""), "quotas.max_vcpu"),
      max_run_seconds: parsePositiveInt(String(quotaRow.max_run_seconds ?? ""), "quotas.max_run_seconds"),
    },
  };

  if (!payload.tenant_id) {
    throw new Error("tenant_id is required.");
  }
  if (!payload.customer_role_arn) {
    throw new Error("customer_role_arn is required.");
  }
  if (!payload.eks_cluster_arn) {
    throw new Error("eks_cluster_arn is required.");
  }
  if (!payload.eks_namespace) {
    throw new Error("eks_namespace is required.");
  }

  return payload;
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

export default function EnvironmentCreateForm() {
  const router = useRouter();
  const [values, setValues] = useState<CreateValues>(defaultValues());
  const [editorMode, setEditorMode] = useState<"form" | "json">("form");
  const [jsonInput, setJsonInput] = useState<string>(() => JSON.stringify(buildPayloadFromValues(defaultValues()), null, 2));
  const [jsonError, setJsonError] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<string>("");
  const [operationId, setOperationId] = useState<string>("");
  const [operationState, setOperationState] = useState<string>("");
  const [operationStep, setOperationStep] = useState<string>("");
  const [operationMessage, setOperationMessage] = useState<string>("");
  const [environmentId, setEnvironmentId] = useState<string>("");
  const [environmentStatus, setEnvironmentStatus] = useState<string>("");

  const trackingActive = operationId && operationState !== "ready" && operationState !== "failed";
  const remediationSnippet = operationMessage.includes("Remediation:")
    ? operationMessage.slice(operationMessage.indexOf("Remediation:")).trim()
    : "";

  function setAndSync(next: CreateValues): void {
    setValues(next);
    setJsonInput(JSON.stringify(buildPayloadFromValues(next), null, 2));
    setJsonError("");
  }

  function applyJsonToForm(): void {
    setJsonError("");
    try {
      const payload = parseEnvironmentPayload(JSON.parse(jsonInput) as unknown);
      setAndSync({
        tenantId: payload.tenant_id,
        region: payload.region,
        instanceArchitecture: payload.instance_architecture ?? "mixed",
        customerRoleArn: payload.customer_role_arn,
        eksClusterArn: payload.eks_cluster_arn ?? "",
        eksNamespace: payload.eks_namespace ?? "",
        warmPoolEnabled: payload.warm_pool_enabled,
        maxConcurrentRuns: String(payload.quotas.max_concurrent_runs),
        maxVcpu: String(payload.quotas.max_vcpu),
        maxRunSeconds: String(payload.quotas.max_run_seconds),
      });
    } catch (err: unknown) {
      setJsonError(err instanceof Error ? err.message : "Unable to apply JSON payload.");
    }
  }

  function validate(): string[] {
    const nextErrors: string[] = [];
    const customerRoleArn = values.customerRoleArn.trim();
    const eksClusterArn = values.eksClusterArn.trim();

    const hasPlaceholder = (value: string) => value.includes("<") || value.includes(">");
    const iamRoleArnPattern = /^arn:aws[a-zA-Z-]*:iam::\d{12}:role\/.+$/;
    const eksClusterArnPattern = /^arn:aws[a-zA-Z-]*:eks:[a-z0-9-]+:\d{12}:cluster\/[A-Za-z0-9._\-]+$/;

    if (!values.tenantId.trim()) {
      nextErrors.push("Tenant ID is required.");
    }
    if (!customerRoleArn) {
      nextErrors.push("Customer role ARN is required.");
    } else if (hasPlaceholder(customerRoleArn)) {
      nextErrors.push("Customer role ARN contains placeholder markers. Replace <...> with real values.");
    } else if (!iamRoleArnPattern.test(customerRoleArn)) {
      nextErrors.push("Customer role ARN must match arn:aws:iam::<12-digit-account-id>:role/<role-name>.");
    }
    const maxConcurrentRuns = Number.parseInt(values.maxConcurrentRuns, 10);
    const maxVcpu = Number.parseInt(values.maxVcpu, 10);
    const maxRunSeconds = Number.parseInt(values.maxRunSeconds, 10);
    if (Number.isNaN(maxConcurrentRuns) || maxConcurrentRuns <= 0) {
      nextErrors.push("Max concurrent runs must be a positive integer.");
    }
    if (Number.isNaN(maxVcpu) || maxVcpu <= 0) {
      nextErrors.push("Max vCPU must be a positive integer.");
    }
    if (Number.isNaN(maxRunSeconds) || maxRunSeconds < 60) {
      nextErrors.push("Max run seconds must be an integer >= 60.");
    }
    if (!eksClusterArn) {
      nextErrors.push("EKS cluster ARN is required in BYOC-Lite mode.");
    } else if (hasPlaceholder(eksClusterArn)) {
      nextErrors.push("EKS cluster ARN contains placeholder markers. Replace <...> with real values.");
    } else if (!eksClusterArnPattern.test(eksClusterArn)) {
      nextErrors.push("EKS cluster ARN must match arn:aws:eks:<region>:<12-digit-account-id>:cluster/<cluster-name>.");
    }
    if (!values.eksNamespace.trim()) {
      nextErrors.push("EKS namespace is required in BYOC-Lite mode.");
    }
    return nextErrors;
  }

  async function submit() {
    setErrors([]);
    setResult("");
    setJsonError("");

    let payload: EnvironmentCreateRequest;
    if (editorMode === "json") {
      try {
        payload = parseEnvironmentPayload(JSON.parse(jsonInput) as unknown);
      } catch (err: unknown) {
        const detail = err instanceof Error ? err.message : jsonParseError(err);
        setJsonError(detail);
        setErrors(["Fix JSON payload errors before creating environment."]);
        return;
      }
    } else {
      const nextErrors = validate();
      if (nextErrors.length > 0) {
        setErrors(nextErrors);
        return;
      }
      payload = buildPayloadFromValues(values);
    }

    setSubmitting(true);
    try {
      const op = await createEnvironment(payload);
      setOperationId(op.id);
      setOperationState(op.state);
      setOperationStep(op.step);
      setOperationMessage(op.message ?? "");
      setEnvironmentId(op.environment_id);
      setEnvironmentStatus("provisioning");
      setResult(`Environment queued. operation_id=${shortId(op.id)} environment_id=${shortId(op.environment_id)}`);
      router.refresh();
    } catch (err: unknown) {
      setErrors([err instanceof Error ? err.message : "Environment create failed"]);
    } finally {
      setSubmitting(false);
    }
  }

  useEffect(() => {
    if (!trackingActive) {
      return;
    }
    let mounted = true;
    let tickCount = 0;
    const maxTicks = 180; // 15 minutes at 5s interval.

    const poll = async () => {
      tickCount += 1;
      if (tickCount > maxTicks) {
        if (mounted) {
          setErrors((prev) => [...prev, "Provisioning tracker timed out after 15 minutes."]);
        }
        return;
      }
      try {
        const op = await fetchProvisioningOperation(operationId);
        if (!mounted) {
          return;
        }
        setOperationState(op.state);
        setOperationStep(op.step);
        setOperationMessage(op.message ?? "");
        if (environmentId) {
          const env = await fetchEnvironment(environmentId);
          if (!mounted) {
            return;
          }
          setEnvironmentStatus(env.status);
        }
        if (op.state === "ready" || op.state === "failed") {
          router.refresh();
        }
      } catch (err: unknown) {
        if (!mounted) {
          return;
        }
        setErrors((prev) => [...prev, err instanceof Error ? err.message : "Provisioning status refresh failed"]);
      }
    };

    void poll();
    const id = setInterval(() => {
      void poll();
    }, 5000);

    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [environmentId, operationId, router, trackingActive]);

  return (
    <div className="card">
      <h3>Create Environment</h3>
      <div className="subtle">BYOC-Lite mode only. Provide target EKS cluster ARN and namespace.</div>
      <div className="button-row">
        <button type="button" className={`button button-sm ${editorMode === "form" ? "" : "button-secondary"}`} onClick={() => setEditorMode("form")}>
          Form Mode
        </button>
        <button
          type="button"
          className={`button button-sm ${editorMode === "json" ? "" : "button-secondary"}`}
          onClick={() => {
            setEditorMode("json");
            setJsonInput(JSON.stringify(buildPayloadFromValues(values), null, 2));
            setJsonError("");
          }}
        >
          JSON Mode
        </button>
      </div>

      {editorMode === "form" ? (
        <div className="form-grid">
          <label>
            Tenant ID
            <input value={values.tenantId} onChange={(event) => setAndSync({ ...values, tenantId: event.target.value })} />
          </label>
          <label>
            Region
            <input value={values.region} onChange={(event) => setAndSync({ ...values, region: event.target.value })} />
          </label>
          <label>
            Instance Architecture
            <select
              value={values.instanceArchitecture}
              onChange={(event) =>
                setAndSync({
                  ...values,
                  instanceArchitecture: event.target.value as CreateValues["instanceArchitecture"],
                })
              }
            >
              <option value="mixed">mixed</option>
              <option value="x86_64">x86_64</option>
              <option value="arm64">arm64</option>
            </select>
          </label>
          {values.instanceArchitecture === "arm64" ? (
            <div className="subtle" style={{ gridColumn: "1 / -1", marginTop: -4, padding: "6px 8px", background: "var(--color-surface-2, #f6f8fa)", borderRadius: 4, border: "1px solid var(--color-border, #e1e4e8)" }}>
              Graviton instances (arm64) offer up to 40% better price-performance for Spark workloads. Requires EMR releases with Graviton support — check the release lifecycle table below.
            </div>
          ) : null}
          <label>
            Customer Role ARN
            <input value={values.customerRoleArn} onChange={(event) => setAndSync({ ...values, customerRoleArn: event.target.value })} />
          </label>
          <label>
            Max Concurrent Runs
            <input type="number" min={1} value={values.maxConcurrentRuns} onChange={(event) => setAndSync({ ...values, maxConcurrentRuns: event.target.value })} />
          </label>
          <label>
            Max vCPU
            <input type="number" min={1} value={values.maxVcpu} onChange={(event) => setAndSync({ ...values, maxVcpu: event.target.value })} />
          </label>
          <label>
            Max Run Seconds
            <input type="number" min={60} value={values.maxRunSeconds} onChange={(event) => setAndSync({ ...values, maxRunSeconds: event.target.value })} />
          </label>
          <label className="checkbox-field">
            <input type="checkbox" checked={values.warmPoolEnabled} onChange={(event) => setAndSync({ ...values, warmPoolEnabled: event.target.checked })} />
            Warm Pool Enabled
          </label>
          <label>
            EKS Cluster ARN
            <input value={values.eksClusterArn} onChange={(event) => setAndSync({ ...values, eksClusterArn: event.target.value })} />
          </label>
          <label>
            EKS Namespace
            <input value={values.eksNamespace} onChange={(event) => setAndSync({ ...values, eksNamespace: event.target.value })} />
          </label>
        </div>
      ) : (
        <div className="json-panel stack">
          <div className="button-row">
            <button type="button" className="button button-sm button-secondary" onClick={() => setJsonInput(JSON.stringify(buildPayloadFromValues(values), null, 2))}>
              Export From Form
            </button>
            <button type="button" className="button button-sm button-secondary" onClick={applyJsonToForm}>
              Apply JSON To Form
            </button>
          </div>
          <label className="multiline-field">
            Environment JSON
            <textarea
              className="json-textarea"
              value={jsonInput}
              onChange={(event) => {
                setJsonInput(event.target.value);
                setJsonError("");
              }}
              rows={18}
            />
          </label>
          <div className="subtle">
            Required keys: <code>tenant_id</code>, <code>region</code>, <code>customer_role_arn</code>, <code>eks_cluster_arn</code>, <code>eks_namespace</code>, <code>quotas</code>.
          </div>
          {jsonError ? <div className="error-text">{jsonError}</div> : null}
        </div>
      )}

      <div className="button-row">
        <button type="button" className="button" disabled={submitting} onClick={submit}>
          {submitting ? "Creating..." : "Create Environment"}
        </button>
      </div>

      {errors.length > 0 ? (
        <ul className="error-list">
          {errors.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {result ? <div className="success-text">{result}</div> : null}

      {operationId ? (
        <div className="card" style={{ marginTop: 12 }}>
          <h3>Provisioning Progress</h3>
          <div className="subtle">
            operation=<code>{shortId(operationId)}</code> environment=<code>{shortId(environmentId)}</code>
          </div>
          <div className="form-grid" style={{ marginTop: 8 }}>
            <div>
              <div className="subtle">Operation State</div>
              <span className={`badge ${operationState}`}>{operationState || "-"}</span>
            </div>
            <div>
              <div className="subtle">Current Step</div>
              <div>{operationStep || "-"}</div>
            </div>
            <div>
              <div className="subtle">Environment Status</div>
              <span className={`badge ${environmentStatus || "muted"}`}>{environmentStatus || "unknown"}</span>
            </div>
          </div>
          <div className="subtle" style={{ marginTop: 8 }}>
            {operationMessage || "Waiting for worker updates..."}
          </div>
          {operationState === "failed" && remediationSnippet ? (
            <div className="error-text" style={{ marginTop: 8 }}>
              {remediationSnippet}
            </div>
          ) : null}
          {trackingActive ? (
            <div className="subtle" style={{ marginTop: 6 }}>
              Live refresh every 5 seconds.
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
