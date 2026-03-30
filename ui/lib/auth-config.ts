const OIDC_ISSUER = (process.env.NEXT_PUBLIC_OIDC_ISSUER ?? "").trim();
const OIDC_CLIENT_ID = (process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "").trim();
const OIDC_REDIRECT_URI = (process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI ?? "").trim();

const MANUAL_TOKEN_MODE =
  (process.env.NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE ?? "").trim().toLowerCase() === "true";

export function isOidcClientConfigured(): boolean {
  return Boolean(OIDC_ISSUER && OIDC_CLIENT_ID && OIDC_REDIRECT_URI);
}

export function isManualTokenModeEnabled(): boolean {
  return MANUAL_TOKEN_MODE && process.env.NODE_ENV !== "production";
}
