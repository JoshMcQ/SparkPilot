import assert from "node:assert/strict";
import test from "node:test";

import { resolveInternalTenantsListState } from "../lib/internal-tenants-list";

test("internal tenants list resolves ready state with mocked API rows", async () => {
  const state = await resolveInternalTenantsListState(async () => [
    {
      tenant_id: "t1",
      tenant_name: "Acme",
      federation_type: "oidc",
      admin_email: "admin@example.invalid",
      created_at: "2026-01-01T00:00:00Z",
      last_login_at: null,
    },
  ]);
  assert.equal(state.status, "ready");
  if (state.status === "ready") {
    assert.equal(state.rows.length, 1);
    assert.equal(state.rows[0].tenant_name, "Acme");
  }
});

test("internal tenants list resolves empty state when API returns empty array", async () => {
  const state = await resolveInternalTenantsListState(async () => []);
  assert.equal(state.status, "ready");
  if (state.status === "ready") {
    assert.deepEqual(state.rows, []);
  }
});

test("internal tenants list resolves error state on API failure", async () => {
  const state = await resolveInternalTenantsListState(async () => {
    throw new Error("boom");
  });
  assert.equal(state.status, "error");
  if (state.status === "error") {
    assert.match(state.message, /boom/);
  }
});
