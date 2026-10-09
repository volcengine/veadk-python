# MPA Studio Turn Control and Resource Workspace

- Change ID: `mpa-studio-control-plane`
- Status: `approved`
- Created / revised: 2026-09-13
- Chinese: [design.zh.md](2026-09-13-mpa-studio-control-plane-design.zh.md)
- Components: [Studio Runtime Diagnostics](../../../specs/studio-runtime-diagnostics/README.md), [Studio MPA Control Plane](../../../specs/studio-mpa-control-plane/README.md)

## Background and evidence

Live verification found that Agent and model selectors overlap, the deployed model allowlist is incomplete, Token categories are not separately visible, environment failures are too generic, the single-Agent topology omits Sandbox and Session resources, Skill Space and Studio tools are hard to discover, and Studio lacks the whole-Turn lifecycle controls already available in mpa-codex-worker. mpa-agent already validates request-local model overrides and has an A2A control store; VeADK already owns an account model catalog, Skill Space routes, Session environment mounts, Studio tool selection, and structured usage fields. The change composes and extends those contracts rather than building parallel systems.

## Goals

- `FR-1`: Query current-account Ark models server-side, filter compatible conversational models, cache successful results, and expose no cloud credential.
- `FR-2`: Freeze model, Skills, tools, and environments into an immutable Turn snapshot on send. Model choice applies to the main Agent and delegated worker and cannot change while non-terminal.
- `FR-3`: Give Agent target, Turn model, usage, lifecycle controls, and send distinct responsive layout slots with no overlap.
- `FR-4`: Display per-Turn and cumulative input, output, reasoning, cache-hit, and total Tokens without replay inflation.
- `FR-5`: Make mpa-agent the sole lifecycle authority for main-model, tools, Sandbox delegation, and worker execution.
- `FR-6`: Provide durable idempotent pause and resume with cooperative safe-point pausing and refresh recovery. Studio exposes no cancel or interrupt action in this release.
- `FR-7`: Persist Session-level Skill Space Skill, Studio tool, and environment mounts; changes apply next Turn and never mutate defaults.
- `FR-8`: Return and render a real Agent-Sandbox-worker-resource topology with actionable node details and no invented active nodes.
- `FR-9`: Explain Studio tool purpose, scenarios, parameters, permissions, examples, source/revision, and Session mounting state.
- `FR-10`: Distinguish environment failures. Authorized administrators/developers may copy a secret without rendering it; ordinary users see configured state only.
- `FR-11`: Advertise capabilities and degrade honestly for old Runtimes.
- `FR-12`: Render each tool call with a human-readable action and its most useful safe subject instead of collapsing different tools into a generic completed label.
- `FR-13`: Preserve complete copyable sanitized tool input/result data while bounding initial rendering; truncation must be explicit and must not silently make the only available data incomplete.
- `FR-14`: Keep model reasoning summaries distinct from Agent working thoughts and suppress only proven transport replays across A2A status and artifact channels.
- `FR-15`: Make the Turn model selector searchable by model ID and display text while retaining keyboard access and the non-terminal Turn lock.

## Non-goals

- Mutating Runtime/Agent defaults or account model activation from chat.
- Hard-coding a seasonal model list or trusting browser model IDs.
- Preempting an in-flight provider request; pause completes at the next safe point.
- Resuming cancelled/completed/failed Turns.
- Letting Studio coordinate mpa-agent and worker independently.
- Rendering or persisting secrets, or retrieving them as an ordinary user.
- Inventing Sandbox, Skill, knowledge, tool, or sub-Agent relationships.

## Scenarios

