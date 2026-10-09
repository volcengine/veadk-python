# MPA Runtime task management

[中文版](README.zh.md)

Revised 2026-09-15. Component ID: studio-mpa-cron-tasks.

Studio presents the selected Runtime's user-scoped scheduled tasks. MPA owns persistence, authorization, scheduling and execution. The Studio server owns Runtime access checks, trusted principal resolution and gateway credentials. No TOP/JWT acquisition or all-user fallback is performed. This contract supersedes the prior all-user viewer after MPA revert `91fd6a3`.

## HTTP and identity

All routes require `region` and existing selected-Runtime authorization. Resolve `x-user-id` from the authenticated Studio principal, never from a browser identity header. Resolve the upstream endpoint/key through existing Runtime connection code. Forward only gateway Authorization and x-user-id. JWT-enabled Runtimes must return their normal authentication failure.

| Studio route | Method | MPA route |
| --- | --- | --- |
| `/web/mpa-cron/{runtime_id}` | GET / POST | `/api/v1/esa-cron-tasks` |
| `/web/mpa-cron/{runtime_id}/{task_id}` | POST / DELETE | `/api/v1/esa-cron-tasks/{task_id}` |
| `/web/mpa-cron/{runtime_id}/{task_id}/run` | POST | `/api/v1/esa-cron-tasks/{task_id}/run` |
| `/web/mpa-cron/{runtime_id}/{task_id}/runs` | GET | `/api/v1/esa-cron-tasks/{task_id}/runs` |

Task IDs allow letters, digits, underscore and hyphen. Mutations allow only existing MPA schema field names, with a 32 KiB body limit. Upstream validates field values. Requests time out after 30 seconds and do not follow redirects. HTTP failures preserve their status without echoing upstream bodies; malformed/network/redirect responses fail safely. Listing uses includeDisabled=true and server pages of 20. History remains paginated. Mutations preserve expectedVersion and stable clientToken for retries of the same create/run operation.

## UI and state

The mono reference supplies list/calendar, status filter, overview, task detail/history, create/edit/copy, delete confirmation, enabled switch and run-now interactions. Studio uses existing local controls/styles rather than adding mono's workspace dependency graph. Creation requires an Agent ID and prompt; Web and Feishu delivery are supported, and edits preserve unchanged delivery metadata. Copy opens a form without writing until save.

Read all task pages before presenting a complete calendar or filtered list, deduplicate IDs, paginate the list locally by 10. Aggregate metrics use the upstream response's actual all-history scope, not an invented seven-day window. Task lastRunAt and nextRunAt remain distinct. Calendar expands Once/Interval/Daily/Weekly/Monthly and fixed-time Cron, honoring schedule zones and DST; complex Cron shows only server nextRunAt. Day cells group multiple executions of one task. Calendar times display in the device zone; schedules show their configured zone.

No target means no request. Target changes abort reads and ignore stale results, including history and mutation completion. Writes use a single-flight guard; aborting an HTTP write does not mean undoing its server effects. Failed writes retain form inputs, and version conflicts require refreshing. Loading, empty and errors are distinct. Existing Studio/TOS scheduling and ADK sessions are unaffected.

## Verification

See the [implementation and acceptance record](../../prd-spec/features/studio-mpa-cron-tasks/2026-09-15-mono-task-management.md). Cover proxy boundaries, API schemas, mutation concurrency/idempotency, paging, timezone/DST, stale responses, IME, loading/error/retry and keyboard behavior. Incremental coverage must exceed 95%. Browser fixture verification is distinct from live Runtime reads; do not claim live write E2E from mocked tests.

The task editor hides executor Agent input. New tasks automatically use the selected Runtime ID as agentId; edits/copies preserve the original value.

New task creation omits agentId. The Runtime resolves the configured Agent display name, falling back to its runtime agent name. Explicit IDs and edit/copy values remain unchanged. This supersedes the previous Runtime ID default. Approved by the user on 2026-09-15; review found no authentication or execution routing changes.
