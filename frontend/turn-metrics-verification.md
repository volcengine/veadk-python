# Turn presentation and metrics verification

Comparison base: `b6c01be4f3315bcbdce2975c71673473769e6da4` on
`feat/studio-recoverable-build-ui`. The existing recoverable-build worktree was
preserved. Remote main was fetched and rebase confirmed the branch was current
with `6dcc022c48e95fad75e9a0e3c90e6071d67f5b78`; the temporary autostash was reapplied.
All changes in this worktree belong to the requested presentation/statistics update.

## Gates

| Gate | Status | Evidence |
|---|---|---|
| Change Basis | PASS | Clean feature branch inspected; current main fetched; source, consumers, tests, protocol 0.154.0 and deployment bindings traced. |
| Contract | PASS | Short English command summaries, icon alignment, failures in place, ms, native turn statistics, steer status and Tokens disclosure defined below. |
| Impact | PASS | Protocol → runner → owner-scoped SQLite → SSE → projection → both renderers; background navigation and cloud update included. |
| Portfolio | PASS | Native protocol, real SQLite, projection/component, real Chromium and deployment readback boundaries selected. |
| Baseline | PASS | Two frontend regressions and one missing SQLite metrics contract observed failing before implementation; Escape reopen reproduced in Chromium. |
| Execution | PASS | 504 affected Python and 1184 frontend tests passed. Build, assets, i18n, Pyright and pinned pre-commit passed. |
| Evaluation | PASS | Terminal statuses, replay, steer, continuation, missing data, usage reset, owner isolation, keyboard, layout and old usage-event compatibility covered. |
| Handoff | PASS | Native cloud update succeeded; cloud resources, Identity redirects, uploaded runtime source and public assets verified; exact uploaded UI passed Chromium journey. |

## Observable contract and impact

A native Codex turn gets one summary when completed, failed or interrupted. Steer
messages remain part of the same turn; automatic continuation starts another native
turn and receives a separate summary. Tool count uses distinct native item IDs and
includes failed/interrupted calls, excluding reasoning, plan and diff. Durations
come from the native turn/item fields; unknown durations are not displayed as zero.
Tool time is a sum and can exceed elapsed time when tools overlap.

Tokens are recorded per native turn. Durable thread-total checkpoints prevent
replayed cumulative snapshots and new connection-local counters from double
counting. Counter reset/compaction and interrupted turns are marked incomplete.
Input/output/model/cache/reasoning details use reported fields; uncached input is
input minus cached input, with cached and reasoning subsets never added twice.
If the remote environment becomes unavailable without a native terminal receipt,
the summary says the task ended and leaves native duration/usage unknown.

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
|---|---|---|---|---|---|
| C01 | Retain native lifecycle facts for all terminal statuses; preserve old usage events | App Server and runner | `codex_app_server.py`, `runner.py`, route SSE adapter | Failure/interruption raises before metrics; old consumers lose usage | R01 High |
| C02 | Metrics survive reconnect/replay under the same owner and lease | SQLite task service | `record_turn`, `run_turns.metrics`, existing owner/lease checks | Foreign writes, lost data, migration or stale-worker writes | R02 High |
| C03 | One summary per native turn, unique tool calls, no steer reset | Transcript projection | `DevelopmentRunProjection`, new `turn-summary` block | Replayed tool count inflation or summaries merging continuations | R03 High |
| C04 | Distinguish reported, missing and incomplete usage | Adapter and durable usage aggregation | `_handle_token_usage`, `record_turn` | Thread cumulative count shown as turn count; reset causes fabricated usage | R04 High |
| C05 | Compact command headings, aligned icons and failure in original item | Shared Blocks and development process | `developmentPresentation`, `DevelopmentProcess`, `DevelopmentItemIcon` | Raw command wrapping, title misalignment, pinned failure duplication | R05 Medium |
| C06 | Running status persists around steer and summaries count as visible content | Hook, App and projection | `useDevelopmentRun`, `assistantTurnIsStreaming`, `turnHasVisibleContent` | User message removes active status; ended turn shows false empty response | R06 Medium |
| C07 | Tokens opens on hover/focus/click; Escape dismisses; narrow layout stays usable | New summary component and both renderers | `DevelopmentTurnSummary`, `StudioConversation`, Base UI Popover | Focus reopens dismissed popup; clipped data or overflow | R07 Medium |
| C08 | Current task suppresses its background notice; dismissal survives navigation | Global task monitor | `DevelopmentTaskNotice` | Repeated toast, wrong-session notice or foreign-owner data | R08 Medium |
| C09 | Update exact existing cloud application with original bindings | Native studio update | Preflight and captured native package | Wrong account, changed Identity/Dev/shared Tool or stale public assets | R09 High |

