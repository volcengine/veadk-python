# MPA Studio Control Plane Implementation Plan

- Change ID: `mpa-studio-control-plane`
- Status: Phase 1 implemented; Phase 2 partially implemented
- Date: 2026-09-13
- Chinese: [implementation-plan.zh.md](2026-09-13-mpa-studio-control-plane-implementation-plan.zh.md)
- Approved design: [design.md](2026-09-13-mpa-studio-control-plane-design.md)

## Execution strategy

Deliver two phases through vertical slices. Preserve current unrelated changes in both repositories and the independent mpa-agent branch. Each slice starts with failing contract tests, then implementation, targeted verification, and reconciliation. Do not publish a Runtime image until all local gates for that slice pass.

## Phase 1 — Turn correctness and lifecycle

### Slice 0 — Prove resumable safe points

1. Characterize VeADK Runner boundaries around model response completion, tool start/result, and delegated worker start/result.
2. Add an isolated mpa-agent spike test that requests pause during each boundary and records whether resumption can continue without re-running an accepted model/tool side effect.
3. Classify boundaries as atomic/non-resumable or durable/resumable. Persist only the minimal checkpoint needed by proven boundaries.
4. Gate: no production pause claim until a red/green test proves one end-to-end safe point and a negative test proves no next operation begins after pause intent.

Spike result (2026-09-13): `mpa-agent/tests/test_turn_safe_point_spike.py` proves
the `after_tool` ADK boundary in one live Invocation. The committed effect occurs
exactly once, the next model request remains blocked while paused, and in-process
resume continues the same Invocation without replaying the accepted user message
or completed tool. The store-backed gate separately verifies a `before_tool`
checkpoint blocks before an operation starts. This authorizes Slice 1 to use
cooperative callback gates. It does not prove process-replacement resume or
arbitrary in-flight provider/tool preemption; those remain explicitly unsupported
until a durable checkpoint can be validated.

### Slice 1 — Durable whole-Turn controller

1. Extend `app/stores/a2a_task_control.py` with migration-compatible states, generation, desired state, command idempotency, participant state, safe-point/checkpoint metadata, and classified control failure.
2. Add mpa-agent control/status routes adjacent to A2A ownership, not Studio-specific state.
3. Add cooperative checks before every next main-model, tool, and delegation boundary.
4. Map worker session handles to the owning Turn and wrap worker pause/resume/cancel. Add a worker interrupt contract only if existing cancel/continue cannot meet the approved semantics.
5. Make refresh/reconnect load persisted state and events.
6. Tests: store transition tables, old-row migration, duplicate command, stale generation, concurrent pause/cancel, worker failure, refresh, cancel terminality, interrupt/new-Turn continuation.

### Slice 2 — Live model catalog and immutable Turn model

1. Extend `frontend/server/model_catalog` response with observed time, stale state, and classified failure. Reuse its account activation/model join.
2. Add server-side intersection with mpa-agent model capability. Do not send API keys to the Runtime or browser.
3. Replace session-local model semantics with a Turn draft in Studio. Freeze ID on send and persist it in mpa-agent's Turn snapshot before execution.
4. Make primary model and delegated worker resolve the same snapshot. Reject stale/invalid IDs before side effects.
5. Tests: cache/stale/no-cache failure, capability intersection, Turn immutability, main/worker consistency, invalid ID, old Runtime single-model behavior.

### Slice 3 — Composer, controls, and usage

1. Refactor Composer layout into target/header and responsive footer slots. Remove competing positioning.
2. Render lifecycle actions from server-provided allowed actions; disable model and conflicting actions while non-terminal.
3. Expose current Turn and Session cumulative input/output/reasoning/cache/total values. Preserve monotonic-delta aggregation.
4. Browser gates at normal and narrow widths, long Agent/model names, every control state, missing Token categories, keyboard/IME, refresh, retry, and error states.

### Slice 3A — Conversation activity fidelity

1. Add A2A fixtures where the same cumulative reasoning is emitted through working status and artifact updates, plus legitimate repeated text that must remain.
2. Preserve reasoning versus Agent-thought metadata through projection and frontend blocks.
3. Add tool-specific presentation adapters for goal, command, search, read, file-change, MCP, and unknown tools, including nested Runtime payloads.
4. Bound previews while keeping complete sanitized copy/download access and identical redaction on every path.
5. Replace the Composer native model select with the existing searchable compact selector and retain the Turn lock.
6. Tests/browser: streaming/history/reconnect parity, no duplicate reasoning, distinct thought labels, meaningful tool rows, complete safe details, keyboard filtering, no-match, running-disabled, and narrow layout.

### Slice 4 — Environment failures and secret copy

1. Split environment load failures into authorization, Runtime unavailable, version missing, Manifest failure, and unsupported secret access.
2. Add an administrator/developer-only Runtime secret-copy POST with no-store headers and value-free audit.
3. Write clipboard directly and discard the value without rendering/persisting/telemetry.
4. Tests: RBAC matrix, cache headers, audit redaction, missing variable, upstream failure, clipboard rejection, DOM/storage/log absence.

### Phase 1 release gate

- Targeted tests in both repositories.
- mpa-agent broad affected suite.
- VeADK Python targeted plus applicable parallel regression.
- frontend test/build and real browser matrix.
- changed-file Ruff/Pyright and pre-commit.
- two review rounds.
- isolated Runtime E2E: catalog, model freeze, pause/resume safe point, cancel, interrupt, refresh recovery, five Token categories, environment errors, authorized/unauthorized secret copy.

## Phase 2 — Session resources and operational topology

### Slice 5 — Session resource revision and Turn snapshots

