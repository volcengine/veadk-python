# Normalize MPA reasoning snapshots by source
[中文版](2026-09-22-mpa-reasoning-snapshots.zh.md)

ID: `mpa-reasoning-snapshots`; date: 2026-09-22; status: implemented.

## Evidence and scope
Read-only inspection of the reported task confirms outer status deltas followed by a multi-part full message, and sandbox deltas followed by an exact full replay. A sandbox tool.call arrives before the last thought tokens. Replaying outer history before sandbox artifacts reproduces the duplicate: existing cross-source suffix comparison drops punctuation and corrupts the accumulated sandbox text. This continues the user-approved missing/duplicate reasoning correction; command presentation is not redesigned.

## Requirements and design
FR-1: Normalize only explicit MPA A2A streams. Add optional `mpa_a2a=False` to the decoder; server passes the existing trusted runtime category. Default/general behavior is preserved.
FR-2: Join consecutive thought parts in MPA status messages before comparing their complete snapshot to accumulated outer text. Usage-marked snapshots remain supported. Never compare sandbox reasoning with outer reasoning or another invocation. Preserve real repeated deltas and novel text; only a complete matching/extended snapshot replaces previously emitted content.
FR-3: Track sandbox reasoning segments per task/invocation. Tool results and answer deltas mark a new reasoning phase, but tool.call alone does not: already-issued thought tails can arrive after a call. Emit `reasoningSegmentId` on thoughts. Scoped frontend projection appends a late tail to the matching thinking block across the tool row. Never move/delete tool rows or distinct reasoning phases. Snapshot equality suppresses only the accumulated full replay after multiple deltas; a new phase with identical text remains visible.
FR-4: Preserve failure/cancellation output, event replay dedup, final-answer dedup, usage and invocation isolation. No credentials, cloud deployment, user-state mutation or new dependencies. Server history missing events cannot be reconstructed.

## Tasks and acceptance
T-1/AC-1: failing synthetic regressions for outer multi-part snapshots, mixed-source punctuation, sandbox full replay, late thought tails, separate invocations, repeated deltas and later distinct phases.
T-2/AC-2: implement the explicit backend mode, pass runtime category, and add scoped frontend segment projection. Update CON-10 in bilingual runtime diagnostics.
T-3/AC-3: targeted Python/frontend and proxy tests, Ruff/Pyright, full frontend tests/build/assets, isolated browser replay, secret scan and diff checks. Record actual activation separately; no automatic restart of a server retaining in-memory session indexes.

## Review and risks
Direct review substitutes for unavailable review-spec. Requirements, security, state ownership, cancellation, compatibility and bilingual equivalence reviewed; no design blockers. User “看看怎么修” continues previous explicit fix authorization. Unlabelled full replay detection is conservative and restricted to a phase with multiple deltas; identical text alone across phases is never enough to deduplicate. Async ordering is covered by a tool.call between thought deltas. No API request-schema change; output metadata is additive.

## Verification
2026-09-22; working diff based on `3bbd260a`. Verification results below. No commit or push requested.

## Delivery verification
Executed 2026-09-22 on the working diff based on `3bbd260a`; T-1 through T-3 implemented and reviewed.
- `pass`: failing baseline reproduced three absent decoder-mode cases, late-tail block splitting, and mixed null metadata. Added regressions cover snapshots, repeated deltas, phase/invocation isolation, interruption, live/history projection and trusted runtime mode selection.
- `pass`: read-only real-task event replay produces two reasoning segments whose full contents exactly match the authoritative outer and worker messages; no raw content/identifiers copied into fixtures or docs. This is replay, not a new live generation.
- `pass`: `uv run --extra dev pytest tests/cli/test_runtime_a2a_stream.py tests/cli/test_frontend_runtime_proxy.py -q` — 130 tests, five existing SDK deprecation warnings.
- `pass`: `npm --prefix frontend test` — 1,303 Node and 25 Vitest tests; `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets` — 104 files, 248 references. Existing chunk-size warnings remain.
- `pass`: isolated real-browser replay with sanitized Python bridge output and actual Blocks; exactly two expandable reasoning blocks, one retained tool, one final answer. Temporary browser/server/fixture removed.
- `pass`: Ruff 0.11.12 check/format on four changed Python files, scoped repository/default gitleaks including built assets, bilingual contract review and `git diff --check`.
- `fail` (existing baseline): Pyright reports 36 errors in `cli_frontend.py` and 20 in `test_frontend_runtime_proxy.py`. Compared copies from HEAD: identical diagnostic messages/rules before and after; zero new errors. Decoder and its tests have zero errors. Unrelated baseline issues were not modified.
- `not_run`: activation/new live cloud generation. Port 8000 process started 17:44:27, before backend edits at 18:01; restart remains necessary. A restart loses process-local A2A session indexes, so activation awaits the user's decision.
- `not_applicable`: new input, keyboard/IME, loading/retry or narrow-layout controls, SDK/sidecar changes. No commit or push performed.
