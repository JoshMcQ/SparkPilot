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
    detail: "Hook, operator, sensor, and deferrable trigger support",
    ctaLabel: "View Airflow provider",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot/tree/main/providers/airflow",
  },
  {
    name: "Dagster package",
    status: "Available now",
    badgeClass: "badge-proven",
    description:
      "Use resources, ops, and assets to submit and monitor Spark workloads in Dagster Cloud or OSS.",
    detail: "Resource + ops + assets for submit, wait, cancel",
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
    ctaLabel: "Open app login",
    ctaHref: appHref("/login"),
  },
];

const PLATFORM_STATUS = [
  {
    title: "Available now",
    body: "Airflow provider, Dagster package, API, and CLI for production workflow orchestration.",
  },
  {
    title: "Beta",
    body: "Additional dispatch targets and expanded policy controls for mixed-runtime teams.",
  },
  {
    title: "Coming soon",
    body: "Deeper integration templates for enterprise rollout playbooks and environment bootstrapping.",
  },
];

const WORKFLOW_STEPS = [
  "Admin configures identity, team scopes, and budget guardrails in the app.",
  "Orchestrator submits jobs through Airflow, Dagster, API, or CLI.",
  "SparkPilot runs preflight checks, dispatches, and tracks lifecycle events.",
  "Operators review runs, diagnostics, and cost attribution in one place.",
];

export default function IntegrationsPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" style={{ paddingBottom: "clamp(28px, 4vw, 48px)" }}>
        <div className="landing-hero-badge">Integrations</div>
        <h2 className="landing-hero-title">
          Connect SparkPilot to your
          <br />
          <span className="landing-hero-accent">existing workflow stack</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot fits into how platform and data teams already operate. Keep Airflow and Dagster in place, then
          run submission, diagnostics, and cost controls through a single control plane.
        </p>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="landing-section-header">
          <div className="landing-section-badge">Availability</div>
          <h2 className="landing-section-title">What you can use today</h2>
        </div>
        <div className="landing-engines-grid">
          {PLATFORM_STATUS.map((item) => (
            <article key={item.title} className="landing-engine-card">
              <div className="landing-engine-header">
                <strong>{item.title}</strong>
              </div>
              <p>{item.body}</p>
            </article>
          ))}
        </div>
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
              <p className="landing-engines-note" style={{ textAlign: "left", marginTop: "6px", marginBottom: "12px" }}>
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
            <div className="landing-hero-actions" style={{ justifyContent: "flex-start", marginTop: "18px" }}>
              <Link href={appHref("/runs")} className="landing-btn landing-btn-primary">
                Open app runs
              </Link>
              <Link href="/getting-started" className="landing-btn landing-btn-secondary">
                Getting started
              </Link>
            </div>
          </article>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
