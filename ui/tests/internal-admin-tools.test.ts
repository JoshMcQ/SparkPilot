import assert from "node:assert/strict";
import test from "node:test";

import type { InternalTenantCreateResponse, InternalTenantUser } from "../lib/api";
import {
  canRegenerateInvite,
  inviteStatusForUser,
  provisionTenantFromForm,
  regenerateInviteConfirmationMessage,
  regenerateInviteWithConfirmation,
  toInternalTenantCreateRequest,
  validateProvisionTenantForm,
} from "../lib/internal-admin-tools";
import { isInternalAdmin } from "../lib/use-internal-admin";

test("isInternalAdmin returns true only when auth flag is true", () => {
  assert.equal(isInternalAdmin(null), false);
  assert.equal(
    isInternalAdmin({
      actor: "a",
      role: "user",
      tenant_id: null,
      team_id: null,
      scoped_environment_ids: [],
      email: null,
      is_internal_admin: false,
    }),
    false,
  );
  assert.equal(
    isInternalAdmin({
      actor: "a",
      role: "admin",
      tenant_id: null,
      team_id: null,
      scoped_environment_ids: [],
      email: "admin@example.invalid",
      is_internal_admin: true,
    }),
    true,
  );
});

test("build request validates required fields and metadata json", () => {
  assert.equal(
    validateProvisionTenantForm({
      name: "ab",
      admin_email: "admin@example.invalid",
      federation_type: "cognito_password",
      idp_metadata_text: "",
    }),
    "Tenant name must be between 3 and 255 characters.",
  );
  assert.equal(
    validateProvisionTenantForm({
      name: "Valid Tenant",
      admin_email: "not-an-email",
      federation_type: "oidc",
      idp_metadata_text: "",
    }),
    "Admin email must be a valid email address.",
  );
  assert.equal(
    validateProvisionTenantForm({
      name: "Valid Tenant",
      admin_email: "admin@example.invalid",
      federation_type: "oidc",
      idp_metadata_text: "{not-json}",
    }),
    "IdP metadata must be valid JSON.",
  );
  assert.equal(
    validateProvisionTenantForm({
      name: "Valid Tenant",
      admin_email: "admin@example.invalid",
      federation_type: "oidc",
      idp_metadata_text: "[1,2,3]",
    }),
    "IdP metadata must be a JSON object.",
  );
});

test("provisionTenantFromForm calls API with normalized request and returns email delivery", async () => {
  const expected: InternalTenantCreateResponse = {
    tenant_id: "t1",
    user_id: "u1",
    invite_email_recipient: "admin@example.invalid",
    invite_email_provider: "resend",
    invite_email_status: "sent",
    invite_email_provider_message_id: "email-123",
    invite_email_failure_detail: null,
  };
  let captured: unknown = null;
  const result = await provisionTenantFromForm(
    {
      name: "  Acme Corp  ",
      admin_email: "ADMIN@EXAMPLE.INVALID",
      federation_type: "saml",
      idp_metadata_text: '{"entity_id":"abc"}',
    },
    async (request) => {
      captured = request;
      return expected;
    },
  );
  assert.deepEqual(
    captured,
    toInternalTenantCreateRequest({
      name: "  Acme Corp  ",
      admin_email: "ADMIN@EXAMPLE.INVALID",
      federation_type: "saml",
      idp_metadata_text: '{"entity_id":"abc"}',
    }),
  );
  assert.deepEqual(result, expected);
});

test("invite status and regenerate gating behave correctly", () => {
  const consumed: Pick<InternalTenantUser, "invite_consumed_at" | "invite_expires_at"> = {
    invite_consumed_at: "2026-01-01T00:00:00Z",
    invite_expires_at: null,
  };
  const pending: Pick<InternalTenantUser, "invite_consumed_at" | "invite_expires_at"> = {
    invite_consumed_at: null,
    invite_expires_at: "2099-01-01T00:00:00Z",
  };
  const expired: Pick<InternalTenantUser, "invite_consumed_at" | "invite_expires_at"> = {
    invite_consumed_at: null,
    invite_expires_at: "2000-01-01T00:00:00Z",
  };
  assert.equal(inviteStatusForUser(consumed), "consumed");
  assert.equal(inviteStatusForUser(pending), "pending");
  assert.equal(inviteStatusForUser(expired), "expired");
  assert.equal(canRegenerateInvite("consumed"), false);
  assert.equal(canRegenerateInvite("pending"), true);
  assert.equal(canRegenerateInvite("expired"), true);
});

test("regenerate invite confirm flow respects cancel/confirm", async () => {
  const message = regenerateInviteConfirmationMessage("person@example.invalid");
  assert.equal(message, "Regenerate invite for person@example.invalid?");

  const cancelled = await regenerateInviteWithConfirmation(
    "t1",
    "u1",
    "person@example.invalid",
    () => false,
    async () => {
      throw new Error("should not execute");
    },
  );
  assert.equal(cancelled, null);

  let called = false;
  const expected: InternalTenantCreateResponse = {
    tenant_id: "t1",
    user_id: "u1",
    invite_email_recipient: "person@example.invalid",
    invite_email_provider: "resend",
    invite_email_status: "sent",
    invite_email_provider_message_id: "email-456",
    invite_email_failure_detail: null,
  };
  const confirmed = await regenerateInviteWithConfirmation(
    "t1",
    "u1",
    "person@example.invalid",
    () => true,
    async () => {
      called = true;
      return expected;
    },
  );
  assert.equal(called, true);
  assert.deepEqual(confirmed, expected);
});
