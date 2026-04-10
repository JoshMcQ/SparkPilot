import Link from "next/link";
import type { ReactNode } from "react";
import { LandingFooter } from "@/components/landing-footer";
import { LandingNav } from "@/components/landing-nav";
import { appHref } from "@/lib/app-url";
import {
  IconActivity,
  IconAlertTriangle,
  IconCheck,
  IconCloud,
  IconCompass,
  IconDollar,
  IconGitBranch,
  IconLayers,
  IconLock,
  IconTrendingDown,
} from "./icons";

const LIVE_NOW = [
  {
    icon: <IconCheck />,
    title: "Batch run lifecycle",
    description:
      "Sign in, submit governed batch runs, track status, inspect logs, and review diagnostics in one workflow.",
  },
  {
    icon: <IconCompass />,
    title: "BYOC-Lite onboarding",
    description:
      "Admins can connect an existing EKS cluster and bring up an EMR on EKS environment through guided onboarding.",
  },
  {
    icon: <IconLock />,
    title: "OIDC auth and scoped access",
    description:
      "OIDC sign-in and role-aware access controls are available across the API and product UI.",
  },
  {
    icon: <IconActivity />,
    title: "Run operations workspace",
    description:
      "The Runs workspace supports job definition setup, run submission, status tracking, logs, and diagnostics.",
  },
  {
    icon: <IconDollar />,
    title: "Usage and KPI visibility",
    description:
      "Usage records and KPI views are available for day-to-day operational visibility.",
  },
];

const LIMITED_VALIDATION = [
  {
    icon: <IconGitBranch />,
    title: "Policy engine",
    description:
      "Policy CRUD and preflight enforcement are available today, with broader enterprise packaging in active delivery.",
  },
  {
    icon: <IconTrendingDown />,
    title: "CUR reconciliation and budget workflows",
    description:
      "Cost and budget workflows are in place, with customer-specific CUR setup depending on each AWS environment.",
  },
  {
    icon: <IconLayers />,
    title: "Lake Formation and queue signals",
    description:
      "Lake Formation checks and queue utilization signals are implemented and being expanded into broader operator workflows.",
  },
  {
    icon: <IconCloud />,
    title: "Orchestration packages",
    description:
      "Airflow and Dagster packages are available in-source and are being expanded for wider production onboarding.",
  },
];

const COMING_SOON = [
  {
    icon: <IconAlertTriangle />,
    title: "Interactive endpoints",
    description:
      "Interactive endpoint management with enterprise governance controls.",
  },
  {
    icon: <IconCloud />,
    title: "Multi-engine runtime parity",
    description:
      "Expanded runtime coverage across EMR Serverless, EMR on EC2, and Databricks.",
  },
  {
    icon: <IconAlertTriangle />,
    title: "Template and security workflows",
    description:
      "Broader template, security configuration, and YuniKorn operator workflows in the product UI.",
  },
];

const WORKFLOW = [
  "Sign in with SSO and verify identity mapping.",
  "Create or connect a BYOC-Lite environment.",
  "Create a job definition and submit a run.",
  "Track lifecycle, logs, diagnostics, and usage evidence.",
];

const LAUNCH_SCOPE = [
  "Batch-first governance on EMR on EKS",
  "SSO sign-in and role-scoped product access",
  "BYOC-Lite environment connection",
  "Run submission and state monitoring",
  "Logs, diagnostics, usage, and KPI basics",
];

const NOT_LAUNCH_SCOPE = [
  "Interactive notebook endpoints",
  "Job template and security configuration management workflows",
  "Lake Formation and YuniKorn customer-facing operations",
  "Full multi-engine customer parity",
  "Enterprise compliance packaging claims",
  "Broad orchestration guarantees across every runtime",
];

