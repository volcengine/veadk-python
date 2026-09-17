# MPA AgentKit P0 Browser Verification Runbook

- Status: `designed`; covers `VC-17`
- Chinese: [browser-cases.zh.md](browser-cases.zh.md)
- Evidence: `evidence/browser/<run-id>/<case-id>/`

## 1. Shared environment

- M0 adds `scripts/run-mpa-p0-browser-fixture.sh`, accepted only with `APP_ENV=test`, `VEADK_MPA_TEST_SCENARIOS=1`, and loopback bind; otherwise startup fails.
- Test API: `GET /__test/mpa/scenarios`, `PUT /__test/mpa/scenarios/{name}`, `GET /__test/mpa/scenarios/{name}`, `POST /__test/mpa/scenarios/{name}/calls/{call}`, and `POST /__test/mpa/scenarios/{name}/barriers/{barrier}/release`. These routes do not exist in production routing.
- Scenarios: `create_success`, `profile_apply_failed`, `smoke_worker_not_ready`, `smoke_output_mismatch`, `cleanup_failed`, `runtime_missing`, `binding_ambiguous`, `orphan_runtime`, `old_runtime`, `session_revision_6`, `cursor_expired`, `slow_scope_switch`, `turn_lifecycle`. S4-07 implements the `turn_lifecycle` participant barriers, control/continue routes, call counts, and state evidence used by BC-09.
- Start: caller first runs `umask 077; VEADK_MPA_SCENARIO_TOKEN=$(openssl rand -hex 32); printf '%s' "$VEADK_MPA_SCENARIO_TOKEN" > .gstack/<run-id>-scenario.token`, verifies `scripts/run-mpa-p0-browser-fixture.sh` exists and the token file is mode `0600`, then starts `APP_ENV=test VEADK_MPA_TEST_SCENARIOS=1 VEADK_MPA_SCENARIO_TOKEN_FILE=.gstack/<run-id>-scenario.token scripts/run-mpa-p0-browser-fixture.sh --host 127.0.0.1 --port 8000`. Delete token/state files at the end; token never enters logs or evidence.
- Browser: `B=$HOME/.claude/skills/gstack/browse/dist/browse`; A runs `env BROWSE_STATE_FILE=.gstack/<run-id>-a.json $B ...`; B runs `env BROWSE_STATE_FILE=.gstack/<run-id>-b.json $B ...`. Both separately open the fixture Studio URL with the test login state required by the mounted fixture; assert equal principal hashes while cookie/localStorage/sessionStorage remain isolated.
- Test API reads the token from `VEADK_MPA_SCENARIO_TOKEN_FILE`. Command template: `curl -fsS -H "Authorization: Bearer $(<.gstack/<run-id>-scenario.token)" -X PUT http://127.0.0.1:8000/__test/mpa/scenarios/create_success -H "Content-Type: application/json" --data '{"barriers":[]}'`; use `GET /__test/mpa/scenarios/{name}` for state, `POST /__test/mpa/scenarios/{name}/calls/{call}` for call counts, and `POST /__test/mpa/scenarios/{name}/barriers/{barrier}/release` to release barriers. The seed response must return exact `barriers{}` state. Use the same Header for every test API request.
- Common browser commands: each side uses its own `BROWSE_STATE_FILE` to run `goto http://127.0.0.1:8000`, `snapshot -i -a -o <path>`, `console --errors`, `network`, and `viewport <WxH>`. Reset/seed before each Case; save call counts and reset afterward.

## BC-01: creation and refresh recovery (`AC-1`, `AC-8`)

- Preconditions: seed `create_success`; record client idempotency key.
- Steps: create from tab/header/empty state; at runtime/profile/smoke stages run `$B reload` and `$B snapshot -D`.
- Input: same minimum Profile and region, three source values.
- Expected: every intent has `category=mpa`; POST is 202; refresh recovers via operation ID/active list; every resource effect count is one; runnable/chat only after cleanup.
- Evidence: `BC-01/{tab,header,empty,refresh}.png`, `network.txt`, `call-counts.json`.
- Failure: duplicate resource, lost operation, or early runnable is `fail`.

## BC-02: creation failures and retry (`AC-8`)

- Preconditions: seed each of `profile_apply_failed`, `smoke_worker_not_ready`, `smoke_output_mismatch`, `cleanup_failed`.
- Steps: create, wait for failure, screenshot, click retry, read and release every `barriers[]` item returned by that scenario's seed response, and await terminal.
- Input: same Profile and persistent idempotency key.
- Expected: safe error/stage/retry; chat disabled; retry resumes safely; effect count unchanged.
- Evidence: `BC-02/<scenario>-before.png`, `after.png`, network/call-counts.
- Failure: early runnable, secret leak, or duplicate effect is `fail`.

## BC-03: Agent detail and versions (`AC-8`, `AC-10`)

