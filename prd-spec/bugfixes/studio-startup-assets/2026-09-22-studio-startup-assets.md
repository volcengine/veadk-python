# Studio Startup Asset Integrity Hotfix

[中文版](2026-09-22-studio-startup-assets.zh.md)

## Metadata

- Change ID: `studio-startup-assets`
- Created: 2026-09-22
- Revised: 2026-09-22
- Status: `implemented`
- User approval: approved in the 2026-09-22 session after the recommended restore-and-prevent-recurrence approach was presented
- Related component specs: no component contract change; see [Component Contract Impact](#component-contract-impact)
- Owning standard: [AgentKit Studio AI Development Specification](../../../frontend/SPEC.md)

## Background and Evidence

### Expected behavior

Running the packaged Studio with the repository-local CLI must serve an executable WebUI:

```bash
.venv/bin/veadk studio --dev --host 127.0.0.1 --port 8000
```

The browser must execute the entry module and render the Studio login or workspace instead of an empty root element. A clean frontend dependency installation must also be reproducible with `npm ci`.

### Actual behavior

The current `origin/main` revision `3bbd260a` serves `/` and its entry JavaScript with HTTP 200, but the browser renders a blank page. The packaged entry file starts with a Git conflict marker:

```text
<<<<<<<< HEAD:veadk/webui/assets/app/index-CKbnL9AU.js
```

Repository inspection found 114 tracked files under `veadk/webui` containing conflict markers. The markers first appear in feature commit `dae75ce8` and are present in merge parent `9ff62d54`; the merge's first parent `fd9bec69` has none. Source files under `frontend/src` do not contain these markers.

The checked-in `frontend/package.json` and `frontend/package-lock.json` are also inconsistent. In a clean hotfix worktree, `npm ci --dry-run --ignore-scripts --no-audit --no-fund` fails because the lockfile does not include the `esbuild@0.28.2` peer resolution required by the locked Vitest/Vite dependency graph. Therefore the repository cannot currently reproduce a clean frontend build.

The existing `frontend/scripts/verifyBuiltAssets.mjs` checks directory structure, internal references, and optional byte-for-byte HTTP serving. It does not explicitly reject unresolved conflict markers. Against the current tree it fails on a missing referenced asset, but it does not report the more direct corruption cause.

### Confirmed root cause

Generated WebUI artifacts from two incompatible builds were committed with unresolved textual merge conflict markers. Because static serving does not parse JavaScript, the server returned 200 and the corruption surfaced only when the browser parsed the entry module. The unreproducible lockfile prevented a clean rebuild from being a reliable recovery path.

## Goals

- Restore a reproducible frontend dependency graph so `npm ci` succeeds from a clean checkout.
- Regenerate `veadk/webui` from the current `frontend` sources so every packaged asset belongs to one coherent build and contains no conflict marker.
- Extend the existing packaged-asset validator to reject unresolved Git conflict markers with a direct diagnostic.
- Prove that ordinary packaged startup renders in a clean Chrome profile without `--vite` or a `--frontend-dir` workaround.
- Keep the hotfix isolated from unrelated application, API, runtime, and UI behavior.

## Non-Goals

- No change to Studio CLI options, host/port defaults, HTTP routes, authentication, Session behavior, Runtime behavior, MPA behavior, or UI interaction design.
- No new frontend or Python dependency. Lockfile reconciliation may update transitive resolutions already required by `package.json`.
- No broad CI workflow redesign. The hotfix strengthens the existing `test:webui-assets` command; wiring new jobs across every workflow is deferred unless current repository evidence proves it necessary.
- No commit, push, pull request, publication, or deployment without separate user authorization.
- No modification of the user's main checkout or its local cleanup commit.

## Scenarios

### Scenario S-1: corrupt generated asset is rejected

Given a file under `veadk/webui` contains a standard unresolved merge line beginning with `<<<<<<<`, `|||||||`, `=======`, or `>>>>>>>`, when `npm --prefix frontend run test:webui-assets` runs, then validation fails, names the affected file, and identifies an unresolved conflict marker.

### Scenario S-2: clean build is reproducible

Given a clean checkout and the supported local Node/npm toolchain, when `npm --prefix frontend ci` and `npm --prefix frontend run build` run, then dependency installation and both frontend builds complete successfully without manual lockfile edits.

### Scenario S-3: packaged Studio renders

Given the regenerated `veadk/webui`, when `.venv/bin/veadk studio --dev` starts without `--vite` or `--frontend-dir`, then `/` and `/web/ui-config` return 200 and a clean Chrome profile renders non-empty Studio UI content without page-level JavaScript errors.

### Scenario S-4: source and runtime contracts remain unchanged

Given the hotfix diff, when reviewers inspect source, API, configuration, and user documentation, then no Studio runtime contract or user workflow change is present; only dependency-lock reconciliation, asset validation, generated WebUI artifacts, and this PRD pair change.

## Requirements

| ID | Requirement |
| --- | --- |
| `FR-1` | `frontend/package-lock.json` must be synchronized with `frontend/package.json`, and `npm --prefix frontend ci` must succeed from a clean dependency directory. |
| `FR-2` | `frontend/scripts/verifyBuiltAssets.mjs` must inspect packaged text assets and fail on unresolved Git conflict markers before reference validation can obscure the direct cause. |
| `FR-3` | The conflict-marker check must cover `.html`, `.css`, and `.js` files under `veadk/webui`, including diff3's `|||||||` base marker, report the relative filename, and avoid treating ordinary minified operators or source text as markers unless they occur at a line boundary in Git's marker form. |
| `FR-4` | `npm --prefix frontend run build` must regenerate one coherent `veadk/webui` tree from current sources; no stale artifacts or unresolved markers may remain. |
| `FR-5` | `npm --prefix frontend run test:webui-assets` must pass on the regenerated assets and retain all existing directory, reference, and optional HTTP byte-equality checks. |
| `FR-6` | A normal packaged `veadk studio --dev` launch must render visible Studio content in a clean Chrome profile. HTTP 200 alone is insufficient evidence. |
| `FR-7` | The change must not alter public Python imports, CLI arguments, server routes, frontend API types, configuration precedence, authentication, persistence, or Runtime semantics. |

## Design

### Chosen approach

Use the existing build and validation architecture:

1. Add a narrow content-integrity check to `verifyBuiltAssets.mjs`. For each packaged `.html`, `.css`, and `.js` file already read by the validator, detect standard unresolved Git marker lines with a multiline expression and throw an assertion that includes the relative path. Run this before internal-reference extraction.
2. Use the current `frontend/package.json` as the dependency intent and regenerate only `package-lock.json` with the repository's npm toolchain. Direct dependency declarations and ranges must not change. Confirm that a clean, ordinary `npm ci --no-audit --no-fund` succeeds rather than accepting an install-only or `--ignore-scripts`-only result.
3. Run the existing `npm --prefix frontend run build`. Its Vite configuration empties `veadk/webui` before generation, preventing stale files from the conflicted builds from surviving.
4. Run the strengthened validator, frontend tests, and real packaged startup browser check.

### Alternatives considered

- **Rebuild only:** repairs today's files but allows unresolved conflict markers to regress. Rejected because the existing validator is the natural low-cost prevention seam.
- **Replace only the entry JavaScript:** masks one symptom while 113 other corrupted assets and the lockfile remain broken. Rejected as incomplete and non-reproducible.
- **Add new full-build jobs to every CI workflow:** offers broader enforcement but expands hotfix scope and CI cost. Deferred; the reusable asset validator is sufficient for this contained repair.

### Error behavior

Validation must fail early with a message shaped around the invariant, for example:

```text
assets/app/index-*.js contains an unresolved Git conflict marker
```

The validator must not print asset contents, because generated bundles can contain configuration-shaped strings even though secrets must never be embedded there.

### Compatibility and rollback

- Runtime compatibility: unchanged. The generated UI is built from the same current sources and APIs.
- Dependency compatibility: direct dependency ranges remain unchanged; the lockfile is reconciled to those ranges.
- Rollback: revert the hotfix commit. A rollback would restore the known blank-page defect, so the preferred operational recovery is to use the last clean generated WebUI while repairing main.

### Security, state, and concurrency

- Security: no credential, authorization, URL-fetching, or trust-boundary change. Validation reads repository-local generated text and reports filenames only.
- State/data: no application data or persistence change.
- Concurrency/cancellation: not applicable; the changed validator is a single-process build-time command.
- External side effects: dependency installation downloads packages already declared by the repository; no cloud or provider operation is authorized.

## Component Contract Impact

No component spec is created or updated. The hotfix preserves all externally observable Studio, CLI, HTTP, Runtime, authentication, state, and configuration contracts. It repairs generated delivery artifacts and their build-time integrity check. The maintained component-spec triggers in `specs/README.md` are therefore not met. This no-impact conclusion must be revisited if implementation needs to change a CLI option, route, configuration default, runtime behavior, or frontend API contract.

## Affected Files

Expected authored files:

- `.gitattributes`
- `frontend/package-lock.json`
- `frontend/scripts/verifyBuiltAssets.mjs`
- `prd-spec/bugfixes/studio-startup-assets/2026-09-22-studio-startup-assets.md`
- `prd-spec/bugfixes/studio-startup-assets/2026-09-22-studio-startup-assets.zh.md`

Expected generated files:

- `veadk/webui/**` as produced by `npm --prefix frontend run build`

No source files under `frontend/src`, Python modules, component specs, or user documentation are expected to change.

## Implementation Tasks

| ID | Task | Requirements |
| --- | --- | --- |
| `T-1` | Add the conflict-marker guard to the existing asset validator, then run the strengthened validator against the still-corrupt pre-rebuild tree as the negative control. Preserve the failure output before any generated asset changes. | `FR-2`, `FR-3` |
| `T-2` | Reconcile `package-lock.json`, remove the hotfix worktree's dependency directory, and prove clean `npm ci`. | `FR-1` |
| `T-3` | Rebuild `veadk/webui` using the existing build command and verify no stale/conflicted assets remain. | `FR-4`, `FR-5` |
| `T-4` | Run frontend tests, asset verification, diff hygiene, and secret scanning/pre-commit gates required for the final diff. | `FR-5`, `FR-7` |
| `T-5` | Start packaged Studio without workarounds and use a clean Chrome profile to verify visible rendering, DOM content, console/page errors, and core HTTP endpoints. | `FR-6` |
| `T-6` | Perform two-pass implementation review and synchronize English/Chinese delivery records with actual evidence. | all |

## Verification and Acceptance

Execution date is 2026-09-22. The final tested scope is `fix/studio-startup-assets` rebased onto `origin/main` revision `821f0f36`, with the hotfix worktree diff. Frontend dependency checks used Node `v22.23.0` and npm `10.9.8`. Revision `3bbd260a` remains the defect reproduction baseline described above.

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-2`, `FR-3` | `T-1` | `AC-1`: after adding the guard but before rebuilding, the current corrupted tree fails specifically on an unresolved conflict marker and names its file; this proves the new check is sensitive to the original defect. | `npm --prefix frontend run test:webui-assets` before rebuilding | `pass`: exit 1 with `assets/app/index-Ceg2hYta.js contains an unresolved Git conflict marker`; output was bounded to 536 bytes. |
| `FR-1` | `T-2` | `AC-2`: a clean ordinary dependency installation, including package lifecycle scripts, succeeds from the committed lockfile without changing `package.json`. | `npm --prefix frontend ci --no-audit --no-fund`; `git diff --exit-code -- frontend/package.json` | `pass`: 697 packages installed; `package.json` SHA-256 remained `81b2946cc95da4014fef3924b4e6a3a096e69d0b5635bfa00e97148571d19ac8`. |
| `FR-4`, `FR-5` | `T-3` | `AC-3`: build succeeds, the generated tree contains zero conflict-marker files, and all asset references resolve. | `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets`; marker scan over `veadk/webui`; repeated-build SHA-256 comparison | `pass`: both Vite builds completed; 104 packaged files and 248 references passed; marker count is 0; two consecutive builds produced identical SHA-256 values for all 104 files. |
| `FR-5`, `FR-7` | `T-4` | `AC-4`: frontend regression tests and build-time checks pass without weakening assertions. | `npm --prefix frontend test`; `npm --prefix frontend run check:i18n`; `git diff --check` | `pass`: after rebasing, 1305 Node tests and 25 Vitest tests passed; 2 locales and 21 namespaces matched; diff check passed. |
| `FR-6` | `T-5` | `AC-5`: packaged Studio returns 200 for `/` and `/web/ui-config`; a fresh Chrome profile produces a non-empty rendered DOM and screenshot with no page-level JavaScript error. | `.venv/bin/veadk studio --dev --host 127.0.0.1 --port 18081` plus isolated Chrome/CDP verification | `pass`: both endpoints returned 200; `rootChildren=1`; rendered login text included `AgentKit Studio`; captured page/console/network error list was empty; screenshot confirmed visible UI. |
| all | `T-6` | `AC-6`: repository-required final gates complete or are honestly recorded with reason; bilingual documents match the delivered diff. | `uv run --extra dev pre-commit run --all-files` and applicable final review | `pass`: Ruff check, Ruff format, and gitleaks passed. Two implementation review passes resolved bounded diagnostics, diff3/CRLF marker coverage, and generated-bundle whitespace handling. |
| repository regression | `T-6` | The required default Python regression is executed and unrelated baseline failures are reported without widening this frontend-only hotfix. | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | `fail`: 5013 passed, 12 skipped, 2 xfailed, 11 failed, and 2 collection errors. Failures are in unchanged environment, Skill, MPA managed-service, and Harness tests; collection errors report missing optional `anthropic`. This hotfix changes no Python source. |

## Risks and Open Questions

- Lockfile regeneration can create a larger transitive diff because existing ranges are broad. Review must distinguish required synchronization from unrelated upgrades and minimize churn where npm permits.
- Dependency commands use the repository-local `frontend/package.json` and `package-lock.json` with the available Node 22/npm 10 toolchain. The final clean-install evidence must report the exact versions used.
- Generated WebUI diffs are large by nature. Validation must focus on reproducibility, absence of conflict markers, internal references, frontend tests, and real browser behavior rather than manual review of minified text alone.
- `website-integration.js` contains third-party template literals with significant trailing whitespace. The existing `.gitattributes` policy already disables whitespace diagnostics for generated JavaScript under `veadk/webui/assets`; this hotfix extends that exact policy to the generated root-level integration bundle instead of rewriting semantic bundle content.
- The current repository does not appear to run `test:webui-assets` in every general PR workflow. This hotfix strengthens the reusable command but does not claim universal CI enforcement. A separate CI-governance change may be proposed later if desired.
- Open questions: none blocking. The user approved the contained restore-and-prevent-recurrence approach on 2026-09-22.

## Review and Delivery Record

- 2026-09-22: scope, alternatives, root-cause evidence, and the recommended approach were presented to the user. The user replied `继续`, approving continuation with the recommended design.
- 2026-09-22 spec review: found and resolved two P1 gaps. The negative control now explicitly runs the strengthened validator before rebuilding, and clean installation now requires ordinary lifecycle scripts instead of relying on `--ignore-scripts`. Bilingual identifiers, commands, affected files, compatibility, component no-impact, security, rollback, and acceptance traceability were checked with no remaining blocker.
- 2026-09-22 implementation review: the second edge-case pass added coverage for the standard diff3 `|||||||` base marker. It also extended the repository's existing generated-JavaScript whitespace attribute to `veadk/webui/website-integration.js`, whose third-party template literals contain significant trailing whitespace.
- Spec review conclusion: approved for implementation.
- 2026-09-22 final synchronization: rebased onto `origin/main` revision `821f0f36`. Upstream had independently replaced the corrupt WebUI while adding later frontend fixes; rebuilding from that latest source produced zero `veadk/webui` diff. The hotfix therefore retains only the reproducible lockfile correction, conflict-marker prevention guard, and this bilingual design record.
- 2026-09-22 delivery: all tasks `T-1` through `T-6` and acceptance criteria `AC-1` through `AC-6` passed. No Python source, frontend application source, public contract, component spec, or user documentation changed.
- The broad Python regression remains red for unrelated latest-main failures recorded above. The frontend-specific delivery gates and repository pre-commit hooks pass; the unrelated Python failures are not suppressed or modified by this hotfix.
- Remaining scope: pull request, publication, and deployment are not part of this delivery. Commit and push were separately authorized by the user.
