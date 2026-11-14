# Fix standard MCP session deadlock

[中文版](2026-10-26-standard-mcp-deadlock.zh.md)

- Change ID: `trusted-mcp-session-routing`
- Created/revised: 2026-10-26
- Status: `approved`
- Component contract: [Trusted MCP sessions](../../../specs/trusted-mcp-sessions/README.md)
- Baseline revision: `c662cc8d`; verification covers the working-tree session manager and two affected test files.

## Background and evidence

The supplied report describes VeADK 1.0.2 with Google ADK 2.1.0, MCP 1.26.0, and Python 3.12. A first standard streamable HTTP session, including Bearer authentication without `x-trusted-mcp`, waits indefinitely before connecting.

In `veadk/tools/mcp_tool/trusted_mcp_session_manager.py`, `create_session` acquires `_session_lock`, then calls `super().create_session(headers)` for a standard connection. The parent also acquires the same non-reentrant lock. A cache miss therefore waits for a lock that its own caller holds. A healthy cached session can return before reaching this defect. The trusted branch creates its own session and avoids the nested parent call.

The initially installed local parent implementation confirmed the nested-lock mechanism; that environment had Google ADK 1.18.0 and MCP 1.20.0. Repository metadata instead requires `google-adk>=2.7.0,<2.8.0` and `mcp==1.26.0`. Initial inspection was source evidence, not a runtime reproduction or verification of the reporter's dependency combination. Runtime checks now use the repository environment resolved by `uv`, as recorded below.

Existing `tests/tools/mcp_tool/test_trusted_mcp_components.py` covers trusted creation and healthy cache reuse; it lacks standard first-connection coverage.

## Goals and non-goals

Restore standard MCP connection creation through `TrustedMcpToolset`, retain trusted routing and authentication-based pooling, and prevent nested locking.

Dependency upgrades, new locks, transport redesign, broader trusted-session cancellation cleanup changes, release/version publication, cloud calls, and unrelated toolset configuration forwarding are outside scope. Public imports and signatures remain compatible.

## Scenarios and requirements

| ID | Given / when | Required result |
| --- | --- | --- |
| `FR-1` | Standard streamable HTTP, SSE, or stdio connection; first session requested | Delegate to the parent before acquiring the subclass session lock; connection creation can progress. |
| `FR-2` | Streamable HTTP with merged `x-trusted-mcp` exactly equal to `"true"` | Use `trusted_mcp_client`; keep the existing trusted session pool and cleanup behavior. |
| `FR-3` | Connection headers plus per-call headers, including a trust override | Use parent merge precedence. Routing inspection does not mutate either caller dictionary. Preserve authentication headers passed to the selected transport. |
| `FR-4` | Standard concurrent requests, repeated requests, or a disconnected cached session | Parent owns serialization, reuse, replacement, and resource cleanup; do not duplicate those operations. |
| `FR-5` | Standard connection failure or cancellation while waiting for the lock | Propagate the failure/cancellation. Release the lock so a later request can proceed; do not add silent success or new timeout behavior. |

An absent marker, `"false"`, or another nonmatching value selects the standard route. A marker on SSE or stdio never enables the trusted transport. Tests use synthetic authentication values and local transport doubles.

## Design and contract impact

Recommended approach: after `_merge_headers(headers)`, inspect connection type and the marker with `.get`, before generating a session key or acquiring `_session_lock`. For a standard route, return `await super().create_session(headers)` immediately, passing the original per-call headers so the parent applies its normal merge and lifecycle.

Only the trusted route executes the existing subclass session-key, lock, cache, disconnected cleanup, and `AsyncExitStack` operations. Generate the trusted session key before removing the trusted marker from the private merged copy for transport use. Remove the now-unreachable standard fallback inside the subclass lock.

Supported-baseline implementation review on 2026-10-26 found that Google ADK 2.7.1 calls `_create_client` with additional `mtls_transport` and `session_key` arguments. Accept and forward parent arguments through the existing override so ordinary creation can progress beyond the fixed lock. Trusted routing behavior remains unchanged. This necessary private-interface adaptation fulfills `FR-1`; no new public contract or product scope is introduced. Update the existing ordinary-cache test to use the current parent pool tuple `(session, exit_stack, loop)` rather than its obsolete two-element fixture.

