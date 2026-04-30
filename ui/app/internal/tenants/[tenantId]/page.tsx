"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  fetchInternalTenantDetail,
  type InternalTenantCreateResponse,
  type InternalTenantDetail,
} from "@/lib/api";
import {
  canRegenerateInvite,
  inviteStatusForUser,
  regenerateInviteWithConfirmation,
  type InviteStatus,
} from "@/lib/internal-admin-tools";
import { formatDate, friendlyError } from "@/lib/format";
import { useInternalAdmin } from "@/lib/use-internal-admin";

function _statusBadge(status: InviteStatus): JSX.Element {
  if (status === "consumed") {
    return <span className="badge badge-success">consumed</span>;
  }
  if (status === "expired") {
    return <span className="badge badge-warning">expired</span>;
  }
  return <span className="badge">pending</span>;
}

export default function InternalTenantDetailPage() {
  const params = useParams<{ tenantId: string }>();
  const tenantId = params.tenantId;
  const { loading: gateLoading, isInternalAdmin, error: gateError } = useInternalAdmin({
    redirectIfDenied: true,
  });

  const [detail, setDetail] = useState<InternalTenantDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InternalTenantCreateResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [regeneratingUserId, setRegeneratingUserId] = useState<string | null>(null);

  async function loadDetail(): Promise<void> {
    try {
      const payload = await fetchInternalTenantDetail(tenantId);
      setDetail(payload);
      setError(null);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to load tenant detail"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (gateLoading || !isInternalAdmin) {
      return;
    }
    setLoading(true);
    setDetail(null);
    setError(null);
    void loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateLoading, isInternalAdmin, tenantId]);

  const usersWithStatus = useMemo(() => {
    if (!detail) {
      return [];
    }
    return detail.users.map((user) => ({
      ...user,
      inviteStatus: inviteStatusForUser(user),
    }));
  }, [detail]);

  async function onRegenerate(userId: string, userEmail: string): Promise<void> {
    setActionError(null);
    setRegeneratingUserId(userId);
    try {
      const invite = await regenerateInviteWithConfirmation(
        tenantId,
        userId,
        userEmail,
        (message) => window.confirm(message),
      );
      if (invite) {
        setResult(invite);
        await loadDetail();
      }
    } catch (err: unknown) {
      setActionError(friendlyError(err, "Invite regeneration failed"));
    } finally {
      setRegeneratingUserId(null);
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

  if (!isInternalAdmin) {
    return null;
  }

  if (loading) {
    return (
      <section className="stack">
        <div className="card">
          <div className="subtle">Loading tenant detail...</div>
        </div>
      </section>
    );
  }

  if (error || !detail) {
    return (
      <section className="stack">
        <div className="card error-card">
          <strong>Tenant Detail Failed</strong>
          <div>{error ?? "Tenant not found."}</div>
        </div>
      </section>
    );
  }

  return (
    <section className="stack">
      <div className="card">
        <div className="card-header-row">
          <h3>{detail.tenant_name}</h3>
          <Link href="/internal/tenants" className="inline-link">
            Back to tenant list
          </Link>
        </div>
        <div className="subtle">
          Federation: <code>{detail.federation_type}</code>
        </div>
        <div className="subtle">Created: {formatDate(detail.created_at)}</div>
      </div>

      {actionError ? (
        <div className="card error-card">
          <strong>Action Failed</strong>
          <div>{actionError}</div>
        </div>
      ) : null}

      <div className="card">
        <h3>Users</h3>
        {usersWithStatus.length === 0 ? (
          <div className="subtle">No users found for this tenant.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Last Login</th>
                  <th>Invite Status</th>
                  <th className="col-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {usersWithStatus.map((user) => (
                  <tr key={user.id}>
                    <td>{user.email}</td>
                    <td>{user.role}</td>
                    <td>{formatDate(user.last_login_at)}</td>
                    <td>{_statusBadge(user.inviteStatus)}</td>
                    <td className="col-actions">
                      {canRegenerateInvite(user.inviteStatus) ? (
                        <button
                          type="button"
                          className="button button-sm"
                          disabled={regeneratingUserId === user.id}
                          onClick={() => void onRegenerate(user.id, user.email)}
                        >
                          {regeneratingUserId === user.id ? "Regenerating..." : "Regenerate Invite"}
                        </button>
                      ) : (
                        <span className="subtle">-</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {result ? (
        <div className="card">
          <h3>
            {result.invite_email_status === "sent" ? "Invite Email Sent" : "Invite Email Failed"}
          </h3>
          <div className="subtle">
            {result.invite_email_status === "sent"
              ? `A fresh invite was sent to ${result.invite_email_recipient}.`
              : (result.invite_email_failure_detail
                ?? "The invite was regenerated, but the email was not sent.")}
          </div>
          <div className="button-row">
            <button
              type="button"
              className="button button-sm"
              onClick={() => {
                setResult(null);
              }}
            >
              Close
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
