"use client";

import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

/* ── Inline SVG icons for feature cards ───────────── */
function IconShield() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  );
}
function IconDollar() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  );
}
function IconCompass() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
    </svg>
  );
}
function IconActivity() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  );
}
function IconLayers() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>
    </svg>
  );
}
function IconCloud() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
    </svg>
  );
}

const FEATURES = [
  {
    icon: <IconShield />,
    title: "Preflight Safety Gates",
    description:
      "Every run passes IAM, IRSA, OIDC, and resource-quota checks before touching your cluster. Bad submissions are blocked with clear remediation steps — not silent failures.",
  },
  {
    icon: <IconDollar />,
    title: "Cost-Aware Operations",
    description:
      "CUR-aligned cost attribution by team and environment. Know what each Spark job costs before it runs, and get automated alerts when budgets are at risk.",
  },
  {
    icon: <IconCompass />,
    title: "Guided Onboarding",
    description:
      "A step-by-step wizard connects your AWS account, validates cross-account trust, and provisions your first environment in minutes — not days.",
  },
  {
    icon: <IconActivity />,
    title: "Run Observability",
    description:
      "Deterministic log pointers, EMR virtual cluster IDs, and real-time state tracking. No more hunting through CloudWatch for the right log group.",
  },
  {
    icon: <IconLayers />,
    title: "Multi-Tenant Isolation",
    description:
      "Each environment gets its own namespace, IRSA bindings, and resource quotas. Teams share a cluster without stepping on each other.",
  },
  {
    icon: <IconCloud />,
    title: "Bring Your Own Cloud",
    description:
      "SparkPilot runs in your AWS account with your VPC, your S3 buckets, and your IAM policies. No data leaves your perimeter.",
  },
];

const HOW_IT_WORKS = [
  {
    step: "1",
    title: "Connect your AWS account",
    description:
      "Create a cross-account IAM role with our CloudFormation template. SparkPilot validates the trust relationship and required permissions automatically.",
  },
  {
    step: "2",
    title: "Provision an environment",
    description:
      "Define your EKS cluster, namespace, and resource quotas. SparkPilot handles EMR virtual cluster registration, IRSA setup, and OIDC federation.",
  },
  {
    step: "3",
    title: "Submit and monitor runs",
    description:
      "Push Spark jobs through the API or UI. Every run is preflight-checked, cost-estimated, dispatched, and tracked with deterministic log access.",
  },
];

export default function LandingPage() {
  return (
    <div className="landing">
      <LandingNav />

      {/* ── Hero ───────────────────────────────── */}
      <section className="landing-hero" id="hero">
        <div className="landing-hero-badge">AWS-first BYOC Platform</div>
        <h2 className="landing-hero-title">
          Production guardrails for<br />
          <span className="landing-hero-accent">Spark on EKS</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot gates every Spark job before it runs — validating IAM, OIDC, quotas, and
          budgets. Your data stays in your AWS account. Your platform team stops firefighting.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            Request access
          </Link>
          <Link href="/pricing" className="landing-btn landing-btn-secondary">
            See pricing
          </Link>
        </div>
        <p className="landing-hero-note">
          Deploys in your AWS account · No data leaves your perimeter
        </p>
      </section>

      {/* ── Features ──────────────────────────── */}
      <section className="landing-section" id="features">
        <div className="landing-section-header">
          <div className="landing-section-badge">Features</div>
          <h2 className="landing-section-title">Everything you need to run Spark safely at scale</h2>
          <p className="landing-section-sub">
            From preflight checks to cost reconciliation, SparkPilot handles the operational
            complexity so your data engineers can focus on building pipelines.
          </p>
        </div>
        <div className="landing-features-grid">
          {FEATURES.map((f) => (
            <article key={f.title} className="landing-feature-card">
              <div className="landing-feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.description}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── How it works ──────────────────────── */}
      <section className="landing-section" id="how-it-works">
        <div className="landing-section-header">
          <div className="landing-section-badge">How It Works</div>
          <h2 className="landing-section-title">From zero to production in three steps</h2>
        </div>
        <div className="landing-steps">
          {HOW_IT_WORKS.map((s) => (
            <div key={s.step} className="landing-step">
              <div className="landing-step-number">{s.step}</div>
              <div className="landing-step-body">
                <h3>{s.title}</h3>
                <p>{s.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ───────────────────────────────── */}
      <section className="landing-cta">
        <h2>Ready to stop firefighting Spark?</h2>
        <p>
          Talk to us about your setup. We'll tell you honestly whether SparkPilot is the right fit.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            Talk to us
          </Link>
          <Link href="/pricing" className="landing-btn landing-btn-secondary">
            View pricing
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
