import { NextRequest, NextResponse } from "next/server";
import { ProxyAuthError, resolveProxyAuthorization, sparkpilotApiBase } from "@/lib/oidc-server";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

export const dynamic = "force-dynamic";

function targetUrl(request: NextRequest, pathParts: string[]): string {
  const apiBase = sparkpilotApiBase();
  const base = new URL(apiBase);
  const basePath = base.pathname.replace(/\/+$/, "");
  const suffix = pathParts.join("/");
  base.pathname = `${basePath}/${suffix}`;
  base.search = new URL(request.url).search;
  return base.toString();
}

async function proxy(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  const { path } = await context.params;
  if (!Array.isArray(path) || path.length === 0) {
    return NextResponse.json({ detail: "Missing SparkPilot API path." }, { status: 400 });
  }

  const headers = new Headers();
  let authorization: string;
  try {
    authorization = await resolveProxyAuthorization(request.headers.get("Authorization"));
  } catch (error) {
    if (error instanceof ProxyAuthError && error.statusCode === 401) {
      return NextResponse.json(
        { detail: "No user access token. Use the auth panel to set your bearer token." },
        { status: 401 }
      );
    }
    const statusCode = error instanceof ProxyAuthError ? error.statusCode : 500;
    return NextResponse.json(
      {
        detail: error instanceof Error ? error.message : "SparkPilot proxy authentication failed.",
      },
      { status: statusCode }
    );
  }
  headers.set("Authorization", authorization);
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
    const response = await fetch(targetUrl(request, path), {
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
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext): Promise<NextResponse> {
  return proxy(request, context);
}
