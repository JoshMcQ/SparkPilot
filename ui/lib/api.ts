const API_PREFIX = "/api/sparkpilot";
export const USER_ACCESS_TOKEN_STORAGE_KEY = "sparkpilot.userAccessToken";
export const USER_ACCESS_TOKEN_CHANGED_EVENT = "sparkpilot:user-access-token-changed";

function _userAccessToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.localStorage.getItem(USER_ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? "";
}

export function storeUserAccessToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const value = token.trim();
  if (value) {
    window.localStorage.setItem(USER_ACCESS_TOKEN_STORAGE_KEY, value);
  } else {
    window.localStorage.removeItem(USER_ACCESS_TOKEN_STORAGE_KEY);
  }
  window.dispatchEvent(new Event(USER_ACCESS_TOKEN_CHANGED_EVENT));
}

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
  const userToken = _userAccessToken();
  if (userToken) {
    headers["Authorization"] = userToken.toLowerCase().startsWith("bearer ")
      ? userToken
      : `Bearer ${userToken}`;
  }
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
  instance_architecture?: "x86_64" | "arm64" | "mixed";
  customer_role_arn: string;
  eks_cluster_arn: string | null;
  eks_namespace: string | null;
  emr_virtual_cluster_id: string | null;
  warm_pool_enabled: boolean;
  max_concurrent_runs: number;
  max_vcpu: number;
  max_run_seconds: number;
  created_at: string;
  updated_at?: string;
};

export type EnvironmentCreateRequest = {
  tenant_id: string;
  provisioning_mode: "full" | "byoc_lite";
  region: string;
  instance_architecture?: "x86_64" | "arm64" | "mixed";
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
   cancellation_requested: boolean;
  emr_job_run_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  log_group: string | null;
  log_stream_prefix: string | null;
  error_message: string | null;
};

async function _extractDetail(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body?.detail === "string" && body.detail.trim()) return body.detail;
  } catch { /* ignore parse failure */ }
  if (response.status === 500) return `${fallback}. Internal server error — check API logs.`;
  if (response.status === 502 || response.status === 503) return `${fallback}. API is unreachable — verify the backend is running.`;
  if (response.status === 401) return `${fallback}. Authentication failed — check OIDC credentials.`;
  if (response.status === 403) return `${fallback}. Access denied — verify your role and team scope.`;
  if (response.status === 404) return `${fallback}. Resource not found.`;
  if (response.status === 409) return `${fallback}. Conflicting resource already exists.`;
  if (response.status === 422) return `${fallback}. Validation failed — check input fields.`;
  return `${fallback} (HTTP ${response.status}).`;
}

export async function fetchEnvironments(): Promise<Environment[]> {
  const response = await fetch(`${API_PREFIX}/v1/environments`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load environments"));
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
    throw new Error(await _extractDetail(response, "Environment creation failed"));
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
    throw new Error(await _extractDetail(response, "Job creation failed"));
  }
  const body = await response.json();
  return _asObject(body, "Job create") as Job;
}

