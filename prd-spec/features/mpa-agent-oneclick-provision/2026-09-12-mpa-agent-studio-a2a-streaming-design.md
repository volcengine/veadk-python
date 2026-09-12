# mpa-agent Studio A2A Streaming Design

## Metadata

- **Change ID:** `mpa-agent-studio-a2a-streaming`
- **Created / revised:** 2026-09-12 / 2026-09-12
- **Lifecycle status:** `approved`
- **Chinese version:** [2026-09-12-mpa-agent-studio-a2a-streaming-design.zh.md](2026-09-12-mpa-agent-studio-a2a-streaming-design.zh.md)
- **Previous design:** [2026-09-11-mpa-agent-provision-orchestration-alignment-design.md](2026-09-11-mpa-agent-provision-orchestration-alignment-design.md)
- **Implementation branches:** mpa-agent `fix/a2a-studio-streaming`; veadk-python `feat/mpa-agent-oneclick-provision`

## 1. Overview

### 1.1 Problem and evidence

VeADK Studio can connect to an mpa-agent Runtime through its A2A compatibility bridge, but `/run_sse` is not a streaming path today:

1. The Studio BFF always calls A2A `message/send` with `blocking=true`.
2. The BFF buffers the complete JSON-RPC response through `_runtime_proxy_buffer()` before emitting one Studio SSE event.
3. The mpa-agent card currently returns `capabilities={}` and does not advertise streaming.
4. Sandbox `CodexNormalizedEvent` objects are sent through `codex_event_handler` to PostgreSQL and the Session Stream, but they do not automatically enter the A2A `EventQueue`.

Live verification proved that the Runtime, sandbox, and final result work. Runtime `r-yeuujrrcowb21078p9jh` v25 completes the command in about 13–16 seconds, returns a completed A2A task, and places the final result in an ADK function-response data part. The missing component is real-time protocol bridging during execution.

### 1.2 Goals

- **G1:** Studio displays A2A task status, sandbox startup, tool calls, command output, text deltas, and final output while execution is in progress.
- **G2:** A user request executes at most once; streaming failure must never trigger an unsafe automatic resubmission.
- **G3:** Preserve ordinary ADK Runtime, legacy non-streaming A2A Runtime, Web, Feishu, scheduled-task, and bot-group behavior.
- **G4:** Add no database schema, direct Studio-to-mpa-agent database access, or process-global event bus.
- **G5:** A task continues after browser disconnect. Initial delivery does not support live stream resumption; refresh can retrieve the final persisted result.

### 1.3 Non-goals

- Live resumption from the last event ID is deferred.
- The mpa-codex-worker protocol is unchanged.
- The A2A SDK is not replaced.
- Agent, Tool, Runtime provisioning and database tables are unchanged.
- Feishu and scheduled-task presentation and terminal semantics are unchanged.

## 2. User scenarios

### Scenario 1: Observe sandbox execution in real time

**Given** the mpa-agent card advertises `streaming=true`.
**When** a Studio user asks the sandbox to run a command with staged output.
**Then** Studio displays working, tool start, output deltas, tool completion, and final text before the task ends.

### Scenario 2: Legacy Runtime compatibility

**Given** an A2A Runtime does not advertise streaming.
**When** a user starts a chat.
**Then** Studio retains the existing blocking `message/send` behavior and displays the final result.

### Scenario 3: Connection loss

**Given** the Runtime accepted the task and started emitting events.
**When** the browser or Studio BFF connection disconnects.
**Then** execution and persistence continue, Studio does not resubmit the request, and refresh can retrieve the final result from the original session/task. Live replay of missed deltas is not required initially.

### Scenario 4: Concurrent sessions

**Given** two Studio sessions use the same Runtime concurrently.
**When** both sandboxes execute.
**Then** each session receives only its own invocation events and uses an isolated sandbox.

## 3. Functional requirements

