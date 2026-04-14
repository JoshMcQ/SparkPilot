import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

const VALUES = [
  {
    title: "Honest over optimistic",
    body: "We keep product claims grounded in what customers can use now. We would rather be clear and reliable than broad and vague.",
  },
  {
    title: "Pre-dispatch, not post-mortem",
    body: "Observability tools tell you what went wrong after a job ran. We prevent the bad run from starting. The value is in the gate, not the dashboard.",
  },
  {
    title: "Your cloud, your data",
    body: "SparkPilot runs in your AWS account. Your Spark job artifacts, S3 buckets, and VPC stay in your perimeter. BYOC is the foundation.",
  },
  {
    title: "Platform teams first",
    body: "Data engineers are the end users. Platform engineers are the buyers. We build for the person who has to set up IRSA bindings at midnight, not just the person who submits jobs.",
  },
];

const TIMELINE = [
  {
    date: "Feb 2026",
    event: "First preflight engine shipped with IAM, OIDC, and quota checks before job dispatch.",
  },
  {
    date: "Mar 3, 2026",
    event: "First production Spark job ran through SparkPilot on a live EKS cluster.",
  },
  {
    date: "Mar 18, 2026",
    event: "A second platform team completed BYOC-Lite setup and first run end-to-end.",
  },
  {
    date: "Mar 2026",
    event: "Open-sourced core preflight and provider integrations. Airflow and Dagster providers are available from source.",
  },
];

export default function AboutPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero landing-hero-compact">
        <div className="landing-hero-badge">About</div>
        <h1 className="landing-hero-title">
          Built by platform engineers<br />
          <span className="landing-hero-accent">for platform engineers</span>
        </h1>
        <p className="landing-hero-sub">
          SparkPilot exists because teams running Spark on EKS eventually build the same control-plane layer and carry that maintenance forever. We built a faster pilot path and a cleaner rollout path.
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
              None of them sit at <strong>pre-dispatch</strong>, the moment before a job starts when you can still stop it. Before IAM misconfigurations waste startup cost. Before a team blows its monthly budget at 2 AM. Before a bad EMR release label causes a silent failure.
            </p>
            <p>
              That is where SparkPilot sits. SparkPilot checks each submission against governance and cost rules before dispatch.
            </p>
          </div>
        </div>
      </section>

      <section className="landing-section landing-section-flush">
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

      <section className="landing-section landing-section-flush">
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
        <h2>Want to scope your pilot architecture?</h2>
        <p>
          We can walk through architecture details, scope your pilot, and confirm technical fit in one call.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Request pilot</Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer" className="landing-btn landing-btn-secondary">
            View on GitHub
          </Link>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
