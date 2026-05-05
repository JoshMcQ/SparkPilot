import test from "node:test";
import assert from "node:assert/strict";

import { buildOidcState, parseOidcState } from "../lib/oidc-client";

test("OIDC state embeds invite state with the CSRF value", () => {
  const state = buildOidcState(" csrf-token ", " invite-state ");

  assert.notEqual(state, "csrf-token");
  assert.deepEqual(parseOidcState(state), {
    csrfState: "csrf-token",
    inviteState: "invite-state",
  });
});

test("OIDC state without invite remains a plain CSRF value", () => {
  const state = buildOidcState(" csrf-token ");

  assert.equal(state, "csrf-token");
  assert.deepEqual(parseOidcState(state), {
    csrfState: "csrf-token",
    inviteState: null,
  });
});

test("OIDC invite state parser rejects malformed embedded payloads", () => {
  assert.throws(
    () => parseOidcState("sp_oidc_v1.not-json"),
    /OIDC state payload is invalid/,
  );
});