## Test portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
|---|---|---|---|---|---|---|
| R01 | Native protocol and actual SSE routes | Protocol/integration | Completed/failed/interrupted; null/negative timing; legacy usage event | Terminal receipt before exception, native values only; old usage frame remains | `test_codex_app_server.py`, `test_codex_presentation_events.py`, `test_intelligent_development_routes.py` | VERIFIED |
| R02 | Real SQLite database and routes | Persistence/authorization | Reopen with same clock, wrong owner, stale lease, cascade retention, schema expansion | Same metrics after replay, foreign/expired writes rejected | `test_intelligent_development_runs.py`, existing service/routes suites | VERIFIED |
| R03 | Actual projection | State transitions | Repeated seq, completed tool replacement, steer, same input with two native turns, empty/missing facts | Exactly one correctly placed summary; two distinct tools count as two | `developmentRuns.test.mjs` | VERIFIED |
| R04 | Adapter and real database | Counter boundary tests | 100→150→150 cumulative; new turn; new connection resets local counter; total reset | First turn 70, second 30, repeated event adds zero; reset marks incomplete | `test_intelligent_development_runs.py`, native usage tests | VERIFIED |
| R05 | Component plus real browser geometry | DOM and Chromium | Long shell command, failed item, thought/tool/plan/diff icons, collapse | English short title, no pinned failure, thought/tool x=507px | `developmentProcess.test.mjs`, browser journey and screenshots | VERIFIED |
| R06 | Hook/projection and actual App | Regression and browser | Delivered steer without new item, existing item continues, reconnect, stop, summary-only response | Active assistant stays present, one processing prompt, no empty-response fallback | Hook/projection tests, browser journey | VERIFIED |
| R07 | Actual built App | Chromium keyboard/pointer/layout | Hover, focus, Enter, Escape, missing/partial tokens, 1440×960 and 820×900 | Popup dismisses without reopening; correct 2000 uncached and 66.7% hit rate; no overflow/errors | `scripts/checkDevelopmentTurnUi.mjs`, browser evidence | VERIFIED |
| R08 | Task monitor and navigation | Chromium plus owner fencing suites | Leave active task, return using notice, replay after return | Current notice disappears, processing and prior output retained | Browser journey and existing owner-switch tests | VERIFIED |
| R09 | Cloud resources/package/HTTP | Native update and readback | Correct account, 1/1 replicas, Identity, Dev and six shared Tools, installed source/assets | Bound resources preserved, uploaded wheel matches source and public UI | `final.json`, `cloud-final.json`, `http-final.json`; main revision 5, scanner/worker revision 3 | VERIFIED |

## Executed evidence

- Python: `PYTHONPATH=. /data00/home/wujiaming.ai/workspace/github/veadk-python/.venv/bin/python -m pytest`
  over the 14 affected files listed in `build-ux-verification.md`: **504 passed,
  zero failed/skipped**, five dependency deprecation warnings. Log:
  `/tmp/studio-turn-final-python.log`.
- Frontend: `npm test`: **1184 passed, zero failed/skipped**. Log:
  `/tmp/studio-turn-full-js.log`.
- `npm run build`: TypeScript and both Vite builds passed. Existing large-bundle
  warnings remain. `npm run test:webui-assets`: **104 files / 248 references**.
  `npm run check:i18n`: **2 locales / 21 namespaces**.
- `uvx pyright --pythonpath /data00/home/wujiaming.ai/workspace/github/veadk-python/.venv/bin/python veadk/cli/codex_app_server.py frontend/server/intelligent_development_runs/repository.py frontend/server/intelligent_development_runs/runner.py`:
  **zero errors/warnings**. The first invocation without the project interpreter
  missed installed `websockets`; the new Mapping parameter typing was also corrected.
