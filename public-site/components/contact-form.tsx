"use client";

import type { ChangeEvent, FormEvent } from "react";

export type ContactFormState = "idle" | "submitting" | "success" | "error" | "invalid";

export type ContactFormValues = {
  name: string;
  email: string;
  company: string;
  useCase: string;
  message: string;
};

type ContactFormProps = {
  contactEndpoint: string;
  errorMessage: string | null;
  form: ContactFormValues;
  formToken: string;
  onChange: (event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  state: ContactFormState;
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

export function ContactForm({
  contactEndpoint,
  errorMessage,
  form,
  formToken,
  onChange,
  onSubmit,
  state,
}: ContactFormProps) {
  return (
    <form
      className="contact-form"
      action={contactEndpoint}
      method="post"
      onSubmit={onSubmit}
      noValidate
    >
      {(state === "error" || state === "invalid") && errorMessage && (
        <div className="contact-form-error" role="alert">
          {errorMessage}
        </div>
      )}

      <input type="hidden" name="formToken" value={formToken} />
      <div className="contact-honeypot" aria-hidden="true">
        <label htmlFor="website">Website</label>
        <input
          id="website"
          name="website"
          type="text"
          tabIndex={-1}
          autoComplete="off"
        />
      </div>

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
            onChange={onChange}
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
            onChange={onChange}
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
          onChange={onChange}
        />
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor="useCase">What brings you here?</label>
        <select
          id="useCase"
          name="useCase"
          className="form-input form-select"
          value={form.useCase}
          onChange={onChange}
        >
          <option value="">Select one...</option>
          {USE_CASES.map((useCase) => (
            <option key={useCase} value={useCase}>{useCase}</option>
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
          onChange={onChange}
        />
      </div>

      <button
        type="submit"
        className="landing-btn landing-btn-primary contact-submit"
        disabled={state === "submitting" || !formToken || !form.name.trim() || !form.email.trim()}
      >
        {state === "submitting" ? "Sending..." : "Get in touch"}
      </button>
    </form>
  );
}
