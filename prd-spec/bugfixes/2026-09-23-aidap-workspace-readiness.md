# Wait for newly created AIDAP Workspace metadata

[中文版](2026-09-23-aidap-workspace-readiness.zh.md)

Date: 2026-09-23. Status: implemented in the working tree. Owner: [Studio MPA creation](../../specs/studio-mpa-creation/README.md). This corrects the automatic PostgreSQL flow in [the feature design](../features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.md).

## Background and evidence

A new MPA creation failed immediately after each Workspace was allocated: the first attempt stopped at `admin_workspace`, and the next attempt reached `business_workspace` before failing. Both recorded Workspace IDs now resolve in the verified account as running PostgreSQL 17 resources with valid ownership tags and connection parameters. Read-only SQL connections to both succeed and the returned account has `CREATEDB`. The exact original exception was redacted by the task runner, so eventual metadata visibility is an inference, not a proven historical response. The implementation confirms a vulnerable path: it validates detail fields and tags immediately after `CreateWorkspace`, outside the `PGNotReady` polling loop.

## Goal, scope and scenarios

- A newly created or recorded VeADK-owned Workspace may temporarily lack detail fields/tags or return provider `ResourceNotFound`. Wait for it to become visible within the existing creation timeout, then continue using the recorded ID.
- A present but wrong account, region, project, name, engine or ownership tag remains a hard failure. Explicit adoption keeps strict validation. No second `CreateWorkspace` call, Workspace deletion, migration, or database write is part of this fix.
- A user retry with the same agent ID must reuse both recorded Workspaces. Other MPA creation steps and generic Studio agents are outside scope.

## Design and affected files

In `veadk/integrations/mpa/managed/pg_bootstrap.py`, treat missing identity fields or expected tags as `PGNotReady` only for Workspaces marked as created by this bootstrap state. Move detail validation into the existing readiness loop; treat provider not-found for such recorded owned resources as transient. Keep nonempty mismatches fatal. Add offline delayed-metadata and wrong-owner tests in `tests/integrations/mpa_managed/test_auto_pg.py`. Update this contract and both language documents; no frontend API or UI change is required.

## Tasks, tests and acceptance

1. Reproduce immediate tag/detail failure with a fake AIDAP provider before the fix.
2. Poll only transient absence and retain strict mismatch checks; keep the original Workspace IDs.
3. Run managed creation tests, affected CLI tests, Python static/type checks when available, and `git diff --check`. Restart local Studio only after confirming no active creation tasks.

Acceptance: delayed provider metadata succeeds without another create; wrong ownership fails; both real recorded Workspaces remain intact; the local Studio process loads the fix. No live creation is needed to establish the offline behavior.

## Risks, review and verification

Review: the fix changes only the timing of validation for owned Workspaces. Permanent absence waits until the existing bootstrap timeout and does not trigger duplicate allocation. A genuine conflicting value still fails immediately. A later SQL, IAM or Runtime issue is not covered by this fix.

Verification record (2026-09-23, branch `feat/from-main-20260922`, uncommitted diff): delayed-metadata test failed before implementation and passes after it; wrong ownership still fails. Read-only AIDAP/SQL checks pass for both recorded resources. `UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py -q`: 346 passed. CLI regression: 41 passed with local mock-server binding allowed. Python compilation and `git diff --check` pass. Ruff/Pyright are unavailable locally and Ruff is absent from the offline cache, so those checks are blocked. The local Studio process was restarted after confirming zero active creation tasks; its config endpoint reports automatic mode enabled and ready. No live retry or new cloud allocation was performed for verification.
