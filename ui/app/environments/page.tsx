"use client";

import { Fragment } from "react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Environment, fetchEnvironments } from "@/lib/api";
import { badgeClass } from "@/lib/badge";
import { friendlyError } from "@/lib/format";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";
import EnvironmentCreateForm from "./environment-create-form";

export default function EnvironmentsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 10 });

  async function loadEnvironments() {
    try {
      const rows = await fetchEnvironments();
      setEnvironments(rows);
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

  const visible = paginate(environments, pg);

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

      {loading ? (
        <div className="card">
          <div className="subtle">Loading environments...</div>
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
                      onClick={() => setExpandedId(expandedId === env.id ? null : env.id)}
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
                              <span>{new Date(env.created_at).toLocaleDateString()}</span>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
                {environments.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="subtle">
                      No environments available.
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <PaginationControls total={environments.length} state={pg} onChange={setPg} />
        </>
      )}
    </section>
  );
}

