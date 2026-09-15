# Recoverable build presentation verification

This change keeps task execution independent from the browser and presents Codex 0.154.0 items as a stable conversation. The recoverable task service, native stop/steer, SQLite retention and owner authorization are described in [recoverable-build-verification.md](recoverable-build-verification.md). This report covers the subsequent presentation and event changes plus integration with the updated main branch.

## Gates

| Gate | Status | Evidence |
|---|---|---|
| Change Basis | PASS | Original worktree at `d2ce736821052de81602b422669ae7b5e82430a6` preserved. Changes applied cleanly onto `6dcc022c48e95fad75e9a0e3c90e6071d67f5b78` after fetching/pulling main, on `feat/studio-recoverable-build-ui`. |
| Contract | PASS | Six requested behaviors mapped below; additive item metadata and event payloads, with existing clients retained. |
| Impact | PASS | Native App Server → public redaction → task runner/SQLite → SSE → projection/hook → both Block consumers traced. |
| Portfolio | PASS | Protocol, redaction, projection, hook race, disclosure DOM, real Chromium and cloud verification boundaries selected. |
| Baseline | PASS | Observed four backend regression failures and three frontend projection failures before implementation. Original source hashes preserved; actual prior uploaded wheel matched all five changed backend modules. |
| Execution | PASS | 498 affected Python tests and 1181 frontend tests passed; build, asset references, i18n and repository-pinned pre-commit checks passed. |
| Evaluation | PASS | Tested error, replay, owner switch, stop, steer, empty thinking, long output and expanded state. Browser limitations stated below. |
| Handoff | PASS | Native update, three Function releases/timers, Identity and resource checks passed; actual uploaded wheel/source/public assets verified; commit/push receipt retained. |

## Contract and impact

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
|---|---|---|---|---|---|
| C01 | Start immediately displays the request and preparation; accepted request ID merges into subscription | App start flow and task hook | `App.tsx`, `useDevelopmentRun.ts`, `developmentRuns.ts` | Empty discovery clears the optimistic request; 1.5s discovery delay; stale owner/session response | R01 High |
| C02 | Current execution status belongs to the assistant/process row; generic busy never implies reasoning | Active transcript and composer | `DevelopmentProcess.tsx`, `Blocks.tsx`, `App.tsx` | Duplicate/misplaced status; false thinking indicator | R02 Medium |
| C03 | Native command actions, file changes and MCP names carry meaning; errors/duration/output survive | Protocol adapter, public payload and tool renderer | `codex_app_server.py`, `frontend_sandbox.py`, `intelligent_development_routes.py`, `sandbox.ts` | Failed command rendered successful; tool output lost; every action looks identical | R03 High |
| C04 | Empty reasoning start is visible; public summary parts remain separate from raw reasoning | Native notifications and thinking blocks | `_handle_notification`, `createSandboxProjection` | No thinking indicator until text arrives; duplicated raw/summary text | R04 Medium |
| C05 | Consecutive process items fold between assistant messages; expansion persists during updates and replay | Process grouping and stable item keys | `developmentPresentation.ts`, `DevelopmentProcess.tsx`, `Blocks.tsx` | Flicker, remount, hidden failures or lost expanded state | R05 Medium |
| C06 | Tool output/progress, plan, diff and meaningful thread status update their existing items | Runner, SSE and frontend projection | `runner.py`, `developmentRuns.ts`, `sandbox.ts` | Event loss/duplication; per-token whole-history render cost | R06 High |
| C07 | All new public content crosses redaction before persistence; user boundaries and stop intent remain enforced | Task text/output projection and task service | `output.py`, `repository.py`, `routes.py`, `useDevelopmentRun.ts` | Split credentials leak; cross-user data or interrupted request continues | R07 High |
| C08 | Rich process content remains usable with keyboard, Chinese IME, narrow layout and reduced motion | Built App and shared Block union consumers | `DevelopmentProcess.css`, `SandboxComposer.tsx`, `StudioConversation.tsx` | Overflow, keyboard-only disclosure inaccessible, premature submit, unsupported new Block | R08 Medium |
| C09 | Existing correct-account site receives the tested source and retains Identity, single instance and Sandbox bindings | Native `studio update`, main/scanner/worker/timers | Deployment receipts and actual uploaded wheel | Wrong account, changed shared Tool config, stale public assets | R09 High |

