import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.SPARKPILOT_API ?? "http://localhost:8000";
const OIDC_ISSUER = process.env.OIDC_ISSUER ?? process.env.SPARKPILOT_OIDC_ISSUER ?? "";
const OIDC_AUDIENCE = process.env.OIDC_AUDIENCE ?? process.env.SPARKPILOT_OIDC_AUDIENCE ?? "";
const OIDC_CLIENT_ID = process.env.OIDC_CLIENT_ID ?? process.env.SPARKPILOT_OIDC_CLIENT_ID ?? "";
const OIDC_CLIENT_SECRET = process.env.OIDC_CLIENT_SECRET ?? process.env.SPARKPILOT_OIDC_CLIENT_SECRET ?? "";
const OIDC_TOKEN_ENDPOINT = process.env.OIDC_TOKEN_ENDPOINT ?? process.env.SPARKPILOT_OIDC_TOKEN_ENDPOINT ?? "";
const OIDC_SCOPE = process.env.OIDC_SCOPE ?? process.env.SPARKPILOT_OIDC_SCOPE ?? "";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

type OIDCTokenCache = {
  token: string;
  expiresAtEpochMs: number;
};

export const dynamic = "force-dynamic";

let _cachedOidcToken: OIDCTokenCache | null = null;

function _targetUrl(request: NextRequest, pathParts: string[]): string {
  const base = new URL(API_BASE);
  const basePath = base.pathname.replace(/\/+$/, "");
  const suffix = pathParts.join("/");
  base.pathname = `${basePath}/${suffix}`;
  base.search = new URL(request.url).search;
  return base.toString();
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
    expiresAtEpochMs: Date.now() + expiresInMs,
  };
  return accessToken;
}

async function _proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  if (!OIDC_ISSUER || !OIDC_AUDIENCE || !OIDC_CLIENT_ID || !OIDC_CLIENT_SECRET) {
    return NextResponse.json(
      {
        detail: (
          "Server is missing required OIDC proxy auth env vars. " +
          "Set OIDC_ISSUER, OIDC_AUDIENCE, OIDC_CLIENT_ID, OIDC_CLIENT_SECRET."
        ),
      },
      { status: 500 }
    );
  }
  const { path } = await context.params;
  if (!Array.isArray(path) || path.length === 0) {
    return NextResponse.json({ detail: "Missing SparkPilot API path." }, { status: 400 });
  }

  const headers = new Headers();
  const accessToken = await _oidcAccessToken();
  headers.set("Authorization", `Bearer ${accessToken}`);
  headers.set("Accept", "application/json");
  const idempotencyKey = request.headers.get("Idempotency-Key");
  if (idempotencyKey) {
    headers.set("Idempotency-Key", idempotencyKey);
  }
  const contentType = request.headers.get("Content-Type");
  if (contentType) {
    headers.set("Content-Type", contentType);
  }

  const method = request.method.toUpperCase();
  const bodyText = method === "GET" || method === "HEAD" ? "" : await request.text();

  try {
    const response = await fetch(_targetUrl(request, path), {
      method,
      headers,
      body: bodyText ? bodyText : undefined,
      cache: "no-store",
      redirect: "manual",
    });

    const passthroughHeaders = new Headers();
    const responseContentType = response.headers.get("Content-Type");
    if (responseContentType) {
      passthroughHeaders.set("Content-Type", responseContentType);
    }
    const replayHeader = response.headers.get("X-Idempotent-Replay");
    if (replayHeader) {
      passthroughHeaders.set("X-Idempotent-Replay", replayHeader);
    }

    return new NextResponse(response.body, {
      status: response.status,
      headers: passthroughHeaders,
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "SparkPilot proxy request failed.",
      },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return _proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return _proxy(request, context);
}
