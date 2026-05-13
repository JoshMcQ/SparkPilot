# PR Audit: #113 And #114 CodeRabbit Review-To-Merge Timeline

Generated: 2026-03-31. Closes #115.

---

## PR #113 - fix(terraform): complete private-subnet AWS endpoints for ECS tasks

**Branch:** `hotfix/vpc-endpoints-for-private-ecs`
**Merge commit:** `650438451d6b921f5db71ef8f3dc4c104eb3bce4`
**Merged:** `2026-03-30 23:48:17 UTC`

### CodeRabbit Review

| Field | Value |
| --- | --- |
| Review state | `COMMENTED` |
| Submitted at | `2026-03-30 23:43:45 UTC` |
| Reviewed commit | `fff21b663a6aa8c88007c2bd01211a438a4bac43` |
| Actionable comments | **2** |

**Actionable findings from CodeRabbit:**

1. **S3 gateway endpoint route table scope** - S3 gateway was being attached to all discovered route tables, including public ones. It should be restricted to only private route tables by filtering against `var.private_subnet_ids`. This appeared twice in `main.tf`.
2. **Missing SQS and STS interface endpoints** - Private control-plane tasks need SQS and STS endpoints for fully private deployments without NAT. CodeRabbit suggested adding `aws_vpc_endpoint.sqs` and `aws_vpc_endpoint.sts`.

### Merge Decision

**Time from CodeRabbit review to merge: about 4.5 minutes.**

PR #113 was merged about 4.5 minutes after CodeRabbit posted its review. Neither actionable finding was addressed before the merge.

**Was CodeRabbit review on the latest commit?** Yes. Reviewed commit `fff21b6` matched the PR head at time of merge.

**Were actionable comments resolved?** No.

### Post-Merge Consequence

The unaddressed route table scope issue did not cause an immediate failure. However, the merge triggered run `23773327556`, which failed at `deploy-dev` because of a separate related route-table discovery bug introduced by the same PR: the strict per-subnet `aws_route_table` data source hard-fails for subnets using the VPC main route table.

This failure required hotfix PR #114.

---

## PR #114 - fix(terraform): handle main-route-table fallback for private subnet endpoint routing

**Branch:** `hotfix/route-table-fallback`
**Merge commit:** `8d55e5d063b4629bb6b04381c27bb3c9f302ad6b`
**Merged:** `2026-03-31 00:28:48 UTC`

### Context

PR #114 was opened to fix the production failure caused by PR #113. The root cause, strict `aws_route_table` data source failure for subnets with main-route-table associations, was a consequence of the route-table lookup code introduced in #113.

### CodeRabbit Review

| Field | Value |
| --- | --- |
| Review state | No formal review record; GitHub API returned no reviews for PR #114 |
| Reviewed commit | `8d55e5d063b4629bb6b04381c27bb3c9f302ad6b`, the merge commit; branch head was not separately recorded |
| Actionable comments | None recorded; PR #114 was a single-line fallback fix with no bot comment thread |
| Verification method | `gh api repos/JoshMcQ/SparkPilot/pulls/114/reviews` returned an empty array; `gh api repos/JoshMcQ/SparkPilot/issues/114/comments` returned an empty array |

PR #114 passed CI on its branch and was merged after the deploy-dev failure was confirmed fixed. Because the PR contained a single targeted fix and no CodeRabbit actionable findings were recorded, no merge-gate violation occurred on #114 itself. The process failure was on #113.

### Post-Merge Consequence

Run `23774480703` was triggered after merging #114 and failed at `deploy-prod` because `AWS_PROD_DEPLOY_ROLE_ARN` was not set. This was a pre-existing issue unrelated to #113 or #114 and was addressed by PR #123 for issue #116.

---

## Root Cause Summary

| Finding | Detail |
| --- | --- |
| Merge before CodeRabbit complete | PR #113 merged 4.5 minutes after a `COMMENTED` review. The bot had not approved. |
| Unresolved actionable findings | Two comments, route table scope and SQS/STS endpoints, were not addressed. |
| Resulting hotfix | PR #114, route table fallback, was required to restore deploy-dev. |
| Unaddressed carry-forward | SQS/STS endpoints from #113 finding #2 are now implemented in `infra/terraform/control-plane/main.tf` as `aws_vpc_endpoint.sqs` and `aws_vpc_endpoint.sts`. The finding is resolved. |

---

## Lessons-Learned Checklist

This checklist is mandatory for future PRs.

- [ ] Wait for CodeRabbit to complete review on the latest commit SHA before considering merge. `COMMENTED` state is not a passing state.
- [ ] Address or explicitly resolve each actionable comment. If deferring, create a follow-up issue and link it in the PR comment thread.
- [ ] If CodeRabbit is rate-limited, wait for cooldown, re-trigger review with `@coderabbitai review`, confirm latest commit is reviewed, then merge.
- [ ] Do not merge while CodeRabbit is pending. The review status must be on the exact commit being merged, not a prior commit.
- [ ] Check the PR checklist before merging.

---

## Cross-Links

- PR #113: https://github.com/JoshMcQ/SparkPilot/pull/113
- PR #114: https://github.com/JoshMcQ/SparkPilot/pull/114
- Issue #115: https://github.com/JoshMcQ/SparkPilot/issues/115
- Issue #116, deploy-secret preflight: https://github.com/JoshMcQ/SparkPilot/issues/116
- Issue #117, CodeRabbit merge gate: https://github.com/JoshMcQ/SparkPilot/issues/117
- PR #123, fix for #116: https://github.com/JoshMcQ/SparkPilot/pull/123
