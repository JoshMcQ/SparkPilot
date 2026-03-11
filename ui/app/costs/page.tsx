"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CostShowbackResponse,
  Environment,
  UsageResponse,
  fetchCostShowback,
  fetchEnvironments,
  fetchUsage,
} from "@/lib/api";
import { shortId, usd, friendlyError } from "@/lib/format";
import { CostBarChart } from "@/components/cost-bar-chart";
import { ShortId } from "@/components/short-id";
import { PaginationControls, PaginationState, paginate } from "@/components/pagination";

function _periodNow(): string {
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}

export default function CostsPage() {
  const [environments, setEnvironments] = useState<Environment[]>([]);
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
    fetchEnvironments()
      .then((rows) => {
        setEnvironments(rows);
        if (!team && rows.length > 0) {
          setTeam(rows[0].tenant_id);
        }
      })
      .catch((err: unknown) => {
        setError(friendlyError(err, "Failed to load environments"));
      })
      .finally(() => {
        setInitializing(false);
      });
  }, []);

  const tenantOptions = useMemo(() => {
    return Array.from(new Set(environments.map((item) => item.tenant_id)));
  }, [environments]);

  // Build a lookup for environment display
  const envMap = useMemo(() => new Map(environments.map((e) => [e.id, e])), [environments]);
  function envDisplay(id: string): string {
    const env = envMap.get(id);
    if (!env) return shortId(id);
    return `${env.region} / ${env.eks_namespace ?? env.provisioning_mode}`;
  }

  async function loadCostData() {
    if (!team || !period) {
      setError("Select a team and billing period first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const [usagePayload, showbackPayload] = await Promise.all([
        fetchUsage(team),
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
      </div>

      <div className="card">
        <div className="form-grid">
          <label>
            Team
            <select value={team} onChange={(event) => setTeam(event.target.value)}>
              <option value="">Select team</option>
              {tenantOptions.map((item) => (
                <option key={item} value={item}>
                  {shortId(item)}
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
        <div className="button-row">
          <button type="button" className="button" disabled={busy} onClick={loadCostData}>
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
                <th className="col-hide-mobile">Period</th>
              </tr>
            </thead>
            <tbody>
              {paginate(showback.items, showbackPg).map((item) => (
                <tr key={item.run_id}>
                  <td><ShortId value={item.run_id} /></td>
                  <td title={item.environment_id}>{envDisplay(item.environment_id)}</td>
                  <td>{usd(item.estimated_cost_usd_micros)}</td>
                  <td>{usd(item.actual_cost_usd_micros)}</td>
                  <td>{usd(item.effective_cost_usd_micros)}</td>
                  <td className="col-hide-mobile">{item.billing_period}</td>
                </tr>
              ))}
              {showback.items.length === 0 ? (
                <tr>
                  <td colSpan={6} className="subtle">
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