- `uvx pre-commit run`: repository-pinned Ruff 0.11.12 check/format and Gitleaks passed.
- Real Chromium journey uses actual built App, HTTP client, hook, projection and
  both data/display states, with controlled external Sandbox/task responses.
  It retains startup, long output, process folding, IME, reconnect, steer and stop
  checks and adds icon geometry, native summary, token popup and background return.
  Browser **zero page errors**, **820px scroll width at 820px viewport**.

Browser reproduction (start a built Studio test server first):

```bash
PLAYWRIGHT_MODULE=/tmp/studio-recoverable-browser/node_modules/playwright-core/index.mjs \
CHROMIUM_EXECUTABLE=/data00/home/wujiaming.ai/.cache/ms-playwright/chromium-1187/chrome-linux/chrome \
STUDIO_TEST_URL=http://127.0.0.1:18080 \
EVIDENCE_DIR=/tmp/studio-turn-ui-evidence \
node frontend/scripts/checkDevelopmentTurnUi.mjs
```

Evidence directory:
`/data00/home/wujiaming.ai/workspace/reports/studio-turn-metrics-20260916/`.
The initial new SQLite test reopened with a real clock after creating a fake-clock
lease; it was corrected to use the same clock. The affected integration suite
caught a compatibility regression from consuming usage only as metrics; the
original `usage` event emission was restored without weakening its assertion.
A browser run against a server caching a replaced build used stale asset names;
the final built server was restarted and the complete journey rerun. The actual
Escape focus-reopen defect was fixed, and its regression remains in the browser script.

## Deployed artifact verification

Native `studio update` exited 0. The existing Volcengine application
`d7014d0f55f7` in `cn-beijing/default` is published at
`https://snm4e0bjff3hs4mdvnuh6.apigateway-cn-beijing.volceapi.com`.
Main function `a7yabcrg` is revision 5; scanner `ah049y3m` and worker `82flpzkg`
are revision 3. Release, timer and async-task checks passed. Main min/max
instances remain 1/1, with the six-hour local task database preserved in configuration.

Identity pool `92617f66-b5a5-440b-b0f4-28b4e9e1b57e` and client
`a51a5645-bd1a-443b-b666-2dcf75bfcac5` match the requested binding. Public
auth configuration, login redirect and unauthenticated userinfo protection passed.
Dev Tool `t-yev58x4ao0zn6n5imleu` and all six shared chat Tool configurations
were read back and match the preflight snapshot.

The exact uploaded wheel is
`veadk_python-1.1.14.dev4+gb6c01be4f.d20260916-py3-none-any.whl`, SHA256
`00af36a5bfa3687a0c456a07174f1bd48bbf090910515783192bad37ee254ab6`.
It contains the requested changes on the comparison-base commit. Nine runtime
Python modules were compared byte-for-byte with the source. Tracked WebUI assets
were synchronized from that wheel, then the packaged asset check and complete
Chromium journey were rerun successfully. Public HTML, entry JS/CSS, logo and
widget hashes match the actual uploaded wheel. No separate rebuild was substituted
for the deployed artifact.

Read-only verification commands used the selected project Python with `PYTHONPATH=.`:
`verify_final.py`, `verify_cloud.py` and `verify_http.py` in the evidence directory.
Their final receipts all report success. The HTTP verifier obtained the authorize
endpoint from the existing pool's OIDC discovery without changing Identity settings.

## Scope and residual risk

Existing unrelated coverage percentages were not treated as a metric for this
change. The affected contract/state tests are discriminating; adding duplicate
calls, hiding the steer placeholder, dropping usage or reopening the popup makes
them fail. No coverage gate was lowered and no failing assertion was removed to
hide a defect. Failure-pinning assertions were deliberately migrated to the user’s
new requirement that failures remain in their original item.

Browser evidence is Chromium with Chinese UI, desktop/narrow layout and reduced
motion. It does not claim Safari/Firefox, a complete locale/theme matrix, cloud
Identity login or a new paid model build. Exact 0.154.0 generated schemas and native
protocol fixtures were used; missing upstream metrics stay unavailable. A reported
model identifies the configured native turn model; no unreported provider routing
is inferred. Tool counts cover the observed/recovered native tool items.

SQLite remains local, owner-scoped and ephemeral for six hours. The migration only
adds a metrics column. An old-version rollback needs a new short-term DB path
because the old writer uses positional inserts. The user accepted short-term
record loss on instance replacement/redeployment. No task history is stored in TOS.
