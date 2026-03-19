"use client";

import Link from "next/link";

const RUNTIME_TOGGLES = [
  {
    key: "SPARKPILOT_PREFLIGHT_AUTOFIX_TRUST_POLICY",
    description: "Controls whether preflight can auto-update EMR execution-role trust policy when remediable.",
    defaultValue: "true",
  },
  {
    key: "SPARKPILOT_PREFLIGHT_AUTOFIX_OIDC_PROVIDER",
    description: "Optional automation gate for creating missing OIDC provider associations (default is detect/instruct only).",
    defaultValue: "false",
  },
  {
    key: "SPARKPILOT_EMR_EXECUTION_ROLE_ARN",
    description: "Execution role target used by dispatch IAM simulation and trust checks.",
    defaultValue: "required",
  },
  {
    key: "SPARKPILOT_DRY_RUN_MODE",
    description: "When true, AWS mutating workflows are skipped and diagnostics run in dry-run semantics.",
    defaultValue: "false (production)",
  },
];

export default function SettingsPage() {
  return (
    <section className="stack">
      <div className="card">
        <h3>Platform Settings & Configuration</h3>
        <p className="subtle" style={{ marginTop: 8 }}>
          Operator control center for SparkPilot runtime behavior, preflight automation posture, and hardening conventions.
        </p>
      </div>

      <div className="card-grid">
        <article className="card">
          <h3>Auth & Access Baseline</h3>
          <ul className="guided-steps" style={{ marginTop: 8 }}>
            <li>Set or refresh your bearer token in the auth panel.</li>
            <li>Confirm actor identity and scope from the Access page.</li>
            <li>Use least-privilege team/environment scope for day-to-day operations.</li>
          </ul>
          <div style={{ marginTop: 8 }}>
            <Link href="/access" className="inline-link">Open access controls &rarr;</Link>
          </div>
        </article>

        <article className="card">
          <h3>Operational Playbooks</h3>
          <ul className="guided-steps" style={{ marginTop: 8 }}>
            <li>Environment readiness and BYOC diagnostics</li>
            <li>Run preflight remediations before dispatch</li>
            <li>Cost and reconciliation review per team/billing period</li>
          </ul>
          <div className="button-row" style={{ marginTop: 8 }}>
            <Link href="/environments" className="inline-link">Environments</Link>
            <Link href="/runs" className="inline-link">Runs</Link>
            <Link href="/costs" className="inline-link">Costs</Link>
          </div>
        </article>
      </div>

      <div className="card">
        <h3>Runtime Toggle Reference</h3>
        <div className="table-wrap" style={{ marginTop: 8 }}>
          <table className="table-compact">
            <thead>
              <tr>
                <th>Setting</th>
                <th>Default</th>
                <th>Purpose</th>
              </tr>
            </thead>
            <tbody>
              {RUNTIME_TOGGLES.map((toggle) => (
                <tr key={toggle.key}>
                  <td><code>{toggle.key}</code></td>
                  <td>{toggle.defaultValue}</td>
                  <td>{toggle.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h3>Security & Compliance Notes</h3>
        <p className="subtle" style={{ marginTop: 8 }}>
          Current hardening baseline includes preflight IAM/IRSA/OIDC diagnostics, trust-policy remediation guidance,
          dependency audit gates, and secret-scanning checks.
        </p>
      </div>
    </section>
  );
}
