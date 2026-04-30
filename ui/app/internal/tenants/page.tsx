"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { type InternalTenantListItem } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { resolveInternalTenantsListState } from "@/lib/internal-tenants-list";
import { useInternalAdmin } from "@/lib/use-internal-admin";

export default function InternalTenantsPage() {
  const { loading: gateLoading, isInternalAdmin, error: gateError } = useInternalAdmin({
    redirectIfDenied: true,
  });
  const [rows, setRows] = useState<InternalTenantListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (gateLoading || !isInternalAdmin) {
      return;
    }
    let cancelled = false;
    (async () => {
      const state = await resolveInternalTenantsListState();
      if (cancelled) {
        return;
      }
      if (state.status === "ready") {
        setRows(state.rows);
        setError(null);
      } else {
        setRows([]);
        setError(state.message);
      }
      if (!cancelled) {
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [gateLoading, isInternalAdmin]);

  if (gateLoading) {
    return (
      <section className="stack">
        <div className="card">
          <div className="subtle">Checking internal admin access...</div>
        </div>
      </section>
    );
  }

  if (gateError) {
    return (
      <section className="stack">
        <div className="card error-card">
          <strong>Access Check Failed</strong>
          <div>{gateError}</div>
        </div>
      </section>
    );
  }

  if (!isInternalAdmin) {
    return null;
  }

  return (
    <section className="stack">
      <div className="card">
        <div className="card-header-row">
          <h3>Internal Tenants</h3>
          <Link href="/internal/tenants/new" className="button button-sm">
            Provision Tenant
          </Link>
        </div>
        <div className="subtle">
          Provision and manage tenant admins from internal tooling. Customer users never see
          this surface.
        </div>
      </div>

      {loading ? (
        <div className="card">
          <div className="subtle">Loading tenants...</div>
        </div>
      ) : error ? (
        <div className="card error-card">
          <strong>Load Failed</strong>
          <div>{error}</div>
        </div>
      ) : rows.length === 0 ? (
        <div className="card">
          <strong>No tenants provisioned</strong>
          <div className="subtle" style={{ marginTop: 6 }}>
            Create the first tenant from the provision form.
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Admin Email</th>
                <th>Federation</th>
                <th>Created</th>
                <th>Last Admin Login</th>
                <th className="col-actions">Open</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.tenant_id}>
                  <td>{row.tenant_name}</td>
                  <td>{row.admin_email ?? "-"}</td>
                  <td>{row.federation_type}</td>
                  <td>{formatDate(row.created_at)}</td>
                  <td>{formatDate(row.last_login_at)}</td>
                  <td className="col-actions">
                    <Link href={`/internal/tenants/${row.tenant_id}`} className="inline-link">
                      View
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
