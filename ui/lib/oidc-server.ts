import "server-only";
import { cookies } from "next/headers";
export { sparkpilotApiBase } from "@/lib/api-base";

export class ProxyAuthError extends Error {
  readonly statusCode: number;

  constructor(message: string, statusCode: number) {
    super(message);
    this.statusCode = statusCode;
  }
}

const SESSION_COOKIE_NAME = "sparkpilot.session";

/**
 * Resolve the Authorization header to forward to the SparkPilot API.
 *
 * Policy (in priority order):
 *   1. If the incoming request carries `Authorization: Bearer <token>`, pass it through directly.
 *   2. If there is an HttpOnly session cookie (sparkpilot.session), use that as the bearer token.
 *   3. If neither is present, throw a ProxyAuthError (→ HTTP 401).
 *
 * The session cookie approach (#58) ensures tokens are not readable from browser JS.
 */
export async function resolveProxyAuthorization(incomingAuthorization: string | null): Promise<string> {
  const incoming = (incomingAuthorization ?? "").trim();

  // Priority 1: explicit Authorization header
  if (incoming) {
    if (!incoming.toLowerCase().startsWith("bearer ")) {
      throw new ProxyAuthError("Authorization header must use Bearer token format.", 401);
    }
    return incoming;
  }

  // Priority 2: HttpOnly session cookie
  const cookieStore = await cookies();
  const sessionCookie = cookieStore.get(SESSION_COOKIE_NAME)?.value ?? "";
  if (sessionCookie.trim()) {
    return `Bearer ${sessionCookie.trim()}`;
  }

  throw new ProxyAuthError(
    "No active user session. Sign in to authenticate.",
    401,
  );
}
