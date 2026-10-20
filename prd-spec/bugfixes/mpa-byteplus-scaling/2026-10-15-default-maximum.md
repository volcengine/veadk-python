# Default BytePlus MPA maximum instances to 10

[中文版](2026-10-15-default-maximum.zh.md)

Date: 2026-10-15. Scope: Studio MPA creation only. Authorized by the user request to change the overseas BytePlus maximum instances to 10. Status: implemented and locally verified.

## Evidence, requirements and design

The creation dialog hardcodes 20 for fresh input, missing editable-draft values, the numeric buffer, new-request reset and localized help. FR-1: choose 10 for BytePlus and retain 20 for Volcengine using the trusted existing cloudProvider prop. FR-2: preserve explicit draft edits and submitted request values, including omission in legacy submitted requests; send the numeric value through the existing maxInstance API field. FR-3: interpolate provider-specific help text and regenerate WebUI assets.

Reuse the existing numeric input and validation. This changes a default scaling limit, not a hard cap or immediate instance allocation. Do not change backend/YAML/CLI profile defaults, minimum instances, concurrency, generic-agent creation or existing deployed Runtime configuration. No cloud operations, commit or push are authorized. The existing CON-21 scaling contract needs only a provider-specific default clarification in both languages.

## Review, tasks and acceptance

Direct design review (review-spec unavailable): provider selection, preserved request identity, legacy omission, localization and unchanged deployment mapping reviewed; no blockers. The user explicitly requested this scoped default change. T-1: failing React tests for fresh BytePlus submission, draft restoration, new-request reset and immutable retry. T-2: implement provider-aware defaults and localized help. T-3: run frontend tests, production build, i18n/assets checks, targeted existing backend scaling tests and proportionate browser verification. Acceptance: BytePlus new requests submit 10; Volcengine remains 20; explicit/legacy retry inputs are unchanged; generated assets match source. No component ownership or API/schema change.

## Verification

- pass: regression first, two new cases failed with expected 10 / actual 20; three explicit/legacy cases already passed.
- pass: `npm --prefix frontend test`, 1,389 Node tests and 116 component tests, including all five new cases.
- pass: `uv run --extra dev pytest -q tests/integrations/mpa_managed/test_creation_scaling.py`, 20 tests; no backend source changes.
- pass: `npm --prefix frontend run build`, TypeScript plus app/widget production bundles.
- pass: `npm --prefix frontend run check:i18n` and `npm --prefix frontend run test:webui-assets`, 113 packaged files / 350 internal references.
- pass: real browser using the actual React dialog and isolated mocked APIs on a temporary local server: BytePlus input/help 10, submitted maxInstance 10, new-request reset 10, zero rejected; Volcengine input/help 20. Temporary fixture/server/tab were removed; no real cloud creation.
- pass: `git diff --check`. Frontend-only change; Python Ruff/Pyright and harness/sidecar smoke are not_applicable.
- not_run: full Python regression (frontend defaults only; existing scaling tests cover the unchanged backend mapping), live cloud scaling, commit and push (not requested).

- pass: `uv run --extra dev pre-commit run --all-files`, formatting, secret scanning and dependency policy.
