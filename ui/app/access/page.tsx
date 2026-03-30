"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import {
  type UserIdentity,
  type UserIdentityCreateRequest,
  type Team,
  type TeamCreateRequest,
  type TeamEnvironmentScope,
  type TeamBudget,
  type TeamBudgetCreateRequest,
  type Environment,
  fetchUserIdentities,
  createUserIdentity,
  fetchTeams,
  createTeam,
  fetchTeamEnvironmentScopes,
  createTeamEnvironmentScope,
  deleteTeamEnvironmentScope,
  fetchTeamBudget,
  createOrUpdateTeamBudget,
  fetchEnvironments,
} from "@/lib/api";
import { friendlyError } from "@/lib/format";
import {
  ACCESS_WORKFLOW_STEPS,
  mapAccessErrorMessage,
  validateBudgetForm,
  validateIdentityForm,
  validateScopeForm,
  validateTeamForm,
} from "@/lib/access-workflow";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";
import { badgeClass } from "@/lib/badge";

// ── Shared states ──────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="empty-state">
      <span className="subtle">{message}</span>
    </div>
  );
}

function LoadingState({ message }: { message: string }) {
  return (
    <div className="loading-state">
      <span className="subtle">{message}</span>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="error-state">
      <span className="error-text">{message}</span>
      {onRetry ? (
        <button type="button" className="button button-sm" style={{ marginLeft: 8 }} onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

function accessError(err: unknown, fallback: string): string {
  return mapAccessErrorMessage(friendlyError(err, fallback));
}

// ── User Identities Section ────────────────────────────────────────────────

function UserIdentitiesSection() {
  const [items, setItems] = useState<UserIdentity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 10 });

  // Create / edit form
  const [editingId, setEditingId] = useState<string | null>(null);
  const [actor, setActor] = useState("");
  const [role, setRole] = useState<"admin" | "operator" | "user">("user");
  const [tenantId, setTenantId] = useState("");
  const [teamId, setTeamId] = useState("");
  const [active, setActive] = useState(true);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);
  const [deactivatingId, setDeactivatingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await fetchUserIdentities();
      setItems(rows);
      setError(null);
    } catch (err: unknown) {
      setError(accessError(err, "Failed to load identities"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function resetForm() {
    setEditingId(null);
    setActor("");
    setRole("user");
    setTenantId("");
    setTeamId("");
    setActive(true);
    setFormError(null);
    setFormSuccess(null);
  }

  function startEdit(u: UserIdentity) {
    setEditingId(u.id);
    setActor(u.actor);
    setRole(u.role as "admin" | "operator" | "user");
    setTenantId(u.tenant_id ?? "");
    setTeamId(u.team_id ?? "");
    setActive(u.active);
    setFormError(null);
    setFormSuccess(null);
  }

  async function handleSave() {
    setFormError(null);
    setFormSuccess(null);
    const validationError = validateIdentityForm(actor);
    if (validationError) {
      setFormError(validationError);
      return;
    }
    setSaving(true);
    try {
      const req: UserIdentityCreateRequest = {
        actor: actor.trim(),
        role,
        tenant_id: tenantId.trim() || null,
        team_id: teamId.trim() || null,
        active,
      };
      const result = await createUserIdentity(req);
      setFormSuccess(editingId ? `Identity "${result.actor}" updated.` : `Identity created for "${result.actor}".`);
      resetForm();
      await load();
    } catch (err: unknown) {
      setFormError(accessError(err, "Identity save failed"));
    } finally {
      setSaving(false);
    }
  }

  async function handleDeactivate(u: UserIdentity) {
    setDeactivatingId(u.id);
    try {
      await createUserIdentity({
        actor: u.actor,
        role: u.role as "admin" | "operator" | "user",
        tenant_id: u.tenant_id ?? null,
        team_id: u.team_id ?? null,
        active: !u.active,
      });
      await load();
    } catch (err: unknown) {
      setError(accessError(err, `Failed to ${u.active ? "deactivate" : "activate"} identity`));
    } finally {
      setDeactivatingId(null);
    }
  }

  return (
    <>
      <details className="card" open={editingId !== null}>
        <summary className="card-summary">
          <h3>{editingId ? "Edit Identity" : "Create / Update Identity"}</h3>
          <span className="subtle">
            {editingId
              ? "Editing existing identity — change role, tenant/team, or active status."
              : "Add or update a user identity with role and tenant/team assignment."}
          </span>
        </summary>
        <div className="form-grid">
          <label>
            Actor (subject)
            <input
              value={actor}
              onChange={(e) => setActor(e.target.value)}
              placeholder="user:demo-admin or user@example.com"
              readOnly={editingId !== null}
              className={editingId ? "input-readonly" : ""}
            />
          </label>
          <label>
            Role
            <select value={role} onChange={(e) => setRole(e.target.value as "admin" | "operator" | "user")}>
              <option value="admin">admin</option>
              <option value="operator">operator</option>
              <option value="user">user</option>
            </select>
          </label>
          <label>
            Tenant ID (optional)
            <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Leave blank for global admin" />
          </label>
          <label>
            Team ID (optional)
            <input value={teamId} onChange={(e) => setTeamId(e.target.value)} placeholder="Restrict to a specific team" />
          </label>
          <label className="checkbox-field">
            <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
            Active
          </label>
        </div>
        <div className="button-row">
          <button type="button" className="button" disabled={saving} onClick={handleSave}>
            {saving ? "Saving…" : editingId ? "Update Identity" : "Save Identity"}
          </button>
          {editingId ? (
            <button type="button" className="button button-secondary" onClick={resetForm}>
              Cancel Edit
            </button>
          ) : null}
        </div>
        {formError ? <div className="error-text">{formError}</div> : null}
        {formSuccess ? <div className="success-text">{formSuccess}</div> : null}
      </details>

      <div className="card">
        <h3>User Identities</h3>
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {loading ? (
          <LoadingState message="Loading identities…" />
        ) : !error && items.length === 0 ? (
          <EmptyState message="No identities registered. Create one above to get started." />
        ) : items.length > 0 ? (
          <>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Actor</th>
                    <th>Role</th>
                    <th className="col-hide-mobile">Tenant</th>
                    <th className="col-hide-mobile">Team</th>
                    <th>Active</th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {paginate(items, pg).map((u) => (
                    <tr key={u.id} className={editingId === u.id ? "row-selected" : ""}>
                      <td><ShortId value={u.id} /></td>
                      <td>{u.actor}</td>
                      <td><span className={badgeClass(u.role)}>{u.role}</span></td>
                      <td className="col-hide-mobile"><ShortId value={u.tenant_id} /></td>
                      <td className="col-hide-mobile"><ShortId value={u.team_id} /></td>
                      <td>
                        <span className={u.active ? "badge badge-success" : "badge badge-muted"}>
                          {u.active ? "Yes" : "No"}
                        </span>
                      </td>
                      <td className="col-actions">
                        <button
                          type="button"
                          className="button button-sm"
                          onClick={() => startEdit(u)}
                          title="Edit identity"
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="button button-sm button-secondary"
                          style={{ marginLeft: 4 }}
                          disabled={deactivatingId === u.id}
                          onClick={() => void handleDeactivate(u)}
                          title={u.active ? "Deactivate identity" : "Activate identity"}
                        >
                          {deactivatingId === u.id ? "…" : u.active ? "Deactivate" : "Activate"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls total={items.length} state={pg} onChange={setPg} />
          </>
        ) : null}
      </div>
    </>
  );
}

// ── Teams Section ──────────────────────────────────────────────────────────

function TeamsSection() {
  const [items, setItems] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pg, setPg] = useState<PaginationState>({ page: 0, pageSize: 10 });

  const [name, setName] = useState("");
  const [tenantId, setTenantId] = useState("");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const rows = await fetchTeams();
      setItems(rows);
      setError(null);
    } catch (err: unknown) {
      setError(accessError(err, "Failed to load teams"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate() {
    setFormError(null);
    setFormSuccess(null);
    const validationError = validateTeamForm(name, tenantId);
    if (validationError) {
      setFormError(validationError);
      return;
    }
    setCreating(true);
    try {
      const req: TeamCreateRequest = { tenant_id: tenantId.trim(), name: name.trim() };
      const created = await createTeam(req);
      setFormSuccess(`Team "${created.name}" created.`);
      setName("");
      await load();
    } catch (err: unknown) {
      setFormError(accessError(err, "Team creation failed"));
    } finally {
      setCreating(false);
    }
  }

  return (
    <>
      <details className="card">
        <summary className="card-summary">
          <h3>Create Team</h3>
          <span className="subtle">Create a team under a tenant for environment scoping and budget governance.</span>
        </summary>
        <div className="form-grid">
          <label>
            Tenant ID
            <input value={tenantId} onChange={(e) => setTenantId(e.target.value)} placeholder="Owning tenant" />
          </label>
          <label>
            Team Name
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="data-engineering" />
          </label>
        </div>
        <div className="button-row">
          <button type="button" className="button" disabled={creating} onClick={handleCreate}>
            {creating ? "Creating…" : "Create Team"}
          </button>
        </div>
        {formError ? <div className="error-text">{formError}</div> : null}
        {formSuccess ? <div className="success-text">{formSuccess}</div> : null}
      </details>

      <div className="card">
        <h3>Teams</h3>
        {error ? <ErrorState message={error} onRetry={load} /> : null}
        {loading ? (
          <LoadingState message="Loading teams…" />
        ) : !error && items.length === 0 ? (
          <EmptyState message="No teams yet. Create one above to get started." />
        ) : items.length > 0 ? (
          <>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Tenant</th>
                    <th className="col-hide-mobile">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {paginate(items, pg).map((t) => (
                    <tr key={t.id}>
                      <td><ShortId value={t.id} /></td>
                      <td>{t.name}</td>
                      <td><ShortId value={t.tenant_id} /></td>
                      <td className="col-hide-mobile">{new Date(t.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls total={items.length} state={pg} onChange={setPg} />
          </>
        ) : null}
      </div>
    </>
  );
}

// ── Team-Environment Scopes Section ────────────────────────────────────────

function TeamScopesSection() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [scopes, setScopes] = useState<TeamEnvironmentScope[]>([]);
  const [loading, setLoading] = useState(true);
  const [scopesLoading, setScopesLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [selectedTeamId, setSelectedTeamId] = useState("");
  const [selectedEnvId, setSelectedEnvId] = useState("");
  const [creating, setCreating] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const loadBase = useCallback(async () => {
    try {
      const [teamRows, envRows] = await Promise.all([fetchTeams(), fetchEnvironments()]);
      setTeams(teamRows);
      setEnvironments(envRows);
      if (teamRows.length > 0) setSelectedTeamId(teamRows[0].id);
      setError(null);
    } catch (err: unknown) {
      setError(accessError(err, "Failed to load teams/environments"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  const loadScopes = useCallback(async (teamId: string) => {
    if (!teamId) { setScopes([]); return; }
    setScopesLoading(true);
    try {
      const rows = await fetchTeamEnvironmentScopes(teamId);
      setScopes(rows);
    } catch (err: unknown) {
      setError(accessError(err, "Failed to load scopes"));
    } finally {
      setScopesLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTeamId) void loadScopes(selectedTeamId);
  }, [selectedTeamId, loadScopes]);

  async function handleAssign() {
    setFormError(null);
    setFormSuccess(null);
    const validationError = validateScopeForm(selectedTeamId, selectedEnvId);
    if (validationError) {
      setFormError(validationError);
      return;
    }
    setCreating(true);
    try {
      await createTeamEnvironmentScope(selectedTeamId, selectedEnvId);
      setFormSuccess("Scope assigned.");
      setSelectedEnvId("");
      await loadScopes(selectedTeamId);
    } catch (err: unknown) {
      setFormError(accessError(err, "Scope assignment failed"));
    } finally {
      setCreating(false);
    }
  }

  async function handleRemove(scope: TeamEnvironmentScope) {
    setRemovingId(scope.id);
    setFormError(null);
    setFormSuccess(null);
    try {
      await deleteTeamEnvironmentScope(scope.team_id, scope.environment_id);
      setFormSuccess("Scope removed.");
      await loadScopes(selectedTeamId);
    } catch (err: unknown) {
      setFormError(accessError(err, "Scope removal failed"));
    } finally {
      setRemovingId(null);
    }
  }

  const teamName = (id: string) => teams.find((t) => t.id === id)?.name ?? id;
  const envLabel = (id: string) => {
    const e = environments.find((env) => env.id === id);
    return e ? `${e.region} / ${e.eks_namespace ?? e.provisioning_mode}` : id;
  };

  return (
    <div className="card">
      <h3>Team-Environment Scopes</h3>
      <div className="subtle">Assign or unassign environments from teams. Each team can only access its scoped environments.</div>
      {error ? <ErrorState message={error} onRetry={loadBase} /> : null}
      {loading ? (
        <LoadingState message="Loading teams and environments…" />
      ) : teams.length === 0 ? (
        <EmptyState message="Create teams and environments first before assigning scopes." />
      ) : (
        <>
          <div className="form-grid" style={{ marginTop: 8 }}>
            <label>
              Team
              <select value={selectedTeamId} onChange={(e) => setSelectedTeamId(e.target.value)}>
                {teams.map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
            <label>
              Environment
              <select value={selectedEnvId} onChange={(e) => setSelectedEnvId(e.target.value)}>
                <option value="">Select environment</option>
                {environments.map((env) => (
                  <option key={env.id} value={env.id}>{envLabel(env.id)}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="button-row">
            <button type="button" className="button" disabled={creating} onClick={handleAssign}>
              {creating ? "Assigning…" : "Assign Scope"}
            </button>
          </div>
          {formError ? <div className="error-text">{formError}</div> : null}
          {formSuccess ? <div className="success-text">{formSuccess}</div> : null}

          {scopesLoading ? (
            <LoadingState message="Loading scopes…" />
          ) : scopes.length > 0 ? (
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>Environment</th>
                    <th className="col-hide-mobile">Scope ID</th>
                    <th className="col-hide-mobile">Assigned</th>
                    <th className="col-actions">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {scopes.map((s) => (
                    <tr key={s.id}>
                      <td>{teamName(s.team_id)}</td>
                      <td>{envLabel(s.environment_id)}</td>
                      <td className="col-hide-mobile"><ShortId value={s.id} /></td>
                      <td className="col-hide-mobile">{new Date(s.created_at).toLocaleDateString()}</td>
                      <td className="col-actions">
                        <button
                          type="button"
                          className="button button-sm button-danger"
                          disabled={removingId === s.id}
                          onClick={() => void handleRemove(s)}
                          title="Remove this scope assignment"
                        >
                          {removingId === s.id ? "Removing…" : "Remove"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState message={`No scopes assigned for ${teamName(selectedTeamId)}.`} />
          )}
        </>
      )}
    </div>
  );
}

// ── Team Budgets Section ───────────────────────────────────────────────────

function TeamBudgetsSection() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [budget, setBudget] = useState<TeamBudget | null>(null);
  const [budgetLoading, setBudgetLoading] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);

  const [selectedTeam, setSelectedTeam] = useState("");
  const [monthlyBudget, setMonthlyBudget] = useState("100");
  const [warnPct, setWarnPct] = useState("80");
  const [blockPct, setBlockPct] = useState("100");
  const [creating, setCreating] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [formSuccess, setFormSuccess] = useState<string | null>(null);

  const loadTeams = useCallback(async () => {
    try {
      const rows = await fetchTeams();
      setTeams(rows);
      if (rows.length > 0) setSelectedTeam(rows[0].name);
      setError(null);
    } catch (err: unknown) {
      setError(accessError(err, "Failed to load teams"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTeams();
  }, [loadTeams]);

  const loadBudget = useCallback(async (team: string) => {
    setBudget(null);
    setBudgetError(null);
    if (!team) return;
    setBudgetLoading(true);
    try {
      const b = await fetchTeamBudget(team);
      setBudget(b);
    } catch (err: unknown) {
      setBudgetError(accessError(err, "No budget configured yet"));
    } finally {
      setBudgetLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedTeam) void loadBudget(selectedTeam);
  }, [selectedTeam, loadBudget]);

  async function handleSave() {
    setFormError(null);
    setFormSuccess(null);
    const validationError = validateBudgetForm(selectedTeam, monthlyBudget, warnPct, blockPct);
    if (validationError) {
      setFormError(validationError);
      return;
    }

    const dollars = Number.parseFloat(monthlyBudget);
    const warn = Number.parseInt(warnPct, 10);
    const block = Number.parseInt(blockPct, 10);
    setCreating(true);
    try {
      const req: TeamBudgetCreateRequest = {
        team: selectedTeam,
        monthly_budget_usd_micros: Math.round(dollars * 1_000_000),
        warn_threshold_pct: warn,
        block_threshold_pct: block,
      };
      await createOrUpdateTeamBudget(req);
      setFormSuccess(`Budget saved for "${selectedTeam}".`);
      await loadBudget(selectedTeam);
    } catch (err: unknown) {
      setFormError(accessError(err, "Budget save failed"));
    } finally {
      setCreating(false);
    }
  }

  function budgetUsd(micros: number): string {
    return `$${(micros / 1_000_000).toFixed(2)}`;
  }

  return (
    <div className="card">
      <h3>Team Budgets</h3>
      <div className="subtle">Set monthly spend limits and alert/block thresholds per team.</div>
      {error ? <ErrorState message={error} onRetry={loadTeams} /> : null}
      {loading ? (
        <LoadingState message="Loading teams…" />
      ) : teams.length === 0 ? (
        <EmptyState message="Create teams first before configuring budgets." />
      ) : (
        <>
          <div className="form-grid" style={{ marginTop: 8 }}>
            <label>
              Team
              <select value={selectedTeam} onChange={(e) => setSelectedTeam(e.target.value)}>
                {teams.map((t) => (
                  <option key={t.id} value={t.name}>{t.name}</option>
                ))}
              </select>
            </label>
            <label>
              Monthly Budget (USD)
              <input type="number" min={1} step="0.01" value={monthlyBudget} onChange={(e) => setMonthlyBudget(e.target.value)} />
            </label>
            <label>
              Warn Threshold (%)
              <input type="number" min={1} max={100} value={warnPct} onChange={(e) => setWarnPct(e.target.value)} />
            </label>
            <label>
              Block Threshold (%)
              <input type="number" min={1} max={100} value={blockPct} onChange={(e) => setBlockPct(e.target.value)} />
            </label>
          </div>
          <div className="button-row">
            <button type="button" className="button" disabled={creating} onClick={handleSave}>
              {creating ? "Saving…" : "Save Budget"}
            </button>
          </div>
          {formError ? <div className="error-text">{formError}</div> : null}
          {formSuccess ? <div className="success-text">{formSuccess}</div> : null}

          {budgetLoading ? (
            <LoadingState message="Loading budget…" />
          ) : budget ? (
            <div className="card-grid" style={{ marginTop: 12 }}>
              <article className="card">
                <h3>Current Budget</h3>
                <div className="cost-total">{budgetUsd(budget.monthly_budget_usd_micros)}</div>
                <div className="subtle">/month for &quot;{budget.team}&quot;</div>
              </article>
              <article className="card">
                <h3>Warn at</h3>
                <div className="stat-value">{budget.warn_threshold_pct}%</div>
                <div className="subtle">of monthly limit</div>
              </article>
              <article className="card">
                <h3>Block at</h3>
                <div className="stat-value">{budget.block_threshold_pct}%</div>
                <div className="subtle">of monthly limit</div>
              </article>
            </div>
          ) : budgetError ? (
            <EmptyState message={budgetError} />
          ) : null}
        </>
      )}
    </div>
  );
}

// ── Main Access Page ───────────────────────────────────────────────────────

export default function AccessPage() {
  return (
    <section className="stack">
      <div className="card">
        <h3>Access &amp; Governance</h3>
        <div className="subtle">
          Manage user identities, teams, team-environment scopes, and budget guardrails.
          All operations require admin-level bearer token authentication.
        </div>
        <div className="subtle" style={{ marginTop: 8 }}>
          Not an admin? Go to <Link href="/getting-started" className="inline-link">Start Here</Link> or{" "}
          <Link href="/contact" className="inline-link">Request access</Link>. This page is for workspace administrators.
        </div>
      </div>
      <div className="card">
        <h3>Guided Admin Workflow</h3>
        <div className="subtle">Follow this sequence to reduce auth/bootstrap errors and enforce least privilege.</div>
        <ol className="guided-steps">
          {ACCESS_WORKFLOW_STEPS.map((step) => (
            <li key={step.id}>
              <strong>{step.title}:</strong> {step.description}
            </li>
          ))}
        </ol>
        <div className="subtle">
          Production target: use real IdP sign-in (Auth0/Okta/Cognito) as the default path and keep manual token input
          as an explicit dev/bootstrap fallback only.
        </div>
      </div>

      <UserIdentitiesSection />
      <TeamsSection />
      <TeamScopesSection />
      <TeamBudgetsSection />
    </section>
  );
}
