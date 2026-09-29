# Studio Runtime Diagnostics

- **Component ID:** `studio-runtime-diagnostics`
- **Status:** Draft; proposed changes are governed by the related PRD
- **Revision:** 2026-09-30
- **Chinese version:** [README.zh.md](README.zh.md)
- **Related PRD:** [MPA Runtime Integration Hardening](../../prd-spec/bugfixes/mpa-runtime-integration/2026-09-12-mpa-runtime-integration-hardening.md)
- **Owned code:** `frontend/server/runtime_logs.py`, `frontend/src/ui/RuntimeLogsDialog.tsx`, `veadk/cli/runtime_a2a_stream.py`, `frontend/src/adk/tokenUsage.ts`, `frontend/src/ui/TraceDrawer.tsx`, and the Runtime A2A BFF in `veadk/cli/cli_frontend.py`

## Responsibility

This component gives an authorized Studio user bounded live Runtime logs, a local download of the visible sanitized snapshot, normalized token usage, request-scoped model selection when advertised by an A2A Runtime, and normalized APMPlus trace inspection. It does not own Runtime log retention, provider billing, model credentials, or APMPlus IAM policy.

## Contract

- `CON-1`: Runtime logs are authorized through the Studio BFF, refreshed as replacement snapshots, sanitized server-side, and bounded to the latest 1,000 logical lines. Download returns exactly the current visible snapshot and never bypasses BFF authorization or sanitization.
- `CON-2`: A2A usage metadata and worker `usage.updated` are normalized into existing ADK `usageMetadata`/`modelVersion` fields. Replayed cumulative snapshots must not inflate the session total.
- `CON-3`: Model selection is visible only when the connected A2A agent advertises more than one allowed model. Studio sends only a model ID in request metadata; the Runtime validates it. Selection is session-local and immutable during an active turn.
- `CON-4`: Trace loading preserves explicit state semantics: 404 disabled, 425 collecting, 403 permission required, 502 provider failure, and 200 normalized spans. Empty or denied data is never reported as success.
- `CON-5`: Runtime API keys, model keys, provider credentials, and raw unsanitized logs never enter downloaded files, model-selector values, agent-card capabilities, or frontend state.

## State and concurrency

The log stream may reconnect; stale streams are cancelled on target/dialog changes and cannot overwrite the latest target. Blob URLs are revoked immediately after download. Token snapshots are keyed by their source/request identity and monotonic within a stream. Model selection cannot change mid-turn. Trace retries stop on close/unmount and distinguish retryable collection from terminal permission/configuration states.

## Compatibility

Non-A2A agents and A2A agents without model capabilities retain the existing Composer. Existing token and trace UI components remain the single presentation owners. Existing specialized transcript/tool renderers are unchanged.

## Verification

| Contract | Validation |
| --- | --- |
| `CON-1` | Runtime log service tests, dialog tests, browser download and reconnection checks |
| `CON-2` | A2A decoder and token aggregation tests plus live Runtime usage |
| `CON-3` | BFF metadata tests, mpa-agent validation tests, and browser default/override/invalid cases |
| `CON-4` | Endpoint tests for 404/425/403/502/200 and real TraceDrawer check |
| `CON-5` | Secret scan and assertions that keys/raw logs are absent from browser payloads/downloads |

- `CON-6`: The A2A bridge emits a nonterminal connecting status before upstream waits. The transcript displays connecting/submitted/working as waiting/queued/running in the existing progress placeholder. Status is not an answer or proof of acceptance; content supersedes it. Valid streams wait until completion, error or cancellation, with no automatic retry.

- `CON-7`: Authorized Runtime proxy requests carry the Studio principal owner as x-user-id, matching task management ownership; incoming identity headers cannot override it.

- `CON-8` (implemented): For MPA A2A streams, a nonempty sandbox `invocation.completed.payload.finalMessage` is projected as a consolidated `turnComplete` answer with its sandbox invocationId. Legacy `text`/`message` payloads remain accepted. Only subsequent complete answer text parts exactly matching a boundary-trimmed sandbox final for that task are omitted. Distinct/extended text, reasoning, partial deltas, tools/errors and usage/status events remain. Empty, failed, cancelled, and unidentified-task events cannot claim this ownership. Identified sandbox source events project once per task across artifact updates and snapshots. State is decoder/request-local and is discarded on completion, disconnect or cancellation. Non-MPA and direct ADK/native session behavior is unchanged.

