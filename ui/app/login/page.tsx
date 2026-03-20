"use client";

import { useState } from "react";
import Link from "next/link";
import { startLoginFlow } from "@/lib/oidc-client";
import { LandingNav } from "@/components/landing-nav";

export default function LoginPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleLogin() {
    setLoading(true);
    setError(null);
    try {
      await startLoginFlow();
    } catch (e) {
      setError(
        "Could not reach your identity provider. Make sure SPARKPILOT_OIDC_DISCOVERY_URL is configured, or contact your administrator."
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
            You'll be redirected to your organization's identity provider.
          </p>

          {error && (
            <div className="login-error" role="alert">
              {error}
            </div>
          )}

          <button
            className="landing-btn landing-btn-primary login-btn"
            onClick={handleLogin}
            disabled={loading}
          >
            {loading ? "Redirecting…" : "Continue with SSO"}
          </button>

          <div className="login-divider">
            <span>or</span>
          </div>

          <p className="login-manual-hint">
            Have a bearer token?{" "}
            <Link href="/dashboard" className="login-link">
              Open the dashboard
            </Link>{" "}
            and paste it in the auth panel.
          </p>

          <p className="login-footer-note">
            New to SparkPilot?{" "}
            <Link href="/contact" className="login-link">
              Contact us to get access.
            </Link>
          </p>
        </div>
      </section>
    </div>
  );
}
