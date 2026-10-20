# Functional Validation Cases: MPA Runtime Integration Hardening

- **Change ID:** `mpa-runtime-integration-hardening`
- **Status:** Active
- **Date:** 2026-09-13
- **Chinese version:** [2026-09-13-functional-validation-cases.zh.md](2026-09-13-functional-validation-cases.zh.md)

## Cases

| Case | Requirements | Preconditions and execution | Expected result | Evidence | Status |
| --- | --- | --- | --- | --- | --- |
| `VC-1` | `FR-1`, `FR-3`, `FR-9` | Run mpa-agent dependency/config tests; after publishing, observe a VeADK Runtime for at least 240 seconds and execute one sandbox turn. | No `ListResources` call, no missing `user_pool_id`, and no expected-config traceback. | Test output; sanitized Runtime logs. | Automated `pass`; live `blocked` by unpublished image. |
| `VC-2` | `FR-2` | Run provisioning env/runtime/CLI tests. | Phase two contains URL and Runtime key; output does not expose the key. | Pytest output and secret scan. | `pass` |
| `VC-3` | `FR-4` | Execute A2A relay tests and a real sandbox command. | First artifact uses `append=false`; subsequent events append and remain visible. | Pytest output; live A2A stream. | Automated `pass`; live `blocked`. |
| `VC-4` | `FR-5` | Run Runtime log backend/frontend tests; open logs, wait for refresh, download. | At most 1,000 sanitized lines; downloaded bytes equal the displayed snapshot. | Pytest/frontend test output; browser screenshot and downloaded file hash. | Automated `pass`; browser `blocked` by missing Playwright Chromium. |
| `VC-5` | `FR-6` | Replay primary A2A usage and repeated worker `usage.updated`; then perform a real primary and sandbox turn. | Existing Token UI shows model/current/cumulative use once; replay does not inflate totals. | Decoder/frontend tests; screenshot and captured SSE. | Automated `pass`; live `blocked`. |
| `VC-6` | `FR-7` | Configure two selectable models; send default and alternate turns; submit an invalid model ID; delegate one turn. | Selector is capability-gated and disabled while busy; valid override reaches both paths; invalid ID is rejected before execution. | mpa-agent/bridge/frontend tests; Runtime logs and screenshots. | Automated `pass`; live `blocked`. |
| `VC-7` | `FR-8` | Inspect Runtime metadata; query `/web/runtime-trace` after a completed turn. | `apmplus_enable=true`; endpoint returns 425 while collecting, 200 with spans, or explicit 403 permission error. | Runtime metadata and normalized trace JSON. | Request tests `pass`; current v31 `fail` because tracing is disabled. |
| `VC-8` | Regression | Run targeted suites, frontend full tests/build, pre-commit, and default Python regression. | No related regression; environment-only failures are separately classified. | Command logs. | `pass` except optional-dependency regression failures. |

## Coverage gate

Every P0/P1 requirement is covered by at least one executable case. Live cases that require publishing are not treated as passed; they remain blocked until explicit deployment authorization is provided.
