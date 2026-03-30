"use client";

import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

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
    cta: { label: "Continue to login", href: "/login" },
  },
  {
    id: "3",
    title: "Complete guided onboarding",
    detail: "Follow the in-app start-here steps to create environment, job template, and first run.",
    cta: { label: "Continue to onboarding", href: "/onboarding/aws" },
  },
  {
    id: "4",
    title: "Run and verify",
    detail: "Submit first run, check diagnostics/logs, and verify usage/cost visibility.",
    cta: { label: "Open Runs", href: "/runs" },
  },
];

const TRACKS = [
  {
    title: "I'm joining an existing SparkPilot workspace",
    audience: "Most users",
    bullets: [
      "Request access or invitation from your SparkPilot admin.",
      "Sign in with SSO and open Start Here onboarding.",
      "Create/select a job template, submit a run, and verify costs.",
      "You should not need AWS IAM, CloudFormation, or Terraform access.",
    ],
  },
  {
    title: "I'm the first admin setting up a new workspace",
    audience: "Platform/Admin owner",
    bullets: [
      "Set up the workspace once, then your end users follow the normal sign-in flow.",
      "Configure OIDC and create first admin identity mapping.",
      "Use assisted BYOC-Lite setup to discover cluster + suggested namespace.",
      "Run first successful job, then onboard end users through Access and onboarding.",
    ],
  },
];

const START_OPTIONS = [
  {
    title: "I am an end user",
    detail: "I just want to sign in and run jobs in an existing SparkPilot workspace.",
    cta: { label: "Sign in", href: "/login" },
  },
  {
    title: "I need access first",
    detail: "I do not have workspace access yet and need an admin to grant it.",
    cta: { label: "Request access", href: "/contact" },
  },
  {
    title: "I am the platform admin",
    detail: "I own first-time workspace setup and want the admin path.",
    cta: { label: "Open admin access", href: "/access" },
  },
];

export default function GettingStartedPage() {
  return (
    <div className="landing">
      <LandingNav />

      <section className="getting-started-page">
        <div className="getting-started-hero">
          <div className="landing-section-badge">Getting Started</div>
          <h1 className="getting-started-title">Clear path from signup to first successful run</h1>
          <p className="getting-started-sub">
            Start by choosing your role. End users sign in and follow guided onboarding. Platform admins handle one-time
            workspace setup and access mapping.
          </p>
          <div className="landing-hero-actions">
            <Link href="/login" className="landing-btn landing-btn-primary">Start guided setup</Link>
            <Link href="/contact" className="landing-btn landing-btn-secondary">Request access</Link>
          </div>
          <div className="getting-started-callout">
            No public self-signup yet. If you are not the platform admin, start with access request and sign-in.
            AWS bootstrap steps are admin-only.
          </div>
        </div>

        <div className="getting-started-grid">
          {START_OPTIONS.map((option) => (
            <article key={option.title} className="getting-started-card">
              <h3>{option.title}</h3>
              <p>{option.detail}</p>
              <Link href={option.cta.href} className="inline-link">{option.cta.label} →</Link>
            </article>
          ))}
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

        <div className="getting-started-grid">
          {FLOW_STEPS.map((step) => (
            <article key={step.id} className="getting-started-card">
              <div className="getting-started-step">Step {step.id}</div>
              <h3>{step.title}</h3>
              <p>{step.detail}</p>
              <Link href={step.cta.href} className="inline-link">{step.cta.label} →</Link>
            </article>
          ))}
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
