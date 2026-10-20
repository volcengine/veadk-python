# Built-in Studio MPA creation profile

[中文版](2026-09-23-studio-builtin-mpa-profile.zh.md)

- Change ID: `studio-builtin-mpa-profile`
- Date: 2026-09-23
- Status: approved by the user's request to remove the Studio YAML dependency
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

Studio currently reads `VEADK_MPA_CREATE_CONFIG`, defaulting to `mpa-create.config.yaml`, for both configuration inspection and task submission. The child process reads the same file again. A missing file prevents creation before cloud checks. The current private Beijing profile contains nonsecret account/resource/image/model defaults and an environment reference for the model API key. Deployment credentials already come from the server environment or credential service.

## Goals, non-goals and scenarios

Studio creation must work without a YAML file. Its existing Beijing account, VPC/subnet, APIG, Runtime/worker images, model and PostgreSQL auto-provisioning defaults remain effective. Secret values remain outside source. The CLI `--config` YAML workflow, existing task records, existing agents and other regions are outside the behavioral change. No live resource creation is part of this change.

- Given no YAML and a valid model-key environment variable and deployment credentials, configuration inspection returns the normal safe summary and creation starts with the built-in profile.
- Given a stale `VEADK_MPA_CREATE_CONFIG`, Studio ignores it; the CLI still reads an explicitly supplied YAML path.
- Given a missing model key or deployment credentials, Studio reports a safe configuration error before cloud writes.
- Given a task starts, the fixed child uses the same built-in profile without reading a YAML path; retries preserve the original agent ID and inputs.

## Requirements and design

- **FR-1:** Add a code-owned, Beijing-only Studio profile matching the current nonsecret private YAML defaults. Keep fixed account/resource IDs, images and Runtime environment settings in this profile. Continue resolving `VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY` at runtime; never embed an API key, PG password, access key or session token.
- **FR-2:** Studio inspection and submission select the built-in profile regardless of `VEADK_MPA_CREATE_CONFIG`. Validate it with the same managed-profile rules and Studio Identity reuse logic as YAML profiles.
- **FR-3:** The task supervisor passes an explicit built-in-profile marker to the fixed child; the child resolves that profile with the requested region. Preserve YAML path handling for CLI and existing task APIs.
- **FR-4:** Keep task payloads, responses and logs free of model/deployment secrets. Unsupported regions and missing environment credentials fail before cloud writes with safe messages.

The profile remains intentionally scoped to the current Beijing deployment. Moving to another account, region or image requires a code change and review. Studio deployments must receive the required model-key and cloud-credential environment variables; the YAML path is no longer needed. The trusted boundary remains the Studio server and fixed child. No new browser input or persisted task field is introduced.

Affected files: managed profile loader and built-in defaults, Studio creation route, task-to-child transport, child runner, paired component contracts, bilingual operator docs and focused tests. CLI profile parsing remains supported.

## Tasks and tests

1. Add failing tests for built-in inspection without YAML, stale YAML path, matching defaults, missing secret, unsupported region, and child profile selection.
2. Add the built-in profile through the existing validator and switch only Studio to it.
3. Update both component-spec languages and operator docs; run managed creation and frontend tests, build/assets, Ruff, Pyright where installed, and pre-commit checks.

## Risks and acceptance

Hard-coded resource IDs can become stale and the pinned images can become obsolete; errors must remain explicit rather than silently selecting another account's resources. Existing task retries must not change their deployment identity. Acceptance requires Studio creation to have no YAML file read, the CLI YAML path to remain functional, no secret literal in source, and a child process that selects the same built-in settings. Tests must use simulated providers; live deployment is separate.

## Review and delivery record

Design review: the built-in profile passes through the existing validator, avoids a second configuration parser, keeps only nonsecret constants in source, and distinguishes Studio's file-free path from the CLI's explicit-file path. The user's request authorizes this scope.

Verification on 2026-09-23 against the uncommitted working-tree diff:

- **pass:** Managed creation and CLI tests (`394 passed`); frontend tests (`1305` Node and `36` Vitest passed); frontend build and web asset check; pre-commit Ruff and secret checks; built-in and existing private YAML profiles compare equal after validation, without printing secrets.
- **fail (unrelated optional dependency):** Broad parallel Python regression reached `5096 passed, 11 skipped, 2 xfailed` before `tests/cloud/test_harness_app_contract.py::TestHarnessConfig::test_spawn_applies_resource_overrides_to_clone_only` failed because `llama_index` is absent. Isolated rerun reproduced the missing dependency. Two runtime modules requiring absent `anthropic` were excluded from collection.
- **not_run:** Pyright, real-browser creation flow, and live cloud creation. The local Studio was not listening on port 8000 during the final check. Deployment or server restart is required before the new behavior can be observed.
