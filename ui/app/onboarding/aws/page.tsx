"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  fetchAuthMe,
  fetchEnvironments,
  getInMemoryToken,
  isSessionActive,
  USER_ACCESS_TOKEN_CHANGED_EVENT,
  type AuthMe,
  type Environment,
} from "@/lib/api";
import { decodeJwtForDisplay, isOidcConfigured, startLoginFlow } from "@/lib/oidc-client";

function statusTone(done: boolean): string {
  return done ? "success" : "pending";
}

export default function AwsOnboardingPage() {
  const oidcConfigured = isOidcConfigured();
  const [loading, setLoading] = useState(true);
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [active, setActive] = useState(false);
  const [authMe, setAuthMe] = useState<AuthMe | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);

  useEffect(() => {
    let mounted = true;
    async function load() {
      try {
        const mem = getInMemoryToken();
        const hasSession = mem ? true : await isSessionActive();
        const [identity, envs] = await Promise.all([
          hasSession ? fetchAuthMe() : Promise.resolve(null),
          hasSession ? fetchEnvironments().catch(() => []) : Promise.resolve([]),
        ]);
        if (!mounted) return;
        setActive(hasSession);
        setAuthMe(identity);
        setEnvironments(envs.filter((row) => row.status !== "deleted"));
      } finally {
        if (mounted) setLoading(false);
      }
    }
    function onTokenChanged() {
      void load();
    }
    void load();
    window.addEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
    return () => {
      mounted = false;
      window.removeEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
    };
  }, []);

  const tokenInfo = useMemo(() => {
    const token = getInMemoryToken();
    return token ? decodeJwtForDisplay(token) : null;
  }, []);

  const steps = [
    {
      title: "Authenticate with AWS-backed identity",
      done: active,
      detail: active
        ? `Signed in${authMe?.actor ? ` as ${authMe.actor}` : ""}.`
        : oidcConfigured
          ? "Use OIDC sign-in to establish a browser session before calling the SparkPilot API."
          : "OIDC is not configured in this deployment, so login falls back to manual token application in the auth panel.",
      action: active
        ? null
        : oidcConfigured
          ? { label: loginPending ? "Redirecting…" : "Sign in", type: "button" as const }
          : { label: "Open auth panel guidance", href: "#manual-auth", type: "link" as const },
    },
    {
      title: "Verify identity mapping and role scope",
      done: Boolean(authMe),
      detail: authMe
        ? `Role: ${authMe.role}. Scoped environments: ${authMe.scoped_environment_ids.length}. Tenant: ${authMe.tenant_id ?? "not bound"}. Team: ${authMe.team_id ?? "not bound"}.`
        : "Confirm /v1/auth/me resolves your actor, tenant/team scope, and environment access before provisioning.",
      action: { label: "Open Access", href: "/access", type: "link" as const },
    },
    {
      title: "Create or review a BYOC-Lite environment",
      done: environments.length > 0,
      detail: environments.length > 0
        ? `${environments.length} environment(s) visible in this session.`
        : "Use the environment flow with a real customer role ARN, cluster ARN, and namespace. Watch the provisioning operation until ready or failed with remediation.",
      action: { label: environments.length > 0 ? "Open Environments" : "Start environment setup", href: "/environments", type: "link" as const },
    },
    {
      title: "Run a proof check before production use",
      done: false,
      detail: "Before this phase can be marked complete, capture evidence for happy-path sign-in, auth failure handling, missing-scope handling, and successful environment provisioning from this UI flow.",
      action: null,
    },
  ];

  async function handleSignIn() {
    setLoginPending(true);
    setLoginError(null);
    try {
      await startLoginFlow();
    } catch (err: unknown) {
      setLoginError(err instanceof Error ? err.message : "Login failed.");
      setLoginPending(false);
    }
  }

  return (
    <section className="stack onboarding-page">
      <div className="card onboarding-hero">
        <div className="eyebrow">AWS ONBOARDING</div>
        <h2>Authenticate, verify scope, then provision BYOC-Lite safely</h2>
        <p className="subtle" style={{ marginTop: 8 }}>
          This page turns the existing auth panel + environment form into one explicit operator workflow. It is still
          not marked complete in the tracker until browser-tested evidence is captured.
        </p>
        <div className="button-row" style={{ marginTop: 12 }}>
          {oidcConfigured && !active ? (
            <button type="button" className="button" disabled={loginPending} onClick={() => void handleSignIn()}>
              {loginPending ? "Redirecting…" : "Sign in with OIDC"}
            </button>
          ) : null}
          <Link href="/environments" className="button button-secondary">Open environment setup</Link>
          <Link href="/access" className="button button-secondary">Review access mapping</Link>
        </div>
        {loginError ? <div className="subtle" style={{ color: "var(--color-error, #c0392b)", marginTop: 8 }}>{loginError}</div> : null}
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Session state</h3>
          <div className={`status-chip ${statusTone(active)}`}>{active ? "Authenticated" : "Not authenticated"}</div>
          <p className="subtle">{active ? "Browser session or in-memory token is active." : "No verified login session yet."}</p>
        </article>
        <article className="card">
          <h3>Identity</h3>
          <div className="stat-value">{authMe?.role ?? "Unknown"}</div>
          <p className="subtle">{authMe?.actor ?? tokenInfo?.email ?? tokenInfo?.sub ?? "No identity resolved yet."}</p>
        </article>
        <article className="card">
          <h3>Environment visibility</h3>
          <div className="stat-value">{loading ? "…" : environments.length}</div>
          <p className="subtle">Non-deleted environments visible to this session.</p>
        </article>
      </div>

      <div className="card">
        <h3>Operator checklist</h3>
        <div className="onboarding-steps">
          {steps.map((step, index) => (
            <div key={step.title} className="onboarding-step">
              <div className={`step-index ${step.done ? "done" : "pending"}`}>{index + 1}</div>
              <div className="step-body">
                <div className="step-header-row">
                  <strong>{step.title}</strong>
                  <span className={`status-chip ${statusTone(step.done)}`}>{step.done ? "Done" : "Needs proof"}</span>
                </div>
                <div className="subtle">{step.detail}</div>
                {step.action?.type === "button" ? (
                  <div className="button-row" style={{ marginTop: 10 }}>
                    <button type="button" className="button button-sm" disabled={loginPending} onClick={() => void handleSignIn()}>
                      {step.action.label}
                    </button>
                  </div>
                ) : null}
                {step.action?.type === "link" ? (
                  <div className="button-row" style={{ marginTop: 10 }}>
                    <Link href={step.action.href} className="inline-link">{step.action.label} →</Link>
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card" id="manual-auth">
        <h3>Current gap</h3>
        <p className="subtle">
          The repo now has a dedicated onboarding route, but Phase 4 still remains unchecked. What is still missing:
          captured browser evidence, failure-path walkthroughs, responsive validation, cross-browser validation,
          Lighthouse results, and dark-mode implementation.
        </p>
      </div>
    </section>
  );
}