- Preconditions: seed `runtime_missing`, `binding_ambiguous`, `orphan_runtime`, `old_runtime`, then normal single binding.
- Steps: open list/detail/versions, snapshot, assert button enabled/disabled state.
- Input: same ID in different scopes and target/applied mismatch.
- Expected: 0/1/N/orphan/unsupported follows `MpaAgentView`; versions come from AgentKit; no GitHub delivery/generic draft/evaluation/optimization; no secret.
- Evidence: `BC-03/<scenario>.png`, console/network, view JSON.
- Failure: binding error, wrong write entry, or cross-scope data is `fail`.

## BC-04: two-client CAS (`AC-3`, `AC-8`)

- Preconditions: seed `session_revision_6`; A/B separately authenticate as the same user; record identical principal hash, Session ID, and ETag 6.
- Steps: A/B submit model/Skill PATCH. The fixture uses barriers `config-patch-a` and `config-patch-b`; after both call counts equal one, release them in order through the authenticated barrier API.
- Input: both requests explicitly carry ETag 6.
- Expected: one 200/revision 7 and one 412; loser renders authority and requires explicit retry; both converge.
- Evidence: `BC-04/context-{a,b}.png`, two network transcripts, barrier/call-count.
- Failure: different principal, requests not both on revision 6, or silent overwrite is `fail`.

## BC-05: explicit Session upgrade (`AC-3`, `AC-8`)

- Preconditions: Session pins N, N+1 is applied, and an active Turn fixture exists.
- Steps: verify only “new version available”; click upgrade; inspect active and next Turns.
- Input: target N+1, current ETag, persistent idempotency key.
- Expected: active Turn stays N; next Turn uses N+1; override/clear retained and inherit updated; invalid target fails atomically.
- Evidence: `BC-05/{before,active,next,error}.png`, revision transcript.
- Failure: automatic upgrade or active-Turn hot switch is `fail`.

## BC-06: streaming refresh and cursor (`AC-7`, `AC-8`)

- Preconditions: controlled stream fixture plus `cursor_expired`.
- Steps: record cursor K, refresh, wait terminal; then use unknown cursor.
- Input: text/usage/artifact/terminal with persistent/live overlap.
- Expected: only events after K; every kind counted once; unknown cursor shows recovery and never success.
- Evidence: `BC-06/{before,after,expired}.png`, SSE JSONL, count JSON.
- Failure: duplicate, missing, or false-success state is `fail`.

## BC-07: keyboard, IME, and narrow view (`AC-8`)

- Preconditions: seed `create_success`; Chinese Pinyin IME; viewports `1440x900`, `1024x768`.
- Steps: Enter during composition, Enter after compositionend, repeated Enter/click while busy; Tab/Shift+Tab; long name/operation/error.
- Input: Chinese text and long safe fixture.
- Expected: no submit during composition, one after; one operation while busy; visible focus; no overlap/horizontal overflow and primary action reachable.
- Evidence: `BC-07/{desktop,narrow,ime-steps}.png`, call-count, OS/browser/IME versions.
- Failure: duplicate submit, unreachable action, or overlap is `fail`.

## BC-08: identity and cache isolation (`AC-6`, `AC-8`)

- Preconditions: seed `slow_scope_switch`; two user/Agent/region fixtures.
- Steps: switch scope while old response waits, release barrier, inspect page/cache; issue denied request.
- Input: same resource ID under different principals/scopes.
- Expected: stale response cannot overwrite; caches isolated; denied reveals no existence, ID, or secret.
- Evidence: `BC-08/{before,after,denied}.png`, storage, network, call-count.
- Failure: cross-scope data or secret leak blocks release.

## BC-09: pause, resume, and explicit continuation (`AC-5`, `AC-8`)

- Preconditions: seed `turn_lifecycle` with primary plus two workers, partial/full ACK, recoverable, and new-turn-required fixtures.
- Steps: pause, release one/all participant barriers, resume; seed timeout and click continue; observe counts during refresh/poll timeout.
- Input: same Session/Turn and stable control/continue idempotency keys.
- Expected: `running -> pausing -> paused -> resuming -> running`; partial ACK is not paused; new-turn-required only shows explicit continue; refresh/poll timeout never creates a Turn; repeated continue creates one linked Turn.
- Evidence: `BC-09/{running,partial,paused,resumed,continue}.png`, control/continue network and participant/call-count JSON.
- Failure: false paused, automatic continue, or duplicate linked Turn blocks release.

## 2. Exit

BC-01 through BC-09 pass with no unhandled console error; each runs `snapshot -a`, `console --errors`, and `network` and saves under `evidence/browser/<run-id>/<case-id>/`. A slice may execute its own BC subset, but only the S5 full regression can mark `VC-17=pass`. If gstack/Chromium or scenario harness is unavailable, `VC-17/AC-8=blocked`; Node tests cannot replace it. Finally reset scenarios, stop A/B through their run-specific state files, stop the fixture service, delete both state files and the token file, and verify zero test resources.
