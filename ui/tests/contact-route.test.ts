import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  clientFingerprintFromHeaders,
  createContactFormToken,
} from "../lib/contact-submit";

const routeSource = readFileSync(new URL("../app/api/contact/route.ts", import.meta.url), "utf8");
const CONTACT_SECRET = "c".repeat(32);

test("contact proxy stores public leads through the canonical submission API", () => {
  assert.doesNotMatch(routeSource, /\/v1\/contact-requests/);
  assert.match(routeSource, /\/v1\/public\/contact/);
});

test("contact proxy POST forwards normalized form data to the canonical public contact API", async () => {
  const originalApiBase = process.env.SPARKPILOT_API;
  const originalContactSecret = process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN;
  const originalFetch = globalThis.fetch;
  const upstreamRequests: Array<{ url: string; init?: RequestInit }> = [];

  try {
    process.env.SPARKPILOT_API = "https://api.internal.example";
    process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN = CONTACT_SECRET;
    globalThis.fetch = async (url, init) => {
      upstreamRequests.push({ url: String(url), init });
      return new Response(JSON.stringify({ id: "lead-1" }), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    };

    const { POST } = await import("../app/api/contact/route");
    const headers = new Headers({
      "Content-Type": "application/x-www-form-urlencoded",
      "Origin": "https://sparkpilot.cloud",
      "Referer": "https://sparkpilot.cloud/contact/",
      "User-Agent": "UnitTestBrowser",
      "X-Forwarded-For": "198.51.100.42",
    });
    const formToken = createContactFormToken(
      CONTACT_SECRET,
      clientFingerprintFromHeaders(headers),
      Date.now(),
    );
    const body = new URLSearchParams({
      formToken,
      name: " Joshua McQueary ",
      email: " Joshua@Example.Invalid ",
      company: " Agent Works Group ",
      useCase: "Pilot evaluation",
      message: " Looking to use SparkPilot for AWS Spark needs. ",
      website: "",
    });

    const response = await POST(new Request("https://app.sparkpilot.cloud/api/contact", {
      body,
      headers,
      method: "POST",
    }) as never);

    assert.equal(response.status, 303);
    assert.equal(upstreamRequests.length, 1);
    assert.equal(upstreamRequests[0].url, "https://api.internal.example/v1/public/contact");
    assert.equal(upstreamRequests[0].init?.method, "POST");
    assert.equal(upstreamRequests[0].init?.cache, "no-store");
    assert.equal(
      (upstreamRequests[0].init?.headers as Record<string, string>)["Content-Type"],
      "application/json",
    );
    assert.deepEqual(JSON.parse(String(upstreamRequests[0].init?.body)), {
      name: "Joshua McQueary",
      email: "joshua@example.invalid",
      company: "Agent Works Group",
      use_case: "Pilot evaluation",
      message: "Looking to use SparkPilot for AWS Spark needs.",
    });
  } finally {
    if (originalApiBase === undefined) {
      delete process.env.SPARKPILOT_API;
    } else {
      process.env.SPARKPILOT_API = originalApiBase;
    }
    if (originalContactSecret === undefined) {
      delete process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN;
    } else {
      process.env.SPARKPILOT_CONTACT_SUBMIT_TOKEN = originalContactSecret;
    }
    globalThis.fetch = originalFetch;
  }
});
