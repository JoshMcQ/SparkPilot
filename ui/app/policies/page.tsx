"use client";

import { useEffect, useState, useMemo } from "react";
import {
  Policy,
  PolicyCreateRequest,
  PolicyEnforcement,
  PolicyRuleType,
  PolicyScope,
  createPolicy,
  deletePolicy,
  fetchEnvironments,
  fetchPolicies,
  fetchTeams,
  Environment,
  Team,
} from "@/lib/api";
import { ShortId } from "@/components/short-id";
import { friendlyError } from "@/lib/format";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";

// ---------------------------------------------------------------------------
// Human-readable labels
// ---------------------------------------------------------------------------

const RULE_TYPE_LABELS: Record<PolicyRuleType, string> = {
  max_runtime_seconds: "Max runtime (seconds)",
  max_vcpu: "Max vCPU per run",
  max_memory_gb: "Max memory per run (GB)",
  required_tags: "Required Spark tags",
  allowed_golden_paths: "Allowed golden paths",
  allowed_release_labels: "Allowed EMR release labels",
  allowed_instance_types: "Allowed instance types",
  allowed_security_configurations: "Allowed security configurations",
};

const RULE_TYPE_DESCRIPTIONS: Record<PolicyRuleType, string> = {
  max_runtime_seconds:
    "Reject or warn on runs whose estimated or actual runtime exceeds this limit.",
  max_vcpu:
    "Reject or warn on runs requesting more vCPU than this threshold.",
  max_memory_gb:
    "Reject or warn on runs requesting more memory than this threshold.",
  required_tags:
    "Require specific Spark tags (e.g. cost_center, project) on every submission.",
  allowed_golden_paths:
    "Restrict submissions to a specific set of job template golden paths.",
  allowed_release_labels:
    "Allow only specific EMR release labels (e.g. emr-7.2.0). Blocks deprecated or EOL releases.",
  allowed_instance_types:
    "Allow only specific EC2 instance types for executor nodes.",
  allowed_security_configurations:
    "Restrict submissions to environments with specific EMR security configurations.",
};

