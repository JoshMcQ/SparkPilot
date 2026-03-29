import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: {
    timeout: 5_000,
  },
  fullyParallel: false,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:3001",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "npm run dev -- --hostname 127.0.0.1 --port 3001",
    url: "http://127.0.0.1:3001/",
    reuseExistingServer: false,
    timeout: 120_000,
    env: {
      NEXT_PUBLIC_OIDC_ISSUER: "https://issuer.example.com",
      NEXT_PUBLIC_OIDC_CLIENT_ID: "sparkpilot-ui",
      NEXT_PUBLIC_OIDC_REDIRECT_URI: "http://127.0.0.1:3001/auth/callback",
      SPARKPILOT_API: "http://127.0.0.1:9999",
    },
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] },
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] },
    },
  ],
});
