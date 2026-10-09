# Change: mpa-agent Studio A2A streaming

## Why

Studio currently wraps blocking A2A `message/send` as SSE, so sandbox progress is invisible until completion.

## What changes

- Advertise and serve standard A2A `message/stream` from mpa-agent.
- Project invocation-scoped sandbox events into A2A progress artifacts.
- Incrementally decode and adapt A2A SSE in the veadk Studio BFF.
- Preserve blocking fallback without resubmitting accepted tasks.
- Continue tasks after disconnect; recover final persisted output on refresh.

## Impact

- mpa-agent: A2A card/executor event projection only.
- veadk-python: Runtime A2A bridge and tests only.
- No database migration or provisioning contract change.
