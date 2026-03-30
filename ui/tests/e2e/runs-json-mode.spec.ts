import { test, expect } from "@playwright/test";

test.describe("runs JSON mode", () => {
  test("run submit card can switch to JSON mode", async ({ page }) => {
    await page.goto("/runs");

    await expect(page.getByRole("button", { name: "Form Mode" })).toBeVisible();
    await expect(page.getByRole("button", { name: "JSON Mode" })).toBeVisible();

    await page.getByRole("button", { name: "JSON Mode" }).click();

    await expect(page.getByText("Run Payload JSON")).toBeVisible();
    await expect(page.locator("textarea.json-textarea")).toBeVisible();
  });
});
