# SparkPilot CLI Integration

Use the SparkPilot CLI when your team prefers terminal-first workflows, CI jobs, or scripted operations.

## Install

```bash
pip install -e .
sparkpilot --help
```

## Required Authentication Environment Variables

Set either the plain OIDC names or the `SPARKPILOT_` aliases.

```bash
export OIDC_ISSUER="https://cognito-idp.us-east-1.amazonaws.com/<pool_id>"
export OIDC_AUDIENCE="<app_client_id>"
export OIDC_CLIENT_ID="<client_id>"
export OIDC_CLIENT_SECRET="<client_secret>"
```

Optional:

```bash
export OIDC_TOKEN_ENDPOINT="https://<issuer>/oauth2/token"
export OIDC_SCOPE="openid"
```

## Common Commands

```bash
sparkpilot env-list --base-url https://api.sparkpilot.cloud
sparkpilot env-preflight --environment-id <env_id> --base-url https://api.sparkpilot.cloud
sparkpilot run-submit --job-id <job_id> --executor-instances 4 --base-url https://api.sparkpilot.cloud
sparkpilot run-list --state running --base-url https://api.sparkpilot.cloud
sparkpilot run-logs --run-id <run_id> --base-url https://api.sparkpilot.cloud
```

## When to Use CLI vs UI

- Use CLI for automation, CI/CD, and terminal-heavy engineering workflows.
- Use UI for onboarding, governance setup, and exploratory run operations.
- Both surfaces hit the same authenticated API and RBAC policy enforcement.