1. Define one Session resource document/revision for Skill versions, Studio tool revisions, and environment/workspace bindings.
2. Validate updates server-side and atomically resolve one immutable Turn resource snapshot.
3. Preserve invalid/deleted/revoked entries visibly and prevent execution.
4. Tests: revision conflicts, edits during active Turn apply next Turn, refresh persistence, removed versions, defaults unchanged.

### Slice 6 — Skill Space and Studio tool workspace

1. Reuse existing Skill Space APIs to list Spaces, Skills, immutable versions, and details in conversation context.
2. Add Session mount/unmount actions with next-Turn labels.
3. Add Studio tool detail containing purpose, scenarios, schema, permissions, examples, source, revision, and mount state.
4. Tests/browser: loading/empty/error/retry, version selection, permissions, invalid resource, refresh persistence, next-Turn execution.

### Slice 7 — Typed resource topology

1. Add mpa-agent typed topology data derived from Agent defaults, Turn/Session snapshots, actual worker handles, MCP, environment, knowledge, and sub-Agent configuration.
2. Render an interactive bounded graph with pan/zoom/fit, detail drawer, and accessible list representation.
3. Keep unmounted optional resources outside the active graph as add affordances.
4. Tests/browser: single Agent plus Sandbox, worker state transitions, Skills/tools/MCP/environment, absent knowledge/sub-Agent, large graph bounds, narrow window, keyboard access.

### Phase 2 release gate

Repeat repository gates and live Runtime E2E with a real Skill Space, Studio tools, environment, worker delegation, refresh, invalid-resource case, and topology state changes.

## File ownership expectations

- mpa-agent: `app/stores/a2a_task_control.py`, A2A executor/app/routes, invocation context, model/delegation integration, Session resource/topology services, tests.
- veadk-python backend: `frontend/server/model_catalog`, Session resource and environment/secret routes, Runtime A2A proxy/types, tests.
- veadk-python frontend: `App.tsx`, `Composer.tsx`, token usage, topology, Skill/tool/resource pickers, i18n/styles/tests, regenerated `veadk/webui` assets.
- mpa-codex-worker: only if Slice 1 proves a missing worker interrupt/checkpoint contract; follow its own PRD/spec and gates before edits.

## Stop conditions

Stop and return to design review if the safe-point spike cannot prove side-effect-free resume, Ark model compatibility cannot be resolved server-side, or secret-copy auditing cannot be implemented without exposing the value to logs/state. Do not weaken acceptance criteria to proceed.

## Verification record — 2026-09-13

- `pass` — frontend suite: `npm --prefix frontend test` (`1096` passed).
- `pass` — production assets: `npm --prefix frontend run build`; the final dialog-layout fix produced and served `assets/app/index-CozNp3D8.js`.
- `pass` — VeADK Runtime proxy, A2A projection, and RBAC targets: `235` passed.
- `pass` — mpa-agent executor, delegation, runtime plugin, lifecycle, safe-point, and task-store targets: `173` passed.
- `pass` — Runtime `r-yeuujrrcowb21078p9jh` version `52` reached `Ready` on image `agentkit/mpa_agent_studio:resource-topology-v52b-20260913` (digest `sha256:205a82a5a32094c6da93e1a6b1ae4f7b70a883021b06489b844a28d1214eaf79`). Its Agent Card advertises 23 compatible models; the Studio proxy intersects them with account activation and currently exposes 14 selectable models, plus whole-Turn lifecycle capability and the configured `Agent -> Sandbox` topology. A live Turn using activated alternate model `glm-5-2-260617` completed successfully and retained that model in the Turn UI.
- `pass` — system-Chrome CDP checks at 1440 px and 375 px found no horizontal overflow. The model popover is independent from the Agent picker, exposes `搜索模型`, and filtering returns only matching selectable models.
- `pass` — a live Turn showed `pause`, `interrupt`, and `cancel`; pause moved to `pausing` at a cooperative safe point, and terminal completion removed all lifecycle buttons. The completed Turn showed separated model reasoning and final answer plus input/output usage.
- `pass` — the Session Skill action opened a real Skill Space picker and loaded account spaces and versioned Skills.
- `fixed during review` — the Skill Space dialog header used the three-column tool-dialog grid without an icon, squeezing its title into one-word lines. It now uses the existing iconless two-column variant, with a regression assertion.
- `fixed during review` — Runtime capability alone exposed three unactivated models and a live selection failed with Ark `NotFoundError`. The Studio proxy now intersects Runtime capability with the account model catalog while retaining the Runtime default as a compatibility fallback.
- `fixed after visual acceptance` — the new-chat model trigger now shares the Agent trigger's 36 px borderless treatment and its container reserves a non-overlapping slot before the 36 px send action. Runtime list items now include `agentCategory`; stable `veadk:agent-type=mpa` metadata is preferred and existing `/mpa_agent*:` image repositories provide compatibility classification into a dedicated `MPA Agent` picker category.
- `blocked` — Pyright is not installed in the repository environment (`Failed to spawn: pyright`).
- `blocked by optional dependencies` — the broader VeADK regression previously completed with `4030 passed, 12 skipped, 2 xfailed`, plus seven failures and two collection errors caused by missing optional `llama_index`/`anthropic` dependencies; affected targeted suites pass.
- `known generated-artifact exception` — `git diff --check` passes when excluding generated `veadk/webui/website-integration.js`; that third-party bundle contains trailing whitespace.

## Explicit remaining Phase 2 scope

Session Skill/Studio-tool/environment selections currently persist in browser local storage and are submitted with the next Turn. A server-owned Session resource document with revision conflicts, invalid-resource retention, and atomic resource resolution is not implemented. Dynamic worker lifecycle nodes are also not yet projected into the topology. These items must not be reported as complete.
