# Three-step Studio MPA creation

[中文版](2026-09-23-studio-mpa-three-step-creation.zh.md)

- Change ID: `studio-mpa-three-step-creation`
- Created/revised: 2026-09-23
- Status: implemented and verified locally; uncommitted
- Component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and evidence

`MpaCreateDialog` currently puts the generated agent ID, images, resource plan and submit button on one screen. The ID is editable. Managed creation uses an existing PostgreSQL instance, with administrator and registry credentials resolved from server environment variables. It creates a distinct business database, but no PostgreSQL cloud instance. OpenViking has no per-creation input in the managed Studio flow, although the MPA Runtime accepts `OPENVIKING_URL` and `OPENVIKING_RESOURCE_ID`.

## Goals and non-goals

Make the ID read-only and arrange creation into three steps: agent basics, existing PostgreSQL instance settings, and OpenViking settings. Add the user-supplied Volcengine console links. Ensure submitted nonsecret settings reach the Runtime and task retry path. Preserve server-owned credentials and authorization. Cloud instance creation, browser-held passwords/API keys, unrelated CLI changes, and changes to existing agents are outside scope.

## Scenarios and requirements

- **FR-1:** A newly opened dialog retains the existing `mi-[0-9a-f]{24}` ID shape. The user can select/copy but cannot edit it; reopen and retry keep the same ID. An unsubmitted twelve-character draft from the brief regression is expanded using its unchanged request UUID; submitted identities stay unchanged for retry. Flat managed provisioning accepts the Studio ID in addition to the CLI's existing twelve-character ID.
- **FR-2:** The first step shows region, ID, description, images and resource plan. Next opens PostgreSQL, Back returns without submission, Next opens OpenViking, and only the third step starts creation. Keyboard, IME, narrow viewport, invalid values and missing server configuration are handled.
- **FR-3:** PostgreSQL step links to the supplied RDS list and accepts a host and port for an existing instance. Defaults come from the authorized server profile. The backend rejects a host/port that differs from its administrator connection, before cloud writes; database credentials stay server-side.
- **FR-4:** OpenViking step links to the supplied context-management page and accepts an optional HTTPS service URL and resource ID. The selected values are applied to the new Runtime; API keys continue to come from the server profile/reference. No secret is put in browser storage or task responses.
- **FR-5:** The task persists the nonsecret choices with the request ID; a lost response, retry or reopen uses the same values. Existing tasks and clients without the new fields retain their behavior.

## Design and contract impact

Extend `GET /web/mpa-creation/config` with nonsecret PostgreSQL host/port defaults. Extend `POST /web/mpa-creation/tasks` with optional `pgHost`, `pgPort`, `openvikingUrl`, `openvikingResourceId`. Validate URL syntax, port bounds, ID length and PostgreSQL administrator target at the server boundary. The task's existing payload persistence carries these nonsecret fields to the child runner. The runner applies them to a copied profile's Runtime environment. `AgentDatabaseProvisioner` still verifies administrator/Runtime host alignment. Empty OpenViking fields keep inherited Runtime settings. Changes to a pending task's choices remain a conflict. The generated ID is still accepted by the API for CLI/backward compatibility.

Permissions remain the existing agent-management permission; account and region remain server-verified. No new dependency, database schema, secret storage, or provider API call is needed. A provider console link does not grant permission or prove reachability. The supplied OpenViking link is an example resource path, not the service endpoint.

## Implementation tasks

- **T-1:** Add failing wizard/ID/link/validation tests and backend override/security tests (`FR-1`–`FR-5`).
- **T-2:** Add localized three-step UI and small responsive styles (`FR-1`–`FR-4`).
- **T-3:** Extend the typed API, backend validation, task payload, and runner profile override (`FR-3`–`FR-5`).
- **T-4:** Update both component specs and operator docs; run the affected tests, type/style checks, build and browser checks (`FR-1`–`FR-5`).

## Acceptance and verification

- **AC-1:** The ID cannot be changed in the form; Back/Next preserve edits and do not send POST.
- **AC-2:** The two console links open the requested destinations. Submit occurs only on step three after validation.
- **AC-3:** PostgreSQL mismatch and malformed OpenViking values fail before provisioning; valid choices reach the Runtime environment without changing secrets.
- **AC-4:** Repeated requests with the same identity and choices reuse the task; changed choices conflict. Existing payloads still work.
- **AC-5:** Frontend tests/build, targeted Python tests, changed-file Ruff/Pyright, bilingual checks and a real browser pass. Do not claim live cloud deployment from simulated tests.

## Risks, review and delivery record

The existing profile must already point to the chosen PostgreSQL instance and supply a usable login and administrator connection. The wizard cannot establish private network access or create the instance. Direct review found that passing credentials through the current task SQLite payload would violate the existing security contract, so this design keeps them server-owned. The existing OpenViking API key remains configured on the server; choosing a URL/resource ID alone does not create or authorize an OpenViking resource.

On 2026-09-23, direct design and implementation review confirmed the POST rejects mismatched PostgreSQL targets and malformed OpenViking settings before task creation. A definite HTTP 400/422 rejection unlocks the form for correction; an uncertain network failure retains the submitted request identity and choices for idempotent retry. Existing clients omit the new fields and retain the previous provisioning path. The two translations and component contracts were checked for matching fields, limits, links and behavior. User review caught an unintended shortening of generated Studio IDs. The correction restores the previous 24-character suffix and adds compatible validation for the flat provisioning path; CLI generation stays at 12 characters.

Verification on the current uncommitted diff: `npm --prefix frontend test` **pass** (1,305 Node tests and 30 Vitest tests); `.venv/bin/pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` **pass** (284 tests); Ruff check/format of changed Python files **pass**; Pyright with `.venv/bin/python` **pass** (0 errors); TypeScript `tsc --noEmit` **pass**; `npm --prefix frontend run build` **pass**; `npm --prefix frontend run test:webui-assets` **pass** (104 files, 248 references); `git diff --check` and bilingual identifier/pair checks **pass**; diff-based Gitleaks scan **pass**. A local browser preview **pass** for all three steps, both console links, read-only ID, narrow width and invalid OpenViking input; it used mocked configuration and did not call cloud provisioning. Live cloud deployment is **not_run** because it would create provider resources. `uv run --extra dev` was **blocked** by the sandbox's inability to write the global uv cache; equivalent targeted tests and checks used the existing repository environment and cached tools instead. Pre-commit `--all-files` is **not_run** because no commit is requested.

After restoring the original Studio ID length, focused dialog tests **pass** (15 tests, including safe draft migration and submitted-ID preservation), `.venv/bin/pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py -q` **pass** (298 tests), changed Python Ruff check/format **pass**, TypeScript check **pass**, rebuild **pass**, packaged assets **pass** (104 files and 248 references), bilingual ID contract check **pass**, and `git diff --check` **pass**. The broad frontend test result above predates this ID correction; the focused dialog suite covers it. Live provisioning remains **not_run**.
