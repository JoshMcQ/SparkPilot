"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  ByocLiteDiscoveredCluster,
  EnvironmentCreateRequest,
  createEnvironment,
  discoverByocLiteTargets,
  fetchAuthMe,
  fetchEnvironment,
  fetchProvisioningOperation,
} from "@/lib/api";
import { shortId } from "@/lib/format";

type SetupStatus = "blocked" | "waiting" | "ready";

type CreateValues = {
  tenantIdOverride: string;
  region: string;
  accountId: string;
  roleName: string;
  manualRoleArnEnabled: boolean;
  manualRoleArn: string;
  manualClusterArnEnabled: boolean;
  manualClusterArn: string;
  selectedClusterArn: string;
  eksNamespace: string;
  instanceArchitecture: "mixed" | "x86_64" | "arm64";
  warmPoolEnabled: boolean;
  maxConcurrentRuns: string;
  maxVcpu: string;
  maxRunSeconds: string;
};

const IAM_ROLE_ARN_PATTERN = /^arn:aws[a-zA-Z-]*:iam::(\d{12}):role\/.+$/;
const ACCOUNT_ID_PATTERN = /^\d{12}$/;
const ROLE_NAME_PATTERN = /^[A-Za-z0-9+=,.@_-]{1,64}$/;
const EKS_CLUSTER_ARN_PATTERN = /^arn:aws[a-zA-Z-]*:eks:[a-z0-9-]+:\d{12}:cluster\/[A-Za-z0-9._\-]+$/;
const EKS_NAMESPACE_PATTERN = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const RESERVED_NAMESPACES = new Set(["default", "kube-system", "kube-public", "kube-node-lease", "emr-workloads"]);

