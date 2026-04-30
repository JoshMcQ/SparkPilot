import assert from "node:assert/strict";
import test from "node:test";

import { buildTopNavItems } from "../lib/top-nav-items";

test("internal nav link is hidden for non-internal users", () => {
  const items = buildTopNavItems(false);
  assert.equal(items.some((item) => item.href === "/internal/tenants"), false);
});

test("internal nav link is shown for internal admins", () => {
  const items = buildTopNavItems(true);
  assert.equal(items.some((item) => item.href === "/internal/tenants"), true);
});
