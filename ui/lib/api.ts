const API_PREFIX = "/api/sparkpilot";
export const USER_ACCESS_TOKEN_STORAGE_KEY = "sparkpilot.userAccessToken";
export const USER_ACCESS_TOKEN_CHANGED_EVENT = "sparkpilot:user-access-token-changed";
/**
 * Fired when the API returns a 401 with X-SparkPilot-Auth-Hint: key-rotation,
 * indicating that signing keys changed and the user must re-authenticate (#84).
 */
export const AUTH_KEY_ROTATION_EVENT = "sparkpilot:auth-key-rotation";

/**
 * In-memory token reference for the current session.
 * Kept in sync with the HttpOnly cookie via the /api/auth/session endpoint.
 * This is NOT persisted in localStorage in production — only in memory for
 * inclusion in the Authorization header during the current page lifecycle.
 * The server-side proxy also reads the HttpOnly cookie as a fallback (#58).
 */
let _inMemoryToken: string = "";

function _userAccessToken(): string {
  if (typeof window === "undefined") {
    return "";
  }
  // In-memory token takes priority (set by storeUserAccessToken or page init)
  if (_inMemoryToken) {
    return _inMemoryToken;
  }
  // Backward compatibility: check localStorage for dev/migration flows
  return window.localStorage.getItem(USER_ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? "";
}

/**
 * Return the current in-memory token value (display-only, not for auth).
 * After a page refresh the in-memory token is empty until the next login/paste.
 */
export function getInMemoryToken(): string {
  return _inMemoryToken;
}

/**
 * Async check whether an HttpOnly session cookie exists on the server.
 * Does NOT expose the token value.
 */
export async function isSessionActive(): Promise<boolean> {
  try {
    const res = await fetch("/api/auth/session", { method: "GET" });
    if (!res.ok) return false;
    const body = await res.json();
    return Boolean(body?.authenticated);
  } catch {
    return false;
  }
}

export function storeUserAccessToken(token: string): void {
  if (typeof window === "undefined") {
    return;
  }
  const value = token.trim();
  _inMemoryToken = value;

  // Store in HttpOnly cookie via session API (#58)
  if (value) {
    fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: value }),
    }).catch(() => {
      // Silent fallback — cookie will be missing, header auth still works
    });
  } else {
    fetch("/api/auth/session", { method: "DELETE" }).catch(() => {});
  }

  // Keep localStorage for backward compat in dev mode only
  if (process.env.NODE_ENV === "development") {
    if (value) {
      window.localStorage.setItem(USER_ACCESS_TOKEN_STORAGE_KEY, value);
    } else {
      window.localStorage.removeItem(USER_ACCESS_TOKEN_STORAGE_KEY);
    }
  } else {
    // Production: remove any legacy localStorage token (#58)
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

export async function fetchProvisioningOperation(operationId: string): Promise<ProvisioningOperation> {
  const response = await fetch(`${API_PREFIX}/v1/provisioning-operations/${operationId}`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load provisioning operation"));
  }
  const payload = await response.json();
  return _asObject(payload, "Provisioning operation fetch") as ProvisioningOperation;
}

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
  last_heartbeat_at?: string | null;
  ended_at: string | null;
  created_at?: string;
  updated_at?: string;
  log_group: string | null;
  log_stream_prefix: string | null;
  error_message: string | null;
  spark_ui_uri?: string | null;
};

