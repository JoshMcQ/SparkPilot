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
import {
  isOidcClientConfigured,
  oidcClientConfig,
  type OidcClientConfig,
  type OidcPool,
} from "@/lib/auth-config";

const INVITE_OIDC_STATE_PREFIX = "sp_oidc_v1";
const PKCE_VERIFIER_KEY = "sparkpilot.oidc.code_verifier";
const PKCE_STATE_KEY = "sparkpilot.oidc.state";
const PKCE_POOL_KEY = "sparkpilot.oidc.pool";
const POST_LOGIN_REDIRECT_KEY = "sparkpilot.oidc.post_login_redirect";

type LoginFlowOptions = {
  returnTo?: string;
  pool?: OidcPool;
  inviteState?: string | null;
};

type ParsedOidcState = {
  csrfState: string;
  inviteState: string | null;
};

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

async function _discover(config: OidcClientConfig): Promise<OIDCDiscovery> {
  const issuer = config.issuer.replace(/\/+$/, "");
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

function _base64urlEncodeText(input: string): string {
  const bytes = new TextEncoder().encode(input);
  let binary = "";
  bytes.forEach((byte) => {
    binary += String.fromCharCode(byte);
  });
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");
}

function _base64urlDecodeText(input: string): string {
  const padded = input.replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(padded.padEnd(padded.length + ((4 - (padded.length % 4)) % 4), "="));
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return new TextDecoder().decode(bytes);
}

export function buildOidcState(csrfState: string, inviteState?: string | null): string {
  const trimmedCsrf = csrfState.trim();
  const trimmedInvite = (inviteState ?? "").trim();
  if (!trimmedInvite) {
    return trimmedCsrf;
  }
  return `${INVITE_OIDC_STATE_PREFIX}.${_base64urlEncodeText(JSON.stringify({
    csrf_state: trimmedCsrf,
    invite_state: trimmedInvite,
  }))}`;
}

export function parseOidcState(state: string): ParsedOidcState {
  const trimmed = state.trim();
  if (!trimmed.startsWith(`${INVITE_OIDC_STATE_PREFIX}.`)) {
    return { csrfState: trimmed, inviteState: null };
  }
  const encoded = trimmed.slice(INVITE_OIDC_STATE_PREFIX.length + 1);
  try {
    const payload = JSON.parse(_base64urlDecodeText(encoded));
    const csrfState = typeof payload?.csrf_state === "string"
      ? payload.csrf_state.trim()
      : "";
    const inviteState = typeof payload?.invite_state === "string"
      ? payload.invite_state.trim()
      : "";
    if (!csrfState || !inviteState) {
      throw new Error("OIDC state payload is missing required fields.");
    }
    return { csrfState, inviteState };
  } catch (error) {
    throw new Error(
      error instanceof Error
        ? `OIDC state payload is invalid: ${error.message}`
        : "OIDC state payload is invalid.",
    );
  }
}

function _normalizeLoginOptions(input?: string | LoginFlowOptions): Required<LoginFlowOptions> {
  if (typeof input === "string") {
    return {
      returnTo: input,
      pool: "customer",
      inviteState: null,
    };
  }
  const pool = input?.pool === "internal" ? "internal" : "customer";
  return {
    returnTo: input?.returnTo ?? (pool === "internal" ? "/internal/tenants" : "/onboarding/aws"),
    pool,
    inviteState: input?.inviteState ?? null,
  };
}

async function _applyInviteCallback(inviteState: string, accessToken: string): Promise<void> {
  const response = await fetch(`/api/sparkpilot/v1/invite/callback?state=${encodeURIComponent(inviteState)}`, {
    cache: "no-store",
    headers: {
      "Accept": "application/json",
      "Authorization": `Bearer ${accessToken}`,
    },
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        detail = payload.detail;
      }
    } catch { /* ignore */ }
    throw new Error(`Invite acceptance failed: ${detail}`);
  }
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns true when the OIDC client-side flow is configured via env vars.
 */
export function isOidcConfigured(): boolean {
  return isOidcClientConfigured("customer");
}

/**
 * Kick off the authorization code + PKCE flow by redirecting the user to the
 * IdP authorization endpoint.
 */
export async function startLoginFlow(options?: string | LoginFlowOptions): Promise<void> {
  const normalized = _normalizeLoginOptions(options);
  const config = oidcClientConfig(normalized.pool);
  if (!isOidcClientConfigured(normalized.pool)) {
    const prefix = normalized.pool === "internal" ? "NEXT_PUBLIC_INTERNAL_OIDC" : "NEXT_PUBLIC_OIDC";
    throw new Error(`OIDC is not configured. Set ${prefix}_ISSUER, ${prefix}_CLIENT_ID, and ${prefix}_REDIRECT_URI.`);
  }

  const { authorization_endpoint } = await _discover(config);

  const csrfState = _randomBase64url(16);
  const codeVerifier = _randomBase64url(32);
  const codeChallenge = await _sha256Base64url(codeVerifier);
  const state = buildOidcState(csrfState, normalized.inviteState);

  sessionStorage.setItem(PKCE_STATE_KEY, state);
  sessionStorage.setItem(PKCE_VERIFIER_KEY, codeVerifier);
  sessionStorage.setItem(PKCE_POOL_KEY, normalized.pool);
  if (normalized.returnTo && normalized.returnTo.startsWith("/") && !normalized.returnTo.startsWith("//")) {
    sessionStorage.setItem(POST_LOGIN_REDIRECT_KEY, normalized.returnTo);
  } else {
    sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);
  }

  const params = new URLSearchParams({
    response_type: "code",
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    scope: "openid profile email",
    state,
    code_challenge: codeChallenge,
    code_challenge_method: "S256",
  });
  if (config.audience) {
    params.set("audience", config.audience);
  }
  if (config.identityProvider) {
    params.set("identity_provider", config.identityProvider);
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
  const savedPool = sessionStorage.getItem(PKCE_POOL_KEY);
  const postLoginRedirect = sessionStorage.getItem(POST_LOGIN_REDIRECT_KEY);

  sessionStorage.removeItem(PKCE_STATE_KEY);
  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  sessionStorage.removeItem(PKCE_POOL_KEY);
  sessionStorage.removeItem(POST_LOGIN_REDIRECT_KEY);

  const returnedState = state.trim();
  if (!savedState || savedState !== returnedState) {
    throw new Error("OIDC state mismatch. The login request may have been tampered with or expired.");
  }
  const parsedState = parseOidcState(returnedState);
  if (!codeVerifier) {
    throw new Error("PKCE code verifier not found in session. Please start the login flow again.");
  }
  const pool: OidcPool = savedPool === "internal" ? "internal" : "customer";
  const config = oidcClientConfig(pool);

  const { token_endpoint } = await _discover(config);

  const body = new URLSearchParams({
    grant_type: "authorization_code",
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
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

  if (parsedState.inviteState) {
    await _applyInviteCallback(parsedState.inviteState, accessToken);
  }
  await storeUserAccessToken(accessToken);
  if (postLoginRedirect && postLoginRedirect.startsWith("/") && !postLoginRedirect.startsWith("//")) {
    return postLoginRedirect;
  }
  return pool === "internal" ? "/internal/tenants" : "/onboarding/aws";
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
