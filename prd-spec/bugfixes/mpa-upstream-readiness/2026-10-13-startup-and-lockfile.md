# MPA upstream PR startup and lock-file readiness

[中文版](2026-10-13-startup-and-lockfile.zh.md)

- Change ID: `mpa-upstream-readiness`; date: 2026-10-13; status: implemented.
- Scope: the four MPA lifecycle commits rebased onto official `b8038fb1`.
- Contracts: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md); [previous lock-file restoration](../frontend-lockfile-sync/2026-10-09-restore-esbuild-lock-entries.md).

## Evidence, requirements and scope

Full offline regression on `ea949fee` returned 7,184 passed, 2 failed, 53 skipped and 4 xfailed. Official `b8038fb1` in an isolated source snapshot passes the Studio startup test but reproduces the artifact-writer MIME test failure under the same local Python 3.10/macOS environment. The branch's new OV adapter eagerly imports `veadk.utils.volcengine_sign`, violating the existing lazy Studio startup contract. The deleted 512 lock-file lines also cause npm 10.9.2 (the frontend CI runtime family) to reject esbuild entries, despite npm 11 accepting them.

FR-1: Registering MPA routes/configuration must preserve the existing lazy startup boundary. Load the signing helper only when an OV API request runs. Preserve wire parameters, retry/error/cancellation behavior and provider boundaries.
FR-2: Restore the complete official frontend lock file. Package dependency declarations match official main; only test-script selection differs. Do not change dependency ranges or unrelated artifact-writer logic.

## Design, tasks and acceptance

T-1 / AC-1: Use the already failing isolated Studio startup test as the regression. Move the signing import into the existing request closure; point two adapter mock patches at the helper's owning module. Update the paired maintained OV startup contract.
T-2 / AC-2: Restore generated `frontend/package-lock.json` from `upstream/main` and repeat an isolated npm 10.9.2 `ci --ignore-scripts --dry-run` using Linux/x64 selection.
T-3 / AC-3: Rerun startup, managed/deployment/RBAC tests, affected frontend tests/coverage, lint/type checks and all-file pre-commit; record actual outcomes. Existing cloud operations, credentials, session identity and cleanup policies remain unchanged.

## Review, authorization and risks

Direct review (review-spec unavailable) confirms this is a correction within the already approved OV feature and previously approved lock restoration, needed to prepare the upstream PR the user explicitly requested. No new feature or cloud action is introduced. No speculative wrapper, dependency upgrade or unrelated MIME fix is needed. Keep the original published development branch; commit the corrections on the separate upstream PR branch. Local baseline failures must be disclosed, not hidden by skipping them or altering unrelated production behavior.

## Verification

Initial failing evidence above is recorded before correction. Final outcomes will be added after execution. Live cloud/OV smoke is not_run because no additional paid resource operation is authorized.

### Final preparation results (2026-10-13)

Scope: `ea949fee` plus this readiness correction, based on `b8038fb1`. AC-1–AC-3 complete.

- pass: 1,185 affected startup/managed/profile-route/RBAC tests after correction; no external services used. The global suite was not repeated because the correction only delays one signing import and restores generated metadata; the failing startup case and all affected deployment boundaries were rerun.
- pass: 1,389 Node tests, 95 React tests, production build, 22 sidecar coverage tests (lines 100%, branches 94.44%), i18n and packaged asset references. Build output remains byte-identical to the rebased tracked assets.
- pass: npm 10.9.2 isolated Linux/x64 `ci --ignore-scripts --dry-run` with the restored official lock; dependency declarations/ranges unchanged. This validates the lock graph, not a real Linux installation.
- pass: Ruff 0.11.12, Pyright (0 errors/warnings) for the corrected adapter/tests; all-file pre-commit including secret/YAML scans; paired-link/identifier/whitespace review.
- fail (baseline): the full local suite before correction had 7,184 passed, 2 failed, 53 skipped and 4 xfailed. Startup is fixed; `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes` also fails on unchanged official main under local Python 3.10/macOS (Markdown MIME resolves to `application/octet-stream`). That unrelated writer/test was not changed.
- not_run: additional paid cloud/OV smoke and real Codex/Pi smoke; no harness protocol changes or live-resource authorization.

The user explicitly authorized creating the official PR on 2026-10-13; this includes the necessary preparation commit and branch push, not merging or deployment. The original fork development branch remains unchanged. Actual commands:

```bash
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"
uv run --extra dev pytest -n 2 -q tests/cli/test_studio_startup_imports.py tests/integrations/mpa_managed tests/frontend/server/mpa/test_runtime_profile_routes.py tests/cli/test_studio_rbac.py
uv run --extra dev pre-commit run --all-files
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:harness-sidecar-coverage
npm --prefix frontend run check:i18n
npm --prefix frontend run test:webui-assets
```
