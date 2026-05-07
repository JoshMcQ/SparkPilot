"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import { appHref } from "@/lib/app-url";

type FormState = "idle" | "submitting" | "success" | "error" | "invalid";
type ContactTokenResponse = {
  formToken?: string;
};

const USE_CASES = [
  "Pilot evaluation",
  "Production rollout planning",
  "EMR on EKS governance",
  "EMR Serverless governance",
  "Cost attribution and FinOps",
  "Airflow or Dagster integration",
  "Other",
];

const CONTACT_EMAIL = "jmcqueary@sparkpilot.cloud";
const CONTACT_ENDPOINT = appHref("/api/contact");

export default function ContactPage() {
  const [form, setForm] = useState({ name: "", email: "", company: "", useCase: "", message: "" });
  const [formToken, setFormToken] = useState("");
  const [state, setState] = useState<FormState>("idle");

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

    const controller = new AbortController();
    async function loadFormToken() {
      try {
        const response = await fetch(CONTACT_ENDPOINT, {
          cache: "no-store",
          credentials: "omit",
          signal: controller.signal,
        });
        const body = (await response.json()) as ContactTokenResponse;
        if (!response.ok || typeof body.formToken !== "string" || !body.formToken) {
          throw new Error("Contact form token request failed.");
        }
        setFormToken(body.formToken);
      } catch (error) {
        if ((error as Error).name === "AbortError") {
          return;
        }
        setState((current) => (current === "idle" ? "error" : current));
      }
    }
    void loadFormToken();
    return () => controller.abort();
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit() {
    setState("submitting");
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
              <h3>Your request was sent.</h3>
              <p>We received your pilot request. Replies go to the work email you provided.</p>
              <Link href="/" className="landing-btn landing-btn-secondary contact-success-back">
                Back to home
              </Link>
            </div>
          ) : (
            <form className="contact-form" action={CONTACT_ENDPOINT} method="post" onSubmit={handleSubmit}>
              {state === "error" ? (
                <div className="contact-error" role="alert">
                  We could not send this request. Email{" "}
                  <a href={`mailto:${CONTACT_EMAIL}`} className="login-link">{CONTACT_EMAIL}</a>{" "}
                  directly while we fix the form endpoint.
                </div>
              ) : null}
              {state === "invalid" ? (
                <div className="contact-error" role="alert">
                  Check your name and work email, then send the request again.
                </div>
              ) : null}
              <div className="contact-honeypot" aria-hidden="true">
                <label htmlFor="website">Website</label>
                <input id="website" name="website" type="text" tabIndex={-1} autoComplete="off" />
              </div>
              <input type="hidden" name="formToken" value={formToken} />
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
                disabled={state === "submitting" || !formToken || !form.name || !form.email}
              >
                {state === "submitting" ? "Sending..." : "Send request"}
              </button>
            </form>
          )}
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
