"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function SecurityPageRedirect() {
  useEffect(() => {
    window.location.replace("/contact");
  }, []);

  return (
    <div className="landing">
      <section className="landing-hero">
        <div className="landing-hero-badge">Redirecting</div>
        <h2 className="landing-hero-title">Security information moved</h2>
        <p className="landing-hero-sub">
          Security and policy details are handled through the contact and pilot evaluation flow.
        </p>
        <div className="landing-hero-actions">
          <Link href="/contact" className="landing-btn landing-btn-primary">Continue to contact</Link>
          <Link href="/" className="landing-btn landing-btn-secondary">Back to site</Link>
        </div>
      </section>
    </div>
  );
}

