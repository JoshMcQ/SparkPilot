import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const VALUES = [
  {
    title: "Honest over optimistic",
    body: "We document what's tested on real AWS and what isn't. Our business overview names what works and what hasn't been validated yet. We'd rather have a smaller, trusted product than a large one nobody can rely on.",
  },
  {
    title: "Pre-dispatch, not post-mortem",
    body: "Observability tools tell you what went wrong after a job ran. We prevent the bad run from starting. The value is in the gate, not the dashboard.",
  },
  {
    title: "Your cloud, your data",
    body: "SparkPilot runs in your AWS account. Your Spark job artifacts, S3 buckets, and VPC never leave your perimeter. BYOC isn't a feature — it's the foundation.",
  },
  {
    title: "Platform teams first",
    body: "Data engineers are the end users. Platform engineers are the buyers. We build for the person who has to set up IRSA bindings at midnight, not just the person who submits jobs.",
  },
];

const TIMELINE = [
  {
    date: "Feb 2026",
    event: "First preflight engine written — 20+ IAM, OIDC, and quota checks before job dispatch.",
  },
  {
    date: "Mar 3, 2026",
    event: "First real Spark job dispatched through SparkPilot on a live EKS cluster. EMR run ID 0000000375sa67p4h2n.",
  },
  {
    date: "Mar 18, 2026",
    event: "Second-operator validation — a non-author completed the full BYOC-Lite loop end-to-end on real AWS.",
  },
  {
    date: "Mar 2026",
    event: "Open-sourced core preflight and provider integrations. Airflow and Dagster providers published.",
  },
];

export default function AboutPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" style={{ paddingBottom: "clamp(24px, 3vw, 40px)" }}>
        <div className="landing-hero-badge">About</div>
        <h2 className="landing-hero-title">
          Built by platform engineers<br />
          <span className="landing-hero-accent">for platform engineers</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot exists because every company running Spark on EKS eventually builds the same internal control plane — and then maintains it forever. We built the third option.
        </p>
      </section>

      <section className="landing-section">
        <div className="about-mission">
          <div className="landing-section-badge">Mission</div>
          <h2 className="landing-section-title">The gap nobody was filling</h2>
          <div className="about-mission-body">
            <p>
              Runtime optimizers like Ocean for Apache Spark make running jobs cheaper. FinOps platforms like Kubecost show you what you spent. Observability tools like Unravel diagnose failures after the fact.
            </p>
            <p>
              None of them sit at <strong>pre-dispatch</strong> — the moment before a job starts, when you can still stop it. Before IAM misconfigurations waste startup cost. Before a team blows its monthly budget at 2 AM. Before a bad EMR release label causes a silent failure.
            </p>
            <p>
              That's where SparkPilot sits. We call it the workload contract: an enforceable declaration evaluated at submission time that a job is allowed to run, is likely to succeed, and will stay within defined cost and governance bounds.
            </p>
          </div>
        </div>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="landing-section-header">
          <div className="landing-section-badge">Values</div>
          <h2 className="landing-section-title">How we work</h2>
        </div>
        <div className="about-values-grid">
          {VALUES.map((v) => (
            <div key={v.title} className="about-value-card">
              <h3>{v.title}</h3>
              <p>{v.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-section" style={{ paddingTop: 0 }}>
        <div className="landing-section-header">
          <div className="landing-section-badge">Timeline</div>
          <h2 className="landing-section-title">How we got here</h2>
        </div>
        <div className="about-timeline">
          {TIMELINE.map((item) => (
            <div key={item.date} className="about-timeline-item">
              <div className="about-timeline-date">{item.date}</div>
              <div className="about-timeline-dot" aria-hidden="true" />
              <div className="about-timeline-event">{item.event}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="landing-cta">
        <h2>Want to know more?</h2>
        <p>
          We're happy to walk you through the architecture, the validation evidence, and how SparkPilot would fit your team's setup.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Talk to us</Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer" className="landing-btn landing-btn-secondary">
            View on GitHub
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
