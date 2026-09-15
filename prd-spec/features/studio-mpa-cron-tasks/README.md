# Studio MPA Runtime scheduled tasks

[中文版](README.zh.md)

Date: 2026-09-15. Change: studio-mpa-cron-tasks. Status: design reviewed; implementation authorized by the current user request.

## Evidence and scope
Studio lists owner-scoped TOS jobs through /web/cronjobs. MPA separately exposes GET /api/v1/esa-cron-tasks, filtered by its validated user identity. Add a read-only source tab for the currently selected Runtime; do not merge, migrate, create, edit, delete or run tasks.

## Requirements and design
FR-1: Pass the selected cloud Runtime ID, name and region from App to CronJobs. Show the target explicitly. No selection means no request; never fall back to another Runtime.
FR-2: Use the existing Runtime proxy and API key handling. Forward an optional X-Jwt-Token entered in a masked field. Keep it only in component memory, clearing it on Runtime/region changes and unmount. Never derive or forge identity, persist credentials or weaken authentication.
FR-3: Show name, enabled state, schedule, next execution and latest result. Fetch 20 records per page including disabled tasks. Provide previous/next and refresh. Separate loading, empty, unavailable API, authentication and other failures. A failed fetch is never an empty list.
FR-4: Abort requests on changes/unmount and ignore late responses. Clear prior target data immediately, preserve readable same-page data while refreshing. Keep Studio task behavior unchanged.

## Files and tasks
T-1: Add the typed client adapter and Runtime panel; wire App/CronJobs and bilingual translations.
T-2: Add HTTP/component regression tests before implementation, cover pagination, failures, cancellation and switching targets.
T-3: Run npm test, build, i18n and incremental coverage above 95%; check browser layout, built assets and secrets; commit/push and update local Studio assets.

## Review and acceptance
Design review: existing components and proxy suffice; no dependencies or backend changes. Bilingual texts are equivalent. Existing Studio tasks and MPA tasks remain separate. User request explicitly authorizes the module; current session authorizes commit/push. The repo-referenced ui-ux-pro-max skill is unavailable; apply frontend/SPEC.md and available frontend-design guidance directly.
AC-1: Selected target and real upstream path match; pagination and states pass tests. AC-2: No stale target data or stored credentials. AC-3: UI and build pass; live data requires a valid MPA JWT and is reported separately from simulated tests.

## Verification — 2026-09-15

Pass: 1095 frontend tests; 34 isolated HTTP/component tests; new adapter/panel statements, branches, functions and lines 100%; TypeScript and both Vite builds; i18n (2 locales, 17 namespaces); packaged assets (102 files, 246 references). Pre-commit Ruff and secret scan pass. Browser verified no-target state, selection propagation and the real selected Runtime proxy request returning 401 with the JWT-required message. Existing Studio tab remains separate. The local Studio assets are updated; its prior bundle is backed up outside the repository. Authenticated real task data and a narrow-viewport screenshot are not verified; real task data requires a valid user JWT. No production task mutations were performed.

## Risks and limits
Runtime-level selection does not grant all-user visibility. Missing JWT is an authentication state, not absence of tasks. No scheduler or MPA business logic changes. Generated assets are included for local Studio delivery. Verification results will be recorded here before delivery.

## Automatic credentials revision — 2026-09-15
The current user authorizes replacing manual JWT entry with server-side TOP GetMpaInstanceToken (2026-03-01). Resolve MPA_AGENT_ID, MPA_SPACE_ID/CLAW_SPACE_ID, MPA_IS_DEBUG_RUNTIME and ARKCLAW_TOP_SERVICE from the authorized selected Runtime. Use trusted enterprise user_pool_user_uid; local administrators configure VEADK_STUDIO_MPA_USER_UID on the server. Never use a browser-supplied identity to acquire credentials. TOP signs the JWT. Match its HTTPS endpoint against the selected Runtime before forwarding Authorization and X-Jwt-Token. Acquire fresh credentials per list request; do not cache, persist or return credentials to the browser. Keep the read-only scope and add task prompt details plus executionCount/successRate summaries following mono SharedAgent/Cron. Missing configuration and TOP errors remain actionable errors. Tests must cover identity, endpoint mismatch, upstream failures, credential containment and cancellation, with incremental coverage above 95%. This revision supersedes the previous manual-JWT contract and its completed verification applies only to the previous revision.

## Revision verification — 2026-09-15

Pass: 43 frontend contract/component tests and 31 Python tests; both new module scopes have 100% statement/branch coverage. All 1095 frontend regression tests, TypeScript/Vite builds, i18n and 102 packaged asset checks pass. New Python module Pyright passes. The CLI file has 34 pre-existing Pyright diagnostics: baseline comparison confirms identical messages and no new diagnostics. Local Studio was updated and restarted; the browser confirms no JWT field, correct selected Runtime and an actionable missing-user-UID error. A separate read-only TOP probe returned 403 AccessDenied for arkclaw:GetMpaInstanceToken using the configured AK/SK. Authenticated task data remains blocked on this permission and the enterprise UserPoolUserUid. Existing Studio TOS task loading also fails in this environment; that source was not modified. Narrow-viewport verification was not run.
