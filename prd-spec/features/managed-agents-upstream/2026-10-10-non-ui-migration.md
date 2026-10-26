# Non-UI Managed Agents upstream migration

[中文版](2026-10-10-non-ui-migration.zh.md)

Change ID: `managed-agents-upstream`. Created/revised: 2026-10-10. Status: implemented (local migration; unpublished).

## Background and evidence

The source repository's `main` at `89a90e02` and the official VeADK `main` at
`171d8d86` diverge from `80e968d7`. Comparing complete trees would overwrite
official Codex, Studio, MPA provisioning, and compatibility improvements.
The source's new runtime implementation lives in `examples/16_self_host_sandbox`;
its library modules import bare example modules and its images require an
adjacent Managed Agents Anthropic SDK checkout. The target already owns
`veadk/runtime/provider.py` and `veadk/integrations/mpa/managed` provisioning.

## Goals and non-goals

Deliver all source-owned non-UI changes on the current official base, with a
packaged runtime, maintained example entry points, isolated tests, and reproducible
image inputs. Source is read-only. UI, Studio-only backend routes/repositories,
built web assets, unrelated upstream code, personal deployment records, and live
cloud mutation are excluded. This does not authorize commit, push, or PR creation.

## Scenarios and requirements

- `FR-1`: A caller imports the packaged loop/client without an example directory,
  credentials, network activity, or a global remote-backed demo Agent.
- `FR-2`: A worker executes native tools, pinned Session Skills and MCP resources,
  retaining Work polling, lease/heartbeat, cancellation, cross-worker replay,
  credential rotation, event ordering, and cleanup behavior from the source.
- `FR-3`: Ark continuation retains tool declarations, uses server retention by
  default, preserves explicit expiration, and emits opt-in safe metadata traces.
- `FR-4`: Runtime Identity supports explicit pool lookup and Session-scoped model
  and MCP credentials; Skills operations preserve their bounded account scope.
- `FR-5`: Feishu streaming controls are opt-in and preserve the official branch's
  graceful shutdown and application-loop lifecycle.
- `FR-6`: Non-UI build, example, and test scripts point to installed library code.
  Images use public package indexes by default, keep locked hashes, never require
  a hardcoded registry or local SDK checkout, and fail early when SDK capability
  requirements are unmet. Image publishing and cloud E2E remain separate actions.

## Design and contract impact

Dependency direction is runtime -> MPA Session integration -> Anthropic/AgentKit
SDK. `veadk/runtime/managed_agents` owns worker, loop, native tools, event tracing,
Identity adapter and health entry point. `veadk/integrations/mpa/session_client.py`
and `session_resources.py` own the protocol client and Session resource snapshots.
Existing MPA provisioning is reused without confusing its `managed/worker.py`
(sandbox provisioning) with model-work execution. Existing RuntimeProvider stays
unchanged. Compatibility wrappers in the example import packaged implementations;
example launchers may load their local environment, library imports may not.
Deployment-specific IDs and defaults are replaced by required configuration.
`veadk/models`, `veadk/skills`, `veadk/integrations/ve_identity`, and
`veadk/extensions/feishu_channel.py` retain their established ownership.

State/event wire formats remain those of the source; no backend schema or cloud
resource migration is introduced. Cancellation must unwind runners/tools and
temporary Skill materializations; terminal replay must not execute completed
inputs again. Credentials remain runtime inputs, are never persisted in docs,
images, traces, or Git, and error reporting must remain redacted. Supported
Python 3.10-3.13 imports must use compatible datetime and asyncio primitives.

Component contracts: [runtime](../../../specs/managed-agent-runtime/README.md),
[resources](../../../specs/managed-agent-resources/README.md),
[Feishu](../../../specs/feishu-channel/README.md).

## Tasks and ownership

