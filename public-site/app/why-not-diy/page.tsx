import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const COSTS = [
  {
    category: "IAM Complexity",
    hours: "40-80 hrs initial setup",
    recurring: "10-20 hrs/month",
    description:
      "Every team needs its own execution role, IRSA binding, trust policy, and namespace scoping. Wrong IAM -> silent job failures, data leakage risk, or blocked dispatches. SparkPilot ships a validated IAM model (BYOC-Lite role, execution role trust, iam:PassRole) and checks it on every preflight.",
  },
  {
    category: "Namespace Isolation",
    hours: "8-16 hrs initial setup",
    recurring: "2-4 hrs/month",
    description:
      "Multi-tenant EKS requires ResourceQuota, LimitRange, and RBAC per namespace. Miss one and a runaway job can starve other teams. SparkPilot validates namespace-level isolation and prevents reserved-namespace collisions at onboarding time.",
  },
  {
    category: "Spot Instance Readiness",
    hours: "6-12 hrs per cluster",
    recurring: "2-5 hrs/month",
    description:
      "Spot requires diversified node groups (3+ instance types), correct executor tolerations, and capacity-type selectors in your spark conf. Without all three, jobs land on on-demand or fail to schedule. SparkPilot validates spot capacity, diversification, and executor placement on every preflight.",
  },
  {
    category: "EMR Release Lifecycle",
    hours: "4-8 hrs initial",
    recurring: "3-6 hrs/month",
    description:
      "EMR releases reach end-of-life without warning. Running a deprecated release means no security patches and no AWS support. SparkPilot tracks release lifecycle status and can warn before dispatch when your configured label is out of date.",
  },
  {
    category: "Cost Visibility",
    hours: "20-40 hrs to set up CUR pipeline",
    recurring: "5-10 hrs/month",
    description:
      "Without per-run cost tagging and CUR reconciliation, you can't answer 'which team spent $12k on Spark last month?' SparkPilot tags every run with a SparkPilot run ID, estimates cost at submission, and reconciles against your CUR via Athena for actual billing data.",
  },
  {
    category: "Policy Enforcement",
    hours: "15-30 hrs to build",
    recurring: "5-10 hrs/month",
    description:
      "Resource guards (max vCPU, max memory, max runtime, allowed release labels) need to be enforced at submission time, not discovered in a bill. SparkPilot ships a policy engine with hard-block (HTTP 422) and soft-warn enforcement - no custom admission webhook required.",
  },
  {
    category: "Upgrade Lifecycle",
    hours: "20-40 hrs per major upgrade",
    recurring: "10-20 hrs/quarter",
    description:
      "Upgrading EMR release labels, Kubernetes versions, and Spark config parameters across multiple environments is a quarterly fire drill when done by hand. SparkPilot surfaces upgrade targets in the UI and validates compatibility in preflight before you change anything.",
  },
  {
    category: "Monitoring & Diagnostics",
    hours: "15-25 hrs initial",
    recurring: "3-8 hrs/month",
    description:
      "CloudWatch log tailing, structured run diagnostics, and pattern-matching for spot interruptions, OOM events, and executor failures are non-trivial to build. SparkPilot ships structured diagnostics with categorized error patterns out of the box.",
  },
];

const WHAT_SP_SHIPS = [
  {
    title: "Available today: Preflight checks",
    body: "20+ IAM, OIDC, quota, policy, release, and spot readiness checks run before every dispatch - not after the job fails.",
  },
  {
    title: "Available today: BYOC-Lite onboarding",
    body: "Automated virtual cluster provisioning, trust policy management, and OIDC provider association in your account.",
  },
  {
    title: "Current focus: Policy engine",
    body: "Policy CRUD and enforcement are available now, with expanded enterprise policy packs in active delivery.",
  },
  {
    title: "Current focus: Cost reconciliation",
    body: "Per-run cost tagging and CUR reconciliation are available, with depth tied to each customer's CUR setup.",
  },
  {
    title: "Current focus: EMR release lifecycle",
    body: "Release lifecycle checks and warnings are available and expanding across broader rollout scenarios.",
  },
  {
    title: "Current focus: Team budgets",
    body: "Budget guardrails support warning and block behavior for operator-controlled rollout.",
  },
  {
    title: "Available today: Structured diagnostics",
    body: "CloudWatch log analysis with pattern matching for spot interruptions, OOM, executor failures, and configuration errors.",
  },
  {
    title: "Planned next: YuniKorn scheduling controls",
    body: "Queue utilization hints are in place, with fuller multi-tenant queue controls planned next.",
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
            You can. Platform teams do it every day. This is a practical breakdown of what it costs to build
            and operate in-house - and what you can accelerate with SparkPilot.
          </p>
        </section>

        {/* Cost table */}
        <section className="objection-section">
          <h2 className="objection-section-title">The real cost of DIY EMR on EKS</h2>
          <p className="objection-section-sub">
            These are directional planning estimates based on common platform delivery patterns.
            Your numbers will vary, but the workload categories are consistent across teams.
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
            <strong>Directional estimate only:</strong> these are planning heuristics, not guaranteed benchmarks.
            Validate with your own team, compliance requirements, and workload profile before committing to a DIY path.
          </div>
        </section>

        {/* What SparkPilot ships */}
        <section className="objection-section objection-section-alt">
          <h2 className="objection-section-title">What SparkPilot ships today</h2>
          <p className="objection-section-sub">
            Core product capabilities for pilot rollout, plus the next set of expansion areas.
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
            <li>You have a compliance requirement that prohibits any third-party software in your data plane - even if it never sees your data.</li>
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
            that SparkPilot ships. No pitch - just a technical deep-dive.
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

