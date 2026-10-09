# Explicit new MPA request

[中文](2026-09-30-explicit-new-request.zh.md)

Change ID: mpa-create-new-request. Date: 2026-09-30. Status: implemented.
Predecessor: [navigation fix](2026-09-30-recover-step-navigation.md).
Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-9.

## Evidence, goals and scope

The directory opens `MpaCreateDialog`, which restores the regional browser draft.
Submitted drafts lock their settings. `startAnotherAgent` already resets identity,
defaults, secrets and state, but its guard/button only allow failed/cancelled tasks.
Users with uncertain POST outcomes or failed task lookup cannot open an editable
new request. The user explicitly approved generating a new request for New Agent.

FR-1: Any submitted draft offers the explicit New Agent action, including unknown,
running and cancelling tasks. It stays disabled during a pending UI action or
configuration load. Merely reopening or navigating never changes identity.
FR-2: Reuse the existing reset: fresh request/agent IDs, step 1, unlocked inputs,
configured image/PG defaults, empty description/OpenViking/TOS secrets and task
state. Same-ID retry remains unchanged until New Agent is clicked.
FR-3: Explain that New Agent does not cancel the old task. Only browser recovery
state is replaced; no POST/cancel/cloud mutation occurs until explicit submission.
Existing per-owner active-task admission may reject submission while old work runs.
Abort old polling and ignore late responses through the existing task-ID effect.

No API, Runtime/Worker, provisioning, task persistence or credential contract
changes. No new task-history UI or automatic cloud cleanup. Existing generated
agent IDs remain read-only. Reuse Button/ModalLayout, no CSS or dependencies.

## Tasks, acceptance and review

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1 | T-1: failing regression, then button/guard change | AC-1: uncertain/running/cancelling/unavailable tasks can explicitly open a fresh form; busy/loading cannot | `vitest run tests/mpaCreation.test.tsx` |
| FR-2 | T-2: reuse reset, bilingual help/user docs | AC-2: identities differ, defaults restored, all editable settings unlocked, secrets cleared, retry unchanged | dialog regression and added-statement coverage >95% |
| FR-3 | T-3: review, build, push/deploy | AC-3: no implicit start/cancel, late poll ignored; real browser edit/keyboard checks, cloud release | `npm --prefix frontend test`, `npm --prefix frontend run build`, pre-commit and browser |

Risks: the old server task/resources remain; its recovery record is replaced on
explicit New Agent. Reopening without that action still restores it. Admission
limits remain authoritative. Rollback is the previous Studio bundle.
Review: CON-9 exception and bilingual semantics reviewed; no automatic identity
change, cancellation or secret persistence. `review-spec` is unavailable; reviewed
directly. Approval: user's explicit New Agent/new-request instruction in this chat.
Verification (2026-09-30): regression failed before the fix (7 failures), then
targeted dialog tests passed 30/30. Added executable statements covered 1/1
(100%). Full frontend test: 1367 Node + 47 Vitest passed; production build and
pre-commit all-files (including secrets) passed. Code `4f1650de` deployed to the
existing cloud Studio (`f5d61f368888` / `xuime6ro`) at 11:02 Asia/Shanghai.
Cloud/browser: pass. The user's restored locked tab offered New Agent; Return
opened step 1 with a different ID and editable description/images. Description
and TOS bucket edits worked, OpenViking/TOS fields were enabled, and 720px-window
layout passed. Test values were cleared; no new MPA was submitted or old task
cancelled. The viewport was reset and the fresh form left open. Python checks:
not_applicable, no Python or API payload changes.
