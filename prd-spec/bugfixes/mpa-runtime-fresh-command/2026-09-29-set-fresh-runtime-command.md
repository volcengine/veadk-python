# Set the Fresh Managed Runtime Command

[中文版](2026-09-29-set-fresh-runtime-command.zh.md)

- **Change ID:** `mpa-runtime-fresh-command`
- **Date:** 2026-09-29
- **Status:** implemented
- **Contract:** [MPA Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md)
- **Predecessor:** [Preserve the reference Runtime command](../../mpa-runtime-reference-command/2026-09-29-preserve-runtime-command.md)

## Background and evidence

After workload identity provisioning was fixed, a live Studio creation using
the built-in profile reached Runtime creation with the requested MPA image,
Worker Tool, and TOS environment, but the Runtime entered version 0 `Error`.
Its `Command` was empty. The earlier fix preserves a reference Runtime command,
but the built-in Studio profile uses `fresh_template()` and has no reference.
The selected MPA Runtime image is started by `bash run.sh`.

## Goals and non-goals

- Set `Command="bash run.sh"` on fresh managed MPA Runtime templates.
- Preserve explicit JSON-template and reference-Runtime command behavior.
- Do not make the command user-configurable or infer it from arbitrary images.

## Requirements and design

- **FR-1:** `fresh_template()` MUST emit the standard MPA command `bash run.sh`.
- **FR-2:** `managed.from-runtime` MUST continue preserving the reference command.
- **FR-3:** An explicit JSON template remains authoritative and is not modified unless the existing Runtime settings do so.

The command is one fixed field in the existing MPA-only fresh template. No API,
schema, permission, persistence, or dependency change is required.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1–FR-3 | T-1 add a failing flat-source assertion and set the fresh-template field | AC-1 all managed source regressions pass | `uv run --extra dev pytest tests/integrations/mpa_managed/test_service.py tests/integrations/mpa_managed/test_agent_deployment.py` |
| FR-1 | T-2 retry live Studio creation | AC-2 the new Runtime progresses beyond version 0 Error with the command present | local Studio creation and Runtime inspection |

## Risks, review, and delivery

This is scoped to the MPA-only fresh template and the same command already used
by the known-good reference Runtime. Rollback removes the field. The design was
reviewed directly for scope, compatibility, security, and testability; the user
requested fixing the creation blockers and retrying a new Runtime. The targeted
60 tests and full 5259-test regression passed. Live Studio creation produced
Ready Runtime `r-yew4qlw5c017agjttpcw` at version 2 with
`Command="bash run.sh"`.