const RULE_TYPE_CONFIG_HINT: Record<PolicyRuleType, string> = {
  max_runtime_seconds: '{"limit": 3600}',
  max_vcpu: '{"limit": 64}',
  max_memory_gb: '{"limit": 256}',
  required_tags: '{"tags": ["cost_center", "project"]}',
  allowed_golden_paths: '{"paths": ["graviton-spot", "standard"]}',
  allowed_release_labels: '{"labels": ["emr-7.2.0", "emr-7.7.0"]}',
  allowed_instance_types: '{"types": ["m7g.xlarge", "m7g.2xlarge"]}',
  allowed_security_configurations: '{"config_ids": ["<security-config-id>"]}',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function enforcementBadge(enforcement: PolicyEnforcement, active: boolean) {
  if (!active) return <span className="badge">Inactive</span>;
  if (enforcement === "hard")
    return <span className="badge badge-danger">Hard block</span>;
  return <span className="badge badge-warning">Soft warn</span>;
}

function scopeLabel(scope: PolicyScope, scopeId: string | null): string {
  if (scope === "global") return "Global";
  if (scope === "tenant") return `Tenant ${scopeId ? scopeId.slice(0, 8) : "—"}`;
  return `Environment ${scopeId ? scopeId.slice(0, 8) : "—"}`;
}

function configSummary(ruleType: PolicyRuleType, config: Record<string, unknown>): string {
  try {
    if (ruleType === "max_runtime_seconds" || ruleType === "max_vcpu" || ruleType === "max_memory_gb") {
      return `limit: ${config.limit}`;
    }
    if (ruleType === "required_tags") {
      const tags = config.tags;
      return Array.isArray(tags) && tags.length > 0 ? tags.map(String).join(", ") : "—";
    }
    if (ruleType === "allowed_golden_paths") {
      const paths = config.paths;
      return Array.isArray(paths) && paths.length > 0 ? paths.map(String).join(", ") : "—";
    }
    if (ruleType === "allowed_release_labels") {
      const labels = config.labels;
      return Array.isArray(labels) && labels.length > 0 ? labels.map(String).join(", ") : "—";
    }
    if (ruleType === "allowed_instance_types") {
      const types = config.types;
      return Array.isArray(types) && types.length > 0 ? types.map(String).join(", ") : "—";
    }
    return JSON.stringify(config);
  } catch {
    return "—";
  }
}

// ---------------------------------------------------------------------------
// Create form
// ---------------------------------------------------------------------------

const EMPTY_FORM: PolicyCreateRequest = {
  name: "",
  scope: "global",
  scope_id: null,
  rule_type: "max_vcpu",
  config: {},
  enforcement: "hard",
  active: true,
};

function CreatePolicyForm({
  environments,
  teams,
  onCreated,
}: {
  environments: Environment[];
  teams: Team[];
  onCreated: (policy: Policy) => void;
}) {
  const [form, setForm] = useState<PolicyCreateRequest>(EMPTY_FORM);
  const [configRaw, setConfigRaw] = useState<string>('{"limit": 64}');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [configError, setConfigError] = useState<string | null>(null);
  const uniqueTenants = useMemo(
    () => Array.from(new Map(teams.map((t) => [t.tenant_id, t])).values()),
    [teams]
  );

  function handleRuleTypeChange(rt: PolicyRuleType) {
    setForm((f) => ({ ...f, rule_type: rt }));
    setConfigRaw(RULE_TYPE_CONFIG_HINT[rt]);
    setConfigError(null);
  }

  function validateConfig(): Record<string, unknown> | null {
    try {
      const parsed = JSON.parse(configRaw);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        setConfigError("Config must be a JSON object");
        return null;
      }
      setConfigError(null);
      return parsed;
    } catch {
      setConfigError("Invalid JSON");
      return null;
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const config = validateConfig();
    if (!config) return;
    if (form.scope !== "global" && !form.scope_id) {
      setError(`A ${form.scope} must be selected when scope is not global.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await createPolicy({ ...form, config });
      onCreated(created);
      setForm(EMPTY_FORM);
      setConfigRaw('{"limit": 64}');
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to create policy"));
    } finally {
      setBusy(false);
    }
  }

  const selectedRuleType = form.rule_type;

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-grid">
        <label>
          Policy name
          <input
            type="text"
            value={form.name}
            onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            placeholder="e.g. max-vcpu-per-run"
            required
            minLength={1}
            maxLength={255}
          />
        </label>

        <label>
          Rule type
          <select
            value={form.rule_type}
            onChange={(e) => handleRuleTypeChange(e.target.value as PolicyRuleType)}
          >
            {(Object.keys(RULE_TYPE_LABELS) as PolicyRuleType[]).map((rt) => (
              <option key={rt} value={rt}>
                {RULE_TYPE_LABELS[rt]}
              </option>
            ))}
          </select>
        </label>

        <label>
          Enforcement
          <select
            value={form.enforcement}
            onChange={(e) => setForm((f) => ({ ...f, enforcement: e.target.value as PolicyEnforcement }))}
          >
            <option value="hard">Hard block — reject submission</option>
            <option value="soft">Soft warn — allow with warning</option>
          </select>
        </label>

        <label>
          Scope
          <select
            value={form.scope}
            onChange={(e) => {
              const scope = e.target.value as PolicyScope;
              setForm((f) => ({ ...f, scope, scope_id: null }));
            }}
          >
            <option value="global">Global — applies to all tenants</option>
            <option value="tenant">Tenant — applies to one tenant</option>
            <option value="environment">Environment — applies to one environment</option>
          </select>
        </label>

        {form.scope === "tenant" ? (
          <label>
            Tenant (select via team)
            <select
              value={form.scope_id ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, scope_id: e.target.value || null }))}
            >
              <option value="">Select tenant</option>
              {uniqueTenants.map((t) => (
                <option key={t.tenant_id} value={t.tenant_id}>
                  {t.tenant_id.slice(0, 8)} ({t.name})
                </option>
              ))}
            </select>
          </label>
        ) : null}

        {form.scope === "environment" ? (
          <label>
            Environment
            <select
              value={form.scope_id ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, scope_id: e.target.value || null }))}
            >
              <option value="">Select environment</option>
              {environments.map((env) => (
                <option key={env.id} value={env.id}>
                  {env.region} / {env.eks_namespace ?? env.provisioning_mode} ({env.id.slice(0, 8)})
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>

      <div className="subtle" style={{ marginTop: 8, marginBottom: 4 }}>
        {RULE_TYPE_DESCRIPTIONS[selectedRuleType]}
      </div>

      <label style={{ display: "block", marginTop: 8 }}>
        Config (JSON)
        <textarea
          value={configRaw}
          onChange={(e) => {
            setConfigRaw(e.target.value);
            setConfigError(null);
          }}
          rows={3}
          placeholder={RULE_TYPE_CONFIG_HINT[selectedRuleType]}
          style={{ fontFamily: "var(--font-mono)", fontSize: "0.85rem" }}
        />
        {configError ? <div className="error-text">{configError}</div> : null}
      </label>

      <div className="button-row" style={{ marginTop: 12 }}>
        <button type="submit" className="button" disabled={busy}>
          {busy ? "Creating..." : "Create policy"}
        </button>
      </div>
      {error ? <div className="error-text">{error}</div> : null}
    </form>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

const POLICY_WORKFLOW = [
  "Policies are evaluated at preflight before every run submission.",
  "Hard-block policies reject the submission with a clear error and the policy name.",
  "Soft-warn policies allow the submission but record the warning in the run audit trail.",
  "Policies apply to all scopes below them: a global policy applies everywhere; a tenant policy applies to all environments in that tenant.",
  "The policy engine is active in production. Creating a hard-block policy with an incorrect config will block real submissions.",
];

export default function PoliciesPage() {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 15 });
  const [deleting, setDeleting] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([fetchPolicies({ limit: 200 }), fetchEnvironments(), fetchTeams()])
      .then(([pols, envs, tms]) => {
        setPolicies(pols);
        setEnvironments(envs);
        setTeams(tms);
      })
      .catch((err: unknown) => setError(friendlyError(err, "Failed to load policies")))
      .finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: string) {
    if (!confirm("Delete this policy? This removes it immediately and stops future enforcement.")) return;
    setDeleting(id);
    try {
      await deletePolicy(id);
      setPolicies((prev) => prev.filter((p) => p.id !== id));
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to delete policy"));
    } finally {
      setDeleting(null);
    }
  }

  const page = paginate(policies, pg);

  return (
    <section className="stack">
      <div className="card">
        <h3>Policy Engine</h3>
        <div className="subtle">
          Submission guardrails evaluated at preflight before every run. Hard-block policies reject
          submissions; soft-warn policies allow with a warning recorded in the audit trail.
        </div>
      </div>

      <div className="card">
        <h3>How policies work</h3>
        <ol className="preflight-list">
          {POLICY_WORKFLOW.map((step, i) => (
            <li key={i} className="subtle">{step}</li>
          ))}
        </ol>
      </div>

      <div className="card">
        <h3>Create policy</h3>
        <CreatePolicyForm
          environments={environments}
          teams={teams}
          onCreated={(p) => {
            setPolicies((prev) => [p, ...prev]);
            setPg({ page: 0, pageSize: pg.pageSize });
          }}
        />
      </div>

      <div className="card">
        <h3>Active policies</h3>
        {loading ? (
          <div className="subtle">Loading policies...</div>
        ) : error ? (
          <div className="error-text">{error}</div>
        ) : policies.length === 0 ? (
          <div className="subtle">No policies configured. All submissions pass by default.</div>
        ) : (
          <>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Rule type</th>
                    <th>Config</th>
                    <th>Scope</th>
                    <th>Enforcement</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {page.map((pol) => (
                    <tr key={pol.id}>
                      <td><ShortId value={pol.id} /></td>
                      <td>{pol.name}</td>
                      <td>
                        <span title={RULE_TYPE_DESCRIPTIONS[pol.rule_type as PolicyRuleType]}>
                          {RULE_TYPE_LABELS[pol.rule_type as PolicyRuleType] ?? pol.rule_type}
                        </span>
                      </td>
                      <td style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                        {configSummary(pol.rule_type as PolicyRuleType, pol.config)}
                      </td>
                      <td>{scopeLabel(pol.scope as PolicyScope, pol.scope_id)}</td>
                      <td>{enforcementBadge(pol.enforcement as PolicyEnforcement, pol.active)}</td>
                      <td>
                        <button
                          type="button"
                          className="button button-danger-outline"
                          disabled={deleting === pol.id}
                          onClick={() => handleDelete(pol.id)}
                        >
                          {deleting === pol.id ? "Deleting..." : "Delete"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls total={policies.length} state={pg} onChange={setPg} />
          </>
        )}
      </div>
    </section>
  );
}
