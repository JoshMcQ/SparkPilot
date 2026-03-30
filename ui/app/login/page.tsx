"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { startLoginFlow } from "@/lib/oidc-client";
import { isSessionActive } from "@/lib/api";
import { isManualTokenModeEnabled, isOidcClientConfigured } from "@/lib/auth-config";
import { LandingNav } from "@/components/landing-nav";

function LoginPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const oidcConfigured = isOidcClientConfigured();
  const manualTokenModeEnabled = isManualTokenModeEnabled();
  const rawNext = searchParams.get("next");
  const returnTo = rawNext && rawNext.startsWith("/") && !rawNext.startsWith("//")
    ? rawNext
    : "/onboarding/aws";
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void isSessionActive().then((authenticated) => {
      if (authenticated) {
        router.replace(returnTo);
      }
    });
  }, [router, returnTo]);

  async function handleLogin() {
    if (!oidcConfigured) {
      setError("OIDC is not configured for this deployment. Contact your administrator.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await startLoginFlow(returnTo);
    } catch {
      setError(
        "Could not reach your identity provider. Make sure NEXT_PUBLIC_OIDC_ISSUER, NEXT_PUBLIC_OIDC_CLIENT_ID, and NEXT_PUBLIC_OIDC_REDIRECT_URI are configured."
      );
      setLoading(false);
    }
  }

  return (
    <div className="landing">
      <LandingNav />

      <section className="login-page">
        <div className="login-card">
          <div className="login-brand">
            <strong>SparkPilot</strong>
          </div>
          <h1 className="login-title">Sign in to your workspace</h1>
          <p className="login-sub">
            You&apos;ll be redirected to your organization&apos;s identity provider. After login, continue in the guided
            onboarding flow to create your first environment and run.
          </p>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button
            className="landing-btn landing-btn-primary login-btn"
            onClick={handleLogin}
            disabled={loading || !oidcConfigured}
          >
            {loading ? "Redirecting..." : oidcConfigured ? "Continue with SSO" : "SSO unavailable"}
          </button>

          <p className="login-manual-hint">
            After sign-in you will continue to authenticated product onboarding.
          </p>

          {manualTokenModeEnabled ? (
            <>
              <div className="login-divider">
                <span>or</span>
              </div>
              <p className="login-manual-hint" style={{ marginTop: -10 }}>
                Development-only manual token mode is enabled for this environment in{" "}
                <Link href="/dashboard" className="login-link">
                  dashboard auth panel
                </Link>
                .
              </p>
            </>
          ) : null}

          <p className="login-footer-note">
            Need the public pre-access guide first?{" "}
            <Link href="/getting-started" className="login-link">
              Open Getting Started.
            </Link>{" "}
            <br />
            Need access first?{" "}
            <Link href="/contact" className="login-link">
              Request access.
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense
      fallback={(
        <div className="landing">
          <LandingNav />
          <section className="login-page">
            <div className="login-card">
              <h1 className="login-title">Sign in to your workspace</h1>
              <p className="login-sub">Loading login flow...</p>
            </div>
          </section>
        </div>
      )}
    >
      <LoginPageContent />
    </Suspense>
  );
}