- **FR-1 — Streaming capability.** The mpa-agent card advertises `capabilities.streaming=true` while retaining `message/send`.
- **FR-2 — Standard streaming call.** Studio uses `message/stream` when supported and parses upstream SSE incrementally.
- **FR-3 — Invocation-local event bridge.** mpa-agent composes the existing `codex_event_handler` for the current A2A invocation and sends allowlisted `CodexNormalizedEvent` projections to the current A2A `EventQueue`. No process-global relay is introduced.
- **FR-4 — Single terminal owner.** The relay emits only progress and artifacts. The official executor and existing distributed-control linearization remain the sole owners of completed, failed, and canceled task states.
- **FR-5 — Studio mapping.** The BFF maps A2A status, text, data, and artifact events into the existing Studio ADK event contract while preserving event, invocation, command, append, and terminal semantics.
- **FR-6 — Safe fallback.** Missing streaming capability selects `message/send` before execution. A streaming attempt may fall back once only when the server explicitly reports method-not-supported before any event is observed. Timeout, 5xx, 401/403, malformed data, and failures after the first event never resubmit.
- **FR-7 — Disconnect semantics.** Disconnect does not cancel or resubmit the Runtime task. Task/session identity is retained so refresh can read the final persisted result. Live resumption is deferred.
- **FR-8 — Backpressure.** Tool states and terminal events cannot be dropped. Adjacent text deltas may be coalesced at no more than 50 ms or 512 characters, and individual output events are bounded.
- **FR-9 — Safe output.** Only normalized, display-safe fields are emitted. API keys, authorization values, endpoint credentials, full environment variables, and raw worker payloads are excluded.
- **FR-10 — Compatibility.** Ordinary ADK `/run_sse`, Web, Feishu, scheduled tasks, bot-group behavior, and legacy blocking A2A remain unchanged.

## 4. Design

### 4.1 Flow

```text
Studio /run_sse
  -> inspect agent-card capability
  -> message/stream
  -> mpa-agent A2A executor
  -> invocation-local codex_event_handler
       -> existing path: Session Stream + PostgreSQL
       -> new path: A2A progress/artifact event
  -> A2A SSE
  -> veadk incremental decoder / adapter
  -> Studio ADK SSE
```

### 4.2 mpa-agent boundary

`app/a2a/app.py` passes `AgentCapabilities(streaming=True)` when building the agent card. The A2A SDK already registers `message/stream`; no new HTTP route is added.

`ObservableA2aAgentExecutor.execute()` creates a composed callback scoped to the current invocation:

1. Invoke the existing handler to preserve Session Stream publication and persistence.
2. Project allowlisted normalized events into A2A progress/artifact events.
3. Enqueue them on the current request's `EventQueue`.
4. Let the closure expire with the invocation; keep no global session-to-queue registry.

`sandbox_task` retains ADK-native `tool_context.actions.skip_summarization` to prevent repeated model calls. Its final output remains a standard function-response artifact.

### 4.3 Public event contract

Progress uses an A2A data part:

```json
{
  "kind": "data",
  "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
  "data": {
    "eventId": "worker-event-id",
    "invocationId": "e-...",
    "eventType": "tool.call",
    "payload": {}
  }
}
```

Allowed event types are `status.notice`, `message.delta`, `tool.call`, `tool.output`, `tool.result`, `tool.error`, `file.change`, `usage.updated`, `invocation.completed`, `invocation.failed`, and `invocation.cancelled`. `thought.delta` is hidden from Studio by default.

### 4.4 Studio bridge

Add `veadk/cli/runtime_a2a_stream.py` with these responsibilities only:

- Incremental A2A SSE frame decoding.
- JSON-RPC/A2A external response validation.
- A2A event to Studio ADK event conversion.
- Per-request deduplication, tool pairing, delta coalescing, and terminal protection.

`cli_frontend.py` remains responsible for capability selection, authenticated upstream connection, fallback, and `StreamingResponse`. The streaming branch must not call `_runtime_proxy_buffer()`.

### 4.5 Event mapping

| A2A event | Studio event | Presentation |
| --- | --- | --- |
| submitted/working | status metadata | running state |
| `status.notice` | progress metadata | sandbox startup/wait |
| `tool.call` | `functionCall` | tool card start |
| `tool.output` | sandbox progress metadata | live command output |
| `tool.result` | `functionResponse` | tool completion |
| `message.delta` | text part with `partial=true` | incremental text |
| final function response | text part with `partial=false` | final text |
| failed/canceled | error/status event | failure/cancel state |

### 4.6 Ordering and terminal behavior

- Prefer `(taskId, eventId)` as the deduplication key.
- Preserve call/output/result order for each `commandId`.
- Ignore late non-terminal events after terminal state.
- Emit at most one final text event and one terminal marker per task.
- The callback relay does not submit terminal task state and therefore cannot bypass distributed control.

### 4.7 Disconnect and recovery

- After task acceptance or the first event, connection failure ends only the browser stream.
- Do not automatically call `message/send` or retry `message/stream`.
- The A2A SDK continues consuming and persisting the task in the background.
- Studio retains the session/task mapping and loads the final result from task or session history after refresh.
- Complete replay of missed deltas is deferred.

