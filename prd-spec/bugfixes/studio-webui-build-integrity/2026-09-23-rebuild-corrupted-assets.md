# Rebuild corrupted Studio WebUI assets

[中文版](2026-09-23-rebuild-corrupted-assets.zh.md)

- Change ID: `studio-webui-build-integrity`
- Created/revised: 2026-09-23
- Status: implemented
- Component specs: no change; the HTTP, UI, and deployment contracts are unchanged.

## Background and evidence

The deployed Studio root returned HTTP 200, but rendered a blank page. Its referenced `assets/app/index-Ceg2hYta.js` began with `<<<<<<<< HEAD`, and `node --check` failed with `Unexpected token '<<'`. A repository scan found conflict markers in 114 packaged JS files. The existing asset verifier checked references, not merge markers. The source build also encountered an implicit-`any` TypeScript error in the WeCom callback and a locally missing declared SDK dependency. The latter was an installation issue, not an application change.

## Goals, non-goals, scenarios, and requirements

- Goal: serve parseable, internally consistent WebUI assets so the Studio login page renders.
- Non-goals: alter login, UserPool, Runtime, MPA, scheduler, or WeCom authorization behavior.
- `FR-1`: Given a clean source build, when assets are packaged, no HTML/CSS/JS file contains a line-start Git conflict marker.
- `FR-2`: Given the deployed Studio URL, when an unauthenticated browser opens `/`, the Identity login UI renders instead of a blank page.
- Boundary: an unauthenticated `/web/runtime-config` request redirects to login; this does not prove the authenticated workbench.

## Design and contract impact

Regenerate `veadk/webui/` with the existing `frontend/scripts/build.mjs` instead of editing minified bundles. Add a conflict-marker assertion to `frontend/scripts/verifyBuiltAssets.mjs`. Type the existing WeCom SDK callback result narrowly to let TypeScript build; runtime logic is unchanged. No new dependency, API, state, persistence, permissions, credential handling, or compatibility contract is introduced. No component spec or user documentation changes are needed. Alternative manual edits to 114 bundles would be unrepeatable and were rejected. The generated JavaScript includes template-string whitespace, so `git diff --check` may report generated lines even when syntax and packaging checks pass.

## Tasks and acceptance

| Requirement | Task | Acceptance | Evidence (2026-09-23, `15ac109`) |
| --- | --- | --- | --- |
| `FR-1` | `T-1` rebuild packaged assets; `T-2` add merge-marker check | `AC-1` every packaged JS parses and asset references resolve | `npm run build`: pass; `npm run test:webui-assets`: pass, 101 files/236 references; `node --check` on all packaged JS: pass |
| `FR-2` | `T-3` redeploy the existing Studio application | `AC-2` browser shows the Identity login heading and button | Existing VeFaaS application update: pass; real browser DOM and screenshot: pass |

`npm test`: pass (1,253 Node tests and 25 Vitest tests). Staged-file pre-commit: pass. Full-file pre-commit: fail because Ruff reformatted three unrelated existing Python test files; those incidental edits were reverted. `git diff --check`: fail on whitespace inside generated `website-integration.js` template strings. Authenticated workbench and MPA creation: not_run; outside this blank-page fix. Cloud credentials and raw logs are intentionally excluded.

## Risks, review, and delivery

Generated asset hashes and many filenames change as a set; deploying only `index.html` would break references. The existing app and Identity configuration were reused, and the scheduler deployment completed. Source, asset, and browser checks resolve the reported blocker. No `review-spec` skill was available; direct review found no contract change or security expansion. This operational repair was performed under the ongoing cloud-deployment request; no separate design approval was recorded before implementation.
