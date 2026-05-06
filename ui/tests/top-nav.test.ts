import assert from "node:assert/strict";
import test from "node:test";

import { buildTopNavItems } from "../lib/top-nav-items";

test("internal nav link is hidden for non-internal users", () => {
  const items = buildTopNavItems(false);
  assert.equal(items.some((item) => item.href === "/internal/tenants"), false);
});

test("internal admins only see tenant provisioning navigation", () => {
  const items = buildTopNavItems(true);
  assert.deepEqual(items, [{ href: "/internal/tenants", label: "Tenants" }]);
});
