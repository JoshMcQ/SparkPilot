import "server-only";

export class ProxyAuthError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.statusCode = statusCode;
  }
}

const API_BASE = (process.env.SPARKPILOT_API ?? "").trim();

function requireApiBase(): string {
  if (!API_BASE) {
    throw new Error("Missing SPARKPILOT_API. Set the upstream SparkPilot API base URL.");
  }
  return API_BASE;
}

/**
 * Resolve the Authorization header to forward to the SparkPilot API.
 *
 * Policy:
 *   - If the incoming request carries `Authorization: Bearer <token>`, pass it through directly.
 *   - If there is no bearer token, throw a ProxyAuthError (→ HTTP 401).
 *
 * Service-principal / M2M fallback has been intentionally removed. All API
 * requests must be authenticated with an end-user OIDC token obtained via the
 * auth panel or the OIDC login flow.
 */
export async function resolveProxyAuthorization(incomingAuthorization: string | null): Promise<string> {
  const incoming = (incomingAuthorization ?? "").trim();

  if (!incoming) {
    throw new ProxyAuthError(
      "No user access token. Use the auth panel to set your bearer token.",
      401,
    );
  }

  if (!incoming.toLowerCase().startsWith("bearer ")) {
    throw new ProxyAuthError("Authorization header must use Bearer token format.", 401);
  }

  return incoming;
}

export function sparkpilotApiBase(): string {
  return requireApiBase();
}
