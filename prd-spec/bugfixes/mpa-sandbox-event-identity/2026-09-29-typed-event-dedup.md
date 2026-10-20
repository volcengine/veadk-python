# Preserve distinct MPA sandbox events sharing a source ID

[中文版](2026-09-29-typed-event-dedup.zh.md)

ID: `mpa-sandbox-event-identity`; date: 2026-09-29; status: implemented.
Contract: [Studio Runtime Diagnostics CON-8](../../../specs/studio-runtime-diagnostics/README.md).

## Evidence, scope and requirements
Read-only session inspection and anonymous replay confirmed that `usage.updated` and `invocation.completed` can share a source ID. The agentkit-mpa-agent relay and both Studio decoder dedup stages discard the completion. Without the authoritative final marker, the UI can retain streamed preview and wrapper result as two answers.

FR-1: Preserve different normalized event types with the same source ID, including usage, completion, failure and cancellation. Deduplicate actual replays by task/invocation/type/source ID; preserve events without source IDs.
FR-2: Preserve multipart snapshots containing both already-seen and new events. Keep wire IDs and the `mpa.sandbox-event.v1` schema unchanged.
FR-3: Keep reasoning, tools and token accounting; one sandbox final must suppress only an exact complete outer answer mirror. Generic A2A/ADK decoding remains unchanged.
Non-goals: UI redesign, fuzzy text filtering, history mutation, authentication changes, image builds, deployment and cloud resource changes.

## Design and affected files
In agentkit-mpa-agent `app/a2a/executor.py`, key the request-local relay set by `(source_event_id, event_type)`; invocation isolation already comes from the handler closure. Original persistence callback and payload allowlist stay unchanged.
In `veadk/cli/runtime_a2a_stream.py`, defer MPA-schema artifact frame deduplication to per-event projection. A first-part ID cannot identify a multipart frame. Projection uses `(task_id, invocation_id, event_type, source_event_id)`. Generic frame identity stays unchanged. No persistent schema, API, permission or dependency changes. Sets remain decoder/request-local and follow its existing lifetime; disconnect/cancel releases them. Completion, failure and cancellation are separate semantic identities, not mutually deduplicated by source ID.
Tests: `tests/cli/test_runtime_a2a_stream.py`, agentkit-mpa-agent `tests/test_a2a_executor.py`. Existing frontend projection is verified with anonymous Python-to-Node replay without changing frontend source/assets.

## Tasks and acceptance
- T-1 / AC-1 (FR-1/2): Add failing offline tests for same-ID usage/completion in both orders, replay suppression, invocation/task isolation, missing IDs, mixed multipart replay and failure/cancellation.
- T-2 / AC-2 (FR-1/2/3): Apply the scoped relay and decoder changes; preserve exact wire payloads and generic deduplication.
- T-3 / AC-3 (FR-3): Run affected Python suites, Ruff/Pyright, anonymous frontend live/history replay, scoped secret scan and whitespace checks. Verify one answer, retained reasoning and correct token count. Record actual results and unverified deployment separately.

## Review, approval and risks
Direct review substitutes for unavailable review-spec. Checked ownership, compatibility, errors/terminal states, callback order, privacy, bounded request-local lifetime, testability and bilingual equivalence; no blockers. User approved implementation with “帮我改下” after the two-repository diagnosis. No production session data is used in committed fixtures.
Risk: Studio alone cannot recover an event the upstream relay never sends. Both fixes must be deployed to activate the complete correction; image deployment is outside this request. Late exact replays remain suppressed; distinct events remain visible. No migration is needed and old persisted history is unchanged.

## Verification
Date: 2026-09-29. Diff bases: VeADK `79acf209`; agentkit-mpa-agent `62cf960`. Existing unrelated edits are preserved. Results follow below.

### Results
T-1/T-2/T-3 completed for the code change, without deployment. Checks were run against the working diff on 2026-09-29.
- `pass`: before the fix, seven new Studio cases and two relay cases failed; the missing-ID compatibility case passed. Afterward, `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` passed 156 tests (six existing deprecation warnings).
- `pass`: in agentkit-mpa-agent, `.venv/bin/python -m pytest tests/test_a2a_executor.py tests/test_a2a_codex_terminal.py tests/test_codex_delegation_tool.py -q` passed 113 tests. Existing ADK experimental/deprecation warnings remain.
- `pass`: `node --test frontend/tests/mpaResponseGrouping.test.mjs frontend/tests/mpaContentPreservation.test.mjs` passed 22 tests. Anonymous Python decoder → actual frontend projector/grouping replay produced one answer, one retained thinking block and exactly 100 tokens in both live and history modes.
- `pass`: Ruff 0.11.12 check on the two changed Python files in each repository; Studio formatter check; Studio `uv run --with pyright pyright veadk/cli/runtime_a2a_stream.py tests/cli/test_runtime_a2a_stream.py` reported zero errors/warnings. Runtime Ruff used `--no-cache` after the sandbox prevented cache writes.
- `fail` (pre-existing baseline): Runtime Pyright on `app/a2a/executor.py` and `tests/test_a2a_executor.py` reported 45 errors. An isolated HEAD copy with the same interpreter/import path reported the same 45 diagnostic messages; this change adds none. Unrelated type cleanup is excluded.
- `pass`: direct code/design review confirms original callbacks, allowlist and generic dedup remain; paired-language identifiers/links, scoped gitleaks scan and `git diff --check` checked.
- `not_applicable`: frontend build/generated assets, sidecar gates and new layout/keyboard/IME checks; no frontend or sidecar files changed.
- `not_run`: real browser/cloud end-to-end, image build, deployment, service restart, commit and push. Verification is offline replay; existing Runtime images still require replacement to activate upstream forwarding, and Studio must reload the decoder. Full repository regression was not run because the correction is limited to explicit MPA events; affected decoder/proxy/relay/terminal and frontend preservation suites were used.

## Rebase validation — 2026-10-07

Reconciled with main `e0448a4d` for PR #17. The original functional patch is retained; upstream discovery/authentication and Worker recovery changes are preserved. See the [combined reconciliation and verification record](../mpa-shared-network-bootstrap/2026-09-28-registry-owned-network.md#pr-17-rebase-reconciliation--2026-10-07).
