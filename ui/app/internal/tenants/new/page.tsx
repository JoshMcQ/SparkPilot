"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { type InternalTenantCreateResponse } from "@/lib/api";
import { friendlyError } from "@/lib/format";
import { provisionTenantFromForm, type ProvisionTenantFormInput } from "@/lib/internal-admin-tools";
import { useInternalAdmin } from "@/lib/use-internal-admin";

const INITIAL_FORM: ProvisionTenantFormInput = {
  name: "",
  admin_email: "",
  federation_type: "cognito_password",
  idp_metadata_text: "",
};

function _metadataHelp(federation: ProvisionTenantFormInput["federation_type"]): string {
  if (federation === "saml") {
    return 'Optional JSON blob for SAML metadata, e.g. {"entity_id":"...","sso_url":"..."}';
  }
  if (federation === "oidc") {
    return 'Optional JSON blob for OIDC metadata, e.g. {"issuer":"...","client_id":"..."}';
  }
  return "";
}

export default function ProvisionInternalTenantPage() {
  const { loading: gateLoading, isInternalAdmin, error: gateError } = useInternalAdmin({
    redirectIfDenied: true,
  });
  const [form, setForm] = useState<ProvisionTenantFormInput>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InternalTenantCreateResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const showMetadata = form.federation_type !== "cognito_password";
  const metadataHelp = useMemo(
    () => _metadataHelp(form.federation_type),
    [form.federation_type],
  );

  async function onSubmit(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setCopied(false);
    try {
      const payload = await provisionTenantFromForm(form);
      setResult(payload);
    } catch (err: unknown) {
      setError(friendlyError(err, "Tenant provisioning failed"));
    } finally {
      setSubmitting(false);
    }
  }

  async function onCopyMagicLink(): Promise<void> {
    if (!result) {
      return;
    }
    await navigator.clipboard.writeText(result.magic_link_url);
    setCopied(true);
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

  return (
    <section className="stack">
      <div className="card">
        <div className="card-header-row">
          <h3>Provision Tenant</h3>
          <Link href="/internal/tenants" className="inline-link">
            Back to tenant list
          </Link>
        </div>
        <div className="subtle">Create a tenant and generate a manual admin invite link.</div>
      </div>

      <form className="card" onSubmit={(event) => void onSubmit(event)}>
        <div className="form-grid">
          <label>
            Tenant Name
            <input
              value={form.name}
              minLength={3}
              maxLength={255}
              required
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
            />
          </label>
          <label>
            Admin Email
            <input
              type="email"
              value={form.admin_email}
              required
              onChange={(event) =>
                setForm((prev) => ({ ...prev, admin_email: event.target.value }))
              }
            />
          </label>
          <label>
            Federation Type
            <select
              value={form.federation_type}
              onChange={(event) =>
                setForm((prev) => ({
                  ...prev,
                  federation_type: event.target.value as ProvisionTenantFormInput["federation_type"],
                }))
              }
            >
              <option value="cognito_password">cognito_password</option>
              <option value="saml">saml</option>
              <option value="oidc">oidc</option>
            </select>
          </label>
          {showMetadata ? (
            <label style={{ gridColumn: "1 / -1" }}>
              IdP Metadata (optional JSON)
              <textarea
                rows={6}
                value={form.idp_metadata_text}
                placeholder={metadataHelp}
                onChange={(event) =>
                  setForm((prev) => ({ ...prev, idp_metadata_text: event.target.value }))
                }
              />
            </label>
          ) : null}
        </div>
        <div className="button-row">
          <button type="submit" className="button" disabled={submitting}>
            {submitting ? "Provisioning..." : "Provision Tenant"}
          </button>
        </div>
        {error ? <div className="error-text">{error}</div> : null}
      </form>

      {result ? (
        <div className="card">
          <h3>Magic Link Ready</h3>
          <div className="subtle">
            Copy this URL and send it manually to the tenant admin.
          </div>
          <pre className="code-block">{result.magic_link_url}</pre>
          <div className="button-row">
            <button type="button" className="button button-sm" onClick={() => void onCopyMagicLink()}>
              Copy
            </button>
            <button
              type="button"
              className="button button-sm button-secondary"
              onClick={() => {
                setResult(null);
                setForm(INITIAL_FORM);
              }}
            >
              Provision Another
            </button>
          </div>
          {copied ? <div className="success-text">Copied to clipboard.</div> : null}
        </div>
      ) : null}
    </section>
  );
}
