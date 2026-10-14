# Preserve owned-resource name preflight on MPA retry

[中文版](2026-10-14-owned-resource-metadata.zh.md)

Change ID: mpa-name-retry. Date: 2026-10-14. Status: implemented.
Contract: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md), CON-20; predecessor [name preflight](../../features/mpa-name-preflight/2026-10-13-runtime-name-and-workspace-labels.md), FR-3.

## Evidence and scope

Same-request retry after Runtime deployment receives runtimeNameTaken. Installed GetRuntimeResponse omits Tags, while ListRuntimes exposes them. Name checks require owner tags only from GetRuntime. Worker creation writes managed_by=mpa-deployment and mpa_agent_key=agent_suffix(account,region,agent_id), plus MPA_AGENT_ID in Envs; name preflight instead demands an MPA_AGENT_ID tag that creation never writes. Existing tests incorrectly emulate that tag and detailed Runtime tags. The observed Runtime Error/startup failure is a separate issue, not repaired here.

Goal: restore the approved own-resource retry guarantee while rejecting foreign/ambiguous matches. No change to frontend, request identity, scope hashing, cloud payload, resource mutation, Runtime startup, account credentials or generic agents. User's current retry-defect report and previously approved same-request recovery requirement authorize this correction; the concrete metadata-based plan was stated before edits.

## Requirements and design

- FR-1: Combine ownership evidence from the same matching ListRuntimes item and GetRuntime detail. Detail MPA_AGENT_ID must match; owner and optional instance tag must match. Conflicting owner/instance evidence in either response fails closed. Missing all owner evidence never authorizes a fresh request; original intents require the private proof in the amendment. Preserve existing CLI behavior without a Studio owner.
- FR-2: Worker identity requires matching environment MPA_AGENT_ID and canonical managed_by/mpa_agent_key tags, using the same account/region/agent suffix as creation. An arbitrary legacy MPA_AGENT_ID tag alone is insufficient. Missing or foreign canonical ownership still blocks.
- FR-3: Keep query timeout/cancellation, failure keys, Workspace checks, pagination, local reservation, private task owner/account snapshot and immutable retry inputs unchanged. No name-check bypass solely because the request ID exists; fresh same-name requests still fail.

T-1: Update unrealistic Worker fixture and write failing SDK-shaped Runtime/list-tag tests and foreign/conflicting/missing-tag cases in test_name_preflight.py. T-2: Fix names.py only using existing suffix/tags helpers. T-3: Run targeted name/worker/task/route tests, managed/startup regression, Ruff/Pyright and scoped repository secret/doc checks; perform separately identified read-only live preflight against the failed task if metadata can be verified.

## Contract assessment, review and acceptance

The maintained CON-20 already promises verified own-resource retry, so this repairs its implementation and test mapping without changing public contracts. Add only a bilingual verification/change link. review-spec unavailable; direct review confirms no weaker ownership requirement, no secret output, unchanged mutation boundary and equivalent languages. Existing default false positives are explained, not treated as permission to reuse unknown resources. No design blocker.

AC-1: Actual SDK-shaped detail without Tags and a matching list item allows original-request ownership; contradictions or missing/foreign owner fail.
AC-2: Creation's real Worker tag shape permits reuse; foreign/missing tags and copied legacy tags reject. Domestic and BytePlus use the same invariant.
AC-3: Required gates pass; no frontend/build required (not_applicable), no real task replay, service restart, commit or push. Read-only preflight evidence does not prove Runtime startup recovery.

## Verification and risks

2026-10-14, base 2ffe6e14 with unrelated local work retained. not_run: implementation checks pending. not_applicable: frontend/browser/harness/Codex gates, no affected UI or protocol. not_run: all-files pre-commit because no commit requested; scoped gates required. Provider list metadata can be eventually consistent; ambiguous ownership continues to block safely. Runtime Error may still cause readiness failure after the name check is fixed.

## Approved design amendment after live readback

Raw GetRuntime and ListRuntimes for the failed BytePlus Runtime both returned empty Tags, so SDK shape correction alone cannot authorize recovery. FR-1 is refined: absent owner tags may be accepted only for a server-authenticated original creation intent with identical normalized stored payload, matching private provider/account/region snapshot and matching server-derived MPA_AGENT_ID environment. Explicit foreign/conflicting tags still reject. CreationTasks.name_scope_for_request reads owner/request-scoped SQLite and rejects changed fingerprints. POST runs it after normalizing secret-free payload, before cloud name checks; public request/response fields do not change. Name preflight verifies the stored account against STS. The child already receives expectedAccount from the validated task snapshot; pass that existing proof into its name check, retaining all account and resource checks. Initial requests without such a saved intent remain strict. Never trust a browser-supplied retry flag. Additional affected files: tasks.py, service.py, frontend/server/mpa_creation.py, and corresponding task/route tests. No runner protocol expansion, resource writes or frontend rebuild is needed. This is a necessary completion of previously approved same-request recovery, not permission to reuse foreign or ambiguous resources. Direct review confirms the stronger fingerprint/account guards and resolves the original missing-owner assumption. Real read-only verification remains required.

2026-10-14 verification on local diff based on 2ffe6e14: pass, initial tests reproduced nine failures; private-proof amendment reproduced five failures before wiring. pass, name/routes targeted 37 tests; managed/startup regression 1,091 tests with two workers (four dependency warnings). pass, read-only actual BytePlus preflight: original stored inputs and derived agent identity/account matched, canonical Worker tags matched, original name accepted. No real task start, cloud mutation or restart was executed. This preflight does not repair the observed Runtime Error. Initial fixtures used an unsupported Profile.provider replacement and typed SDK constructor; corrected to values.cloud_provider and model_validate. Ruff/Pyright fixture imports/nullable assertions were corrected before final gates. Final static/secret/doc results recorded below. Frontend/build/browser/harness/Codex not_applicable: no UI/protocol change; supporting API regression is covered. All-files pre-commit/commit/push not_run: not requested. Unrelated local changes retained.

Final gates: pass, Ruff check/format and Pyright on all six affected Python files (zero errors/warnings); final name/route regression 37 tests; repository-configured Gitleaks on isolated scope; paired IDs/relative links and diff whitespace. Existing secret-scan exclusions for tests/build are unchanged. Final review confirms no public retry-proof input and private matching happens before cloud checks and task acceptance. No outstanding in-scope blocker.
