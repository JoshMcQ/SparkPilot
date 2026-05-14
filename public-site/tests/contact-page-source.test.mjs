import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const contactPage = readFileSync(new URL("../app/contact/page.tsx", import.meta.url), "utf8");

test("static contact page submits through the app contact proxy instead of the dead public API host", () => {
  assert.doesNotMatch(contactPage, /API_URL/);
  assert.doesNotMatch(contactPage, /api\.sparkpilot\.cloud/);
  assert.doesNotMatch(contactPage, /\/v1\/public\/contact/);
  assert.match(contactPage, /APP_URL/);
  assert.match(contactPage, /\/api\/contact/);
});
