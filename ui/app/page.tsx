"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  fetchEnvironments,
  fetchRuns,
  fetchUsage,
  type Run,
  USER_ACCESS_TOKEN_CHANGED_EVENT,
  USER_ACCESS_TOKEN_STORAGE_KEY,
} from "@/lib/api";

const VALUE_PILLARS = [
  {
    title: "Fail-fast preflight safety",
    detail:
      "SparkPilot blocks bad submissions before dispatch with IAM/IRSA/OIDC diagnostics and remediation steps.",
  },
  {
    title: "Cost-aware operations",
    detail:
      "Track environment/run usage and connect run execution to accountable cost controls and team ownership.",
  },
  {
    title: "Operator-first workflows",
    detail:
      "Guided access setup, explicit run states, and deterministic log pointers reduce on-call investigation time.",
  },
];

function shortId(value: string): string {
  if (!value) return "-";
  if (value.length <= 12) return value;
  return `${value.slice(0, 8)}…${value.slice(-4)}`;
}

function formatUsd(value: number | null): string {
  if (value == null) return "N/A";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function parseTimestamp(run: Run): number {
  const raw = run.created_at ?? run.updated_at ?? run.started_at ?? run.ended_at ?? "";
  const parsed = Date.parse(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatTimestamp(raw: string | null | undefined): string {
  if (!raw) return "-";
  const timestamp = Date.parse(raw);
  if (!Number.isFinite(timestamp)) return raw;
  return new Date(timestamp).toLocaleString();
}

export default function HomePage() {
  const [environments, setEnvironments] = useState(0);
  const [runs, setRuns] = useState(0);
  const [running, setRunning] = useState(0);
  const [runRows, setRunRows] = useState<Run[]>([]);
  const [estimatedCostUsd, setEstimatedCostUsd] = useState<number | null>(null);
  const [costRangeLabel, setCostRangeLabel] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        setLoading(true);
        const [envData, runData] = await Promise.all([fetchEnvironments(), fetchRuns()]);

        let nextEstimatedCostUsd: number | null = null;
        let nextCostRangeLabel: string | null = null;
        if (envData.length > 0) {
          try {
            const usage = await fetchUsage(envData[0].tenant_id);
            nextEstimatedCostUsd = usage.items.reduce(
              (sum, item) => sum + item.estimated_cost_usd_micros,
              0
            ) / 1_000_000;
            nextCostRangeLabel = `${formatTimestamp(usage.from_ts)} – ${formatTimestamp(usage.to_ts)}`;
          } catch {
            nextEstimatedCostUsd = null;
            nextCostRangeLabel = null;
          }
        }

        if (cancelled) {
          return;
        }
        setEnvironments(envData.length);
        setRuns(runData.length);
        setRunRows(runData);
        setRunning(runData.filter((r) => ["accepted", "running", "dispatching"].includes(r.state)).length);
        setEstimatedCostUsd(nextEstimatedCostUsd);
        setCostRangeLabel(nextCostRangeLabel);
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

  const terminalRuns = useMemo(
    () => runRows.filter((run) => ["succeeded", "failed", "cancelled"].includes(run.state)),
    [runRows]
  );
  const succeededRuns = useMemo(
    () => terminalRuns.filter((run) => run.state === "succeeded").length,
    [terminalRuns]
  );
  const successRatePct = terminalRuns.length > 0 ? Math.round((succeededRuns / terminalRuns.length) * 100) : 0;

  const recentRuns = useMemo(
    () => [...runRows].sort((a, b) => parseTimestamp(b) - parseTimestamp(a)).slice(0, 5),
    [runRows]
  );

  return (
    <section className="stack">
      <div className="card">
        <h3>SparkPilot</h3>
        <p className="subtle" style={{ marginTop: 8 }}>
          Production guardrails for Spark on EKS: preflight gating, reliable dispatch telemetry, and cost-aware
          run operations.
        </p>
        <div className="button-row" style={{ marginTop: 12 }}>
          <Link href="/environments" className="button">Get Started</Link>
          <Link
            href="/runs"
            className="button"
            style={{ background: "var(--surface)", color: "var(--brand)", border: "1px solid var(--brand)" }}
          >
            Explore Run Operations
          </Link>
        </div>
      </div>

      <div className="card-grid">
        {VALUE_PILLARS.map((pillar) => (
          <article key={pillar.title} className="card">
            <h3>{pillar.title}</h3>
            <p className="subtle">{pillar.detail}</p>
          </article>
        ))}
      </div>

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
        <article className="card">
          <h3>Success Rate</h3>
          <div className="stat-value">{terminalRuns.length > 0 ? `${successRatePct}%` : "N/A"}</div>
          <div className="subtle">Terminal runs succeeded</div>
        </article>
        <article className="card">
          <h3>Estimated Cost</h3>
          <div className="stat-value">{formatUsd(estimatedCostUsd)}</div>
          <div className="subtle">Usage API summary{costRangeLabel ? ` (${costRangeLabel})` : ""}</div>
        </article>
      </div>

      {recentRuns.length > 0 ? (
        <div className="card">
          <div className="card-header-row">
            <h3>Recent Runs</h3>
            <Link href="/runs" className="inline-link">Open full run history &rarr;</Link>
          </div>
          <div className="table-wrap" style={{ marginTop: 10 }}>
            <table className="table-compact">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>State</th>
                  <th>Environment</th>
                  <th>Updated</th>
                </tr>
              </thead>
              <tbody>
                {recentRuns.map((run) => (
                  <tr key={run.id}>
                    <td>{shortId(run.id)}</td>
                    <td><span className={`badge ${run.state}`}>{run.state}</span></td>
                    <td>{shortId(run.environment_id)}</td>
                    <td>{formatTimestamp(run.updated_at ?? run.created_at ?? run.started_at ?? run.ended_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {isEmpty ? (
        <div className="card">
          <h3>Getting Started</h3>
          <p className="subtle">
            Start by provisioning an environment, then create a job and submit a run. Each run goes through
            preflight checks before dispatching to EMR on EKS.
          </p>
          <div className="button-row">
            <Link href="/environments" className="button">Create Environment</Link>
            <Link
              href="/runs"
              className="button"
              style={{ background: "var(--surface)", color: "var(--brand)", border: "1px solid var(--brand)" }}
            >
              View Runs
            </Link>
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
