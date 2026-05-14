import { NextRequest, NextResponse } from "next/server";
import {
  clientFingerprintFromHeaders,
  contactFormValue,
  contactSubmissionPayloadFromForm,
  contactSubmitSecretFromEnv,
  createContactFormToken,
  isContactFormTokenValid,
} from "@/lib/contact-submit";
import { sparkpilotApiBase } from "@/lib/oidc-server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const CONTACT_FALLBACK_URL = "https://sparkpilot.cloud/contact/";
const ALLOWED_CONTACT_HOSTS = new Set(["sparkpilot.cloud", "www.sparkpilot.cloud"]);
const RATE_LIMIT_WINDOW_MS = 10 * 60 * 1000;
const RATE_LIMIT_MAX_SUBMISSIONS = 5;

type RateLimitEntry = {
  count: number;
  resetAt: number;
};

type ContactRateLimitGlobal = typeof globalThis & {
  __sparkpilotContactRateLimit?: Map<string, RateLimitEntry>;
};

function contactRateLimitStore(): Map<string, RateLimitEntry> {
  const contactGlobal = globalThis as ContactRateLimitGlobal;
  if (!contactGlobal.__sparkpilotContactRateLimit) {
    contactGlobal.__sparkpilotContactRateLimit = new Map<string, RateLimitEntry>();
  }
  return contactGlobal.__sparkpilotContactRateLimit;
}

function contactRedirectUrl(request: NextRequest, status: "sent" | "invalid" | "error"): URL {
  const referer = request.headers.get("Referer") ?? "";
  let target = new URL(CONTACT_FALLBACK_URL);
  try {
    const parsed = new URL(referer);
    if (ALLOWED_CONTACT_HOSTS.has(parsed.hostname) && parsed.pathname.startsWith("/contact")) {
      target = parsed;
    }
  } catch {
    // Keep the safe fallback.
  }
  target.searchParams.set("contact", status);
  return target;
}

function clientFingerprint(request: NextRequest): string {
  return clientFingerprintFromHeaders(request.headers);
}

function isRateLimited(request: NextRequest): boolean {
  const now = Date.now();
  const store = contactRateLimitStore();
  const key = clientFingerprint(request);
  const current = store.get(key);

  // Best-effort per-process backstop. The signed form token and server-side submit
  // token are the primary controls; this intentionally avoids centralized state.
  if (!current || current.resetAt <= now) {
    store.set(key, { count: 1, resetAt: now + RATE_LIMIT_WINDOW_MS });
    return false;
  }
  if (current.count >= RATE_LIMIT_MAX_SUBMISSIONS) {
    return true;
  }
  current.count += 1;
  return false;
}

function isAllowedFormSource(request: NextRequest): boolean {
  const origin = request.headers.get("Origin");
  if (origin) {
    try {
      return ALLOWED_CONTACT_HOSTS.has(new URL(origin).hostname);
    } catch {
      return false;
    }
  }

  const referer = request.headers.get("Referer");
  if (!referer) {
    return false;
  }
  try {
    return ALLOWED_CONTACT_HOSTS.has(new URL(referer).hostname);
  } catch {
    return false;
  }
}

function corsHeaders(request: NextRequest): Record<string, string> {
  const origin = request.headers.get("Origin") ?? "";
  try {
    if (origin && ALLOWED_CONTACT_HOSTS.has(new URL(origin).hostname)) {
      return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Cache-Control": "no-store",
        "Vary": "Origin",
      };
    }
  } catch {
    // Fall through to no CORS headers.
  }
  return {"Cache-Control": "no-store"};
}

export async function OPTIONS(request: NextRequest): Promise<NextResponse> {
  return new NextResponse(null, {
    status: 204,
    headers: corsHeaders(request),
  });
}

export async function GET(request: NextRequest): Promise<NextResponse> {
  if (!isAllowedFormSource(request)) {
    return NextResponse.json(
      { error: "Contact form source is not allowed." },
      { status: 403, headers: corsHeaders(request) },
    );
  }

  const secret = contactSubmitSecretFromEnv();
  const fingerprint = clientFingerprint(request);
  return NextResponse.json(
    { formToken: createContactFormToken(secret, fingerprint) },
    { headers: corsHeaders(request) },
  );
}

export async function POST(request: NextRequest): Promise<NextResponse> {
  if (!isAllowedFormSource(request)) {
    return NextResponse.redirect(contactRedirectUrl(request, "error"), { status: 303 });
  }

  let form: FormData;
  try {
    form = await request.formData();
  } catch {
    return NextResponse.redirect(contactRedirectUrl(request, "invalid"), { status: 303 });
  }

  const secret = contactSubmitSecretFromEnv();
  const formToken = contactFormValue(form, "formToken", 512);
  if (!isContactFormTokenValid(formToken, secret, clientFingerprint(request))) {
    return NextResponse.redirect(contactRedirectUrl(request, "error"), { status: 303 });
  }

  if (contactFormValue(form, "website", 255)) {
    return NextResponse.redirect(contactRedirectUrl(request, "sent"), { status: 303 });
  }

  if (isRateLimited(request)) {
    return NextResponse.redirect(contactRedirectUrl(request, "error"), { status: 303 });
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 15_000);
  try {
    const response = await fetch(`${sparkpilotApiBase().replace(/\/+$/, "")}/v1/public/contact`, {
      method: "POST",
      headers: {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Request-Id": crypto.randomUUID(),
      },
      body: JSON.stringify(contactSubmissionPayloadFromForm(form)),
      cache: "no-store",
      signal: controller.signal,
    });
    if (response.ok) {
      return NextResponse.redirect(contactRedirectUrl(request, "sent"), { status: 303 });
    }
    if (response.status === 400 || response.status === 422) {
      return NextResponse.redirect(contactRedirectUrl(request, "invalid"), { status: 303 });
    }
  } catch {
    // Fall through to the generic error redirect.
  } finally {
    clearTimeout(timeout);
  }
  return NextResponse.redirect(contactRedirectUrl(request, "error"), { status: 303 });
}
