# Restore Frontend esbuild Lock Entries

[中文版](2026-10-09-restore-esbuild-lock-entries.zh.md)

## Metadata

- Change ID: `frontend-lockfile-sync`
- Created: 2026-10-09
- Revised: 2026-10-10
- Status: implemented
- Related component specs: none; this change restores generated dependency metadata without changing component contracts

## Background and Evidence

Pull request #23 fails the Harness Sidecar Release Gate during `npm ci --ignore-scripts`. The CI log reports that `esbuild@0.28.2` and its platform packages are missing from `frontend/package-lock.json`.

`frontend/package.json` is identical to `origin/main`. Commit `3f134207` removed 512 lock-file lines, including Vitest's nested esbuild package and platform-specific optional packages, without changing dependency declarations. The confirmed root cause is an incomplete generated lock file.

## Goals and Non-goals

### Goals

- Restore a lock file that is complete for supported CI platforms.
- Make `npm ci --ignore-scripts` and the affected frontend release gate pass.
- Preserve all declared dependency versions and product behavior.

### Non-goals

- Change frontend dependencies or version ranges.
- Change Studio UI, runtime behavior, or harness-sidecar contracts.
- Modify unrelated PR #23 implementation files.

## Scenarios and Requirements

### Scenario

Given the unchanged `frontend/package.json`, when CI runs `npm ci --ignore-scripts` on Linux, then npm must resolve the exact lock-file graph without reporting missing esbuild packages.

- `FR-1`: `frontend/package-lock.json` must contain the dependency graph generated for the current `frontend/package.json`.
- `FR-2`: The fix must not change `frontend/package.json` or component behavior.
- `FR-3`: The affected frontend gate, normal frontend tests, and production build must pass locally.

## Design and Contract Impact

Restore `frontend/package-lock.json` to the complete `origin/main` version because `frontend/package.json` is unchanged and the branch-only lock diff consists solely of accidental deletions.

- Interfaces and state: not applicable; no source contract changes.
- Concurrency and permissions: not applicable.
- Security: no credentials or external inputs are added.
- Compatibility: restores Linux CI compatibility while preserving dependency declarations.
- Component specs: no impact; the change corrects generated package metadata only.
- User documentation: no impact.

Alternative rejected: running a broad dependency upgrade. It would create unrelated version churn and does not address the confirmed accidental deletion narrowly.

## Implementation Tasks

- `T-1` (`FR-1`, `FR-2`): restore `frontend/package-lock.json` from `origin/main`.
- `T-2` (`FR-3`): run the affected installation, coverage, test, and build commands.
- `T-3`: review the final diff for unrelated changes and record verification evidence.

## Verification and Acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1` | `AC-1`: npm accepts the lock file | `npm --prefix frontend ci --ignore-scripts` | pass: 695 packages installed |
| `FR-2` | `T-1`, `T-3` | `AC-2`: dependency declarations and component contracts are unchanged | `git diff origin/main -- frontend/package.json` and diff review | pass: no package declaration or contract diff |
| `FR-3` | `T-2` | `AC-3`: affected coverage gate passes | `npm --prefix frontend run test:harness-sidecar-coverage` | pass: 22 tests |
| `FR-3` | `T-2` | `AC-4`: frontend tests pass | `npm --prefix frontend test` | pass: 1,377 Node tests and 65 Vitest tests |
| `FR-3` | `T-2` | `AC-5`: production build passes | `npm --prefix frontend run build` | pass |

## Risks and Open Questions

- `npm run build` may regenerate tracked web assets. Any generated diff must be reviewed and retained only if it is required by the current source.
- No open design questions remain.

## Review and Delivery Record

- 2026-10-09: Root cause confirmed from PR #23 CI logs and the branch diff.
- 2026-10-09: Design review found no contract, security, compatibility, or testability blocker.
- 2026-10-09: The user approved restoring the complete lock file and running the frontend gates.
- 2026-10-09: Restored the 512 deleted lock-file lines from `origin/main`; installation, affected coverage, complete frontend tests, and production build passed on diff scope `d3370fd1` plus this working-tree fix.
- 2026-10-09: `npm ci` reported existing dependency audit findings (6 low, 3 moderate, 6 high, 1 critical); dependency remediation is outside this lock restoration.
- 2026-10-10: Commit `5644e146` reintroduced the same 512-line deletion. Restored the lock file from current `upstream/main`; `npm ci --ignore-scripts`, 1,377 Node tests, 67 Vitest tests, 22 Sidecar coverage tests, and both production builds passed.
- Commit, push, and PR updates remain separately authorized operations.
