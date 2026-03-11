"use client";

import { useEffect, useState } from "react";
import { USER_ACCESS_TOKEN_STORAGE_KEY, storeUserAccessToken } from "@/lib/api";
import { isOidcConfigured, startLoginFlow, decodeJwtForDisplay } from "@/lib/oidc-client";

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
  const [value, setValue] = useState("");
  const [active, setActive] = useState(false);
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const oidcConfigured = isOidcConfigured();

  useEffect(() => {
    const existing = window.localStorage.getItem(USER_ACCESS_TOKEN_STORAGE_KEY)?.trim() ?? "";
    setValue(existing);
    setActive(Boolean(existing));
  }, []);

  function saveToken() {
    storeUserAccessToken(value);
    setActive(Boolean(value.trim()));
  }

  function clearToken() {
    setValue("");
    storeUserAccessToken("");
    setActive(false);
  }

  async function handleSignIn() {
    setLoginPending(true);
    setLoginError(null);
    try {
      await startLoginFlow();
      // startLoginFlow() redirects the page; nothing to do after this point.
    } catch (err: unknown) {
      setLoginError(err instanceof Error ? err.message : "Login failed.");
      setLoginPending(false);
    }
  }

  // Decode the current token for display (no verification — display only).
  const tokenInfo = active ? decodeJwtForDisplay(value) : null;
  const displaySubject = tokenInfo?.email ?? tokenInfo?.name ?? tokenInfo?.sub ?? null;
  const expiryText = tokenInfo ? _formatExpiry(tokenInfo.exp) : "";

  return (
    <div className="auth-panel">
      {oidcConfigured ? (
        <>
          <label className="auth-label">Authentication</label>
          {active ? (
            <div className="auth-row">
              <span className="subtle" style={{ flex: 1 }}>
                {displaySubject ? `Signed in as ${displaySubject}${expiryText}` : `Token active${expiryText}`}
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
          <div className="subtle auth-status">
            {active
              ? "Requests are sent with your OIDC token."
              : "Sign in to authenticate your requests."}
          </div>
        </>
      ) : (
        <>
          <label className="auth-label" htmlFor="user-token">
            User access token
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
            <button type="button" className="button button-sm" onClick={saveToken}>
              Apply
            </button>
            <button type="button" className="button button-sm button-secondary" onClick={clearToken}>
              Clear
            </button>
          </div>
          <div className="subtle auth-status">
            {active
              ? "Requests are sent with your bearer token."
              : "Paste a token to authenticate API requests."}
          </div>
        </>
      )}
    </div>
  );
}