async function _extractDetail(response: Response, fallback: string): Promise<string> {
  // Detect key-rotation signature failures (#84)
  if (response.status === 401) {
    const authHint = response.headers.get("X-SparkPilot-Auth-Hint");
    if (authHint === "key-rotation" && typeof window !== "undefined") {
      window.dispatchEvent(new Event(AUTH_KEY_ROTATION_EVENT));
    }
  }
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

/**
 * Authenticated user context from GET /v1/auth/me (#75).
 */
export type AuthMe = {
  actor: string;
  role: "admin" | "operator" | "user";
  tenant_id: string | null;
  team_id: string | null;
  scoped_environment_ids: string[];
};

/**
 * Fetch the authenticated user's identity context.
 * Returns null if not authenticated or identity not yet provisioned.
 */
export async function fetchAuthMe(): Promise<AuthMe | null> {
  try {
    const response = await fetch(`${API_PREFIX}/v1/auth/me`, {
      cache: "no-store",
      headers: _headers(false),
    });
    if (!response.ok) return null;
    const body = await response.json();
    return body as AuthMe;
  } catch {
    return null;
  }
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

export async function retryEnvironmentProvisioning(environmentId: string): Promise<ProvisioningOperation> {
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}/retry`, {
    method: "POST",
    headers: _headers(true),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Environment retry failed"));
  }
  const body = await response.json();
  return _asObject(body, "Environment retry") as ProvisioningOperation;
}

export async function deleteEnvironment(environmentId: string): Promise<Environment> {
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}`, {
    method: "DELETE",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Environment delete failed"));
  }
  const payload = await response.json();
  return _asObject(payload, "Environment delete") as Environment;
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

export type QueueUtilizationResponse = {
  environment_id: string;
  yunikorn_queue: string | null;
  active_run_count: number;
  used_vcpu: number;
  guaranteed_vcpu: number | null;
  max_vcpu: number | null;
  utilization_pct: number | null;
};

export async function fetchQueueUtilization(environmentId: string): Promise<QueueUtilizationResponse> {
  const response = await fetch(`${API_PREFIX}/v1/environments/${environmentId}/queue-utilization`, {
    cache: "no-store",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load queue utilization"));
  }
  const payload = await response.json();
  return _asObject(payload, "Queue utilization fetch") as QueueUtilizationResponse;
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
// Policy Engine (#39)
// ---------------------------------------------------------------------------

export type PolicyScope = "global" | "tenant" | "environment";
export type PolicyEnforcement = "hard" | "soft";
export type PolicyRuleType =
  | "max_runtime_seconds"
  | "max_vcpu"
  | "max_memory_gb"
  | "required_tags"
  | "allowed_golden_paths"
  | "allowed_release_labels"
  | "allowed_instance_types"
  | "allowed_security_configurations";

export type Policy = {
  id: string;
  name: string;
  scope: PolicyScope;
  scope_id: string | null;
  rule_type: PolicyRuleType;
  config: Record<string, unknown>;
  enforcement: PolicyEnforcement;
  active: boolean;
  created_by_actor: string | null;
  created_at: string;
  updated_at: string;
};

export type PolicyCreateRequest = {
  name: string;
  scope?: PolicyScope;
  scope_id?: string | null;
  rule_type: PolicyRuleType;
  config: Record<string, unknown>;
  enforcement?: PolicyEnforcement;
  active?: boolean;
};

export async function fetchPolicies(params?: {
  scope?: PolicyScope;
  scope_id?: string;
  active_only?: boolean;
  limit?: number;
}): Promise<Policy[]> {
  const qs = new URLSearchParams();
  if (params?.scope) qs.set("scope", params.scope);
  if (params?.scope_id) qs.set("scope_id", params.scope_id);
  if (params?.active_only !== undefined) qs.set("active_only", String(params.active_only));
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  const url = `${API_PREFIX}/v1/policies${qs.size ? `?${qs}` : ""}`;
  const response = await fetch(url, { cache: "no-store", headers: _headers(false) });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load policies"));
  }
  return _asObjectArray(await response.json(), "Policies fetch") as Policy[];
}

export async function createPolicy(req: PolicyCreateRequest): Promise<Policy> {
  const response = await fetch(`${API_PREFIX}/v1/policies`, {
    method: "POST",
    headers: _headers(true),
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to create policy"));
  }
  return _asObject(await response.json(), "Policy create") as Policy;
}

export async function deletePolicy(policyId: string): Promise<void> {
  const response = await fetch(`${API_PREFIX}/v1/policies/${policyId}`, {
    method: "DELETE",
    headers: _headers(false),
  });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to delete policy"));
  }
}

// ---------------------------------------------------------------------------
// EMR Release Lifecycle (#40)
// ---------------------------------------------------------------------------

export type EmrReleaseLifecycleStatus = "current" | "deprecated" | "end_of_life";

export type EmrRelease = {
  id: string;
  release_label: string;
  lifecycle_status: EmrReleaseLifecycleStatus;
  graviton_supported: boolean;
  lake_formation_supported: boolean;
  upgrade_target: string | null;
  source: string;
  last_synced_at: string;
  created_at: string;
  updated_at: string;
};

export async function fetchEmrReleases(params?: { limit?: number }): Promise<EmrRelease[]> {
  const qs = new URLSearchParams();
  if (params?.limit !== undefined) qs.set("limit", String(params.limit));
  const url = `${API_PREFIX}/v1/emr-releases${qs.size ? `?${qs}` : ""}`;
  const response = await fetch(url, { cache: "no-store", headers: _headers(false) });
  if (!response.ok) {
    throw new Error(await _extractDetail(response, "Failed to load EMR releases"));
  }
  return _asObjectArray(await response.json(), "EMR releases fetch") as EmrRelease[];
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
