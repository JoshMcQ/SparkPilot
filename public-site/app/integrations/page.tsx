import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import { appHref } from "@/lib/app-url";

const INTEGRATIONS = [
  {
    name: "Airflow provider",
    status: "Available now",
    badgeClass: "badge-proven",
    description:
      "Submit SparkPilot runs, wait for terminal states, and manage retries from your existing DAGs.",
    detail: "Installable from source: hook, operator, sensor, and deferrable trigger support",
    ctaLabel: "View Airflow provider",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot/tree/main/providers/airflow",
  },
  {
    name: "Dagster package",
    status: "Available now",
    badgeClass: "badge-proven",
    description:
      "Use resources, ops, and assets to submit and monitor Spark workloads in Dagster Cloud or OSS.",
    detail: "Installable from source: resource + ops + assets for submit, wait, cancel",
    ctaLabel: "View Dagster package",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot/tree/main/providers/dagster",
  },
  {
    name: "SparkPilot API and CLI",
    status: "Available now",
    badgeClass: "badge-proven",
    description:
      "Run SparkPilot through internal portals, CI jobs, or terminal workflows without changing team ownership.",
    detail: "REST API, RBAC, audit trail, run-submit and run-logs commands",
    ctaLabel: "Request pilot integration walkthrough",
    ctaHref: "/contact",
  },
];

const DEMO_ASSETS = [
  {
    title: "Live integration walkthrough",
    badge: "Available now",
    badgeClass: "badge-proven",
    body: "Walk through Airflow or Dagster submission, preflight checks, run tracking, and diagnostics with your workflow shape.",
  },
  {
    title: "Integration screenshot pack",
    badge: "In beta",
    badgeClass: "badge-supported",
    body: "Redacted screenshots for buyer and security reviews are shared during active pilot evaluations.",
  },
  {
    title: "Short onboarding clips",
    badge: "Coming soon",
    badgeClass: "badge-soon",
    body: "Short onboarding clips are coming soon, alongside planned workflow extensions such as Apache Iceberg governance.",
  },
];

const WORKFLOW_STEPS = [
  "Admin configures identity, team scopes, and budget guardrails in the app.",
  "Orchestrators submit jobs through Airflow, Dagster, API, or CLI.",
  "SparkPilot runs preflight checks, dispatches jobs, and tracks lifecycle events.",
  "Operators review runs, diagnostics, and cost visibility in one place.",
];

export default function IntegrationsPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero landing-hero-compact">
        <div className="landing-hero-badge">Integrations</div>
        <h1 className="landing-hero-title">
          Connect SparkPilot to your
          <br />
          <span className="landing-hero-accent">existing workflow stack</span>
        </h1>
        <p className="landing-hero-sub">
          Keep Airflow and Dagster in place, then run submission, diagnostics, and cost controls through one governed control plane.
        </p>
      </section>

      <section className="landing-section landing-section-alt">
        <div className="landing-section-header">
          <div className="landing-section-badge">Integration Options</div>
          <h2 className="landing-section-title">Orchestrator and interface coverage</h2>
        </div>
        <div className="landing-engines-grid">
          {INTEGRATIONS.map((integration) => (
            <article key={integration.name} className="landing-engine-card">
              <div className="landing-engine-header">
                <strong>{integration.name}</strong>
                <span className={`landing-engine-badge ${integration.badgeClass}`}>{integration.status}</span>
              </div>
              <p>{integration.description}</p>
              <p className="landing-engines-note landing-engines-note-left">
                {integration.detail}
              </p>
              <Link
                href={integration.ctaHref}
                className="landing-btn landing-btn-secondary"
                target={integration.ctaHref.startsWith("http") ? "_blank" : undefined}
                rel={integration.ctaHref.startsWith("http") ? "noopener noreferrer" : undefined}
              >
                {integration.ctaLabel}
              </Link>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-section-header">
          <div className="landing-section-badge">Workflow Fit</div>
          <h2 className="landing-section-title">How teams operate with SparkPilot</h2>
        </div>
        <div className="landing-engines-grid">
          <article className="landing-engine-card">
            <ol className="guided-steps">
              {WORKFLOW_STEPS.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <div className="landing-hero-actions landing-actions-start">
              <Link href="/contact" className="landing-btn landing-btn-primary">
                Request pilot
              </Link>
              <Link href={appHref("/login")} className="landing-btn landing-btn-secondary">
                Existing customer sign in
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section className="landing-section landing-section-alt">
        <div className="landing-section-header">
          <div className="landing-section-badge">Demo Assets</div>
          <h2 className="landing-section-title">What you can review during evaluation</h2>
        </div>
        <div className="landing-engines-grid">
          {DEMO_ASSETS.map((asset) => (
            <article key={asset.title} className="landing-engine-card">
              <div className="landing-engine-header">
                <strong>{asset.title}</strong>
                <span className={`landing-engine-badge ${asset.badgeClass}`}>{asset.badge}</span>
              </div>
              <p>{asset.body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>Connect your orchestrator in a pilot call</h2>
        <p>
          We will walk through your Airflow or Dagster setup, scope one workload, and confirm
          integration fit before you commit to a rollout.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            Request pilot
          </Link>
          <Link href="/getting-started" className="landing-btn landing-btn-secondary">
            View pilot guide
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
