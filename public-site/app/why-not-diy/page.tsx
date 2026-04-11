import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const COSTS = [
  {
    category: "IAM Complexity",
    hours: "40 to 80 hrs initial setup",
    recurring: "10 to 20 hrs/month",
    description:
      "Every team needs its own execution role, IRSA binding, trust policy, and namespace scoping. Wrong IAM -> silent job failures, data leakage risk, or blocked dispatches. SparkPilot ships a validated IAM model (BYOC-Lite role, execution role trust, iam:PassRole) and checks it on every preflight.",
  },
  {
    category: "Namespace Isolation",
    hours: "8 to 16 hrs initial setup",
    recurring: "2 to 4 hrs/month",
    description:
      "Multi-tenant EKS requires ResourceQuota, LimitRange, and RBAC per namespace. Miss one and a runaway job can starve other teams. SparkPilot validates namespace-level isolation and prevents reserved-namespace collisions at onboarding time.",
  },
  {
    category: "Spot Instance Readiness",
    hours: "6 to 12 hrs per cluster",
    recurring: "2 to 5 hrs/month",
    description:
      "Spot requires diversified node groups (3+ instance types), correct executor tolerations, and capacity-type selectors in your spark conf. Without all three, jobs land on on-demand or fail to schedule. SparkPilot validates spot capacity, diversification, and executor placement on every preflight.",
  },
  {
    category: "EMR Release Lifecycle",
    hours: "4 to 8 hrs initial",
    recurring: "3 to 6 hrs/month",
    description:
      "EMR releases reach end-of-life without warning. Running a deprecated release means no security patches and no AWS support. SparkPilot syncs 141+ EMR release records, tracks current/deprecated/EOL status, and warns you before dispatch if your label is out of date.",
  },
  {
    category: "Cost Visibility",
    hours: "20 to 40 hrs to set up CUR pipeline",
    recurring: "5 to 10 hrs/month",
    description:
      "Without per-run cost tagging and CUR reconciliation, you can't answer 'which team spent $12k on Spark last month?' SparkPilot tags every run with a SparkPilot run ID, estimates cost at submission, and reconciles against your CUR via Athena for actual billing data.",
  },
  {
    category: "Policy Enforcement",
    hours: "15 to 30 hrs to build",
    recurring: "5 to 10 hrs/month",
    description:
      "Resource guards (max vCPU, max memory, max runtime, allowed release labels) need to be enforced at submission time, not discovered in a bill. SparkPilot ships a policy engine with hard-block (HTTP 422) and soft-warn enforcement, without a custom admission webhook.",
  },
  {
    category: "Upgrade Lifecycle",
    hours: "20 to 40 hrs per major upgrade",
    recurring: "10 to 20 hrs/quarter",
    description:
      "Upgrading EMR release labels, Kubernetes versions, and Spark config parameters across multiple environments is a quarterly fire drill when done by hand. SparkPilot surfaces upgrade targets in the UI and validates compatibility in preflight before you change anything.",
  },
  {
    category: "Monitoring & Diagnostics",
    hours: "15 to 25 hrs initial",
    recurring: "3 to 8 hrs/month",
    description:
      "CloudWatch log tailing, structured run diagnostics, and pattern-matching for spot interruptions, OOM events, and executor failures are non-trivial to build. SparkPilot ships structured diagnostics with categorized error patterns out of the box.",
  },
];

const WHAT_SP_SHIPS = [
  {
    title: "Preflight checks",
    body: "20+ IAM, OIDC, quota, policy, release, and spot readiness checks run before every dispatch, not after the job fails.",
  },
  {
    title: "BYOC-Lite onboarding",
    body: "Automated virtual cluster provisioning, trust policy management, and OIDC provider association in your account.",
  },
  {
    title: "Policy engine (Coming soon)",
    body: "Global and scoped policies with hard-block (HTTP 422) or soft-warn enforcement. max_vcpu, max_memory_gb, max_run_seconds, allowed_release_labels, allowed_golden_paths, and more.",
  },
  {
    title: "CUR reconciliation (Beta)",
    body: "Per-run cost tagging, estimated cost at submission, and Athena-backed reconciliation against your Cost and Usage Reports.",
  },
  {
    title: "EMR release lifecycle (Beta)",
    body: "141+ release records with current/deprecated/EOL status, Graviton support, and upgrade target tracking, synced from the AWS API.",
  },
  {
    title: "Team budgets",
    body: "Monthly budget caps per team with utilization tracking and soft-cap warnings before jobs run over budget.",
  },
  {
    title: "Structured diagnostics",
    body: "CloudWatch log analysis with pattern matching for spot interruptions, OOM, executor failures, and configuration errors.",
  },
  {
    title: "YuniKorn queue management",
    body: "Queue utilization checks and guaranteed vs max vCPU tracking for multi-tenant fair scheduling.",
  },
];