| Task | Requirements | Files / owner |
| --- | --- | --- |
| `T-1` | `FR-1`, `FR-2` | Runtime/Session packages, runtime tests, example Python wrappers: runtime agent |
| `T-2` | `FR-3`, `FR-4` | Ark, IdentityClient, Skills client, model/resource tests: model/skills agent |
| `T-3` | `FR-5` | Feishu extension, channel tests and paired user docs: channel agent |
| `T-4` | `FR-6` | Docker, dependency metadata/lock, non-UI scripts, example docs: root agent |
| `T-5` | all | Integration, regression, packaging, secret scan, documentation reconciliation: root agent |

Writers have disjoint file ownership. No shared Git index operations or commits
occur while agents work. Root reconciles package metadata and runs final gates.

## Verification and acceptance

| Requirements | Acceptance | Verification | Status |
| --- | --- | --- | --- |
| `FR-1`, `FR-2` | `AC-1`: installable library with equivalent lifecycle | targeted runtime/Session and actual SDK transport/native-tool tests | pass; included in final 387 focused tests |
| `FR-3`, `FR-4` | `AC-2`: existing official behavior plus source resource/model delta | model/Identity/Skills tests | pass; 109 initially, included in final focused run |
| `FR-5` | `AC-3`: streaming and shutdown tests pass | channel tests | pass; 18, included in final focused run |
| all | `AC-4`: integrated regression and repository gates | parallel regression plus all-file/changed-file pre-commit | pass for scoped regression; unfiltered gate has 7 reproduced official UI failures (see below) |
| `FR-6` | `AC-5`: wheel/import/CLI/build-input validation | wheel/import/CLI, shell syntax, image build and container checks | pass; local image only |

Tests use synthetic services and temporary state. Live cloud/provider E2E and
image publication: not_run, outside the authorized local migration. UI checks:
not_applicable because UI and Studio backend changes are excluded.

## Risks and recovery

The source's EnvironmentWorkDispatcher currently requires a Managed Agents SDK
capability not present in a generic Anthropic installation. Check available SDK
capabilities and implement a supported explicit integration, rather than silently
claiming worker readiness. The final record must distinguish simulated runtime
tests, installed package imports, image build, and real cloud E2E. Original source
and official base remain intact; abandoning the new branch restores the base.

## Review and delivery record

The user approved the architecture and non-UI scope with “ok, just do it, do it
best” and explicitly authorized multiple subagents. Direct design review found
and resolved: use the official base; preserve existing MPA and runtime interfaces;
exclude UI backend wiring; keep SDK requirements explicit; avoid import-time
credential access; preserve Python 3.10 compatibility; validate async cleanup.
No `review-spec` skill is installed, so the repository's equivalent direct review
is used. Component owners review their bilingual contracts before production
edits. All `T-1` through `T-5` tasks are complete within the non-UI scope.

### Source-to-target reconciliation

| Source | Delivered location / decision |
| --- | --- |
| `main.py`, `managed_agent_loop.py`, `event_debug.py`, `runtime_identity.py` | `veadk/runtime/managed_agents/{worker,loop,events,identity}.py` |
| demo agent/session lifecycle | packaged `sandbox.py`; example discovery factory remains a thin adapter |
| `sandbox_client.py`, `managed_session_resources.py` | `veadk/integrations/mpa/{session_client,session_resources}.py` |
| missing private SDK dispatcher | packaged dispatcher using the published SDK, with real protocol tests |
| Ark/Identity/Skills/Feishu | existing owning SDK modules plus standalone `veadk/skills/ma_infra.py` |
| Worker/Runtime launch and claimed Tool startup | `docker/managed-agents/`, installed module entry points, `/opt/gem/run.sh`, thin example launchers |
| conversation/distributed/Kubernetes/soak/fault checks | portable example scripts and packaged runtime/Session/completion-gate tests |
| personal rollout/build-candidate scripts, RDS and external ma-server/task-server deployments | replaced by public Worker build and generic Kubernetes template; no deployment-specific state copied |
| UI, Studio-only Skills repository/routes, gateway UI image and built assets | excluded as approved |
| historical deployment proof and one-off analysis documents | not copied as current evidence; this design records new local verification |

### Verification record (2026-10-10)

