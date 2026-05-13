import { test, expect } from "@playwright/test";

test.describe("Getting started journey", () => {
  test("redirects UI /getting-started to marketing pilot guide", async ({ page }) => {
    await page.goto("/getting-started");

    await expect(page).toHaveURL(/https:\/\/(www\.)?sparkpilot\.cloud\/getting-started\/?/);

    await expect(
      page.getByRole("heading", { name: /How to launch a SparkPilot pilot without confusion/i }),
    ).toBeVisible();

    await expect(page.getByRole("heading", { name: /Recommended pilot sequence/i })).toBeVisible();

    await expect(page.getByRole("link", { name: /Request pilot/i }).first()).toBeVisible();

    await expect(page.getByRole("link", { name: /Existing customer sign in/i }).first()).toBeVisible();
  });
});
