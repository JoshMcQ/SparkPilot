import Link from "next/link";
import { appHref } from "@/lib/app-url";

export function LandingFooter() {
  return (
    <footer className="landing-footer">
      <div className="landing-footer-grid">
        <div className="landing-footer-brand">
          <strong>SparkPilot</strong>
          <p>Pre-dispatch governance and cost control for Spark on AWS. Your data never leaves your account.</p>
        </div>
        <div className="landing-footer-col">
          <h4>Product</h4>
          <Link href="/#features">Capabilities</Link>
          <Link href="/#engines">Engine support</Link>
          <Link href="/integrations">Integrations</Link>
          <Link href="/#how-it-works">How It Works</Link>
          <Link href="/#compare">Why SparkPilot</Link>
          <Link href="/pricing">Pricing</Link>
        </div>
        <div className="landing-footer-col">
          <h4>Company</h4>
          <Link href="/about">About</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/contact">Start pilot evaluation</Link>
          <a href={appHref("/login")}>Existing customers only: Sign in</a>
        </div>
        <div className="landing-footer-col">
          <h4>Resources</h4>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer">
            Documentation
          </Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot/issues" target="_blank" rel="noopener noreferrer">
            Open issues
          </Link>
          <Link href="/getting-started">Pilot guide</Link>
          <Link href="/contact">Security contact</Link>
          <Link href="/why-not-diy">Why Not DIY?</Link>
          <Link href="/why-not-serverless">Why Not Serverless?</Link>
        </div>
      </div>
      <div className="landing-footer-bottom">
        <span>&copy; 2026 SparkPilot. All rights reserved.</span>
        <span className="landing-footer-bottom-links">
          <Link href="/contact">Start pilot evaluation</Link>
          <a href={appHref("/login")}>Existing customers only: Sign in</a>
        </span>
      </div>
    </footer>
  );
}
