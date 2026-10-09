# Hide the incompatible session artifact entry for MPA

[中文版](2026-09-30-hide-artifact-entry.zh.md)

- Change ID: `studio-mpa-artifact-entry`; created/revised: 2026-09-30
- Status: approved; contract: [Studio Sandbox downloads](../../../specs/studio-sandbox-download/README.md), `CON-5`

## Background, scope and requirements

The composer mounts `RuntimeArtifacts` for every connected Runtime session.
Its hook fetches even while closed. That service reads Studio `artifacts/`
or a Runtime `/mnt/artifacts` mount, not an MPA Worker `/data/output` mount.
The user explicitly requested hiding this entry for MPA until supported.

- `FR-1`: Given native or A2A MPA connections identified by existing Runtime
  metadata, no artifact entry/component is mounted and its fetch hook does not run.
- `FR-2`: Given a general Runtime with a session, retain the existing entry;
  local apps, no-session states and dedicated Sandbox views retain their guards.
- `FR-3`: Switching between general and MPA connections reevaluates visibility.
  Existing Markdown file downloads, backend authorization, storage paths,
  credentials and MPA identity/transport classification are unchanged.

## Design and review

Add only the two existing product predicates `isMpaRuntimeApp` and
`isMpaA2aRuntimeApp` to the composer mount condition. Do not change those
transport-sensitive predicates, hide with CSS, add a configuration switch,
infer category from image/name, or wire another storage adapter. Removing the
component also retains its existing abort/unmount behavior. No schemas,
persistence or permissions change; UI hiding is not an authorization control.
No style, typography, icon, layout or replacement notice changes.

Direct review (`review-spec` unavailable) checked native/A2A coverage, scope,
security, testability and bilingual equivalence. User request approves this
scope. Ponytail selects the existing predicates; frontend-design preserves the
current visual system. Referenced `ui-ux-pro-max` files are unavailable; apply
the existing Studio/Foundation rules instead. No design blockers.

## Tasks, verification and risks

| Requirement | Task | Acceptance | Evidence |
| --- | --- | --- | --- |
| `FR-1`, `FR-2` | `T-1`: regress and change the actual composer guard | `AC-1`: native/A2A MPA hidden; general visible; existing guards retained | Source-extracted actual guard: 5 failures before the fix, 25 passes after |
| `FR-3` | `T-2`: check switching and ordinary artifact interactions | `AC-2`: current selection controls mounting without changing download APIs | Selection regression passes; 19 artifact interaction/cache tests pass; browser session check blocked as below |
| all | `T-3`: build, review and deliver | `AC-3`: synchronized docs/assets, >95% incremental coverage | 1376 Node + 47 Vitest tests pass; build and packaged assets pass; pre-commit passes |

Run a failing regression first. Reuse the existing source-extraction test
pattern to execute the actual App guard with the real classification helpers,
including both metadata forms and absent Runtime/session/Sandbox boundaries.
Run artifact interaction tests explicitly because the default npm test does
not include them. Build matching `veadk/webui` assets, inspect the browser at
normal/narrow widths and verify general-to-MPA switching. Record all results
here. No cloud deployment or real agent execution is requested; no Python
behavior changes require rerunning the unrelated full Python suite.

### Results and remaining browser check

The one-line production guard reuses both existing predicates. V8 coverage of
the source-extracted actual guard with real classifiers is 100% (5/5 ranges;
counts 23/19/15/11/9), not whole-App coverage. TypeScript, Vite and widget builds
pass; packaged asset validation verifies 113 files and 350 internal references.
Generated hash-dependent bundles are updated together. Build chunk-size warnings
are non-blocking. Diff whitespace and pre-commit checks pass.

The current source was served on local Vite port 5188 using the existing local
backend on 8765, without changing that backend or cloud resources. Browser login,
home and agent picker render; the MPA list remained in loading state after
selection, so an existing session could not be opened. Actual session visibility,
browser switching and narrow-window checks remain unverified; the source-level
matrix is not presented as browser E2E. No cloud deployment or model invocation
was performed. The remaining browser check does not justify unrelated fixes.

Risk: incomplete connection metadata cannot identify MPA; retain the existing
classification contract rather than guessing. Future Sandbox artifact support
needs a separate adapter; this change does not implement or promise it.
