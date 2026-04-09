import Link from "next/link";
import { LandingFooter } from "@/components/landing-footer";
import { LandingNav } from "@/components/landing-nav";

const TIERS = [
  {
    name: "Open Source",
    price: "Free",
    period: "self-hosted",
    description: "Code access and local development workflows.",
    cta: "View repository",
    ctaHref: "https://github.com/JoshMcQ/SparkPilot",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Core API and UI codebase",
      "CLI and provider source packages",
      "Local and mocked test workflows",
      "No hosted SLA commitments",
    ],
  },
  {
    name: "Staging Pilot",
    price: "Current focus",
    period: "",
    description: "Validated, batch-first staged workflow for real customer-style trials.",
    cta: "Start staging flow",
    ctaHref: "/getting-started",
    ctaStyle: "landing-btn-primary",
    featured: true,
    features: [
      "OIDC sign-in and onboarding",
      "BYOC-Lite environment connection",
      "Batch run submit, monitor, logs, diagnostics",
      "Usage and KPI visibility",
      "Policy and governance basics (limited validation)",
      "Advanced runtime features clearly labeled as beta or coming soon",
    ],
  },
  {
    name: "Enterprise Expansion",
    price: "Coming soon",
    period: "",
    description: "Broader multi-engine and enterprise packaging after additional live validation.",
    cta: "Talk to us",
    ctaHref: "/contact",
    ctaStyle: "landing-btn-secondary",
    featured: false,
    features: [
      "Interactive endpoints maturity",
      "Customer-facing job template workflows",
      "Security configuration workflows",
      "Lake Formation and YuniKorn rollout depth",
      "Broader runtime parity",
      "Expanded compliance and support packaging",
      "Only announced after evidence-backed readiness",
    ],
  },
];

const FAQ = [
  {
    q: "Is SparkPilot fully production-wide today?",
    a: "Not yet. The current honest scope is a staged, batch-first workflow with clearly marked beta and coming-soon areas.",
  },
  {
    q: "What is the best path to evaluate right now?",
    a: "Use the staging flow end-to-end: sign in, onboard, connect BYOC-Lite environment, submit a run, and verify logs/diagnostics/usage.",
  },
  {
    q: "Are all backend features customer-ready?",
    a: "No. Some backend capabilities exist without full customer-surface or live validation yet; those are marked as beta or coming soon.",
  },
  {
    q: "How are advanced features currently classified?",
    a: "Interactive endpoints, template/security workflows, Lake Formation depth, YuniKorn controls, and broader orchestration rollout are currently beta or coming soon unless explicitly proven.",
  },
  {
    q: "Does SparkPilot run in our AWS account?",
    a: "Yes. SparkPilot is BYOC-oriented and keeps workload execution and data inside your AWS account boundary.",
  },
];

export default function PricingPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" style={{ paddingBottom: "clamp(28px, 4vw, 48px)" }}>
        <div className="landing-hero-badge">Plans and Scope</div>
        <h2 className="landing-hero-title">
          Honest packaging for the <br />
          <span className="landing-hero-accent">current product stage</span>
        </h2>
        <p className="landing-hero-sub">
          This page reflects current reality: what is usable now, what is in limited validation, and what is not yet
          a launch commitment.
        </p>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="pricing-grid">
          {TIERS.map((tier) => (
            <div key={tier.name} className={`pricing-card${tier.featured ? " pricing-card-featured" : ""}`}>
              {tier.featured && <div className="pricing-badge">Current Recommended Path</div>}
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
                {tier.features.map((feature) => (
                  <li key={feature} className="pricing-feature">
                    <span className="pricing-check" aria-hidden="true">+</span>
                    {feature}
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
          <h2 className="landing-section-title">Scope clarity</h2>
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
        <h2>Need an evidence-backed pilot path?</h2>
        <p>Start with the staged workflow and expand scope only after live validation in your environment.</p>
        <div className="landing-hero-actions">
          <Link href="/getting-started" className="landing-btn landing-btn-primary">Open getting started</Link>
          <Link href="/contact" className="landing-btn landing-btn-secondary">Talk to us</Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}

