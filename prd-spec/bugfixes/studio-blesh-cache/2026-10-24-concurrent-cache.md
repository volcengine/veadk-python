# Concurrent Bash cache initialization

[中文版](2026-10-24-concurrent-cache.zh.md)

- Change ID: `studio-blesh-cache`
- Created/revised: 2026-10-24
- Status: implemented
- Component impact: implementation-only correction; no public API, shell configuration contract, final cache format, or permission change. No component spec update is needed.

## Evidence and scope

The pinned ble.sh v0.4.0-devel3 release writes and renames the same `$cache.part` in `ble/builtin/bind/read-user-settings/.collect`. Concurrent shells can rename another shell's temporary file, producing `mv: cannot stat` on first workspace entry. The deployed release and these two lines were inspected. Upstream now uses a process-specific temporary filename in [src/decode.sh](https://github.com/akinomyoga/ble.sh/blob/master/src/decode.sh).

Preserve Bash, highlighting, key bindings, and the shared final cache. Do not upgrade unrelated dependencies, change project files, publish an image, or restart running work. The user approved fixing both image source and the current workspace on 2026-10-24.

## Requirements and design

- FR-1: Concurrent shells must publish complete Readline caches without sharing a temporary filename. Backport the upstream `$$` filename suffix, which remains stable across the pipeline and subsequent rename.
- FR-2: Full builds and incremental image builds must apply the same idempotent patch. Unexpected vendor source must fail before modification. Write through a sibling temporary file and atomically replace the vendor file, preserving its permissions.
- FR-3: Repair the current workspace without privilege changes. Its system plugin is read-only and sudo is disabled, so copy the installed plugin to the user's local data directory, apply the same patch, back up `.bashrc`, and change only the plugin source path. New terminals use the copy; existing terminals are left running.

Affected code: `frontend/sandbox-image/runtime/ble_cache.py` (new), `install-image.py`, and `refresh-editor.py`. Regression coverage is under `frontend/sandbox-image/tests/`. The current workspace changes are outside the repository and contain no credentials or project edits.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| FR-1 | T-1: reproduce then patch | AC-1: synchronized competing writers finish without missing temporary files or incomplete caches | Targeted Bash subprocess regression | pass: original loses one writer; patched writers both succeed |
| FR-2 | T-2: wire both builds | AC-2: repeat patch preserves bytes, permissions, and mtime; unexpected source stays unchanged | Python patch tests and build entry-point review | pass |
| FR-3 | T-3: repair live workspace | AC-3: fresh terminals load patched ble.sh and run commands successfully | Browser terminal verification | pass: fresh terminal confirmed the loaded path and patched function, then executed `echo ok` |

Commands: `python3 -m unittest discover -s frontend/sandbox-image/tests -v`; Ruff and Pyright for changed Python files; `git diff --check`.

## Review, risks, and recovery

Direct design review found no API, ownership, credential, or dependency change. English and Chinese requirements and acceptance are equivalent. The pinned-source check prevents an unnoticed future vendor change. Deterministic concurrent tests cover the actual write/rename race; UI-only checks cannot prove concurrency. The patch does not suppress genuine filesystem errors. The temporary suffix does not change persistent cache names.

Current workspace rollback restores the backed-up `.bashrc`; no system file is changed. Full image build/publication and broad application tests are not in this task's approved scope. Image source is prepared locally; new cloud workspaces require a later image release. Live repair lifetime follows the current sandbox filesystem.

Verification on 2026-10-24, local diff based on `c662cc8d4`: `python3 -m unittest discover -s frontend/sandbox-image/tests -v` passed all 15 tests, including the pre-submission rerun. The repository's existing Python environment ran Ruff and Pyright on `runtime/ble_cache.py`, `runtime/install-image.py`, `runtime/refresh-editor.py`, and `tests/test_ble_cache.py`: pass, no errors. `pre-commit run --all-files`: pass, including Ruff, formatting, secret scanning, and dependency policy. `git diff --check`: pass. Full Docker builds and broad application tests: not_run, limited to the requested source repair and lightweight checks. A draft PR was requested on 2026-10-24; image publication remains outside scope.
