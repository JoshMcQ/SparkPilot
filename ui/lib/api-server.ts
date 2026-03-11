import "server-only";

import type { Environment, PreflightResponse, Run } from "@/lib/api";
import { sparkpilotApiBase } from "@/lib/oidc-server";

function asObject(value: unknown, context: string): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  throw new Error(`${context} returned invalid JSON object payload.`);
}

function asObjectArray(value: unknown, context: string): Record<string, unknown>[] {
  if (!Array.isArray(value)) {
    throw new Error(`${context} returned invalid JSON array payload.`);
  }
  const rows: Record<string, unknown>[] = [];
  for (const item of value) {
    rows.push(asObject(item, context));
  }
  return rows;
}

/**
 * Server-side direct API request helper.
 *
 * NOTE: Service-principal M2M token fallback has been removed. This helper is
 * used only by server components that run in contexts where a bearer token is
 * obtained through another means (e.g. cookie-based session, forwarded header).
 * For unauthenticated server-side calls, pass the token explicitly via the
 * `authorization` parameter.
 */
async function request(path: string, authorization?: string): Promise<Response> {
  const apiBase = sparkpilotApiBase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authorization) {
    headers["Authorization"] = authorization;
  }
  return fetch(`${apiBase}${path}`, {
    cache: "no-store",
    headers,
  });
}

export async function fetchEnvironmentsServer(): Promise<Environment[]> {
  const response = await request("/v1/environments");
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return asObjectArray(payload, "Environment fetch") as Environment[];
}

export async function fetchEnvironmentServer(environmentId: string): Promise<Environment> {
  const response = await request(`/v1/environments/${environmentId}`);
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return asObject(payload, "Environment fetch") as Environment;
}

export async function fetchEnvironmentPreflightServer(
  environmentId: string,
  runId?: string
): Promise<PreflightResponse> {
  const params = new URLSearchParams();
  if (runId) {
    params.set("run_id", runId);
  }
  const suffix = params.size > 0 ? `?${params.toString()}` : "";
  const response = await request(`/v1/environments/${environmentId}/preflight${suffix}`);
  if (!response.ok) {
    throw new Error(`Environment preflight failed: ${response.status}`);
  }
  const payload = await response.json();
  return asObject(payload, "Environment preflight") as PreflightResponse;
}

export async function fetchRunsServer(): Promise<Run[]> {
  const response = await request("/v1/runs");
  if (!response.ok) {
    throw new Error(`Run fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return asObjectArray(payload, "Run fetch") as Run[];
}
