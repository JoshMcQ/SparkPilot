"use client";

import { Fragment } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Environment, deleteEnvironment, fetchEnvironments, retryEnvironmentProvisioning } from "@/lib/api";
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
      <EnvironmentCreateForm />
      <div className="card">
        <h3>Tenant Environments</h3>
        <div className="subtle">
          BYOC-Lite uses an existing EKS namespace. Full mode is hidden in UI for this deployment until full-BYOC
          infrastructure is explicitly enabled.
        </div>
      </div>

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
    </section>
  );
}

