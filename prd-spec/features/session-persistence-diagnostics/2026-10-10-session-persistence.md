# Session persistence diagnostics

## Authorization and evidence
The user authorized completing instrumentation against the AgentKit diagnostic scheme, including Runtime persistence phases. ADK Runner calls SessionService.append_event during execution; AgentkitAgentServerApp preserves caller-provided SessionService identity. VeADK constructs DatabaseSessionService in its SQLite, MySQL and PostgreSQL factories.

## Design and scope
Use an internal DatabaseSessionService subclass in these three factories. Time actual append_event calls as veadk.session.append_event, preserving argument, return, state, failure and cancellation behavior. Partial events bypass timing because ADK does not persist them. Reuse the existing OTel provider; telemetry failure cannot block the database operation. Record no database URL, credentials, event body, session state or raw exception. Custom SessionService and the SDK identity contract remain unchanged. No new exporter, storage or schema.

## Review
Reviewed against existing factories and SDK identity tests. No method monkeypatching, protocol or configuration changes. Bilingual maintained tracing spec must describe scope. SQLite verifies real persistence; patched base-method tests cover cancellation and telemetry failure. MySQL/PostgreSQL factories are checked without connecting to shared databases. Remote deployment and APMPlus receipt remain unverified.

## Tasks and acceptance
- Add internal traced database service and wire all three owned factories.
- Verify real SQLite event/state persistence, partial events, parent context, cancellation, failure redaction and fail-open telemetry.
- Update tracing contract and record exact tests before commit.

## Verification
Affected tests: `uv run --extra dev --extra extensions --extra codex --extra sandbox pytest tests/memory/test_session_persistence_tracing.py tests/memory/test_postgres_schema.py tests/test_adk_compat.py tests/test_short_term_memory.py -q`: 32 passed. Real ADK Runner persisted events/state through local SQLite; parent Trace, identifiers, partial-event bypass, error redaction, cancellation and telemetry fail-open verified. Full regression completed: 6704 passed, 50 skipped, 4 xfailed (484.07 s). Skips do not prove environment-dependent behavior.
