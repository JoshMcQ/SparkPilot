# Public Site + Dormant App Ops Runbook

## 1) Verify public site health (always-on surface)

```powershell
nslookup sparkpilot.cloud 1.1.1.1
curl.exe -sS -I https://sparkpilot.cloud/
curl.exe -sS https://sparkpilot.cloud/ | Select-Object -First 12
```

Expected:
- DNS resolves.
- HTTPS returns `200`.
- HTML is the static marketing page.

## 2) Verify app is dormant (default state)

```powershell
aws ecs describe-services `
  --cluster sparkpilot-staging-ecs `
  --services sparkpilot-staging-api sparkpilot-staging-ui `
  --region us-east-1 `
  --query "services[].{service:serviceName,desired:desiredCount,running:runningCount}" `
  --output table

aws rds describe-db-instances `
  --db-instance-identifier sparkpilot-staging-postgres `
  --region us-east-1 `
  --query "DBInstances[0].DBInstanceStatus" `
  --output text

curl.exe -sS -o NUL -w "%{http_code}" https://app-staging.sparkpilot.cloud/healthz
```

Expected dormant values:
- ECS desired/running counts = `0`.
- RDS status = `stopped`.
- `/healthz` returns `503` (runtime down).

## 3) Bring staging app runtime up (pilot/demo window)

```powershell
gh workflow run environment-runtime-toggle.yml --ref main `
  -f target_environment=staging `
  -f action=up `
  -f manage_rds=true `
  -f wait_for_db_available=true `
  -f api_desired_count=1 `
  -f ui_desired_count=1 `
  -f worker_desired_count=1 `
  -f dry_run=false
```

Then watch the run:

```powershell
gh run list --workflow environment-runtime-toggle.yml --branch main --limit 1
gh run watch <run-id> --interval 10 --exit-status
```

Validate:

```powershell
curl.exe -sS -o NUL -w "%{http_code}" https://app-staging.sparkpilot.cloud/healthz
```

Expected during active window:
- `/healthz` returns `200`.

## 4) Bring staging app runtime down (end of window)

```powershell
gh workflow run environment-runtime-toggle.yml --ref main `
  -f target_environment=staging `
  -f action=down `
  -f manage_rds=true `
  -f wait_for_db_available=false `
  -f api_desired_count=0 `
  -f ui_desired_count=0 `
  -f worker_desired_count=0 `
  -f dry_run=false
```

Then watch/verify:

```powershell
gh run list --workflow environment-runtime-toggle.yml --branch main --limit 1
gh run watch <run-id> --interval 10 --exit-status
curl.exe -sS -o NUL -w "%{http_code}" https://app-staging.sparkpilot.cloud/healthz
```

Expected after shutdown:
- ECS returns to `0/0`.
- DB transitions to `stopping` then `stopped`.
- `/healthz` returns `503`.

## 5) Dormancy definitions

- **Warm dormant**:
  - Public site remains live.
  - App ECS tasks are `0`.
  - RDS is stopped.
  - ALB + VPC endpoints remain for faster next startup.

- **Deep dormant (next phase)**:
  - Everything in warm dormant, plus remove expensive idle network/control-plane resources (for example ALB and interface endpoints) and recreate them only when needed.
  - This requires a one-command `deep-down` / `deep-up` workflow with infra apply/destroy guards.

