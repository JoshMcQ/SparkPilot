import Link from "next/link";
import type { ReactNode } from "react";
import { LandingFooter } from "@/components/landing-footer";
import { LandingNav } from "@/components/landing-nav";
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
      "End-to-end staged flow is live: sign in, submit batch runs, monitor state, open logs, and view diagnostics.",
  },
  {
    icon: <IconCompass />,
    title: "BYOC-Lite onboarding",
    description:
      "Admins can connect an existing EKS cluster and reach a ready EMR on EKS environment through guided onboarding.",
  },
  {
    icon: <IconLock />,
    title: "OIDC auth and scoped access",
    description:
      "OIDC sign-in and role checks are active in the API and UI for admin/operator/user access boundaries.",
  },
  {
    icon: <IconActivity />,
    title: "Run operations workspace",
    description:
      "Runs page supports job definition creation, run submission, queue/status visibility, logs, and diagnostics.",
  },
  {
    icon: <IconDollar />,
    title: "Usage and KPI visibility",
    description:
      "Usage records and KPI endpoints are wired and visible for staged operational evidence.",
  },
];

const LIMITED_VALIDATION = [
  {
    icon: <IconGitBranch />,
    title: "Policy engine",
    description:
      "Policy CRUD and preflight evaluation paths are implemented, but enterprise-hardening and broader runtime proof are still in progress.",
  },
  {
    icon: <IconTrendingDown />,
    title: "CUR reconciliation and budget workflows",
    description:
      "Cost and budget surfaces are implemented, but customer-by-customer CUR data wiring and validation depth vary.",
  },
  {
    icon: <IconLayers />,
    title: "Lake Formation and queue signals",
    description:
      "Lake Formation preflight logic and queue utilization APIs exist, but customer-facing rollout proof is still limited by environment-specific setup.",
  },
  {
    icon: <IconCloud />,
    title: "Orchestration packages",
    description:
      "Airflow and Dagster providers are implemented in-source, with narrower live validation for customer production rollout.",
  },
];

const COMING_SOON = [
  {
    icon: <IconAlertTriangle />,
    title: "Interactive endpoints",
    description:
      "Endpoint APIs exist, but interactive governance controls and operational maturity are not yet launch-ready.",
  },
  {
    icon: <IconCloud />,
    title: "Multi-engine runtime parity",
    description:
      "Serverless, EMR on EC2, and Databricks code paths exist in backend routing but are not yet proven launch workflows.",
  },
  {
    icon: <IconAlertTriangle />,
    title: "Template and security workflows",
    description:
      "Job template, security configuration, and YuniKorn queue controls need stronger customer-facing UX and rollout evidence before launch claims.",
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
  "Broad orchestration-runtime guarantees beyond staged proof",
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
        <div className="landing-hero-badge">AWS-first batch governance control plane</div>
        <h2 className="landing-hero-title">
          SparkPilot launch scope is now <br />
          <span className="landing-hero-accent">explicit and evidence-backed</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot is focused on one honest story for launch: governed batch Spark operations in your AWS account.
          We separate what is live now from what is beta and what is still coming soon.
        </p>
        <div className="landing-hero-actions">
          <Link href="/getting-started" className="landing-btn landing-btn-primary">
            Start with staged flow
          </Link>
          <Link href="/pricing" className="landing-btn landing-btn-secondary">
            View scope and plans
          </Link>
        </div>
        <p className="landing-hero-note">
          BYOC-Lite is the current validated path. Full BYOC and broader engine coverage are limited validation.
        </p>
      </section>

      <section className="landing-section" id="truth-map">
        <div className="landing-section-header">
          <div className="landing-section-badge">Product Truth Map</div>
          <h2 className="landing-section-title">Live now, limited validation, and coming soon</h2>
          <p className="landing-section-sub">
            Capability labels are tied to current staging evidence and implementation depth.
          </p>
        </div>
        <div className="landing-engines-grid">
          <CapabilityColumn title="Live now" subtitle="Validated in staged customer workflow." rows={LIVE_NOW} />
          <CapabilityColumn title="Limited validation / beta" subtitle="Implemented with narrower live proof." rows={LIMITED_VALIDATION} />
          <CapabilityColumn title="Coming soon" subtitle="Do not treat as launch commitments yet." rows={COMING_SOON} />
        </div>
      </section>

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
            <Link href="/login?next=%2Fonboarding%2Faws" className="button button-secondary">
              Open sign-in
            </Link>
            <Link href="/onboarding/aws" className="button button-secondary">
              Open onboarding
            </Link>
            <Link href="/runs" className="button button-secondary">
              Open runs
            </Link>
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
        <h2>Need a realistic pilot path?</h2>
        <p>
          Start with the staged batch-first workflow, validate against your own BYOC setup, then expand capability
          claims only after live evidence exists.
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

