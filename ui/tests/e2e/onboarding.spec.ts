import { test, expect } from "@playwright/test";

test.describe("AWS onboarding flow", () => {
  test("shows unauthenticated onboarding guidance", async ({ page }) => {
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: false }),
      });
    });

    await page.goto("/onboarding/aws");

    await expect(page.getByRole("heading", { name: /authenticate, verify scope, then provision byoc-lite safely/i })).toBeVisible();
    await expect(page.getByText("Not authenticated")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in with oidc/i })).toBeVisible();
    await expect(page.getByText(/Use OIDC sign-in to establish a browser session/i)).toBeVisible();
  });

  test("shows authenticated identity + environment visibility", async ({ page }) => {
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

    await page.goto("/onboarding/aws");

    await expect(page.getByText("Authenticated")).toBeVisible();
    await expect(page.getByText("josh@example.com", { exact: true })).toBeVisible();
    await expect(page.getByText(/Role: admin. Scoped environments: 1./i)).toBeVisible();
    await expect(page.getByText(/1 environment\(s\) visible in this session./i)).toBeVisible();
  });

  test("shows missing-scope state without crashing when auth/me is unavailable", async ({ page }) => {
    await page.route("**/api/auth/session", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ authenticated: true }),
      });
    });

    await page.route("**/api/sparkpilot/v1/auth/me", async (route) => {
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Access denied" }),
      });
    });

    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/onboarding/aws");

    await expect(page.getByText("Authenticated")).toBeVisible();
    await expect(page.getByText("Unknown")).toBeVisible();
    await expect(page.getByText(/Confirm \/v1\/auth\/me resolves your actor, tenant\/team scope/i)).toBeVisible();
    await expect(page.getByText(/Use the environment flow with a real customer role ARN/i)).toBeVisible();
  });
});
