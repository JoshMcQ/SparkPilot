import Link from "next/link";

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
          <Link href="/#engines">Supported Engines</Link>
          <Link href="/#integrations">Integrations</Link>
          <Link href="/#how-it-works">How It Works</Link>
          <Link href="/#compare">Why SparkPilot</Link>
          <Link href="/pricing">Pricing</Link>
        </div>
        <div className="landing-footer-col">
          <h4>Company</h4>
          <Link href="/about">About</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/contact">Sales</Link>
          <Link href="/login">Log In</Link>
        </div>
        <div className="landing-footer-col">
          <h4>Resources</h4>
          <Link href="https://github.com/JoshMcQ/SparkPilot" target="_blank" rel="noopener noreferrer">
            Documentation
          </Link>
          <Link href="https://github.com/JoshMcQ/SparkPilot/issues" target="_blank" rel="noopener noreferrer">
            Changelog
          </Link>
          <Link href="/security">Security</Link>
        </div>
      </div>
      <div className="landing-footer-bottom">
        <span>© 2026 SparkPilot. All rights reserved.</span>
        <span className="landing-footer-bottom-links">
          <Link href="/security">Security</Link>
          <Link href="/contact">Contact</Link>
        </span>
      </div>
    </footer>
  );
}
