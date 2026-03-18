# AWS Validation Log

| Date (ET) | Action | Resources Created | Resources Deleted | Cost Estimate | Teardown Proof |
|---|---|---|---|---|---|
| 2026-03-18 18:12 | Issue #3 live preflight integration test (`tests/test_issue3_live_preflight_integration.py`) against existing cluster `sparkpilot-live-1` and role `SparkPilotByocLiteRoleAdmin` | none | none | ~$0.00 (STS/IAM simulation/EKS describe only) | No ephemeral resources created; teardown not required |
| 2026-03-18 18:58 | Issue #18 live prerequisite integration test (`tests/test_issue18_live_prereq_integration.py`) validating BYOC-Lite matrix checks/remediations against `sparkpilot-live-1` | none | none | ~$0.00 (read-only IAM/EKS/EMR preflight APIs) | No ephemeral resources created; teardown not required |

## Notes

- Live checks executed in sequence: `sts:GetCallerIdentity` → `iam:SimulatePrincipalPolicy` → `eks:DescribeCluster` → IRSA trust validation.
- All four checks returned `pass` for the tested customer role / cluster / namespace combination.
- Environment variables for required runtime validation fields were set only for the test process.
- Issue #18 live run verified presence and non-failing status for prerequisite matrix codes: cluster ARN/namespace/region/account alignment, OIDC association, execution role trust, dispatch permission, and iam:PassRole.