The tested scope is the uncommitted feature diff on official `171d8d86`, including
new package files. Locked package versions/hashes and unrelated platform markers
are unchanged; only the sandbox Anthropic minimum changes from `>=0.40.0` to the
source's required `>=1.3.0`.

- **pass:** Python 3.12 final focused run: 387 tests, including actual SDK HTTP,
  native file/bash, MCP, canonical cross-worker replay, cleanup and supervision.
- **pass:** Python 3.10.20 isolated frozen environment: 356 focused tests plus
  actual SDK transient publishing. The discovered generic-alias SDK cast issue is
  fixed using `typing.Dict`; no unsupported production import is hidden by mocks.
- **pass:** `MODEL_AGENT_API_KEY=offline-regression-test-key .venv/bin/python -m
  pytest -n 4 -m "not codex_smoke and not piagent_smoke" -q --tb=short`, with the
  seven explicit baseline deselections below: 6963 passed, 42 skipped, 4 xfailed,
  6 subtests passed. Four workers were selected for this final large regression;
  the initial default two-worker run exposed test setup and baseline issues.
- **fail, official baseline:** the unfiltered regression's seven
  `tests/frontend/test_migration_delivery_recovery.py` cases also fail on an
  untouched official worktree with identical dependencies. They are:
  `test_mirror_delivery_writes_the_documents_the_cli_would_have_written`,
  `test_mirror_delivery_keeps_the_sequence_the_cli_already_started`,
  `test_mirror_delivery_refuses_a_delivery_the_cli_already_settled`,
  `test_verification_mirrors_the_cli_finding_projection`,
  `test_an_unparseable_findings_file_reports_no_findings_at_all`,
  `test_a_startup_fallback_degrades_the_delivery`, and
  `test_a_rebuild_that_lands_settles_the_task_on_the_cli_delivery_contract`.
  Each was deselected with `--deselect <file>::<name>` for the scoped regression;
  no marker, production UI code or assertion was changed to suppress them.
- The initial unfiltered run also exposed existing examples/Harness tests relying
  on an unrelated example test's import-time dummy model key. New tests no longer
  mutate global credentials during collection. The final command provides an
  explicit offline fixture key instead. Test package names now avoid a
  `test_dispatcher` collision with Studio scheduler tests.
- **pass:** all-file and changed-file pre-commit (Ruff check/format, gitleaks,
  YAML secret scan); `git diff --check`; bilingual Markdown links and no-UI scope.
- **pass:** `uv build --wheel`; extracted installed wheel imports and CLI help
  from a temporary directory with a sanitized environment and no example path.
- **pass:** `npm --prefix docs run types:check` and `npm --prefix docs run build`.
  Dependency installation uses the repository's frozen pnpm lock; generated
  workspace policy and Corepack's unintended parent configuration change were
  removed from the feature scope.
- **pass:** local Docker image `veadk-managed-agents-worker:upstream-local` built
  from locked sandbox dependencies with public indexes. Local network/proxy
  settings were supplied only to the build. The dedicated Worker excludes
  optional integration/development/Codex extras. No neighboring SDK wheel is used.
- **pass:** container SDK imports/CLI and `/opt/gem/run.sh` checked as UID 10001
  with network disabled and read-only filesystem; installed health server returns
  HTTP 200 on `/ping` in the same isolation. These checks do not exercise a real
  Work gateway, model provider or AgentKit deployment.
- **not_run:** live cloud/model E2E, image publication, Git commit/push and PR
  creation. The image is local, the branch tracks `volcengine/main`, and the
  original source worktree remains clean.

### Review fixes

Independent review resolved import-time credential access, failed-turn completion
and secret-bearing errors, Skill workspace collisions/symlink cleanup, closing all
tool contexts after a cleanup failure, Work lease fencing/Session FIFO/auth refresh,
first-valid-poll readiness, Python 3.10 casts, credential-bearing index arguments,
obsolete database assumptions in distributed tests, and named BuildKit cache
isolation. Claimed Tool execution retains its historical launch path and local
tool default inside the deployment's OS isolation.
