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

## 2026-10-20 scope correction: direct database URL

The continuing authorized instrumentation task exposed another SDK-owned construction path: `ShortTermMemory(db_url=...)` creates the original `DatabaseSessionService` directly and bypasses CON-6. The existing three-factory tests do not cover this entry point. The current Playground memory backend is not evidence that database persistence was exercised.

Route this constructor through the same internal traced subclass, preserving `db_url` precedence and `db_kwargs`. Keep the original base-class import for existing type checks. Do not wrap caller-owned services, change database configuration or log the URL. Extend the existing real SQLite and ADK Runner tests to both factory and direct-URL entry points; establish failure before the fix, then verify event/state persistence, the parent Trace and redaction. Existing cancellation, partial-event and telemetry-failure contracts remain unchanged.

Direct review against the parent design and CON-6 found no API, authentication, exporter or storage-schema change. This is a correction within the user's existing implementation authorization, renewed by the instruction to continue. Runtime deployment and APMPlus receipt remain separate acceptance steps. Verification on the rebased upstream main `86c93529969e6dde86890b30f7e407bfc32ff5ea`: direct-URL regression first reproduced 2 failures (missing persistence Spans) and 1 pass; after the fix, the affected suite passed 35 tests. The full parallel regression passed 7539 tests, with 50 skipped and 4 xfailed (502.56 s), excluding `codex_smoke` and `piagent_smoke`. `uv run --no-sync --extra dev pre-commit run --all-files` passed. Test commands used the existing local environment with `--no-sync` and the dev/extensions/codex/sandbox extras. A separate local SDK-to-VeADK ASGI probe verified `/run`, `/run_sse` and `/invoke` with a fresh SQLite database: each request persisted events and produced four save Spans under the request Trace and diagnostic Run. The default in-memory probe also passed. These are local deterministic-model checks, not remote database, real-model or APMPlus ingestion evidence. Runtime V6 still uses the earlier VeADK revision; this correction has not been deployed.

### Regression environment clarification (10/20)

The 7539-test full regression above used the existing Python 3.12.14 / Google ADK 2.2.0 / OpenTelemetry 1.37.0 environment (`--no-sync`). The synchronized upstream source requires ADK >=2.7,<2.8, so that result establishes legacy dependency compatibility only. Wheels from the fixed commits and Linux/Python 3.11 dependency resolution have now succeeded (ADK 2.7.1, OpenTelemetry 1.42.1); isolated-environment runtime verification is recorded separately.

Isolated declared-dependency verification: the base image lock passes `uv pip check`, 35 affected tests (13.54 s), and SQLite/in-memory correlation through all three SDK routes. After installing dev/extensions/codex/sandbox, the full regression passes 7539 tests, with 50 skipped, 4 xfailed and 82 warnings (566.68 s), excluding real smoke runs. The extended regression uses cachetools 6.2.6 versus 7.2.1 in the base image; Google ADK 2.7.1, OTel 1.42.1 and FastMCP 3.4.8 are the same. ADK warns that the existing Google GenAI auto-instrumentation package is below its recommended version. These checks establish VeADK model/tool/save spans, not completeness of ADK other automatic tracing.
