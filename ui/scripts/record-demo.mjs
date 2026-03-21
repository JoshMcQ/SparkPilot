import fs from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";

const root = process.cwd();
const videoDir = path.join(root, "artifacts", "demo-temp-video");
const outputDir = path.join(root, "artifacts", "demo");
const outputPath = path.join(outputDir, "sparkpilot-ui-demo-20260319.webm");

await fs.rm(videoDir, { recursive: true, force: true });
await fs.mkdir(videoDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  recordVideo: { dir: videoDir, size: { width: 1440, height: 900 } },
});
const page = await context.newPage();

await page.route("**/api/auth/session", async (route) => {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ authenticated: true }),
  });
});

await page.route("**/api/sparkpilot/v1/auth/me", async (route) => {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      actor: "josh@example.com",
      role: "admin",
      tenant_id: "tenant-123",
      team_id: "team-456",
      scoped_environment_ids: ["env-1"],
    }),
  });
});

await page.route("**/api/sparkpilot/v1/environments", async (route) => {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify([
      {
        id: "env-1",
        tenant_id: "tenant-123",
        cloud: "aws",
        region: "us-east-1",
        engine: "emr_on_eks",
        status: "ready",
        provisioning_mode: "byoc_lite",
        customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRoleAdmin",
        eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/sparkpilot-live-1",
        eks_namespace: "sparkpilot-demo-2",
        emr_virtual_cluster_id: "vc-123",
        warm_pool_enabled: false,
        max_concurrent_runs: 10,
        max_vcpu: 256,
        max_run_seconds: 7200,
        created_at: "2026-03-19T13:00:00Z",
        updated_at: "2026-03-19T13:00:00Z",
      },
    ]),
  });
});

const base = "http://127.0.0.1:3001";
await page.goto(`${base}/onboarding/aws`);
await page.waitForTimeout(1200);

await page.getByRole("button", { name: /switch to dark mode|toggle theme/i }).click();
await page.waitForTimeout(800);

await page.getByRole("link", { name: /open environments/i }).click();
await page.waitForTimeout(1200);

await page.getByRole("link", { name: /open aws onboarding/i }).click();
await page.waitForTimeout(1000);

await page.evaluate(() => window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" }));
await page.waitForTimeout(1200);
await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
await page.waitForTimeout(1200);

const video = page.video();
await page.close();
await context.close();
await browser.close();

if (!video) {
  throw new Error("No Playwright video handle was created.");
}

const tempVideoPath = await video.path();
await fs.rm(outputPath, { force: true });
await fs.copyFile(tempVideoPath, outputPath);
console.log(outputPath);