export async function fetchJobs(environmentId?: string): Promise<Job[]> {
  const params = new URLSearchParams();
  if (environmentId) {
    params.set("environment_id", environmentId);
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const response = await fetch(`${API_PREFIX}/v1/jobs${suffix}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load jobs"));
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Job fetch") as Job[];
}

export async function fetchEnvironment(environmentId: string): Promise<Environment> {
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load environment"));
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
    throw new Error(await _extractDetail(response, "Failed to load runs"));
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

export async function fetchRunLogs(runId: string, options?: { limit?: number }): Promise<RunLogsResponse> {
  const params = new URLSearchParams();
  if (options?.limit != null) {
    params.set("limit", String(options.limit));
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const response = await fetch(`${API_PREFIX}/v1/runs/${runId}/logs${suffix}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load run logs"));
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
    throw new Error(await _extractDetail(response, "Preflight check failed"));
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
    throw new Error(await _extractDetail(response, "Run submission failed"));
  }
  const body = await response.json();
  return _asObject(body, "Run submit") as Run;
}

export async function cancelRun(runId: string): Promise<Run> {
  const response = await fetch(`${API_PREFIX}/v1/runs/${runId}/cancel`, {
    method: "POST",
    headers: _headers(true),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Run cancellation failed"));
  }
  const body = await response.json();
  return _asObject(body, "Run cancel") as Run;
}

export type UsageItem = {
  run_id: string;
  vcpu_seconds: number;
  memory_gb_seconds: number;
  estimated_cost_usd_micros: number;
  recorded_at: string;
};

export type UsageResponse = {
  tenant_id: string;
  from_ts: string;
  to_ts: string;
  items: UsageItem[];
};

export async function fetchUsage(tenantId: string): Promise<UsageResponse> {
  const params = new URLSearchParams({ tenant_id: tenantId });
  const response = await fetch(`${API_PREFIX}/v1/usage?${params.toString()}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load usage data"));
  }
  const payload = await response.json();
  return _asObject(payload, "Usage fetch") as UsageResponse;
}

export type CostShowbackItem = {
  run_id: string;
  environment_id: string;
  team: string;
  cost_center: string;
  estimated_cost_usd_micros: number;
  actual_cost_usd_micros: number | null;
  effective_cost_usd_micros: number;
  billing_period: string;
  cur_reconciled_at: string | null;
};

export type CostShowbackResponse = {
  team: string;
  period: string;
  total_estimated_cost_usd_micros: number;
  total_actual_cost_usd_micros: number;
  total_effective_cost_usd_micros: number;
  items: CostShowbackItem[];
};

export async function fetchCostShowback(team: string, period: string): Promise<CostShowbackResponse> {
  const params = new URLSearchParams({ team, period });
  const response = await fetch(`${API_PREFIX}/v1/costs?${params.toString()}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load cost data"));
  }
  const payload = await response.json();
  return _asObject(payload, "Cost showback fetch") as CostShowbackResponse;
}

// ---------------------------------------------------------------------------
// RBAC: User Identities
// ---------------------------------------------------------------------------

export type UserIdentity = {
  id: string;
  actor: string;
  role: "admin" | "operator" | "user";
  tenant_id: string | null;
  team_id: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type UserIdentityCreateRequest = {
  actor: string;
  role: "admin" | "operator" | "user";
  tenant_id?: string | null;
  team_id?: string | null;
  active?: boolean;
};

export async function fetchUserIdentities(): Promise<UserIdentity[]> {
  const response = await fetch(`${API_PREFIX}/v1/user-identities`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load user identities"));
  }
  const payload = await response.json();
  return _asObjectArray(payload, "User identities fetch") as UserIdentity[];
}

export async function createUserIdentity(req: UserIdentityCreateRequest): Promise<UserIdentity> {
  const response = await fetch(`${API_PREFIX}/v1/user-identities`, {
    method: "POST",
    headers: _headers(false),
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "User identity creation failed"));
  }
  const body = await response.json();
  return _asObject(body, "User identity create") as UserIdentity;
}

// ---------------------------------------------------------------------------
// RBAC: Teams
// ---------------------------------------------------------------------------

export type Team = {
  id: string;
  tenant_id: string;
  name: string;
  created_at: string;
  updated_at: string;
};

export type TeamCreateRequest = {
  tenant_id: string;
  name: string;
};

export async function fetchTeams(tenantId?: string): Promise<Team[]> {
  const params = new URLSearchParams();
  if (tenantId) params.set("tenant_id", tenantId);
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const response = await fetch(`${API_PREFIX}/v1/teams${suffix}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load teams"));
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Teams fetch") as Team[];
}

export async function createTeam(req: TeamCreateRequest): Promise<Team> {
  const response = await fetch(`${API_PREFIX}/v1/teams`, {
    method: "POST",
    headers: _headers(false),
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Team creation failed"));
  }
  const body = await response.json();
  return _asObject(body, "Team create") as Team;
}

// ---------------------------------------------------------------------------
// RBAC: Team-Environment Scopes
// ---------------------------------------------------------------------------

export type TeamEnvironmentScope = {
  id: string;
  team_id: string;
  environment_id: string;
  created_at: string;
};

export async function fetchTeamEnvironmentScopes(teamId: string): Promise<TeamEnvironmentScope[]> {
  const response = await fetch(`${API_PREFIX}/v1/teams/${teamId}/environments`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load team-environment scopes"));
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Team-env scopes fetch") as TeamEnvironmentScope[];
}

export async function createTeamEnvironmentScope(teamId: string, environmentId: string): Promise<TeamEnvironmentScope> {
  const response = await fetch(`${API_PREFIX}/v1/teams/${teamId}/environments/${environmentId}`, {
    method: "POST",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Scope assignment failed"));
  }
  const body = await response.json();
  return _asObject(body, "Scope create") as TeamEnvironmentScope;
}

export async function deleteTeamEnvironmentScope(teamId: string, environmentId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/v1/teams/${teamId}/environments/${environmentId}`, {
    method: "DELETE",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Scope removal failed"));
  }
}

// ---------------------------------------------------------------------------
// RBAC: Team Budgets
// ---------------------------------------------------------------------------

export type TeamBudget = {
  id: string;
  team: string;
  monthly_budget_usd_micros: number;
  warn_threshold_pct: number;
  block_threshold_pct: number;
  created_at: string;
  updated_at: string;
};

export type TeamBudgetCreateRequest = {
  team: string;
  monthly_budget_usd_micros: number;
  warn_threshold_pct: number;
  block_threshold_pct: number;
};

export async function fetchTeamBudget(team: string): Promise<TeamBudget> {
  const response = await fetch(`${API_PREFIX}/v1/team-budgets/${encodeURIComponent(team)}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load team budget"));
  }
  const body = await response.json();
  return _asObject(body, "Team budget fetch") as TeamBudget;
}

export async function createOrUpdateTeamBudget(req: TeamBudgetCreateRequest): Promise<TeamBudget> {
  const response = await fetch(`${API_PREFIX}/v1/team-budgets`, {
    method: "POST",
    headers: _headers(false),
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Budget creation/update failed"));
  }
  const body = await response.json();
  return _asObject(body, "Team budget create") as TeamBudget;
}

// ---------------------------------------------------------------------------
// Run Diagnostics
// ---------------------------------------------------------------------------

export type DiagnosticItem = {
  id: string;
  run_id: string;
  category: string;
  description: string;
  remediation: string;
  log_snippet: string | null;
  created_at: string;
};

export type DiagnosticsResponse = {
  run_id: string;
  items: DiagnosticItem[];
};

export async function fetchRunDiagnostics(runId: string): Promise<DiagnosticsResponse> {
  const response = await fetch(`${API_PREFIX}/v1/runs/${runId}/diagnostics`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load run diagnostics"));
  }
  const body = await response.json();
  return _asObject(body, "Run diagnostics fetch") as DiagnosticsResponse;
}
