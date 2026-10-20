# Relocate MPA compatibility resources under Studio

[中文版](2026-10-14-studio-owned-resources.zh.md)

- Change ID: `mpa-contract-location`; date: 2026-10-14; status: implemented.
- Contract: [Studio MPA control plane](../../../specs/studio-mpa-control-plane/README.md).

## Evidence, requirements and non-goals

The root `contracts/mpa-p0` contains only `compatibility-matrix.json` and `benchmark-report.schema.json`. Studio and CLI share the evaluator in `veadk.cli.mpa_p0_contract`; its default loader uses the root matrix when present and otherwise the identical embedded rules. Integration tests and documented `--matrix` examples reference the root file. The benchmark schema has no discovered runtime caller. Studio release staging copies the frontend Python tree, but setuptools currently has no package-data declaration for the new JSON path. Existing unrelated `frontend/package-lock.json` edits must remain byte-identical.

FR-1: Move both JSON files unchanged to `frontend/server/mpa/contracts/mpa-p0/` and remove the empty root directory. Do not change rule/schema values, decision outcomes, MPA/general-agent behavior or OpenViking behavior.
FR-2: Update `default_matrix_path()` and integration tests/documented commands. Keep public function signatures, the required custom `--matrix` argument and embedded fallback unchanged. Missing packaged files still use embedded rules; malformed present JSON continues to fail visibly. Existing callers explicitly using the old root file path must use the new path.
FR-3: Include both JSON resources in the Python wheel and Studio source staging; access them by sibling filesystem paths without importing the heavy frontend composition package. Verify source and an isolated extracted wheel resolve the same rules.

Non-goals: moving evaluator ownership, changing SDK/version rules, removing compatibility preflight, deleting OpenSpec/PRD/spec directories, changing UI or cloud resources. No commit, push or deployment is requested.

## Design, files and tasks

Retain `mpa-p0` nesting. Compute the default path from the evaluator's installed source root to frontend/server/mpa; add the precise existing-resource package-data glob to `frontend.server` in pyproject.toml. Studio's copytree staging already includes that directory and needs no production change. Update bilingual current design/validation examples and append a relocation note to the maintained control-plane contract.

T-1 / AC-1: Write a failing path/source-loading regression first and exercise normal compatibility, invalid manifest and rejection before writes. Move both resources byte-for-byte and update the path.
T-2 / AC-2: Test missing fallback and malformed-file failure; update CLI examples/tests without changing explicit custom-file behavior.
T-3 / AC-3: Add a real source-staging assertion for both resources; build a local wheel and inspect/extract it to verify JSON presence and default-loader resolution. No publication occurs.
T-4 / AC-4: Targeted compatibility/CLI/release checks, changed Python Ruff/Pyright, paired documents/links, whitespace and secret checks. Record actual evidence and preserve unrelated local changes.

## Review, risks and authorization

Direct review replaces unavailable review-spec: requirements, ownership, consumer paths, filesystem/wheel behavior, error semantics, no-new-import boundary and paired languages are consistent. The user approved the exact whole-directory migration on 2026-10-14 with “按此方案迁移（推荐）”. Changing the file location is intentional; custom CLI argument semantics stay stable. No runtime concurrency, authorization, credential or cloud API changes occur. Both language versions and the maintained contract must be updated together. Main risk is omitted package data; wheel extraction is the acceptance check. Implementation and tests are authorized; approval does not authorize commit/push/deployment.

## Verification record

Execution scope starts at `2ffe6e14` plus this change; outcomes are recorded below. Live cloud/browser/sidecar smoke is not_applicable because only internal static-resource location changes. No TypeScript or rendered UI changes are planned, so frontend rebuild and browser interaction tests are not applicable.

### Completed verification — 2026-10-14

Scope: `2ffe6e14` plus this local migration. T-1–T-4 / AC-1–AC-4 completed. Test-first result was 6 failed / 4 passed before moving files/changing the loader. After implementation:

| Check | Result | Evidence / limitation |
| --- | --- | --- |
| Targeted compatibility tests | pass | 10 tests, including new location, both source-staged JSON files, missing fallback and visible malformed-file errors. |
| Related compatibility, Studio RBAC/GitHub, release and startup regression | pass | 376 tests with two workers; cloud/provider calls mocked. Pre-mutation compatibility rejection and general-agent paths remain covered. |
| Changed Python Ruff/format/Pyright | pass | Repository Ruff 0.11.12; Pyright uses repository Python, 0 errors/warnings. Temporary uvx tools, no global configuration changes. |
| Standard wheel and actual Studio-staged wheel | pass | Both built locally. Isolated extraction finds the two JSON files at the new path, byte-identical to HEAD originals; default loader reads the packaged matrix and returns compatible for the existing baseline. Real stage_studio_wheel_source excludes node_modules/src and includes the resources. Nothing uploaded/installed globally. |
| Review / documents / secret / whitespace | pass | Paired identifiers/commands/relative links reviewed; repository Gitleaks rules on this changed-file scope; git diff whitespace. No credentials added. |
| Existing local changes | pass | Unrelated frontend/package-lock.json SHA-256 unchanged. |
| Full repository regression / frontend/browser / live cloud / sidecar smoke | not_run / not_applicable | Focused regression covers every known path consumer; no further shared logic, TypeScript, UI, cloud or harness protocol change. No external cloud effects exercised. |
| Commit / push / deployment | not_run | Not requested or authorized for this migration. |

Final review found no additional behavior, import, ownership or packaging change. Explicit old-root CLI paths must use the new path as approved; custom matrix options and builtin fallback stay compatible. Actual commands (MPA_STAGE_ROOT is the temporary source returned by real Studio staging):

```bash
uv run --extra dev pytest tests/integrations/test_mpa_compatibility_manifest.py -q
uv run --extra dev pytest -n 2 -q tests/integrations/test_mpa_compatibility_manifest.py tests/cli/test_studio_rbac.py tests/cli/test_github_cicd.py tests/cli/test_studio_release.py tests/test_studio_release_server.py tests/cli/test_studio_startup_imports.py
uvx --from ruff==0.11.12 ruff check veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uvx --from ruff==0.11.12 ruff format --check veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uvx pyright --pythonpath .venv/bin/python veadk/cli/mpa_p0_contract.py tests/integrations/test_mpa_compatibility_manifest.py
uv build --wheel --out-dir /tmp/veadk-mpa-contract-wheel-20261014
uv build "$MPA_STAGE_ROOT" --wheel --out-dir /tmp/veadk-mpa-contract-release-wheel-20261014
git diff --check
```
