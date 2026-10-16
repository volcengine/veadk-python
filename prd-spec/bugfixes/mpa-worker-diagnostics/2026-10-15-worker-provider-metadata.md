# MPA Worker Provider Metadata Diagnostics

[中文版](2026-10-15-worker-provider-metadata.zh.md)

## Metadata

- Change ID: `mpa-worker-diagnostics`
- Created: 2026-10-15
- Revised: 2026-10-15
- Status: approved
- Related component spec: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)

## Background and Evidence

BytePlus Studio MPA creation failed for task `84f8dfe6-e7fa-4063-9803-912ff12fbc3a` at stage `worker` with diagnostics `create_worker/provider_error`, then surfaced as `creationFailed` at stage `network`. The private task database recorded no `error_code` or `request_id` for the Worker failure. Read-only checks showed:

- `/web/ui-config` is `provider:"byteplus"` and `/web/runtime-config` reports `credentials:true`.
- The BytePlus PG bootstrap database already has admin and per-agent business Workspace records for `mpa_agent_wlc-ap-test`.
- BytePlus AgentKit Tools list has no `wlc-ap-test` Tool and no Tool tagged with the target `mpa_agent_key`.
- The current child runner drops raw stderr and only persists allowlisted `MPA_EVENT` diagnostics, so the historical provider response cannot be recovered.
- Runtime and OpenViking paths already extract safe provider `Error.Code` and `RequestId` from wrapped SDK bodies, but Worker retry diagnostics only classify the exception and discard those identifiers.

Assumption: the provider response may contain a structured error code in the SDK wrapper body or response object, as seen in Runtime/OpenViking tests. This change does not assume which cloud-side error is present.

## Goals and Non-Goals

Goals:

- Preserve safe provider `errorCode` and `requestId` for Worker API failures when available.
- Reuse the existing `task_diagnostics.error_code` and `request_id` fields.
- Keep raw provider messages, request bodies, credentials, image URLs with tokens, and exception text out of task state and logs.
- Avoid changing Worker create payloads, resource lifecycle, retry counts, UI behavior, or cloud permissions.

Non-goals:

- Fix the underlying BytePlus `CreateTool` rejection.
- Add new UI fields or expose raw provider messages to the browser.
- Retry failed historical tasks automatically.
- Change Runtime/OpenViking behavior beyond moving shared safe-metadata extraction to a common helper.

## Scenarios and Requirements

- `FR-1`: Given `WorkerCloud.create` raises an SDK error whose wrapped body contains `ResponseMetadata.Error.Code` and `RequestId`, when `retry_worker` records the failed attempt, then `task_diagnostics` stores the allowlisted `error_code` and `request_id`.
- `FR-2`: Given the SDK error body is malformed, oversized, free text, or token-shaped, when diagnostics run, then no raw text or unsafe identifier is stored.
- `FR-3`: Given a safe provider code is extracted, when the existing category is generic `provider_error` or `unknown`, then diagnostics may refine the category through the existing safe code-category map.
- `FR-4`: Given Runtime create/update failures already record metadata, when the helper moves to diagnostics, then existing Runtime behavior and tests remain equivalent.

## Design and Contract Impact

The implementation adds a shared safe helper in `veadk.integrations.mpa.managed.diagnostics` to inspect a bounded exception chain for:

- direct `error_code` / `request_id` attributes,
- structured `response.json()` or `body` metadata handled by the existing OpenViking helper,
- single string/bytes SDK arguments containing bounded JSON or bytes literals.

`retry_worker` uses the helper before recording diagnostics. It passes the safe identifiers to the existing `report()` path, which already validates allowlisted fields. The helper rejects malformed, oversized, free-text and token-shaped values.

Component spec impact: no contract change. `task_diagnostics` already supports optional `error_code` and `request_id`, and the redaction boundary remains unchanged. This bugfix fills missing Worker coverage for the existing observability contract.

Security impact: positive. The change increases structured diagnosis without widening persisted data. Raw provider messages and payloads remain excluded.

Compatibility impact: additive diagnostic metadata only. Existing rows remain valid and callers that ignore the fields are unchanged.

## Implementation Tasks

- `T-1`: Move safe SDK metadata extraction into `diagnostics.py`.
- `T-2`: Update Runtime create/update diagnostics to use the shared helper without behavior drift.
- `T-3`: Update Worker retry diagnostics to report safe `errorCode` and `requestId`.
- `T-4`: Add regression coverage for Worker SDK wrapper metadata and unsafe body rejection.

## Verification and Acceptance

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-3`, `T-4` | `AC-1`: Worker diagnostics preserve safe provider code/request ID | `uv run --extra dev pytest tests/integrations/mpa_managed/test_runtime_diagnostics.py tests/integrations/mpa_managed/test_worker_recovery.py -q` | `pass`, 57 passed on 2026-10-15 |
| `FR-2` | `T-1`, `T-4` | `AC-2`: malformed/unsafe bodies do not persist text or tokens | Same targeted pytest command | `pass`, 57 passed on 2026-10-15 |
| `FR-3` | `T-3`, `T-4` | `AC-3`: safe codes can refine generic Worker categories | Same targeted pytest command | `pass`, 57 passed on 2026-10-15 |
| `FR-4` | `T-2` | `AC-4`: existing Runtime diagnostics tests still pass | Same targeted pytest command | `pass`, 57 passed on 2026-10-15 |

Required targeted command:

```bash
uv run --extra dev pytest tests/integrations/mpa_managed/test_runtime_diagnostics.py tests/integrations/mpa_managed/test_worker_recovery.py -q
```

Live BytePlus confirmation requires restarting Studio with the updated backend and retrying the same or a new MPA creation request. That cloud retry is separate from automated unit verification.

## Risks and Open Questions

- The provider may still omit structured metadata; in that case diagnostics will remain generic and no raw fallback will be stored.
- The likely BytePlus cause remains unconfirmed until a new retry records a code or cloud control-plane logs are checked.
- `.zshrc` currently starts Studio as a side effect after exporting BytePlus credentials; interactive shell launches can accidentally attempt a second Studio process on port 8000.

## Review and Delivery Record

Design review conclusion: this is a narrow observability bugfix using an already-established redaction pattern. It does not change cloud payloads or user-visible API shape.

User approval: active debugging request requested continuous monitoring and root-cause diagnosis; this diagnostic enhancement is required to avoid guessing from generic `provider_error`.

Implementation completed on 2026-10-15. Targeted pytest passed with 57 tests; `uv run ruff check veadk/integrations/mpa/managed/diagnostics.py veadk/integrations/mpa/managed/runtime.py tests/integrations/mpa_managed/test_worker_recovery.py` and `git diff --check` also passed.
