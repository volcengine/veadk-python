# A2A First Event Heartbeat

- **Status:** Implemented and verified
- **Date:** 2026-09-12
- **Change type:** Bugfix
- **Chinese version:** [2026-09-12-a2a-first-event-heartbeat.zh.md](2026-09-12-a2a-first-event-heartbeat.zh.md)
- **Affected component:** [Studio Tool Activity](../../../specs/studio-tool-activity/README.md)

## 1. Evidence and Problem

Studio aborts `/run_sse` when no SSE frame is received within 30 seconds. In the verified Runtime request, the A2A task started at 22:15:41 and the model produced its first displayable content at 22:16:02, but agent-card negotiation made the total request age exceed 30 seconds. The Runtime returned HTTP 200 and logged the active invocation, proving that the public APIG route was reachable.

The bridge currently drops A2A `submitted` and message-less `working` status updates. A healthy long-running invocation can therefore produce no downstream Studio frame before the browser deadline and be cancelled as a false network timeout.

## 2. Scope and Design

- Convert non-final A2A `submitted` and message-less `working` status updates into a Studio metadata-only heartbeat event.
- Preserve the existing projection for `working` messages containing visible text.
- Do not render heartbeat text, create a transcript block, complete the turn, or resubmit the request.
- Do not alter Runtime provisioning, mpa-agent, task semantics, history persistence, or the existing 30-second client deadline.

`a2a_event_to_studio_events()` emits one partial ADK-compatible event containing an empty `parts` list and `customMetadata.a2aStatus`. `runSSE()` treats the parsed frame as first-event evidence, while `createAssistantEventProjector()` ignores events that do not affect the assistant turn. Terminal status updates remain excluded.

## 3. Tests and Acceptance

- Unit-test `submitted` and message-less `working` heartbeat projection.
- Unit-test that the heartbeat is ignored by transcript projection.
- Preserve text-bearing working and terminal status behavior.
- Run targeted A2A/Studio tests, frontend tests, build, asset verification, and pre-commit.
- Live Runtime acceptance: the first downstream SSE frame arrives before 30 seconds and the original request is submitted once.

## 4. Risks

- A heartbeat must not create an empty assistant turn. Mitigation: empty parts and an explicit projector test.
- A terminal state must not masquerade as liveness. Mitigation: emit only non-final `submitted`/`working`.
- A retry could duplicate work. Mitigation: no retry or fallback behavior changes.

## 5. Verification Record

- `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q`: 85 passed.
- Live Runtime `r-yeuujrrcowb21078p9jh`: first metadata-only heartbeat arrived in 0.737 seconds; the final answer arrived in 5.999 seconds; one request produced nine downstream frames.
- Repeated message-less `working` updates are suppressed per `(taskId, state)` by the request-local decoder.