Alternatives:

1. Replace the lock with a reentrant async lock: adds custom lock behavior and conflicts with parent lock ownership; unnecessary.
2. Copy parent session creation into the subclass: avoids nesting but duplicates transport and lifecycle behavior, increasing upstream compatibility risk.

This changes concurrency ownership for standard sessions, so the narrow bilingual component contract is required. No Studio, generated code, dependency metadata, permissions, event schemas, or deployment contracts change. No consumer migration is required. Existing user documentation is assessed during reconciliation; changing inaccurate general documentation beyond this routing defect requires separate scope.

## Tasks and affected files

| Task | Work | Requirements |
| --- | --- | --- |
| `T-1` | Review this bilingual PRD and `specs/trusted-mcp-sessions/README{,.zh}.md`; record user approval. | All |
| `T-2` | Add `tests/tools/mcp_tool/test_trusted_mcp_session_routing.py`. First prove standard creation times out before the fix, using the real parent session method with transport/session doubles and a bounded `asyncio.wait_for`. | `FR-1` |
| `T-3` | Apply early routing and parent client-argument forwarding in `veadk/tools/mcp_tool/trusted_mcp_session_manager.py`. | `FR-1`, `FR-2`, `FR-3` |
| `T-4` | Cover standard transport types, marker values/overrides, synthetic Bearer headers, trusted creation/reuse, concurrent creation, disconnected replacement, failure retry, and cancellation while waiting for the lock. Retain existing component tests, updating the ordinary-cache fixture for the parent pool tuple. | `FR-2`–`FR-5` |
| `T-5` | Run targeted and broader regression checks; review diff, resource ownership, and bilingual equivalence; reconcile documents with actual evidence. | All |

Task order: `T-1` → failing regression in `T-2` → `T-3` → remaining coverage in `T-4` → `T-5`. Record failed pre-fix evidence before implementation.

Execution plan (approved scope):

- [x] `T-1`: User approved code and test changes on 2026-10-26: “按这个方案修改代码和测试”.
- [x] `T-2`: Build an isolated transport fixture with real parent locking and session pooling. Run `uv run --extra dev pytest tests/tools/mcp_tool/test_trusted_mcp_session_routing.py -k standard_first_session`; expect a bounded timeout before any transport entry.
- [x] `T-3`: Insert `if not (isinstance(self._connection_params, StreamableHTTPConnectionParams) and merged_headers and merged_headers.get("x-trusted-mcp") == "true"): return await super().create_session(headers)` before key generation. Keep the trusted key, remove its marker from the merged copy before transport entry, and eliminate the locked parent fallback. Run the same first-session test; expect success.
- [x] `T-4`: Run all routing/component tests with isolated transport/session contexts, checking creation counts, identity reuse, header values, cleanup, failure propagation, and post-cancellation progress.
- [x] `T-5`: Execute the verification commands below, review the final source/test diff against `FR-1`–`FR-5`, update both languages and component status, and record actual results. Subsequent user instructions authorize a scoped commit and synchronization of local history to `origin/main`.

## Verification and acceptance

Use `uv run --extra dev` with current repository metadata. Do not treat the stale local environment as the supported baseline. Doubles replace network/process transports, not the parent lock implementation.

