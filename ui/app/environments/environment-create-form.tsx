"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createEnvironment } from "@/lib/api";
import { shortId } from "@/lib/format";

type CreateValues = {
  tenantId: string;
  region: string;
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

  function validate(): string[] {
    const nextErrors: string[] = [];
    if (!values.tenantId.trim()) {
      nextErrors.push("Tenant ID is required.");
    }
    if (!values.customerRoleArn.trim()) {
      nextErrors.push("Customer role ARN is required.");
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
    if (!values.eksClusterArn.trim()) {
      nextErrors.push("EKS cluster ARN is required in BYOC-Lite mode.");
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
      setResult(`Environment queued. operation_id=${shortId(op.id)} environment_id=${shortId(op.environment_id)}`);
      router.refresh();
    } catch (err: unknown) {
      setErrors([err instanceof Error ? err.message : "Environment create failed"]);
    } finally {
      setSubmitting(false);
    }
  }

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
    </div>
  );
}
