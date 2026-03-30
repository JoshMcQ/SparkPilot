/**
 * Client-side OIDC authorization-code + PKCE flow.
 *
 * Environment variables (all NEXT_PUBLIC_ so they're available in the browser):
 *   NEXT_PUBLIC_OIDC_ISSUER       – e.g. https://auth.example.com
 *   NEXT_PUBLIC_OIDC_CLIENT_ID    – public client ID (no secret needed with PKCE)
 *   NEXT_PUBLIC_OIDC_REDIRECT_URI – e.g. https://app.example.com/auth/callback
 *   NEXT_PUBLIC_OIDC_AUDIENCE     – API audience (optional, IdP-specific)
 */

import { storeUserAccessToken } from "@/lib/api";
import { isOidcClientConfigured } from "@/lib/auth-config";

const ISSUER = (process.env.NEXT_PUBLIC_OIDC_ISSUER ?? "").trim();
const CLIENT_ID = (process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "").trim();
const REDIRECT_URI = (process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI ?? "").trim();
const AUDIENCE = (process.env.NEXT_PUBLIC_OIDC_AUDIENCE ?? "").trim();

const PKCE_VERIFIER_KEY = "sparkpilot.oidc.code_verifier";
const PKCE_STATE_KEY = "sparkpilot.oidc.state";
const POST_LOGIN_REDIRECT_KEY = "sparkpilot.oidc.post_login_redirect";

// ---------------------------------------------------------------------------
// PKCE helpers
// ---------------------------------------------------------------------------

function _randomBase64url(byteLength: number): string {
  const bytes = crypto.getRandomValues(new Uint8Array(byteLength));
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

async function _sha256Base64url(input: string): Promise<string> {
  const encoded = new TextEncoder().encode(input);
  const digest = await crypto.subtle.digest("SHA-256", encoded);
  return btoa(String.fromCharCode(...new Uint8Array(digest)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

// ---------------------------------------------------------------------------
// OIDC Discovery
// ---------------------------------------------------------------------------

type OIDCDiscovery = {
  authorization_endpoint: string;
  token_endpoint: string;
};

async function _discover(): Promise<OIDCDiscovery> {
  const issuer = ISSUER.replace(/\/+$/, "");
  const response = await fetch(`${issuer}/.well-known/openid-configuration`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`OIDC discovery failed (HTTP ${response.status}).`);
  }
  const payload = await response.json();
  const authorization_endpoint = typeof payload?.authorization_endpoint === "string"
    ? payload.authorization_endpoint.trim()
    : "";
  const token_endpoint = typeof payload?.token_endpoint === "string"
    ? payload.token_endpoint.trim()
    : "";
  if (!authorization_endpoint || !token_endpoint) {
    throw new Error("OIDC discovery response is missing required endpoints.");
  }
  return { authorization_endpoint, token_endpoint };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns true when the OIDC client-side flow is configured via env vars.
 */
export function isOidcConfigured(): boolean {
  return isOidcClientConfigured();
}

/**
 * Kick off the authorization code + PKCE flow by redirecting the user to the
 * IdP authorization endpoint.
 */
export async function startLoginFlow(returnTo?: string): Promise<void> {
  if (!isOidcConfigured()) {
    throw new Error("OIDC is not configured. Set NEXT_PUBLIC_OIDC_ISSUER, NEXT_PUBLIC_OIDC_CLIENT_ID, and NEXT_PUBLIC_OIDC_REDIRECT_URI.");
  }

  const { authorization_endpoint } = await _discover();

  const state = _randomBase64url(16);
  const codeVerifier = _randomBase64url(32);
  const codeChallenge = await _sha256Base64url(codeVerifier);

  sessionStorage.setItem(PKCE_STATE_KEY, state);
  sessionStorage.setItem(PKCE_VERIFIER_KEY, codeVerifier);
  if (returnTo && returnTo.startsWith("/") && !returnTo.startsWith("//")) {
    sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, returnTo);
  } else {
    sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
  }

  const params = new URLSearchParams({
    response_type: "code",
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    scope: "openid profile email",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  if (AUDIENCE) {
    params.set("audience", AUDIENCE);
  }

  window.location.assign(`${authorization_endpoint}?${params.toString()}`);
}

/**
 * Complete the authorization code exchange after the IdP redirects back.
 * Verifies state, exchanges the code for tokens via PKCE, and stores the
 * access token.
 */
export async function handleCallback(code: string, state: string): Promise<string> {
  const savedState = sessionStorage.getItem(PKCE_STATE_KEY);
  const codeVerifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
  const postLoginRedirect = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY);

  sessionStorage.removeItem(PKCE_STATE_KEY);
  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);

  if (!savedState || savedState !== state) {
    throw new Error("OIDC state mismatch. The login request may have been tampered with or expired.");
  }
  if (!codeVerifier) {
    throw new Error("PKCE code verifier not found in session. Please start the login flow again.");
  }

  const { token_endpoint } = await _discover();

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: CLIENT_ID,
    redirect_uri: REDIRECT_URI,
    code,
    code_verifier: codeVerifier,
  });

  const response = await fetch(token_endpoint, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
      "Accept": "application/json",
    },
    body: body.toString(),
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const errPayload = await response.json();
      if (typeof errPayload?.error_description === "string") {
        detail = errPayload.error_description;
      } else if (typeof errPayload?.error === "string") {
        detail = errPayload.error;
      }
    } catch { /* ignore */ }
    throw new Error(`Token exchange failed: ${detail}`);
  }

  const payload = await response.json();
  const accessToken = typeof payload?.access_token === "string" ? payload.access_token.trim() : "";
  if (!accessToken) {
    throw new Error("Token endpoint response did not include an access_token.");
  }

  storeUserAccessToken(accessToken);
  if (postLoginRedirect && postLoginRedirect.startsWith("/") && !postLoginRedirect.startsWith("//")) {
    return postLoginRedirect;
  }
  return "/onboarding/aws";
}

// ---------------------------------------------------------------------------
// JWT decode helper (client-side display only — no signature verification)
// ---------------------------------------------------------------------------

export type JwtDisplayInfo = {
  sub: string | null;
  exp: number | null;
  email: string | null;
  name: string | null;
};

export function decodeJwtForDisplay(token: string): JwtDisplayInfo | null {
  try {
    const parts = token.split(".");
    if (parts.length !== 3) return null;
    const padded = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const json = atob(padded.padEnd(padded.length + ((4 - (padded.length % 4)) % 4), "="));
    const claims = JSON.parse(json);
    return {
      sub: typeof claims.sub === "string" ? claims.sub : null,
      exp: typeof claims.exp === "number" ? claims.exp : null,
      email: typeof claims.email === "string" ? claims.email : null,
      name: typeof claims.name === "string" ? claims.name : null,
    };
  } catch {
    return null;
  }
}
