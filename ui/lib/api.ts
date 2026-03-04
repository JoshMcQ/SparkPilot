const API_PREFIX = "/api/sparkpilot";

function _idempotencyKey(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return globalThis.crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random()}`;
}

function _headers(idempotent: boolean): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (idempotent) {
    headers["Idempotency-Key"] = _idempotencyKey();
  }
  return headers;
}

function _asObject(value: unknown, context: string): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new Error(`${context} returned invalid JSON object payload.`);
}

function _asObjectArray(value: unknown, context: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} returned invalid JSON array payload.`);
  }
  const rows: Record<string, unknown>[] = [];
  for (const item of value) {
    rows.push(_asObject(item, context));
  }
  return rows;
}

export type Environment = {
  id: string;
  tenant_id: string;
  cloud: string;
  region: string;
  engine: string;
  status: string;
  provisioning_mode: string;
  customer_role_arn: string;
  eks_cluster_arn: string | null;
  eks_namespace: string | null;
  emr_virtual_cluster_id: string | null;
  warm_pool_enabled: boolean;
  max_concurrent_runs: number;
  max_vcpu: number;
  max_run_seconds: number;
  created_at: string;
};

export type EnvironmentCreateRequest = {
  tenant_id: string;
  provisioning_mode: "full" | "byoc_lite";
  region: string;
  customer_role_arn: string;
  eks_cluster_arn?: string;
  eks_namespace?: string;
  warm_pool_enabled: boolean;
  quotas: {
    max_concurrent_runs: number;
    max_vcpu: number;
    max_run_seconds: number;
  };
};

export type ProvisioningOperation = {
  id: string;
  environment_id: string;
  state: string;
  step: string;
  started_at: string;
  ended_at: string | null;
  message: string | null;
  logs_uri: string | null;
  created_at: string;
  updated_at: string;
};

export type JobCreateRequest = {
  environment_id: string;
  name: string;
  artifact_uri: string;
  artifact_digest: string;
  entrypoint: string;
  args: string[];
  spark_conf: Record<string, string>;
  retry_max_attempts: number;
  timeout_seconds: number;
};

export type Job = {
  id: string;
  environment_id: string;
  name: string;
  artifact_uri: string;
  artifact_digest: string;
  entrypoint: string;
  args: string[];
  spark_conf: Record<string, string>;
  retry_max_attempts: number;
  timeout_seconds: number;
  created_at: string;
  updated_at: string;
};

export type Run = {
  id: string;
  job_id: string;
  environment_id: string;
  state: string;
  emr_job_run_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  log_group: string | null;
  log_stream_prefix: string | null;
  error_message: string | null;
};

export async function fetchEnvironments(): Promise<Environment[]> {
  const response = await fetch(`${API_PREFIX}/v1/environments`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Environment fetch") as Environment[];
}

export async function createEnvironment(payload: EnvironmentCreateRequest): Promise<ProvisioningOperation> {
  const response = await fetch(`${API_PREFIX}/v1/environments`, {
    method: "POST",
    headers: _headers(true),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    const detail = data?.detail ?? "unknown error";
    throw new Error(`Environment create failed (${response.status}): ${detail}`);
  }
  const body = await response.json();
  return _asObject(body, "Environment create") as ProvisioningOperation;
}

export async function createJob(payload: JobCreateRequest): Promise<Job> {
  const response = await fetch(`${API_PREFIX}/v1/jobs`, {
    method: "POST",
    headers: _headers(true),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const data = (await response.json().catch(() => null)) as { detail?: string } | null;
    const detail = data?.detail ?? "unknown error";
    throw new Error(`Job create failed (${response.status}): ${detail}`);
  }
  const body = await response.json();
  return _asObject(body, "Job create") as Job;
}

export async function fetchEnvironment(environmentId: string): Promise<Environment> {
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObject(payload, "Environment fetch") as Environment;
}

export async function fetchRuns(): Promise<Run[]> {
  const response = await fetch(`${API_PREFIX}/v1/runs`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(`Run fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Run fetch") as Run[];
}

export type RunLogsResponse = {
  run_id: string;
  log_group: string | null;
  log_stream_prefix: string | null;
  lines: string[];
};

export async function fetchRunLogs(runId: string): Promise<RunLogsResponse> {
  const response = await fetch(`${API_PREFIX}/v1/runs/${runId}/logs`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(`Run logs fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObject(payload, "Run logs fetch") as RunLogsResponse;
}

export type PreflightCheck = {
  code: string;
  status: "pass" | "warning" | "fail";
  message: string;
  remediation: string | null;
  details: Record<string, string | number | boolean>;
};

export type PreflightResponse = {
  environment_id: string;
  run_id: string | null;
  ready: boolean;
  generated_at: string;
  checks: PreflightCheck[];
};

export async function fetchEnvironmentPreflight(
  environmentId: string,
  runId?: string
): Promise<PreflightResponse> {
  const params = new URLSearchParams();
  if (runId) {
    params.set("run_id", runId);
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}/preflight${suffix}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(`Environment preflight failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObject(payload, "Environment preflight") as PreflightResponse;
}

export type RunSubmitRequest = {
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

export async function submitRun(jobId: string, payload: RunSubmitRequest): Promise<Run> {
  const response = await fetch(`${API_PREFIX}/v1/jobs/${jobId}/runs`, {
    method: "POST",
    headers: _headers(true),
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Run submit failed: ${response.status}`);
  }
  const body = await response.json();
  return _asObject(body, "Run submit") as Run;
}