## 5. Edge cases

| Case | Behavior |
| --- | --- |
| Agent card has no streaming field | Use existing `message/send` |
| Method-not-supported before any event | Fall back once to blocking mode |
| Stream drops after submitted | Do not resubmit; offer refresh for final result |
| 401/403 | Surface authentication failure; no fallback |
| Malformed SSE/JSON | Surface protocol failure; no resubmission |
| Duplicate event ID | Drop duplicate |
| Slow consumer | Coalesce text; retain tool result and terminal |
| Empty final text | Do not fabricate output; close with actual task state |
| Concurrent sessions | Bind callback closure to each invocation/EventQueue |

## 6. Implementation tasks

| Task | Work | Dependency | Deliverable |
| --- | --- | --- | --- |
| `T-1` | Isolate current mpa-agent work on a feature branch | None | `fix/a2a-studio-streaming` |
| `T-2` | Write failing agent-card capability tests | T-1 | Capability contract test |
| `T-3` | Write failing invocation relay tests | T-2 | Ordering, isolation, terminal tests |
| `T-4` | Implement mpa-agent capability and relay | T-3 | Raw `message/stream` emits progress |
| `T-5` | Define and test the veadk SSE decoder | T-4 | `runtime_a2a_stream.py` |
| `T-6` | Integrate `message/stream` and safe fallback | T-5 | Incremental Studio `/run_sse` |
| `T-7` | Map tool cards, output deltas, and final text | T-6 | Studio streaming presentation |
| `T-8` | Test disconnect, concurrency, cancel, and old Runtime | T-7 | Integration evidence |
| `T-9` | Regress Feishu and bot-group behavior | T-8 | Non-regression evidence |

## 7. Tests and acceptance

| Requirement | Acceptance | Verification |
| --- | --- | --- |
| FR-1 | `AC-1`: agent-card returns `streaming=true` | mpa-agent unit test and curl |
| FR-2/3 | `AC-2`: `message/stream` emits before task completion | Raw A2A SSE integration test |
| FR-3/5 | `AC-3`: tool start, output, and completion reach Studio in order | Cross-repo integration test |
| FR-4 | `AC-4`: one terminal event per task | Unit and E2E tests |
| FR-6 | `AC-5`: fallback only on pre-event method-not-supported | veadk unit tests |
| FR-6/7 | `AC-6`: stream loss creates no second task | Request count and task-store assertion |
| FR-7 | `AC-7`: task completes after disconnect and refresh loads final output | Live disconnect test |
| FR-8 | `AC-8`: slow consumers retain tool results and terminal events | Bounded-queue stress test |
| FR-9 | `AC-9`: no secret, credential, or raw environment data in stream | Secret scan and payload assertions |
| FR-10 | `AC-10`: legacy Runtime, Web, Feishu, scheduled task, and bot group pass | Regression and live checks |
| All | `AC-11`: `sleep 2; echo step-1; sleep 2; echo step-2` arrives over time | Timestamped E2E record |
| All | `AC-12`: concurrent sessions use distinct sandboxes without cross-streaming | Concurrent E2E |

Completion requires unit tests, raw A2A streaming evidence, visible Studio progress and final output, legacy Runtime fallback, and Feishu non-regression. A visible final response alone is insufficient.

## 8. Risks and rollback

- **Duplicate execution:** fallback is limited to pre-event method-not-supported.
- **Data exposure:** project only allowlisted normalized payload fields.
- **Terminal races:** progress relay never produces terminal task state.
- **Memory pressure:** use an invocation-local bounded queue and coalesce text.
- **Release constraints:** the test registry has a tag limit; delete only test tags proven unused by any Ready Runtime.
- **Rollback:** restore the previous Ready mpa-agent Runtime version and disable the capability path in veadk to return to `message/send`. No data migration is involved.

## 9. Review and decision record

- 2026-09-12: `review-spec` found that switching to `message/stream` alone cannot expose sandbox side-channel events; invocation-local callback relay was added.
- 2026-09-12: PostgreSQL polling and a process-global relay were rejected to avoid database coupling and multi-replica routing complexity.
- 2026-09-12: Initial live stream resumption was explicitly deferred. Tasks must not be resubmitted, and refresh must recover the final persisted result.
- 2026-09-12: mpa-agent work was safely moved from `main` to `fix/a2a-studio-streaming` with all uncommitted changes preserved.
