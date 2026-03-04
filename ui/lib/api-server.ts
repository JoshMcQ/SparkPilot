import "server-only";

import type { Environment, PreflightResponse, Run } from "@/lib/api";

const API_BASE = process.env.SPARKPILOT_API ?? "http://localhost:8000";
const OIDC_ISSUER = process.env.OIDC_ISSUER ?? process.env.SPARKPILOT_OIDC_ISSUER ?? "";
const OIDC_AUDIENCE = process.env.OIDC_AUDIENCE ?? process.env.SPARKPILOT_OIDC_AUDIENCE ?? "";
const OIDC_CLIENT_ID = process.env.OIDC_CLIENT_ID ?? process.env.SPARKPILOT_OIDC_CLIENT_ID ?? "";
const OIDC_CLIENT_SECRET = process.env.OIDC_CLIENT_SECRET ?? process.env.SPARKPILOT_OIDC_CLIENT_SECRET ?? "";
const OIDC_TOKEN_ENDPOINT = process.env.OIDC_TOKEN_ENDPOINT ?? process.env.SPARKPILOT_OIDC_TOKEN_ENDPOINT ?? "";
const OIDC_SCOPE = process.env.OIDC_SCOPE ?? process.env.SPARKPILOT_OIDC_SCOPE ?? "";

type OIDCTokenCache = {
  token: string;
  expiresAtEpochMs: number;
};

let _cachedOidcToken: OIDCTokenCache | null = null;

function _requireOidcConfig(): void {
  if (!OIDC_ISSUER || !OIDC_AUDIENCE || !OIDC_CLIENT_ID || !OIDC_CLIENT_SECRET) {
    throw new Error(
      "Missing required OIDC server auth env vars. " +
      "Set OIDC_ISSUER, OIDC_AUDIENCE, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET."
    );
  }
}

async function _discoverTokenEndpoint(issuer: string): Promise<string> {
  const normalizedIssuer = issuer.replace(/\/+$/, "");
  const response = await fetch(`${normalizedIssuer}/.well-known/openid-configuration`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`OIDC discovery failed with status ${response.status}.`);
  }
  const payload = await response.json();
  const endpoint = typeof payload?.token_endpoint === "string" ? payload.token_endpoint.trim() : "";
  if (!endpoint) {
    throw new Error("OIDC discovery response missing token_endpoint.");
  }
  return endpoint;
}

async function _oidcAccessToken(): Promise<string> {
  _requireOidcConfig();
  const now = Date.now();
  if (_cachedOidcToken && _cachedOidcToken.expiresAtEpochMs > now + 30_000) {
    return _cachedOidcToken.token;
  }

  const tokenEndpoint = OIDC_TOKEN_ENDPOINT || await _discoverTokenEndpoint(OIDC_ISSUER);
  const body = new URLSearchParams();
  body.set("grant_type", "client_credentials");
  body.set("audience", OIDC_AUDIENCE);
  if (OIDC_SCOPE.trim()) {
    body.set("scope", OIDC_SCOPE.trim());
  }
  const basicAuth = Buffer.from(`${OIDC_CLIENT_ID}:${OIDC_CLIENT_SECRET}`).toString("base64");
  const response = await fetch(tokenEndpoint, {
    method: "POST",
    headers: {
      "Accept": "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
      "Authorization": `Basic ${basicAuth}`,
    },
    body: body.toString(),
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`OIDC token request failed with status ${response.status}.`);
  }
  const payload = await response.json();
  const accessToken = typeof payload?.access_token === "string" ? payload.access_token.trim() : "";
  if (!accessToken) {
    throw new Error("OIDC token response missing access_token.");
  }
  const expiresInRaw = Number(payload?.expires_in ?? 300);
  const expiresInMs = Number.isFinite(expiresInRaw) ? Math.max(30, Math.floor(expiresInRaw)) * 1000 : 300_000;
  _cachedOidcToken = {
    token: accessToken,
    expiresAtEpochMs: now + expiresInMs,
  };
  return accessToken;
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

async function _request(path: string): Promise<Response> {
  const accessToken = await _oidcAccessToken();
  return fetch(`${API_BASE}${path}`, {
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${accessToken}`,
    },
  });
}

export async function fetchEnvironmentsServer(): Promise<Environment[]> {
  const response = await _request("/v1/environments");
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Environment fetch") as Environment[];
}

export async function fetchEnvironmentServer(environmentId: string): Promise<Environment> {
  const response = await _request(`/v1/environments/${environmentId}`);
  if (!response.ok) {
    throw new Error(`Environment fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObject(payload, "Environment fetch") as Environment;
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
  const response = await _request(`/v1/environments/${environmentId}/preflight${suffix}`);
  if (!response.ok) {
    throw new Error(`Environment preflight failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObject(payload, "Environment preflight") as PreflightResponse;
}

export async function fetchRunsServer(): Promise<Run[]> {
  const response = await _request("/v1/runs");
  if (!response.ok) {
    throw new Error(`Run fetch failed: ${response.status}`);
  }
  const payload = await response.json();
  return _asObjectArray(payload, "Run fetch") as Run[];
}
