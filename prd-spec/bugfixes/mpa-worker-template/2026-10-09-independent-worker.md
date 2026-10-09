# Worker creation without an old-account template

[中文版](2026-10-09-independent-worker.zh.md)

- Change ID: `mpa-worker-template`
- Created/revised: 2026-10-09
- Status: implemented
- Contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md), [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md).

## Background and evidence

Studio's built-in Worker profile references a Tool in a previous account. A fresh deployment account cannot read that Tool: creation fails at `get_reference_worker` before `CreateTool`. The Worker image is already explicit. `worker.py` only copies environment settings from the reference; command, resources, role and networking come from the provisioner. The pinned Worker source revision `81f3496`, `scripts/run.sh`, supplies startup defaults without a reference Tool.

## Goals, non-goals and scenarios

Allow a fresh account to create a Worker from its image and explicit startup settings. Keep optional references/existing Workers compatible. Do not change images, IAM/networking, Runtime chat, frontend, or automatically modify existing Tools. Registry image access remains an independent prerequisite.

- Fresh Studio creation reaches `CreateTool` without reading an old reference.
- A CLI profile may explicitly inherit an accessible Tool's environment, with explicit settings taking precedence.
- Missing explicit references remain failures; retrying an uncertain creation preserves its payload/token.

## Requirements and design

- **FR-1:** Remove built-in `reference-id`. Pin nonsecret `PORT`, Worker port, headless/minimal mode, workspace/data/runtime/sidecar roots and Skill Space base directory to the pinned image's defaults.
- **FR-2:** Add optional `managed.worker.env: dict[str, str]`, default empty. Resolve whole `${ENV_NAME}` references on the server. Reject invalid uppercase environment keys, agent/Runtime/Tool/Skill Space bindings, inherited channel/Runtime credentials and control database URLs. Nonempty env with `existing-id` fails rather than being silently ignored.
- **FR-3:** Merge filtered reference environment, explicit env, then generated `MPA_AGENT_ID`. Do not mutate the profile or reference response. Optional explicit reference failure never falls back to an empty environment.
- **FR-4:** Keep sorted request hashing, ClientToken, ownership validation, cancellation and bounded retry unchanged. Changed explicit env on an unfinished request is a configuration conflict. Do not persist env values in deployment records or expose them in config summaries, repr or error responses.

The existing image contract handles model credentials per session; Studio does not copy old model keys. Additional operator settings use Worker env with server secret references. No new dependency, cloud API, permission, task schema or frontend asset is required. The Studio component owns the new configuration contract; Runtime provisioning references it. Legacy non-managed creation is unchanged.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1 | T-1: update built-in profile and regression | AC-1: image-only fresh-account request skips reference lookup and carries explicit startup settings |
| FR-2 | T-2: config schema/resolution and safe validation tests | AC-2: secret refs resolve; invalid/owned keys and existing-worker env fail without exposing values |
| FR-3 | T-3: request merge and compatibility tests | AC-3: explicit values win, agent binding remains generated, explicit missing reference still fails |
| FR-4 | T-4: retry/immutability tests and review | AC-4: unchanged payload retries use the same token; changed env fails; registry/summary/repr exclude env values |

## Risks and recovery

Defaults cover the pinned image; custom images may need explicit env. No cloud creation smoke is performed automatically. Existing Tool IDs remain authoritative; no rename/update. Tasks that failed before Worker intent creation can retry with the same agent ID after Studio restarts. Already-dispatched tasks with changed hashes require their original configuration; never reset intent to bypass duplicate protection.

## Review and verification record

Direct design review (review-spec unavailable) cleared configuration precedence, secret handling, account boundaries, partial failure, compatibility and bilingual equivalence. User approved the proposed removal of the fixed old template and explicit configuration with “帮我改” on 2026-10-09 before implementation.

Verification scope: this Worker change on `ef0ad519` plus prior uncommitted account/IAM/network/APIG fixes. Required commands: targeted config/Worker tests, managed provisioning regression, changed-file Ruff/Pyright, scoped pre-commit, bilingual/link/whitespace checks. Live cloud creation: `not_run`; code and simulated requests cannot prove image pull permissions or platform readiness. Browser/frontend gates: `not_applicable`, no UI/API changes. Results will be recorded after execution.

### Executed checks (2026-10-09)

- `fail` before implementation: config/Worker regression reproduced the fixed old reference and missing env support (5 failed, 94 passed).
- `pass`: `uv run --extra dev pytest tests/integrations/mpa_managed/test_config.py tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker_metadata.py -q --tb=short` — 152 passed.
- `pass`: `uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 594 passed, 5 existing deprecation warnings; includes final reference filtering and pending-env recovery.
- `pass`: `uvx --from ruff==0.11.12 ruff check` and `uvx pyright --pythonpath .venv/bin/python` on `config.py`, `worker.py`, `studio_profile.py`, `test_config.py`, `test_worker.py` in their managed source/test directories — zero errors.
- `pass`: `uv run --extra dev pre-commit run --files` on the five Python files and all eight changed documentation files — Ruff and hardcoded-secret detection passed. YAML hook `not_applicable` (no YAML changed).
- `pass`: paired language identifiers/relative links and `git diff --check`. Direct implementation review found no blockers: no reference lookup in the simulated new-account request, explicit override/immutability, filtered bindings/control URLs, safe secret refs and unchanged pending-token protection. AC-1 through AC-4 passed with simulated requests.
- `not_run`: live image pull/container startup and broad unrelated SDK regression. The isolated managed suite covers the affected contracts; no cloud resource was created for verification. `not_applicable`: frontend build/browser, generated assets and runtime process smoke (no chat/frontend/image code changes). Full all-files commit gates await a separately authorized commit.

T-1 through T-4 are complete. No agreed implementation scope is deferred; live platform readiness remains an operational validation limit. Restart local Studio and retry the same agent that stopped before Worker intent creation.

Startup-default follow-up: [2026-10-09-worker-image-defaults](2026-10-09-worker-image-defaults.md) supersedes the explicit built-in env choice in FR-1/AC-1. Initial verification above is historical evidence; all other contracts remain.
