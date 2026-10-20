# Recoverable intelligent-build verification

Comparison base: `d2ce736821052de81602b422669ae7b5e82430a6` (`origin/main` at branch creation). Branch: `feat/studio-recoverable-build`. Verification date: 2026-09-15. No commit, push, PR, or production deployment is part of this handoff.

## Gate Status

| Gate | Status | Evidence or blocking reason |
|---|---|---|
| Change Basis | PASS | Isolated worktree; tracked changes and new source/test files inspected; original checkout left intact. |
| Contract | PASS | Task lifetime, native execution, ownership, retained output, Stop/Steer and expiry contracts below. |
| Impact | PASS | R01–R10 cover execution, data, native APIs, publication, UI and packaged consumers. |
| Portfolio | PASS | SQLite integration, native adapter contracts, subprocess fault tests, DOM/hook tests and real Sandbox/browser journeys. |
| Baseline | PASS | 258 baseline tests; recorded failures for recovery, output, lifespan and version retry; comparison-base type checks. |
| Execution | PASS | Backend/frontend suites, build, native final-state checks, browser journeys and scans executed. |
| Evaluation | PASS | State/side-effect oracles verified; unexecuted environments and pre-existing diagnostics identified below. |
| Handoff | PASS | All Risk IDs have a final status; configuration, evidence and operational limits are documented. |

## Change Basis

The accepted design uses short-term local SQLite for task state and event replay, with no TOS task storage. Existing immutable source-project storage remains independent. The implementation targets one Studio instance, multiple authenticated users and Codex App Server 0.154.0. SQLite's directory must survive Studio restarts.

The worktree contains backend task/repository/runner/control changes, the existing Sandbox and Codex adapters, Studio composer/observation/notification integration, tests, image pins, documentation and matching `veadk/webui` artifacts. Unrelated modifications in the original checkout were not copied or changed.

Commands were discovered from `AGENTS.md`, `frontend/SPEC.md`, package scripts, `.pre-commit-config.yaml` and CI. The executable Python is `/data00/home/wujiaming.ai/workspace/github/veadk-python/.venv/bin/python` (3.12); the system Python has no SQLite support. Browser checks use Chromium 1187 and temporary Playwright tooling outside the repository. No dependency was added for task storage or browser verification.

## Observable Contracts

| Change ID | Old behavior | New behavior | Inputs/outputs/state | Side effects | Error modes |
|---|---|---|---|---|---|
| C01 | HTTP/SSE request owned build execution | Background run survives subscriber loss and process restart | Durable run, input revision, events, checkpoints and lease | Reattach exact native thread/turn | Recovery status; unresolved state waits for user without discarding output |
| C02 | Some environment access depended on local connection state | Fresh owner-scoped environment resolution | Authenticated owner is required for run operations | Only authorized environment receives native calls | Foreign IDs return 404; no admin ownership bypass |
| C03 | Stream errors appeared as stopped/failed tasks | Native retry/reconciliation distinguishes connection loss from terminal execution | `thread/resume`, turn history/read, native `willRetry` | Resume observation; bounded continuation only after a confirmed terminal turn | Ambiguous acceptance is never blindly resent |
| C04 | Stop was coupled to stream cancellation; sending while busy was disabled | Independent durable Stop and native Steer | Requested and confirmed stop differ; ordered input revisions | `turn/interrupt`; `turn/steer` with expected turn | Stop remains pending until confirmed; ambiguous Steer is reconciled |
| C05 | Publication identifiers could change after retry | Deterministic delivery/version identity and remote receipt | Fixed IDs, digest checks, resumable publication stage | Existing successful effects are reused | Conflicting artifact digest is rejected; old retry cannot rewind binding |
| C06 | Error could clear partial browser output | Append/replay by sequence and native item identity | Rich blocks retained across error, navigation and refresh | Short-term SQLite event writes | Missing/gapped stream reconnects; terminal expiry is explicit retention behavior |
| C07 | Navigation lost task visibility | Global owner-scoped task notice and return action | Editable composer, separate Stop, accepted/queued input feedback | Navigation detaches only | Stale owner/session callbacks cannot overwrite the active view |
| C08 | No durable short-term run lifecycle | Terminal retention defaults to 6 h, max active life 8 h | Configurable local DB/retention/lifetime; active work is not TTL deleted | Expired terminal rows cleaned; overdue work gets durable Stop | Per-user/global/input/event limits reject excess admission safely |
| C09 | Image used an older Codex binary | Runtime pinned to 0.154.0 | x64 and arm64 asset digests and executable member paths | Image installer uses pinned binary | Checksum/member validation; actual x64 binary version verified |
| C10 | Existing `/messages` and rich Sandbox consumers | Compatibility adapter delegates to durable task service | Existing delivery/usage/activity consumers remain | Matching bundled frontend | Terminal run status replaces request-level failure for recoverable tasks |

