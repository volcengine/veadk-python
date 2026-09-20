# Studio Runtime Diagnostics

- **Component ID:** `studio-runtime-diagnostics`
- **Status:** Draft; proposed changes are governed by the related PRD
- **Revision:** 2026-09-12
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
