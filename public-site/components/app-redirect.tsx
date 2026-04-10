"use client";

import { useEffect } from "react";
import { appHref } from "@/lib/app-url";

export function AppRedirect({ path, label }: { path: string; label: string }) {
  const target = appHref(path);

  useEffect(() => {
    window.location.replace(target);
  }, [target]);

  return (
    <div className="landing">
      <section className="landing-hero">
        <div className="landing-hero-badge">Redirecting</div>
        <h2 className="landing-hero-title">{label}</h2>
        <p className="landing-hero-sub">
          Taking you to the SparkPilot app.
        </p>
        <div className="landing-hero-actions">
          <a href={target} className="landing-btn landing-btn-primary">Continue</a>
          <a href="/" className="landing-btn landing-btn-secondary">Back to site</a>
        </div>
      </section>
    </div>
  );
}
