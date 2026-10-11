# Use the entered MPA name in Skill Space descriptions

[中文版](2026-10-09-entered-name-description.zh.md)

- Change ID: `mpa-skill-space-description`; date: 2026-10-09; status: implemented.
- Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-3/CON-4.

## Background and scope

`managed/skills.py` currently creates `Description: Skills for MPA agent <agent_id>`. Studio creation now separates the entered Runtime name from the generated internal ID. A user identifying an agent by its entered name therefore cannot recognize the description. The user requested that this description use the entered name.

Change only descriptions of newly created named Skill Spaces. Keep generated `mpa_skills_<scoped hash>` names, `display_name` tags, IDs, ownership tags, database/channel/Worker bindings and internal ID generation unchanged. Existing/configured spaces are reused without updates. No cloud rename, migration, deployment, commit or push is in scope. Generic agents, UI, dependencies and permissions are unchanged.

## Requirements, scenarios and acceptance

- FR-1 / AC-1: A fresh named deployment creates `Description: Skills for MPA agent <trimmed runtime_name>`. Use the existing Runtime-name validation. Without a name, preserve the original internal-ID description.
- FR-2 / AC-2: Forward `runtime_name` from Runtime deployment to Skill Space preparation. Space names, tags and bindings remain based on internal identity. Existing spaces require no create/update, regardless of the supplied display name.
- FR-3 / AC-3: Preserve unknown-outcome recovery: no blind second CreateSkillSpace. When a pre-upgrade persisted request matches the complete current request with only its description restored to the original internal-ID value, replay that persisted request for discovery/ownership verification. Reject all other pending-input changes, including changed new descriptions or projects.

Scenarios: fresh named request has a recognizable description; unnamed CLI retains its behavior; an existing space remains untouched; a lost response from an old or new request is discovered exactly once; an undiscovered lost response or changed pending request remains an explicit error.

## Design and affected contracts

Add an optional keyword-only `runtime_name: str = ""` to `ensure_skill_space`, validate nonempty names with `validate_runtime_name`, and pass it from `RuntimeDeployer.deploy`. Description uses `runtime_name or agent_id`. The existing persisted `skill_space_request` already contains all recovery inputs; no field/schema migration is needed. Compare the full old-description candidate before permitting legacy recovery. Keep name discovery, ownership validation, locking, cancellation, timeout and resource cleanup rules unchanged. Description is presentation metadata and must not become an ownership key.

Production: `managed/skills.py`, `managed/runtime.py`. Tests: `test_agent_deployment.py`, `test_service.py`. Update the bilingual creation spec and managed README. No frontend, generated assets, external API request-body or runtime image change. Optional Python keyword preserves callers. No credentials or live user data in fixtures/evidence.

## Tasks and verification

1. T-1 / FR-1–FR-3: Add failing regressions for named/unnamed descriptions, internal binding stability, name validation, existing reuse, old/new lost-response recovery and pending-input refusal.
2. T-2 / FR-1–FR-3: Implement name forwarding and exact legacy-description recovery.
3. T-3: Run targeted deployment/service tests, managed/CLI regression with two workers, changed-file Ruff/Pyright, pre-commit, bilingual/link and whitespace checks; review consistency and record results.

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed/test_agent_deployment.py tests/integrations/mpa_managed/test_runtime_deployment_edges.py tests/integrations/mpa_managed/test_service.py -n 2 -q`; `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`; changed-file Ruff/Pyright; `uv run --extra dev pre-commit run --all-files`; `git diff --check`.

## Review, approval and risks

The user's request to replace the internal ID in the description with the entered name approves this narrow extension of the preceding naming fix. `review-spec` is unavailable; direct review checked request compatibility, full-payload recovery, ownership boundaries, errors and bilingual equivalence. No blockers. Old/existing spaces keep their descriptions; the improvement applies after restarting Studio to fresh creation. Display metadata does not imply a cloud ID or uniqueness guarantee. Live cloud operations are not authorized. Frontend/build/browser/sidecar gates are not applicable to this backend-only metadata change.

## Delivery record

T-1–T-3 and AC-1–AC-3 are complete. Direct implementation review verified that descriptions never authorize adoption, full legacy payload comparison preserves repeated unknown-outcome recovery, existing spaces are untouched, and changed pending inputs still fail. All pre-existing uncommitted changes, including the image-discovery rollback and Worker-name fix, are preserved separately.

Tested on 2026-10-09: the four changed Python files and affected managed/CLI suites in the uncommitted diff based on `df797f94`.

- `pass`: Regression-first checks reproduced six failures before implementation (two compatibility/default cases already passed).
- `pass`: Targeted deployment/edge/service command above: 182 tests. Final managed/CLI command with two workers: 686 tests, including named/unnamed creation, unchanged internal bindings, existing reuse, invalid names and old/new recovery.
- `pass`: Ruff 0.11.12 check/format on the four changed Python files; Pyright: zero errors/warnings.
- `pass`: `uv run --extra dev pre-commit run --all-files`, including both secret checks; bilingual pairs, contract identifiers and local design links; `git diff --check`.
- `not_run`: Full-repository Python regression; affected managed/CLI coverage was selected for this bounded metadata change.
- `not_run`: Real cloud creation/update; no live operations authorized or performed. Restart Studio before verifying a fresh creation in the console. Previously created spaces retain their original descriptions.
- `not_applicable`: Frontend/browser/build, sidecar and runtime-process smoke gates; no changes to those contracts or artifacts.

No commit, push or deployment was performed.
