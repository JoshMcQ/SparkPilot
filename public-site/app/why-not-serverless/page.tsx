import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const TRADEOFFS = [
  {
    title: "No persistent clusters",
    impact: "High",
    description:
      "EMR Serverless spins up workers on demand for every application. You cannot pre-warm a set of workers that stay alive between jobs. For batch workloads running every 15 minutes, this is constant cold-start overhead.",
    sparkpilot:
      "EMR on EKS with SparkPilot supports persistent managed node groups and Karpenter-based warm capacity. Workers can be reused across jobs within the same virtual cluster.",
  },
  {
    title: "Cold start latency",
    impact: "High",
    description:
      "Serverless cold starts range from 30 seconds to several minutes depending on worker size and availability. Interactive and near-real-time workloads cannot absorb this latency.",
    sparkpilot:
      "With EKS-backed warm pools and Spot node groups, SparkPilot environments can keep executor startup low for pre-warmed capacity, depending on workload and cluster sizing.",
  },
  {
    title: "No Kubernetes scheduling control",
    impact: "Medium",
    description:
      "You cannot use Kubernetes node selectors, taints, tolerations, or pod affinity to control where workloads land. Serverless manages placement entirely. You cannot co-locate jobs with S3 Express One Zone endpoints or GPU nodes.",
    sparkpilot:
      "Full Kubernetes scheduling control via spark conf. Spot selectors, GPU node affinity, S3 Express co-location, and Karpenter NodePool targeting are all supported.",
  },
  {
    title: "No YuniKorn fair scheduling",
    impact: "Medium",
    description:
      "YuniKorn provides queue-based fair scheduling, guaranteed vCPU allocations per team, and preemption policies. None of these exist in Serverless, so every application competes for capacity without SLA guarantees.",
    sparkpilot:
      "Planned support for operator-installed YuniKorn environments is coming soon. Full fairness enforcement will depend on cluster-level YuniKorn deployment and policy.",
  },
  {
    title: "No cost allocation per team",
    impact: "High",
    description:
      "Serverless bills by application-level resource usage, but does not give you per-team or per-run cost attribution unless you build it yourself using resource tags and a CUR pipeline.",
    sparkpilot:
      "SparkPilot tags every run with a run ID, estimates cost at submission, and reconciles actual cost per run from your CUR via Athena. Cost is attributed by team, environment, and job automatically.",
  },
  {
    title: "No BYOC model",
    impact: "High",
    description:
      "EMR Serverless is a fully managed AWS service. Your job artifacts run in AWS-managed infrastructure. VPC placement depends on connector configuration and offers less infrastructure-level placement control than BYOC EKS.",
    sparkpilot:
      "SparkPilot is BYOC-first. The control plane runs in your account, your VPC, and your EKS cluster. The BYOC-Lite role grants SparkPilot only the permissions required for dispatch and checks.",
  },
  {
    title: "No pre-dispatch policy enforcement",
    impact: "Medium",
    description:
      "Serverless will accept and start any job you submit. Resource limits, release label policies, and team budget caps are not enforced at submission time. You discover overages in the bill.",
    sparkpilot:
      "Policy controls are coming soon for max_vcpu, max_memory_gb, max_run_seconds, and allowed_release_labels checks before dispatch.",
  },
  {
    title: "Limited Spark configuration surface",
    impact: "Medium",
    description:
      "Serverless constrains the Spark configuration you can set. Properties that affect cluster topology, shuffle behavior on persistent disk, or advanced JVM tuning are either unavailable or have no effect.",
    sparkpilot:
      "Full Spark configuration is passed through to the EMR on EKS job run, including executor node selectors, toleration hints, and shuffle storage for supported environments.",
  },
];

const WHEN_SERVERLESS_WINS = [
  {
    scenario: "Truly ad-hoc workloads",
    detail:
      "Jobs that run once a week or once a month where cold-start latency is irrelevant and you want zero cluster management overhead.",
  },
  {
    scenario: "Dev and sandbox environments",
    detail:
      "Exploratory data work where you want no minimum cluster cost and you do not need per-run cost attribution.",
  },
  {
    scenario: "Very small teams",
    detail:
      "Teams of 1 to 2 data engineers where multi-tenant isolation, policy controls, and cost allocation overhead is not worth the setup.",
  },
  {
    scenario: "AWS Glue replacement",
    detail:
      "Workloads migrating from Glue where the primary goal is eliminating the per-DPU hour cost, not adding governance.",
  },
];

const COMPARE_ROWS = [
  { capability: "Persistent warm capacity", serverless: false, sp: true },
  { capability: "Lower executor startup with warm capacity (workload-dependent)", serverless: false, sp: true },
  { capability: "Kubernetes scheduling control", serverless: false, sp: true },
  { capability: "YuniKorn fair scheduling (coming soon)", serverless: false, sp: false },
  { capability: "Per-run cost attribution", serverless: false, sp: true },
  { capability: "BYOC model (your VPC, your EKS)", serverless: false, sp: true },
  { capability: "Pre-dispatch policy enforcement", serverless: false, sp: true },
  { capability: "Spot instance management", serverless: "partial", sp: true },
  { capability: "Full Spark conf surface", serverless: false, sp: true },
  { capability: "Zero cluster management", serverless: true, sp: false },
  { capability: "No minimum cluster cost", serverless: true, sp: false },
  { capability: "Automatic scaling to zero", serverless: true, sp: "partial" },
];

