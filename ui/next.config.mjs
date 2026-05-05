import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const staticAllowedDevOrigins = [
  "8c0f-76-109-132-91.ngrok-free.app",
  "b62b-76-109-132-91.ngrok-free.app",
];
const extraAllowedDevOrigins = (process.env.NEXT_ALLOWED_DEV_ORIGINS ?? "")
  .split(",")
  .map((origin) => origin.trim())
  .filter(Boolean);
const allowedDevOrigins = Array.from(new Set([
  ...staticAllowedDevOrigins,
  ...extraAllowedDevOrigins,
]));

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  allowedDevOrigins,
  turbopack: {
    root: __dirname,
  },
  async headers() {
    const isDev = process.env.NODE_ENV === "development";

    // Next.js emits small inline runtime/bootstrap scripts in production.
    // Keep unsafe-inline until a nonce-based CSP is fully wired end-to-end.
    const scriptSrc = isDev
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self' 'unsafe-inline'";

    // #59: Allowlist external OIDC issuer origins in CSP connect-src.
    // Driven by customer/internal OIDC issuer env vars; deny-by-default for unknown origins.
    const oidcIssuers = [
      process.env.NEXT_PUBLIC_OIDC_ISSUER,
      process.env.NEXT_PUBLIC_INTERNAL_OIDC_ISSUER,
    ]
      .map((issuer) => (issuer ?? "").trim().replace(/\/+$/, ""))
      .filter(Boolean);
    const connectSrcParts = ["'self'"];
    for (const oidcIssuer of oidcIssuers) {
      try {
        const issuerUrl = new URL(oidcIssuer);
        const issuerOrigin = issuerUrl.origin;
        if (issuerOrigin && issuerOrigin !== "null" && !connectSrcParts.includes(issuerOrigin)) {
          connectSrcParts.push(issuerOrigin);
        }
        // Cognito often serves discovery on cognito-idp.* while token exchange
        // uses the hosted auth domain (*.amazoncognito.com).
        if (issuerUrl.hostname.includes("cognito-idp.") && !connectSrcParts.includes("https://*.amazoncognito.com")) {
          connectSrcParts.push("https://*.amazoncognito.com");
        }
      } catch {
        // Invalid URL - keep deny-by-default
      }
    }
    // Allow additional OIDC connect origins via env var (comma-separated)
    const extraOidcOrigins = (process.env.NEXT_PUBLIC_OIDC_CONNECT_ORIGINS ?? "").trim();
    if (extraOidcOrigins) {
      for (const origin of extraOidcOrigins.split(",")) {
        const trimmed = origin.trim();
        if (trimmed) {
          try {
            const parsed = new URL(trimmed).origin;
            if (parsed && parsed !== "null" && !connectSrcParts.includes(parsed)) {
              connectSrcParts.push(parsed);
            }
          } catch {
            // Skip invalid entries
          }
        }
      }
    }
    const connectSrc = `connect-src ${connectSrcParts.join(" ")}`;

    const csp = [
      "default-src 'self'",
      scriptSrc,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self' data:",
      connectSrc,
      "object-src 'none'",
      "base-uri 'self'",
      "form-action 'self'",
      "frame-ancestors 'none'",
    ].join("; ");

    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: csp,
          },
          {
            key: "X-Content-Type-Options",
            value: "nosniff",
          },
          {
            key: "X-Frame-Options",
            value: "DENY",
          },
          {
            key: "Referrer-Policy",
            value: "strict-origin-when-cross-origin",
          },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