## Change Impact Traceability

| Change ID | Changed contract | Affected surface | Repository evidence | Failure mode | Risk |
|---|---|---|---|---|---|
| C01 | Detached execution and restart | Studio lifespan, scheduler, SQLite leases | `intelligent_development_runs/service.py`, route lifespan wrapper | Restart leaves work unobserved or starts duplicate worker | R01 High |
| C02 | User isolation and redaction | Run APIs, session resolver, SQLite and event output | `routes.py`, owner-qualified repository queries, `output.py` | Cross-user read/control or credential exposure | R02 High |
| C03 | Native reconciliation | `codex_app_server.py`, runner | Exact association, native status precedence and client-message correlation | Duplicate start, wrong thread, premature completion | R03 High |
| C04 | Stop/Steer races | Runner control loop, repository inputs, hook/composer | Durable stop before interruption; expectedTurnId | Stop lost on refresh; duplicate/misrouted input | R04 High |
| C05 | Resumable publication | RunShell, DeliveryPublisher, project service | Remote lock/started marker/receipt; deterministic version | Repeat external operation or rewind version binding | R05 High |
| C06 | Output preservation | Text projection, event storage and rich renderer | Stable suffix deltas; snapshot upsert; cursor validation | Cleared/duplicated output, split-secret leak, quadratic storage | R06 High |
| C07 | Task UI and identity | App, useDevelopmentRun, DevelopmentTaskNotice, SandboxComposer | Owner/session guards; existing Toast/Button | Wrong user's transcript; disabled interruption; layout overlap | R07 High |
| C08 | Retention and capacity | Repository admission/cleanup and scheduler | Limits, active/waiting lifecycle, WAL | Delete live work, unbounded growth, stale lease writes | R08 Medium |
| C09 | Codex version | Sandbox image assets and installer | Pinned asset URLs/digests and native schema | Installer failure or unavailable native control API | R09 Medium |
| C10 | Existing consumers | Source preview, legacy messages, ordinary Sandbox, packaged assets | Affected Python/frontend suites and build | Break deployment/source access, IME, imports or bundle references | R10 Medium |

## Test Portfolio Traceability

