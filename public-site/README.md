# SparkPilot Public Site

This directory contains the standalone public marketing site as a static Next.js export.

## Purpose

The public site is intentionally decoupled from the authenticated product app runtime:

- Public site: always-on, cheap static hosting (`sparkpilot.cloud`)
- Product app: authenticated workload operations (`app.sparkpilot.cloud`)

This lets SparkPilot keep the public site online while app infrastructure can be scaled down when no active pilot/demo/customer session is running.

## Build

```bash
bash scripts/public_site/build_public_site.sh
```

Environment variable:

- `PUBLIC_SITE_APP_URL` (optional, default: `https://app.sparkpilot.cloud`)

Build output:
- `public-site/dist`

## Deploy

Workflow: `.github/workflows/public-site.yml`

Required production environment secrets for deploy:

- `AWS_PUBLIC_SITE_DEPLOY_ROLE_ARN`
- `PUBLIC_SITE_S3_BUCKET`

Optional secret:

- `PUBLIC_SITE_CLOUDFRONT_DISTRIBUTION_ID`

Required production environment variables:

- `PUBLIC_SITE_DEPLOY_ENABLED=true`
- `PUBLIC_SITE_APP_URL=https://app.sparkpilot.cloud`
