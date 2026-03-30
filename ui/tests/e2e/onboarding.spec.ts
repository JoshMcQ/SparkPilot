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

    await expect(page.getByTestId("onboarding-title")).toHaveText(/guided onboarding to first successful spark run/i);
    await expect(page.getByTestId("session-status")).toHaveText("Not authenticated");
    await expect(
      page.getByRole("button", { name: /sign in with oidc/i }).or(page.getByRole("link", { name: /open login/i }))
    ).toBeVisible();
    await expect(page.getByText(/Start an authenticated browser session before using environments or runs./i).first()).toBeVisible();
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
            instance_architecture: "mixed",
            customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRoleAdmin",
            eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/sparkpilot-live-1",
            eks_namespace: "sparkpilot-demo-2",
            emr_virtual_cluster_id: "vc-123",
            warm_pool_enabled: false,
            lake_formation_enabled: false,
            lf_catalog_id: null,
            lf_data_access_scope: null,
            identity_mode: "oidc",
            security_configuration_id: null,
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

    await expect(page.getByText("josh@example.com", { exact: true })).toBeVisible();
    await expect(page.getByText(/Role: admin. Tenant: tenant-123. Team: team-456./i)).toBeVisible();
    await expect(page.getByText(/1 total visible environment\(s\)./i)).toBeVisible();
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

    await expect(page.getByTestId("session-status")).toHaveText("Authenticated");
    await expect(page.getByText("Unknown")).toBeVisible();
    await expect(page.getByText(/Signed in, but \/v1\/auth\/me did not return scoped identity details./i).first()).toBeVisible();
    await expect(page.getByText(/Environment setup is blocked until access mapping is complete./i)).toBeVisible();
  });

  test("routes unbound non-admin users to request-access path", async ({ page }) => {
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
          actor: "user@example.com",
          role: "user",
          tenant_id: null,
          team_id: null,
          scoped_environment_ids: [],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/jobs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/onboarding/aws");

    const nextActionCard = page.locator(".card").filter({
      has: page.getByRole("heading", { name: /Current next action/i }),
    });
    await expect(
      nextActionCard.getByText(/Ask your SparkPilot admin to map your identity to a tenant in Access./i)
    ).toBeVisible();
    await expect(nextActionCard.getByRole("link", { name: /Request access/i })).toBeVisible();
    await expect(nextActionCard.getByRole("link", { name: /Open Access/i })).toHaveCount(0);
  });

  test("supports assisted environment setup without manual cluster ARN entry", async ({ page }) => {
    let environmentCreated = false;

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
          actor: "admin@example.com",
          role: "admin",
          tenant_id: "tenant-ops-123",
          team_id: "team-456",
          scoped_environment_ids: [],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      if (route.request().method() === "POST") {
        const payload = route.request().postDataJSON() as Record<string, unknown>;
        expect(payload).toMatchObject({
          customer_role_arn: "arn:aws:iam::123456789012:role/team/platform/SparkPilotByocLiteRole",
          eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
          eks_namespace: "sparkpilot-tenant-ops-123-primary-cluster",
        });
        environmentCreated = true;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: "op-123",
            environment_id: "env-123",
            state: "queued",
            step: "queued",
            started_at: "2026-03-29T10:00:00Z",
            ended_at: null,
            message: "Queued for provisioning.",
            logs_uri: null,
            created_at: "2026-03-29T10:00:00Z",
            updated_at: "2026-03-29T10:00:00Z",
          }),
        });
        return;
      }

      const body = environmentCreated
        ? [
            {
              id: "env-123",
              tenant_id: "tenant-ops-123",
              cloud: "aws",
              region: "us-east-1",
              engine: "emr_on_eks",
              status: "ready",
              provisioning_mode: "byoc_lite",
              instance_architecture: "mixed",
              customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
              eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
              eks_namespace: "sparkpilot-tenant-ops-123-primary-cluster",
              emr_virtual_cluster_id: "vc-123",
              warm_pool_enabled: false,
              lake_formation_enabled: false,
              lf_catalog_id: null,
              lf_data_access_scope: null,
              identity_mode: "oidc",
              security_configuration_id: null,
              max_concurrent_runs: 10,
              max_vcpu: 256,
              max_run_seconds: 7200,
              created_at: "2026-03-29T10:00:00Z",
              updated_at: "2026-03-29T10:00:00Z",
            },
          ]
        : [];

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    });

    await page.route("**/api/sparkpilot/v1/jobs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/usage*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant_id: "tenant-ops-123",
          from_ts: "2026-03-01T00:00:00Z",
          to_ts: "2026-03-29T00:00:00Z",
          items: [],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/aws/byoc-lite/discovery*", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("customer_role_arn")).toBe(
        "arn:aws:iam::123456789012:role/team/platform/SparkPilotByocLiteRole"
      );
      expect(url.searchParams.get("region")).toBe("us-east-1");
      expect(url.searchParams.get("tenant_id")).toBe("tenant-ops-123");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          customer_role_arn: "arn:aws:iam::123456789012:role/team/platform/SparkPilotByocLiteRole",
          region: "us-east-1",
          account_id: "123456789012",
          recommended_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
          namespace_suggestion: "sparkpilot-tenant-ops-123-primary-cluster",
          clusters: [
            {
              name: "primary-cluster",
              arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
              status: "ACTIVE",
              version: "1.31",
              oidc_issuer: "https://oidc.eks.us-east-1.amazonaws.com/id/PRIMARY",
              has_oidc: true,
            },
          ],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/provisioning-operations/op-123", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "op-123",
          environment_id: "env-123",
          state: "ready",
          step: "ready",
          started_at: "2026-03-29T10:00:00Z",
          ended_at: "2026-03-29T10:02:00Z",
          message: "Environment ready.",
          logs_uri: null,
          created_at: "2026-03-29T10:00:00Z",
          updated_at: "2026-03-29T10:02:00Z",
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/environments/env-123", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "env-123",
          tenant_id: "tenant-ops-123",
          cloud: "aws",
          region: "us-east-1",
          engine: "emr_on_eks",
          status: "ready",
          provisioning_mode: "byoc_lite",
          instance_architecture: "mixed",
          customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
          eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
          eks_namespace: "sparkpilot-tenant-ops-123-primary-cluster",
          emr_virtual_cluster_id: "vc-123",
          warm_pool_enabled: false,
          lake_formation_enabled: false,
          lf_catalog_id: null,
          lf_data_access_scope: null,
          identity_mode: "oidc",
          security_configuration_id: null,
          max_concurrent_runs: 10,
          max_vcpu: 256,
          max_run_seconds: 7200,
          created_at: "2026-03-29T10:00:00Z",
          updated_at: "2026-03-29T10:00:00Z",
        }),
      });
    });

    await page.goto("/onboarding/aws");

    await expect(page.getByTestId("assisted-environment-setup")).toBeVisible();
    await page.getByTestId("assisted-account-id-input").fill("123456789012");
    await page.getByTestId("assisted-role-name-input").fill("team/platform/SparkPilotByocLiteRole");
    await expect(page.getByTestId("assisted-role-arn-preview")).toHaveValue(
      "arn:aws:iam::123456789012:role/team/platform/SparkPilotByocLiteRole"
    );
    await page.getByRole("button", { name: /discover eks clusters/i }).click();
    await expect(page.getByTestId("discovered-cluster-select")).toHaveValue(
      "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster"
    );
    await expect(page.getByTestId("assisted-namespace-input")).toHaveValue(/sparkpilot-/i);

    await expect(page.getByTestId("create-environment-button")).toBeEnabled();
    await page.getByTestId("create-environment-button").click();
    await expect(page.getByTestId("assisted-environment-setup")).toHaveCount(0);
    await expect(page.getByText(/1 total visible environment\(s\)\./i).first()).toBeVisible();
  });

  test("allows manual ARN fallback after discovery remediation error", async ({ page }) => {
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
          actor: "admin@example.com",
          role: "admin",
          tenant_id: "tenant-ops-123",
          team_id: "team-456",
          scoped_environment_ids: [],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      if (route.request().method() === "POST") {
        const payload = route.request().postDataJSON() as Record<string, unknown>;
        expect(payload).toMatchObject({
          customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
          eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/manual-cluster",
          eks_namespace: "sparkpilot-tenant-ops-manual",
        });
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify({
            id: "op-manual-123",
            environment_id: "env-manual-123",
            state: "queued",
            step: "queued",
            started_at: "2026-03-29T10:00:00Z",
            ended_at: null,
            message: "Queued for provisioning.",
            logs_uri: null,
            created_at: "2026-03-29T10:00:00Z",
            updated_at: "2026-03-29T10:00:00Z",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/jobs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.route("**/api/sparkpilot/v1/usage*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant_id: "tenant-ops-123",
          from_ts: "2026-03-01T00:00:00Z",
          to_ts: "2026-03-29T00:00:00Z",
          items: [],
        }),
      });
    });

    await page.route("**/api/sparkpilot/v1/aws/byoc-lite/discovery*", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("customer_role_arn")).toBe(
        "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole"
      );
      expect(url.searchParams.get("region")).toBe("us-east-1");
      expect(url.searchParams.get("tenant_id")).toBe("tenant-ops-123");
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "Access denied while listing EKS clusters for BYOC-Lite discovery. Remediation: grant customer_role_arn eks:ListClusters and retry.",
        }),
      });
    });
    await page.route("**/api/sparkpilot/v1/provisioning-operations/op-manual-123", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "op-manual-123",
          environment_id: "env-manual-123",
          state: "ready",
          step: "ready",
          started_at: "2026-03-29T10:00:00Z",
          ended_at: "2026-03-29T10:01:00Z",
          message: "Environment ready.",
          logs_uri: null,
          created_at: "2026-03-29T10:00:00Z",
          updated_at: "2026-03-29T10:01:00Z",
        }),
      });
    });
    await page.route("**/api/sparkpilot/v1/environments/env-manual-123", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "env-manual-123",
          tenant_id: "tenant-ops-123",
          cloud: "aws",
          region: "us-east-1",
          engine: "emr_on_eks",
          status: "ready",
          provisioning_mode: "byoc_lite",
          instance_architecture: "mixed",
          customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
          eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/manual-cluster",
          eks_namespace: "sparkpilot-tenant-ops-manual",
          emr_virtual_cluster_id: "vc-123",
          warm_pool_enabled: false,
          lake_formation_enabled: false,
          lf_catalog_id: null,
          lf_data_access_scope: null,
          identity_mode: "oidc",
          security_configuration_id: null,
          max_concurrent_runs: 10,
          max_vcpu: 256,
          max_run_seconds: 7200,
          created_at: "2026-03-29T10:00:00Z",
          updated_at: "2026-03-29T10:00:00Z",
        }),
      });
    });

    await page.goto("/onboarding/aws");
    await page.getByTestId("assisted-account-id-input").fill("123456789012");
    await page.getByRole("button", { name: /discover eks clusters/i }).click();
    await expect(page.getByText(/Access denied while listing EKS clusters/i).first()).toBeVisible();

    await page.locator("summary.card-summary").click();
    await page.getByLabel("Manual role ARN override").check();
    await page.getByTestId("assisted-manual-role-arn-input").fill("arn:aws:iam::123456789012:role/SparkPilotByocLiteRole");
    await page.getByLabel("Manual cluster ARN override").check();
    await page.getByTestId("manual-cluster-arn-input").fill("arn:aws:eks:us-east-1:123456789012:cluster/manual-cluster");
    await page.getByTestId("assisted-namespace-input").fill("sparkpilot-tenant-ops-manual");

    await expect(page.getByTestId("create-environment-button")).toBeEnabled();
    await page.getByTestId("create-environment-button").click();
    await expect(page.getByText(/Environment queued\. operation_id=/i)).toBeVisible();
  });

  test("resets discovery-derived namespace and cluster when discovery context changes", async ({ page }) => {
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
          actor: "admin@example.com",
          role: "admin",
          tenant_id: "tenant-ops-123",
          team_id: "team-456",
          scoped_environment_ids: [],
        }),
      });
    });
    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/sparkpilot/v1/jobs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/sparkpilot/v1/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/sparkpilot/v1/usage*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant_id: "tenant-ops-123",
          from_ts: "2026-03-01T00:00:00Z",
          to_ts: "2026-03-29T00:00:00Z",
          items: [],
        }),
      });
    });
    await page.route("**/api/sparkpilot/v1/aws/byoc-lite/discovery*", async (route) => {
      const url = new URL(route.request().url());
      expect(url.searchParams.get("customer_role_arn")).toBe(
        "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole"
      );
      expect(url.searchParams.get("region")).toBe("us-east-1");
      expect(url.searchParams.get("tenant_id")).toBe("tenant-ops-123");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
          region: "us-east-1",
          account_id: "123456789012",
          recommended_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
          namespace_suggestion: "sparkpilot-tenant-ops-123-primary-cluster",
          clusters: [
            {
              name: "primary-cluster",
              arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
              status: "ACTIVE",
              version: "1.31",
              oidc_issuer: "https://oidc.eks.us-east-1.amazonaws.com/id/PRIMARY",
              has_oidc: true,
            },
          ],
        }),
      });
    });

    await page.goto("/onboarding/aws");
    await page.getByTestId("assisted-account-id-input").fill("123456789012");
    await page.getByRole("button", { name: /discover eks clusters/i }).click();
    await expect(page.getByTestId("discovered-cluster-select")).toHaveValue(
      "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster"
    );
    await expect(page.getByTestId("assisted-namespace-input")).toHaveValue("sparkpilot-tenant-ops-123-primary-cluster");

    await page.getByTestId("assisted-region-input").fill("us-west-2");
    await expect(page.getByTestId("discovered-cluster-select")).toHaveValue("");
    await expect(page.getByTestId("assisted-namespace-input")).toHaveValue("");
  });

  test("hides assisted create flow when an environment already exists", async ({ page }) => {
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
          actor: "admin@example.com",
          role: "admin",
          tenant_id: "tenant-ops-123",
          team_id: "team-456",
          scoped_environment_ids: ["env-123"],
        }),
      });
    });
    await page.route("**/api/sparkpilot/v1/environments", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            id: "env-123",
            tenant_id: "tenant-ops-123",
            cloud: "aws",
            region: "us-east-1",
            engine: "emr_on_eks",
            status: "provisioning",
            provisioning_mode: "byoc_lite",
            instance_architecture: "mixed",
            customer_role_arn: "arn:aws:iam::123456789012:role/SparkPilotByocLiteRole",
            eks_cluster_arn: "arn:aws:eks:us-east-1:123456789012:cluster/primary-cluster",
            eks_namespace: "sparkpilot-tenant-ops-123-primary-cluster",
            emr_virtual_cluster_id: null,
            warm_pool_enabled: false,
            lake_formation_enabled: false,
            lf_catalog_id: null,
            lf_data_access_scope: null,
            identity_mode: "oidc",
            security_configuration_id: null,
            max_concurrent_runs: 10,
            max_vcpu: 256,
            max_run_seconds: 7200,
            created_at: "2026-03-29T10:00:00Z",
            updated_at: "2026-03-29T10:00:00Z",
          },
        ]),
      });
    });
    await page.route("**/api/sparkpilot/v1/jobs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/sparkpilot/v1/runs", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/sparkpilot/v1/usage*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tenant_id: "tenant-ops-123",
          from_ts: "2026-03-01T00:00:00Z",
          to_ts: "2026-03-29T00:00:00Z",
          items: [],
        }),
      });
    });

    await page.goto("/onboarding/aws");
    await expect(page.getByTestId("assisted-environment-setup")).toHaveCount(0);
    await expect(page.getByText(/Environment exists but is not ready yet./i).first()).toBeVisible();
  });
});