| Risk ID | Boundary | Method | Cases | Oracle | Evidence | Status |
|---|---|---|---|---|---|---|
| R01 | Actual SQLite + service lifespan + real Studio | Integration and process fault injection | Disconnect, shutdown, hard restart, lease takeover, custom lifespan | Same run/thread/turn completes; no duplicate native turn | Service/repository/routes tests; clean live run 5 | VERIFIED |
| R02 | HTTP owner resolution + real DB + streamed text | Authorization and sensitive-data fault cases | Foreign list/read/stream/stop/steer/delete, replay, split secret and credential rotation | No cross-owner content/effects; secrets absent from stored/public events | Run API/repository/output tests; secret scans | VERIFIED |
| R03 | Codex wire adapter and runner | Contract/fault injection + native live execution | Lost start response, `willRetry`, history pagination, inProgress commentary, exact attach | No resend of unknown input; explicit native status wins | Codex tests; runner unknown-submission cases; live run 5 | VERIFIED |
| R04 | DB/control/native API + browser | Race tests, DOM/hook tests, native interruption | Stop during submit/navigation, pending Steer withdrawal, late ack, same-turn Steer | Accepted intent persists; native turn interrupted; retained output | Runner/repository/hook/composer tests; live runs 4–6 | VERIFIED |
| R05 | Real subprocess wrapper + project service | Lost-response/stop fault tests and storage failure injection | Duplicate wrapper, delayed submission, process-group stop, commit/binding failure, old retry | Side effect once; receipt authoritative; one version; latest binding preserved | `test_development_run_shell.py`; project service regression | VERIFIED |
| R06 | Backend and browser projection | Stream/property-size tests and live replay | Split tokens, commentary snapshot, late ack, sequence gap/duplicate, reconnect | Exact content retained, same item upserted, linear event growth | Output/frontend projection tests; live before/after SSE and screenshots | VERIFIED |
| R07 | Actual React hook/composer and Chromium | DOM, race integration, visual/interaction review | IME Enter, steer while running, sending/stopping, error/resume, refresh, navigation | Correct callback/disabled behavior, no stale identity update, no overlapping task notice | Hook/composer tests; browser journeys | VERIFIED |
| R08 | SQLite/time boundaries | Integration with controlled clock and limits | Terminal TTL, waiting/active retention, admission limits, lease expiry, finish/stop race | Live records retained; excess work rejected; expired writer fenced | Repository and service tests | VERIFIED |
| R09 | Actual archives/binary and installed SDK | Checksum/member/response-contract validation | x64/arm64 downloads, x64 version, native SetSessionTtl response | Digests and members match; binary 0.154.0; returned expiry used | Image validation; renewal contract; actual managed DevEnv | VERIFIED |
| R10 | Transitive consumers/build pipeline | Affected suite, full frontend suite, static/build checks | Source access/integrity, compatibility delivery, composer consumers, packaged imports | Assertions pass; no new type diagnostics; all asset references resolve | 549 Python tests; 1173 frontend tests; build/assets/Ruff/Pyright | VERIFIED |

## Baseline Evidence

The original affected baseline passed 258 tests (`/tmp/studio-recoverable-build-baseline.xml`). Observed RED→GREEN cases include unsent Steer incorrectly acknowledged during resume, withdrawn input resurrection, status cursor mismatch, identity collisions after message redaction, cumulative-output quadratic growth, native `inProgress` commentary incorrectly treated as terminal, and a custom Studio lifespan that did not start the recovery scheduler.

Additional executed regressions found during completion: first deterministic version lookup caught the wrong NotFound subtype; a late retry could rewind the binding to an older version. The first failed in `/tmp/studio-runs-persistence-renewal-red.log`, the second in `/tmp/studio-runs-persistence-order-red.log`; the retained service test now passes.

Live run 1 required a manual correction to pre-fix test data and is **not** evidence of uninterrupted recovery. Live run 2 exposed the lifespan issue. Clean live run 5 was created after these fixes, forcibly interrupted only at the Studio process, automatically resumed and completed without editing its task data. Run 4 independently confirmed real native interruption after a browser Stop.

## Execution Result

Commands below run from the worktree unless `frontend/` is stated. `$PY` denotes the venv Python described above.