function defaultValues(): CreateValues {
  return {
    tenantIdOverride: "",
    region: "us-east-1",
    accountId: "",
    roleName: "SparkPilotByocLiteRole",
    manualRoleArnEnabled: false,
    manualRoleArn: "",
    manualClusterArnEnabled: false,
    manualClusterArn: "",
    selectedClusterArn: "",
    eksNamespace: "",
    instanceArchitecture: "mixed",
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

function namespaceFragment(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, "-")
    .replace(/-{2,}/g, "-")
    .replace(/^-+/, "")
    .replace(/-+$/, "");
}

function suggestedNamespace(tenantId: string, clusterName: string): string {
  const tenantPart = namespaceFragment(tenantId).slice(0, 20) || "tenant";
  const clusterPart = namespaceFragment(clusterName).slice(0, 20) || "cluster";
  const candidate = `sparkpilot-${tenantPart}-${clusterPart}`.replace(/-+$/, "");
  return candidate.slice(0, 63).replace(/-+$/, "") || "sparkpilot";
}

function extractClusterNameFromArn(clusterArn: string): string {
  const marker = ":cluster/";
  if (!clusterArn.includes(marker)) {
    return "";
  }
  return clusterArn.split(marker, 2)[1] ?? "";
}

function roleArnFromValues(values: CreateValues): string {
  if (values.manualRoleArnEnabled) {
    return values.manualRoleArn.trim();
  }
  const accountId = values.accountId.trim();
  const roleName = values.roleName.trim();
  if (!accountId || !roleName) {
    return "";
  }
  return `arn:aws:iam::${accountId}:role/${roleName}`;
}

function clusterArnFromValues(values: CreateValues): string {
  return values.manualClusterArnEnabled
    ? values.manualClusterArn.trim()
    : values.selectedClusterArn.trim();
}

function buildPayloadFromValues(values: CreateValues, tenantId: string): EnvironmentCreateRequest {
  return {
    tenant_id: tenantId,
    provisioning_mode: "byoc_lite",
    region: values.region.trim() || "us-east-1",
    instance_architecture: values.instanceArchitecture,
    customer_role_arn: roleArnFromValues(values),
    eks_cluster_arn: clusterArnFromValues(values),
    eks_namespace: values.eksNamespace.trim(),
    warm_pool_enabled: values.warmPoolEnabled,
    quotas: {
      max_concurrent_runs: parsePositiveInt(values.maxConcurrentRuns, "Max concurrent runs"),
      max_vcpu: parsePositiveInt(values.maxVcpu, "Max vCPU"),
      max_run_seconds: parsePositiveInt(values.maxRunSeconds, "Max run seconds"),
    },
  };
}

export default function EnvironmentCreateForm({
  onEnvironmentQueued,
}: {
  onEnvironmentQueued?: (environmentId: string, operationId: string) => void;
}) {
  const router = useRouter();
  const [values, setValues] = useState<CreateValues>(defaultValues());
  const [identityTenantId, setIdentityTenantId] = useState<string>("");
  const [identityActor, setIdentityActor] = useState<string>("");
  const [identityLoading, setIdentityLoading] = useState(true);
  const [identityError, setIdentityError] = useState<string>("");
  const [clusters, setClusters] = useState<ByocLiteDiscoveredCluster[]>([]);
  const [discoveryLoading, setDiscoveryLoading] = useState(false);
  const [discoveryError, setDiscoveryError] = useState<string>("");
  const [discoveryHint, setDiscoveryHint] = useState<string>("");
  const [discoveredNamespaceHint, setDiscoveredNamespaceHint] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [result, setResult] = useState<string>("");
  const [operationId, setOperationId] = useState<string>("");
  const [operationState, setOperationState] = useState<string>("");
  const [operationStep, setOperationStep] = useState<string>("");
  const [operationMessage, setOperationMessage] = useState<string>("");
  const [environmentId, setEnvironmentId] = useState<string>("");
  const [environmentStatus, setEnvironmentStatus] = useState<string>("");

  const effectiveTenantId = values.tenantIdOverride.trim() || identityTenantId;
  const resolvedRoleArn = roleArnFromValues(values);
  const resolvedClusterArn = clusterArnFromValues(values);
  const discoveryContext = `${resolvedRoleArn}|${(values.region.trim() || "us-east-1").toLowerCase()}`;
  const discoveryContextRef = useRef(discoveryContext);
  const trackingActive = operationId && operationState !== "ready" && operationState !== "failed";
  const remediationSnippet = operationMessage.includes("Remediation:")
    ? operationMessage.slice(operationMessage.indexOf("Remediation:")).trim()
    : "";

  useEffect(() => {
    let mounted = true;
    const loadIdentity = async () => {
      setIdentityLoading(true);
      setIdentityError("");
      try {
        const me = await fetchAuthMe();
        if (!mounted) return;
        if (!me) {
          setIdentityError("No authenticated identity context found. Sign in before creating environments.");
          return;
        }
        setIdentityActor(me.actor);
        if (me.tenant_id) {
          setIdentityTenantId(me.tenant_id);
        } else {
          setIdentityError("Identity is missing tenant mapping. Complete Access mapping or provide advanced tenant override.");
        }
      } catch {
        if (!mounted) return;
        setIdentityError("Unable to resolve identity context from /v1/auth/me.");
      } finally {
        if (mounted) setIdentityLoading(false);
      }
    };
    void loadIdentity();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (discoveryContextRef.current === discoveryContext) {
      return;
    }
    discoveryContextRef.current = discoveryContext;
    setClusters([]);
    setDiscoveryHint("");
    setDiscoveredNamespaceHint("");
    setDiscoveryError("");
    setValues((prev) => {
      if (prev.manualClusterArnEnabled || !prev.selectedClusterArn) {
        return prev;
      }
      return { ...prev, selectedClusterArn: "" };
    });
  }, [discoveryContext]);

  useEffect(() => {
    if (!values.selectedClusterArn || values.eksNamespace.trim()) {
      return;
    }
    const selectedCluster = clusters.find((item) => item.arn === values.selectedClusterArn);
    const clusterName = selectedCluster?.name ?? extractClusterNameFromArn(values.selectedClusterArn);
    if (!clusterName || !effectiveTenantId) {
      return;
    }
    setValues((prev) => ({
      ...prev,
      eksNamespace: suggestedNamespace(effectiveTenantId, clusterName),
    }));
  }, [clusters, effectiveTenantId, values.eksNamespace, values.selectedClusterArn]);

  const setupReadiness = useMemo((): { status: SetupStatus; detail: string; remediation?: string } => {
    if (identityLoading) {
      return { status: "waiting", detail: "Resolving tenant and identity context..." };
    }
    if (!effectiveTenantId) {
      return {
        status: "blocked",
        detail: "Tenant context is not resolved yet.",
        remediation: identityError || "Map the identity to a tenant in Access before setup.",
      };
    }
    if (discoveryLoading) {
      return { status: "waiting", detail: "Discovering clusters from AWS..." };
    }
    if (discoveryError && !values.manualClusterArnEnabled) {
      return {
        status: "blocked",
        detail: "AWS discovery failed.",
        remediation: `${discoveryError} You can switch to manual cluster ARN in Advanced to continue.`,
      };
    }
    if (!resolvedRoleArn) {
      return {
        status: "blocked",
        detail: "Customer role is incomplete.",
        remediation: "Provide AWS account + role name (or manual role ARN in Advanced).",
      };
    }
    if (!resolvedClusterArn) {
      return {
        status: "blocked",
        detail: "No EKS cluster is selected yet.",
        remediation: "Run discovery and select a cluster, or set manual cluster ARN in Advanced.",
      };
    }
    if (!values.eksNamespace.trim()) {
      return {
        status: "blocked",
        detail: "Namespace is missing.",
        remediation: "Use the generated namespace or provide a namespace value.",
      };
    }
    return { status: "ready", detail: "Inputs are valid and ready for environment creation." };
  }, [
    discoveryError,
    discoveryLoading,
    effectiveTenantId,
    identityError,
    identityLoading,
    resolvedClusterArn,
    resolvedRoleArn,
    values.manualClusterArnEnabled,
    values.eksNamespace,
  ]);

  function validate(): string[] {
    const nextErrors: string[] = [];

    if (!effectiveTenantId) {
      nextErrors.push("Tenant context is required. Resolve /v1/auth/me mapping or provide advanced tenant override.");
    }

    if (!resolvedRoleArn) {
      nextErrors.push("Customer role ARN is required.");
    } else if (resolvedRoleArn.includes("<") || resolvedRoleArn.includes(">")) {
      nextErrors.push("Customer role ARN contains placeholder markers. Replace <...> with real values.");
    } else if (!IAM_ROLE_ARN_PATTERN.test(resolvedRoleArn)) {
      nextErrors.push("Customer role ARN must match arn:aws:iam::<12-digit-account-id>:role/<role-name>.");
    }

    if (!values.manualRoleArnEnabled) {
      if (!ACCOUNT_ID_PATTERN.test(values.accountId.trim())) {
        nextErrors.push("AWS account ID must be a 12-digit number.");
      }
      if (!ROLE_NAME_PATTERN.test(values.roleName.trim())) {
        nextErrors.push("Role name can contain letters, numbers, and +=,.@_- only.");
      }
    }

    if (!resolvedClusterArn) {
      nextErrors.push("Select a discovered EKS cluster or provide a manual cluster ARN.");
    } else if (!EKS_CLUSTER_ARN_PATTERN.test(resolvedClusterArn)) {
      nextErrors.push("EKS cluster ARN must match arn:aws:eks:<region>:<12-digit-account-id>:cluster/<cluster-name>.");
    }

    const namespace = values.eksNamespace.trim();
    if (!namespace) {
      nextErrors.push("EKS namespace is required in BYOC-Lite mode.");
    } else if (!EKS_NAMESPACE_PATTERN.test(namespace)) {
      nextErrors.push("EKS namespace must be lowercase alphanumeric with optional '-' separators.");
    } else if (RESERVED_NAMESPACES.has(namespace)) {
      nextErrors.push(`EKS namespace '${namespace}' is reserved. Choose a tenant-specific namespace.`);
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
    return nextErrors;
  }

  async function runDiscovery() {
    setErrors([]);
    setDiscoveryError("");
    setDiscoveryHint("");
    setDiscoveredNamespaceHint("");

    if (!resolvedRoleArn) {
      setDiscoveryError("Customer role ARN is incomplete. Fill account + role name or set manual role ARN.");
      return;
    }
    if (!IAM_ROLE_ARN_PATTERN.test(resolvedRoleArn)) {
      setDiscoveryError("Customer role ARN format is invalid.");
      return;
    }

    setDiscoveryLoading(true);
    try {
      const discovered = await discoverByocLiteTargets(resolvedRoleArn, values.region);
      const options = discovered.clusters ?? [];
      setClusters(options);
      if (!values.accountId.trim() && discovered.account_id && !values.manualRoleArnEnabled) {
        setValues((prev) => ({ ...prev, accountId: discovered.account_id ?? prev.accountId }));
      }
      if (options.length === 0) {
        setValues((prev) => ({ ...prev, selectedClusterArn: "" }));
        setDiscoveryError(
          "No EKS clusters were discovered for this role and region. Remediation: verify role permissions and region."
        );
        return;
      }

      const recommendedArn = discovered.recommended_cluster_arn ?? options[0].arn;
      const selectedCluster = options.find((item) => item.arn === recommendedArn) ?? options[0];
      setValues((prev) => ({
        ...prev,
        selectedClusterArn: recommendedArn,
        eksNamespace: prev.eksNamespace.trim() || suggestedNamespace(effectiveTenantId || identityActor, selectedCluster.name),
      }));
      setDiscoveredNamespaceHint(discovered.namespace_suggestion || "");
      setDiscoveryHint(
        `Discovered ${options.length} cluster${options.length === 1 ? "" : "s"} in ${discovered.region}.`
      );
    } catch (err: unknown) {
      setClusters([]);
      setValues((prev) => ({ ...prev, selectedClusterArn: "" }));
      setDiscoveryError(err instanceof Error ? err.message : "Cluster discovery failed.");
    } finally {
      setDiscoveryLoading(false);
    }
  }

  async function submit() {
    setErrors([]);
    setResult("");
    const validationErrors = validate();
    if (validationErrors.length > 0) {
      setErrors(validationErrors);
      return;
    }

    const payload = buildPayloadFromValues(values, effectiveTenantId);
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
      onEnvironmentQueued?.(op.environment_id, op.id);
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
    const maxTicks = 180;

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
        if (!mounted) return;
        setOperationState(op.state);
        setOperationStep(op.step);
        setOperationMessage(op.message ?? "");
        if (environmentId) {
          const env = await fetchEnvironment(environmentId);
          if (!mounted) return;
          setEnvironmentStatus(env.status);
        }
        if (op.state === "ready" || op.state === "failed") {
          router.refresh();
        }
      } catch (err: unknown) {
        if (!mounted) return;
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
    <div className="card" data-testid="assisted-environment-setup">
      <h3>Assisted BYOC-Lite Environment Setup</h3>
      <div className="subtle">
        Cluster ARN entry is now assisted. Discover clusters first, then select one and use the generated namespace.
      </div>

      <div className="card" style={{ marginTop: 12 }}>
        <div className="card-header-row">
          <strong>Setup readiness</strong>
          <span className={`badge ${setupReadiness.status === "ready" ? "ready" : setupReadiness.status === "waiting" ? "queued" : "failed"}`}>
            {setupReadiness.status}
          </span>
        </div>
        <div className="subtle" style={{ marginTop: 8 }}>
          {setupReadiness.detail}
        </div>
        {setupReadiness.remediation ? (
          <div className="error-text" style={{ marginTop: 8 }}>
            {setupReadiness.remediation}
          </div>
        ) : null}
        <div className="subtle" style={{ marginTop: 8 }}>
          Tenant context: <code>{effectiveTenantId || "unresolved"}</code>
        </div>
      </div>

      <div className="form-grid">
        <label>
          Region
          <input
            value={values.region}
            onChange={(event) => setValues((prev) => ({ ...prev, region: event.target.value }))}
            data-testid="assisted-region-input"
          />
        </label>

        {!values.manualRoleArnEnabled ? (
          <>
            <label>
              AWS Account ID
              <input
                value={values.accountId}
                onChange={(event) => setValues((prev) => ({ ...prev, accountId: event.target.value }))}
                placeholder="123456789012"
                data-testid="assisted-account-id-input"
              />
            </label>
            <label>
              Customer Role Name
              <input
                value={values.roleName}
                onChange={(event) => setValues((prev) => ({ ...prev, roleName: event.target.value }))}
                placeholder="SparkPilotByocLiteRole"
                data-testid="assisted-role-name-input"
              />
            </label>
            <label>
              Resolved Customer Role ARN
              <input value={resolvedRoleArn} readOnly className="input-readonly" data-testid="assisted-role-arn-preview" />
            </label>
          </>
        ) : (
          <label>
            Manual Customer Role ARN
            <input
              value={values.manualRoleArn}
              onChange={(event) => setValues((prev) => ({ ...prev, manualRoleArn: event.target.value }))}
              placeholder="arn:aws:iam::<account-id>:role/<role-name>"
              data-testid="assisted-manual-role-arn-input"
            />
          </label>
        )}
      </div>

      <div className="button-row">
        <button
          type="button"
          className="button button-secondary"
          onClick={() => void runDiscovery()}
          disabled={discoveryLoading}
          data-testid="discover-clusters-button"
        >
          {discoveryLoading ? "Discovering..." : "Discover EKS Clusters"}
        </button>
      </div>

      {discoveryHint ? <div className="success-text">{discoveryHint}</div> : null}
      {discoveryError ? <div className="error-text">{discoveryError}</div> : null}

      <div className="form-grid">
        {!values.manualClusterArnEnabled ? (
          <label>
            Discovered EKS Cluster
            <select
              value={values.selectedClusterArn}
              onChange={(event) => setValues((prev) => ({ ...prev, selectedClusterArn: event.target.value }))}
              data-testid="discovered-cluster-select"
            >
              <option value="">Select a discovered cluster</option>
              {clusters.map((cluster) => (
                <option key={cluster.arn} value={cluster.arn}>
                  {cluster.name} ({cluster.status}{cluster.has_oidc ? ", OIDC" : ", OIDC missing"})
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label>
            Manual EKS Cluster ARN
            <input
              value={values.manualClusterArn}
              onChange={(event) => setValues((prev) => ({ ...prev, manualClusterArn: event.target.value }))}
              placeholder="arn:aws:eks:<region>:<account-id>:cluster/<cluster-name>"
              data-testid="manual-cluster-arn-input"
            />
          </label>
        )}

        <label>
          EKS Namespace
          <input
            value={values.eksNamespace}
            onChange={(event) => setValues((prev) => ({ ...prev, eksNamespace: event.target.value }))}
            data-testid="assisted-namespace-input"
          />
          {discoveredNamespaceHint ? (
            <span className="subtle">Suggested by discovery: <code>{discoveredNamespaceHint}</code></span>
          ) : null}
        </label>
      </div>

      <details className="card" style={{ marginTop: 12 }}>
        <summary className="card-summary">
          <strong>Advanced options</strong>
          <span className="subtle">Manual overrides and runtime tuning</span>
        </summary>
        <div className="form-grid" style={{ marginTop: 12 }}>
          <label>
            Tenant ID Override
            <input
              value={values.tenantIdOverride}
              onChange={(event) => setValues((prev) => ({ ...prev, tenantIdOverride: event.target.value }))}
              placeholder="Optional override if identity has no tenant"
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={values.manualRoleArnEnabled}
              onChange={(event) => {
                setDiscoveryError("");
                setValues((prev) => ({
                  ...prev,
                  manualRoleArnEnabled: event.target.checked,
                  manualRoleArn: event.target.checked ? prev.manualRoleArn : "",
                }));
              }}
            />
            Manual role ARN override
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={values.manualClusterArnEnabled}
              onChange={(event) => {
                setDiscoveryError("");
                setValues((prev) => ({
                  ...prev,
                  manualClusterArnEnabled: event.target.checked,
                  manualClusterArn: event.target.checked ? prev.manualClusterArn : "",
                }));
              }}
            />
            Manual cluster ARN override
          </label>
          <label>
            Instance Architecture
            <select
              value={values.instanceArchitecture}
              onChange={(event) =>
                setValues((prev) => ({
                  ...prev,
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
            Max Concurrent Runs
            <input
              type="number"
              min={1}
              value={values.maxConcurrentRuns}
              onChange={(event) => setValues((prev) => ({ ...prev, maxConcurrentRuns: event.target.value }))}
            />
          </label>
          <label>
            Max vCPU
            <input
              type="number"
              min={1}
              value={values.maxVcpu}
              onChange={(event) => setValues((prev) => ({ ...prev, maxVcpu: event.target.value }))}
            />
          </label>
          <label>
            Max Run Seconds
            <input
              type="number"
              min={60}
              value={values.maxRunSeconds}
              onChange={(event) => setValues((prev) => ({ ...prev, maxRunSeconds: event.target.value }))}
            />
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={values.warmPoolEnabled}
              onChange={(event) => setValues((prev) => ({ ...prev, warmPoolEnabled: event.target.checked }))}
            />
            Warm pool enabled
          </label>
        </div>
      </details>

      <div className="button-row">
        <button
          type="button"
          className="button"
          disabled={submitting || setupReadiness.status !== "ready"}
          onClick={() => void submit()}
          data-testid="create-environment-button"
        >
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
