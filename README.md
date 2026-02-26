# SparkPilot

SparkPilot is an AWS-first BYOC managed Spark control plane for Kubernetes-native teams.

This repository contains:

- `src/sparkpilot`: FastAPI control-plane API, workers, and shared services
- `ui`: Next.js thin operator UI
- `infra/terraform/control-plane`: Terraform baseline for SparkPilot control plane
- `infra/cloudformation`: Customer bootstrap templates
- `tests`: API and workflow tests
- `planning/jira`: Jira-importable execution backlog

## Quick Start

1. Create a Python environment and install dependencies:

```powershell
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -e ".[dev]"
```

2. Run database-backed API locally:

```powershell
$env:SPARKPILOT_DATABASE_URL="sqlite:///./sparkpilot.db"
uvicorn sparkpilot.api:app --reload
```

3. Run workers (separate shells):

```powershell
python -m sparkpilot.workers provisioner --once
python -m sparkpilot.workers scheduler --once
python -m sparkpilot.workers reconciler --once
```

4. Run CLI against local API:

```powershell
sparkpilot --help
```

5. Run tests:

```powershell
pytest
```

## First Real AWS Run

- Set up AWS credentials: `docs/setup/aws-auth-quickstart.md`
- Run your first live job: `docs/setup/first-live-run.md`

## Current Scope

Implemented MVP control-plane behaviors include:

- Idempotent mutating APIs (`Idempotency-Key`)
- Environment provisioning operations and state machine
- Spark job template + run submission with per-run overrides
- Queue-style worker loops (provisioner, scheduler, reconciler)
- Deterministic log pointers and run log proxy
- Audit events and quota checks
- Starter AWS infra templates (Terraform + CloudFormation)
- BYOC-Lite mode (`provisioning_mode=byoc_lite`) for existing EKS cluster + namespace onboarding

## Execution Tracking

- Master tracker: `docs/execution-tracker.md`
- Jira setup: `docs/jira-setup.md`
- Jira import CSV: `planning/jira/sparkpilot_jira_import.csv`
- POC criteria template: `docs/poc-success-criteria-template.md`
- Security one-pager template: `docs/security-one-pager-template.md`
- Weekly GTM scorecard: `docs/gtm-weekly-scorecard.md`
