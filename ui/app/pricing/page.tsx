"use client";

import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const TIERS = [
  {
    name: "Community",
    price: "Free",
    period: "forever",
    description: "Self-hosted on your own infrastructure. Everything you need to get started.",
    cta: "Get started",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Single tenant",
      "Up to 3 environments",
      "BYOC-Lite provisioning",
      "20+ preflight safety checks",
      "Run lifecycle management",
      "Cost estimation",
      "Airflow & Dagster providers",
      "Community support (GitHub)",
    ],
  },
  {
    name: "Team",
    price: "Contact us",
    period: "",
    description: "Supported deployment for growing data platform teams with production SLAs.",
    cta: "Talk to us",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-primary",
    featured: true,
    features: [
      "Multi-tenant",
      "Unlimited environments",
      "BYOC-Lite provisioning",
      "Full preflight + diagnostics suite",
      "CUR cost reconciliation",
      "Team budget enforcement",
      "Policy engine (coming soon)",
      "Email support with SLA",
      "Deployment assistance",
      "Private Slack channel",
    ],
  },
  {
    name: "Enterprise",
    price: "Custom",
    period: "",
    description: "For organizations with compliance requirements, advanced security, and scale.",
    cta: "Contact sales",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Everything in Team",
      "SSO / SAML integration",
      "Custom RBAC policies",
      "Audit log export",
      "SOC 2 documentation",
      "Dedicated support engineer",
      "Custom SLA",
      "Procurement & legal review",
    ],
  },
];

const FAQ = [
  {
    q: "Does SparkPilot have access to my AWS account?",
    a: "No. SparkPilot runs inside your AWS account using a cross-account IAM role you provision. Your Spark job data, S3 buckets, and VPC resources never leave your perimeter.",
  },
  {
    q: "What does BYOC mean?",
    a: "Bring Your Own Cloud. You provide the EKS cluster and IAM setup. SparkPilot registers your environment, validates prerequisites, and dispatches jobs — all within your account.",
  },
  {
    q: "What AWS services does SparkPilot require?",
    a: "EMR on EKS (virtual cluster), EKS (your cluster), IAM (cross-account role + IRSA bindings), CloudWatch (log retrieval), and optionally Athena + S3 for CUR cost reconciliation.",
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
          Simple, transparent<br />
          <span className="landing-hero-accent">pricing for every team</span>
        </h2>
        <p className="landing-hero-sub">
          Start free with self-hosted Community. Talk to us when you need production support, SLAs, or enterprise compliance.
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
        <h2>Not sure which plan is right for you?</h2>
        <p>Talk to us. We'll help you figure out the right setup for your team's size and AWS footprint.</p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Talk to us</Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer" className="landing-btn landing-btn-secondary">
            View docs
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
