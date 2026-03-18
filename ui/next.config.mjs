/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    const isDev = process.env.NODE_ENV === "development";

    // #58: Remove 'unsafe-inline' for scripts in production.
    // Use nonce-based script policy for production builds.
    const scriptSrc = isDev
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self'";

    // #59: Allowlist external OIDC issuer origins in CSP connect-src.
    // Driven by NEXT_PUBLIC_OIDC_ISSUER env var; deny-by-default for unknown origins.
    const oidcIssuer = (process.env.NEXT_PUBLIC_OIDC_ISSUER ?? "").trim().replace(/\/+$/, "");
    const connectSrcParts = ["'self'"];
    if (oidcIssuer) {
      try {
        const issuerOrigin = new URL(oidcIssuer).origin;
        if (issuerOrigin && issuerOrigin !== "null") {
          connectSrcParts.push(issuerOrigin);
        }
      } catch {
        // Invalid URL — keep deny-by-default
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