function Cell({ value }: { value: boolean | "partial" }) {
  if (value === true) return <span className="objection-cell objection-cell-yes" aria-label="Yes">✓</span>;
  if (value === false) return <span className="objection-cell objection-cell-no" aria-label="No">✗</span>;
  return <span className="objection-cell objection-cell-partial" aria-label="Partial">~</span>;
}

export default function WhyNotServerlessPage() {
  return (
    <>
      <LandingNav />
      <main className="objection-page">
        {/* Hero */}
        <section className="objection-hero">
          <div className="objection-hero-badge">Common Objection</div>
          <h1 className="objection-hero-title">
            &ldquo;Why not just use EMR Serverless?&rdquo;
          </h1>
          <p className="objection-hero-sub">
            EMR Serverless is a strong fit for some workloads. Here are the practical tradeoffs so teams can choose the right path for real requirements.
          </p>
        </section>

        {/* Quick comparison */}
        <section className="objection-section">
          <h2 className="objection-section-title">Head-to-head capability comparison</h2>
          <div className="objection-compare-wrapper">
            <table className="objection-compare-table">
              <thead>
                <tr>
                  <th className="objection-compare-cap">Capability</th>
                  <th>EMR Serverless</th>
                  <th className="objection-compare-sp">SparkPilot + EMR on EKS</th>
                </tr>
              </thead>
              <tbody>
                {COMPARE_ROWS.map((row) => (
                  <tr key={row.capability}>
                    <td className="objection-compare-cap">{row.capability}</td>
                    <td><Cell value={row.serverless as boolean | "partial"} /></td>
                    <td><Cell value={row.sp as boolean | "partial"} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="objection-compare-note">
            On mobile, swipe horizontally to view the full table.
            <br />
            Partial indicates limited support. Spot in Serverless is available but without the
            placement control, diversification validation, or toleration management that
            SparkPilot provides on EKS.
          </p>
        </section>

        {/* Detailed tradeoffs */}
        <section className="objection-section objection-section-alt">
          <h2 className="objection-section-title">Tradeoff deep-dive</h2>
          <p className="objection-section-sub">
            These are real constraints, and each one matters in specific production scenarios.
          </p>
          <div className="objection-tradeoff-list">
            {TRADEOFFS.map((t) => (
              <div key={t.title} className="objection-tradeoff-card">
                <div className="objection-tradeoff-header">
                  <h3>{t.title}</h3>
                  <span className={`objection-impact-badge objection-impact-${t.impact.toLowerCase()}`}>
                    Impact: {t.impact}
                  </span>
                </div>
                <p className="objection-tradeoff-problem">{t.description}</p>
                <div className="objection-tradeoff-sp">
                  <span className="objection-tradeoff-sp-label">SparkPilot approach:</span>
                  {t.sparkpilot}
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* When Serverless wins */}
        <section className="objection-section">
          <h2 className="objection-section-title">When EMR Serverless is the right choice</h2>
          <p className="objection-section-sub">
            Serverless is the better choice for some use cases. Here is when.
          </p>
          <div className="objection-wins-grid">
            {WHEN_SERVERLESS_WINS.map((item) => (
              <div key={item.scenario} className="objection-wins-card">
                <h3>{item.scenario}</h3>
                <p>{item.detail}</p>
              </div>
            ))}
          </div>
        </section>

        {/* SparkPilot also supports Serverless */}
        <section className="objection-section objection-section-highlight">
          <h2 className="objection-section-title">SparkPilot also dispatches to EMR Serverless</h2>
          <p>
            SparkPilot is not an either/or choice. The same preflight pipeline,
            and cost tagging runs regardless of which execution engine you use. You can route
            production batch workloads to EMR on EKS for latency and cost control, and route
            ad-hoc or dev workloads to Serverless from the same control plane. EMR on EKS is available now; Serverless routing is in beta.
          </p>
          <p>
            The governance layer, including preflight checks, CUR reconciliation, and audit trail,
            applies to supported engines. You get visibility and control across jobs, regardless
            of which AWS service runs it.
          </p>
        </section>

        {/* CTA */}
        <section className="objection-cta">
          <h2>Evaluate both in your actual environment</h2>
          <p>
            We can help model latency, cost, and operational tradeoffs for your workload profile before you commit to a rollout path.
          </p>
          <div className="objection-cta-actions">
            <Link href="/contact" className="landing-btn landing-btn-primary">
              Request pilot
            </Link>
            <Link href="/why-not-diy" className="landing-btn landing-btn-secondary">
              Why not build it yourself?
            </Link>
          </div>
        </section>
      </main>
      <LandingFooter />
    </>
  );
}
