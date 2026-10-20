# Managed MPA runtime role

[中文](2026-10-09-managed-runtime-role.zh.md)

Change ID: `mpa-runtime-iam`; created/revised: 2026-10-09; status: implemented; isolated verification passed, live smoke unverified.
Contracts: [Studio creation](../../../specs/studio-mpa-creation/README.md), [provisioning](../../../specs/mpa-runtime-provisioning/README.md).

## Background, goals and boundaries

The built-in Studio profile references `IDRoleForArkClawShareAgent` for both Runtime and Worker but never prepares it. A new deployment account can therefore fail during cloud creation. Read-only inspection of the historical role confirmed trust in `vefaas` and `apig` and 12 system policies; historical test/IDrive policies are not copied.

Prepare the approved role before other resource mutations. This does not make the entire Beijing profile portable: account assertions, images and Worker reference still require valid deployment configuration. General agents, legacy CLI defaults, custom roles, existing trust documents and policy bodies remain outside automatic mutation. No live IAM mutation, commit, push or deployment is authorized by design approval.

## Scenarios and requirements

- FR-1: Built-in Studio uses `managed.iam.mode: auto`; explicit managed profiles default to `existing` and skip IAM preparation. Auto mode accepts only the default Runtime/Worker role and a fresh template source; incompatible sources fail before IAM requests.
- FR-2: In the STS-verified deployment account, get or create the default role with unconditional `sts:AssumeRole` trust for `vefaas` and `apig`. Existing trust must contain both and no deny statements; never rewrite it. Validate returned role name and account TRN.
- FR-3: Add missing Global bindings for the 12 agreed system policies and versioned custom policy `VeADKMPARuntimeAccessV1`. Preserve extra bindings. The custom policy contains the 14 approved actions with resource `*`; a conflicting existing document fails without overwrite.
- FR-4: Explicit missing-object responses alone permit creation. Creation races reread after already-exists. Bounded polling handles visibility delay; timeout/cancellation retain resources for retry with the same agent ID. Requests use fresh verified credentials and isolated SDK instances with transport timeouts.
- FR-5: Emit stage `iam_role` and allowlisted errors for permissions, trust/policy conflicts, ownership and verification failure. Never expose raw SDK messages, documents or credentials. Failure stops before PG/network/Runtime preparation.
- FR-6: Add `iam:CreatePolicy` to the Studio execution policy; other necessary IAM actions already exist. Deployment credentials must be permitted to get/create role and policy, list bindings and attach policies. Configuration inspection performs no IAM calls.

## Permission baseline

System: `AgentKitSkillsSandboxAccess`, `AgentKitToolAccess`, `LLMShieldProtectSdkAccess`, `Mem0ReadOnlyAccess`, `AgentKitRuntimeAccess`, `AgentKitTosAccess`, `CloudControlReadOnlyAccess`, `TorchlightApiFullAccess`, `IDReadOnlyAccess`, `VikingdbFullAccess`, `APMPlusServerDataExportRolePolicy`, `AgentKitReadOnlyAccess`.

Custom: `arkclaw:ListResources`, `arkclaw:GetMpaInstanceConf`, `apig:ListGateways`, `apig:GetGateway`, `apig:CreateGateway`, `apig:CreateIMChannelGateway`, `apig:GetIMChannelGatewayStatus`, `apig:CreateUpstream`, `apig:CreateRoute`, `agentkit:DeleteSession`, `agentkit:PauseSession`, `agentkit:ResumeSession`, `agentkit:SetSessionTtl`, `agentkit:CreateSessionSnapshot`.

This is the user-approved compatibility baseline, not a claim of least privilege. ArkClaw actions are compatibility permissions. IAM resources are account-wide, independent of deployment region.

## Design, tasks and affected files

- T-1 (FR-1–6): Review this bilingual design and update both component contracts before implementation.
- T-2 (FR-1–4): Add failing isolated tests; implement `managed/iam.py` and configuration/profile integration. Additive reconciliation plus readback was chosen over cloning historical test policies or overwriting user trust. Poll for at most 120 seconds; each SDK request has 5-second connect/read timeouts. Cancellation stops new operations; an in-flight synchronous SDK call may finish within its transport limit.
- T-3 (FR-5–6): Integrate early in `managed/service.py`; map safe errors through `runner.py`/`tasks.py`; update diagnostics, bilingual UI resources and `frontend_deploy_policy.py`.
- T-4: Update bilingual managed usage docs, targeted Python and frontend tests; build release assets and verify browser behavior with isolated mock responses.

No new persistent tables or public request fields are needed. Existing IAM state is the recovery record. Policy and role creation are idempotent by fixed names; same-account concurrent creation converges by readback. A cancellation does not roll back shared permissions. Unsupported trust shapes fail conservatively.

## Acceptance and verification

AC-1: New role creation binds all 12 system policies plus the custom policy and verifies readback. AC-2: Reuse, missing attachments, races and delayed visibility converge without removing extras. AC-3: Permission failures, wrong account, unsafe trust and policy conflicts fail before unrelated mutations and produce safe errors. AC-4: Existing-mode profiles and general agents retain their behavior. AC-5: UI renders the role stage/error in both languages; built assets match sources.

