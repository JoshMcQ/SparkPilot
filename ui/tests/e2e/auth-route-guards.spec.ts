import { test, expect } from "@playwright/test";

test.describe("auth route guards", () => {
  test("unauthenticated navigation redirects protected routes and keeps public start page public", async ({ page }) => {
    await page.context().clearCookies();

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login\?next=%2Fdashboard$/);

    await page.goto("/onboarding/aws");
    await expect(page).toHaveURL(/\/login\?next=%2Fonboarding%2Faws$/);

    await page.goto("/internal/tenants");
    await expect(page).toHaveURL(/\/login\?next=%2Finternal%2Ftenants&pool=internal$/);

    await page.goto("/getting-started");
    await expect(page).toHaveURL("https://sparkpilot.cloud/getting-started/");
  });

  test("authenticated session can enter protected product routes", async ({ page }) => {
    await page.context().clearCookies();

    const session = await page.request.post("/api/auth/session", {
      data: { access_token: "e2e.dummy.token" },
      headers: { "Content-Type": "application/json" },
    });
    expect(session.ok()).toBeTruthy();

    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/dashboard$/);

    await page.goto("/onboarding/aws");
    await expect(page).toHaveURL(/\/onboarding\/aws$/);

    await page.goto("/settings");
    await expect(page).toHaveURL(/\/settings$/);
  });
});
