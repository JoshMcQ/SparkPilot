"use client";

import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const TIERS = [
  {
    name: "Open Source Evaluation",
    price: "Free",
    period: "",
    description: "Self-guided path for technical teams that want to evaluate core workflow behavior on their own.",
    cta: "Technical evaluators: Review open-source docs",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Single-team workspace",
      "Core preflight checks",
      "Manual environment setup",
      "20+ preflight safety checks",
      "Run lifecycle tracking",
      "Estimated run cost",
      "Airflow and Dagster providers",
      "Community support (GitHub)",
    ],
  },
  {
    name: "Pilot Program",
    price: "Contact us",
    period: "",
    description: "Sales-led pilot for platform teams that need a governed Spark path with clear success criteria.",
    cta: "Request pilot",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-primary",
    featured: true,
    features: [
      "Multi-tenant controls",
      "Pilot environment setup",
      "BYOC-Lite provisioning",
      "Preflight and diagnostics suite",
      "CUR cost reconciliation (In beta)",
      "Team budget guardrails",
      "Policy controls (Coming soon)",
      "Guided rollout plan",
      "Support channel during pilot",
    ],
  },
  {
    name: "Enterprise Rollout",
    price: "Custom",
    period: "",
    description: "Post-pilot rollout path for organizations with procurement, security, and multi-team operations.",
    cta: "Discuss rollout after pilot",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Everything in Pilot Program",
      "Production environment expansion",
      "Security and procurement review",
      "Support channels and escalation guidance",
      "Deployment and operations guidance",
      "Executive rollout planning",
    ],
  },
];

const PILOT_PATH = [
  "Discovery call to scope one workload and success metrics",
  "Guided setup and first governed run in your AWS account",
  "Pilot review and rollout recommendation",
];

const FAQ = [
  {
    q: "Does SparkPilot have access to my AWS account?",
    a: "SparkPilot runs inside your AWS account using a cross-account IAM role you provision. Spark job data and storage remain in your AWS environment.",
  },
  {
    q: "What does BYOC mean?",
    a: "Bring Your Own Cloud. You provide the EKS cluster and IAM setup. SparkPilot registers your environment, validates prerequisites, and dispatches jobs within your account.",
  },
  {
    q: "What AWS services does SparkPilot require?",
    a: "EMR on EKS (virtual cluster), EKS (your cluster), IAM (cross-account role + IRSA bindings), CloudWatch (log retrieval), and optionally Athena + S3 for CUR cost reconciliation (Beta).",
  },
  {
    q: "How does a pilot start?",
    a: "Most teams begin with a scoped pilot call, then run one governed workload in their AWS account before deciding rollout scope.",
  },
  {
    q: "Can we evaluate SparkPilot without changing our current infrastructure?",
    a: "Yes. BYOC-Lite connects SparkPilot to an existing EKS cluster without replacing your IAM model or S3 setup. The pilot scopes one workload to a test environment before any production changes.",
  },
];

export default function PricingPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero landing-hero-compact">
        <div className="landing-hero-badge">Pricing</div>
        <h1 className="landing-hero-title">
          Pilot-first commercial path for<br />
          <span className="landing-hero-accent">enterprise Spark teams</span>
        </h1>
        <p className="landing-hero-sub">
          SparkPilot is sales-led. Most teams start with a guided pilot, prove value quickly, and then choose a rollout path.
        </p>
      </section>

      <section className="landing-section landing-section-flush">
        <div className="pricing-grid">
          {TIERS.map((tier) => (
            <div key={tier.name} className={`pricing-card${tier.featured ? " pricing-card-featured" : ""}`}>
              {tier.featured && <div className="pricing-badge">Recommended</div>}
              <div className="pricing-header">
                <h3 className="pricing-name">{tier.name}</h3>
                <div className="pricing-price">
                  <span className="pricing-price-main">{tier.price}</span>
                  {tier.period && <span className="pricing-price-period">/{tier.period}</span>}
                </div>
                <p className="pricing-description">{tier.description}</p>
              </div>
              <Link
                href={tier.ctaHref}
                className={`landing-btn ${tier.ctaStyle} pricing-cta`}
                target={tier.ctaHref.startsWith("http") ? "_blank" : undefined}
                rel={tier.ctaHref.startsWith("http") ? "noopener noreferrer" : undefined}
              >
                {tier.cta}
              </Link>
              <ul className="pricing-features">
                {tier.features.map((f) => (
                  <li key={f} className="pricing-feature">
                    <span className="pricing-check" aria-hidden="true">+</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="landing-engines-note landing-engines-note-top">
          Capability labels show current maturity: Available now, In beta, or Coming soon.
        </p>
      </section>

      <section className="landing-section landing-section-flush">
        <div className="landing-section-header">
          <div className="landing-section-badge">Pilot Path</div>
          <h2 className="landing-section-title">How commercial evaluation works</h2>
        </div>
        <div className="landing-engines-grid">
          <article className="landing-engine-card">
            <ol className="guided-steps">
              {PILOT_PATH.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ol>
            <div className="landing-hero-actions landing-actions-start">
              <Link href="/contact" className="landing-btn landing-btn-primary">
                Request pilot
              </Link>
              <Link href="/getting-started" className="landing-btn landing-btn-secondary">
                View pilot guide
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section className="landing-section">
        <div className="landing-section-header">
          <div className="landing-section-badge">FAQ</div>
          <h2 className="landing-section-title">Common questions</h2>
        </div>
        <div className="faq-list">
          {FAQ.map((item) => (
            <div key={item.q} className="faq-item">
              <h4 className="faq-question">{item.q}</h4>
              <p className="faq-answer">{item.a}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>Need a realistic pilot plan?</h2>
        <p>We start by scoping your pilot, then recommend the right rollout path based on pilot results.</p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Request pilot</Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer" className="landing-btn landing-btn-secondary">
            Technical evaluators: Review open-source docs
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
