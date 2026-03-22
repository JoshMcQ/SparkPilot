"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CostShowbackResponse,
  Environment,
  Team,
  UsageResponse,
  fetchCostShowback,
  fetchEnvironments,
  fetchTeams,
  fetchUsage,
} from "@/lib/api";
import { shortId, usd, friendlyError } from "@/lib/format";
import { CostBarChart } from "@/components/cost-bar-chart";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";
import { badgeClass } from "@/lib/badge";

function _periodNow(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default function CostsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [teams, setTeams] = useState<Team[]>([]);
  const [initializing, setInitializing] = useState<boolean>(true);
  const [team, setTeam] = useState<string>("");
  const [period, setPeriod] = useState<string>(_periodNow());
  const [usage, setUsage] = useState<UsageResponse | null>(null);
  const [showback, setShowback] = useState<CostShowbackResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<boolean>(false);
  const [showbackPg, setShowbackPg] = useState<PaginationState>({ page: 0, pageSize: 10 });
  const [usagePg, setUsagePg] = useState<PaginationState>({ page: 0, pageSize: 10 });

  useEffect(() => {
    Promise.all([fetchEnvironments(), fetchTeams()])
      .then(([envRows, teamRows]) => {
        setEnvironments(envRows);
        setTeams(teamRows);
      })
      .catch((err: unknown) => {
        setError(friendlyError(err, "Failed to load teams and environments"));
      })
      .finally(() => {
        setInitializing(false);
      });
  }, []);

  useEffect(() => {
    if (!team && teams.length > 0) {
      setTeam(teams[0].name);
    }
  }, [team, teams]);

  // Build a lookup for environment display
  const envMap = useMemo(() => new Map(environments.map((e) => [e.id, e])), [environments]);
  function envDisplay(id: string): string {
    const env = envMap.get(id);
    if (!env) return shortId(id);
    return `${env.region} / ${env.eks_namespace ?? env.provisioning_mode}`;
  }

  const teamByName = useMemo(() => new Map(teams.map((t) => [t.name, t])), [teams]);

  function costStatus(item: CostShowbackResponse["items"][number]): { code: "reconciled" | "cur_pending" | "estimated_only"; label: string } {
    if (item.actual_cost_usd_micros != null && item.cur_reconciled_at) {
      return { code: "reconciled", label: "Reconciled" };
    }
    if (item.actual_cost_usd_micros == null) {
      return { code: "cur_pending", label: "CUR pending" };
    }
    return { code: "estimated_only", label: "Estimated only" };
  }

  const reconciliationSummary = useMemo(() => {
    if (!showback) return null;
    const reconciled = showback.items.filter((item) => costStatus(item).code === "reconciled").length;
    const pending = showback.items.filter((item) => costStatus(item).code === "cur_pending").length;
    const estimatedOnly = showback.items.filter((item) => costStatus(item).code === "estimated_only").length;
    const lastReconciledAt = showback.items
      .map((item) => item.cur_reconciled_at)
      .filter((item): item is string => typeof item === "string" && item.length > 0)
      .sort()
      .at(-1);
    return { reconciled, pending, estimatedOnly, lastReconciledAt };
  }, [showback]);

  async function loadCostData() {
    if (!team || !period) {
      setError("Select a team and billing period first.");
      return;
    }
    const tenantId = teamByName.get(team)?.tenant_id;
    if (!tenantId) {
      setError("Selected team is missing tenant mapping. Verify team configuration in Access.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const [usagePayload, showbackPayload] = await Promise.all([
        fetchUsage(tenantId),
        fetchCostShowback(team, period),
      ]);
      setUsage(usagePayload);
      setShowback(showbackPayload);
    } catch (err: unknown) {
      setError(friendlyError(err, "Failed to load cost data"));
      setUsage(null);
      setShowback(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="stack">
      <div className="card">
        <h3>Cost and Usage</h3>
        <div className="subtle">
          CUR-aligned showback and resource usage by team and billing period.
        </div>
        <div className="cur-explainer" style={{ marginTop: 12 }}>
          <div className="cur-explainer-item">
            <span className="badge reconciled">Reconciled</span>
            <span>
              SparkPilot matched this run&apos;s estimated cost against a real AWS Cost and Usage Report
              (CUR) line item via Athena. The <strong>Actual</strong> column reflects your real AWS bill.
            </span>
          </div>
          <div className="cur-explainer-item">
            <span className="badge cur_pending">CUR pending</span>
            <span>
              The run completed but AWS has not yet published a CUR line item for it. CUR data
              typically lags 24–48 hours. SparkPilot will reconcile automatically when the data
              arrives.
            </span>
          </div>
          <div className="cur-explainer-item">
            <span className="badge estimated_only">Estimated only</span>
            <span>
              No CUR reconciliation configured for this environment. The cost shown is SparkPilot&apos;s
              pre-run estimate based on vCPU and memory pricing — not actual AWS billing.
            </span>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="form-grid">
          <label>
            Team
            <select value={team} onChange={(event) => setTeam(event.target.value)}>
              <option value="">Select team</option>
              {teams.map((item) => (
                <option key={item.id} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Billing Period
            <input type="month" value={period} onChange={(event) => setPeriod(event.target.value)} />
          </label>
        </div>
        {initializing ? <div className="subtle">Loading team options...</div> : null}
        {!initializing && teams.length === 0 ? (
          <div className="subtle">
            No team entities found yet. Create teams on the Access page before loading showback.
          </div>
        ) : null}
        <div className="button-row">
          <button type="button" className="button" disabled={busy || teams.length === 0} onClick={loadCostData}>
            {busy ? "Loading..." : "Load cost data"}
          </button>
        </div>
        {error ? <div className="error-text">{error}</div> : null}
      </div>

      {showback ? (
        <div className="card-grid">
          <article className="card">
            <h3>Total Estimated</h3>
            <div className="cost-total">{usd(showback.total_estimated_cost_usd_micros)}</div>
            <div className="subtle">Pre-run resource cost model</div>
          </article>
          <article className="card">
            <h3>Total Actual</h3>
            <div className="cost-total">{usd(showback.total_actual_cost_usd_micros)}</div>
            <div className="subtle">CUR-reconciled AWS billing</div>
          </article>
          <article className="card">
            <h3>Total Effective</h3>
            <div className="cost-total">{usd(showback.total_effective_cost_usd_micros)}</div>
            <div className="subtle">Blended (actual when available)</div>
          </article>
        </div>
      ) : null}

      {showback && reconciliationSummary ? (
        <div className="card">
          <h3>Reconciliation Health</h3>
          <div className="subtle">
            Team: <strong>{showback.team}</strong>
            {teamByName.get(showback.team)?.tenant_id ? (
              <> | tenant: <ShortId value={teamByName.get(showback.team)?.tenant_id ?? ""} /></>
            ) : null}
          </div>
          <div className="card-grid" style={{ marginTop: 8 }}>
            <article className="card">
              <h3>Reconciled</h3>
              <div className="stat-value">{reconciliationSummary.reconciled}</div>
            </article>
            <article className="card">
              <h3>CUR Pending</h3>
              <div className="stat-value">{reconciliationSummary.pending}</div>
            </article>
            <article className="card">
              <h3>Estimated Only</h3>
              <div className="stat-value">{reconciliationSummary.estimatedOnly}</div>
            </article>
          </div>
          <div className="subtle" style={{ marginTop: 8 }}>
            Last CUR reconciliation:
            {" "}
            {reconciliationSummary.lastReconciledAt ? new Date(reconciliationSummary.lastReconciledAt).toLocaleString() : "not yet available"}
          </div>
        </div>
      ) : null}

      {/* --- Bar chart visualization --- */}
      {showback && showback.items.length > 0 ? (
        <CostBarChart items={showback.items} />
      ) : null}

      {showback ? (
        <>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Environment</th>
                <th>Estimated</th>
                <th>Actual</th>
                <th>Effective</th>
                <th>Status</th>
                <th className="col-hide-mobile">Period</th>
              </tr>
            </thead>
            <tbody>
              {paginate(showback.items, showbackPg).map((item) => (
                (() => {
                  const status = costStatus(item);
                  return (
                <tr key={item.run_id}>
                  <td><ShortId value={item.run_id} /></td>
                  <td title={item.environment_id}>{envDisplay(item.environment_id)}</td>
                  <td>{usd(item.estimated_cost_usd_micros)}</td>
                  <td>{usd(item.actual_cost_usd_micros)}</td>
                  <td>{usd(item.effective_cost_usd_micros)}</td>
                  <td>
                    <span className={badgeClass(status.code)}>{status.label}</span>
                  </td>
                  <td className="col-hide-mobile">{item.billing_period}</td>
                </tr>
                  );
                })()
              ))}
              {showback.items.length === 0 ? (
                <tr>
                  <td colSpan={7} className="subtle">
                    No showback data for this team and period. Run a workload first.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <PaginationControls total={showback.items.length} state={showbackPg} onChange={setShowbackPg} />
        </>
      ) : null}

      {usage ? (
        <div className="card">
          <h3>Usage Records</h3>
          <div className="subtle">
            {usage.items.length} {usage.items.length === 1 ? "record" : "records"} from {usage.from_ts ? new Date(usage.from_ts).toLocaleDateString() : "-"} to {usage.to_ts ? new Date(usage.to_ts).toLocaleDateString() : "-"}
          </div>
          {usage.items.length > 0 ? (
            <>
            <div className="table-wrap" style={{ marginTop: 8 }}>
              <table>
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>vCPU-sec</th>
                    <th>Mem GB-sec</th>
                    <th>Est. Cost</th>
                    <th className="col-hide-mobile">Recorded</th>
                  </tr>
                </thead>
                <tbody>
                  {paginate(usage.items, usagePg).map((rec) => (
                    <tr key={rec.run_id}>
                      <td><ShortId value={rec.run_id} /></td>
                      <td>{rec.vcpu_seconds.toLocaleString()}</td>
                      <td>{rec.memory_gb_seconds.toLocaleString()}</td>
                      <td>{usd(rec.estimated_cost_usd_micros)}</td>
                      <td className="col-hide-mobile">{new Date(rec.recorded_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <PaginationControls total={usage.items.length} state={usagePg} onChange={setUsagePg} />
            </>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

