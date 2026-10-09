# Preserve discovered A2A session routing

[中文版](2026-09-22-a2a-session-routing.zh.md)

## Metadata
- ID: `studio-a2a-session-routing`
- Date: 2026-09-22
- Status: implemented
- Component: [Studio Runtime Diagnostics, CON-9](../../../specs/studio-runtime-diagnostics/README.md)

## Evidence, goals and non-goals
The last clean committed frontend bundle at `ea1c384d` omitted MPA category/instance metadata when registering Runtime connections. Rebuilding current source preserves this metadata and selects native MPA routes even when discovery returned `a2a-default`. Isolated replay with identical connection input reproduced the switch. The affected Runtime's A2A card was available while native Profile status returned `500 JWT_PUBLIC_KEY is not configured`. This does not establish the exact bundle previously loaded in the user's browser.

Goal: preserve the discovered A2A session protocol and existing answer deduplication. Non-goals: cloud deployment, JWT configuration, authentication bypass, automatic error fallback, changing Profile management, or migrating session IDs across protocols.

## Requirements and design
- FR-1: A Runtime app exactly equal to `a2a-default` uses existing A2A create/list/read/delete/run even with MPA category or instance metadata.
- FR-2: Native MPA apps retain Profile initialization, native CRUD/run/SSE and execution-config preflight. Ordinary ADK apps are unchanged.
- FR-3: Chat execution-config preflight uses the same native-protocol predicate; A2A sends do not query native execution config. MPA product metadata remains available to the rail.
- FR-4: Errors, retry, cancellation and timeout stay on the selected protocol. No fallback after 401/403/500.

Pass the resolved app to the endpoint predicate and exclude the explicit A2A virtual app; reuse it through `isMpaRuntimeApp` for chat preflight. No persisted schema, backend route, credential, or extra discovery request changes. Existing per-run cancellation and terminal handling remain authoritative. Protocol selection is based on discovery, not error text.

## Tasks, files and acceptance
- T-1 / AC-1 (FR-1): add failing tests in `frontend/tests/runSseAbort.test.mjs` for restored MPA-tagged A2A create/list/read/delete/run.
- T-2 / AC-2 (FR-2, FR-3): update `frontend/src/adk/client.ts` and `frontend/src/App.tsx`; verify native preflight remains and A2A preflight is skipped.
- T-3 / AC-3 (FR-4): test errors/retry/abort without protocol fallback; run full frontend tests/build, asset checks and browser verification. Preserve dedup tests.
- T-4: reconcile bilingual contracts, `frontend/README.md`, generated `veadk/webui` assets and verification records.

## Review, risks and approval
2026-09-22: user approved the scoped protocol fix with “改下”. `review-spec` is unavailable; direct review covered auth preservation, protocol identity, restored connections, native compatibility, cancellation and bilingual equivalence; no blockers. Existing A2A history depends on the process-local BFF index. Restart clears that index; activation must account for cached HTML and active sessions. This change does not add history persistence. No cloud mutations or live model execution are implied by simulated tests.

## Verification
Implemented and verified as recorded below. Real-browser transport checks distinguish isolated responses from live Runtime access. Keyboard/IME and layout code are unchanged. No commit or push requested.

### 2026-09-22 verification record
Scope: current uncommitted protocol diff on top of the existing dedup changes.
- pass: new test-first suite reproduced 8 failures and 3 passes before the fix; all 11 pass after it. The chat preflight test executes the actual function extracted from App.tsx.
- pass: targeted protocol, run/abort and session-config tests: 38 passed.
- pass: `npm --prefix frontend test`: 1,272 Node tests and 25 Vitest tests passed.
- pass: `npm --prefix frontend run build` (includes TypeScript); existing chunk-size/import warnings remain.
- pass: `npm --prefix frontend run test:webui-assets`: 104 files and 248 internal references.
- pass: isolated real-browser fixture importing the actual client: A2A create/empty list/read/run/delete, loading/cancellation, visible 500 error and explicit retry, native MPA Profile/session creation. Responses are mocked; this is not live model verification.
- pass: targeted existing gitleaks pre-commit hook, including the generated app entry; `git diff --check`. Initial sandbox denial accessing uv cache was resolved with scoped execution permission, without changing global configuration.
- not_applicable: new Python checks, generated Python, harness-sidecar coverage, input/IME/layout changes: none changed in this fix. Existing earlier A2A backend checks are recorded in their own PRD.
- not_run: commit-time branch synchronization/all-files pre-commit; no commit requested. Live model generation was not performed.
- Local activation: `/index.html` is served from disk by the existing static fallback and loads the rebuilt entry without restarting the process. `/` retains its startup-cached entry until normal restart. No backend restart, cloud mutation, commit or push was performed.

- pass: authenticated actual Studio browser at `/index.html` loaded `index-1z730Cp-.js` and the MPA picker, using the existing local server and identity.
- pass: the first actual Studio connection attempt failed during Runtime discovery. Explicit UI retry succeeded: the selected app is `a2a-default`, a new session appears in history and the composer is available, with no JWT creation error. Live model generation remains not_run; streaming is covered by isolated browser/client tests.
- Final review: the only new production edits are the shared native-session predicate and chat preflight gate. MPA connection metadata, authentication and existing dedup changes are preserved. No blocker found in the code review; actual session creation passed after the explicit connection retry. No live model answer is claimed.
