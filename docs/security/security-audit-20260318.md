# SparkPilot Security Audit — 2026-03-18

## Scope

- Dependency risk (Python + UI)
- AuthN/AuthZ abuse-path regression checks
- Secrets exposure checks (working tree + git history)
- AWS Well-Architected security alignment review (least privilege, encryption, auditability)

## 1) Dependency Security

### Python
- Tool: `pip-audit`
- Result: **PASS**
- Finding remediated: `PyJWT 2.11.0` (CVE-2026-32597) upgraded to `PyJWT 2.12.1`
- Project constraint updated in `pyproject.toml` to `PyJWT[crypto]>=2.12.0`

### UI (Node/Next.js)
- Tool: `npm audit`
- Result: **PASS (0 vulnerabilities)**
- Remediation: upgraded to `next@16.2.0` and aligned lint toolchain to ESLint 9 flat config (`eslint.config.mjs`)

## 2) Auth/AuthZ Abuse-Path Checks

Command:
- `pytest tests/test_rbac.py tests/test_oidc.py tests/test_security_hardening.py`

Result: **PASS (19/19)**

Coverage highlights:
- RBAC bypass attempts rejected (`403`) for unauthorized role/scope actions
- Cross-tenant and out-of-scope access blocked by team/environment scoping
- Token/identity edge behavior covered by OIDC tests
- Input-hardening checks for malformed/unsafe payload flows covered by security hardening tests

## 3) Secrets Management Review

### Hardcoded secret scan
- Method: regex scan across tracked files (`git ls-files` + `Select-String`)
- Patterns: AKIA-style keys, `sk-` tokens, private key headers, credential-literal patterns
- Result: **PASS** (no credential literals detected)

### `.env` ignore policy
- `.gitignore` contains:
  - `.env`
  - `.env.*`
  - `*.env`
- Result: **PASS**

### Git history scan
- Method: `git log --all -p` pattern scan for key material markers
- Result: **PASS** (only variable-name references and docs/test placeholders; no credential-like material)

## 4) AWS Well-Architected Security Alignment

### 4.1 Least-Privilege IAM
Status: **PASS (with explicit action scoping)**

Evidence:
- Dispatch permission simulation checks are action-bounded:
  - `emr-containers:StartJobRun`
  - `emr-containers:DescribeJobRun`
  - `emr-containers:CancelJobRun`
- `iam:PassRole` simulation is scoped to configured execution role ARN.
- Trust-policy and OIDC checks provide exact required permissions and remediation commands on AccessDenied.

### 4.2 Encryption at Rest / In Transit
Status: **PARTIAL**

Confirmed:
- Browser session token cookie set as `HttpOnly`, `SameSite=Strict`, and `Secure` in production.
- OIDC/provider and AWS API checks rely on HTTPS endpoints and AWS SDK transport.

Gap to close:
- Explicit, centrally documented enforcement checks for data-at-rest encryption settings (S3/KMS/RDS/CloudWatch log groups) are not yet codified in a single compliance gate.

### 4.3 Logging / Audit Trail Completeness
Status: **PASS**

Evidence:
- Scheduler records `run.preflight_passed` and `run.preflight_failed` audit events with check-level details.
- API surfaces latest preflight snapshot to operators for operational traceability.

## Residual Risk / Follow-ups

1. Add explicit encryption-at-rest policy assertions (KMS/log-group encryption checks) into preflight/compliance path.
2. Keep dependency hygiene on heartbeat cadence (`pip-audit`, `npm audit`) and enforce in CI.
3. Keep UI lint running under ESLint CLI (post-Next 16 migration) as regression gate.

## Conclusion

Current hardening pass materially improves security posture:
- Known dependency vulnerabilities remediated
- RBAC/auth abuse-path tests passing
- Secret leakage checks clean
- AWS preflight permission diagnostics and remediation guidance strengthened

Open work remains on formalizing at-rest encryption compliance checks as first-class automated gates.
