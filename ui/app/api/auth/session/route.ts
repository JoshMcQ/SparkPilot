/**
 * API route for HttpOnly cookie-backed token session (#58).
 *
 * POST /api/auth/session – stores access token in HttpOnly; Secure; SameSite cookie.
 * DELETE /api/auth/session – clears the session cookie.
 * GET /api/auth/session – returns session status (no token value exposed).
 *
 * This ensures no bearer token is readable from browser JS storage APIs.
 */
import { NextRequest, NextResponse } from "next/server";

const COOKIE_NAME = "sparkpilot.session";
const IS_PRODUCTION = process.env.NODE_ENV === "production";

/** POST: Store access token in HttpOnly cookie. */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body." }, { status: 400 });
  }

  const accessToken = typeof body?.access_token === "string" ? body.access_token.trim() : "";
  if (!accessToken) {
    return NextResponse.json({ detail: "Missing access_token in request body." }, { status: 400 });
  }

  // Default 8-hour session cookie
  const maxAge = typeof body?.max_age === "number" ? body.max_age : 28800;
  const response = NextResponse.json({ status: "session_created" });
  response.cookies.set(COOKIE_NAME, accessToken, {
    httpOnly: true,
    secure: IS_PRODUCTION,
    sameSite: "strict",
    path: "/",
    maxAge,
  });
  return response;
}

/** DELETE: Clear session cookie. */
export async function DELETE(): Promise<NextResponse> {
  const response = NextResponse.json({ status: "session_cleared" });
  response.cookies.set(COOKIE_NAME, "", {
    httpOnly: true,
    secure: IS_PRODUCTION,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}

/** GET: Return session status (authenticated or not). No token value exposed. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  const sessionToken = request.cookies.get(COOKIE_NAME)?.value ?? "";
  const hasSession = Boolean(sessionToken.trim());
  return NextResponse.json({ authenticated: hasSession });
}
