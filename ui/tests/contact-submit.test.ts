import assert from "node:assert/strict";
import test from "node:test";

import {
  clientFingerprintFromHeaders,
  contactSubmitSecretFromEnv,
  createContactFormToken,
  isContactFormTokenValid,
} from "../lib/contact-submit";

const SECRET = "c".repeat(32);

test("contact form token validates for the same request fingerprint", () => {
  const headers = new Headers({
    "User-Agent": "UnitTestBrowser",
    "X-Forwarded-For": "198.51.100.10",
  });
  const fingerprint = clientFingerprintFromHeaders(headers);
  const token = createContactFormToken(SECRET, fingerprint, 1_000);

  assert.equal(isContactFormTokenValid(token, SECRET, fingerprint, 2_000), true);
});

test("contact form token rejects a different request fingerprint", () => {
  const token = createContactFormToken(SECRET, "fingerprint-a", 1_000);

  assert.equal(isContactFormTokenValid(token, SECRET, "fingerprint-b", 2_000), false);
});

test("contact form token rejects expired and malformed tokens", () => {
  const token = createContactFormToken(SECRET, "fingerprint-a", 1_000);

  assert.equal(isContactFormTokenValid(token, SECRET, "fingerprint-a", 31 * 60 * 1_000), false);
  assert.equal(isContactFormTokenValid("not-a-token", SECRET, "fingerprint-a", 2_000), false);
});

test("contact submit secret requires configured length", () => {
  const original = process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN;
  try {
    process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN = "too-short";
    assert.throws(() => contactSubmitSecretFromEnv(), /Missing SPARKPILOT_CONTACT_SUBMIT_TOKEN/);

    process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN = SECRET;
    assert.equal(contactSubmitSecretFromEnv(), SECRET);
  } finally {
    if (original === undefined) {
      delete process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN;
    } else {
      process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN = original;
    }
  }
});
