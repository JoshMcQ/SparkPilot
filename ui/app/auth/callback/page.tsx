"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { handleCallback } from "@/lib/oidc-client";

function AuthCallbackContent() {
  const searchParams = useSearchParams();
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const errorParam = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");
  const callbackError = errorParam
    ? (errorDescription ?? errorParam)
    : (!code || !state
      ? "Missing code or state in callback URL. The login flow may have been interrupted."
      : null);

  const [asyncError, setAsyncError] = useState<string | null>(null);

  useEffect(() => {
    if (callbackError || !code || !state) {
      return;
    }

    handleCallback(code, state)
      .then((nextPath) => {
        // Use a full navigation so middleware reads the freshly persisted
        // HttpOnly session cookie on the first authenticated route load.
        // replace() prevents users from navigating back to a stale callback URL.
        window.location.replace(nextPath);
      })
      .catch((err: unknown) => {
        setAsyncError(err instanceof Error ? err.message : "Login failed. Please try again.");
      });
  }, [callbackError, code, state]);

  const effectiveError = asyncError ?? callbackError;

  if (effectiveError) {
    return (
      <div className="card" style={{ padding: "2rem" }}>
        <h2>Login failed</h2>
        <p style={{ color: "var(--text-muted)" }}>{effectiveError}</p>
        <Link href="/" className="button" style={{ marginTop: "1rem", display: "inline-block" }}>
          Back to home
        </Link>
      </div>
    );
  }

  return (
    <div className="card" style={{ padding: "2rem", color: "var(--text-muted)" }}>
      Completing login&hellip;
    </div>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <div className="card" style={{ padding: "2rem", color: "var(--text-muted)" }}>
          Loading&hellip;
        </div>
      }
    >
      <AuthCallbackContent />
    </Suspense>
  );
}
