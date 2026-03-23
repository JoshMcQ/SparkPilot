"use client";

import { Fragment, useMemo } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Environment, EmrRelease, EmrReleaseLifecycleStatus, deleteEnvironment, fetchEnvironments, fetchEmrReleases, retryEnvironmentProvisioning } from "@/lib/api";
import { badgeClass } from "@/lib/badge";
import { friendlyError } from "@/lib/format";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";
import EnvironmentCreateForm from "./environment-create-form";

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return "-";
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return value;
  return new Date(parsed).toLocaleString();
}

function lifecycleBadge(status: EmrReleaseLifecycleStatus) {
  if (status === "current") return <span className="badge badge-success">Current</span>;
  if (status === "deprecated") return <span className="badge badge-warning">Deprecated</span>;
  return <span className="badge badge-danger">End of Life</span>;
}

function EmrReleasesSection() {
  const [releases, setReleases] = useState<EmrRelease[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    fetchEmrReleases({ limit: 100 })
      .then(setReleases)
      .catch((err: unknown) => setError(friendlyError(err, "Failed to load EMR releases")))
      .finally(() => setLoading(false));
  }, []);

  const warnCount = releases.filter((r) => r.lifecycle_status !== "current").length;
  const visible = useMemo(() => {
    if (showAll) return releases;
    const nonCurrent = releases.filter((r) => r.lifecycle_status !== "current");
    const currentSlice = releases.filter((r) => r.lifecycle_status === "current").slice(0, 10);
    return [...nonCurrent, ...currentSlice];
  }, [showAll, releases]);

  return (
    <div className="card">
      <div className="card-header-row">
        <h3>EMR Release Lifecycle</h3>
        {warnCount > 0 ? (
          <span className="badge badge-warning">{warnCount} deprecated or EOL</span>
        ) : null}
      </div>
      <div className="subtle">
        SparkPilot syncs EMR release label lifecycle status from AWS. Deprecated and end-of-life labels are blocked or warned depending on your policy configuration.
      </div>
      {loading ? (
        <div className="subtle" style={{ marginTop: 8 }}>Loading EMR releases...</div>
      ) : error ? (
        <div className="error-text" style={{ marginTop: 8 }}>{error}</div>
      ) : releases.length === 0 ? (
        <div className="subtle" style={{ marginTop: 8 }}>No EMR release data synced yet. Releases are populated by the SparkPilot worker on first connect.</div>
      ) : (
        <>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table>
              <thead>
                <tr>
                  <th>Release Label</th>
                  <th>Status</th>
                  <th>Graviton</th>
                  <th>Lake Formation</th>
                  <th className="col-hide-mobile">Upgrade Target</th>
                  <th className="col-hide-mobile">Last Synced</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((rel) => (
                  <tr key={rel.id} className={rel.lifecycle_status === "end_of_life" ? "row-warn" : undefined}>
                    <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{rel.release_label}</td>
                    <td>{lifecycleBadge(rel.lifecycle_status)}</td>
                    <td>{rel.graviton_supported ? <span className="badge badge-success">Yes</span> : <span className="badge">No</span>}</td>
                    <td>{rel.lake_formation_supported ? <span className="badge badge-success">Yes</span> : <span className="badge">No</span>}</td>
                    <td className="col-hide-mobile">
                      {rel.upgrade_target ? (
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}>{rel.upgrade_target}</span>
                      ) : (
                        <span className="subtle">—</span>
                      )}
                    </td>
                    <td className="col-hide-mobile">
                      {rel.last_synced_at ? new Date(rel.last_synced_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {showAll || visible.length < releases.length ? (
            <div className="button-row" style={{ marginTop: 8 }}>
              <button type="button" className="button button-secondary button-sm" onClick={() => setShowAll((v) => !v)}>
                {showAll ? "Show fewer" : `Show all ${releases.length} releases`}
              </button>
            </div>
          ) : null}
        </>
      )}
    </div>
  );
}

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 10 });

  async function loadEnvironments() {
    try {
      const rows = await fetchEnvironments();
      setEnvironments(rows.filter((row) => row.status !== "deleted"));
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to load environments"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadEnvironments();
  }, []);

  useEffect(() => {
    const hasActiveProvisioning = environments.some((env) =>
      ["provisioning", "upgrading", "deleting"].includes(env.status)
    );
    if (!hasActiveProvisioning) {
      return;
    }
    const id = setInterval(() => {
      void loadEnvironments();
    }, 5000);
    return () => clearInterval(id);
  }, [environments]);

  async function handleRetry(environmentId: string) {
    setRetryingId(environmentId);
    setActionError(null);
    setActionMessage(null);
    try {
      const op = await retryEnvironmentProvisioning(environmentId);
      setActionMessage(`Retry queued for ${environmentId}. operation_id=${op.id}`);
      await loadEnvironments();
    } catch (err: unknown) {
      setActionError(friendlyError(err, "Retry failed"));
    } finally {
      setRetryingId(null);
    }
  }

  async function handleDelete(environmentId: string) {
    const confirmed = window.confirm("Delete this environment? This is blocked if runs are active.");
    if (!confirmed) {
      return;
    }
    setDeletingId(environmentId);
    setActionError(null);
    setActionMessage(null);
    try {
      await deleteEnvironment(environmentId);
      setActionMessage(`Environment ${environmentId} deleted.`);
      await loadEnvironments();
    } catch (err: unknown) {
      setActionError(friendlyError(err, "Delete failed"));
    } finally {
      setDeletingId(null);
    }
  }

  const visible = paginate(environments, pg);
  const isEmpty = environments.length === 0;

  return (
    <section className="stack">
      <div className="card">
        <div className="card-header-row">
          <h3>Tenant Environments</h3>
          <Link href="/onboarding/aws" className="inline-link">Open AWS onboarding →</Link>
        </div>
        <div className="subtle">
          BYOC-Lite uses an existing EKS namespace. Full mode is hidden in UI for this deployment until full-BYOC
          infrastructure is explicitly enabled.
        </div>
      </div>
      <EnvironmentCreateForm />

      {error ? (
        <div className="card error-card">
          <strong>Error</strong>
          <div>{error}</div>
        </div>
      ) : null}
      {actionError ? (
        <div className="card error-card">
          <strong>Action Failed</strong>
          <div>{actionError}</div>
        </div>
      ) : null}
      {actionMessage ? (
        <div className="card">
          <div className="success-text">{actionMessage}</div>
        </div>
      ) : null}

      {loading ? (
        <div className="card">
          <div className="subtle">Loading environments...</div>
        </div>
      ) : isEmpty ? (
        <div className="card">
          <strong>No environments yet</strong>
          <div className="subtle" style={{ marginTop: 6 }}>
            Start by creating a BYOC-Lite environment above. Once created, it will appear here with mode, status, and namespace details.
          </div>
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <table className="table-compact">
              <thead>
                <tr>
                  <th>Environment</th>
                  <th>Mode</th>
                  <th>Region / Namespace</th>
                  <th>Status</th>
                  <th className="col-actions">Detail</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((env) => (
                  <Fragment key={env.id}>
                    <tr
                      className={expandedId === env.id ? "row-selected row-expandable" : "row-expandable"}
                      tabIndex={0}
                      aria-expanded={expandedId === env.id}
                      onClick={() => setExpandedId(expandedId === env.id ? null : env.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          setExpandedId(expandedId === env.id ? null : env.id);
                        }
                      }}
                    >
                      <td><ShortId value={env.id} /></td>
                      <td>
                        <span className={badgeClass(env.provisioning_mode)}>{env.provisioning_mode}</span>
                      </td>
                      <td>
                        {env.region} / {env.eks_namespace ?? "-"}
                      </td>
                      <td>
                        <span className={badgeClass(env.status)}>{env.status}</span>
                      </td>
                      <td className="col-actions">
                        <Link className="inline-link" href={`/environments/${env.id}`} onClick={(e) => e.stopPropagation()}>
                          Open
                        </Link>
                      </td>
                    </tr>
                    {expandedId === env.id && (
                      <tr className="row-detail">
                        <td colSpan={5}>
                          <div className="detail-grid">
                            <div className="detail-item">
                              <span className="detail-label">Tenant</span>
                              <ShortId value={env.tenant_id} />
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">EMR Virtual Cluster</span>
                              <ShortId value={env.emr_virtual_cluster_id} />
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Max Concurrent Runs</span>
                              <span>{env.max_concurrent_runs}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Max vCPU</span>
                              <span>{env.max_vcpu}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Max Run Seconds</span>
                              <span>{env.max_run_seconds.toLocaleString()}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Warm Pool</span>
                              <span>{env.warm_pool_enabled ? "Enabled" : "Disabled"}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Cloud / Engine</span>
                              <span>{env.cloud} / {env.engine}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Created</span>
                              <span>{formatTimestamp(env.created_at)}</span>
                            </div>
                            <div className="detail-item">
                              <span className="detail-label">Updated</span>
                              <span>{formatTimestamp(env.updated_at)}</span>
                            </div>
                          </div>
                          <div className="button-row" style={{ marginTop: 10 }}>
                            {env.status === "failed" ? (
                              <button
                                type="button"
                                className="button button-secondary"
                                disabled={retryingId === env.id}
                                onClick={() => void handleRetry(env.id)}
                              >
                                {retryingId === env.id ? "Retrying..." : "Retry Provisioning"}
                              </button>
                            ) : null}
                            <button
                              type="button"
                              className="button button-danger"
                              disabled={deletingId === env.id}
                              onClick={() => void handleDelete(env.id)}
                            >
                              {deletingId === env.id ? "Deleting..." : "Delete Environment"}
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          <PaginationControls total={environments.length} state={pg} onChange={setPg} />
        </>
      )}
      <EmrReleasesSection />
    </section>
  );
}