export default function WhyNotDIYPage() {
  return (
    <>
      <LandingNav />
      <main className="objection-page">
        {/* Hero */}
        <section className="objection-hero">
          <div className="objection-hero-badge">Common Objection</div>
          <h1 className="objection-hero-title">
            &ldquo;We can build this ourselves.&rdquo;
          </h1>
          <p className="objection-hero-sub">
            You can. Platform teams have been doing it for years. Here is an honest accounting
            of what that actually costs, and what your team gives up each month when it is maintained manually.
          </p>
        </section>

        {/* Cost table */}
        <section className="objection-section">
          <h2 className="objection-section-title">The real cost of DIY EMR on EKS</h2>
          <p className="objection-section-sub">
            These estimates are based on work we observed while building SparkPilot.
            Your numbers will vary, but the cost categories are consistent across teams.
          </p>
          <div className="objection-cost-grid">
            {COSTS.map((c) => (
              <div key={c.category} className="objection-cost-card">
                <div className="objection-cost-header">
                  <h3>{c.category}</h3>
                  <div className="objection-cost-meta">
                    <span className="objection-cost-tag">{c.hours}</span>
                    <span className="objection-cost-tag objection-cost-tag-recurring">{c.recurring}</span>
                  </div>
                </div>
                <p>{c.description}</p>
              </div>
            ))}
          </div>
          <div className="objection-cost-total">
            <strong>Total rough estimate:</strong> 130 to 250 hours to reach parity with SparkPilot&apos;s
            current feature set, plus 40 to 80 hours of ongoing maintenance each month.
          </div>
        </section>

        {/* What SparkPilot ships */}
        <section className="objection-section objection-section-alt">
          <h2 className="objection-section-title">What SparkPilot ships today</h2>
          <p className="objection-section-sub">
            Available now capabilities are listed directly. Beta and coming-soon items are labeled in place.
          </p>
          <div className="objection-ships-grid">
            {WHAT_SP_SHIPS.map((item) => (
              <div key={item.title} className="objection-ships-card">
                <h3>{item.title}</h3>
                <p>{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        {/* The honest case for DIY */}
        <section className="objection-section">
          <h2 className="objection-section-title">When DIY is the right answer</h2>
          <p className="objection-section-sub">
            We would rather lose a deal than have a bad-fit customer. Here is when you should
            build it yourself:
          </p>
          <ul className="objection-honest-list">
            <li>You have a dedicated platform engineering team with 2+ engineers and Spark is their primary focus.</li>
            <li>You have unique IAM or network topology requirements that a multi-tenant control plane cannot accommodate.</li>
            <li>You run exclusively in a single team with no need for multi-tenant isolation, policy enforcement, or cost allocation.</li>
            <li>You have a compliance requirement that prohibits any third-party software in your data plane, even if it never sees your data.</li>
          </ul>
          <p className="objection-honest-note">
            If none of those apply, you are paying engineering salary to solve a problem that is
            already solved. Every hour your platform team spends on IAM plumbing is an hour they
            are not spending on the problems that are actually specific to your business.
          </p>
        </section>

        {/* CTA */}
        <section className="objection-cta">
          <h2>Still want to evaluate?</h2>
          <p>
            We will walk you through the exact IAM model, preflight checks, and policy configuration
            that SparkPilot ships. This is a technical walkthrough, not a sales pitch.
          </p>
          <div className="objection-cta-actions">
            <Link href="/contact" className="landing-btn landing-btn-primary">
              Talk to an engineer
            </Link>
            <Link href="/why-not-serverless" className="landing-btn landing-btn-secondary">
              Why not EMR Serverless?
            </Link>
          </div>
        </section>
      </main>
      <LandingFooter />
    </>
  );
}
