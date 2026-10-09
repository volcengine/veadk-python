# Persistent MPA Runtime MCP secret

[中文版](2026-10-07-persistent-mcp-secret.zh.md)

- Change ID: `mpa-runtime-mcp-secret`; date: 2026-10-07; status: implemented.
- Contracts: [Runtime provisioning](../../../specs/mpa-runtime-provisioning/README.md), [Studio creation](../../../specs/studio-mpa-creation/README.md).

## Background and scope

Both legacy provisioning and managed Studio/CLI creation omit `MCP_TOKEN_SECRET` by default. MPA consequently uses a process-local secret that cannot verify tokens after replacement or across replicas. The user explicitly requested implementation from the main branch after agreeing to generate once and retain the configured value.

The scope is provisioning configuration, persistence, reference-template isolation, and secret masking. MPA JWT format, Meegle OAuth, frontend flows, automatic modification of existing deployments, and live cloud releases are outside this change.

## Requirements and design

- `FR-1`: Fresh creation injects a cryptographically random 32-byte secret, encoded as 64 hexadecimal characters, into Runtime environment variables. Blank values count as missing.
- `FR-2`: An explicit nonblank value wins. Otherwise reuse the target Runtime's nonblank value before generating a replacement. Do not mutate caller-owned environment dictionaries.
- `FR-3`: Creation, endpoint/key finalization, and retries use the same secret. Managed creation stores `mcp_token_secret` in the agent's PostgreSQL `mpa_deployment_settings` table before CreateRuntime. Atomic insert-or-retain handles retries and concurrent generation; explicit/current values reconcile the stored value only after validating any pending request hash, so rejected retries cannot replace its saved secret. Dispose connections on success and failure, and propagate database errors before cloud creation.
- `FR-4`: Reference Runtime templates exclude `MCP_TOKEN_SECRET`, so a new Agent gets its own secret. Explicit JSON-template values remain supported. Dry-run output masks explicit values; normal results and nonsecret deployment registry records exclude the secret.
- `FR-5`: Legacy provisioning persists through Runtime environment values. Lost-response name lookup reuses the existing resource and its secret. Existing managed unfinished requests with incompatible hashes remain blocked under the existing recovery contract.

No signatures, OAuth permissions, or credential access scopes change. Use existing standard-library `secrets`, SQLAlchemy, and Runtime SDK objects. PostgreSQL storage has the same access boundary as the agent database; Runtime env is still the verification source of truth. Random generation during dry-run is unnecessary. No new UI or dependencies are needed.

## Tasks and acceptance

| Requirement | Task | Acceptance | Verification |
| --- | --- | --- | --- |
| FR-1, FR-2 | T-1: legacy Runtime injection | AC-1: generation, explicit/blank values, reuse, and unchanged input | `tests/integrations/test_mpa_runtime.py` |
| FR-3 | T-2: durable managed secret and injection | AC-2: retries/finalization retain secret; failures dispose connections | managed database and deployment tests |
| FR-4 | T-3: reference isolation and masking | AC-3: reference secret excluded and output masked | managed deployment and environment tests |
| FR-1–FR-5 | T-4: regression, incremental coverage, lint and review | AC-4: incremental executable-line coverage >95%; required checks recorded | pytest-cov, diff coverage, pre-commit, Pyright |

Affected files: `mpa_runtime.py`, `mpa_provision.py`, `managed/runtime.py`, `managed/database.py`, their existing tests, and the two linked bilingual contracts.

## Review and verification record

Direct design review performed because `review-spec` is unavailable: ownership, retries, secret isolation, database cleanup, error propagation, compatibility and bilingual equivalence checked; no design blockers. User approval: explicit implementation request in this chat on 2026-10-07, building on the previously agreed generate-once/persist behavior. User instructions authorize commit/push after checks.

Verification on 2026-10-07, branch `fix/mpa-runtime-mcp-secret`, against `superops/main` at `056e8acd0096b6b7b0ee8203ef0f4f11f1efbfcc`:

| Check | Outcome | Evidence |
| --- | --- | --- |
| Regression before implementation | pass | Missing secret, reuse and managed persistence tests failed before the corresponding fix; rejected changed-secret retry also reproduced before moving persistence after hash validation. |
| Changed test files | pass | 93 tests, including 21 added parameterized cases. |
| Coverage and deployment edge contracts | pass | 113 tests; added executable lines covered: 23/23 (100%), computed by intersecting `git diff --unified=0 superops/main` with coverage XML line hits. |
| Affected managed creation regression | pass | 478 tests on repeat and in the final post-sync coverage run; main baseline has 457 tests. Initial run had one transient failure in the unchanged subprocess diagnostic test; repeat passed. |
| Pre-commit and whitespace | pass | `uv run --extra dev pre-commit run --all-files` and `git diff --check`; Ruff and secret scans passed. |
| Pyright on eight changed Python files | fail (baseline) | 34 diagnostics on both this branch and main, with identical file/message/rule sets; no added diagnostics. Existing SDK alias constructor declarations and fake-client optional attributes cause the failures. |
| Full unrelated repository regression | not_run | Scope is MPA provisioning only, with no shared dependency or runtime execution changes; affected managed creation regression was used. |
| Live cloud/PostgreSQL/Feishu | not_run | Offline SDK/database fakes only; this task authorizes source changes, not a cloud deployment. |

Coverage collection encounters an SDK/Pydantic lazy-import error on both main and this branch. Preloading the unmodified SDK before enabling pytest-cov avoids that interaction without replacing the SDK or changing application behavior:

```bash
uv run --extra dev python - <<'PYTEST'
import agentkit.sdk.skills.types
import pytest
raise SystemExit(pytest.main([
    "tests/integrations/test_mpa_runtime.py",
    "tests/integrations/test_mpa_provision_env.py",
    "tests/integrations/mpa_managed/test_agent_deployment.py",
    "tests/integrations/mpa_managed/test_deployment_database_unit.py",
    "tests/integrations/mpa_managed/test_runtime_deployment_edges.py",
    "-q", "--tb=short",
    "--cov=veadk.integrations.mpa.mpa_runtime",
    "--cov=veadk.integrations.mpa.mpa_provision",
    "--cov=veadk.integrations.mpa.managed.runtime",
    "--cov=veadk.integrations.mpa.managed.database",
    "--cov-report=xml:/tmp/mpa-mcp-secret-coverage.xml",
]))
PYTEST
```

For the broader affected run, also preload `from pydantic import RootModel`, then use the managed test directory plus the two legacy test files without coverage. Pyright uses the project `.venv/bin/python` via `--pythonpath`; compare baseline diagnostics instead of claiming a clean type check.

Implementation review: explicit configuration wins; blank values generate/reuse correctly; active Runtime values reconcile the durable value; retries preserve request identity; reference templates exclude the secret; caller dictionaries and public results remain safe; database engines dispose on success and failure. T-1 through T-4 and AC-1 through AC-4 are complete within the offline scope.

Risks: database preparation now requires writing the agent-owned settings table; callers explicitly overriding a key perform an intentional rotation. Existing unfinished pre-change requests with incompatible hashes still require their existing recovery procedure. Secrets must never appear in reports or fixture snapshots.
