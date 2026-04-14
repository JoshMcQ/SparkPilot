import type { Metadata } from "next";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import { appHref } from "@/lib/app-url";

export const metadata: Metadata = {
  title: "Getting Started | SparkPilot",
  description: "Getting started guide for SparkPilot onboarding.",
};

const FLOW_STEPS = [
  {
    id: "1",
    title: "Request pilot kickoff",
    detail: "Share your workload profile and goals so we can scope a focused pilot with clear success criteria.",
    cta: { label: "Request pilot", href: "/contact" },
  },
  {
    id: "2",
    title: "Confirm architecture and owner roles",
    detail: "Align environment ownership, identity model, and timeline before setup starts.",
    cta: { label: "Request pilot", href: "/contact" },
  },
  {
    id: "3",
    title: "Connect AWS and run onboarding",
    detail: "Platform admins complete authenticated onboarding to validate IAM, OIDC, namespace, and dispatch prerequisites.",
    cta: { label: "Existing customer: Sign in for onboarding", href: appHref("/login?next=%2Fonboarding%2Faws") },
  },
  {
    id: "4",
    title: "Submit first pilot run",
    detail: "Run one governed workload, review diagnostics and cost visibility, then decide production rollout next steps.",
    cta: { label: "Existing customer: Sign in to view runs", href: appHref("/login?next=%2Fruns") },
  },
];

const TRACKS = [
  {
    title: "I am evaluating SparkPilot as a buyer",
    audience: "Pilot owner",
    bullets: [
      "Start with a pilot kickoff call to define scope and success criteria.",
      "Confirm one workload family and one owner from platform engineering.",
      "Use pilot checkpoints to evaluate operational fit and commercial fit.",
      "Pilots are guided so teams can evaluate quickly with clear success criteria.",
    ],
  },
  {
    title: "I am the platform admin running setup",
    audience: "Platform owner",
    bullets: [
      "Complete authenticated onboarding once, then onboard users with role mapping.",
      "Validate OIDC trust, execution role bindings, namespace rules, and budget limits.",
      "Run the first governed job and share pilot outputs with stakeholders.",
      "After pilot sign-off, expand environments and user access in phases.",
    ],
  },
];

const START_OPTIONS = [
  {
    title: "New evaluator",
    detail: "I want a realistic pilot plan and a technical walkthrough for my team.",
    cta: { label: "Request pilot", href: "/contact" },
  },
  {
    title: "Existing customer user",
    detail: "I already have workspace access and need to continue onboarding or run operations.",
    cta: { label: "Existing customer sign in", href: appHref("/login?next=%2Fonboarding%2Faws") },
  },
  {
    title: "Existing customer admin",
    detail: "I own first-time setup and need access to onboarding and access controls.",
    cta: { label: "Existing customer admin: Sign in to manage access", href: appHref("/login?next=%2Faccess") },
  },
];

const CLI_COMMANDS = [
  "sparkpilot env-list",
  "sparkpilot run-submit",
  "sparkpilot run-list",
  "sparkpilot run-logs",
];

function TrackLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="inline-link">
      {label}
    </Link>
  );
}

export default function GettingStartedPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="getting-started-page">
        <div className="getting-started-hero">
          <div className="landing-section-badge">Pilot Start Guide</div>
          <h1 className="getting-started-title">How to launch a SparkPilot pilot without confusion</h1>
          <p className="getting-started-sub">
            SparkPilot starts with a guided pilot led by our team. Begin with pilot kickoff, then move into authenticated onboarding for setup and run operations.
          </p>
          <div className="landing-hero-actions">
            <Link href="/contact" className="landing-btn landing-btn-primary">Request pilot</Link>
            <Link href={appHref("/login?next=%2Fonboarding%2Faws")} className="landing-btn landing-btn-secondary">Existing customer sign in</Link>
          </div>
          <div className="getting-started-callout">
            Authenticated setup, runs, costs, and access management stay in the app. This page shows how to start a pilot.
          </div>
        </div>

          <div className="getting-started-sections">
          <div className="getting-started-section-title-row">
            <h2>Pick your starting point</h2>
            <p>Choose the path that matches your role so buyer and operator workflows stay separate.</p>
          </div>
          <div className="getting-started-grid">
            {START_OPTIONS.map((option) => (
              <article key={option.title} className="getting-started-card">
                <h3>{option.title}</h3>
                <p>{option.detail}</p>
                <TrackLink href={option.cta.href} label={option.cta.label} />
              </article>
            ))}
          </div>

          <div className="getting-started-section-title-row">
            <h2>Role-based tracks</h2>
            <p>Pilot owners and platform admins have different responsibilities during setup and evaluation.</p>
          </div>
          <div className="getting-started-grid">
            {TRACKS.map((track) => (
              <article key={track.title} className="getting-started-card">
                <div className="getting-started-step">{track.audience}</div>
                <h3>{track.title}</h3>
                <ul className="contact-expect-list">
                  {track.bullets.map((bullet) => (
                    <li key={bullet}>{bullet}</li>
                  ))}
                </ul>
              </article>
            ))}
          </div>

          <div className="getting-started-section-title-row">
            <h2>Recommended pilot sequence</h2>
            <p>Follow these steps in order to keep pilot execution clean and measurable.</p>
          </div>
          <div className="getting-started-grid">
            {FLOW_STEPS.map((step) => (
              <article key={step.id} className="getting-started-card">
                <div className="getting-started-step">Step {step.id}</div>
                <h3>{step.title}</h3>
                <p>{step.detail}</p>
                <TrackLink href={step.cta.href} label={step.cta.label} />
              </article>
            ))}
          </div>

          <div className="getting-started-section-title-row">
            <h2>Command line quickstart (after sign-in)</h2>
            <p>Use these commands after sign-in for operator workflows and CI automation.</p>
          </div>
          <div className="getting-started-grid">
            <article className="getting-started-card">
              <div className="getting-started-step">CLI</div>
              <h3>Submit and operate runs from terminal</h3>
              <ul className="contact-expect-list">
                {CLI_COMMANDS.map((cmd) => (
                  <li key={cmd}>
                    <code>{cmd}</code>
                  </li>
                ))}
              </ul>
              <p>Use the same authenticated workspace context as the dashboard and API.</p>
            </article>
          </div>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}