Commands: `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py`; changed-file Ruff/Pyright; `npm --prefix frontend test`; `npm --prefix frontend run build`; `npm --prefix frontend run test:webui-assets`; `npm --prefix frontend run check:i18n`; regression `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`. Live new-account IAM smoke is not_run unless separately authorized. Browser checks must not touch real IAM/user state.

## Risks and review record

System policies can be unavailable in an account or require product enablement; fail visibly and retry after administrator repair. Existing trust restrictions are not automatically widened. Broad baseline permissions are intentional and documented; no real cloud snapshot is checked in. Shared role changes affect consumers of that role. SDK singleton isolation and cancellation require regression coverage.

Direct design review (review-spec unavailable): scope, additive semantics, bounded retries, credential rotation, no secret output, legacy compatibility, tests and bilingual equivalence reviewed; no unresolved design blockers. User approved the permission additions and implementation with “嗯，帮我改下，”. Approval precedes production/test edits. Existing `frontend/package-lock.json` changes belong to the user and are preserved.

## Implementation review and verification results

Tested scope: uncommitted `mpa-runtime-iam` feature on `feat/test-main`, base `ef0ad519`, 2026-10-09. T-1–4 and AC-1–5 are covered by isolated tests and browser checks; live new-account readiness remains unverified.

Implementation review corrected the provider binding shape to `PolicyScope[].PolicyScopeType: Global` and the official creation collision code to `PolicyAlreadyExist`. `PolicyAttachConflict` requires readback, never assumed success. Sources: [official IAM errors](https://docs.volcengine.com/docs/IAM/ErrorCodeList?lang=en) and [official SDK binding structure](https://pkg.go.dev/github.com/volcengine/volcengine-go-sdk@v1.2.45/service/iam#AttachedPolicyMetadataForListAttachedRolePoliciesOutput). New regression fixtures first failed for missing implementation and subsequently for the real collision/conflict codes; corrected implementation passes. Permission errors never authorize creation. Singleton isolation, fresh credentials, timeout/cancellation, trust/account conflicts, project-only bindings, retries and safe child errors were reviewed. No new blockers remain in the feature scope.

| Check | Outcome | Evidence / limits |
| --- | --- | --- |
| `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q` | pass | Final correction: 474 passed; no real cloud operations. |
| `uvx --from ruff==0.11.12 ruff check <changed-python-files>` and format | pass | Version matches repository hook; temporary tool environment. |
| `uvx pyright --pythonpath .venv/bin/python <changed-production-python-files>` | pass | 0 errors / warnings; repository interpreter. |
| `npm --prefix frontend test` | pass | 1,377 Node tests and 48 Vitest tests. |
| `npm --prefix frontend run build` | pass | TypeScript and both bundles built; existing chunk-size/deprecation warnings only. |
| `npm --prefix frontend run test:webui-assets` | pass | 113 packaged files, 350 references. Hash-renamed dependent chunks are generated assets. |
| `npm --prefix frontend run check:i18n` | pass | 2 locales, 21 namespaces consistent. |
| Isolated real Chrome browser (`node /tmp/mpa-iam-browser.cjs`) | pass | Chinese/English three-step flow, readonly ID, IAM error/stage, Enter-key same-ID retry, cancellation, 375px layout; all service responses mocked. Temporary fixture/server removed. First fixture load caused a Vite dependency optimization reload; warmed final runs passed without page errors. |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | Earlier iteration: 6,240 passed, 7 failed, 19 skipped, 2 xfailed, 2 collection errors. Six Harness failures lack `llama_index`; two self-host sandbox collection errors lack `anthropic`. One upload retry test captured other background-thread sleeps; isolated rerun passed (1 test). These paths have no feature diff. Final IAM race correction was validated with the 474-test affected suite rather than repeating dependency-blocked unrelated tests. |
| `uv run --extra dev pre-commit run --files <changed-python-files>` | pass | Ruff/check/format and gitleaks hooks passed; YAML hook skipped (no YAML files). Full `--all-files` is not_run because no commit is requested. |
| `git diff --check`; bilingual links/identifiers/permission baseline | pass | Paired designs/contracts present, links resolve and identifiers align. |
| Live IAM / real new-account creation | not_run | Separate cloud mutation authorization and isolated account setup required. |
| Codex/PI smoke, sidecar coverage, IME/empty-flow changes | not_applicable | No runtime/sidecar/input/empty-state contracts changed. |

Local environment lacked Ruff/Pyright; use of temporary tools is recorded here, not a machine-global configuration change. Existing package-lock modifications were preserved. No commit, push or deployment was performed. Existing hosted Studio execution policies need the added `iam:CreatePolicy` permission before this feature can prepare roles; updates are not deployed by this change. The built-in profile still asserts its configured account and uses configured image/reference resources; changing accounts requires updating those settings independently.
