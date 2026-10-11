# Tasks

- [x] `T-1` Isolate mpa-agent work on `fix/a2a-studio-streaming`. (`VC-1`)
- [x] `T-2` Add failing agent-card streaming capability tests. (`VC-1`)
- [x] `T-3` Add failing invocation-local relay tests for ordering, isolation, and terminal ownership. (`VC-2`, `VC-4`, `VC-9`, `VC-10`, `VC-13`)
- [x] `T-4` Implement mpa-agent streaming capability and progress relay. (`VC-1`, `VC-2`, `VC-4`, `VC-13`, `VC-14`)
- [x] `T-5` Add failing veadk incremental SSE decoder and event mapping tests. (`VC-3`, `VC-4`, `VC-9`)
- [x] `T-6` Implement `message/stream` and safe pre-execution fallback. (`VC-3`, `VC-5`, `VC-6`, `VC-7`, `VC-11`)
- [x] `T-7` Map tool progress, output delta, direct answer, and final result into Studio events. (`VC-3`, `VC-4`, `VC-15`)
- [x] `T-8` Execute disconnect, refresh, concurrency, cancel, and compatibility validation. (`VC-7`, `VC-8`, `VC-11`, `VC-13`, `VC-14`)
- [x] `T-9` Execute Web, Feishu, scheduled-task, and bot-group regression. (`VC-12`)
- [x] `T-10` Run two review rounds and E2E, then commit and push both repositories. Production release tags are intentionally not created because a veadk tag triggers PyPI/docs publication and requires separate release authorization. (all cases)

## Verification result (2026-09-12)

- Runtime `r-yeuujrrcowb21078p9jh` version 31 is Ready on image `mpa_agent:a2a-v8`.
- Studio sandbox E2E emitted tool calls at 20.23s, output at 22.87s, text deltas from 26.51s, and one final result at 27.44s. Refresh restored the same final result.
- Direct answers emit upstream ADK text deltas followed by one persisted final event; cumulative working snapshots are suppressed without splitting fabricated tokens.
- Two concurrent sessions produced distinct invocation IDs and no cross-stream marker leakage.
- Disconnect completion/recovery and legacy fallback are covered by live evidence and regression tests; no request is resubmitted after task acceptance.
- Secret scan covered 13 local evidence files with zero credential matches.
- Web, Feishu, scheduled-task, and group-bot code paths passed the mpa-agent regression suite. Live Feishu delivery remains environment-blocked because no bot credentials/install target were supplied.
- Frontend package tests are environment-blocked before execution because local `vite`, `esbuild`, and `typescript` dependencies are absent; backend bridge tests pass.
