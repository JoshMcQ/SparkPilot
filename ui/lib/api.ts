const API_BASE = process.env.NEXT_PUBLIC_SPARKPILOT_API ?? "http://localhost:8000";

export type Environment = {
  id: string;
  tenant_id: string;
  region: string;
  status: string;
  engine: string;
  provisioning_mode: string;
  eks_namespace: string | null;
  warm_pool_enabled: boolean;
  max_concurrent_runs: number;
  max_vcpu: number;
  created_at: string;
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
  const response = await fetch(`${API_BASE}/v1/environments`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchRuns(): Promise<Run[]> {
  const response = await fetch(`${API_BASE}/v1/runs`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Run fetch failed: ${response.status}`);
  }
  return response.json();
}

export type RunLogsResponse = {
  run_id: string;
  log_group: string | null;
  log_stream_prefix: string | null;
  lines: string[];
};

export async function fetchRunLogs(runId: string): Promise<RunLogsResponse> {
  const response = await fetch(`${API_BASE}/v1/runs/${runId}/logs`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Run logs fetch failed: ${response.status}`);
  }
  return (await response.json()) as RunLogsResponse;
}
