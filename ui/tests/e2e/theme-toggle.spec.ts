import { test, expect } from "@playwright/test";

test.describe("theme toggle", () => {
  test("switches to dark mode and persists after reload", async ({ page }) => {
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: false }),
      });
    });

    await page.goto("/onboarding/aws");
    await expect(page.locator("html")).not.toHaveAttribute("data-theme", "dark");

    await page.getByRole("button", { name: /switch to dark mode/i }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("button", { name: /switch to light mode/i })).toBeVisible();

    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await expect(page.getByRole("button", { name: /switch to light mode/i })).toBeVisible();
  });
});
