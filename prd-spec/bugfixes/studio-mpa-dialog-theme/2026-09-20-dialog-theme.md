# Studio MPA dialog theme repair

[中文版](2026-09-20-dialog-theme.zh.md)

- Change ID: `studio-mpa-dialog-theme`; created/revised: 2026-09-20.
- Status: implemented. User approved the proposed repair with “改一下”.
- Related contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md); [frontend standard](../../../frontend/SPEC.md).

## Evidence and goals

The production entry imports legacy page styles but omits the component library theme styles. The built CSS has no definitions of `--studio-text-primary` or `--studio-bg-elevated`. MpaCreateDialog uses these variables without fallbacks while ModalLayout falls back to a dark background, leaving inherited near-black body text unreadable. The supplied screenshot reproduces this on the light agents page.

Restore readable dialog labels, values, plan and error messages using existing component themes. Do not change provisioning APIs, configuration, task state, deployment or resource allocation.

## Requirements and design

- FR-1: Load the existing theme and component-theme CSS through the production Studio entry before rendering; do not create another palette or override primitive styles.
- FR-2: With no explicit root theme, initialize `data-theme=light` to match the existing page. Preserve an explicit light or dark root theme. Do not change saved preferences or component-preview defaults.
- FR-3: The dialog, inputs, textarea and action buttons must use coherent colors; labels and body text must have at least 4.5:1 contrast. Preserve missing-config submission blocking, retry, close and keyboard behavior at desktop and 390px width.

Changes are limited to `frontend/src/main.tsx`, this bilingual record, a short frontend README note and matching generated `veadk/webui` assets. Loading shared styles may correct other library components too; check their scoped selectors and keep the legacy page surface unchanged. No public API, persistence, permission or component contract changes: this restores the already documented themed-component behavior. No backend tests or cloud operations apply.

## Tasks and acceptance

- T-1 / AC-1: Record the missing variables and failed browser contrast before editing production code.
- T-2 / AC-2: Load both existing stylesheets and initialize the absent root theme; verify light/dark styles and unchanged explicit-theme selection.
- T-3 / AC-3: Run `npm --prefix frontend test`, `npm --prefix frontend run build`, and `npm --prefix frontend run test:webui-assets`; verify the actual dialog in a browser with isolated configuration responses, readable errors, retry, keyboard focus and a narrow viewport.
- T-4 / AC-4: Review the diff, preserve unrelated working changes, and record real outcomes in both languages. No commit, image publication or deployment is part of this repair.

## Review, risks and verification

Direct design review: pass. The existing component styles own button/textarea light variants, so loading only the base token stylesheet would be incomplete. Root theme initialization must precede rendering and must not overwrite an explicit theme. Bilingual scope and identifiers match. The referenced frontend-design and ui-ux-pro-max skills are absent from the repository and installed skill roots; follow the checked-in frontend standard. A sibling repository's review-spec skill owns a different workflow and is not applied here.

Verification pending. Use isolated browser fixtures, not real provisioning calls. Native OS IME interaction and real cloud configuration remain outside this visual repair.


### Verification record (2026-09-20)

Scope: six added production-entry lines, README, this design pair and regenerated package assets; unrelated existing working-tree changes preserved. T-1–T-4 / AC-1–AC-4 are complete.

- **pass — baseline browser reproduction:** actual main.tsx and MpaCreateDialog with isolated API responses rendered `rgb(9, 9, 11)` text on `rgb(28, 28, 30)`; theme token was empty.
- **pass — browser after repair:** default light background `rgb(255, 255, 255)`, secondary text contrast 6.23:1, primary labels/values 14.53:1. Explicit dark theme retained with light text. At 390×844 the 358px-wide modal fits the viewport; missing-configuration and loading messages remain visible. Retry enables creation, multiline Chinese text and Tab work, Escape closes the dialog. No live creation request was made. Native OS IME was not automated.
- **pass — frontend tests:** `npm --prefix frontend test`: 1208 Node tests and 22 Vitest tests. Existing dependency/deprecation warnings only.
- **pass — production build:** `npm --prefix frontend run build`, including TypeScript and both application/widget builds. Existing large-bundle warning retained.
- **pass — package assets:** `npm --prefix frontend run test:webui-assets`: 104 files, 248 references. No temporary fixture code included in built assets.
- **pass — review:** shared theme selectors and fallback behavior inspected; no duplicated colors, primitive overrides, backend/API changes or new dependencies. Paired-language scope and identifiers checked; `git diff --check` passes. Temporary fixture/server/tabs removed and viewport reset.
- **not_run — Gitleaks:** executable unavailable on PATH and checked local locations; manually reviewed the six added runtime lines and documentation, which contain no credential material. No commit or publication performed; repository pre-commit remains required before an authorized commit.
- **not_applicable — Python/Ruff/Pyright/cloud verification:** no Python or cloud behavior changed. The server prerequisite error in the screenshot is preserved and is not fixed by a theme repair.

Preview recovery: changing the temporary Vite configuration caused blank hot reloads; an isolated cache fixed the verification environment. Production config was not changed. The package build succeeded with the normal config.
