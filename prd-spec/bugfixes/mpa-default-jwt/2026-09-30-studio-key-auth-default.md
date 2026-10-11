# Restore the Studio MPA JWT bypass default

[中文版](2026-09-30-studio-key-auth-default.zh.md)

- Change ID: `mpa-studio-key-auth-default`
- Created/revised: 2026-09-30
- Status: approved
- Contract: [MPA Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md)
- Predecessor: [A2A discovery defaults](../2026-09-23-mpa-a2a-discovery-default.md); supersedes only its JWT default decision.

## Background and scope

`build_runtime_env` currently injects `DISABLE_JWT_AUTH=false`. Studio uses the
Runtime API key, not a legacy `X-Jwt-Token`, so JWT-gated REST calls such as file
download can fail. The user explicitly requested changing this existing PR's
default to `true`. Both managed flat creation and `veadk mpa create` consume the
shared helper; referenced Runtime/templates use their own environments.

Goals: restore the shared default and retain explicit overrides. Non-goals:
cloud deployment, existing Runtime/session migration, image builds, frontend
changes, JWT issuance, or enabling `MPA_AGENTKIT_MODE`.

## Requirements and design

- `FR-1`: Given fresh flat inputs without an override, the generated environment
  contains `DISABLE_JWT_AUTH=true`, `ENABLE_A2A=true`, and
  `A2A_TIP_VERIFY_ENABLED=false`; outer gateway key-auth is unchanged.
- `FR-2`: Given explicit `extra_env` or `managed.runtime.env` with
  `DISABLE_JWT_AUTH=false`, it wins without mutating the input mapping.
- `FR-3`: Existing Runtime/template environments and deployed resources are not
  automatically changed. `MPA_AGENTKIT_MODE` remains unset by this helper.

Change one default in `build_runtime_env`, not its callers. Reuse the existing
override mechanism and regression tests; add no configuration or dependency.
There are no schema, persistence, concurrency, or retry changes.

Security: bypassing the inner legacy REST JWT gate also affects admin checks
and header-based identity, not just download. APIG key-auth remains required;
trusted Studio/gateway callers must control user headers. Endpoints that obtain
a Runtime principal directly are not fixed by this flag. With a compatible
MPA image, `/list-apps` may advertise ADK instead of forcing A2A discovery;
this change does not guarantee transport compatibility or migrate old sessions.
Operators needing legacy JWT must explicitly set `false`. Recovery is an
explicit configuration override and release, not an automatic rollback.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`: update default and paired contracts/docs | `AC-1`: default and managed create payload match | `test_mpa_provision_env.py`, `mpa_managed/test_service.py`, CLI regressions | pass: 460 focused tests |
| `FR-2` | `T-2`: regress explicit override | `AC-2`: explicit false wins, other settings unchanged | Existing helper/managed override tests | pass: included in focused tests |
| `FR-3` | `T-3`: verify scope and gates | `AC-3`: no cloud writes, mode unset, source retained | Diff review, focused tests, full regression, Ruff/Pyright/pre-commit | Scope pass; gate limitations below |

Use `uv run --extra dev pytest` for affected tests, plus coverage for
`veadk.integrations.mpa.mpa_provision` and changed executable lines (required
incremental coverage above 95%). Full regression:
`uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`.
Run Ruff and Pyright on changed Python files, and
`uv run --extra dev pre-commit run --all-files`. No provider credentials are
required. Live cloud/download E2E is `not_run`: outside this code-only request.

## Review and delivery

2026-09-30: direct design review (`review-spec` unavailable) checked shared
callers, override precedence, security/discovery changes, testability, scope,
and bilingual equivalence. No design blockers. Approval is the user's explicit
request to restore `true` in the existing PR. Implementation is complete;
repository-wide gate limitations keep the design status `approved`.

Verification on 2026-09-30, changes on `42120304`, synchronized with
`superops/main` (`6fba185d`):

- Regression-first: default assertion failed before the fix (`false != true`).
- Focused command: `uv run --extra dev python -c 'import pydantic_settings; import pytest; raise SystemExit(pytest.main(["tests/integrations/test_mpa_provision_env.py", "tests/integrations/mpa_managed", "tests/cli/test_cli_mpa.py", "--cov=veadk.integrations.mpa.mpa_provision", "--cov-branch", "--cov-report=term-missing", "-q"]))'`:
  **460 passed**. The preload avoids the existing focused collection
  import-order problem without changing dependencies.
- Coverage: the constant has no independent executable coverage line. Its
  enclosing dictionary assignment (line 162) is covered **1/1 (100%)**, with
  no new branch. Module combined statement/branch coverage: **96.77%**;
  statement coverage: **98.98%**.
- Full parallel regression using the command above: **6152 passed, 7 failed,
  2 collection errors, 22 skipped, 2 xfailed**. Six Harness failures lack
  optional `llama_index`; two self-hosted collection errors lack `anthropic`;
  the unchanged wheel test expects SDK `>=0.8.0` instead of declared `>=0.8.5`.
  These failures are outside this change; full regression is not a pass.
- Ruff: pass via `uv tool run --from ruff==0.11.12 ruff check` on all three
  changed Python files. Direct `uv run ruff` / `uv run pyright` cannot find
  those tools in the project environment, so isolated runners were used.
- `uv tool run --from pyright pyright --pythonpath .venv/bin/python` on all
  three changed Python files reports two diagnostics in unchanged
  `test_service.py` lines 78/137 (optional template, dynamic `_credentials`).
  The production helper and environment test alone pass with zero diagnostics.
- `uv run --extra dev pre-commit run --all-files`: pass, including Ruff format
  and both secret scans. Diff whitespace, bilingual requirement IDs, and
  relative Markdown links: pass.
- Frontend build/browser: not_applicable; no frontend code/assets changed.
  Contracts, paired managed READMEs, and `frontend/README.md` are synchronized.
  Cloud deployment/download E2E: not_run, outside this code-only request.
