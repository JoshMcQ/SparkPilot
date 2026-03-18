"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  fetchEnvironments,
  fetchRuns,
  USER_ACCESS_TOKEN_CHANGED_EVENT,
  USER_ACCESS_TOKEN_STORAGE_KEY,
} from "@/lib/api";

export default function HomePage() {
  const [environments, setEnvironments] = useState(0);
  const [runs, setRuns] = useState(0);
  const [running, setRunning] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        const [envData, runData] = await Promise.all([fetchEnvironments(), fetchRuns()]);
        if (cancelled) {
          return;
        }
        setEnvironments(envData.length);
        setRuns(runData.length);
        setRunning(runData.filter((r) => ["accepted", "running", "dispatching"].includes(r.state)).length);
        setError(null);
      } catch (err: unknown) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load dashboard metrics.");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    const onTokenChanged = () => {
      void load();
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === USER_ACCESS_TOKEN_STORAGE_KEY) {
        void load();
      }
    };

    window.addEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
    window.addEventListener("storage", onStorage);
    void load();
    return () => {
      cancelled = true;
      window.removeEventListener(USER_ACCESS_TOKEN_CHANGED_EVENT, onTokenChanged);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const isAuthError =
    !!error && /authentication failed|access denied|no user access token|oidc jwt validation failed/i.test(error);
  const isApiDown =
    !!error && /api is unreachable|backend is running|network|failed to fetch|http 5\d\d/i.test(error);
  const isEmpty = environments === 0 && runs === 0 && !error;

  return (
    <section className="stack">
      {loading ? (
        <div className="card">
          <div className="subtle">Loading dashboard metrics...</div>
        </div>
      ) : null}

      {error ? (
        <div className="card error-card">
          <strong>{isAuthError ? "Authentication Required" : isApiDown ? "API Unreachable" : "Dashboard Error"}</strong>
          <div>
            {isAuthError
              ? "Your token is missing, expired, or invalid. Apply a fresh bearer token in the auth panel."
              : isApiDown
                ? "SparkPilot backend is not responding. Verify the API server is running and check your network connectivity."
                : error}
          </div>
        </div>
      ) : null}

      <div className="card-grid">
        <article className="card">
          <h3>Environments</h3>
          <div className="stat-value">{environments}</div>
          <div className="subtle">Dedicated tenant clusters</div>
          {environments === 0 && !error ? (
            <Link href="/environments" className="inline-link cta-link">Create your first environment &rarr;</Link>
          ) : null}
        </article>
        <article className="card">
          <h3>Total Runs</h3>
          <div className="stat-value">{runs}</div>
          <div className="subtle">Submitted job runs</div>
          {runs === 0 && environments > 0 ? (
            <Link href="/runs" className="inline-link cta-link">Submit your first run &rarr;</Link>
          ) : null}
        </article>
        <article className="card">
          <h3>In Flight</h3>
          <div className="stat-value">{running}</div>
          <div className="subtle">Dispatching / accepted / running</div>
        </article>
      </div>

      {isEmpty ? (
        <div className="card">
          <h3>Getting Started</h3>
          <p className="subtle">
            Welcome to SparkPilot. Start by provisioning an environment, then create a job and submit a run.
            Each run goes through preflight checks before dispatching to EMR on EKS.
          </p>
          <div className="button-row">
            <Link href="/environments" className="button">Create Environment</Link>
            <Link href="/runs" className="button" style={{ background: "var(--surface)", color: "var(--brand)", border: "1px solid var(--brand)" }}>View Runs</Link>
          </div>
        </div>
      ) : null}

      <div className="card-grid">
        <article className="card">
          <h3>Environment Operations</h3>
          <p className="subtle">Provisioning state and isolation profile per tenant.</p>
          <Link href="/environments" className="inline-link">Open environments &rarr;</Link>
        </article>
        <article className="card">
          <h3>Run Operations</h3>
          <p className="subtle">Run status, EMR IDs, and deterministic log pointers.</p>
          <Link href="/runs" className="inline-link">Open runs &rarr;</Link>
        </article>
        <article className="card">
          <h3>Cost &amp; Usage</h3>
          <p className="subtle">CUR-aligned showback and resource usage by team.</p>
          <Link href="/costs" className="inline-link">Open costs &rarr;</Link>
        </article>
      </div>
    </section>
  );
}