function CapabilityColumn({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: { icon: ReactNode; title: string; description: string }[];
}) {
  return (
    <div className="landing-engine-card reveal">
      <div className="landing-engine-header">
        <strong>{title}</strong>
      </div>
      <p className="landing-section-sub">{subtitle}</p>
      <div className="landing-features-grid" style={{ marginTop: "16px" }}>
        {rows.map((row) => (
          <article key={row.title} className="landing-feature-card">
            <div className="landing-feature-icon">{row.icon}</div>
            <h3>{row.title}</h3>
            <p>{row.description}</p>
          </article>
        ))}
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" id="hero">
        <div className="landing-hero-badge">AWS-first Spark control plane</div>
        <h2 className="landing-hero-title">
          Governed Spark operations <br />
          <span className="landing-hero-accent">for enterprise AWS teams</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot helps platform teams connect their AWS environment, run governed batch workloads, and operate with
          clear diagnostics and cost visibility.
        </p>
        <div className="landing-hero-actions">
          <Link href="/getting-started" className="landing-btn landing-btn-primary">
            Start evaluation
          </Link>
          <Link href="/pricing" className="landing-btn landing-btn-secondary">
            View plans
          </Link>
        </div>
        <p className="landing-hero-note">
          Current release focus: batch-first on EMR on EKS. Interactive workflows and broader runtime coverage are planned next.
        </p>
      </section>

      <div id="features" />
      <section className="landing-section" id="truth-map">
        <div className="landing-section-header">
          <div className="landing-section-badge">Product Overview</div>
          <h2 className="landing-section-title">Available today, current focus, and planned next</h2>
          <p className="landing-section-sub">
            A clear view of what teams can use now, what is expanding next, and what is on the roadmap.
          </p>
        </div>
        <div className="landing-engines-grid">
          <CapabilityColumn title="Available today" subtitle="Ready for pilots and technical evaluations." rows={LIVE_NOW} />
          <CapabilityColumn title="Current focus" subtitle="In active delivery for broader enterprise rollout." rows={LIMITED_VALIDATION} />
          <CapabilityColumn title="Planned next" subtitle="On the roadmap for future releases." rows={COMING_SOON} />
        </div>
      </section>

      <div id="integrations" />
      <section className="landing-section landing-section-alt" id="workflow">
        <div className="landing-section-header">
          <div className="landing-section-badge">Validated Workflow</div>
          <h2 className="landing-section-title">Current end-to-end customer path</h2>
        </div>
        <div className="landing-step reveal">
          <ol className="guided-steps">
            {WORKFLOW.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <div className="button-row" style={{ marginTop: "12px" }}>
            <a href={appHref("/login?next=%2Fonboarding%2Faws")} className="button button-secondary">
              Open sign-in
            </a>
            <a href={appHref("/login?next=%2Fonboarding%2Faws")} className="button button-secondary">
              Open onboarding
            </a>
            <a href={appHref("/runs")} className="button button-secondary">
              Open runs
            </a>
          </div>
        </div>
      </section>

      <section className="landing-section" id="scope">
        <div className="landing-section-header">
          <div className="landing-section-badge">Launch Scope</div>
          <h2 className="landing-section-title">What is in and out for near-term launch</h2>
        </div>
        <div className="landing-before-after-grid">
          <div className="landing-ba-row reveal">
            <div className="landing-ba-before">
              <span className="landing-ba-icon landing-ba-icon-yes" aria-hidden>
                <IconCheck />
              </span>
              <span>In launch scope</span>
            </div>
            <div className="landing-ba-after">
              <ul className="contact-expect-list">
                {LAUNCH_SCOPE.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
          <div className="landing-ba-row reveal">
            <div className="landing-ba-before">
              <span className="landing-ba-icon landing-ba-icon-no" aria-hidden>
                <IconAlertTriangle />
              </span>
              <span>Not launch scope yet</span>
            </div>
            <div className="landing-ba-after">
              <ul className="contact-expect-list">
                {NOT_LAUNCH_SCOPE.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-cta">
        <h2>Need a practical pilot plan?</h2>
        <p>
          Start with a batch-first rollout in your AWS account, then expand scope as your production readiness grows.
        </p>
        <div className="landing-hero-actions">
          <Link href="/getting-started" className="landing-btn landing-btn-primary">
            Open getting started
          </Link>
          <Link href="/contact" className="landing-btn landing-btn-secondary">
            Talk to us
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}

