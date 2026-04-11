"use client";

import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const TIERS = [
  {
    name: "Community",
    price: "Free",
    period: "forever",
    description: "Open-source self-hosted package for technical teams that want to evaluate on their own.",
    cta: "View open source",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Single-tenant workspace",
      "Up to 3 environments",
      "BYOC-Lite provisioning",
      "20+ preflight safety checks",
      "Run lifecycle management",
      "Estimated run cost at submission",
      "Airflow and Dagster providers",
      "Community support (GitHub)",
    ],
  },
  {
    name: "Pilot Program",
    price: "Contact us",
    period: "",
    description: "Sales-led 30-day pilot for platform teams that need governed Spark workflows quickly.",
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
      "Policy engine (Coming soon)",
      "Guided rollout plan",
      "Support channel during pilot",
    ],
  },
  {
    name: "Enterprise Rollout",
    price: "Custom",
    period: "",
    description: "Production rollout for organizations with procurement, security, and operational scale requirements.",
    cta: "Plan rollout",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Everything in Pilot Program",
      "Production environment expansion",
      "Security and procurement review",
      "Support plan and SLA options",
      "Deployment and operations guidance",
      "Executive rollout planning",
    ],
  },
];

const PILOT_PATH = [
  "Discovery call to scope one workload and success metrics",
  "Guided setup and first governed run in your AWS account",
  "Pilot review with rollout recommendation",
];

const FAQ = [
  {
    q: "Does SparkPilot have access to my AWS account?",
    a: "No. SparkPilot runs inside your AWS account using a cross-account IAM role you provision. Your Spark job data, S3 buckets, and VPC resources never leave your perimeter.",
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
    q: "Is there a free trial for the Team plan?",
    a: "Yes. We offer a 30-day evaluation for qualifying teams. Get in touch and we'll set you up.",
  },
  {
    q: "Can I self-host the Team or Enterprise version?",
    a: "Yes. SparkPilot deploys on ECS Fargate in your AWS account. We provide the Terraform modules and deployment support.",
  },
];

export default function PricingPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" style={{ paddingBottom: "clamp(28px, 4vw, 48px)" }}>
        <div className="landing-hero-badge">Pricing</div>
        <h2 className="landing-hero-title">
          Pilot-first pricing for<br />
          <span className="landing-hero-accent">enterprise Spark teams</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot is sales-led. Most teams start with a guided pilot, prove value quickly, and then decide rollout scope.
        </p>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="pricing-grid">
          {TIERS.map((tier) => (
            <div key={tier.name} className={`pricing-card${tier.featured ? " pricing-card-featured" : ""}`}>
              {tier.featured && <div className="pricing-badge">Most Popular</div>}
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
                    <span className="pricing-check" aria-hidden="true">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="landing-engines-note" style={{ marginTop: "14px" }}>
          Available now capabilities are listed directly. In beta and coming-soon capabilities are labeled in place.
        </p>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
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
            <div className="landing-hero-actions" style={{ justifyContent: "flex-start", marginTop: "16px" }}>
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
        <h2>Need help choosing the right path?</h2>
        <p>We will recommend whether to start with open source, a guided pilot, or a production rollout plan.</p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Request pilot</Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer" className="landing-btn landing-btn-secondary">
            View open source
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