## Test portfolio

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
|---|---|---|---|---|---|---|
| R01 | Hook + actual observer + built App | Controlled HTTP race tests and Chromium | Slow create/connect; empty discovery; retry; owner switch; immediate seed | Request remains visible without a welcome frame; same request ID; no stale owner update | `useDevelopmentRun.test.mjs`, `developmentRuns.test.mjs`, `browser.json` | VERIFIED |
| R02 | Actual transcript | DOM + visual inspection | Preparing, thinking, MCP progress, recovery, stopped | Active process reflects actual event; composer remains input/control area | `developmentProcess.test.mjs`, screenshots | VERIFIED |
| R03 | Native protocol/public events/Block rendering | Contract + integration + browser | Read/list/search/file/MCP metadata; failed command; exit code; duration; live log | Native identity and failure retained; live log end is visible | `test_codex_presentation_events.py`, projection tests, expanded screenshot | VERIFIED |
| R04 | Native reasoning notification and projection | Regression tests + Chromium | Empty start; raw followed by multiple summary parts; final snapshot | Immediate “正在思考”; one public summary | Four observed backend RED cases → GREEN, projection regression | VERIFIED |
| R05 | Disclosure + projection | DOM updates and real keyboard interaction | Stream, completion, recovery, assistant split, hidden failure summary | Same disclosure node; manual expansion unchanged; failure visible when collapsed | `developmentProcess.test.mjs`, browser journey | VERIFIED |
| R06 | SSE and item projection | Packet replay and update tests | 100 text frames; duplicate seq; authoritative snapshots; plan/diff replacement | One packet causes bounded UI updates; one item per identity | `developmentRuns.test.mjs`, browser journey | VERIFIED |
| R07 | Streaming redaction, SQLite service, hook | Split-boundary, authorization, stop/race tests | Every secret split; tool vs assistant channel; ownership; stop during create/navigation; steer ack | No partial credential reaches public frames; no foreign data; stop remains effective | `test_development_run_output.py`, run service/repository/routes/runner tests, hook tests | VERIFIED |
| R08 | Browser and TypeScript union consumers | Chromium + build + composer DOM | 1440×960/820×900; long logs; keyboard disclosure; IME Enter; stop/steer; reduced motion | No page errors/overflow; input preserved; both renderers support diff | `browser.json`, 1181 frontend tests, TypeScript build | VERIFIED |
| R09 | Correct-account cloud resources and uploaded package | Native update, readback and HTTP byte comparison | Identity, bound tools, replicas, task DB, three functions/timers, source and assets | Existing URL live; expected resources unchanged; exact tested content deployed | `preflight.json`, `final.json`, `cloud-final.json`, `http-final.json` | VERIFIED |

## Executed evidence

Python: `PYTHONPATH=. /data00/home/wujiaming.ai/workspace/github/veadk-python/.venv/bin/python -m pytest` with the following affected paths:

- `tests/cli/test_codex_app_server.py`, `test_codex_presentation_events.py`, `test_frontend_sandbox.py`, `test_studio_update.py`
- `tests/frontend/server/test_development_run_output.py`, `test_development_runner.py`, `test_development_run_routes.py`, `test_development_run_service.py`, `test_development_run_shell.py`, `test_intelligent_development_runs.py`, `test_intelligent_development_routes.py`, `test_intelligent_development_source.py`, `test_intelligent_development_projects.py`, `test_sandbox_remote.py`

Result: **498 collected/executed/passed, 0 failed/skipped**. Five dependency deprecation warnings. Log: `/tmp/studio-ux-integrated-python.log`.

Frontend: `npm test`: **1181 collected/executed/passed, 0 failed/skipped**. Log: `/tmp/studio-ux-frontend-final.log`. `npm run build` passed TypeScript and both Vite bundles. `npm run test:webui-assets` verified **104 packaged files and 248 references**. `npm run check:i18n` verified **2 locales and 21 namespaces**. `uvx pre-commit run` passed repository-pinned Ruff check, Ruff format and Gitleaks with staged source, new modules, tests and assets.

