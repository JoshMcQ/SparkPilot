"use client";

import Link from "next/link";
import { useEffect } from "react";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

/* ── Scroll-reveal hook ─────────────────────────────── */
function useReveal(selector: string) {
  useEffect(() => {
    const els = document.querySelectorAll<HTMLElement>(selector);
    if (!els.length) return;
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            (e.target as HTMLElement).classList.add("revealed");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" }
    );
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [selector]);
}

/* ── SVG Icons ──────────────────────────────────────── */
function IconShield() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
    </svg>
  );
}
function IconDollar() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
    </svg>
  );
}
function IconCompass() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
    </svg>
  );
}
function IconActivity() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  );
}
function IconLayers() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>
    </svg>
  );
}
function IconCloud() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M18 10h-1.26A8 8 0 1 0 9 20h9a5 5 0 0 0 0-10z"/>
    </svg>
  );
}
function IconLock() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
    </svg>
  );
}
function IconTrendingDown() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="23 18 13.5 8.5 8.5 13.5 1 6"/><polyline points="17 18 23 18 23 12"/>
    </svg>
  );
}
function IconGitBranch() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/>
    </svg>
  );
}
function IconCpu() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/>
    </svg>
  );
}
function IconCheck() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  );
}
function IconX() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
    </svg>
  );
}
function IconArrowRight() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>
    </svg>
  );
}