1. Selecting a compatible model while idle freezes it on send and locks the selector until terminal.
2. Pause enters `pausing`, finishes only the current non-preemptible operation, starts no next step, and becomes `paused` only when main executor and workers confirm safe points.
3. Refresh restores the authoritative paused/running state and allowed actions from mpa-agent. Pause and resume share the Composer’s single primary action with send; no duplicate lifecycle toolbar is rendered.
4. A paused Turn remains eligible for same-Turn resume for five minutes. A later resume click, or a resume click after the owner is no longer recoverable, terminalizes the old Turn as interrupted and starts a new Turn in the same Session with an incremental continuation instruction. No timeout-triggered work starts without the user’s click.
5. Internal terminalization may stop an unrecoverable old Turn, but Studio exposes no interrupt or cancel action in this release.
5. Skill/tool/environment mounts persist in the Session and enter the next Turn snapshot without changing the active Turn.
6. Environment errors identify authorization, Runtime, version, Manifest, or secret-access boundaries.
7. Authorized secret copy uses a no-store audited action and writes directly to clipboard without rendering; unauthorized copy returns 403.
8. Topology shows observed Agent, Sandbox, worker, Skill Space, Studio tool, MCP, environment, knowledge, and sub-Agent relationships only.
9. Tool activity states the concrete action and safe subject; complete sanitized data remains available through an explicit detail action.
10. A reasoning summary replayed by both A2A status and artifact transport is shown once, while a distinct Agent thought remains separately labelled.
11. The model picker accepts typed filtering and cannot change the frozen model of a non-terminal Turn.

## Architecture

### Four-layer configuration

1. Agent defaults are read-only.
2. Session configuration stores Skill, Studio tool, and environment mounts.
3. Turn snapshot atomically freezes model/resource identifiers and versions.
4. Turn lifecycle is durably owned by mpa-agent.

Session edits during a non-terminal Turn are explicitly labelled as next-Turn drafts. Deleted or unauthorized resources remain visibly invalid until removed/replaced.

### Model catalog and Turn freeze

The Studio server queries Ark with server credentials, filters enabled resources to mpa-agent-compatible conversation models, and caches the last success with freshness metadata. Failure serves labelled stale cache or an explicit unavailable state. mpa-agent validates the selected ID against its effective allowlist before side effects and persists it in the Turn snapshot. Main model and worker delegation read only the snapshot.

### Whole-Turn lifecycle

```text
queued -> running -> completed | failed
             | -> pausing -> paused -> resuming -> running
             |                    \-> interrupted -> new incremental Turn
```

mpa-agent persists control generation, idempotency key, desired/observed state, participant states, safe-point data, pause time, resume deadline, and failure detail. Studio calls only mpa-agent. mpa-agent forwards worker commands and aggregates acknowledgements. A running atomic operation may finish after pause intent, but no next model/tool/delegation starts. Resume within five minutes continues from a proven durable safe point without replaying completed tools or the accepted user message. After the deadline or when same-Turn recovery is unavailable, the user’s resume click interrupts the old execution and creates a new incremental Turn in the same Session.

### Session resources and topology

Session mounts store immutable Skill version plus Space ID, Studio tool ID/revision, and environment/workspace bindings. The typed topology uses node kinds `agent`, `sandbox`, `worker-session`, `skill-space`, `skill`, `studio-tool`, `mcp`, `environment`, `knowledge`, and `sub-agent`, with relationships such as `delegates-to`, `runs-on`, `mounts`, `provides`, and `calls`. Optional unmounted categories are graph-external affordances, not fake nodes. Node details expose source, configured/observed status, lifecycle, capabilities, recent calls, and safe navigation identifiers.

### Composer and usage

The Composer follows one conventional input surface with one footer row: attachment, Agent target, Turn model, compact status/usage, and one primary button. The primary button means send when idle/terminal, pause while running, progress while pausing/resuming, and resume while paused. Agent and model selectors share the same borderless 36 px trigger style. No second lifecycle toolbar, cancel action, or interrupt action is rendered. Long IDs truncate accessibly and the send/control slot never overlaps the model selector. Usage shows five categories for current Turn and Session cumulative totals; missing values show `—`, and cumulative snapshots contribute positive deltas only.

### Environment and secrets

Normal environment responses include name, source, sensitivity, configured state, and allowed non-secret values, never secret values. Secret copy is a separate administrator/developer-only POST with `Cache-Control: no-store`. It audits actor, Runtime, variable, time, and result without value. Frontend writes the response directly to `navigator.clipboard.writeText` and does not render, persist, cache, or emit it in telemetry/errors.

