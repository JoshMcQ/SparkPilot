"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { LandingNav } from "@/components/landing-nav";
import { LandingFooter } from "@/components/landing-footer";
import { ContactForm, type ContactFormState, type ContactFormValues } from "@/components/contact-form";
import { APP_URL } from "@/lib/app-url";

const CONTACT_EMAIL = "hello@sparkpilot.cloud";
const CONTACT_ENDPOINT = `${APP_URL}/api/contact`;

export default function ContactPage() {
  const [form, setForm] = useState<ContactFormValues>({ name: "", email: "", company: "", useCase: "", message: "" });
  const [formToken, setFormToken] = useState("");
  const [state, setState] = useState<ContactFormState>("idle");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const params = new URLSearchParams(window.location.search);
    const contactStatus = params.get("contact");
    if (contactStatus === "sent") {
      setState("success");
      return () => {
        cancelled = true;
      };
    } else if (contactStatus === "invalid") {
      setState("invalid");
      setErrorMessage("Please check the required fields and try again.");
    } else if (contactStatus === "error") {
      setState("error");
      setErrorMessage("We could not send your request. Please try again or email us directly.");
    }

    fetch(CONTACT_ENDPOINT, { method: "GET", cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error("Contact form is unavailable.");
        }
        const body = await response.json();
        if (typeof body?.formToken !== "string" || !body.formToken) {
          throw new Error("Contact form token was not returned.");
        }
        return body.formToken;
      })
      .then((token) => {
        if (!cancelled) {
          setFormToken(token);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState("error");
          setErrorMessage("Contact form is temporarily unavailable. Please email us directly.");
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    if (!formToken) {
      e.preventDefault();
      setState("error");
      setErrorMessage("Contact form is still initializing. Please try again.");
      return;
    }
    setState("submitting");
    setErrorMessage(null);
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
                within one business day.
              </p>
              <Link href="/" className="landing-btn landing-btn-secondary contact-success-back">
                Back to home
              </Link>
            </div>
          ) : (
            <ContactForm
              contactEndpoint={CONTACT_ENDPOINT}
              errorMessage={errorMessage}
              form={form}
              formToken={formToken}
              onChange={handleChange}
              onSubmit={handleSubmit}
              state={state}
            />
          )}
        </div>
      </section>

      <LandingFooter />
    </div>
  );
}
