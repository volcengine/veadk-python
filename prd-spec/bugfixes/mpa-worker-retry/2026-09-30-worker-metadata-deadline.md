# Worker metadata stage deadline

[中文版](2026-09-30-worker-metadata-deadline.zh.md)

- ID: mpa-worker-metadata-deadline; created/revised: 2026-09-30; status: approved.
- Predecessor: [metadata visibility](2026-09-20-worker-metadata-visibility.md).
- Contract: [Studio creation CON-10](../../../specs/studio-mpa-creation/README.md).

## Evidence, goals and scope

Cloud diagnostics showed four incomplete ownership-tag observations during Worker initialization, followed by failure after 35 seconds. Read-only metadata inspection later showed the same Tool Ready with matching ownership, project and agent binding, approximately 151 seconds after creation. The source imposes a four-observation limit independently of the 600-second Worker deadline. The shared `ensure_worker` path serves managed Studio and CLI provisioning.

Wait for delayed ownership metadata within the existing deadline instead of failing early. Non-goals: TOS validation changes, image changes, HTTP/UI/schema changes, timeout extension, deployment, resource creation or live retries. Template readiness does not prove Sandbox/session/TOS execution.

## Requirements and design

- FR-1: Given complete persisted managed creation intent and recognized initialization status, missing ownership metadata is polled every 5 seconds until it becomes visible or the existing deadline/cancellation ends the operation. Remove the independent four-observation budget; do not use unbounded exponential sleep.
- FR-2: Ready with missing required metadata, conflicting present values, terminal/unknown states and incomplete creation intent retain fail-fast behavior. Intermediate complete initialization responses do not reset or extend the deadline. Preserve Worker binding and never create a second Tool during polling.
- FR-3: Preserve the diagnostic protocol's attempt range 1–4 by saturating the metadata observation counter at 4. Later events remain `metadata_pending`/`retrying`; bounded task history and redaction remain unchanged. Worker API error retries still have four attempts and 1/2/4-second waits.

Reuse `asyncio.wait_for` in `ensure_worker`; change only the missing-metadata branch of `worker.py`. No new configuration, dependency, persistence or public interface. Update CON-10 and the paired operator guide; legacy create paths and TOS credential boundaries are unchanged.

## Tasks and acceptance

| Requirement | Task | Acceptance / verification |
| --- | --- | --- |
| FR-1/3 | T-1: failing metadata regression, minimal loop fix | AC-1: more than four incomplete observations reach Ready, including interleaved complete initialization; fixed sleeps and valid saturated diagnostics |
| FR-2 | T-2: timeout/cancellation and existing security regressions | AC-2: continued polling ends at deadline/cancellation, keeps binding, creates nothing extra; strict negative cases pass |
| FR-1–3 | T-3: coverage, gates and paired documentation | AC-3: changed executable-line coverage >95%; affected/full Python tests, changed-file Ruff/Pyright, pre-commit and doc checks pass |

## Review and risks

User approval: “那你改下代码” approves the preceding proposal to wait within the stage timeout and retain strict Ready ownership checks. Direct design review (`review-spec` unavailable) covers callers, deadline/cancellation, conflicts, credential isolation, diagnostic bounds and bilingual equivalence; no blockers. Fixed polling increases reads versus exponential backoff but matches the existing readiness polling cadence and remains deadline-bounded. Missing TOS mount metadata remains independently strict and outside this confirmed ownership-tag defect.

## Verification record

2026-09-30 working diff:

- pass: test-first `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker_metadata.py -q` reproduced the defect before implementation (13 failed, 17 passed).
- pass: `uv run --extra dev python -c 'import pydantic_settings; import pytest; raise SystemExit(pytest.main(["tests/integrations/mpa_managed", "tests/cli/test_cli_mpa.py", "-q", "--tb=short", "--cov=veadk.integrations.mpa.managed.worker", "--cov-branch", "--cov-report=json:/tmp/veadk-worker-metadata-coverage-20260930.json", "--cov-report=term-missing"]))'` — 443 passed. Direct targeted collection initially encountered an existing lazy-import `pydantic.RootModel` ordering failure; initializing `pydantic_settings` before collection avoids it without a source/dependency change. Module line/branch coverage is 89%; changed executable-line coverage is 100% (3/3), satisfying >95%. Simulated metadata tests cover 4/30/200 incomplete observations, interleaved initialization, valid saturated diagnostics, cancellation/deadline, conflicts and unchanged creation counts.
- pass: changed-file Ruff 0.11.12 and Pyright, pre-commit all-files (including Gitleaks/YAML secret scan), new relative links and `git diff --check`. The first pre-commit run formatted the two changed Python files; its second run passed all hooks.
- fail: `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" -q --tb=short` — 6151 passed, 8 failed, 2 collection errors, 22 skipped, 2 xfailed, 6 subtests passed. Six Harness failures require absent optional `llama_index`; two self-host collection errors require absent `anthropic`; one GitHub delivery test makes an unmocked external request and timed out; one wheel metadata assertion expects `>=0.8.0` while unchanged `pyproject.toml` requires `>=0.8.5`. Those files/dependency declarations are unchanged by this fix; no Worker metadata test failed. AC-3's full-repository gate remains blocked, so the design remains approved rather than claiming all acceptance complete. No unrelated dependency/test changes are included.
- not_run: cloud/browser/deployment are outside this code-only change. Frontend test/build and Codex/provider smoke: not_applicable, no UI/generated assets or process/provider execution changes.

Direct implementation review confirms unchanged caller interfaces, strict ownership/TOS checks, bounded fixed polling under the existing wrapper deadline, cancellation propagation and retained bindings. Both document languages preserve FR/AC/T IDs and numeric limits. The branch was fetched and rebased against the existing PR's `superops/main` base before verification; already up to date. No running Studio process or cloud resource was modified.
