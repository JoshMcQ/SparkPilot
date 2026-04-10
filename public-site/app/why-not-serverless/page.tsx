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
      "On the EMR on EKS path, SparkPilot can run with persistent node groups and warm capacity depending on your cluster configuration.",
  },
  {
    title: "Cold start latency",
    impact: "High",
    description:
      "Serverless cold starts range from 30 seconds to several minutes depending on worker size and availability. Interactive and near-real-time workloads cannot absorb this latency.",
    sparkpilot:
      "With EKS-backed warm capacity and tuned node groups, SparkPilot can reduce startup latency for repeated workloads.",
  },
  {
    title: "No Kubernetes scheduling control",
    impact: "Medium",
    description:
      "You cannot use Kubernetes node selectors, taints, tolerations, or pod affinity to control where workloads land. Serverless manages placement entirely. You cannot co-locate jobs with S3 Express One Zone endpoints or GPU nodes.",
    sparkpilot:
      "SparkPilot passes Spark configuration to EMR on EKS runs, including Kubernetes selector and placement hints when configured.",
  },
  {
    title: "No YuniKorn fair scheduling",
    impact: "Medium",
    description:
      "YuniKorn provides queue-based fair scheduling, guaranteed vCPU allocations per team, and preemption policies. None of these exist in Serverless - every application competes for capacity without SLA guarantees.",
    sparkpilot:
      "SparkPilot supports YuniKorn queue fields and preflight queue-capacity checks, with broader queue operations planned next.",
  },
  {
    title: "No cost allocation per team",
    impact: "High",
    description:
      "Serverless bills by application-level resource usage, but does not give you per-team or per-run cost attribution unless you build it yourself using resource tags and a CUR pipeline.",
    sparkpilot:
      "SparkPilot tracks per-run usage and attribution fields, with deeper cost reconciliation based on customer CUR setup.",
  },
  {
    title: "No BYOC model",
    impact: "High",
    description:
      "EMR Serverless is a fully managed AWS service. Your job artifacts run in AWS-managed infrastructure. There is no way to ensure workers run inside your VPC, your subnets, or your security groups without complex VPC connector configuration.",
    sparkpilot:
      "SparkPilot is BYOC-first. The control plane runs in your account, your VPC, your EKS cluster. Your data never leaves your perimeter. The BYOC-Lite role grants SparkPilot exactly the permissions it needs - nothing more.",
  },
  {
    title: "No pre-dispatch policy enforcement",
    impact: "Medium",
    description:
      "Serverless will accept and start any job you submit. Resource limits, release label policies, and team budget caps are not enforced at submission time. You discover overages in the bill.",
    sparkpilot:
      "SparkPilot policy checks run at preflight and support operator-controlled rollout.",
  },
  {
    title: "Limited Spark configuration surface",
    impact: "Medium",
    description:
      "Serverless constrains the Spark configuration you can set. Properties that affect cluster topology, shuffle behavior on persistent disk, or advanced JVM tuning are either unavailable or have no effect.",
    sparkpilot:
      "Full Spark configuration is passed through to the EMR on EKS job run, including executor node selectors, toleration hints, shuffle storage, and YuniKorn scheduling properties.",
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
      "Teams of 1-2 data engineers where the multi-tenant isolation, policy engine, and cost allocation overhead is not worth the setup.",
  },
  {
    scenario: "AWS Glue replacement",
    detail:
      "Workloads migrating from Glue where the primary goal is eliminating the per-DPU hour cost, not adding governance.",
  },
];

const COMPARE_ROWS = [
  { capability: "Persistent warm capacity", serverless: false, sp: true },
  { capability: "Lower startup latency with warm capacity", serverless: false, sp: true },
  { capability: "Kubernetes scheduling control", serverless: false, sp: true },
  { capability: "YuniKorn fair scheduling", serverless: false, sp: "partial" },
  { capability: "Per-run cost attribution", serverless: false, sp: true },
  { capability: "BYOC model (your VPC, your EKS)", serverless: false, sp: true },
  { capability: "Pre-dispatch policy enforcement", serverless: false, sp: "partial" },
  { capability: "Spot instance management", serverless: "partial", sp: true },
  { capability: "Full Spark conf surface", serverless: false, sp: true },
  { capability: "Zero cluster management", serverless: true, sp: false },
  { capability: "No minimum cluster cost", serverless: true, sp: false },
  { capability: "Automatic scaling to zero", serverless: true, sp: "partial" },
];

function Cell({ value }: { value: boolean | "partial" }) {
  if (value === true) return <span className="objection-cell objection-cell-yes" aria-label="Yes">Y</span>;
  if (value === false) return <span className="objection-cell objection-cell-no" aria-label="No">N</span>;
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
            EMR Serverless is a strong choice for some workloads. This page outlines the tradeoffs so platform teams
            can choose the right operating model.
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
            ~ indicates partial support. Spot in Serverless is available but without the
            placement control, diversification validation, or toleration management that
            SparkPilot provides on EKS.
          </p>
        </section>

        {/* Detailed tradeoffs */}
        <section className="objection-section objection-section-alt">
          <h2 className="objection-section-title">Tradeoff deep-dive</h2>
          <p className="objection-section-sub">
            These constraints matter in real production scenarios and should be evaluated against your workload profile.
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
            Honest answer: Serverless is better for some use cases. Here is when to choose it.
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
          <h2 className="objection-section-title">EMR Serverless path status</h2>
          <p>
            SparkPilot includes backend dispatch code for EMR Serverless. The current product focus is batch-first on
            EMR on EKS, with broader multi-engine operations planned next.
          </p>
          <p>
            If your immediate priority is low-ops ad-hoc execution, EMR Serverless may still be the better short-term
            choice while SparkPilot expands proven multi-engine parity.
          </p>
        </section>

        {/* CTA */}
        <section className="objection-cta">
          <h2>Evaluate both in your actual environment</h2>
          <p>
            We can help you model the latency, cost, and operational tradeoffs for your
            specific workload profile. No commitment required.
          </p>
          <div className="objection-cta-actions">
            <Link href="/contact" className="landing-btn landing-btn-primary">
              Talk to an engineer
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