### Studio tool discoverability

Tool detail includes purpose, scenarios, input schema, permissions, examples, source/revision, and default/Session mounting state. Add/remove applies next Turn. No tool credential enters browser data.

### Conversation activity projection and presentation

The A2A projection layer preserves the semantic kind of model reasoning summary versus Agent working thought. It tracks cumulative text independently per task, invocation, semantic kind, and transport source. Cross-source content is suppressed only when it is an exact replay or a proven cumulative-prefix replay of the same logical stream; arbitrary repeated prose is retained. Stable source event IDs remain the primary deduplication key.

The frontend derives a safe action title and subject from tool-specific fields, including nested Runtime payloads. Known tools such as `create_goal`, `exec_command`, search, read, and file-change operations receive action-specific labels. Unknown tools display their concrete name. The collapsed row stays concise; expanded details expose sanitized input and result. Large values use bounded DOM rendering plus an explicit complete-copy/download path, and never replace the only accessible representation with an unannounced truncated value. Secret masking and unsafe-control removal remain mandatory before preview or copy.

The Composer reuses the existing accessible searchable compact selector rather than a native `select`. Filtering covers model ID and display text, preserves arrow/Enter/Escape behavior, reports no matches, and is disabled while the Turn model is immutable.

## Interface contracts

- Account model catalog returns compatible models, freshness/stale metadata, and classified failure.
- Agent Card advertises versioned `turnModelSelection`, `turnLifecycleControl`, `sessionResourceMounts`, and `resourceTopology`.
- Turn creation carries validated model ID and Session resource revision; mpa-agent persists resolved snapshot.
- Turn control exposes pause/resume to Studio with idempotency and expected generation. Internal terminalization remains available to mpa-agent but is not a Studio action.
- Turn status returns state, desired state, generation, safe-point/participant summaries, failure, pause time, resume deadline/disposition, and allowed actions. A 409 response carries the same authoritative state shape and Studio consumes it instead of surfacing raw transport text.
- Session resource APIs return defaults, deltas, invalid resources, revision, and next-Turn semantics.
- Topology returns typed nodes/edges for one Session/Turn.
- Secret copy is a no-store role-protected action and never part of list responses.

## Compatibility and failures

Old agents without capabilities retain one default model, hide pause/resume, and show verified topology only. Stream disconnect is not cancellation; Studio reconnects persisted state/events. Concurrent controls resolve by generation/idempotency and return authoritative conflicts. Studio absorbs structured 409 state. Exact process-replacement resume is replaced by a user-triggered incremental Turn after five minutes or when the owner cannot resume. Native ArkClaw and non-MPA Studio paths remain unchanged.

## Tasks

| ID | Work | Owner | Dependency |
| --- | --- | --- | --- |
| `T-1` | Durable Turn state, safe points, idempotent commands, participant aggregation | mpa-agent | none |
| `T-2` | Wrap worker pause/resume and expired-resume fallback behind mpa-agent | mpa-agent | `T-1` |
| `T-3` | Compose Ark catalog, compatibility, and Turn validation | Studio BFF + mpa-agent | none |
| `T-4` | Persist Session mounts and atomically create Turn snapshots | Studio BFF + mpa-agent | `T-1` |
| `T-5` | Skill Space browse/mount and Studio tool details/examples | Studio | `T-4` |
| `T-6` | Typed topology endpoint, graph, and detail drawer | mpa-agent + Studio | `T-4` |
| `T-7` | Composer layout and Turn model/lifecycle controls | Studio frontend | `T-1`, `T-3` |
| `T-8` | Usage category UI and environment/secret-copy flows | Studio | none |
| `T-9` | Browser, Runtime, race, refresh, security, and legacy E2E | both repos | `T-1`–`T-8` |
| `T-10` | Conversation event semantics, replay-safe thought/reasoning projection, human-readable tool activity, complete sanitized details, and searchable model selection | Studio BFF + Studio frontend | `T-3` |

## Acceptance

