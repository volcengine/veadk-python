# MPA creation maximum instances and highlighted errors

[中文版](2026-10-13-max-instance-input.zh.md)

- Change ID: `mpa-create-scaling`
- Created/revised: 2026-10-13
- Status: implemented
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-21

## Evidence and scope

The basic information step exposes name/description only. Managed Runtime settings already support `max_instance` and map it to AgentKit `MaxInstance`; the built-in profile currently selects 1. Request/task/runner inputs have no per-creation maximum. Name availability errors render as ordinary body paragraphs, so they lack the existing red error-container emphasis.

FR-1: Highlight the existing name-conflict message using the same danger/soft Alert as Studio confirmations; preserve the exact localized message and alert semantics. Reuse the component through public props, without a separate CSS/icon system.
FR-2: Add an editable numeric “Maximum instances” field in basic information. Fresh forms and new editable drafts default to 20, accept positive safe integers, and preserve edits while navigating/loading config. Reject empty, zero, negative and fractional input before Next/submission. Server validation rejects invalid integer types, including booleans/string numbers/floats, and values below configured minimum instances. The minimum and concurrency fields are not changed. A maximum of 20 is a scaling limit, not a request to start 20 instances.
FR-3: Carry explicit `maxInstance` through browser draft, POST, SQLite request identity and runner stdin; apply it to managed Runtime settings before preparing deployment, using the existing `MaxInstance` mapping and Runtime template snapshot. Submitted requests cannot edit the field; new-request action resets to 20. Changed values on retry conflict with the original request fingerprint. Omitted/null fields are not added to old fingerprints and preserve old profile behavior; submitted legacy drafts are not upgraded or shown a fictitious 20.

No modification of existing deployed Runtimes, generic-agent creation, minimum instances, per-instance concurrency, images, resource cleanup or provider adapters is included. No real cloud creation/scale change is authorized.

## Design, files and contract assessment

Reuse current numeric-field layout in the creation dialog and the danger/soft Alert already used by StudioConfirmDialog. Keep a text editing buffer for an empty/in-progress numeric input while recording a numeric canonical draft value. Optional API field `maxInstance` is a strict positive integer. Add a small scaling profile helper used by both the BFF (pre-task validation) and runner (actual deployment); the existing YAML/CLI Runtime default remains unchanged. Task persistence pins the value, and stdin passes it only when present. Preserve cancellation/late-response locks, existing step navigation and old saved inputs.

Files: MpaCreateDialog/API types/locales, authorized creation request, managed config/tasks/runner, targeted frontend and Python regression tests, paired PRD/spec/frontend documentation and packaged WebUI. Existing service/runtime mapping is reused; test emitted CreateRuntime/update settings rather than adding another mapping. Both domestic and BytePlus MPA use the same input, while generic agents use their existing separate flow. No database schema migration is required.

## Tasks, tests and acceptance

- T-1 / FR-1 / AC-1: failing React test for visible danger/soft name-conflict Alert; real browser confirms red emphasis and accessible text.
- T-2 / FR-2 / AC-2: fresh 20, editable integer, invalid numeric cases, navigation/config response, restored draft and old submitted request tests.
- T-3 / FR-3 / AC-3: BFF validation, task idempotency/stdin, runner and actual Runtime payload assertions; preserve old request fingerprint and configured defaults.
- T-4 / AC-4: targeted then managed deployment regression, Ruff/Pyright changed Python, full frontend tests/build/i18n/assets, browser normal/error/retry/keyboard/narrow cases, redacted secret and paired-document checks.

## Review, risks and authorization

`review-spec` is unavailable; direct review confirms ownership, reusable UI baseline, optional-field compatibility and separation from generic agents. The user approved this concrete plan with “按此方案实施（推荐）” on 2026-10-13. Direct review is complete and no design blockers remain; implementation and regression tests are authorized within this scope. Provider quotas/maximum limits remain enforced by AgentKit; no undocumented quota guarantee is introduced. Existing task snapshots prevent a retry from silently changing the scaling limit. Pre-implementation results were not_run; no commit, push, restart, deployment or cloud mutation is authorized.

## Implementation and verification — 2026-10-13

Scope: working diff based on `0dd3907d`, limited to FR-1–FR-3, their tests/documents and generated WebUI. T-1–T-4 and AC-1–AC-4 are complete. Direct implementation review confirmed numeric transmission to actual CreateRuntime/update payloads, independent profile copies, immutable task identity, strict server validation and unchanged general-agent routes. No blockers remain.

Regression-first evidence: before production changes, the targeted Python suite had 13 failed / 6 passed; React creation tests had 7 failed / 47 passed. The failures covered the missing UI/API/scaling behavior. Final results:

| Check | Result | Evidence / limitations |
| --- | --- | --- |
| Targeted Python | pass | 20 tests; strict types, configured minimum, omitted/null compatibility, subprocess stdin, idempotent retries, runner and emitted Runtime payloads. |
| Managed/deployment integration regression | pass | 998 tests using two workers; external services mocked, smoke markers excluded. |
| Frontend suite | pass | 1,389 Node tests and 95 React tests, including 57 MPA creation cases; existing category, deletion and cancellation coverage stays green. |
| Build / i18n / asset references | pass | Both app and integration widget rebuilt; 2 locales / 21 namespaces consistent; 113 packaged files / 350 references verified. Existing chunk-size/dependency warnings are non-blocking. |
| Changed Python Ruff / format / Pyright | pass | Five files; Ruff uses the repository pre-commit version 0.11.12. Pyright reports 0 errors / 0 warnings using the repository Python. Temporary `uvx` tools were used because these tools are not installed locally; no global configuration changed. |
| Real Chromium UI | pass | Real React dialog in an isolated temporary fixture; simulated APIs only. Checked desktop/narrow 390×844, default 20, numeric validation, keyboard increment, navigation preservation, numeric submission, read-only failed request, new request reset, BytePlus manual OV, legacy omission and both preflight/task-level duplicate alerts. Full Chinese alert text wraps without horizontal overflow. |
| Secret scan / documents / whitespace | pass | Changed-file scan with repository Gitleaks rules and redacted output; paired identifiers/numeric limits/commands/relative links reviewed; `git diff --check`. |
| Live cloud / Codex smoke / sidecar coverage | not_applicable | No cloud operations or harness/sidecar behavior changed; no live provisioning authorization. Actual provider quota/scale behavior was not exercised. |
| Commit / pre-commit / push / restart | not_run | Not requested or authorized. Before a future commit, synchronize the intended base and run required pre-commit/unit gates. |

An exploratory unpinned `uvx ruff check` selected Ruff 0.17.0 and failed with 17 findings under its expanded rules. It is not the configured repository gate; the pinned 0.11.12 check and format check both passed. No unrelated rules or production code were changed to hide this result.

Commands executed:

```bash
uv run --extra dev pytest tests/integrations/mpa_managed/test_creation_scaling.py -q --no-cov
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov
uvx --from ruff==0.11.12 ruff check frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
uvx --from ruff==0.11.12 ruff format --check frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
uvx pyright --pythonpath .venv/bin/python frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run check:i18n
npm --prefix frontend run test:webui-assets
git diff --check
```