| Command | Collected | Executed | Passed | Failed | Skipped | What it proves |
|---|---:|---:|---:|---:|---:|---|
| `$PY -m pytest` with the affected files listed below, `-q --tb=short --junitxml=/tmp/studio-runs-full-impact-final.xml` | 549 | 549 | 549 | 0 | 0 | Backend impact scope and image runtime helpers |
| Final focused project-retry and native-renewal tests after test typing cleanup | 2 | 2 | 2 | 0 | 0 | Typed fixtures retain the same runtime assertions |
| `cd frontend && npm test` | 1173 | 1173 | 1173 | 0 | 0 | Full existing frontend test suite including new hook/DOM/projection cases |
| `cd frontend && npm run build` | — | 1 | 1 | 0 | — | TypeScript and both Vite production bundles |
| `cd frontend && npm run test:webui-assets` | — | 1 | 1 | 0 | — | Packaged file/reference validation |
| `uv tool run --from ruff==0.11.12 ruff check --config pyproject.toml $(cat /tmp/studio-changed-python.txt)` | 27 files | 27 | 27 | 0 | 0 | Changed Python lint |
| `uv tool run pyright --pythonpath "$PY" $(cat /tmp/studio-changed-python.txt)` and comparison-base run | 27 files | 27 | — | 75 existing diagnostics | 0 | No added diagnostics; see comparison record |
| Repository-configured Gitleaks; additional default-rule scan including tests and bundles | — | 2 | — | 0 credential findings | — | Repository scan clean; supplemental scan has one verified vendor-code false positive |
| Source-only `git diff --check` | — | 1 | 1 | 0 | — | No whitespace errors in maintained source |
| Prettier Markdown parser over the three changed Markdown files | 3 | 3 | 3 | 0 | 0 | Markdown parses; README/report link targets resolve |

The Python impact command includes:

```text
tests/frontend/server/test_intelligent_development_routes.py
tests/frontend/server/test_intelligent_development_task.py
tests/frontend/server/test_intelligent_development_projects.py
tests/frontend/server/test_intelligent_development_source.py
tests/frontend/server/test_intelligent_development_runs.py
tests/frontend/server/test_development_runner.py
tests/frontend/server/test_development_run_routes.py
tests/frontend/server/test_development_run_output.py
tests/frontend/server/test_development_run_service.py
tests/frontend/server/test_development_run_shell.py
tests/frontend/server/test_sandbox_remote.py
tests/cli/test_codex_app_server.py
tests/cli/test_frontend_sandbox.py
tests/cli/test_frontend_sandbox_options.py
tests/cli/test_frontend_sandbox_proxy.py
tests/cli/test_studio_sandbox_tools.py
frontend/sandbox-image/tests/test_runtime.py
```

No cases were skipped/deselected in this selected command. One existing Starlette/AnyIO deprecation warning was reported. Initial 62 backend failures were traced to 61 obsolete source-preview fakes using the old session interface and one old commentary event assertion; the fake interface was migrated while retaining ownership/archive/integrity checks, and the assertion was migrated to the single-item text projection. Two additional hook regressions cover losing both the initial submission and Stop response, and losing a deferred Stop after submission acceptance. Before the fix they permanently locked submission or left Stop disabled. They now permit retry while retaining the input request ID and its Stop intent (`/tmp/studio-runs-stop-retry-red.log`, `/tmp/studio-runs-stop-deferred-red.log`, and the final frontend suite). The initial composer DOM failure was an incomplete translation mock. Subsequent source-consumer assertions were updated after removal of the unreachable request-owned intelligent-build path. These failures were investigated, not retried away.

## Coverage and Oracle Quality

This is an affected-scope verification, not a claim that the entire Python repository or every cloud provider was tested. The repository's unrelated sidecar coverage gate does not apply to this task path; no new coverage percentage was invented. Core failure modes have state and side-effect assertions, including exact native turn association, publication count, owner-qualified access, stop confirmation, event ordering and output size. Reintroducing those defects fails the corresponding retained regressions.

The final Pyright run reports 75 diagnostics, identical to the comparison base by file, source statement and diagnostic message. `/tmp/studio-runs-pyright-comparison.json` records zero added/removed diagnostics. Seventy-four are existing dynamic-test typing issues; one is the unchanged `envs` request boundary in `frontend_sandbox.py`. New task package code has no type diagnostics. Full TypeScript compilation passes.

