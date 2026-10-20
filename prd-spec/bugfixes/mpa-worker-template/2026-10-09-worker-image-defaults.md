# Use Worker image defaults without duplicate Tool environment

[中文版](2026-10-09-worker-image-defaults.zh.md)

- Change ID: `mpa-worker-image-defaults`
- Created/revised: 2026-10-09
- Status: implemented
- Predecessor: [independent Worker creation](2026-10-09-independent-worker.md), amends its FR-1/AC-1 startup-setting choice only.
- Contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md); Runtime provisioning consumes that contract unchanged.

## Evidence, goals and scope

The pinned Worker source `81f3496` Dockerfile defines PORT=8000, MPA_CODEX_WORKER_PORT=8092, headless/minimal mode and all five configured directory roots. scripts/run.sh also supplies these defaults and synchronizes PUBLIC_PORT from PORT. Duplicating the nine defaults in Tool Envs is unnecessary and overrides defaults when an operator selects another image. The control-plane Tool environment list is not the full container environment.

Remove only the nine built-in Worker env entries. Keep optional managed.worker.env, reference/existing Worker support, fixed CreateTool.Port=8000 and generated MPA_AGENT_ID. Do not mutate existing Tools, chat, frontend, image versions, permissions or resource identity. Custom images must support the existing /opt/gem/run.sh entrypoint and public port 8000, or use explicit compatible configuration; removing duplication does not guarantee arbitrary image compatibility.

## Requirements, scenarios and design

- FR-1: Built-in Studio has empty Worker env and no reference ID. Its new CreateTool Envs contains only generated MPA_AGENT_ID; Port remains 8000. Container startup obtains its port/mode/path settings from the image.
- FR-2: Preserve explicit Worker env merging, validation, redaction and sorted hashing/ClientToken behavior. Existing bindings are not updated. A previously dispatched pending request with changed env still fails hash validation rather than creating a duplicate.
- AC-1: Built-in profile and simulated new-account creation tests prove no duplicate env keys/reference lookup, retain image/role/Port and bind MPA_AGENT_ID.
- AC-2: Existing config/Worker recovery regressions pass, including explicit env and changed-pending-payload rejection.

No state/schema/API/permission/dependency changes. The Studio spec and bilingual guide describe image-owned defaults; no frontend assets are needed.

## Tasks, review and verification

- T-1 (FR-1/AC-1): failing built-in profile/request regressions, remove env block in studio_profile.py, update test_config.py/test_worker.py.
- T-2 (FR-2/AC-2): existing affected provisioning regression and Python gates; synchronize Studio spec/guide and predecessor note.

User approved removal of all unnecessary defaults on 2026-10-09 with “没必要的就都去了”. Direct design review (review-spec unavailable) cleared bilingual equivalence, entrypoint/port boundary, explicit overrides and pending-intent safety before edits. No blocker or unanswered implementation decision.

Verification scope: this follow-up on ef0ad519 plus prior uncommitted MPA fixes. Required: fail-first two targeted tests; managed/legacy provisioning and IAM suite; Ruff/Pyright on three changed Python files; scoped pre-commit and paired-language links/identifiers/whitespace. Live cloud startup is not_run (no new cloud writes authorized for verification); frontend/browser/generated assets and runtime process smoke are not_applicable (no changes to those paths). Full commit gates await an authorized commit. Results follow below.

## Results (2026-10-09)

- fail before implementation: two targeted tests failed on the duplicate defaults (97 deselected).
- pass: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 594 passed, five existing deprecation warnings. AC-1/AC-2 and T-1/T-2 completed with simulated requests.
- pass: `uvx --from ruff==0.11.12 ruff check` and `uvx pyright --pythonpath .venv/bin/python` on studio_profile.py, test_config.py and test_worker.py in their managed directories; zero errors.
- pass: `uv run --extra dev pre-commit run --files` on these three Python files and eight changed documentation files; Ruff/format/hardcoded-secret detection passed. YAML hook not_applicable, no YAML changes.
- pass: paired identifiers/relative links and `git diff --check`; direct implementation review confirms image defaults, generated agent binding and optional explicit env coexist without changing recovery protection.
- not_run: live cloud creation/container startup and unrelated full SDK regression; affected deployment suite passed. not_applicable: UI/build/browser/generated artifacts and runtime smoke. No cloud resources or existing Tools changed. Full commit gates await authorized commit.
