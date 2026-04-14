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
        <div className="landing-hero-badge">Existing customer route</div>
        <h2 className="landing-hero-title">{label}</h2>
        <p className="landing-hero-sub">
          This path is for existing customer workspaces.
        </p>
        <div className="landing-hero-actions">
          <a href={target} className="landing-btn landing-btn-primary">Existing customer: Continue to app</a>
          <a href="/contact" className="landing-btn landing-btn-secondary">New here? Request pilot</a>
        </div>
      </section>
    </div>
  );
}
