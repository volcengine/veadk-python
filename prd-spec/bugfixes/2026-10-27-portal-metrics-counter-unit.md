# Bugfix PRD: chat_exception_counter unit

## Background / evidence
`veadk/tracing/telemetry/portal_metrics.py` creates `chat_exception_counter` with
`unit="time"`. Its description is "Number of exceptions occurred during chat
completions". A counter that counts discrete events must not carry a duration
unit; sibling `llm_invoke_counter` uses `"count"`, and `skill_download_counter`
/ `skill_load_counter` already use `"1"`.

## Goals
- Align `chat_exception_counter` to a count unit (`"1"`).
- Add a stdlib-only static regression guard for the counter unit metadata.

## Non-goals
- No change to span/event contracts, public API, dependencies, or metric names.
- No runtime wiring change; no new metric.

## Scenarios
- An operator building a dashboard from `llm_completions_exceptions` sees a
  dimensionless count rather than a duration unit.

## Affected files
- `veadk/tracing/telemetry/portal_metrics.py` (one line: unit `"time"` -> `"1"`)
- `tests/test_portal_metrics_counter_unit.py` (new, static guard)

## Tests
- Static test, run locally in isolation: base main `2301477` fails the exception
  counter assertion (RED); head passes (GREEN). The sibling-counter scope guard
  passes on both revisions.
- The recorder-based runtime test (`test_portal_metrics.py`) requires google.adk
  and is left to CI; not run locally.

## Risks
- Dashboard unit display only; no data migration. Risk: negligible.

## Acceptance
- `chat_exception_counter` unit is `"1"`; the static regression passes; no other
  counter unit changed.
