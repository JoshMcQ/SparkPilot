export type OidcPool = "customer" | "internal";

export type OidcClientConfig = {
  pool: OidcPool;
  issuer: string;
  clientId: string;
  redirectUri: string;
  audience: string;
  identityProvider: string;
};

const CUSTOMER_OIDC_ISSUER = (process.env.NEXT_PUBLIC_OIDC_ISSUER ?? "").trim();
const CUSTOMER_OIDC_CLIENT_ID = (process.env.NEXT_PUBLIC_OIDC_CLIENT_ID ?? "").trim();
const CUSTOMER_OIDC_REDIRECT_URI = (process.env.NEXT_PUBLIC_OIDC_REDIRECT_URI ?? "").trim();
const CUSTOMER_OIDC_AUDIENCE = (process.env.NEXT_PUBLIC_OIDC_AUDIENCE ?? "").trim();
const CUSTOMER_COGNITO_IDENTITY_PROVIDER = (
  process.env.NEXT_PUBLIC_COGNITO_IDENTITY_PROVIDER ?? ""
).trim();

const INTERNAL_OIDC_ISSUER = (process.env.NEXT_PUBLIC_INTERNAL_OIDC_ISSUER ?? "").trim();
const INTERNAL_OIDC_CLIENT_ID = (
  process.env.NEXT_PUBLIC_INTERNAL_OIDC_CLIENT_ID ?? ""
).trim();
const INTERNAL_OIDC_REDIRECT_URI = (
  process.env.NEXT_PUBLIC_INTERNAL_OIDC_REDIRECT_URI ?? ""
).trim();
const INTERNAL_OIDC_AUDIENCE = (
  process.env.NEXT_PUBLIC_INTERNAL_OIDC_AUDIENCE ?? ""
).trim();
const INTERNAL_COGNITO_IDENTITY_PROVIDER = (
  process.env.NEXT_PUBLIC_INTERNAL_COGNITO_IDENTITY_PROVIDER ?? ""
).trim();

export function oidcClientConfig(pool: OidcPool = "customer"): OidcClientConfig {
  if (pool === "internal") {
    return {
      pool,
      issuer: INTERNAL_OIDC_ISSUER,
      clientId: INTERNAL_OIDC_CLIENT_ID,
      redirectUri: INTERNAL_OIDC_REDIRECT_URI || CUSTOMER_OIDC_REDIRECT_URI,
      audience: INTERNAL_OIDC_AUDIENCE,
      identityProvider: INTERNAL_COGNITO_IDENTITY_PROVIDER,
    };
  }
  return {
    pool,
    issuer: CUSTOMER_OIDC_ISSUER,
    clientId: CUSTOMER_OIDC_CLIENT_ID,
    redirectUri: CUSTOMER_OIDC_REDIRECT_URI,
    audience: CUSTOMER_OIDC_AUDIENCE,
    identityProvider: CUSTOMER_COGNITO_IDENTITY_PROVIDER,
  };
}

const MANUAL_TOKEN_MODE =
  (process.env.NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE ?? "").trim().toLowerCase() === "true";

export function isOidcClientConfigured(pool: OidcPool = "customer"): boolean {
  const config = oidcClientConfig(pool);
  return Boolean(config.issuer && config.clientId && config.redirectUri);
}

export function isManualTokenModeEnabled(): boolean {
  return MANUAL_TOKEN_MODE && process.env.NODE_ENV !== "production";
}
