const required = [
  "SPARKPILOT_API",
  "NEXT_PUBLIC_OIDC_ISSUER",
  "NEXT_PUBLIC_OIDC_CLIENT_ID",
  "NEXT_PUBLIC_OIDC_REDIRECT_URI",
];

const missing = required.filter((name) => !(process.env[name] ?? "").trim());
if (missing.length > 0) {
  console.error("Missing required production UI environment variables:");
  for (const name of missing) {
    console.error(`- ${name}`);
  }
  process.exit(1);
}

const manualMode = (process.env.NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE ?? "").trim().toLowerCase() === "true";
if (manualMode) {
  console.error("NEXT_PUBLIC_ENABLE_MANUAL_TOKEN_MODE=true is not allowed for production-style testing.");
  process.exit(1);
}

const enforceAuth = (process.env.SPARKPILOT_UI_ENFORCE_AUTH ?? "").trim().toLowerCase();
if (enforceAuth === "false") {
  console.error("SPARKPILOT_UI_ENFORCE_AUTH=false is not allowed for production-style testing.");
  process.exit(1);
}

console.log("Production UI environment validation passed.");
