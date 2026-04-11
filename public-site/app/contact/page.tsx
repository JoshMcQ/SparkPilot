"use client";

import { useState } from "react";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";

type FormState = "idle" | "submitting" | "success" | "error";

const USE_CASES = [
  "Pilot evaluation",
  "Production rollout planning",
  "Multi-tenant Spark governance",
  "Cost attribution and FinOps",
  "Airflow or Dagster integration",
  "Other",
];

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", useCase: "", message: "" });
  const [state, setState] = useState<FormState>("idle");

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setState("submitting");
    // mailto fallback; replace with a real form endpoint when available
    const subject = encodeURIComponent(`SparkPilot inquiry from ${form.name} at ${form.company}`);
    const body = encodeURIComponent(
      `Name: ${form.name}\nEmail: ${form.email}\nCompany: ${form.company}\nUse case: ${form.useCase}\n\n${form.message}`
    );
    window.location.href = `mailto:hello@sparkpilot.io?subject=${subject}&body=${body}`;
    setState("success");
  }

  return (
    <div className="landing">
      <LandingNav />

      <section className="landing-hero" style={{ paddingBottom: "clamp(24px, 3vw, 40px)" }}>
        <div className="landing-hero-badge">Contact</div>
        <h2 className="landing-hero-title">
          Book a pilot conversation<br />
          <span className="landing-hero-accent">for your Spark platform</span>
        </h2>
        <p className="landing-hero-sub">
          We will help you decide quickly whether SparkPilot is a fit, what a pilot should cover, and how to run it with clear ownership.
        </p>
      </section>

      <section className="contact-layout">
        <div className="contact-info">
          <div className="contact-info-block">
            <h3>What to expect</h3>
            <ul className="contact-expect-list">
              <li>Response within one business day</li>
              <li>A focused technical call to understand your workload profile</li>
              <li>Clear pilot recommendation with next steps</li>
            </ul>
          </div>

          <div className="contact-info-block">
            <h3>Good conversations to have</h3>
            <ul className="contact-expect-list">
              <li>You run EMR on EKS and need governed self-service for data teams</li>
              <li>You need per-team cost attribution reconciled against CUR</li>
              <li>You want a pilot path before committing to a larger rollout</li>
              <li>You have a specific preflight or policy requirement</li>
            </ul>
          </div>

          <div className="contact-info-block">
            <h3>Direct email</h3>
            <a href="mailto:hello@sparkpilot.io" className="contact-email-link">
              hello@sparkpilot.io
            </a>
          </div>
        </div>

        <div className="contact-form-wrap">
          {state === "success" ? (
            <div className="contact-success">
              <div className="contact-success-icon" aria-hidden="true">✓</div>
              <h3>Thanks, we'll be in touch.</h3>
              <p>Check your email client. Your message was pre-filled. If it did not open, email us directly at <a href="mailto:hello@sparkpilot.io" className="login-link">hello@sparkpilot.io</a>.</p>
              <Link href="/" className="landing-btn landing-btn-secondary" style={{ marginTop: "16px", display: "inline-flex" }}>
                Back to home
              </Link>
            </div>
          ) : (
            <form className="contact-form" onSubmit={handleSubmit} noValidate>
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
                {state === "submitting" ? "Opening email..." : "Request pilot call"}
              </button>
            </form>
          )}
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
