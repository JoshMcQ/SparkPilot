"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  fetchAuthMe,
  fetchEnvironments,
  fetchJobs,
  fetchRuns,
  fetchUsage,
  getInMemoryToken,
  isSessionActive,
  USER_ACCESS_TOKEN_CHANGED_EVENT,
  type AuthMe,
  type Environment,
  type Job,
  type Run,
} from "@/lib/api";
import { decodeJwtForDisplay, isOidcConfigured, startLoginFlow } from "@/lib/oidc-client";
import EnvironmentCreateForm from "@/app/environments/environment-create-form";

type StepStatus = "done" | "todo" | "waiting" | "blocked";

type OnboardingAction =
  | { kind: "button"; label: string }
  | { kind: "link"; label: string; href: string }
  | null;

type OnboardingStep = {
  id: string;
  title: string;
  status: StepStatus;
  detail: string;
  remediation?: string;
  action: OnboardingAction;
};

function statusLabel(status: StepStatus): string {
  if (status === "done") return "Done";
  if (status === "todo") return "Do this now";
  if (status === "waiting") return "Waiting";
  return "Blocked";
}

function statusClass(status: StepStatus): string {
  return status === "done" ? "success" : "pending";
}

export default function AwsOnboardingPage() {
  const oidcConfigured = isOidcConfigured();
  const [refreshNonce, setRefreshNonce] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loginPending, setLoginPending] = useState(false);
  const [loginError, setLoginError] = useState<string | null>(null);
  const [active, setActive] = useState(false);
  const [authMe, setAuthMe] = useState<AuthMe | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [usageRecords, setUsageRecords] = useState<number | null>(null);
  const [usageWarning, setUsageWarning] = useState<string | null>(null);
  const currentRequestIdRef = useRef(0);

  useEffect(() => {
    let mounted = true;

    async function load() {
      const requestId = ++currentRequestIdRef.current;
      try {
        const mem = getInMemoryToken();
        const sessionActive = mem ? true : await isSessionActive();
        const identity = await fetchAuthMe().catch(() => null);
        const hasSession = sessionActive || Boolean(mem) || Boolean(identity);

        const [envRows, jobRows, runRows] = await Promise.all([
          hasSession ? fetchEnvironments().catch(() => []) : Promise.resolve([]),
          hasSession ? fetchJobs().catch(() => []) : Promise.resolve([]),
          hasSession ? fetchRuns().catch(() => []) : Promise.resolve([]),
        ]);

        let usageCount: number | null = null;
        let warning: string | null = null;
        if (hasSession && identity?.tenant_id) {
          try {
            const usage = await fetchUsage(identity.tenant_id);
            usageCount = usage.items.length;
          } catch {
            warning = "Usage records are delayed or unavailable. First-run completion can still be validated.";
          }
        }

        const tenantId = identity?.tenant_id ?? null;
        const scopedEnvironments = envRows.filter(
          (row) => row.status !== "deleted" && tenantId != null && row.tenant_id === tenantId
        );
        const scopedEnvironmentIds = new Set(scopedEnvironments.map((row) => row.id));
        const scopedJobs = jobRows.filter((row) => scopedEnvironmentIds.has(row.environment_id));
        const scopedRuns = runRows.filter((row) => scopedEnvironmentIds.has(row.environment_id));

        if (!mounted || requestId !== currentRequestIdRef.current) return;
        setActive(hasSession);
        setAuthMe(identity);
        setEnvironments(scopedEnvironments);
        setJobs(scopedJobs);
        setRuns(scopedRuns);
        setUsageRecords(usageCount);
        setUsageWarning(warning);
      } finally {
        if (mounted && requestId === currentRequestIdRef.current) setLoading(false);
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
  }, [refreshNonce]);

  const token = getInMemoryToken();
  const tokenInfo = useMemo(() => (token ? decodeJwtForDisplay(token) : null), [token]);

  const readyEnvironments = useMemo(
    () => environments.filter((row) => row.status === "ready"),
    [environments]
  );
  const succeededRuns = useMemo(
    () => runs.filter((row) => row.state === "succeeded"),
    [runs]
  );
  const isAdmin = authMe?.role === "admin";
  const identityBound = Boolean(authMe?.tenant_id);

  const steps: OnboardingStep[] = [
    {
      id: "session",
      title: "Start authenticated session",
      status: active ? "done" : "todo",
      detail: active
        ? "Session is active."
        : "Start an authenticated browser session before using environments or runs.",
      remediation: active
        ? undefined
        : oidcConfigured
          ? "Use OIDC sign-in from this page to establish the session."
          : "OIDC is not configured. Use the login/manual token path for this environment.",
      action: active
        ? null
        : oidcConfigured
          ? { kind: "button", label: loginPending ? "Redirecting..." : "Sign in with OIDC" }
          : { kind: "link", label: "Open login", href: "/login" },
    },
    {
      id: "identity",
      title: "Verify identity mapping",
      status: !active ? "blocked" : identityBound ? "done" : isAdmin ? "todo" : "blocked",
      detail: authMe
        ? `Role: ${authMe.role}. Tenant: ${authMe.tenant_id ?? "not bound"}. Team: ${authMe.team_id ?? "not bound"}.`
        : active
          ? "Signed in, but /v1/auth/me did not return scoped identity details."
          : "Identity checks run after session authentication.",
      remediation: identityBound
        ? undefined
        : !authMe
          ? "Retry sign-in and identity lookup before requesting access changes."
        : active
          ? isAdmin
            ? "Map this identity to a tenant in Access before creating environments or submitting runs."
            : "Ask your SparkPilot admin to map your identity to a tenant in Access."
          : "Authenticate first, then recheck identity mapping.",
      action: !active
        ? { kind: "link", label: "Open login", href: "/login" }
        : !authMe
          ? { kind: "link", label: "Open login", href: "/login" }
        : identityBound
          ? { kind: "link", label: "Open Access", href: "/access" }
          : isAdmin
            ? { kind: "link", label: "Open Access", href: "/access" }
            : { kind: "link", label: "Request access", href: "/contact" },
    },
    {
      id: "environment",
      title: "Get one ready environment",
      status: !active || !authMe
        ? "blocked"
        : !authMe.tenant_id
          ? "blocked"
        : readyEnvironments.length > 0
          ? "done"
          : isAdmin
            ? environments.length > 0
              ? "waiting"
              : "todo"
            : "blocked",
      detail: readyEnvironments.length > 0
        ? `${environments.length} total visible environment(s).`
        : !active || !authMe
          ? "Environment setup is blocked until access mapping is complete."
        : !identityBound
          ? "Environment setup is blocked because your identity is not mapped to a tenant."
        : isAdmin
          ? environments.length > 0
            ? "Environment exists but is not ready yet."
            : "Create your first BYOC-Lite environment."
            : "Environment creation requires admin role.",
      remediation: readyEnvironments.length > 0
        ? undefined
        : !active || !authMe
          ? "Complete sign-in and identity mapping first."
        : !identityBound
            ? isAdmin
              ? "Map this identity to a tenant in Access, then continue with assisted setup."
              : "Ask your SparkPilot admin to map your identity in Access before environment setup."
          : isAdmin
            ? environments.length > 0
              ? "Wait for provisioning to complete or open Environments for retry/remediation."
              : "Run assisted setup: discover cluster, use suggested namespace, then create environment."
            : "Ask an admin to create the first environment, then continue here.",
      action: !active || !authMe
        ? { kind: "link", label: "Open login", href: "/login" }
        : !identityBound
          ? isAdmin
            ? { kind: "link", label: "Open Access", href: "/access" }
            : { kind: "link", label: "Request access", href: "/contact" }
        : environments.length > 0
          ? { kind: "link", label: "Open Environments", href: "/environments" }
        : isAdmin
          ? { kind: "link", label: "Open assisted setup", href: "#assisted-environment-setup" }
          : { kind: "link", label: "Open Environments", href: "/environments" },
    },
    {
      id: "job",
      title: "Create one job template",
      status: !active || !authMe || !authMe.tenant_id || readyEnvironments.length === 0 ? "blocked" : jobs.length > 0 ? "done" : "todo",
      detail: jobs.length > 0
        ? `${jobs.length} job template(s) available.`
        : !active || !authMe || !authMe.tenant_id || readyEnvironments.length === 0
          ? "Job creation is blocked until a ready environment exists."
          : "Create your first job template from the Runs workspace.",
      remediation: jobs.length > 0
        ? undefined
        : "Use a known-good artifact URI and entrypoint for your first run.",
      action: { kind: "link", label: "Open Runs", href: "/runs" },
    },
    {
      id: "run",
      title: "Reach first successful run",
      status: !active || !authMe || !authMe.tenant_id || readyEnvironments.length === 0 || jobs.length === 0
        ? "blocked"
        : succeededRuns.length > 0
          ? "done"
          : runs.length > 0
            ? "waiting"
            : "todo",
      detail: succeededRuns.length > 0
        ? `${succeededRuns.length} succeeded run(s).`
        : !active || !authMe || !authMe.tenant_id || readyEnvironments.length === 0 || jobs.length === 0
          ? "Run submission is blocked by incomplete prerequisites."
          : runs.length > 0
            ? "Run submitted; waiting for terminal success."
            : "Submit your first run after preflight passes.",
      remediation: succeededRuns.length > 0
        ? undefined
        : runs.length > 0
          ? "Open Runs for logs and diagnostics if this state stalls or fails."
          : "Run preflight, resolve failed checks, then submit.",
      action: { kind: "link", label: "Open Runs", href: "/runs" },
    },
    {
      id: "value",
      title: "Verify proof of value",
      status: !active || !authMe || !authMe.tenant_id || succeededRuns.length === 0
        ? "blocked"
        : usageRecords != null && usageRecords > 0
          ? "done"
          : "waiting",
      detail: usageRecords != null && usageRecords > 0
        ? `${usageRecords} usage record(s) visible for cost/usage evidence.`
        : !active || !authMe || !authMe.tenant_id || succeededRuns.length === 0
          ? "Proof of value unlocks after first successful run."
          : "Run succeeded; waiting for usage/cost records to appear.",
      remediation: usageRecords != null && usageRecords > 0
        ? undefined
        : "Open Costs and confirm estimated/reconciled records once ingestion completes.",
      action: { kind: "link", label: "Open Costs", href: "/costs" },
    },
  ];

  const completedCount = steps.filter((step) => step.status === "done").length;
  const progressPct = Math.round((completedCount / steps.length) * 100);
  const nextStep = steps.find((step) => step.status !== "done") ?? null;
  const showEmbeddedEnvironmentSetup = active && Boolean(authMe?.tenant_id) && isAdmin && environments.length === 0;

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
        <div className="eyebrow">START HERE</div>
        <h2 data-testid="onboarding-title">Guided onboarding to first successful Spark run</h2>
        <p className="subtle" style={{ marginTop: 8 }}>
          This flow is the canonical path from sign-in to proof-of-value. Follow each gate in order and resolve
          blocked steps before moving forward.
        </p>
        <div className="subtle" style={{ marginTop: 8 }}>
          Progress: {completedCount}/{steps.length} complete ({progressPct}%)
        </div>
        {usageWarning ? (
          <div className="subtle" style={{ marginTop: 8, color: "var(--color-warning, #8a5300)" }}>
            {usageWarning}
          </div>
        ) : null}
        {loginError ? (
          <div className="subtle" style={{ marginTop: 8, color: "var(--color-error, #c0392b)" }}>
            {loginError}
          </div>
        ) : null}
      </div>

      <div className="card">
        <h3>Current next action</h3>
        {nextStep ? (
          <div className="onboarding-step" style={{ marginTop: 8 }}>
            <div className="step-index pending">!</div>
            <div className="step-body">
              <div className="step-header-row">
                <strong>{nextStep.title}</strong>
                <span className={`status-chip ${statusClass(nextStep.status)}`}>{statusLabel(nextStep.status)}</span>
              </div>
              <div className="subtle">{nextStep.detail}</div>
              {nextStep.remediation ? <div className="subtle" style={{ marginTop: 6 }}>{nextStep.remediation}</div> : null}
              {nextStep.action?.kind === "button" ? (
                <div className="button-row" style={{ marginTop: 10 }}>
                  <button type="button" className="button button-sm" disabled={loginPending} onClick={() => void handleSignIn()}>
                    {nextStep.action.label}
                  </button>
                </div>
              ) : null}
              {nextStep.action?.kind === "link" ? (
                <div className="button-row" style={{ marginTop: 10 }}>
                  <Link href={nextStep.action.href} className="inline-link">{nextStep.action.label} →</Link>
                </div>
              ) : null}
            </div>
          </div>
        ) : (
          <div className="subtle" style={{ marginTop: 8 }}>
            Onboarding is complete. Move to normal operations in Runs and Costs.
          </div>
        )}
      </div>

      {showEmbeddedEnvironmentSetup ? (
        <EnvironmentCreateForm
          onEnvironmentQueued={() => {
            setRefreshNonce((prev) => prev + 1);
          }}
        />
      ) : null}

      <div className="card-grid">
        <article className="card">
          <h3>Session</h3>
          <div data-testid="session-status" className={`status-chip ${statusClass(active ? "done" : "todo")}`}>
            {active ? "Authenticated" : "Not authenticated"}
          </div>
          <p className="subtle">{active ? "Browser session is active." : "No verified session yet."}</p>
        </article>
        <article className="card">
          <h3>Identity</h3>
          <div className="stat-value">{authMe?.role ?? "Unknown"}</div>
          <p className="subtle">{authMe?.actor ?? tokenInfo?.email ?? tokenInfo?.sub ?? "No identity resolved yet."}</p>
        </article>
        <article className="card">
          <h3>Environment visibility</h3>
          <div className="stat-value">{loading ? "..." : environments.length}</div>
          <p className="subtle">{readyEnvironments.length} ready environment(s).</p>
        </article>
      </div>

      <div className="card">
        <h3>Step-by-step gate status</h3>
        <div className="subtle">States are explicit: done, do now, waiting, or blocked.</div>
        <div className="onboarding-steps">
          {steps.map((step, index) => (
            <div key={step.id} className="onboarding-step">
              <div className={`step-index ${step.status === "done" ? "done" : "pending"}`}>{index + 1}</div>
              <div className="step-body">
                <div className="step-header-row">
                  <strong>{step.title}</strong>
                  <span className={`status-chip ${statusClass(step.status)}`}>{statusLabel(step.status)}</span>
                </div>
                <div className="subtle">{step.detail}</div>
                {step.remediation ? <div className="subtle" style={{ marginTop: 6 }}>{step.remediation}</div> : null}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>Quick links</h3>
        <div className="button-row">
          <Link href="/getting-started" className="button button-secondary">Getting Started</Link>
          <Link href="/access" className="button button-secondary">Access</Link>
          <Link href="/environments" className="button button-secondary">Environments</Link>
          <Link href="/runs" className="button button-secondary">Runs</Link>
          <Link href="/costs" className="button button-secondary">Costs</Link>
        </div>
      </div>
    </section>
  );
}
