# Change: MPA Runtime integration hardening

## Why

VeADK-created mpa-agent Runtimes use external PostgreSQL/OpenViking and a synthetic compatibility space ID, but still call ArkClaw resource discovery, omit the Runtime key from built-in MCP configuration, misorder A2A progress artifacts, and lack complete Studio diagnostics.

## What changes

- Disable ArkClaw resource discovery and lazy login only for VeADK provisioning.
- Publish the Runtime key and public URL in phase two and enable APMPlus safely.
- Correct A2A artifact creation/append ordering and relay usage/reasoning.
- Add bounded sanitized log download and Token usage projection.
- Add allowlisted request-scoped Studio model selection shared by primary and delegated execution.

## Impact

- mpa-agent: configuration, dependency wiring, A2A card/executor, model resolution, sandbox delegation.
- veadk-python: provisioning, Runtime A2A bridge, Studio diagnostics and UI.
- No database migration. Native ArkClaw defaults remain unchanged.
- Live completion requires a separately authorized image publication and Runtime update.
