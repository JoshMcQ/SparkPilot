import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

export default function SecurityPage() {
  return (
    <div className="landing">
      <LandingNav />
      <section className="landing-hero">
        <div className="landing-hero-badge">Security</div>
        <h2 className="landing-hero-title">
          Security posture for <span className="landing-hero-accent">enterprise Spark operations</span>
        </h2>
        <p className="landing-hero-sub">
          SparkPilot is BYOC-first: workload execution and data remain in your AWS account boundary.
          Contact us for architecture, access controls, and deployment details.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Contact security</Link>
          <a
            href="https://github.com/JoshMcQ/SparkPilot"
            target="_blank"
            rel="noopener noreferrer"
            className="landing-btn landing-btn-secondary"
          >
            View repository
          </a>
        </div>
      </section>
      <LandingFooter />
    </div>
  );
}
