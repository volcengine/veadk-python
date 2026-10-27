# Agent-owned session sandbox integration

[中文](2026-10-23-agent-owned-mcp-sandbox.zh.md)

Status: implemented. Date: 2026-10-23. Supersedes the Runner integration in
[the earlier design](2026-10-23-managed-mcp-sandbox.md).
Contract: [sandbox lifecycle](../../../specs/sandbox-lifecycle/README.md).

## Intent and evidence

The user selected the second approach: configure `Agent(sandbox=manager)` and
execute the sandbox binding inside the Agent lifecycle, including with an
unmodified google.adk Runner. Storing Agent configuration that only VeADK Runner
reads would not satisfy this request. ADK invokes Agent._run_async_impl inside
an aclosing scope; model callbacks are resolved via canonical_before_model_callbacks.
The existing per-Runner plugin is removed. The unpublished Runner(sandbox=...)
prototype API is replaced by Agent(sandbox=...); existing lower-level Manager API
and runners without sandbox keep their behavior.

## Requirements and design

- FR-A1: Agent accepts a live SandboxManager reference, excluded from repr and
  serialized model output. Validate it and the single ADK agent/empty tools/no
  sub-agents/no code executor scope at construction and again during execution
  (clone bypasses construction validators). Reject run_live explicitly.
- FR-A2: Agent._run_async_impl acquires by trusted app/user/session, creates a
  standard McpToolset and binds it to this async execution context. Each model
  request resolves that context through a built-in callback and registers both
  declarations and executable tools. Existing user callback fields and Agent.tools
  remain unchanged. No Runner registration, custom Toolset or shared URL mutation.
- FR-A3: Exhaustion, model/tool/discovery errors, cancellation and stream aclose
  unwind model execution and MCP before releasing the sandbox lock. Nested scopes
  restore context; no signed endpoint is stored in chat state. Pause/resume keeps
  the physical binding and recreates connections with current endpoints.
- FR-A4: A single Agent works with both VeADK Runner and ordinary ADK Runner,
  across multiple independent concurrent sessions and sequential turns. Same-key
  sandbox execution is locked, but this cannot serialize Runner's earlier chat
  writes: callers must submit turns sequentially within a chat. No claim of
  cross-process chat queuing or fixing ADK concurrent-session history semantics.

Use a ContextVar carrying invocation identity, Agent identity and the transient
McpToolset. A computed canonical callback list prepends tool injection without
mutating the supplied callback field; empty/default agents get no extra callback.
No persistent runtime object is copied when cloning Agents. Agent keeps the
manager configuration only, and validates live manager type lazily. Sandbox
execution is in the default ADK branch only; other runtimes are rejected.

## Tasks, acceptance and risks

| Task | Requirements | Acceptance / checks |
| --- | --- | --- |
| T-A1 | FR-A1–3 | Implement Agent field/scope/callback, remove Runner-specific registration; test failures and cleanup. |
| T-A2 | FR-A2–4 | Parametrize real local MCP tests across ordinary ADK and VeADK Runners; same Agent, two sessions with identical tool names/different output, sequential reuse/resume and persistent chat. |
| T-A3 | FR-A1–4 | Test clone/reconfiguration validation, excluded serialization and missing-session/live boundaries; run affected Agent/runtime/Runner regressions. |
| T-A4 | FR-A4 | Update runnable example and all current bilingual contracts; execute native ADK cloud smoke if credentials remain available. |

Non-goals remain distributed sandbox locking, background task tracking, automatic
TTL renewal/pause/delete, Studio configuration UI/generator support, multi-agent
sharing, live/bidi, and additional model tools. Native ADK compatibility does not
prove Studio UI round-trip support for a live Python manager object. Hooks run
inside ADK's model execution; pre-agent short-circuit callbacks need no sandbox.
The sandbox lock does not cover earlier Runner writes or later Runner compaction.

## Approval and review

The user explicitly chose “第二种吧” after the Agent-native design was proposed.
Direct review substitutes for the unavailable review-spec skill. Reviewed dynamic
scope isolation, callback ordering, clone behavior, schema exclusion, resource
closure, lifecycle ownership, backend dependence and bilingual parity. The chat
queue limitation follows from ADK source and is stated before implementation.
No design blockers remain; approval covers replacing the unpublished Runner API.

## Verification and delivery

Date: 2026-10-23. Scope: current uncommitted Agent-native diff and associated
sandbox code/tests/examples; Python 3.13, google-adk 2.7.1, agentkit-sdk-python
0.8.9, mcp 1.26.0. No dependency changes or cloud Tool configuration changes.

| Check | Result | Evidence |
| --- | --- | --- |
| Test-first regression | pass | 16 Agent-native cases failed before the Agent field/scope existed. |
| `uv run --extra dev pytest tests/sandbox tests/runner tests/runtime/test_agent_transfer.py tests/runtime/test_dispatch_runtime_provider.py tests/agents/test_remote_sandbox_agent.py -q` | pass | 70 tests, 27 upstream deprecation warnings. Both ordinary ADK and VeADK runners exercise concurrency/reuse, callback preservation, errors, cancellation, early close, missing session/live rejection and before-agent short circuit. Includes clone/serialization and existing runtime/Runner/remote-Agent regressions. |
| Ruff check/format on sandbox source/tests/example | pass | New code and example code fences pass. |
| Full-file Agent/Runner Ruff | fail (existing baseline) | 31 Agent and 13 Runner diagnostics, exactly matching HEAD by rule/message; no new diagnostics. |
| CLI help, bilingual pairs, relative links, Python snippets, git diff whitespace | pass | Example directly imports google.adk.runners.Runner and configures sandbox only on Agent. |
| Native ADK cloud smoke | pass | Asserted exact native Runner type and Agent manager reference. One shared Agent/Runner served two independent concurrent sessions for two turns each; same-path files with distinct contents were read back through real model MCP calls. Physical SessionIds were reused; both temporary sandboxes were deleted and confirmed. |
| Cloud pause/resume | not_run | Tool snapshots disabled; local transition tested. |
| Studio UI / full repository suite / pre-commit | not_run | No Studio configuration work or commit requested; targeted Agent/runtime/Runner regression above covers this change. |

T-A1–T-A4 and FR-A1–4 accepted. Direct review checked Agent-native ownership,
context matching/restoration, closed-binding rejection, callback preservation,
clone revalidation, serialization exclusion and native Runner dispatch. The
only remaining Runner change is generic explicit generator closure, needed for
VeADK stream cleanup; there is no sandbox parameter, registry or plugin in Runner.
Current documentation distinguishes sandbox locking from chat queuing. No known
blocking findings remain. No commit, publication or deployment performed.


## Branch validation: 2026-10-27

Branch: `feat/agent-session-sandbox`, synchronized with `origin/main` at
`23014771` using `git pull --rebase origin main` before restoring this change;
no conflicts. `uv run --extra dev pre-commit run --all-files`: pass, including
configured Ruff, secret scans and dependency policy. The targeted regression
command above: pass, 70 tests and 27 upstream warnings. Bilingual document pairs,
relative links and staged diff whitespace: pass. No cloud test was repeated for
this branch operation; cloud evidence remains dated 2026-10-23.