The first affected Python run exposed an old test that expected raw reasoning to append to summary; its expected sequence was corrected to the newly declared protocol contract. Two old frontend exact-object assertions were updated to include retained item IDs and completion status. Their original content/order checks remain. New tests still demonstrate the originally observed failures. Browser harness locator/ack-timing mistakes were corrected; they are not counted as product passes.

The unpinned global Ruff invocation used unrelated ambient rules and reported pre-existing diagnostics; the actual repository-pinned pre-commit checks above passed. A Pyright check of the five backend presentation modules retained one identical baseline diagnostic in pre-existing Sandbox environment typing, with no new diagnostic after the duration type fix. The system Python lacks SQLite; the selected project interpreter was used for Python tests.

Browser evidence uses actual built Studio served locally and Chromium 1187, with controlled Sandbox/task HTTP responses to exercise slow startup, native event ordering and transport failure deterministically. The actual App, HTTP client, hook, SSE parser, projection, renderer and composer run without mocks. This is not a claim of a new real model build. Earlier real App Server/Sandbox interruption/recovery evidence remains separately documented in `recoverable-build-verification.md`.

Final browser observations: **4ms** from create response to event subscription; 28 startup samples retained the user request without a welcome frame; the user bubble remained at y=28px across preparation and execution; keyboard disclosure, retained expansion, 150-line live output, plan/diff, recovery, steer, stop and Chinese IME passed; **0 page errors**; **820px scroll width at an 820px viewport**. Screenshots were visually reviewed. The sampled delay is a local controlled measurement, not a cloud latency guarantee.

Evidence directory: `/data00/home/wujiaming.ai/workspace/reports/studio-build-ux-20260915/`, including `baseline-manifest.json`, `browser.json`, `preparation.png`, `initial-thinking.png`, `expanded-desktop.png`, `stopped-narrow.png` and cloud receipts. Browser script: `/tmp/studio-recoverable-browser/ux-journey.mjs`.

## Limits

Safari/Firefox and a real cloud network partition were not exercised for this UI change. Browser testing used Chinese and the existing light appearance; locale catalog parity and the normal suite passed, but this is not a full theme/locale visual matrix. Cloud Identity login and a new paid model build are not implied by public HTTP/resource verification. SQLite is intentionally local/ephemeral for six-hour task retention; the user accepted loss of task records when the single cloud instance is replaced. These limits do not weaken server-side owner authorization.


## Deployed result

Native `studio update` completed successfully for `veadk-studio-recoverable-0915` in Volcengine `cn-beijing/default`, account `2116711330`. Existing application `d7014d0f55f7` and URL `https://snm4e0bjff3hs4mdvnuh6.apigateway-cn-beijing.volceapi.com` were retained. Main Function `a7yabcrg` is revision **4**; scanner `ah049y3m` and worker `82flpzkg` are revision **2**, with their existing enabled minute timers verified. Min/max instances remain **1/1**. Identity pool/client, Dev Sandbox binding, six-hour SQLite settings and six shared Tool configurations were read back and verified.

The actual native wheel is `veadk_python-1.1.14.dev3+g6dcc022c4.d20260915-py3-none-any.whl`, SHA256 `6f00e60aff5d0327b64f8fcad1d4644f5e86da11f889a8b61471f6eee98b6d65`. Fourteen changed runtime Python files match the source byte-for-byte. Public HTML, entry JavaScript, CSS, logo and widget match this wheel; Identity redirect and unauthenticated access protection passed. Generated WebUI files committed with this change were taken from that exact uploaded wheel. The native builder sets its release metadata and produced a different entry hash from the earlier ordinary local build, so the actual native artifacts were also checked locally instead of treating an independently rebuilt bundle as uploaded evidence.

All Risk IDs R01–R09 are VERIFIED within the boundaries stated above. No material test gap is left unexplained; the browser/provider limits above still apply.
