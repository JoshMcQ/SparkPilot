import {
  type InternalTenantCreateRequest,
  type InternalTenantCreateResponse,
  type InternalTenantUser,
  createInternalTenant,
  regenerateInternalTenantInvite,
} from "@/lib/api";

export type InviteStatus = "consumed" | "pending" | "expired";

export type ProvisionTenantFormInput = {
  name: string;
  admin_email: string;
  federation_type: InternalTenantCreateRequest["federation_type"];
  idp_metadata_text: string;
};

const EMAIL_PATTERN = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function validateProvisionTenantForm(input: ProvisionTenantFormInput): string | null {
  const name = input.name.trim();
  if (name.length < 3 || name.length > 255) {
    return "Tenant name must be between 3 and 255 characters.";
  }
  const email = input.admin_email.trim().toLowerCase();
  if (!EMAIL_PATTERN.test(email)) {
    return "Admin email must be a valid email address.";
  }
  if (input.federation_type !== "cognito_password" && input.idp_metadata_text.trim()) {
    try {
      const parsed = JSON.parse(input.idp_metadata_text);
      if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
        return "IdP metadata must be a JSON object.";
      }
    } catch {
      return "IdP metadata must be valid JSON.";
    }
  }
  return null;
}

export function toInternalTenantCreateRequest(
  input: ProvisionTenantFormInput,
): InternalTenantCreateRequest {
  const metadataText = input.idp_metadata_text.trim();
  let idpMetadata: Record<string, unknown> | null = null;
  if (input.federation_type !== "cognito_password" && metadataText) {
    idpMetadata = JSON.parse(metadataText) as Record<string, unknown>;
  }
  return {
    name: input.name.trim(),
    admin_email: input.admin_email.trim().toLowerCase(),
    federation_type: input.federation_type,
    idp_metadata: idpMetadata,
  };
}

export async function provisionTenantFromForm(
  input: ProvisionTenantFormInput,
  createFn: (
    request: InternalTenantCreateRequest,
  ) => Promise<InternalTenantCreateResponse> = createInternalTenant,
): Promise<InternalTenantCreateResponse> {
  const validationError = validateProvisionTenantForm(input);
  if (validationError) {
    throw new Error(validationError);
  }
  return createFn(toInternalTenantCreateRequest(input));
}

export function inviteStatusForUser(
  user: Pick<InternalTenantUser, "invite_consumed_at" | "invite_expires_at">,
  now: Date = new Date(),
): InviteStatus {
  if (user.invite_consumed_at) {
    return "consumed";
  }
  if (!user.invite_expires_at) {
    return "pending";
  }
  const expiresAt = Date.parse(user.invite_expires_at);
  if (!Number.isFinite(expiresAt)) {
    return "pending";
  }
  return expiresAt <= now.getTime() ? "expired" : "pending";
}

export function canRegenerateInvite(status: InviteStatus): boolean {
  return status === "pending" || status === "expired";
}

export function regenerateInviteConfirmationMessage(userEmail: string): string {
  return `Regenerate invite for ${userEmail}?`;
}

export async function regenerateInviteWithConfirmation(
  tenantId: string,
  userId: string,
  userEmail: string,
  confirmFn: (message: string) => boolean,
  regenerateFn: (
    tenantId: string,
    userId: string,
  ) => Promise<InternalTenantCreateResponse> = regenerateInternalTenantInvite,
): Promise<InternalTenantCreateResponse | null> {
  if (!confirmFn(regenerateInviteConfirmationMessage(userEmail))) {
    return null;
  }
  return regenerateFn(tenantId, userId);
}
