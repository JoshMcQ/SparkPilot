# CodeRabbit Merge Gate Runbook

Mandatory process for all PRs. Addresses issue #117.

---

## Rule

**Do not merge a PR until CodeRabbit has reviewed the latest commit SHA and all actionable comments are resolved.**

A `COMMENTED` state with open actionable comments is not a passing review.

---

## Normal Flow

1. Open PR and wait for CodeRabbit to review automatically.
2. Address each actionable comment by fixing it or deferring it with a linked issue.
3. Push any fixup commits.
4. Wait for CodeRabbit to re-review the latest commit.
5. Confirm all actionable comments are resolved or explicitly deferred.
6. Check the PR checklist in the PR template.
7. Merge.

---

## Rate-Limited Or Pending Review

If CodeRabbit shows as pending or rate-limited on the latest commit:

1. **Wait**. CodeRabbit rate limits reset within 15-60 minutes.
2. **Re-trigger** by commenting `@coderabbitai review` on the PR.
3. **Confirm** that the review covers the exact commit SHA you intend to merge.
4. **Then merge** only after the re-triggered review completes.

Do not merge optimistically while waiting for a rate-limit reset.

---

## Deferring A CodeRabbit Finding

If a finding is valid but out of scope for this PR:

1. Open a new GitHub issue describing the deferred work.
2. Comment on the CodeRabbit review thread: `Deferred to #NNN.`
3. Add the issue number to the PR body.
4. The PR may then be merged.

If a finding is invalid:

1. Reply to the CodeRabbit comment explaining why.
2. Use `@coderabbitai ignore` if applicable.
3. Document the dismissal reason in the PR body.

---

## What Went Wrong In PR #113

PR #113 was merged about 4.5 minutes after CodeRabbit posted `COMMENTED` with two actionable findings: route table scope and missing SQS/STS endpoints. Neither finding was addressed. The merge broke `deploy-dev` and required hotfix PR #114.

Full audit: [docs/process/pr-audit-113-114.md](./pr-audit-113-114.md)

---

## Branch Protection

The goal is to add a required CodeRabbit status check to the `main` branch protection rule. Until that is configured in GitHub repo settings, the PR checklist in `.github/pull_request_template.md` is the enforcement mechanism.

To add CodeRabbit as a required status check:

1. Go to repository Settings, then Branches, then the branch protection rule for `main`.
2. Add `CodeRabbit` or the specific check name to Required status checks.
3. Enable "Require status checks to pass before merging."
