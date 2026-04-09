import type { Metadata } from "next";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

export const metadata: Metadata = {
  title: "Getting Started | SparkPilot",
  description: "Public pre-access guide for SparkPilot onboarding.",
};

const FLOW_STEPS = [
  {
    id: "1",
    title: "Request access",
    detail: "If your team has not provisioned SparkPilot access yet, request access first.",
    cta: { label: "Request access", href: "/contact" },
  },
  {
    id: "2",
    title: "Sign in with SSO",
    detail: "Use your organization identity provider to start an authenticated session.",
    cta: { label: "Continue to login", href: "/login?next=%2Fonboarding%2Faws" },
  },
  {
    id: "3",
    title: "Enter product onboarding",
    detail: "After sign-in, continue in the authenticated Start Here flow to configure your workspace.",
    cta: { label: "Go to product onboarding", href: "/login?next=%2Fonboarding%2Faws" },
  },
  {
    id: "4",
    title: "Run and verify",
    detail: "Submit your first run from the UI or CLI, check diagnostics/logs, and verify usage/cost visibility.",
    cta: { label: "Open Runs after login", href: "/login?next=%2Fruns" },
  },
];

const TRACKS = [
  {
    title: "I am joining an existing SparkPilot workspace",
    audience: "Most users",
    bullets: [
      "Request access or invitation from your SparkPilot admin.",
      "Sign in with SSO and open Start Here onboarding.",
      "Create/select a job definition, submit a run, and verify costs.",
      "You should not need AWS IAM, CloudFormation, or Terraform access.",
    ],
  },
  {
    title: "I am the first admin setting up a new workspace",
    audience: "Platform/Admin owner",
    bullets: [
      "Set up the workspace once, then your end users follow the normal sign-in flow.",
      "Configure OIDC and create first admin identity mapping.",
      "Use assisted BYOC-Lite setup to discover cluster and suggested namespace.",
      "Run the first successful job, then onboard end users through Access and onboarding.",
    ],
  },
];

const START_OPTIONS = [
  {
    title: "I am an end user",
    detail: "I want to sign in and run jobs in an existing SparkPilot workspace.",
    cta: { label: "Sign in", href: "/login?next=%2Fonboarding%2Faws" },
  },
  {
    title: "I need access first",
    detail: "I do not have workspace access yet and need an admin to grant it.",
    cta: { label: "Request access", href: "/contact" },
  },
  {
    title: "I prefer command line workflows",
    detail: "I want to authenticate once, then submit and inspect runs from terminal automation.",
    cta: { label: "Sign in then use CLI", href: "/login?next=%2Fruns" },
  },
  {
    title: "I am the platform admin",
    detail: "I own first-time workspace setup and need the admin path.",
    cta: { label: "Open admin access", href: "/login?next=%2Faccess" },
  },
];

const CLI_COMMANDS = [
  "sparkpilot env-list",
  "sparkpilot run-submit",
  "sparkpilot run-list",
  "sparkpilot run-logs",
];

function ArrowLink({ href, label }: { href: string; label: string }) {
  return (
    <Link href={href} className="inline-link">
      {label} {"->"}
    </Link>
  );
}

export default function GettingStartedPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="getting-started-page">
        <div className="getting-started-hero">
          <div className="landing-section-badge">Public Pre-Access Guide</div>
          <h1 className="getting-started-title">Clear path from pre-access to authenticated onboarding</h1>
          <p className="getting-started-sub">
            This page is public and explains where to start. End users sign in and follow authenticated onboarding.
            Platform admins handle one-time
            workspace setup and access mapping for the current batch-first launch scope.
          </p>
          <div className="landing-hero-actions">
            <Link href="/login?next=%2Fonboarding%2Faws" className="landing-btn landing-btn-primary">Sign in and continue</Link>
            <Link href="/contact" className="landing-btn landing-btn-secondary">Request access</Link>
          </div>
          <div className="getting-started-callout">
            Public flow ends here. Product operations (Onboarding, Environments, Runs, Costs, Access) require sign-in.
            Interactive endpoints, advanced template/security workflows, Lake Formation depth, and broader runtime parity
            are not part of the current launch path yet.
          </div>
        </div>

        <div className="getting-started-sections">
          <div className="getting-started-section-title-row">
            <h2>Pick your starting point</h2>
            <p>Use the path that matches your role so onboarding stays clean and predictable.</p>
          </div>
          <div className="getting-started-grid getting-started-grid-3">
            {START_OPTIONS.map((option) => (
              <article key={option.title} className="getting-started-card">
                <h3>{option.title}</h3>
                <p>{option.detail}</p>
                <ArrowLink href={option.cta.href} label={option.cta.label} />
              </article>
            ))}
          </div>

          <div className="getting-started-section-title-row">
            <h2>Role-based tracks</h2>
            <p>End users and admins have different responsibilities during first-time setup.</p>
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
            <h2>Canonical onboarding sequence</h2>
            <p>Follow these gates in order to reach a successful first run with evidence.</p>
          </div>
          <div className="getting-started-grid">
            {FLOW_STEPS.map((step) => (
              <article key={step.id} className="getting-started-card">
                <div className="getting-started-step">Step {step.id}</div>
                <h3>{step.title}</h3>
                <p>{step.detail}</p>
                <ArrowLink href={step.cta.href} label={step.cta.label} />
              </article>
            ))}
          </div>

          <div className="getting-started-section-title-row">
            <h2>Command line quickstart (after sign-in)</h2>
            <p>SparkPilot supports terminal-first batch operations for platform teams and CI workflows.</p>
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
              <p>CLI auth uses OIDC client-credentials for service-style automation, not browser user sessions.</p>
            </article>
          </div>
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}