Gitleaks with repository configuration found no leaks. The supplementary scan deliberately included normally excluded tests and generated bundles. Its single hit is a minified editor selection expression accessing `anchor.key` and `focus.key`, with no string literal; the identical expression exists in the base bundle. No scanner rule or allowlist was relaxed. Raw scan output is redacted.

Generated `website-integration.js` contains grammar strings with embedded whitespace; source-only diff checks pass. Generated bundles are validated through the production build and asset-reference verifier, without modifying third-party grammar strings.

## Cross-Boundary and Non-Functional Evidence

The real Tool is `t-yev5151m9stkidoa8h58` (`studio-recoverable-20260915-dev`), an independent Ready DevEnv in cn-beijing with snapshots disabled. No existing Tool was modified. The dedicated session is `s-yev51pzx8gzn6n5in25b`, owned by the local verification identity. Studio listens only on `127.0.0.1:18080`. No credentials or authenticated endpoints are included in this report. A separate local user was also tested against the running Studio: its task list was empty, and run detail, event replay, Stop, Resume, Steer and delete all returned 404. Receipt: `/tmp/studio-recoverable-live/owner-isolation-receipt.json`.

Clean run 5: `2801807c67bc48ba92a55585f73809fc`; native thread `01a0a4a9-f8c4-7303-b3f0-b626ce9cf84e`; turn `01a0a4c7-43ff-7fe0-a4ed-acb1499c8dff`. It survived a SIGKILL of Studio while an actual `sleep 180` command was active, was reclaimed after the SQLite lease expired, accepted Steer in the same native turn, and completed successfully. One native turn and two delivered inputs were recorded. Output markers before and after restart remain replayable. Receipt: `/tmp/studio-recoverable-live/restart-receipt.json`.

Final run 6 (`b9bfa8a1364f479f8d3dff9762bd0f38`) was stopped from the Chinese browser UI. Studio reached `cancelled`; an independent App Server read confirmed native turn `01a0a4cc-ade6-7e43-ab2d-ef56d1fec2eb` was `interrupted`. The same verification independently confirmed run 5 was `completed` and the remote binary was `codex-cli 0.154.0`. See `/tmp/studio-recoverable-live/native-final-receipt.json`. The browser retained earlier output and an unsent IME draft, recorded zero page errors and no horizontal overflow at 820×900. Screenshots: `/tmp/studio-recoverable-browser/final-zh-stopped-desktop.png` and `final-zh-stopped-narrow.png`.

Native shell tests execute the remote wrapper locally as real subprocesses and verify command effects are not repeated after a lost response, delayed submission cannot bypass Stop, and stopping a running command terminates its process group and writes a receipt. SQLite tests verify bounded admission and event retention. A size regression ensures text storage grows linearly rather than storing every cumulative prefix.

Both Codex archives match their pinned checksums and installer member paths. The x64 executable reports `codex-cli 0.154.0`; the managed DevEnv also reported 0.154.0. The arm64 executable was inspected, not executed on this x64 host. Native SDK models and the SetSessionTtl request/response were exercised in a contract test; the live session was not near expiry, so real control-plane renewal was not induced.

## Frontend Verification

The main Studio canvas uses the existing light theme, including when the operating system prefers dark mode. The composer, rich-block renderer, Toast and Button are reused; no new visual shell or design system was introduced. Desktop and narrow-window checks assess readable wrapping, separate accessible Stop/Steer actions and disappearance of the off-page task notice when opening its conversation.

