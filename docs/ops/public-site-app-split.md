# Public Site / Product App Split

## Domains

- `sparkpilot.cloud` -> static public site (`public-site/dist`)
- `app.sparkpilot.cloud` -> authenticated product app (`ui` + API)
- `sparkpilot-auth.auth.us-east-1.amazoncognito.com` -> Cognito hosted login domain

## Separation Rules

1. Public site must not depend on app/API availability.
2. Product app routes are for authenticated workflows (onboarding, environments, runs, costs, access).
3. Marketing pages on app runtime redirect to `sparkpilot.cloud`.

## Deployment

### Public site

- Build: `bash scripts/public_site/build_public_site.sh`
- Deploy workflow: `.github/workflows/public-site.yml`
- Hosting target: S3 + CloudFront (or Amplify Hosting with the same static artifact)

### Product app/control plane

- Existing workflow: `.github/workflows/ci-cd.yml`
- Deploy lanes are gated by `*_DEPLOY_ENABLED` variables and environment preflight checks.

## Cost policy

- Public site: always on.
- Prod app: enable during active pilot/customer operation.
- Staging: off/manual by default after prod activation.
- Dev: off by default.

## Manual runtime controls

- Workflow: `.github/workflows/environment-runtime-toggle.yml`
- Script: `scripts/ops/set_environment_runtime.sh`

This provides explicit `up`/`down` actions for `dev`, `staging`, and `prod` ECS+RDS runtime state so app environments can stay dormant by default and be enabled only for active demos/pilots/customer sessions.
