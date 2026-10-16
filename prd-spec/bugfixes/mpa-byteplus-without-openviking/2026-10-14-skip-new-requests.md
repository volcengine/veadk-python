# Temporarily skip OpenViking in new BytePlus Studio requests

[中文版](2026-10-14-skip-new-requests.zh.md)

Change ID: mpa-byteplus-without-openviking. Date: 2026-10-14. Status: superseded; temporary behavior restored on 2026-10-14.
Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-17/CON-18.

## Evidence, goals and scope

A BytePlus task reached OV creation after PG/network/IM Gateway/Worker succeeded, then failed with ProductUnordered. The user explicitly requests skipping OV to test the rest of the creation/chat chain. Do not purchase/activate services or change billing. Preserve domestic automatic OV and already-submitted request identity; do not reset the uncertain-create guard or change existing resource bindings.

## Requirements and scenarios

- FR-1: Built-in BytePlus configuration stops advertising automatic OV for new requests; domestic defaults continue advertising it. Explicit prior automatic requests and manual profiles retain supported behavior.
- FR-2: New BytePlus forms and editable restored drafts clear OV auto selection and manual fields when the server no longer advertises auto. Show a localized skipped-memory explanation, hide OV inputs, and submit without auto or credentials. Submitted automatic/manual requests preserve their original fields and retry intent.
- FR-3: Blank request fields use the existing manual-disabled server path, remove inherited OPENVIKING_* variables and never call OV provisioning. PG, IAM, network, APIG/IM Gateway, Worker, Skill Space, Runtime and general agents keep their existing contracts.
- FR-4: Keep three-step navigation, console link, optional TOS, cancellation, new-request action and retry behavior. Old failed automatic requests require the existing New Agent action; they are not silently converted.

## Design, tasks and review

T-1: config.py disables only built-in BytePlus auto availability. The existing with_creation_resources empty-input behavior owns Runtime omission; no new API enum or dependency.
T-2: MpaCreateDialog.tsx clears OV choices only for editable BytePlus requests with no server auto availability and clears memory-only key state. Render the existing paragraph/layout for the skipped state; no CSS/icon/component extension. Add paired locale copy. Archived automatic and nonempty manual requests retain their existing UI.
T-3: Test profile defaults, domestic compatibility, old explicit auto, restored editable draft, submitted retry and no-OV Runtime payload (including inherited settings) before implementation. Run managed/startup Python, Ruff/Pyright, frontend test/build/i18n/assets, isolated browser normal/retry/narrow/Escape checks and secret scanning.
T-4: Synchronize this bilingual design, component contract and module/frontend READMEs; preserve unrelated local changes and generated outputs from other tasks.

Approval: user's explicit 2026-10-14 request to temporarily skip BytePlus OV; the implementation scope was stated before editing. Direct review (review-spec unavailable) checked boundaries, absent-field compatibility, immutable submitted requests, secret omission and bilingual equivalence; no blocker. Repository-referenced frontend-design/ui-ux-pro-max files are unavailable at their paths or installed skill roots; use the existing dialog and Foundation/SPEC rules without introducing visual design.

## Acceptance and risks

AC-1 (FR-1): BytePlus new config omits auto; domestic still advertises auto; explicit old auto resolves unchanged.
AC-2 (FR-2/FR-4): New/restored editable BytePlus requests contain no OV credentials/auto and display the skipped explanation; retries preserve submitted identity and values. Existing manual recovery still works.
AC-3 (FR-3): Mocked BytePlus provisioning reaches Runtime with no OPENVIKING_* values, including inherited template/reference values; no OV API is called.
AC-4 (all): Required targeted/regression/static/frontend/browser/secret gates pass with actual evidence. Live chat validation is separate and user-driven. No server restart, cloud mutation, commit or push in this implementation.

The resulting agent has no OV-backed long-term memory. This change cannot make an old automatic task retry as a different request. Other cloud/model/startup errors may still prevent the full chain from succeeding.

## Verification

2026-10-14, diff based on 2ffe6e14. not_run: implementation checks pending. Live cloud creation/chat not_run; no automatic additional resource writes. Harness/Codex smoke not_applicable because execution protocols are unchanged.

Verification completed 2026-10-14: pass, failing regressions reproduced BytePlus auto advertisement and retained editable auto draft; an additional failure reproduced submitted intent being cleared by configuration refresh. All fixed. pass: `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` (1,045 tests, four dependency warnings, two workers). pass: `npm --prefix frontend test` (Node suite and 100 React cases), production build, i18n (2 locales/21 namespaces), packaged assets (113 files/350 references). pass: Ruff 0.11.12 and Pyright with explicit repository Python interpreter on all three changed Python files (zero errors/warnings). pass: actual dialog in Chromium with mocked cloud APIs, normal no-OV submission, same-request retry, editable stale draft, submitted auto recovery, domestic auto, narrow viewport and Escape. pass: repository Gitleaks hook over 128 isolated in-scope source/doc/generated files. Browser fixture initially lacked application theme tokens; it was corrected to import the real theme and set the same light default before final visual verification. Temporary browser files/server removed. pass: paired identifiers/links and diff whitespace. not_run: full-repository/all-files pre-commit because no commit requested; focused static/secret and affected regression gates were used. No new dependencies, billing changes or cloud writes. Existing package-lock changes are preserved.

Superseded by [restore OV and complete Runtime diagnostics](../mpa-runtime-diagnostics/2026-10-14-sdk-json-and-restore-ov.md), explicitly requested after OV allowlisting. Historical evidence below describes the temporary skip only.