| Surface or consumer | State and data | Viewport or runtime | Method and oracle | Executed evidence | Result |
|---|---|---|---|---|---|
| Task composer | Running, sending, stopping, error, resume, IME | React/JSDOM | IME Enter does not send; Enter/Steer sends once; independent Stop remains available | `developmentComposer.test.mjs` | PASS |
| Task hook | Submission/Stop/navigation/identity races | React/JSDOM | Request ID reused on ambiguous failure; old callback cannot overwrite current user/session | `useDevelopmentRun.test.mjs` | PASS |
| Task replay | Duplicate/gap/late ack/commentary | Node projection integration | Stable item IDs and exact sequence produce retained nonduplicated blocks | `developmentRuns.test.mjs` | PASS |
| Active build | Reconnected native turn and old output | Chromium, en-US, 1440×960 | Marker survives navigation/reload, editable input, no overlapping task notice | `final-running-desktop.png`, restart browser receipt | PASS |
| Active build | Narrow viewport, long Chinese content | Chromium, 820×900 | Text and controls wrap without overlap/horizontal clipping | `final-running-narrow.png` | PASS |
| Stop | User requests native interruption | Real Sandbox + Chromium | Backend cancelled and native interrupted; preceding text retained | Run 4 and run 6 native receipts; final Chinese screenshots | PASS |

The first final-browser attempt loaded a blank page because the local Studio process cached HTML before the final asset rebuild. The existing server loads its entry HTML at startup; restarting that local process after the completed build resolved the test-environment mismatch. The native stop verifier was initially invoked before this browser could submit Stop and correctly rejected the still-running turn. These failed attempts are not counted as passing Stop evidence.

Playwright is temporary tooling in `/tmp/studio-recoverable-browser`; screenshots and receipts stay outside source. These are visual inspections, not a pre-existing screenshot-diff baseline. Safari/Firefox, a full arm64 runtime, multi-instance deployment and actual cloud-region outages were not executed; related uncertainty remains bounded by protocol/DOM tests and the single-instance support boundary.

## Residual Risk

| Risk ID | Inherent level | Executed evidence or control | Remaining uncertainty |
|---|---|---|---|
| R01, R03 | High | Clean hard-restart/live same-turn recovery and native contract tests | Recovery needs the retained SQLite directory and recoverable remote workspace/thread |
| R02 | High | Owner-scoped API/SQL tests and credential-safe event projection | Local-mode identity headers assume a trusted loopback/dev deployment; production uses existing authentication |
| R04 | High | Durable intent, race tests and native interruption | A disconnected environment cannot confirm stop immediately; UI says confirmation is pending |
| R05 | High | Remote receipt/lock and deterministic version reconciliation | Native correlation IDs are not remote idempotency keys; arbitrary agent side effects cannot be promised exactly once |
| R06, R07 | High | Backend/client projection tests, hook/DOM tests and live replay | Refresh after configured terminal retention expires does not restore deleted short-term history |
| R08 | Medium | Admission/TTL/lease/finish race tests | No production-scale load benchmark; one Studio instance only |
| R09 | Medium | Archive verification, SDK renewal contract, real x64 DevEnv | No full image rebuild, arm64 execution, or induced live TTL renewal |
| R10 | Medium | Affected suites, build/assets and comparison-base static checks | Existing Python type diagnostics and upstream build size/deprecation warnings remain |

No impact severity is reduced merely because tests pass. Definite integrity or environment-loss failures remain terminal; recoverable and uncertain failures preserve output and offer continuation. SQLite fencing prevents stale local writes and does not claim globally exactly-once native effects.

## Handoff

Implementation and verification are complete within the scope above. R01–R10 are VERIFIED against the stated boundaries. Operational usage and configuration are documented in [README.md](README.md). The supported deployment is one Studio instance with a retained local SQLite directory and multiple isolated users. Existing Python type diagnostics remain unchanged. No High risk is blocked, and unexecuted environments are listed as residual uncertainty. No commit or push was made.

Final evidence logs: `/tmp/studio-runs-full-impact-final.log`, `/tmp/studio-recoverable-frontend-tests-final6.log`, `/tmp/studio-recoverable-frontend-build-final5.log`, `/tmp/studio-recoverable-assets-final3.log`, `/tmp/studio-runs-pyright-final2.log`, `/tmp/studio-runs-pyright-comparison.json`, and `/tmp/studio-recoverable-browser/final-stop-browser3.log`. The packaged verifier checked 104 files and 248 internal references. The Markdown files are repository READMEs/report rather than MDX site pages; no site-wide Next.js build was necessary.
