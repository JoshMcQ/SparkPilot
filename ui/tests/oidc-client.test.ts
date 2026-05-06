import test from "node:test";
import assert from "node:assert/strict";

import { buildOidcState, parseOidcState, selectApiBearerToken } from "../lib/oidc-client";

function jwt(claims: Record<string, unknown>): string {
  const encode = (value: unknown) => Buffer
    .from(JSON.stringify(value))
    .toString("base64url");
  return `${encode({ alg: "RS256", typ: "JWT" })}.${encode(claims)}.signature`;
}

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

test("API bearer token selection prefers an ID token with email claims", () => {
  const accessToken = jwt({ sub: "user-123", token_use: "access" });
  const idToken = jwt({
    sub: "user-123",
    token_use: "id",
    email: "admin@sparkpilot.cloud",
  });

  assert.equal(selectApiBearerToken({ access_token: accessToken, id_token: idToken }), idToken);
});

test("API bearer token selection falls back to access token without email-bearing ID token", () => {
  const accessToken = jwt({ sub: "user-123", token_use: "access" });
  const idToken = jwt({ sub: "user-123", token_use: "id" });

  assert.equal(selectApiBearerToken({ access_token: accessToken, id_token: idToken }), accessToken);
});
