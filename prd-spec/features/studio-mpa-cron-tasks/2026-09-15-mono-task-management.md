# Runtime task management aligned with mono

[中文版](2026-09-15-mono-task-management.zh.md)

Change ID: studio-mpa-cron-management. Created/revised: 2026-09-15. Status: implemented.
Component: [Runtime task viewer](../../../specs/studio-mpa-cron-tasks/README.md).

## Evidence and intent

The user requests the Studio Runtime task page match the supplied mono screenshot and implementation. Studio currently exposes only task listing through `frontend/server/mpa_cron.py`. Mono's `SharedAgent/Cron/index.tsx` uses `CronStandalonePanel`; `packages/claw-cron/src/components/` owns list, calendar, form, detail and actions. Its workspace dependencies prevent a simple standalone import into Studio. Reuse its observable behavior and field mapping with Studio's existing UI primitives, without modifying mono.

MPA commit `91fd6a3` restores user-scoped reads. All existing `/api/v1/esa-cron-tasks` operations require user identity even with JWT disabled. No JWT acquisition or all-user fallback is authorized. The approved identity source is the authenticated Studio principal.

## Requirements and scenarios

- FR-1: Selecting a Runtime shows its name/region and a list/calendar switch. The list is the focal point: task, last execution, schedule, last status with filter, executing Agent and actions. Use the supplied white/neutral surface, restrained blue links, green success, muted pending and red failure states, existing system typography and Studio tokens. Place compact overview metrics above the table and creation at top right; avoid dashboard metric cards and raw schedule JSON as the primary view.
- FR-2: Create, edit, copy, delete, enable/disable and run now use existing MPA endpoints. Copy opens a prefilled form and creates only on save; delete requires confirmation. Name opens task detail and paginated execution history. Failed writes keep form input and display actionable errors.
- FR-3: Calendar follows mono's schedule semantics and timezone handling, including one-shot and recurring tasks. It must load all required server pages and never present a single page as a complete calendar. The last execution column uses the last execution timestamp, never nextRunAt.
- FR-4: Use the selected Runtime's server-resolved endpoint and gateway key. Add only allowlisted task routes. Keep credentials out of the browser. JWT-enabled Runtime errors remain errors; do not restore TOP/JWT flows or widen MPA permissions.
- FR-5: Preserve expectedVersion on updates and clientToken on retries of the same create/run operation. Prevent duplicate submits; show version conflicts and allow refresh. Runtime changes abort reads and discard stale results; an aborted write must not be reported as undone.
- FR-6: Handle loading, empty, auth, validation, missing endpoint, network and conflict states distinctly. Calendar/list, menus, dialogs and forms support keyboard, Escape, focus restoration, IME and narrow windows. No cloud task is created, executed or deleted solely for UI verification.

## Contract impact and implementation

T-1 / FR-4: Resolve the identity decision and revise the paired component spec. Extend `frontend/server/mpa_cron.py` and CLI route wiring for list/create/update/delete/run/history using existing Runtime authorization. Do not expose an arbitrary upstream URL or generic proxy.

T-2 / FR-2, FR-5: Extend `frontend/src/adk/mpaCronTasks.ts` and client wrappers with typed task/run responses, scheduling fields, versions and mutation requests. Preserve unknown delivery settings on edits. Do not assume mono TOP response casing or its unpaginated API matches MPA REST.

T-3 / FR-1, FR-3, FR-6: Split the existing Runtime view into focused list/actions, calendar, editor and detail components as needed. Reuse Studio controls/tokens and compare each view with mono. Metrics must reflect their actual server time window; do not label them seven-day statistics without evidence.

T-4: Add regression/interaction and proxy contract coverage, update bilingual docs and frontend README, regenerate webui, install into local Studio and perform browser checks. Keep existing Studio/TOS tasks and session behavior unchanged.

## Acceptance and verification

- AC-1 / T-3: Screenshot-aligned list and functioning calendar, accurate status/time/Agent rendering, responsive layout and keyboard operation.
- AC-2 / T-1, T-2: Every visible action reaches its specific MPA route with the same user identity, gateway authorization and correct optimistic-concurrency/idempotency fields. Negative cases prove no credential leaks, arbitrary proxying or cross-Runtime stale data.
- AC-3 / T-4: Incremental executable coverage exceeds 95%; run `npm --prefix frontend test`, `npm --prefix frontend run test:mpa-cron-coverage`, `npm --prefix frontend run build`, `npm --prefix frontend run check:i18n`, `npm --prefix frontend run test:webui-assets`, targeted Python tests, Ruff, Pyright and pre-commit. Record simulated versus live outcomes separately.

## Review and delivery record

Source review: pass, 2026-09-15. Bilingual design review: pass for scope, endpoint ownership, error isolation and testability; identity is resolved to the authenticated Studio principal. User design approval: granted on 2026-09-15 (go ahead); use the authenticated Studio principal. Production and test implementation completed; verification is recorded below. No deployment is part of this change. Prior GitHub SSH push failure may still block publishing; recheck at delivery and report truthfully.

## Final verification — 2026-09-15

User approval: go ahead; trusted Studio principal selected. Implementation review: pass for route allowlists, credentials, optimistic versions, retry tokens, cancellation, timezone/DST and bilingual consistency.

- Frontend component/API suite: 71 pass; line coverage 99.71%, branch coverage 97.19%.
- Studio frontend regression suite: 1096 pass.
- Server proxy suite: 12 pass, 100% line coverage.
- TypeScript/Vite production build, i18n (2 locales / 17 namespaces), packaged assets (102 files / 246 references), Ruff and pre-commit secret scanning: pass.
- Scoped server Pyright has no new diagnostics. Full CLI Pyright remains blocked by the same 34 pre-existing diagnostics as before this change; its only change is route callback wiring.
- Real browser fixture: list/actions, calendar, editor, Escape/focus restoration and 760px narrow viewport inspected; pass. No fixture files are shipped.
- Local Studio installed and restarted. Live selected Runtime r-yetmv58y68itpb2txuvg: list HTTP 200, 1 task; task detail shows 1 successful execution. No live task writes were performed. Runtime was already Ready on V10/image 20260915-073a536; this change did not deploy it.
- Source branch synchronized with feat/mpa-agent-oneclick-provision before gates. Git publishing result is recorded in the delivery message.