| Requirement | Acceptance evidence | Initial |
| --- | --- | --- |
| `FR-1`, `FR-2` | Catalog contracts and live two-model Turn proving main/worker consistency and invalid-ID no-side-effect rejection | `not_run` |
| `FR-3` | Browser screenshots/tests at normal/narrow widths with long model IDs | `not_run` |
| `FR-4` | Token tests and replay/refresh live evidence for all five categories | `not_run` |
| `FR-5`, `FR-6` | Integration/live `running -> pausing -> paused -> resuming -> running`, five-minute fallback, race, and idempotency | `not_run` |
| `FR-7`, `FR-9` | Real Skill Space/tool Session mounts survive refresh and apply next Turn | `not_run` |
| `FR-8` | Contract and browser proof that only real relationships render | `not_run` |
| `FR-10` | Precise failures, no rendered secret, authorized copy, ordinary-user 403, value-free audit | `not_run` |
| `FR-11` | Legacy Agent Card fixtures and browser degradation | `not_run` |
| `FR-12`, `FR-13` | Tool-specific/nested/unknown fixtures, large sanitized result copy/download, and browser inspection | `not_run` |
| `FR-14` | Status/artifact replay fixtures plus live/history/reconnect reasoning and thought rendering | `not_run` |
| `FR-15` | Keyboard and typed filtering, no-match behavior, and non-terminal disabled selection | `not_run` |

Required gates follow `AGENTS.md` and `frontend/SPEC.md`: targeted tests, broad regression for shared contracts, frontend test/build, changed-file Ruff/Pyright, real browser normal/error/cancel/retry/narrow cases, pre-commit, two review rounds, and isolated Runtime E2E.

## Risks and approval

Safe-point implementation must first prove which Runner boundaries resume without duplicate side effects. Account resources may be enabled but incompatible with the Runtime credential/base URL, so intersection fails closed. Large topologies require bounds, detail loading, pan/zoom, and an accessible list. Browser clipboard policy failure must never fall back to rendering.

The user approved phased delivery, live Ark catalog, immutable Turn model, whole-flow cooperative pause, mpa-agent lifecycle ownership, non-overlapping Composer layout, real resource topology, next-Turn Session mounts, and administrator/developer secret copy without rendering. The written bilingual design and component contract, including the single dynamic primary action and user-triggered five-minute fallback, were approved on 2026-09-13.

## Design review record

The repository review found and resolved these design blockers:

- **Worker pause contract difference:** mpa-codex-worker implements pause by interrupting the active Codex Turn and resume through `thread/resume`. mpa-agent must wrap that behavior as a whole-flow safe point and, after five minutes or when the owner is unrecoverable, create an incremental Turn only after the user clicks resume; Studio never coordinates the worker directly.
- **mpa-agent state gap:** its current A2A store owns running/cancel-requested/final states only. `T-1` is an explicit schema/state-machine migration with legacy-row compatibility, not a UI-only extension.
- **Safe-point ambiguity:** the design forbids claiming process-restart resume until a concrete Runner boundary has an atomic checkpoint and duplicate-side-effect proof. The first vertical slice must spike and test that boundary before implementing full pause/resume.
- **Model-catalog duplication risk:** Studio already has `frontend/server/model_catalog`; `T-3` extends its response with freshness/stale/compatibility metadata and intersects it with Runtime capabilities rather than creating another catalog service.
- **Secret endpoint reuse risk:** existing raw API-key routes demonstrate no-store transport but do not satisfy Runtime-variable RBAC/audit. Secret copy gets its own role-protected audited contract and may not reuse a weaker generic resolver.
- **Scope sequencing:** delivery is split into two approved phases. Phase 1 is model catalog/freeze, lifecycle controller, usage, environment errors/secret copy, and Composer layout. Phase 2 is Session Skill/tool mounts, tool guidance, and resource topology. Phase 2 cannot weaken Phase 1 lifecycle/snapshot contracts.

No P0/P1 product-design blocker remains. Implementation is still gated on the user's review of this written pair and an implementation plan that starts with the safe-point spike.
