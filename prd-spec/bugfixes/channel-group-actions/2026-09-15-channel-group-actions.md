# Compact group permission actions

[中文](2026-09-15-channel-group-actions.zh.md)

Date: 2026-09-15. Status: implemented. The user requests removal of Edit and replacement of Remove with a cross icon in Feishu group permission rows.

## Evidence, scope and design
RuntimeChannels renders Edit and Remove as full buttons; its descendant span rule also stretches button internals. Remove Edit, reuse the repository SVG cross for the remaining accessible icon button, and scope text sizing to the row's direct label. Keep a 28px target on the right and wrap long group names within available space. Preserve the existing DELETE/refresh, busy/error behavior, and form. No new confirmation is introduced; the current handler has none. No API, permission, state/data or backend contract changes; the component contract assessment is no impact.

## Tasks and acceptance
T-1/AC-1: no Edit entry, one cross action per group with a group-specific accessible label. T-2/AC-2: existing removal works and long names do not displace the icon at narrow widths. T-3/AC-3: run existing channel/frontend tests, build/assets, and mocked real-browser desktop/narrow checks. No new tests for the reversible presentation change; existing removal handlers remain unchanged.

## Review and risks
Direct review (review-spec unavailable): user instruction approves scope, existing SVG/button/semantic tokens reused, no behavior or authorization expansion. No blockers. Design skills referenced by frontend/SPEC.md remain unavailable. No cloud/provider operations or deployment. Verification complete.

## Verification results
2026-09-15 current uncommitted group-action diff: pass. `cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`: 31 tests; `npm --prefix frontend test`: 1208 tests; `npm --prefix frontend run build`: pass (existing bundle warnings); `npm --prefix frontend run test:webui-assets`: 104 files/248 references. Browser with isolated mocked APIs: no Edit, 28px cross, long names fit desktop and 480×1000 narrow layout; keyboard Enter removes the row and shows zero groups. The initial mock missed Runtime DELETE method override; correcting the mock passed without production handler changes. Scoped whitespace/paired links passed. Python/IME/new asynchronous-state checks not_applicable; live operations, deployment and pre-commit gates not_run (no deployment or commit requested). T-1 through T-3/AC-1 through AC-3 complete; no review blockers.
