"use client";

import { useEffect, useState } from "react";

import {
  type ContactSubmission,
  type ContactSubmissionApproveResponse,
  approveContactSubmission,
  fetchContactSubmissions,
  rejectContactSubmission,
} from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useInternalAdmin } from "@/lib/use-internal-admin";

type StatusFilter = "all" | "pending" | "approved" | "rejected";

type ApprovingState = {
  submission: ContactSubmission;
  tenantName: string;
  working: boolean;
  error: string | null;
};

function StatusBadge({ status }: { status: ContactSubmission["status"] }) {
  if (status === "pending") return <span className="badge badge-warning">Pending</span>;
  if (status === "approved") return <span className="badge badge-success">Approved</span>;
  return <span className="badge badge-muted">Rejected</span>;
}

export default function InternalContactPage() {
  const { loading: gateLoading, isInternalAdmin, error: gateError } = useInternalAdmin({
    redirectIfDenied: true,
  });
  const [rows, setRows] = useState<ContactSubmission[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("pending");
  const [approving, setApproving] = useState<ApprovingState | null>(null);
  const [lastResult, setLastResult] = useState<ContactSubmissionApproveResponse | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);

  async function load(filter: StatusFilter) {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchContactSubmissions(filter === "all" ? undefined : filter);
      setRows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load submissions.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (gateLoading || !isInternalAdmin) return;
    load(statusFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateLoading, isInternalAdmin, statusFilter]);

  async function handleApproveConfirm() {
    if (!approving) return;
    const name = approving.tenantName.trim();
    if (!name || name.length < 3) return;
    setApproving((a) => a && { ...a, working: true, error: null });
    try {
      const result = await approveContactSubmission(approving.submission.id, name);
      setLastResult(result);
      setApproving(null);
      setRows((prev) =>
        prev.map((r) =>
          r.id === approving.submission.id ? { ...r, status: "approved" } : r,
        ),
      );
    } catch (err) {
      setApproving((a) =>
        a && { ...a, working: false, error: err instanceof Error ? err.message : "Approval failed." },
      );
    }
  }

  async function handleReject(id: string) {
    if (!window.confirm("Reject this submission? This cannot be undone.")) return;
    setRejectingId(id);
    try {
      await rejectContactSubmission(id);
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, status: "rejected" } : r)));
    } catch (err) {
      alert(err instanceof Error ? err.message : "Rejection failed.");
    } finally {
      setRejectingId(null);
    }
  }

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

  if (!isInternalAdmin) return null;

  return (
    <section className="stack">
      {/* Success/result banner after approval */}
      {lastResult && (
        <div className={lastResult.invite_email_status === "sent" ? "card" : "card error-card"}>
          <div className="card-header-row">
            <strong>
              {lastResult.invite_email_status === "sent"
                ? "Tenant provisioned — invite sent"
                : "Tenant provisioned — invite email failed"}
            </strong>
            <button type="button" className="button button-sm" onClick={() => setLastResult(null)}>
              Dismiss
            </button>
          </div>
          <div className="subtle" style={{ marginTop: 6 }}>
            Tenant: <code>{lastResult.tenant_id}</code>
            {lastResult.invite_email_status === "failed" && lastResult.invite_email_failure_detail && (
              <> — {lastResult.invite_email_failure_detail}</>
            )}
          </div>
        </div>
      )}

      {/* Header / filter */}
      <div className="card">
        <div className="card-header-row">
          <h3>Leads</h3>
          <div style={{ display: "flex", gap: 8 }}>
            {(["pending", "approved", "rejected", "all"] as StatusFilter[]).map((f) => (
              <button
                key={f}
                type="button"
                className="button button-sm"
                style={statusFilter === f ? { fontWeight: 700 } : undefined}
                onClick={() => {
                  setApproving(null);
                  setStatusFilter(f);
                }}
              >
                {f.charAt(0).toUpperCase() + f.slice(1)}
              </button>
            ))}
          </div>
        </div>
        <div className="subtle">
          Contact form submissions from the public site. Approve to provision a tenant and send the
          Cognito invite email.
        </div>
      </div>

      {/* Approve inline form */}
      {approving && (
        <div className="card">
          <div className="card-header-row">
            <h4 style={{ margin: 0 }}>
              Approve: <strong>{approving.submission.name}</strong> &lt;{approving.submission.email}&gt;
            </h4>
            <button
              type="button"
              className="button button-sm"
              onClick={() => setApproving(null)}
              disabled={approving.working}
            >
              Cancel
            </button>
          </div>
          <div className="subtle" style={{ margin: "8px 0 12px" }}>
            This will create a tenant and send a Cognito invite email to{" "}
            <strong>{approving.submission.email}</strong>. Set the tenant name below, then confirm.
          </div>
          <div className="form-group" style={{ maxWidth: 400 }}>
            <label className="form-label" htmlFor="approve-tenant-name">
              Tenant name
            </label>
            <input
              id="approve-tenant-name"
              type="text"
              className="form-input"
              value={approving.tenantName}
              onChange={(e) => setApproving((a) => a && { ...a, tenantName: e.target.value })}
              disabled={approving.working}
              minLength={3}
              maxLength={255}
              autoFocus
            />
          </div>
          {approving.error && (
            <div className="error-text" style={{ marginTop: 8 }}>
              {approving.error}
            </div>
          )}
          <div className="button-row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="button"
              onClick={handleApproveConfirm}
              disabled={approving.working || approving.tenantName.trim().length < 3}
            >
              {approving.working ? "Provisioning…" : "Provision & Send Invite"}
            </button>
          </div>
        </div>
      )}

      {/* Submissions table */}
      {loading ? (
        <div className="card">
          <div className="subtle">Loading...</div>
        </div>
      ) : error ? (
        <div className="card error-card">
          <strong>Load Failed</strong>
          <div>{error}</div>
        </div>
      ) : rows.length === 0 ? (
        <div className="card">
          <strong>No {statusFilter === "all" ? "" : statusFilter} submissions</strong>
          <div className="subtle" style={{ marginTop: 6 }}>
            {statusFilter === "pending"
              ? "No pending leads yet. Share the contact form to get started."
              : "Nothing to show here."}
          </div>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Email</th>
                <th>Company</th>
                <th>Use Case</th>
                <th>Message</th>
                <th>Status</th>
                <th>Submitted</th>
                <th className="col-actions">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>{row.email}</td>
                  <td>{row.company ?? "—"}</td>
                  <td>{row.use_case ?? "—"}</td>
                  <td style={{ maxWidth: 220, fontSize: "0.85em", whiteSpace: "pre-wrap" }}>
                    {row.message
                      ? row.message.length > 140
                        ? row.message.slice(0, 140) + "…"
                        : row.message
                      : "—"}
                  </td>
                  <td>
                    <StatusBadge status={row.status} />
                  </td>
                  <td>{formatDate(row.created_at)}</td>
                  <td className="col-actions">
                    {row.status === "pending" ? (
                      <span style={{ display: "flex", gap: 6 }}>
                        <button
                          type="button"
                          className="button button-sm"
                          disabled={!!approving}
                          onClick={() =>
                            setApproving({
                              submission: row,
                              tenantName: row.company ?? row.name,
                              working: false,
                              error: null,
                            })
                          }
                        >
                          Approve
                        </button>
                        <button
                          type="button"
                          className="button button-sm button-danger"
                          disabled={rejectingId === row.id || !!approving}
                          onClick={() => handleReject(row.id)}
                        >
                          {rejectingId === row.id ? "…" : "Reject"}
                        </button>
                      </span>
                    ) : row.status === "approved" && row.tenant_id ? (
                      <span className="subtle" style={{ fontSize: "0.85em" }}>
                        {row.tenant_id.slice(0, 8)}…
                      </span>
                    ) : (
                      <span className="subtle">—</span>
                    )}
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
