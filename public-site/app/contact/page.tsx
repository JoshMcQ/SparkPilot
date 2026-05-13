"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import { API_URL } from "@/lib/api-url";

type FormState = "idle" | "submitting" | "success" | "error" | "invalid";

const USE_CASES = [
  "Pilot evaluation",
  "Production rollout planning",
  "EMR on EKS governance",
  "EMR Serverless governance",
  "Cost attribution and FinOps",
  "Airflow or Dagster integration",
  "Other",
];

const CONTACT_EMAIL = "hello@sparkpilot.cloud";

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", useCase: "", message: "" });
  const [state, setState] = useState<FormState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const contactStatus = params.get("contact");
    if (contactStatus === "sent") {
      setState("success");
      return;
    } else if (contactStatus === "invalid") {
      setState("invalid");
    } else if (contactStatus === "error") {
      setState("error");
    }
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setState("submitting");
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_URL}/v1/public/contact`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name.trim(),
          email: form.email.trim(),
          company: form.company.trim() || undefined,
          use_case: form.useCase || undefined,
          message: form.message.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? "Something went wrong. Please try again.");
      }
      setState("success");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Something went wrong. Please try again.");
      setState("error");
    }
  }

  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero landing-hero-compact">
        <div className="landing-hero-badge">Contact</div>
        <h1 className="landing-hero-title">
          Book a pilot conversation<br />
          <span className="landing-hero-accent">for your Spark platform</span>
        </h1>
        <p className="landing-hero-sub">
          We will quickly assess fit, define pilot scope, and align ownership for execution.
        </p>
      </section>

      <section className="contact-layout">
        <div className="contact-info">
          <div className="contact-info-block">
            <h3>What to expect</h3>
            <ul className="contact-expect-list">
              <li>Typical response time is within one business day</li>
              <li>A focused technical call to understand your workload profile</li>
              <li>Clear pilot recommendation with next steps</li>
            </ul>
          </div>

          <div className="contact-info-block">
            <h3>Good conversations to have</h3>
            <ul className="contact-expect-list">
              <li>You run EMR on EKS or EMR Serverless and need governed self-service for data teams</li>
              <li>You need per-team cost attribution reconciled against CUR</li>
              <li>You want a pilot path before committing to a larger rollout</li>
              <li>You have a specific preflight or policy requirement</li>
            </ul>
          </div>

          <div className="contact-info-block">
            <h3>Direct email</h3>
            <a href={`mailto:${CONTACT_EMAIL}`} className="contact-email-link">
              {CONTACT_EMAIL}
            </a>
          </div>
        </div>

        <div className="contact-form-wrap">
          {state === "success" ? (
            <div className="contact-success">
              <div className="contact-success-icon" aria-hidden="true">OK</div>
              <h3>We got it.</h3>
              <p>
                Thanks for reaching out. We will review your message and get back to you
                within one business day at <strong>{form.email}</strong>.
              </p>
              <Link href="/" className="landing-btn landing-btn-secondary contact-success-back">
                Back to home
              </Link>
            </div>
          ) : (
            <form className="contact-form" onSubmit={handleSubmit} noValidate>
              {state === "error" && errorMessage && (
                <div className="contact-form-error" role="alert">
                  {errorMessage}
                </div>
              )}

              <div className="contact-form-row">
                <div className="form-group">
                  <label className="form-label" htmlFor="name">Name</label>
                  <input
                    id="name"
                    name="name"
                    type="text"
                    className="form-input"
                    placeholder="Alex Smith"
                    value={form.name}
                    onChange={handleChange}
                    required
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" htmlFor="email">Work email</label>
                  <input
                    id="email"
                    name="email"
                    type="email"
                    className="form-input"
                    placeholder="alex@company.com"
                    value={form.email}
                    onChange={handleChange}
                    required
                  />
                </div>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="company">Company</label>
                <input
                  id="company"
                  name="company"
                  type="text"
                  className="form-input"
                  placeholder="Acme Corp"
                  value={form.company}
                  onChange={handleChange}
                />
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="useCase">What brings you here?</label>
                <select
                  id="useCase"
                  name="useCase"
                  className="form-input form-select"
                  value={form.useCase}
                  onChange={handleChange}
                >
                  <option value="">Select one...</option>
                  {USE_CASES.map((uc) => (
                    <option key={uc} value={uc}>{uc}</option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label className="form-label" htmlFor="message">Tell us more</label>
                <textarea
                  id="message"
                  name="message"
                  className="form-input form-textarea"
                  placeholder="Describe your current setup, the problem you're trying to solve, or any questions you have..."
                  rows={5}
                  value={form.message}
                  onChange={handleChange}
                />
              </div>

              <button
                type="submit"
                className="landing-btn landing-btn-primary contact-submit"
                disabled={state === "submitting" || !form.name || !form.email}
              >
                {state === "submitting" ? "Sending..." : "Get in touch"}
              </button>
            </form>
          )}
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
