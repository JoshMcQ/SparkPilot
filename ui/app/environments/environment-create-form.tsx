"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createEnvironment, fetchEnvironment, fetchProvisioningOperation } from "@/lib/api";
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

export default function EnvironmentCreateForm() {
  const router = useRouter();
  const [values, setValues] = useState<CreateValues>(defaultValues());
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
    const nextErrors = validate();
    if (nextErrors.length > 0) {
      setErrors(nextErrors);
      return;
    }

    setSubmitting(true);
    try {
      const op = await createEnvironment({
        tenant_id: values.tenantId.trim(),
        provisioning_mode: "byoc_lite",
        region: values.region.trim() || "us-east-1",
        instance_architecture: values.instanceArchitecture,
        customer_role_arn: values.customerRoleArn.trim(),
        eks_cluster_arn: values.eksClusterArn.trim(),
        eks_namespace: values.eksNamespace.trim(),
        warm_pool_enabled: values.warmPoolEnabled,
        quotas: {
          max_concurrent_runs: Number.parseInt(values.maxConcurrentRuns, 10),
          max_vcpu: Number.parseInt(values.maxVcpu, 10),
          max_run_seconds: Number.parseInt(values.maxRunSeconds, 10),
        },
      });
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
      <div className="form-grid">
        <label>
          Tenant ID
          <input value={values.tenantId} onChange={(event) => setValues((current) => ({ ...current, tenantId: event.target.value }))} />
        </label>
        <label>
          Region
          <input value={values.region} onChange={(event) => setValues((current) => ({ ...current, region: event.target.value }))} />
        </label>
        <label>
          Instance Architecture
          <select
            value={values.instanceArchitecture}
            onChange={(event) =>
              setValues((current) => ({
                ...current,
                instanceArchitecture: event.target.value as CreateValues["instanceArchitecture"],
              }))
            }
          >
            <option value="mixed">mixed</option>
            <option value="x86_64">x86_64</option>
            <option value="arm64">arm64</option>
          </select>
        </label>
        <label>
          Customer Role ARN
          <input
            value={values.customerRoleArn}
            onChange={(event) => setValues((current) => ({ ...current, customerRoleArn: event.target.value }))}
          />
        </label>
        <label>
          Max Concurrent Runs
          <input
            type="number"
            min={1}
            value={values.maxConcurrentRuns}
            onChange={(event) => setValues((current) => ({ ...current, maxConcurrentRuns: event.target.value }))}
          />
        </label>
        <label>
          Max vCPU
          <input
            type="number"
            min={1}
            value={values.maxVcpu}
            onChange={(event) => setValues((current) => ({ ...current, maxVcpu: event.target.value }))}
          />
        </label>
        <label>
          Max Run Seconds
          <input
            type="number"
            min={60}
            value={values.maxRunSeconds}
            onChange={(event) => setValues((current) => ({ ...current, maxRunSeconds: event.target.value }))}
          />
        </label>
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={values.warmPoolEnabled}
            onChange={(event) => setValues((current) => ({ ...current, warmPoolEnabled: event.target.checked }))}
          />
          Warm Pool Enabled
        </label>
        <label>
          EKS Cluster ARN
          <input
            value={values.eksClusterArn}
            onChange={(event) => setValues((current) => ({ ...current, eksClusterArn: event.target.value }))}
          />
        </label>
        <label>
          EKS Namespace
          <input
            value={values.eksNamespace}
            onChange={(event) => setValues((current) => ({ ...current, eksNamespace: event.target.value }))}
          />
        </label>
      </div>

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
