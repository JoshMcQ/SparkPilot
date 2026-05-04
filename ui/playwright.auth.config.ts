import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: "http://127.0.0.1:3130",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "node .next/standalone/server.js",
    url: "http://127.0.0.1:3130/",
    reuseExistingServer: true,
    timeout: 120_000,
    env: {
      PORT: "3130",
      HOSTNAME: "127.0.0.1",
      SPARKPILOT_API: "http://127.0.0.1:9999",
      SPARKPILOT_UI_ENFORCE_AUTH: "true",
      NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE: "false",
      NEXT_PUBLIC_OIDC_ISSUER: "https://issuer.example.com",
      NEXT_PUBLIC_OIDC_CLIENT_ID: "sparkpilot-ui",
      NEXT_PUBLIC_OIDC_REDIRECT_URI: "http://127.0.0.1:3130/auth/callback",
      NEXT_PUBLIC_OIDC_AUDIENCE: "sparkpilot-api",
      NEXT_PUBLIC_INTERNAL_OIDC_ISSUER: "https://internal-issuer.example.com",
      NEXT_PUBLIC_INTERNAL_OIDC_CLIENT_ID: "sparkpilot-internal-ui",
      NEXT_PUBLIC_INTERNAL_OIDC_REDIRECT_URI: "http://127.0.0.1:3130/auth/callback",
      NEXT_PUBLIC_INTERNAL_OIDC_AUDIENCE: "sparkpilot-internal-api",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
