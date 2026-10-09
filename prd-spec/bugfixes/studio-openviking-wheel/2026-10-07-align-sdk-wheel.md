# Align the Studio OpenViking wheel

[中文版](2026-10-07-align-sdk-wheel.zh.md)

- Change ID: `studio-openviking-wheel`
- Created/revised: 2026-10-07
- Status: implemented
- Scope: Studio dependency packaging; no cloud deployment or commit requested.

## Evidence and goals

`pyproject.toml` requires `openviking-sdk>=0.1.9`, and `uv.lock` resolves
0.1.9. However, `veadk/cli/studio_dependencies.py` still stages 0.1.4.
`build_local_studio_requirements(offline_runtime=False)` writes this wheel and
the local VeADK wheel into the same requirements list, creating conflicting
requirements. BytePlus provider staging also uses this list. Complete offline
builds already resolve from `uv.lock` and use 0.1.9.

Restore compatible packaging without changing SDK APIs, the dependency minimum,
the lockfile, MPA images, or running deployments. Do not redesign dependency
resolution or update unrelated pinned packages.

## Requirements and scenarios

- FR-1: For both `volcengine` and `byteplus`, the bundled OpenViking wheel must
  satisfy the project's declared SDK requirement.
- FR-2: Its version, filename, download URL and SHA256 must match the locked PyPI
  wheel. Existing staging and checksum failure behavior remain unchanged.
- FR-3: Regression checks must fail when the pin becomes older than the required
  minimum or differs from the locked artifact. Tests must not access cloud or
  package servers.

Given the current 0.1.4 pin, consistency tests fail. After alignment to the locked
0.1.9 artifact, both provider paths pass. Prepared caches containing only the old
wheel must be refreshed; a missing current wheel continues to fail explicitly.

## Design and contract assessment

Copy the 0.1.9 filename, URL and SHA256 from the committed lock into the existing
static wheel record. Update the deployment-test fixture. Add cross-file tests
using `packaging` and the existing TOML parser support, with no new dependency.
The alternative of downgrading the SDK requirement would conflict with its
updated options API and is rejected.

No component spec change is needed: this restores the existing declared SDK
compatibility and locked-artifact integrity rather than defining a new API,
configuration, state, permission or failure contract. Concurrency, cancellation,
session handling and UI behavior are unaffected. Existing checksum enforcement
remains in place; no credentials or external resource mutations are involved.

## Tasks and acceptance

| Requirement | Task | Acceptance |
| --- | --- | --- |
| FR-1 | T-1: add a regression test before the fix | AC-1: both provider pins satisfy the project requirement |
| FR-2 | T-2: update the wheel record and deployment fixture | AC-2: version, filename, URL and hash match `uv.lock` |
| FR-3 | T-3: run affected tests, lint/type and documentation checks | AC-3: pre-fix failures and post-fix passes are recorded |

Affected implementation/tests: `veadk/cli/studio_dependencies.py`,
`tests/cli/test_studio_dependencies.py`, `tests/cli/test_studio_deploy_target.py`.
Run the new tests, Studio release/deployment/offline-packaging tests and existing
OpenViking backend tests via `uv run --extra dev pytest`; run Ruff and Pyright on
changed Python files and `git diff --check`.

## Review, risks and delivery

- User approved the proposed 0.1.9 pin, URL/hash and test changes with “帮改下”.
- Direct design review (`review-spec` unavailable): scope, existing callers,
  dependency compatibility, error behavior, security and bilingual equivalence
  reviewed; no blocking findings.
- Updating the source does not change existing deployments. Rebuild/redeploy is
  required separately. Old prepared dependency caches need regeneration.
- Browser/frontend build: not_applicable; no UI, frontend source or web assets
  change. Cloud deployment and full Linux package build: not_run; this task
  validates the pin and packaging contracts locally without deploying resources.
- Implementation review: the diff changes only the OpenViking artifact and test
  fixture, adds cross-file regression coverage, and preserves staging behavior.
  Both document languages and their relative links were reconciled.

### Verification (2026-10-07, working diff on `056e8acd`)

| Check | Result |
| --- | --- |
| `uv run --extra dev pytest tests/cli/test_studio_dependencies.py -q` before fix | fail (expected): 4 failures, exposing 0.1.4 versus the SDK requirement and lock |
| Regression command below, 2 workers | pass: 192 tests, including all 4 new cases |
| `uv run --with ruff==0.11.12 ruff check veadk/cli/studio_dependencies.py tests/cli/test_studio_dependencies.py tests/cli/test_studio_deploy_target.py` | pass: repository-pinned Ruff version |
| `uv tool run pyright --pythonpath .venv/bin/python veadk/cli/studio_dependencies.py tests/cli/test_studio_dependencies.py` | pass: 0 errors |
| Same Pyright command including `tests/cli/test_studio_deploy_target.py` | fail: 10 existing errors at lines 1169, 1366, 1713 and 2424; identical diagnostics reproduced against the unchanged HEAD file in a temporary directory |
| `uv run --extra dev pre-commit run --files <all five changed files>` | pass: Ruff lint/format and secret scan; YAML hook not_applicable (no YAML files) |
| `git diff --check`, bilingual content/identifier/link review | pass |

```bash
uv run --extra dev pytest tests/cli/test_studio_dependencies.py tests/cli/test_studio_release.py tests/cli/test_studio_deploy_target.py tests/cli/test_studio_sidecar_prerequisites.py tests/cli/test_studio_offline_runtime.py tests/test_openviking_knowledgebase.py tests/test_openviking_long_term_memory.py -n 2 -q
```

An initial unpinned Ruff run reported 8 findings; the required repository-pinned
0.11.12 check passes without unrelated edits. The existing deployment-test type
errors remain visible and are not claimed as passing. T-1 through T-3 and AC-1
through AC-3 are complete; live deployment remains outside this change.
