# Session history Sandbox downloads

[中文](2026-09-17-history-download.zh.md)

## Scope and approval
User approved implementation on `czh/studio-cron-e2e` after agreeing that history Markdown paths should invoke MPA downloads. Stored history already contains `[random.txt](/data/output/random.txt)`. No Worker, SSE protocol, artifact registry, or persistence change is needed.

## Design
Follow [component contract](../../../specs/studio-sandbox-download/README.md). Supply conversation scope around assistant blocks; the shared Markdown renderer recognizes allowed links before video handling. A small link component owns loading, errors, cancellation and blob download. The existing ADK client resolves the selected Runtime and forwards the request through the authenticated Studio proxy. Preserve link labels and use the larger download control approved below. No dependencies or new backend routes.

## Tasks and acceptance
1. Add failing regression tests for paths, Unicode/spaces, history Markdown, proxy routing and lifecycle.
2. Implement scoped links and localized loading/error feedback; retry by clicking again.
3. Run frontend tests/build and incremental coverage above 95%; inspect local browser and commit generated web assets.
4. Fetch/rebase intended upstream, run pre-commit, commit and push.

## Review
Direct design review (review-spec unavailable): ownership, session scope, root allowlist, cancellation, credential isolation, unchanged external links and bilingual equivalence checked. No blockers. frontend-design applied; ui-ux-pro-max unavailable locally, existing frontend/SPEC.md controls visual behavior.

## Risks and verification
Sandbox lifetime limits availability. Blob downloads buffer files in browser memory. No automatic Sandbox creation or recovery. Tests, browser evidence and gate results will be recorded after implementation.

## Approved presentation update
User confirmed downloads work and requested hiding legacy file-card contents and a larger, more visible download control. Use existing primary colors, 44px minimum height, visible focus and wrapping filenames; suppress file-card/personal-drive-enable-card subtrees only in conversation scope. Regression tests must preserve surrounding Markdown.

## Verification record (2026-09-17)
- PASS: `npm --prefix frontend run test:sandbox-download-coverage`: 26 tests. New component lines/statements/functions/branches 100%; added instrumented source lines 46/46 (100%). Conservatively counting the uninstrumented App provider expression as uncovered: 46/47 (97.87%). Existing client/Markdown whole-file coverage is not the incremental coverage metric.
- PASS: `npm --prefix frontend test`: 1102 tests; `npm --prefix frontend run build` (TypeScript and both bundles); `npm --prefix frontend run check:i18n`.
- PASS: `git fetch polaris` and `git rebase --autostash polaris/czh/studio-cron-e2e` (already current; changes restored); `UV_PROJECT_ENVIRONMENT=/Users/bytedance/Applications/veadk-studio-mpa/.venv uv run --no-sync --extra dev pre-commit run --all-files` (existing environment, Ruff and secret scan).
- PASS: real Chrome localhost:8765, last MPA agent, existing random-file history: legacy path hidden, visible download button, Enter activates loading and download; Runtime proxy upstream HTTP 200. User independently confirmed download before the presentation update. Error/retry/cancellation and Unicode paths validated in isolated tests, not deliberately induced in live Sandbox. Narrow viewport not run.
- Backend/Python regression: not applicable (no Python edits). Build warns about existing bundle sizes. Generated vendor bundles retain upstream trailing whitespace; authored source diff whitespace clean.
- Review: authentication stays in existing transport, conversation context scopes the feature, path traversal/unsupported roots excluded, abort and object URL cleanup tested. No credentials or production payloads added to fixtures.
