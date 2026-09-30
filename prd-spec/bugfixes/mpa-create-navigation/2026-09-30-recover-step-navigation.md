# Recover MPA creation step navigation

[中文](2026-09-30-recover-step-navigation.zh.md)

Change ID: mpa-create-navigation. Date: 2026-09-30. Status: approved.

## Evidence and scope

`MpaCreateDialog` restores submitted drafts at step 3, renders inert step labels,
and hides Previous for submitted requests. A lost POST response therefore leaves
users unable to inspect earlier settings. The user requested a fix and cloud update.

## Requirements and design

- FR-1: Step buttons and Previous allow inspecting earlier settings after restore.
  Forward navigation retains image/PG validation; busy requests disable navigation.
- FR-2: Submitted settings and retry identity stay locked. Preserve the existing
  New Agent action for failed/cancelled tasks. Unknown and running requests must
  retain their identity; navigation never submits or cancels a cloud request.
- FR-3: Preserve styling, keyboard focus, secret exclusion, and the API payload.

Reuse the existing dialog and validators; no new dependency.
Update Studio creation's navigation contract. Backend provisioning, task storage,
resource cleanup and automatic recovery are outside scope. An unknown original
request may have created resources, so navigation must preserve its identity.

## Tasks, acceptance and review

T-1/AC-1: Add regression tests for restored drafts, locked settings, navigation,
forward validation, running/busy states and explicit fresh draft creation.
T-2/AC-2: Implement step buttons and Previous, preserving identity and locks.
T-3/AC-3: Run frontend tests/build, measure added-line coverage, push and deploy;
verify the restored-draft flow in a browser without creating cloud resources.

Review: identity and bilingual scope reviewed; no automatic POST/reset on restore.
Approval: user's explicit fix/deploy instruction in this conversation.
Verification (2026-09-30): regression tests failed before the fix (pass as a
reproducer). Frontend suite: 1367 Node + 42 Vitest tests pass; build pass;
added executable statements: 3/3 covered (100%); pre-commit all-files pass,
including secret scans. Cloud/browser verification: not_run, deployment pending.
