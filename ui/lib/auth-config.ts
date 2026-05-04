export type OidcPool = "customer" | "internal";

export type OidcClientConfig = {
  pool: OidcPool;
  issuer: string;
  clientId: string;
  redirectUri: string;
  audience: string;
  identityProvider: string;
};

function _env(name: string): string {
  return (process.env[name] ?? "").trim();
}

export function oidcClientConfig(pool: OidcPool = "customer"): OidcClientConfig {
  const customerRedirectUri = _env("NEXT_PUBLIC_OIDC_REDIRECT_URI");
  if (pool === "internal") {
    return {
      pool,
      issuer: _env("NEXT_PUBLIC_INTERNAL_OIDC_ISSUER"),
      clientId: _env("NEXT_PUBLIC_INTERNAL_OIDC_CLIENT_ID"),
      redirectUri: _env("NEXT_PUBLIC_INTERNAL_OIDC_REDIRECT_URI") || customerRedirectUri,
      audience: _env("NEXT_PUBLIC_INTERNAL_OIDC_AUDIENCE"),
      identityProvider: _env("NEXT_PUBLIC_INTERNAL_COGNITO_IDENTITY_PROVIDER"),
    };
  }
  return {
    pool,
    issuer: _env("NEXT_PUBLIC_OIDC_ISSUER"),
    clientId: _env("NEXT_PUBLIC_OIDC_CLIENT_ID"),
    redirectUri: customerRedirectUri,
    audience: _env("NEXT_PUBLIC_OIDC_AUDIENCE"),
    identityProvider: _env("NEXT_PUBLIC_COGNITO_IDENTITY_PROVIDER"),
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