`CON-8` is maintained by [MPA A2A final-answer ownership](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-a2a-final.md), verified in `tests/cli/test_runtime_a2a_stream.py` and cross-layer frontend replay. This addition does not promote the other draft contracts to implemented status.

- `CON-9` (implemented): A Runtime app discovered as `a2a-default` uses the A2A bridge for session create/list/read/delete/run and skips native execution-config preflight, regardless of MPA category/instance metadata. Other MPA apps retain native Profile/session/run/SSE behavior; ordinary ADK apps are unchanged. Errors and cancellation never switch protocols. No session migration, auth change or persistence change is implied. See [A2A session routing](../../prd-spec/bugfixes/studio-session-protocol/2026-09-22-a2a-session-routing.md) and `frontend/tests/runSseAbort.test.mjs`.

- `CON-10` (implemented): Explicit MPA A2A transcript mode reconciles adjacent matching/extending consolidated outer reasoning snapshots and evaluates empty-response notices across one user request. Partial deltas and sandbox events remain intact; genuinely empty completed requests retain one notice. General ADK/A2A and native MPA default behavior is unchanged. See [MPA A2A reasoning](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-a2a-reasoning.md). MPA outer and sandbox consolidated events without authoritative thought text retain thinking blocks from the live-preview region while replacing answer preview. This preserves distinct outer and sandbox reasoning after the final answer, including direct answers without sandbox calls; authoritative thought snapshots retain replacement semantics. Explicit MPA A2A bridge mode normalizes multi-part outer thought snapshots independently of sandbox invocation segments. Additive `reasoningSegmentId` keeps delayed sandbox thought tails in their original block across tool.call; tool results and answer deltas separate phases. General/default decoding is unchanged. MPA final/replacement artifact thought parts must be joined with exact whitespace before snapshot comparison; append-only chunks remain deltas. Coalescing never crosses non-thought parts.

- `CON-11` (implemented): MPA A2A presents adjacent assistant fragments as one response with one footer, source-keyed request usage, last visible answer feedback identity and latest session-trace cutoff. Source turns and general-agent behavior remain unchanged. See [response grouping](../../prd-spec/features/mpa-response-grouping/2026-09-22-mpa-response-grouping.md).

CON-8/CON-11 correction (implemented): preserve distinct outer text and reasoning after sandbox completion. Deduplicate only exact complete answer parts in the bridge; MPA grouped view may hide exact answer mirrors without mutating source turns and restores an extended fragment intact. General Codex tool behavior is restored. See [preserve follow-up](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-preserve-followup-content.md).

- [MPA reasoning snapshot normalization](../../prd-spec/bugfixes/studio-codex-commentary-dedup/2026-09-22-mpa-reasoning-snapshots.md).

- `CON-12`: Only MPA A2A restores the trusted control-plane endpoint prefix `/runtime/[a-z0-9-]+` for a same-origin default `/a2a/jsonrpc` card URL. Already-prefixed URLs, other paths, cross-origin URLs, query/fragment/userinfo are not rewritten. Sending and history restoration use the same resolved address; general agents remain unchanged. See [A2A discovery fix](../../prd-spec/bugfixes/2026-09-23-mpa-a2a-discovery-default.md).

- `CON-13` (implemented): Authorized GET Runtime-proxy `list-apps` prefers a usable Agent Card for control-plane-classified MPA and returns `["a2a-default"]` before ADK probing. General Runtimes and MPA without a usable card retain existing discovery/error behavior. Other requests, authorization, key/header construction and existing sessions are unchanged; reconnect refreshes cached apps, not session migration. See [MPA A2A preference](../../prd-spec/bugfixes/studio-mpa-a2a-preference/2026-09-30-prefer-a2a.md) and `tests/cli/test_frontend_runtime_proxy.py`.

### CON-8 typed event identity (implemented correction, 2026-09-29)
For `mpa.sandbox-event.v1`, source IDs identify upstream records, not unique normalized event types. Project once per `(task_id, invocation_id, event_type, source_event_id)`; an absent source ID disables identity deduplication. MPA artifact frames reach per-part projection, including snapshots mixing old and new parts. Same-ID usage and completion must both survive in either order. Generic A2A frame deduplication is unchanged. The agentkit-mpa-agent relay uses type/source identity within its invocation closure and preserves wire IDs and its original callback. See [design and verification](../../prd-spec/bugfixes/mpa-sandbox-event-identity/2026-09-29-typed-event-dedup.md).
