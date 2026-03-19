import { test, expect } from "@playwright/test";

const VIEWPORTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "desktop-1440", width: 1440, height: 900 },
];

for (const viewport of VIEWPORTS) {
  test(`onboarding layout remains usable at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });

    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: false }),
      });
    });

    await page.goto("/onboarding/aws");

    await expect(page.getByRole("heading", { name: /authenticate, verify scope, then provision byoc-lite safely/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in with oidc/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /open environment setup/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /operator checklist/i })).toBeVisible();

    const hero = page.locator(".onboarding-hero");
    await expect(hero).toBeVisible();
    const heroBox = await hero.boundingBox();
    if (!heroBox) throw new Error(`Missing hero bounding box at ${viewport.name}`);
    expect(heroBox.width).toBeGreaterThan(280);
    expect(heroBox.x).toBeGreaterThanOrEqual(0);

    const pageMain = page.locator("main.page");
    const pageBox = await pageMain.boundingBox();
    if (!pageBox) throw new Error(`Missing page bounding box at ${viewport.name}`);
    expect(pageBox.width).toBeLessThanOrEqual(viewport.width + 2);
  });
}
