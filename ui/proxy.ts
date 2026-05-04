import { NextRequest, NextResponse } from "next/server";

const SESSION_COOKIE = "sparkpilot.session";

function isAuthEnforced(): boolean {
  const raw = (process.env.SPARKPILOT_UI_ENFORCE_AUTH ?? "").trim().toLowerCase();
  if (raw === "true") return true;
  if (raw === "false") return false;
  return true;
}

function isManualTokenModeEnabled(): boolean {
  const manualMode = (process.env.NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE ?? "").trim().toLowerCase() === "true";
  return manualMode && process.env.NODE_ENV !== "production";
}

function loginRedirect(request: NextRequest, pool: "customer" | "internal"): NextResponse {
  const loginUrl = new URL("/login", request.url);
  const target = `${request.nextUrl.pathname}${request.nextUrl.search}`;
  loginUrl.searchParams.set("next", target);
  if (pool === "internal") {
    loginUrl.searchParams.set("pool", "internal");
  }
  return NextResponse.redirect(loginUrl);
}

export function proxy(request: NextRequest): NextResponse {
  if (!isAuthEnforced() || isManualTokenModeEnabled()) {
    return NextResponse.next();
  }

  const session = request.cookies.get(SESSION_COOKIE)?.value?.trim();
  if (session) {
    return NextResponse.next();
  }

  const pool = request.nextUrl.pathname.startsWith("/internal") ? "internal" : "customer";
  return loginRedirect(request, pool);
}

export const config = {
  matcher: [
    "/dashboard/:path*",
    "/onboarding/:path*",
    "/environments/:path*",
    "/runs/:path*",
    "/integrations/:path*",
    "/costs/:path*",
    "/policies/:path*",
    "/internal/:path*",
    "/access/:path*",
    "/settings/:path*",
  ],
};
