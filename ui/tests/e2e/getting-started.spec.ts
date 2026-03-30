import { test, expect } from "@playwright/test";

test.describe("Getting started journey", () => {
  test("shows clear signup-to-first-run path", async ({ page }) => {
    await page.goto("/getting-started");

    await expect(
      page.getByRole("heading", { name: /clear path from signup to first successful run/i })
    ).toBeVisible();

    await expect(page.getByText("Step 1")).toBeVisible();
    await expect(page.getByText("Step 2")).toBeVisible();
    await expect(page.getByText("Step 3")).toBeVisible();
    await expect(page.getByText("Step 4")).toBeVisible();

    await expect(page.getByRole("link", { name: /start guided setup/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /request access/i }).first()).toBeVisible();
    await expect(page.getByRole("link", { name: /continue to login/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /continue to onboarding/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /open runs/i })).toBeVisible();
  });
});
