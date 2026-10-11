# Use writable temporary state for Studio MPA creation

[中文版](2026-09-23-use-temporary-state.zh.md)

- Change ID: `studio-mpa-writable-state`
- Created/Revised: 2026-09-23
- Status: implemented
- Related component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)
- User approval: 2026-09-23, use `/tmp` as the temporary cloud fix instead of implementing TOS persistence now.

## Background and evidence

The deployed Studio code directory is read-only. The first MPA creation request fails before starting its child process because `CreationTasks` tries to create `.adk/mpa-creation.sqlite3`; automatic PostgreSQL preparation would later fail for the same reason at `.adk/mpa-pg-bootstrap.sqlite3`. A local read-only-directory reproduction and runtime instrumentation confirmed the first failure. Both stores contain nonsecret control state, but require a writable filesystem.

Expected behavior is that an authorized cloud Studio request can start creation. Actual behavior is HTTP 500 before task submission.

## Goals and non-goals

Goals:

- Put the built-in cloud Studio task database and PostgreSQL bootstrap database under `/tmp/veadk-studio/`.
- Preserve explicit `VEADK_MPA_TASK_DB` overrides and standalone CLI/YAML defaults.
- Keep secret handling, API shapes, task limits, and cloud orchestration unchanged.

Non-goals:

- Durable state across function-instance replacement or multiple Studio instances.
- TOS CAS, NAS, database-backed coordination, migration of existing `.adk` files, or deployment.

## Scenarios and requirements

- **FR-1:** Given no task DB override, when Studio lazily creates its task service, then it uses `/tmp/veadk-studio/mpa-creation.sqlite3`.
- **FR-2:** Given `VEADK_MPA_TASK_DB`, when Studio creates its task service, then the explicit path wins.
- **FR-3:** Given the built-in Studio profile, automatic PG bootstrap uses `/tmp/veadk-studio/mpa-pg-bootstrap.sqlite3`.
- **FR-4:** Given a standalone YAML profile without `bootstrap-path`, its existing `.adk/mpa-pg-bootstrap.sqlite3` default remains unchanged.
- **FR-5:** No credential or OpenViking API key is added to either SQLite store.

## Design and contract impact

The HTTP route owns the Studio task-store default and changes only that default. The code-owned Studio profile owns its PG bootstrap path and changes only that profile value. `CreationTasks` and `BootstrapStore` retain their SQLite implementation, schemas, locking, and file mode.

`/tmp` is writable in the target VeFaaS runtime but ephemeral and instance-local. Restart or replacement may lose task history and bootstrap identity. Therefore this fix is suitable only as an explicitly accepted temporary single-instance recovery. If a task is lost during an uncertain cloud create, operators must inspect cloud resources before retrying. A durable shared implementation remains follow-up work.

Security and permissions are unchanged: parent directories use mode `0700`, database files use `0600`, and secrets are not persisted. Compatibility is preserved for HTTP payloads and standalone CLI/YAML callers. No frontend contract changes.

Alternatives rejected for this temporary fix:

- TOS CAS: durable and shared, but requires task leases, restart reconciliation, and bootstrap concurrency semantics.
- NAS: durable with minimal code change, but requires deployment storage configuration.
- Removing state: unsafe because idempotency and uncertain-result recovery require it.

## Implementation tasks

- **T-1 (FR-1, FR-2):** Add route tests and change the Studio task DB default.
- **T-2 (FR-3, FR-4):** Add profile tests and change the built-in bootstrap path.
- **T-3 (FR-5):** Run existing route/task/config security regression tests.
- **T-4:** Remove temporary runtime instrumentation after post-fix evidence is collected.

Affected files: `frontend/server/mpa_creation.py`, `veadk/integrations/mpa/managed/studio_profile.py`, `tests/integrations/mpa_managed/test_routes.py`, `tests/integrations/mpa_managed/test_config.py`, and the bilingual component spec.

## Verification and acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1`, `FR-2` | `T-1` | `AC-1`: default and override resolve to the expected task paths | `uv run --extra dev pytest tests/integrations/mpa_managed/test_routes.py` | `pass`, 2026-09-23 |
| `FR-3`, `FR-4` | `T-2` | `AC-2`: built-in and YAML profile paths remain correctly separated | `uv run --extra dev pytest tests/integrations/mpa_managed/test_config.py` | `pass`, 2026-09-23 |
| `FR-5` | `T-3` | `AC-3`: existing task and route redaction tests pass | `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` | `pass`, 396 tests, 2026-09-23 |
| `FR-1`, `FR-3` | `T-4` | `AC-4`: read-only code-directory reproduction initializes both stores under `/tmp` | Local read-only-CWD reproduction; cloud smoke requires separate deployment authorization | local `pass`; cloud `not_run`, 2026-09-23 |

Required changed-file Ruff and Pyright checks follow `frontend/SPEC.md`. Frontend tests/build are not applicable because no UI or HTTP schema changes.

## Risks and recovery

- Instance restart loses `/tmp` state; cloud resources may outlive their local intent record.
- Multiple function instances do not share locks or concurrency counts. The current deployment must remain single-instance while this workaround is active.
- Rollback restores `.adk` defaults but also restores the read-only-directory failure in cloud Studio.

## Review and delivery record

Design review on 2026-09-23 found no API, secret-handling, or standalone CLI compatibility change. The known durability and multi-instance limitations are explicit and accepted by the user as a temporary fix. English/Chinese requirement IDs, paths, limits, tasks, and acceptance criteria were checked for equivalence.

Implementation verification on 2026-09-23 passed 396 MPA/CLI tests, changed-file Ruff, changed-file Pyright, `git diff --check`, and a read-only-CWD initialization of both `/tmp` stores. Cloud deployment and live creation remain `not_run` because deployment requires separate authorization.
