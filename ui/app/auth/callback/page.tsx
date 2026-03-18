"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { handleCallback } from "@/lib/oidc-client";

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const errorParam = searchParams.get("error");
    const errorDescription = searchParams.get("error_description");

    if (errorParam) {
      setError(errorDescription ?? errorParam);
      return;
    }

    if (!code || !state) {
      setError("Missing code or state in callback URL. The login flow may have been interrupted.");
      return;
    }

    handleCallback(code, state)
      .then(() => {
        router.replace("/");
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Login failed. Please try again.");
      });
  }, [searchParams, router]);

  if (error) {
    return (
      <div className="card" style={{ padding: "2rem" }}>
        <h2>Login failed</h2>
        <p style={{ color: "var(--text-muted)" }}>{error}</p>
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