/* ── Data ────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: <IconShield />,
    title: "Preflight Safety Gates",
    description:
      "IAM, IRSA, OIDC, resource quota, Spot capacity, and Lake Formation permission checks run before a single byte moves. Bad configs are blocked at the gate with exact remediation steps — no silent failures.",
  },
  {
    icon: <IconDollar />,
    title: "CUR-Aligned Cost Attribution",
    description:
      "Every run gets an estimated cost before dispatch. After completion, SparkPilot reconciles against your real AWS Cost and Usage Report via Athena — not estimates, actual line-item costs attributed to teams.",
  },
  {
    icon: <IconLayers />,
    title: "Multi-Tenant Isolation",
    description:
      "Tenants, teams, environments, and runs are fully scoped. Each environment gets its own namespace, IRSA bindings, and resource quotas. Teams share a cluster without interference.",
  },
  {
    icon: <IconLock />,
    title: "Governance and Audit",
    description:
      "Role-based access (admin, operator, user) enforced on every API endpoint. Team-environment scopes, budget guardrails with warn and block thresholds, and a full audit trail for every action.",
  },
  {
    icon: <IconCloud />,
    title: "Bring Your Own Cloud",
    description:
      "SparkPilot runs inside your AWS account. Your VPC, your S3 buckets, your IAM policies. BYOC-Lite connects an existing EKS cluster in minutes. Full BYOC provisions the entire stack via Terraform.",
  },
  {
    icon: <IconActivity />,
    title: "Run Observability",
    description:
      "Deterministic CloudWatch log pointers, EMR virtual cluster IDs, and real-time state tracking from queued to terminal. No hunting for the right log group after a failure.",
  },
  {
    icon: <IconCompass />,
    title: "Guided Onboarding",
    description:
      "A step-by-step wizard validates cross-account trust, OIDC federation, namespace prerequisites, and execution role bindings — with exact remediation for every misconfiguration.",
  },
  {
    icon: <IconTrendingDown />,
    title: "Budget Guardrails",
    description:
      "Set monthly budget limits per team with configurable warn and hard-block thresholds. Submissions that would exceed the block threshold are rejected before any compute runs.",
  },
  {
    icon: <IconCpu />,
    title: "Spot Optimization",
    description:
      "Preflight validates Spot instance availability, instance type diversification, and executor placement before dispatch. No wasted job starts on under-provisioned Spot nodegroups.",
  },
  {
    icon: <IconGitBranch />,
    title: "Policy Engine",
    description:
      "Define submission guardrails as policy rules — restrict instance types, enforce release labels, require cost center tags, or block teams from exceeding vCPU limits. Applied at preflight before dispatch.",
  },
];

const BEFORE_AFTER = [
  {
    before: "Manually validate IAM trust policy and OIDC association before every job",
    after: "SparkPilot checks 15+ conditions automatically — fails fast with remediation steps",
  },
  {
    before: "Hunt through 6 different CloudWatch log groups to find your job output",
    after: "Every run has a deterministic log pointer. One click to the right stream",
  },
  {
    before: "Estimate cost in a spreadsheet after the job finishes",
    after: "CUR-aligned cost is attributed to your team automatically, reconciled against real AWS billing",
  },
  {
    before: "Engineers share a cluster namespace with no isolation or quota enforcement",
    after: "Each team gets scoped access, resource quotas, and budget guardrails",
  },
  {
    before: "Debug Spot interruptions by reading EMR service events manually",
    after: "Spot capacity and diversification are validated before the job starts",
  },
  {
    before: "Write one-off Terraform for every new EKS-based Spark deployment",
    after: "SparkPilot provisions network, EKS, and EMR from a versioned, reproducible control plane",
  },
];

const ENGINES = [
  {
    name: "EMR on EKS",
    badge: "Proven",
    badgeClass: "badge-proven",
    desc: "Native EMR virtual cluster on your EKS cluster. Validated end-to-end with real workloads including Structured Streaming.",
  },
  {
    name: "EMR Serverless",
    badge: "Supported",
    badgeClass: "badge-supported",
    desc: "Submit to an EMR Serverless application for fully managed capacity. No EKS cluster required.",
  },
  {
    name: "EMR on EC2",
    badge: "Supported",
    badgeClass: "badge-supported",
    desc: "Dispatch to existing EMR on EC2 clusters via step submission. Integrates with your current EC2-based Spark estate.",
  },
  {
    name: "Databricks on AWS",
    badge: "Supported",
    badgeClass: "badge-supported",
    desc: "Submit to a Databricks workspace via the Jobs API. Unified control plane for mixed Databricks and EMR environments.",
  },
];

const INTEGRATIONS = [
  {
    name: "Apache Airflow",
    desc: "SparkPilotSubmitRunOperator with full deferrable trigger support. Drop into any existing DAG — sync or async.",
    detail: "Operator · Hook · Sensor · Async Trigger",
  },
  {
    name: "Dagster",
    desc: "Native @asset definitions and ops for run submission, polling, and cancellation. Works with Dagster Cloud and OSS.",
    detail: "Assets · Ops · Config Schema",
  },
];

const HOW_IT_WORKS = [
  {
    step: "1",
    title: "Connect your AWS account",
    description:
      "Create a cross-account IAM role and OIDC association. SparkPilot validates the trust relationship, required permissions, and namespace prerequisites automatically — with exact remediation for every failure.",
  },
  {
    step: "2",
    title: "Choose your deployment model",
    description:
      "BYOC-Lite connects to an existing EKS cluster and provisions the EMR virtual cluster in minutes. Full BYOC runs Terraform to provision VPC, EKS, and EMR from scratch — with checkpoint recovery if any stage fails.",
  },
  {
    step: "3",
    title: "Define job templates",
    description:
      "Encode submission patterns as versioned templates — Spot configurations, Graviton instance preferences, S3 Express paths, container images, and Spark configuration golden paths.",
  },
  {
    step: "4",
    title: "Submit through your orchestrator",
    description:
      "Push jobs through the SparkPilot API, the Airflow operator, or the Dagster asset. Every submission passes preflight gates, gets a cost estimate, and is dispatched with deterministic logging.",
  },
  {
    step: "5",
    title: "Track cost and usage",
    description:
      "Estimated costs appear immediately. After the job finishes, SparkPilot reconciles against your AWS Cost and Usage Report via Athena — actual line-item costs attributed to teams and environments.",
  },
];

const COMPARE_ROWS = [
  { topic: "Preflight IAM/OIDC validation", diy: false, serverless: false, sp: true },
  { topic: "Multi-tenant namespace isolation on EKS", diy: false, serverless: false, sp: true },
  { topic: "CUR-aligned cost attribution per team", diy: false, serverless: false, sp: true },
  { topic: "Budget guardrails with hard-block", diy: false, serverless: false, sp: true },
  { topic: "Spot diversification validation at preflight", diy: false, serverless: false, sp: true },
  { topic: "Airflow and Dagster native integrations", diy: false, serverless: false, sp: true },
  { topic: "Lake Formation FGAC permission validation", diy: false, serverless: false, sp: true },
  { topic: "Policy engine for submission guardrails", diy: false, serverless: false, sp: true },
  { topic: "Kubernetes-native control plane", diy: true, serverless: false, sp: true },
  { topic: "No infra management required", diy: false, serverless: true, sp: false },
  { topic: "Sub-minute job start time", diy: false, serverless: true, sp: false },
];

/* ── Page ────────────────────────────────────────────── */
export default function LandingPage() {
  useReveal(".reveal");

  return (
    <div className="landing">
      <LandingNav />

      {/* ── Hero ─────────────────────────────────────── */}
      <section className="landing-hero" id="hero">
        <div className="landing-hero-badge">AWS-native Spark Control Plane</div>
        <h2 className="landing-hero-title">
          Stop firefighting Spark.<br />
          <span className="landing-hero-accent">Ship with confidence.</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot is a production control plane for Spark on AWS — preflight safety
          gates, CUR-aligned cost attribution, multi-tenant isolation, and orchestrator
          integrations. Your data never leaves your AWS account.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            Request access
          </Link>
          <Link href="/#how-it-works" className="landing-btn landing-btn-secondary">
            See how it works
          </Link>
        </div>
        <p className="landing-hero-note">
          Runs in your AWS account · No data leaves your perimeter · BYOC-Lite or Full BYOC
        </p>
      </section>

      {/* ── Before / After ───────────────────────────── */}
      <section className="landing-section landing-section-tight" id="before-after">
        <div className="landing-section-header">
          <div className="landing-section-badge">The Problem</div>
          <h2 className="landing-section-title">Before SparkPilot, this was your day</h2>
          <p className="landing-section-sub">
            Every team with a shared EKS cluster and a Spark workload hits the same walls.
            SparkPilot eliminates them operationally, not just conceptually.
          </p>
        </div>
        <div className="landing-before-after-grid">
          {BEFORE_AFTER.map((row, i) => (
            <div key={i} className="landing-ba-row reveal">
              <div className="landing-ba-before">
                <span className="landing-ba-icon landing-ba-icon-no" aria-hidden><IconX /></span>
                <span>{row.before}</span>
              </div>
              <div className="landing-ba-arrow" aria-hidden>→</div>
              <div className="landing-ba-after">
                <span className="landing-ba-icon landing-ba-icon-yes" aria-hidden><IconCheck /></span>
                <span>{row.after}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ─────────────────────────────────── */}
      <section className="landing-section" id="features">
        <div className="landing-section-header">
          <div className="landing-section-badge">Capabilities</div>
          <h2 className="landing-section-title">Everything your platform team needs</h2>
          <p className="landing-section-sub">
            Each capability is fully implemented and validated on real AWS — not
            checkbox features or marketing claims.
          </p>
        </div>
        <div className="landing-features-grid">
          {FEATURES.map((f, i) => (
            <article
              key={f.title}
              className="landing-feature-card reveal"
              style={{ transitionDelay: `${(i % 3) * 60}ms` } as React.CSSProperties}
            >
              <div className="landing-feature-icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.description}</p>
            </article>
          ))}
        </div>
      </section>

      {/* ── Engines ──────────────────────────────────── */}
      <section className="landing-section landing-section-alt" id="engines">
        <div className="landing-section-header">
          <div className="landing-section-badge">Supported Engines</div>
          <h2 className="landing-section-title">One control plane, four Spark runtimes</h2>
          <p className="landing-section-sub">
            SparkPilot routes submissions to EMR on EKS, EMR Serverless, EMR on EC2, or
            Databricks — from the same API and the same preflight pipeline.
          </p>
        </div>
        <div className="landing-engines-grid">
          {ENGINES.map((e) => (
            <div key={e.name} className="landing-engine-card reveal">
              <div className="landing-engine-header">
                <strong>{e.name}</strong>
                <span className={`landing-engine-badge ${e.badgeClass}`}>{e.badge}</span>
              </div>
              <p>{e.desc}</p>
            </div>
          ))}
        </div>
        <p className="landing-engines-note">
          <strong>Proven</strong> = validated end-to-end on real AWS with real run IDs and CloudWatch output.&nbsp;
          <strong>Supported</strong> = dispatch code is implemented and routed; live end-to-end validation in progress.
        </p>
      </section>

      {/* ── How It Works ─────────────────────────────── */}
      <section className="landing-section" id="how-it-works">
        <div className="landing-section-header">
          <div className="landing-section-badge">How It Works</div>
          <h2 className="landing-section-title">From zero to production in five steps</h2>
        </div>
        <div className="landing-steps landing-steps-5">
          {HOW_IT_WORKS.map((s, i) => (
            <div key={s.step} className="landing-step reveal" style={{ transitionDelay: `${i * 70}ms` } as React.CSSProperties}>
              <div className="landing-step-number">{s.step}</div>
              <div className="landing-step-body">
                <h3>{s.title}</h3>
                <p>{s.description}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Integrations ─────────────────────────────── */}
      <section className="landing-section landing-section-alt" id="integrations">
        <div className="landing-section-header">
          <div className="landing-section-badge">Orchestrator Integrations</div>
          <h2 className="landing-section-title">Works with the orchestrators your team already uses</h2>
          <p className="landing-section-sub">
            Native provider packages for Apache Airflow and Dagster — not HTTP wrappers,
            first-class operators with async support, config schemas, and error mapping.
          </p>
        </div>
        <div className="landing-integrations-grid">
          {INTEGRATIONS.map((intg) => (
            <div key={intg.name} className="landing-integration-card reveal">
              <div className="landing-integration-name">{intg.name}</div>
              <p className="landing-integration-desc">{intg.desc}</p>
              <div className="landing-integration-detail">{intg.detail}</div>
            </div>
          ))}
        </div>
        <div className="landing-integrations-note reveal">
          Both packages are installable from source today. PyPI publishing pending.
        </div>
      </section>

      {/* ── Comparison ───────────────────────────────── */}
      <section className="landing-section" id="compare">
        <div className="landing-section-header">
          <div className="landing-section-badge">Why SparkPilot</div>
          <h2 className="landing-section-title">What you don&apos;t get with DIY or EMR Serverless</h2>
          <p className="landing-section-sub">
            DIY gives you primitives. EMR Serverless removes cluster management.
            Neither gives you a multi-tenant control plane with built-in governance.
          </p>
        </div>
        <div className="landing-compare-wrapper reveal">
          <table className="landing-compare-table">
            <thead>
              <tr>
                <th className="landing-compare-topic">Capability</th>
                <th>DIY on AWS</th>
                <th>EMR Serverless</th>
                <th className="landing-compare-sp">SparkPilot</th>
              </tr>
            </thead>
            <tbody>
              {COMPARE_ROWS.map((row) => (
                <tr key={row.topic}>
                  <td className="landing-compare-topic">{row.topic}</td>
                  <td>
                    <span className={`landing-compare-cell ${row.diy ? "cell-yes" : "cell-no"}`}>
                      {row.diy ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                  <td>
                    <span className={`landing-compare-cell ${row.serverless ? "cell-yes" : "cell-no"}`}>
                      {row.serverless ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                  <td>
                    <span className={`landing-compare-cell ${row.sp ? "cell-yes" : "cell-no"}`}>
                      {row.sp ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="landing-compare-caveat">
          This comparison reflects capabilities of the SparkPilot control plane, not the
          underlying AWS services. Rows marked with ✓ for DIY reflect platform primitives
          you can build yourself — SparkPilot ships them configured and enforced.
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────── */}
      <section className="landing-cta">
        <h2>Ready to stop firefighting Spark?</h2>
        <p>
          Talk to us about your setup. We&apos;ll tell you honestly whether
          SparkPilot is the right fit for your team.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            <span>Talk to us</span>
            <span className="landing-btn-arrow"><IconArrowRight /></span>
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
