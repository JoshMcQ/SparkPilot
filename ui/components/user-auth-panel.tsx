"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  USER_ACCESS_TOKEN_STORAGE_KEY,
  USER_ACCESS_TOKEN_CHANGED_EVENT,
  AUTH_KEY_ROTATION_EVENT,
  fetchEnvironments,
  storeUserAccessToken,
  getInMemoryToken,
  isSessionActive,
  fetchAuthMe,
  type AuthMe,
} from "@/lib/api";
import { startLoginFlow, decodeJwtForDisplay } from "@/lib/oidc-client";
import { isManualTokenModeEnabled, isOidcClientConfigured, type OidcPool } from "@/lib/auth-config";

function _formatExpiry(exp: number | null): string {
  if (exp === null) return "";
  const date = new Date(exp * 1000);
  const now = Date.now();
  if (date.getTime() < now) return " (expired)";
  const diffMin = Math.round((date.getTime() - now) / 60_000);
  if (diffMin < 60) return ` (expires in ${diffMin}m)`;
  const diffHr = Math.round(diffMin / 60);
  return ` (expires in ${diffHr}h)`;
}

export function UserAuthPanel() {
  const pathname = usePathname();
  const authPool: OidcPool = pathname.startsWith("/internal") ? "internal" : "customer";
  const [value, setValue] = useState("");
  const [active, setActive] = useState(false);
  const [applyPending, setApplyPending] = useState(false);
  const [applyFeedback, setApplyFeedback] = useState<string | null>(null);
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [keyRotationDetected, setKeyRotationDetected] = useState(false);
  const [authMe, setAuthMe] = useState<AuthMe | null>(null);
  const oidcConfigured = isOidcClientConfigured(authPool);
  const manualTokenModeEnabled = !oidcConfigured && isManualTokenModeEnabled();

  useEffect(() => {
    // Initialise from in-memory token first, then check HttpOnly session cookie.
    const mem = getInMemoryToken();
    if (mem) {
      setValue(mem);
      setActive(true);
      // Resolve identity context from backend (#75)
      fetchAuthMe().then(setAuthMe);
      return;
    }

    // Non-OIDC dev mode: fall back to localStorage for manual-paste workflow
    if (manualTokenModeEnabled) {
      const stored = window.localStorage.getItem(USER_ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? "";
      setValue(stored);
      setActive(Boolean(stored));
      if (stored) fetchAuthMe().then(setAuthMe);
      return;
    }

    if (oidcConfigured) {
      // OIDC mode + no in-memory token (e.g. page refresh): ask server for cookie state
      isSessionActive().then((hasSession) => {
        setActive(hasSession);
        if (hasSession) fetchAuthMe().then(setAuthMe);
      });
      return;
    }

    setValue("");
    setActive(false);
    setAuthMe(null);
  }, [manualTokenModeEnabled, oidcConfigured]);

  // Sync state when token is updated elsewhere (e.g. OIDC callback in same lifecycle)
  useEffect(() => {
    function onTokenChanged() {
      const mem = getInMemoryToken();
      if (mem) {
        setValue(mem);
        setActive(true);
        setKeyRotationDetected(false);
        fetchAuthMe().then(setAuthMe);
      } else {
        setValue("");
        setActive(false);
        setAuthMe(null);
      }
    }
    window.addEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
    return () => window.removeEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
  }, []);

  // Detect key-rotation 401 and prompt re-authentication (#84)
  useEffect(() => {
    function onKeyRotation() {
      setKeyRotationDetected(true);
    }
    window.addEventListener(AUTH_KEY_ROTATION_EVENT, onKeyRotation);
    return () => window.removeEventListener(AUTH_KEY_ROTATION_EVENT, onKeyRotation);
  }, []);

  async function saveToken() {
    const normalized = value.trim();
    setValue(normalized);
    storeUserAccessToken(normalized);
    setActive(Boolean(normalized));
    setApplyFeedback(null);

    if (!normalized) {
      setApplyFeedback("Token cleared.");
      return;
    }

    setApplyPending(true);
    try {
      const envs = await fetchEnvironments();
      setApplyFeedback(`Token applied. API auth verified (${envs.length} environments visible).`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "API validation failed.";
      setApplyFeedback(`Token saved, but API check failed: ${message}`);
    } finally {
      setApplyPending(false);
    }
  }

  function clearToken() {
    setValue("");
    storeUserAccessToken("");
    setActive(false);
    setAuthMe(null);
    setApplyFeedback("Token cleared.");
  }

  async function handleSignIn() {
    setLoginPending(true);
    setLoginError(null);
    try {
      await startLoginFlow({ pool: authPool, returnTo: pathname });
      // startLoginFlow() redirects the page; nothing to do after this point.
    } catch (err: unknown) {
      setLoginError(err instanceof Error ? err.message : "Login failed.");
      setLoginPending(false);
    }
  }

  // Decode the current token for display (no verification — display only).
  const tokenInfo = active ? decodeJwtForDisplay(value) : null;
  // Derive display name: prefer authMe.actor, fall back to JWT decode
  const displaySubject = authMe?.email ?? tokenInfo?.email ?? tokenInfo?.name ?? authMe?.actor ?? tokenInfo?.sub ?? null;
  const expiryText = tokenInfo ? _formatExpiry(tokenInfo.exp) : "";
  const roleLabel = authMe ? (authMe.is_internal_admin ? "internal admin" : authMe.role) : null;
  const authStatus = active
    ? authMe
      ? authMe.is_internal_admin
        ? "Internal admin access enabled."
        : `${authMe.scoped_environment_ids.length} environment(s) accessible.`
      : "Requests are sent with your OIDC token."
    : "Sign in to authenticate your requests.";

  return (
    <div className="auth-panel">
      {oidcConfigured ? (
        <>
          <label className="auth-label">Authentication</label>
          {keyRotationDetected ? (
            <div
              className="auth-row"
              style={{
                background: "var(--color-warning-bg, #fef3cd)",
                border: "1px solid var(--color-warning-border, #ffc107)",
                borderRadius: 6,
                padding: "0.5rem 0.75rem",
                marginBottom: 8,
              }}
            >
              <span style={{ flex: 1 }}>
                Signing keys have changed. Please sign in again to get a new token.
              </span>
              <button
                type="button"
                className="button button-sm"
                onClick={() => {
                  setKeyRotationDetected(false);
                  clearToken();
                  void handleSignIn();
                }}
                disabled={loginPending}
              >
                {loginPending ? "Redirecting…" : "Sign in again"}
              </button>
            </div>
          ) : null}
          {active ? (
            <div className="auth-row">
              <span className="subtle" style={{ flex: 1 }}>
                {displaySubject ? `Signed in as ${displaySubject}` : "Token active"}
                {roleLabel ? ` (${roleLabel})` : ""}
                {expiryText}
              </span>
              <button type="button" className="button button-sm button-secondary" onClick={clearToken}>
                Sign out
              </button>
            </div>
          ) : (
            <div className="auth-row">
              <button
                type="button"
                className="button button-sm"
                onClick={() => void handleSignIn()}
                disabled={loginPending}
              >
                {loginPending ? "Redirecting…" : "Sign in"}
              </button>
            </div>
          )}
          {loginError ? (
            <div className="subtle" style={{ color: "var(--color-error, #c0392b)", marginTop: 4 }}>
              {loginError}
            </div>
          ) : null}
          <div className="subtle auth-status">{authStatus}</div>
        </>
      ) : manualTokenModeEnabled ? (
        <>
          <label className="auth-label" htmlFor="user-token">
            User access token (development mode)
          </label>
          {active && tokenInfo ? (
            <div className="subtle" style={{ marginBottom: 4 }}>
              {displaySubject ? `Subject: ${displaySubject}` : "Token active"}{expiryText}
            </div>
          ) : null}
          <div className="auth-row">
            <input
              id="user-token"
              className="auth-input"
              placeholder="Paste Bearer token to use per-user RBAC"
              value={value}
              onChange={(event) => setValue(event.target.value)}
            />
            <button type="button" className="button button-sm" onClick={() => void saveToken()} disabled={applyPending}>
              {applyPending ? "Applying..." : "Apply"}
            </button>
            <button type="button" className="button button-sm button-secondary" onClick={clearToken}>
              Clear
            </button>
          </div>
          {applyFeedback ? <div className="subtle auth-feedback">{applyFeedback}</div> : null}
          <div className="subtle auth-status">
            {active
              ? "Requests are sent with your bearer token."
              : "Paste a token to authenticate API requests."}
          </div>
        </>
      ) : (
        <>
          <label className="auth-label">Authentication</label>
          <div className="subtle auth-status">
            Single sign-on is required, but OIDC is not configured for this deployment.
            Contact your administrator to configure `NEXT_PUBLIC_OIDC_*` settings.
          </div>
        </>
      )}
    </div>
  );
}
