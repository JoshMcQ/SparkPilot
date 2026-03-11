"use client";

import { usd } from "@/lib/format";
import type { CostShowbackItem } from "@/lib/api";

/**
 * A pure-CSS horizontal bar chart showing estimated vs actual cost per run.
 * No external charting library needed.
 */
export function CostBarChart({ items }: { items: CostShowbackItem[] }) {
  if (items.length === 0) return null;

  // Find the max value to scale bars
  const maxMicros = Math.max(
    ...items.flatMap((i) => [i.estimated_cost_usd_micros, Number(i.actual_cost_usd_micros ?? 0)])
  );
  const scale = maxMicros > 0 ? 100 / maxMicros : 0;

  return (
    <div className="card">
      <h3>Cost per Run</h3>
      <div className="subtle" style={{ marginBottom: 12 }}>Estimated (green) vs. Actual CUR-reconciled (blue) cost per run.</div>
      <div className="cost-chart">
        {items.map((item) => {
          const estPct = item.estimated_cost_usd_micros * scale;
          const actPct = Number(item.actual_cost_usd_micros ?? 0) * scale;
          const label = item.run_id.length > 8 ? item.run_id.slice(0, 8) : item.run_id;
          return (
            <div key={item.run_id} className="cost-chart-row">
              <div className="cost-chart-label" title={item.run_id}>{label}</div>
              <div className="cost-chart-bars">
                <div className="cost-bar cost-bar-estimated" style={{ width: `${Math.max(estPct, 1)}%` }}>
                  <span className="cost-bar-value">{usd(item.estimated_cost_usd_micros)}</span>
                </div>
                <div className="cost-bar cost-bar-actual" style={{ width: `${Math.max(actPct, 1)}%` }}>
                  <span className="cost-bar-value">{usd(item.actual_cost_usd_micros)}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="cost-chart-legend">
        <span className="cost-legend-swatch cost-legend-estimated" /> Estimated
        <span className="cost-legend-swatch cost-legend-actual" style={{ marginLeft: 16 }} /> Actual
      </div>
    </div>
  );
}