| Requirements | Tasks | Acceptance | Check | Current result |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-2`, `T-3` | `AC-1`: first standard creation fails with bounded timeout before the fix and succeeds after it | `uv run --extra dev pytest tests/tools/mcp_tool/test_trusted_mcp_session_routing.py -k standard_first_session -q` | `pass`: two pre-fix timeouts at nested locking; two post-fix successes |
| `FR-2`, `FR-3` | `T-3`, `T-4` | `AC-2`: trusted routing, merge precedence, caller headers, and authentication remain correct | `uv run --extra dev pytest tests/tools/mcp_tool -q` | `pass`: included in 24 passing tests |
| `FR-4`, `FR-5` | `T-4` | `AC-3`: standard lifecycle, concurrent reuse, failure retry, and lock-wait cancellation pass | `uv run --extra dev pytest tests/tools/mcp_tool -q` | `pass`: 24 tests passed in 3.05s |
| All | `T-5` | `AC-4`: broader affected regression passes | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | `fail`: 7556 passed, 17 failed, 58 skipped, 4 xfailed, 2 collection errors; 436.40s; two workers |
| All | `T-5` | `AC-5`: changed Python and document checks pass | Ruff 0.11.12 lint/format commands in the record below; `git diff --check`; paired-language/path/link review | `pass`: three Python files and both document pairs |

The user subsequently authorized commit and push to `origin/main`, including local history synchronization. Pre-commit is therefore required before committing. PR creation, package publication, and deployment are not authorized. Live cloud/provider and real trusted attestation checks are `not_applicable`: the bug is lock ownership before transport entry, and verification is isolated. Existing trusted component tests establish simulated compatibility, not real attestation.

## Risks and open questions

- Google ADK private methods can evolve; verify against the declared 2.7.x baseline. Testing the reporter's 2.1.0 combination would be additional compatibility evidence, not a dependency-policy change or release guarantee.
- Parent methods re-merge headers on standard delegation. The first merge must remain a side-effect-free routing inspection.
- Parent transport failures and cancellations after resources have been entered retain upstream semantics. This change guarantees no additional subclass-held lock; it does not promise to repair upstream cleanup issues.
- The existing trusted branch catches `Exception`, not all cancellation cases. Broadening that cleanup is outside this focused deadlock fix.
- Google ADK 2.7.1 uses three-element parent pool entries; the unchanged trusted branch stores two elements. Its inherited final `close()` compatibility is a pre-existing limitation outside this ordinary-routing fix. Trusted simulated tests explicitly close their owned stacks and do not claim inherited final-close compatibility.
- No unresolved product choice blocks this design. Supported-environment setup and targeted behavior are verified; the reporter's Google ADK 2.1.0/Python 3.12 combination remains untested.

## Review and delivery record

2026-10-26, baseline `c662cc8d`, actual diff scope: the session manager, new isolated routing tests, the existing ordinary-cache test fixture, and this PRD/component-spec pair.

Direct design review used because no `review-spec` skill is available in the supplied skill catalog. Reviewed ownership, feasibility, interfaces, errors, security, compatibility, testability, and bilingual equivalence. Findings resolved in design: route before locking; inspect headers without mutation; retain trusted key generation before marker removal; use the declared dependency baseline; distinguish source inspection from runtime evidence. No outstanding design blockers.

User approval: granted on 2026-10-26, “按这个方案修改代码和测试”. The scoped source/test changes and document reconciliation are complete. Final implementation review found no blocking in-scope correctness, concurrency, header-isolation, resource-ownership, or compatibility issues. `AC-1`, `AC-2`, `AC-3`, and `AC-5` pass. `AC-4` is not satisfied because the full repository gate fails outside this routing change; retain `approved` rather than claim all acceptance criteria are implemented. No unrelated fixes or package release are included.

Commit authorization was subsequently granted: “提交并推送到origin/main上”, “将本地历史一并同步到 origin/main”, and “提交代码”. The initial synchronization attempt was `blocked`: Git requires GPG signing, but the filesystem sandbox denied GPG's write to `~/.gnupg`. The rebase was aborted and all seven task files restored; no commit or push occurred. The backup stash remains available. Git hooks and signing configuration were not changed.

Commit preparation on 2026-10-26, unchanged baseline `c662cc8d` and the seven-file staged diff: `uv run --extra dev pytest tests/tools/mcp_tool -q`: `pass`, 24 tests in 4.09s. The initial `uv run --extra dev pre-commit run --all-files` was `blocked` by virtualenv cache writes outside the sandbox. Re-running with temporary cache configuration, `VIRTUALENV_OVERRIDE_APP_DATA=/tmp/veadk-mcp-precommit-virtualenv uv run --extra dev pre-commit run --all-files`: `pass` for Ruff lint, Ruff format, Gitleaks, runtime dependency policy, and YAML secret scanning. All hooks remained enabled. `git diff --cached --check`: `pass`. These are preparation checks before successful synchronization; required post-synchronization checks remain pending. The previously recorded full-regression failures remain unresolved.

Documentation verification on 2026-10-26: `pass` for both PRD/spec language pairs, matching requirement/task/acceptance/contract IDs, existing relative link targets, placeholder scan, and trailing whitespace; `git diff --check`: `pass`. These checks cover the four new design files and do not establish runtime behavior.

Implementation evidence on 2026-10-26:

- Environment resolved by `uv`: Python 3.11.14, Google ADK 2.7.1, MCP 1.26.0.
- Pre-fix first-session tests: `fail`, two `TimeoutError` results after 2s each, no transport entry, stack at the parent's lock acquisition.
- Post-fix first-session tests after fixture isolation correction: `pass`, two tests in 1.93s. The initial post-fix fixture exposed Google auth credential autodiscovery; the final fixture explicitly disables it and corrects memory-stream directions.
- Targeted final checks: `uv run --extra dev pytest tests/tools/mcp_tool -q`: `pass`, 24 tests, including 19 new tests and five retained component tests. The new fixture replaces external transports and trusted attestation with memory streams; ADK `SessionContext`, MCP initialization, local MCP server, discovery, and tool invocation are real.
- Initial combined run found an obsolete ordinary-cache tuple and a missing timeout argument in the trusted test fixture. Both test fixtures were corrected; no production workaround was added.
- `uv run --extra dev ruff check ...`: `blocked`, Ruff executable absent from the dev extra. Resolved without dependency metadata changes using the repository pre-commit version: `uvx --from ruff==0.11.12 ruff check veadk/tools/mcp_tool/trusted_mcp_session_manager.py tests/tools/mcp_tool/test_trusted_mcp_components.py tests/tools/mcp_tool/test_trusted_mcp_session_routing.py`: `pass`. The same files with `ruff format --check`: `pass`, all three already formatted.
- Existing upstream deprecation warnings remain; they do not indicate failed tests.
- Baseline comparison with the final isolated fixture: loaded the session manager source from `git show HEAD:veadk/tools/mcp_tool/trusted_mcp_session_manager.py` into a separate Python process and substituted only the toolset's manager class. `pytest.main(["tests/tools/mcp_tool/test_trusted_mcp_session_routing.py", "-k", "standard_first_session", "-q", "--tb=short"])`: `fail`, two expected lock timeouts, 17 deselected, 4.31s. This confirms the final fixture detects the original defect without changing working-tree files.

Full-regression findings:

- `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: `fail`, 7556 passed, 17 failed, 58 skipped, 4 xfailed, 52 warnings, 2 collection errors in 436.40s. All affected MCP tests passed. Skipped and xfailed tests are not evidence of passed behavior.
- Ten Codex runtime failures require the absent `openai_codex` optional package. Two self-host sandbox collection errors require the absent `anthropic` optional package. These dependencies are unrelated to MCP routing.
- Three failures attempted writes outside the workspace (Studio state and sibling application output); filesystem sandboxing rejected those paths. No broader filesystem access or machine configuration changes were requested.
- Four assertions failed in unchanged tests: Markdown artifact content type, two harness model configuration checks, and a sidecar child environment check. Avoid recording actual local model identifiers or raw environment values.
- Baseline confirmation: substitute the original manager class into both manager/toolset modules in a separate process, then run the following node IDs with `pytest.main([... , "-q", "--tb=no", "-o", "cache_dir=/tmp/veadk-mcp-baseline-pytest-cache"])`: all five failed in 6.87s, reproducing the corresponding failures with the pre-change manager:
  - `tests/frontend/server/runtime_artifacts/test_writer.py::test_success_uses_trusted_scope_and_hashes_utf8_bytes`
  - `tests/runtime/codex/test_codex_runtime.py::test_turn_usage_reports_this_turn_not_the_resumed_threads_total`
  - `tests/cloud/test_harness_app_http.py::test_harness_app_exposes_agent_info`
  - `tests/cloud/test_harness_app_http.py::test_harness_session_create_accepts_id_and_get_agent_config`
  - `tests/extensions/harness/sidecar_runtime/test_sidecar.py::test_run_wraps_child_with_sidecar_environment`
- A terminal polling retry restarted the full command after its sandbox-rejected result; the redundant run was interrupted rather than repeated. The completed 436.40s run above is the recorded gate result.
- User docs/examples were assessed: no API or configuration migration is needed for the existing trusted examples. No published version is claimed to contain this working-tree fix. Real trusted attestation and the reporter's exact dependency combination remain unverified; trusted final-close compatibility remains the documented pre-existing limitation.
