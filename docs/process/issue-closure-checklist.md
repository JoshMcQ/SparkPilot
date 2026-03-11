# Issue Closure Checklist

Use this checklist before closing any roadmap or platform issue.

## Required

- [ ] Code implemented and pushed on a reviewed PR (no direct unreviewed push to `main`).
- [ ] All relevant automated tests pass locally and in CI.
- [ ] Real AWS validation executed for runtime-impacting changes.
- [ ] Evidence artifacts committed or attached:
  - [ ] `artifacts/<issue-or-slice>/summary.json`
  - [ ] supporting logs/payload snapshots
- [ ] Issue comment includes:
  - [ ] what changed
  - [ ] exact test commands run
  - [ ] artifact paths/links
  - [ ] known limitations or residual risks

## Security

- [ ] No critical/high unresolved security finding in touched scope.
- [ ] No credentials/secrets introduced in code, docs, or artifacts.
- [ ] Authz path for changed endpoints validated with negative tests.

## Docs and UX

- [ ] User-facing docs updated for changed behavior.
- [ ] If API/UI behavior changed, tutorial or runbook updated with exact commands/inputs.
- [ ] Validation language matches reality (no unsupported claims).
