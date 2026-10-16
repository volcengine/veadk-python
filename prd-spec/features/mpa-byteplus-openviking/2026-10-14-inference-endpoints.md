# BytePlus OV inference credentials

[中文版](2026-10-14-inference-endpoints.zh.md)

Change ID: `mpa-byteplus-ov-inference-endpoints`. Date: 2026-10-14. Status: implemented; live acceptance pending.
Predecessor: [automatic creation](2026-10-14-automatic-creation.md).
Contract: [CON-18](../../../specs/studio-mpa-creation/README.md).

## Background and approved scope

The supplied overseas script supports ordinary inference credentials with `Source=volcengine`, `ApiKey`, and an `EndpointID` for each model. The initial local integration implemented only Coding Plan. The user explicitly requests removing Coding Plan and using ordinary API Key plus inference endpoints; the user also requests trying the domestic endpoint identifiers as overseas defaults. This approval replaces the predecessor's credential decision, not its personal-edition or separate Runtime-adaptation scope.

## Goals, scenarios and requirements

- FR-1: BytePlus automatic creation reuses the ordinary model key resolved by the existing MPA creation pipeline, including deployment-credential discovery. Do not read `OV_MODEL_API_KEY`, add a browser secret, or fall back to Coding Plan/AgentPlan.
- FR-2: Create a developer library with top-level and per-model `Source=volcengine`. Keep overseas model names `seed-2-0-lite` and `skylark-embedding-vision`; omit ModelVersion. Default EndpointID values are `doubao-seed-2-0-lite-260428` and `doubao-embedding-vision-251215`, explicitly requested for trial, not verified overseas. Server `OV_VLM_ENDPOINT_ID` and `OV_EMBEDDING_ENDPOINT_ID` override them. Each must be 1–128 ASCII letters, digits, hyphens, underscores or periods, starting with a letter/digit. Explicit blank or invalid values fail before cloud mutation, without echoing the value.
- FR-3: Save nonsecret Source/EndpointID in the existing OV intent. Retries with changed endpoints or a prior Coding Plan intent fail as configuration conflicts without creating or altering another library. Previously missing-key failures without an OV intent can retry. Unknown create outcomes, cancellation, retention, locking and readback validation remain unchanged.
- FR-4: Keep domestic model parameters, submitted manual requests, normal agents and four OV Runtime variables unchanged. Do not create model endpoints or change Runtime memory code.
- FR-5: Update localized UI and bilingual instructions to explain reuse of inference credentials and configurable endpoints, removing the Coding Plan prerequisite. Preserve layout and interactions.

## Design, affected files and tasks

T-1 (FR-1/2): Replace the dedicated key resolver in managed/openviking.py with a nonsecret endpoint resolver; config.py validates endpoints, service.py captures them before mutation and passes them to ensure_openviking, which uses the existing resolved model key. Optional keyword arguments preserve domestic callers.
T-2 (FR-3/4): Retain intent comparison and strict Get readback. Do not migrate existing Coding Plan libraries; their source cannot be silently changed. Only current-process endpoint choices are captured; a restart with changed configuration fails safely against a recorded intent.
T-3 (FR-5): Update locale strings, managed README pair, frontend README, CON-18 pair and generated web assets.
T-4: Test first, run managed/startup and UI regressions, Ruff/Pyright, build/i18n/assets checks, browser verification and secret scanning. No live cloud side effects during tests.

## Review and acceptance

User approval: explicit request to replace Coding Plan and follow domestic endpoint defaults, 2026-10-14. Direct design review (review-spec unavailable): scope, script schema, credential separation, safe failures, retry compatibility and bilingual equivalence reviewed; no design blockers. Resource IDs, secrets and account entitlements are not inferred.

- AC-1: With no OV_MODEL_API_KEY, default BytePlus auto configuration succeeds; the created request contains the resolved ordinary key and both endpoints. Existing domestic regression remains passing.
- AC-2: Override, blank/malformed endpoints, changed endpoint retry, prior Coding Plan intent, remote endpoint mismatch, cancellation and ambiguous creation are covered; errors and registry never contain model keys.
- AC-3: UI no longer asks for Coding Plan; tests/build and focused browser verification pass. No new inputs, IME or keyboard behavior changes.
- AC-4: Both document languages, contract and generated assets agree; record actual checks and unverified live scope below.

## Risks and verification record

The requested default endpoint identifiers may not exist or be callable with the overseas account's key. Provider rejection must remain an explicit error; operators can set actual endpoints and retry only when no conflicting library was created. This implementation does not prove Runtime personal-user or overseas data-plane support. Live provisioning/memory tests are not_run: no cloud creation authorized for this code change and Runtime adaptation is separate. Commit/push are outside this request.

2026-10-14: implementation checks pending; scope is the current uncommitted BytePlus OV diff on this branch. Existing unrelated contract relocation, OpenSpec deletion and lockfile edits are preserved.

## Verification results (2026-10-14)

Tested scope: current uncommitted BytePlus OV change based on `2ffe6e14`; no commit, push or cloud deployment.

- pass: test-first OV regression reproduced 14 failures before implementation; after implementation OV-targeted tests passed (52).
- pass: `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` — 1,004 passed, 4 warnings. Two workers match repository guidance. The initial added service test used an incorrect Profile constructor and domestic network fixtures; corrected those test fixtures, then reran the complete affected suite successfully.
- pass: `npm --prefix frontend test` — 1,389 Node and 96 React tests.
- pass: Ruff 0.11.12 check/format on five changed Python files; Pyright with `.venv/bin/python` — 0 errors/warnings.
- pass: `npm --prefix frontend run build`, `run check:i18n` (2 locales/21 namespaces), `run test:webui-assets` (113 files/350 references), `git diff --check`.
- pass: real Chromium using the actual dialog and mocked API responses: ordinary-key wording, no Coding Plan prerequisite, no manual secret fields, explicit endpoint error, same-request retry, manual recovery, domestic copy, Escape, and 390px viewport. The first temporary fixture omitted component theme imports; corrected the fixture and repeated the browser check. Temporary pages and their isolated Vite server are removed after checking.
- pass: bilingual requirement identifiers/local links; existing unrelated lockfile hash unchanged.
- not_run: full repository Python suite and all-files pre-commit because scope is the MPA integration and locale copy, no commit requested; affected regression and full frontend gates run instead. Harness/Codex smoke not_applicable: runtime/sidecar contracts unchanged.
- not_run: live overseas endpoint invocation, paid library creation and Runtime memory integration. Do not infer overseas validity of the requested default EndpointIDs from offline success.

- pass: `uv run --extra dev pre-commit run gitleaks --files <changed-existing-files>` — source, tests, documents and built assets; no secrets detected.
