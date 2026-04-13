"use client";

import Link from "next/link";
import { useEffect } from "react";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import {
  IconShield,
  IconDollar,
  IconCompass,
  IconActivity,
  IconLayers,
  IconCloud,
  IconLock,
  IconTrendingDown,
  IconGitBranch,
  IconCpu,
  IconCheck,
  IconX,
  IconArrowRight,
  IconAlertTriangle,
} from "./icons";

/* ── Scroll-reveal hook ─────────────────────────────── */
function useReveal(selector: string) {
  useEffect(() => {
    // Mark document as JS-ready so CSS transitions activate.
    // Without this class, .reveal elements remain visible (safe fallback).
    document.documentElement.classList.add("js-reveal-ready");
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

/* ── Data ────────────────────────────────────────────── */
const FEATURES = [
  {
    icon: <IconShield />,
    title: "Preflight Safety Gates",
    description:
      "IAM, IRSA, OIDC, resource quota, Spot capacity, and Lake Formation permission checks run before a single byte moves. Bad configs are blocked with clear remediation steps so teams can fix issues before dispatch.",
  },
  {
    icon: <IconDollar />,
    title: "CUR-Aligned Cost Attribution",
    description:
      "SparkPilot provides per-run cost estimates before dispatch and can reconcile against AWS Cost and Usage Report data in Athena when CUR integration is configured.",
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
      "Role-based access is enforced across SparkPilot APIs, with team-environment scopes, budget guardrails, and audit events for key control-plane actions.",
  },
  {
    icon: <IconCloud />,
    title: "Bring Your Own Cloud",
    description:
      "SparkPilot runs inside your AWS account. Your VPC, S3 buckets, and IAM policies stay under your control. BYOC-Lite is designed for fast connection to an existing EKS cluster, depending on IAM and OIDC readiness.",
  },
  {
    icon: <IconActivity />,
    title: "Runtime Management",
    description:
      "Three background workers, Scheduler, Reconciler, and Provisioner, manage the run lifecycle. SparkPilot dispatches queued jobs to AWS, polls EMR for state transitions, and surfaces deterministic log pointers. You track runs in a dashboard, not a CloudWatch stream.",
  },
  {
    icon: <IconAlertTriangle />,
    title: "Structured Diagnostics",
    description:
      "When a run fails, SparkPilot classifies the cause such as OOM kill, Spot interruption, S3 access denied, timeout, or user error. Engineers get a clear starting point for remediation.",
  },
  {
    icon: <IconCompass />,
    title: "Guided Onboarding",
    description:
      "A step-by-step wizard validates cross-account trust, OIDC federation, namespace prerequisites, and execution role bindings, with actionable guidance for misconfigurations.",
  },
  {
    icon: <IconTrendingDown />,
    title: "Budget Guardrails",
    description:
      "Set monthly budget limits per team with configurable warn and hard-block thresholds. Runs that breach block thresholds are stopped before dispatch so compute does not start.",
  },
  {
    icon: <IconCpu />,
    title: "Spot Optimization",
    description:
      "Preflight validates Spot instance availability, instance diversification, and executor placement before dispatch to reduce wasted starts on under-provisioned Spot node groups.",
  },
  {
    icon: <IconGitBranch />,
    title: "Policy Engine",
    description:
      "Define submission guardrails as policy rules, including allowed instance types, required cost tags, release labels, and vCPU limits. Policies are checked during preflight before dispatch.",
  },
];

const BEFORE_AFTER = [
  {
    before: "Manually validate IAM trust policy and OIDC association before every job",
    after: "SparkPilot checks 20+ conditions automatically and fails fast with remediation steps",
  },
  {
    before: "Hunt through 6 different CloudWatch log groups to find your job output",
    after: "Every run has a deterministic log pointer. One click to the right stream",
  },
  {
    before: "Estimate cost in a spreadsheet after the job finishes",
    after: "Estimated cost is recorded per run, and actuals can be reconciled against CUR billing data when configured",
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
  {
    before: "Poll EMR DescribeJobRun in a cron loop to know when your job finishes",
    after: "SparkPilot's Reconciler polls EMR continuously and writes structured state transitions from queued to running to succeeded",
  },
  {
    before: "Parse raw EMR error events to understand why a job failed",
    after: "SparkPilot classifies failures, including OOM, Spot interruption, S3 access denied, and timeout, with remediation context",
  },
];

const PILOT_ASSETS = [
  {
    title: "Live guided demo",
    badge: "Available now",
    badgeClass: "badge-proven",
    description:
      "Walk through submission, preflight, run tracking, and diagnostics with your team and workload shape.",
    ctaLabel: "Request pilot",
    ctaHref: "/contact",
  },
  {
    title: "Pilot screenshot pack",
    badge: "In beta",
    badgeClass: "badge-supported",
    description:
      "Redacted screenshots and run summaries are shared during active pilot evaluations.",
    ctaLabel: "Request pilot pack",
    ctaHref: "/contact",
  },
  {
    title: "Recorded walkthrough clips",
    badge: "Coming soon",
    badgeClass: "badge-soon",
    description:
      "Short videos for onboarding and run operations are planned for customer enablement.",
    ctaLabel: "Discuss roadmap in demo",
    ctaHref: "/contact",
  },
];

const ENGINES = [
  {
    name: "EMR on EKS",
    badge: "Available now",
    badgeClass: "badge-proven",
    desc: "Native EMR virtual cluster on your EKS cluster for production Spark workloads.",
  },
  {
    name: "EMR Serverless",
    badge: "Beta",
    badgeClass: "badge-supported",
    desc: "Submit to an EMR Serverless application for fully managed capacity. No EKS cluster required.",
  },
  {
    name: "EMR on EC2",
    badge: "Beta",
    badgeClass: "badge-supported",
    desc: "Dispatch to existing EMR on EC2 clusters via step submission. Integrates with your current EC2-based Spark estate.",
  },
  {
    name: "Databricks on AWS",
    badge: "Coming soon",
    badgeClass: "badge-soon",
    desc: "Planned support for Databricks Jobs API routing from the SparkPilot control plane.",
  },
];

const INTEGRATIONS = [
  {
    name: "Apache Airflow",
    desc: "SparkPilotSubmitRunOperator with full deferrable trigger support. Drop into any existing DAG - sync or async.",
    detail: "Operator | Hook | Sensor | Async Trigger",
  },
  {
    name: "Dagster",
    desc: "Native @asset definitions and ops for run submission, polling, and cancellation. Works with Dagster Cloud and OSS.",
    detail: "Assets | Ops | Config Schema",
  },
  {
    name: "SparkPilot CLI",
    desc: "Engineers can submit, inspect, cancel, and tail runs from terminal workflows without opening the dashboard.",
    detail: "run-submit | run-list | run-logs | usage-get",
  },
  {
    name: "SparkPilot API",
    desc: "Teams can integrate SparkPilot into internal portals and automation jobs through authenticated REST endpoints.",
    detail: "REST API | RBAC | Audit Trail",
  },
];
const RUN_STATES = [
  { label: "queued", terminal: false },
  { label: "dispatching", terminal: false },
  { label: "accepted", terminal: false },
  { label: "running", terminal: false },
];
const RUN_TERMINAL_STATES = ["succeeded", "failed", "cancelled", "timed_out"];

const WORKERS = [
  {
    name: "Scheduler",
    icon: <IconCpu />,
    desc: "Polls for queued runs and dispatches them to AWS EMR, EMR Serverless, EMR on EC2, or Databricks. Manages concurrency limits and environment-level queueing.",
  },
  {
    name: "Reconciler",
    icon: <IconActivity />,
    desc: "Continuously polls EMR for job state changes and writes structured transitions from accepted to running to succeeded or failed. Detects stalled runs and triggers timeout handling.",
  },
  {
    name: "Provisioner",
    icon: <IconLayers />,
    desc: "Manages environment lifecycle, including BYOC-Lite and Full BYOC provisioning, checkpoint recovery across Terraform stages, and environment teardown.",
  },
];

const HOW_IT_WORKS = [
  {
    step: "1",
    title: "Define pilot scope",
    description:
      "Align on one workload family, success criteria, and owner roles before setup starts. This keeps pilot scope clear and measurable.",
    docLink: { href: "/getting-started", label: "Open the pilot guide" },
  },
  {
    step: "2",
    title: "Connect your AWS account",
    description:
      "Create the cross-account IAM role and OIDC association. SparkPilot validates trust, permissions, and namespace prerequisites with clear remediation steps.",
  },
  {
    step: "3",
    title: "Choose deployment model",
    description:
      "BYOC-Lite connects to your existing EKS cluster quickly. Full BYOC provisions VPC, EKS, and EMR from Terraform modules when needed.",
  },
  {
    step: "4",
    title: "Submit your first governed run",
    description:
      "Encode submission patterns as versioned templates, including Spot configurations, Graviton instance preferences, S3 Express paths, container images, and Spark configuration baselines.",
  },
  {
    step: "5",
    title: "Review outcomes and decide rollout",
    description:
      "Compare pilot results against your success criteria, including reliability, diagnostics, and cost visibility. Then move to production rollout with the same control plane.",
  },
];

const COMPARE_ROWS = [
  { topic: "Preflight IAM/OIDC validation", diy: false, serverless: false, sp: true },
  { topic: "Multi-tenant namespace isolation on EKS", diy: false, serverless: false, sp: true },
  { topic: "CUR-aligned cost attribution per team", diy: false, serverless: false, sp: true },
  { topic: "Budget guardrails with hard-block", diy: false, serverless: false, sp: true },
  { topic: "Spot diversification validation at preflight", diy: false, serverless: false, sp: true },
  { topic: "Airflow and Dagster native integrations", diy: false, serverless: false, sp: true },
  { topic: "Kubernetes-native control plane", diy: true, serverless: false, sp: true },
  { topic: "No infra management required", diy: false, serverless: true, sp: false },
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
        <h1 className="landing-hero-title">
          Govern Spark runs on AWS<br />
          <span className="landing-hero-accent">without building a control plane from scratch.</span>
        </h1>
        <p className="landing-hero-sub">
          SparkPilot is built for platform teams running Spark on AWS. You get preflight
          safety checks, run diagnostics, and cost visibility in one place while keeping
          infrastructure and data inside your AWS account.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            Request pilot
          </Link>
          <Link href="/getting-started" className="landing-btn landing-btn-secondary">
            See pilot plan
          </Link>
        </div>
      </section>

      {/* ── Before / After ───────────────────────────── */}
      <section className="landing-proof" id="status">
        <div className="landing-proof-inner">
          <div className="landing-proof-stat">
            <strong>Available now</strong>
            <span>Governed EMR on EKS control plane</span>
          </div>
          <div className="landing-proof-divider" />
          <div className="landing-proof-stat">
            <strong>In beta</strong>
            <span>EMR Serverless and EMR on EC2 dispatch paths</span>
          </div>
          <div className="landing-proof-divider" />
          <div className="landing-proof-stat">
            <strong>Coming soon</strong>
            <span>Databricks routing from the same control plane</span>
          </div>
        </div>
      </section>

      <section className="landing-section landing-section-tight" id="proof-assets">
        <div className="landing-section-header">
          <div className="landing-section-badge">Pilot Evaluation</div>
          <h2 className="landing-section-title">What you can review before rollout</h2>
          <p className="landing-section-sub">
            Start with a live demo, then use pilot artifacts to align technical, security, and buyer stakeholders.
          </p>
        </div>
        <div className="landing-engines-grid">
          {PILOT_ASSETS.map((asset) => (
            <article key={asset.title} className="landing-engine-card reveal">
              <div className="landing-engine-header">
                <strong>{asset.title}</strong>
                <span className={`landing-engine-badge ${asset.badgeClass}`}>{asset.badge}</span>
              </div>
              <p>{asset.description}</p>
              <Link href={asset.ctaHref} className="landing-btn landing-btn-secondary">
                {asset.ctaLabel}
              </Link>
            </article>
          ))}
        </div>
      </section>
      <section className="landing-section landing-section-tight" id="before-after">
        <div className="landing-section-header">
          <div className="landing-section-badge">The Problem</div>
          <h2 className="landing-section-title">What teams replace in week one</h2>
          <p className="landing-section-sub">
            Platform teams running Spark on shared EKS clusters hit the same operational bottlenecks.
            SparkPilot replaces manual run prep with a governed workflow.
          </p>
        </div>
        <div className="landing-before-after-grid">
          {BEFORE_AFTER.slice(0, 4).map((row) => (
            <div key={row.before} className="landing-ba-row reveal">
              <div className="landing-ba-before">
                <span className="landing-ba-icon landing-ba-icon-no" aria-hidden><IconX /></span>
                <span>{row.before}</span>
              </div>
              <div className="landing-ba-arrow" aria-hidden><IconArrowRight /></div>
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
          <h2 className="landing-section-title">Core capabilities for pilot and rollout</h2>
          <p className="landing-section-sub">
            These are the capabilities teams use first. Availability labels are shown only where they affect adoption decisions.
          </p>
        </div>
        <div className="landing-features-grid">
          {FEATURES.slice(0, 8).map((f, i) => (
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

      {/* ── Run Lifecycle ────────────────────────────── */}
      <section className="landing-section landing-section-alt" id="lifecycle">
        <div className="landing-section-header">
          <div className="landing-section-badge">Run Lifecycle</div>
          <h2 className="landing-section-title">How SparkPilot handles run operations</h2>
          <p className="landing-section-sub">
            Teams submit through API, CLI, Airflow, or Dagster. SparkPilot manages dispatch,
            state reconciliation, and diagnostics so operators do not stitch together raw AWS calls.
          </p>
        </div>

        {/* State machine */}
        <div className="reveal" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: "6px", padding: "18px 24px", background: "var(--surface-1)", border: "1px solid var(--line-soft)", borderRadius: "var(--radius-lg)", marginBottom: "32px", maxWidth: "760px", margin: "0 auto 32px" } as React.CSSProperties}>
          {RUN_STATES.map((s) => (
            <span key={s.label} style={{ display: "inline-flex", alignItems: "center", gap: "6px" }}>
              <span style={{ fontSize: "0.76rem", fontWeight: 600, letterSpacing: "0.03em", padding: "3px 11px", borderRadius: "999px", background: "var(--surface-2)", border: "1px solid var(--line-soft)", color: "var(--text-soft)" }}>
                {s.label}
              </span>
              <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}><IconArrowRight /></span>
            </span>
          ))}
          <span style={{ fontSize: "0.76rem", fontWeight: 600, letterSpacing: "0.03em", padding: "3px 11px", borderRadius: "999px", background: "var(--surface-2)", border: "1px solid var(--line-soft)", color: "var(--text-muted)" }}>
            {RUN_TERMINAL_STATES.join(" · ")}
          </span>
        </div>

        {/* Workers */}
        <div className="landing-engines-grid">
          {WORKERS.map((w) => (
            <div key={w.name} className="landing-engine-card reveal">
              <div className="landing-engine-header">
                <div className="landing-feature-icon">{w.icon}</div>
                <strong>{w.name}</strong>
              </div>
              <p>{w.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Engines ──────────────────────────────────── */}
      <section className="landing-section" id="engines">
        <div className="landing-section-header">
          <div className="landing-section-badge">Supported Engines</div>
          <h2 className="landing-section-title">One control plane, four Spark runtimes</h2>
          <p className="landing-section-sub">
            SparkPilot routes submissions to EMR on EKS, EMR Serverless, EMR on EC2, or
            Databricks from the same API and preflight pipeline.
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
      </section>

      {/* ── How It Works ─────────────────────────────── */}
      <section className="landing-section" id="how-it-works">
        <div className="landing-section-header">
          <div className="landing-section-badge">How It Works</div>
          <h2 className="landing-section-title">From pilot kickoff to rollout in five steps</h2>
        </div>
        <div className="landing-steps landing-steps-5">
          {HOW_IT_WORKS.map((s, i) => (
            <div key={s.step} className="landing-step reveal" style={{ transitionDelay: `${i * 70}ms` } as React.CSSProperties}>
              <div className="landing-step-number">{s.step}</div>
              <div className="landing-step-body">
                <h3>{s.title}</h3>
                <p>{s.description}</p>
                {"docLink" in s && s.docLink ? (
                  <Link href={s.docLink.href} className="landing-step-doc-link">
                    {s.docLink.label}
                  </Link>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Integrations ─────────────────────────────── */}
      <section className="landing-section landing-section-alt" id="integrations">
        <div className="landing-section-header">
          <div className="landing-section-badge">Integrations and Interfaces</div>
          <h2 className="landing-section-title">Use SparkPilot from orchestrators, terminal, or API</h2>
          <p className="landing-section-sub">
            SparkPilot supports workflow engines and engineer-first interfaces, so teams can
            adopt it through existing DAGs, CI pipelines, and terminal-driven operations.
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
          Airflow and Dagster providers are installable from source today. CLI and API are available now for platform teams and automation.
        </div>
        <div className="landing-hero-actions" style={{ marginTop: "20px" }}>
          <Link href="/integrations" className="landing-btn landing-btn-secondary">
            Open integration guide
          </Link>
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
                    <span role="img" className={`landing-compare-cell ${row.diy ? "cell-yes" : "cell-no"}`} aria-label={row.diy ? "Yes" : "No"}>
                      {row.diy ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                  <td>
                    <span role="img" className={`landing-compare-cell ${row.serverless ? "cell-yes" : "cell-no"}`} aria-label={row.serverless ? "Yes" : "No"}>
                      {row.serverless ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                  <td>
                    <span role="img" className={`landing-compare-cell ${row.sp ? "cell-yes" : "cell-no"}`} aria-label={row.sp ? "Yes" : "No"}>
                      {row.sp ? <IconCheck /> : <IconX />}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="landing-compare-caveat">
          On mobile, swipe horizontally to view the full table.
          <br />
          This comparison reflects capabilities of the SparkPilot control plane, not the
          underlying AWS services. Rows marked as available in DIY reflect platform primitives
          you can build yourself, while SparkPilot ships them configured and enforced.
        </div>
      </section>

      {/* ── Learn More ───────────────────────────────── */}
      <section className="landing-section" id="learn-more">
        <div className="landing-section-header">
          <div className="landing-section-badge">Still evaluating?</div>
          <h2 className="landing-section-title">Common questions, honest answers</h2>
          <p className="landing-section-sub">
            We outline tradeoffs so your team can choose the right path.
          </p>
        </div>
        <div className="landing-learnmore-grid">
          <Link href="/why-not-diy" className="landing-learnmore-card">
            <div className="landing-learnmore-icon" aria-hidden>DIY</div>
            <h3>Why not build it yourself?</h3>
            <p>
              130 to 250 hours to reach parity. 40 to 80 hours of ongoing maintenance per month.
              An honest cost accounting of DIY EMR on EKS.
            </p>
            <span className="landing-learnmore-link">Read the breakdown</span>
          </Link>
          <Link href="/why-not-serverless" className="landing-learnmore-card">
            <div className="landing-learnmore-icon" aria-hidden>AWS</div>
            <h3>Why not EMR Serverless?</h3>
            <p>
              Cold-start latency, no persistent clusters, no YuniKorn, no BYOC. When
              Serverless is the right answer, and when it is not.
            </p>
            <span className="landing-learnmore-link">Read the tradeoffs</span>
          </Link>
        </div>
      </section>

      {/* ── CTA ──────────────────────────────────────── */}
      <section className="landing-cta">
        <h2>Start with a guided Spark pilot</h2>
        <p>
          Share your workload profile and we will map a practical pilot plan with clear
          success criteria, owner responsibilities, and rollout options.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">
            <span>Request pilot</span>
            <span className="landing-btn-arrow"><IconArrowRight /></span>
          </Link>
          <Link href="/getting-started" className="landing-btn landing-btn-secondary">
            View pilot steps
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
