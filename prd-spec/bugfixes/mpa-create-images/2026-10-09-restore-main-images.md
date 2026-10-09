# Restore main MPA creation image defaults

[中文版](2026-10-09-restore-main-images.zh.md)

- Change ID: `restore-main-images`
- Date: 2026-10-09
- Status: approved by the user's explicit request to withdraw public image discovery; implemented and locally verified; not committed or pushed.

## Background and evidence

A Worker CreateTool request failed with `InvalidParameter.ImageUrl` after Studio selected a public image using a digest reference. The user requires withdrawing the public registry discovery change and following main's two `/mpa/` `:latest` defaults. The earlier creation-page correction already follows main.

## Scope, scenarios and requirements

- FR-1: Restore built-in MPA image `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_agent:latest` and Worker image `agentkit-platform-2112682748-cn-beijing.cr.volces.com/mpa/mpa_codex_worker:latest`. Config inspection and POST use local profile defaults, without registry queries or digest conversion.
- FR-2: Restore main's creation dialog/client wiring and regressions. Remove discovery-only resolver, fixtures, tests, request-image helper and timeout/query extensions. Keep legacy explicit API images and pre-existing first-submission image snapshots.
- FR-3: Preserve STS-derived deployment account, automatic IAM preparation, network/APIG fixes, independent Worker creation, safe IAM diagnostics and main's named creation/basic details.
- FR-4: Reconcile bilingual specs/docs and regenerate packaged WebUI assets. Remove the withdrawn feature's documentation and accidental Vite cache artifact.

Non-goals: database/task/registry edits, clearing pending intents, live deployment, migration, committing or pushing. An old failed request may still contain the rejected digest in its immutable snapshot; it must not silently change on retry. A fresh request uses the restored defaults. `latest` is mutable and does not guarantee immutable image content across time.

## Design, affected files and contract assessment

Restore main versions of Studio routes, API client, dialog and image/name tests; retain IAM regression coverage. Change only image settings in `managed/studio_profile.py`, preserving its new-account/IAM/reference-free settings. Remove `frontend/server/mpa_creation_images.py`, discovery-only tests/conftest, and `CreationTasks.request_images`. Keep `CreationTasks.start` snapshot semantics unchanged. Current ownership/API defaults are maintained by [Studio creation CON-1/CON-9](../../../specs/studio-mpa-creation/README.md); restore their local-default contract in both languages. Other resource contracts are unchanged. Remove the superseded public-image PRD pair and point current specs to this correction.

## Tasks, tests and acceptance

1. T-1 / FR-1: Restore main's route/name regression expectations and observe failure against the discovery implementation.
2. T-2 / FR-1–FR-3: Withdraw discovery wiring and restore defaults; assert other branch behavior remains in the diff.
3. T-3 / FR-4: Synchronize documents and build assets; run creation/CLI Python tests, changed-file Ruff/Pyright, frontend tests/build/i18n/assets, pre-commit and an isolated browser flow.

Acceptance: exact default URLs in config and new task snapshots, no discovery code references or network dependency, unchanged legacy snapshots/owner isolation, main form without image fields, intact new-account changes, passing affected gates. No cloud writes are needed to prove the rollback; live cloud pull/readiness remains unverified.

## Review and risks

`review-spec` is unavailable; direct review covers scope, bilingual equivalence, compatibility, ownership, secret exclusion, retries, cancellation and tests. The user explicitly approved withdrawal; no further approval is required for this bounded rollback. Existing failed digest snapshots and mutable latest tags are the known limits. No blockers.

## Verification

Scope: uncommitted rollback against `df797f94`, using `origin/main` at `f6ed8ffa` as the reference. Execution date: 2026-10-09. T-1–T-3 and FR-1–FR-4 are complete within local rollback scope.

| Check | Outcome | Evidence |
| --- | --- | --- |
| Regression first | pass | Restored `test_new_creation_generates_owner_scoped_id_and_latest_images` and `test_authorized_config_returns_defaults_and_task_freezes_them`; both failed before withdrawal and pass after it. |
| `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q` | pass | 614 passed, 10 warnings; 2 workers selected for the local machine. |
| `npm --prefix frontend test` | pass | 1,377 Node tests and 65 Vitest tests passed; no skips. Covers recovery, retry, errors, cancellation, loading, keyboard/IME and owner isolation. |
| `npm --prefix frontend run build` | pass | App and widget built, packaged assets regenerated. Existing chunk-size/dependency warnings remain non-blocking. |
| `npm --prefix frontend run check:i18n` / `run test:webui-assets` | pass | 2 locales / 21 namespaces; 113 files and 350 internal references verified. |
| Changed-file Ruff / Pyright | pass | `uvx --from ruff==0.11.12 ruff check` and `uvx pyright --pythonpath .venv/bin/python` for the route, profile, tasks and two restored test modules: no findings. |
| `uv run --extra dev pre-commit run --all-files` | pass | Ruff check/format, hardcoded secret detection and YAML secret scanning passed. |
| Isolated real browser | pass | Mock configuration only: name required, description preserved, all three steps, no image inputs; final create entry enabled. 390×844 viewport has no horizontal overflow. No real submission; temporary files, tab and Vite process removed. |
| Contract/diff review | pass | Route/client/dialog match main; profile retains STS/IAM/reference-free differences, tasks retain IAM diagnostics. No runtime discovery references or dangling withdrawn-PRD links. Bilingual identifiers and links checked; `git diff --check` passed. |
| Real cloud creation / pull readiness | not_run | No cloud mutation authorized for this rollback. Existing failed task snapshots were not edited; start a fresh request after reloading Studio to use new defaults. |
| Full SDK regression / harness smoke | not_applicable | This rollback affects only managed Studio image selection and restores main contracts; shared SDK and sidecar behavior are unchanged. |

Local tests prove default selection and compatibility, not that cloud services accept or can pull either mutable tag. The user's existing Studio process was not restarted.
