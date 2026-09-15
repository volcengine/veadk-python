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
