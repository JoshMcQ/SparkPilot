import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const routeSource = readFileSync(new URL("../app/api/contact/route.ts", import.meta.url), "utf8");

test("contact proxy stores public leads through the canonical submission API", () => {
  assert.doesNotMatch(routeSource, /\/v1\/contact-requests/);
  assert.match(routeSource, /\/v1\/public\/contact/);
});
