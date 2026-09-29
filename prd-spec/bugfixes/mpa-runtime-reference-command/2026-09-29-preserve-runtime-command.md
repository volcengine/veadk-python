# Preserve the reference Runtime command

[中文版](2026-09-29-preserve-runtime-command.zh.md)

- **Change ID:** `mpa-runtime-reference-command`
- **Date:** 2026-09-29
- **Status:** implemented
- **Contract:** [MPA Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md)

## Background and evidence

Live managed creation from a Ready reference Runtime produced a new Runtime in
version 0 `Error`. The reference used `Command="bash run.sh"`; the new Runtime
had an empty command. Source inspection confirms `template_from_runtime()`
copies image, resources, role, and project but omits `Command`.

## Goals and non-goals

- Preserve a reference Runtime's `Command` in the new Runtime create payload.
- Keep all existing identity, credential, endpoint, Tool, network, and
  environment sanitization unchanged.
- Do not infer a command when the reference omits it and do not change flat or
  explicit-template creation.

## Requirements and design

- **FR-1:** `managed.from-runtime` MUST copy `Command` when present.
- **FR-2:** Reference-owned identities and secrets MUST continue to be removed.
- **FR-3:** A missing reference command MUST remain absent rather than receiving
  a guessed default.

Add `Command` to the existing allowlist in `template_from_runtime()`. This is
the smallest root-cause fix and preserves the allowlist's security boundary.
No API, schema, permission, concurrency, or persistence changes are required.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| `FR-1` | `T-1` add a failing reference-template assertion, then update the allowlist | `AC-1` copied template contains the exact command | `uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py` |
| `FR-2`, `FR-3` | `T-2` run affected managed regressions | `AC-2` sanitization and command-absence behavior remain unchanged | same command plus `tests/integrations/mpa_managed/test_service.py` |

## Risks, review, and delivery

The command is already trusted Runtime configuration from the same account and
is passed to the same control-plane field. The risk is limited to preserving a
previously dropped value; rollback removes the allowlist entry. `review-spec`
is unavailable, so scope, security, compatibility, failure behavior,
testability, and bilingual equivalence were reviewed directly. No blockers
remain, and the user's instruction approves this fix.

Implemented on 2026-09-29. The regression failed before the implementation with
missing `Command`; after the one-field allowlist change, the two affected test
files pass all 58 tests. The present/absent reference-command tests execute all
12 executable lines in `template_from_runtime()` (100%). Changed-file
pre-commit Ruff and secret checks pass, as does `git diff --check`. The required
all-files pre-commit reaches and passes Ruff check and both secret scanners, but
Ruff format rewrites the unrelated pre-existing layout in
`veadk/integrations/mpa/managed/tasks.py`; that out-of-scope edit was reverted.
Live cloud recreation is `not_run` in this code-change step.
