# Complete the Studio MPA cloud runtime policy

[中文版](2026-09-23-complete-mpa-cloud-runtime-policy.zh.md)

- Change ID: `studio-mpa-cloud-runtime-permissions`
- Created/Revised: 2026-09-23
- Status: approved
- Related component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)
- Predecessor: [AIDAP-only permission fix](2026-09-23-complete-aidap-runtime-policy.md)
- User approval: 2026-09-23, grant every permission used by all MPA creation stages, including VPC and APIG.

## Background and evidence

Cloud Studio uses `VeADKFrontendServiceRole` STS credentials, while a local deployment commonly uses an operator's broader AK/SK permissions. The initial audit found four missing AIDAP actions. The expanded code audit covers every direct cloud adapter reachable from `provision()`:

| Stage | Direct operations | Existing coverage before this revision |
| --- | --- | --- |
| Account check | `sts:GetCallerIdentity` | Missing |
| Automatic PG | Nine explicit `aidap:` actions | Complete after the predecessor fix |
| Network | `ecs:DescribeZones`; VPC describe/list/create operations | Missing `ecs:DescribeZones`, `vpc:DescribeSubnetAttributes`, `vpc:CreateVpc`, `vpc:CreateSubnet` |
| Gateway | APIG list/create/get and IM Gateway create/status operations | All five missing |
| Worker, Skill Space, Runtime | AgentKit get/list/create/update operations | Covered by existing `agentkit:*` |
| Database/OpenViking | PostgreSQL protocol and Runtime environment injection | No additional cloud IAM Action |

The policy mismatch can cause cloud-only failures at successive stages even when local creation succeeds.

## Goals and non-goals

Goals:

- Cover every cloud IAM Action directly exercised by the current MPA creation path.
- Keep the default role refresh idempotent for existing deployments.
- Add one regression test that documents the complete cross-service permission set.
- Preserve customer-owned role ownership and credential handling.

Non-goals:

- Granting `aidap:*`, `vpc:*`, `ecs:*`, or `apig:*`.
- Adding speculative actions not reached by the current implementation.
- Replacing the existing `agentkit:*` policy in this fix.
- Changing orchestration, API payloads, retry/state behavior, or deploying the change.

## Scenarios and requirements

- **FR-1:** The default Studio policy contains `sts:GetCallerIdentity`.
- **FR-2:** The policy contains all seven network actions used by `NetworkCloud`: `ecs:DescribeZones`, `vpc:DescribeVpcs`, `vpc:DescribeVpcAttributes`, `vpc:DescribeSubnets`, `vpc:DescribeSubnetAttributes`, `vpc:CreateVpc`, and `vpc:CreateSubnet`.
- **FR-3:** The policy contains all five APIG actions used by `GatewayCloud`: `apig:ListGateways`, `apig:CreateGateway`, `apig:GetGateway`, `apig:CreateIMChannelGateway`, and `apig:GetIMChannelGatewayStatus`.
- **FR-4:** The policy retains `aidap:DescribeWorkspaces`, `aidap:CreateWorkspace`, `aidap:DescribeWorkspaceDetail`, `aidap:DescribeBranches`, `aidap:DescribeComputes`, `aidap:DescribeWorkspaceEndpoint`, `aidap:DescribeDBAccounts`, `aidap:DescribeDatabases`, `aidap:DescribeDBAccountConnection`, and `agentkit:*` coverage required by automatic PG, Worker, Skill Space, and Runtime operations.
- **FR-5:** `studio update` refreshes the default role policy; customer-owned roles remain unchanged.
- **FR-6:** No new service wildcard is introduced for STS, ECS, VPC, APIG, or AIDAP.

## Design and contract impact

Add ten missing explicit actions to `FRONTEND_DEPLOY_POLICY`: one STS action, one ECS action, three VPC actions, and five APIG actions. Existing actions remain unchanged. The policy already contains the four VPC read actions and all nine AIDAP actions required by the flow, as well as `agentkit:*`.

`ensure_default_frontend_role_policy` already updates and reads back `VeADKFrontendPolicy`, so existing default deployments receive the expanded document on `studio update`. Customer roles are not modified automatically and must grant the same required actions themselves.

No secret, state, API, concurrency, network topology, or cloud resource lifecycle changes. Permissions authorize only operations the approved flow already attempts. A Runtime's bound role is a separate trust boundary; this change affects the Studio execution role, not Runtime workload permissions.

## Implementation tasks

- **T-1 (FR-1–FR-6):** Replace the AIDAP-only regression with a complete MPA cloud-policy test and confirm it fails before the policy edit.
- **T-2 (FR-1–FR-3, FR-6):** Add the ten missing explicit actions.
- **T-3 (FR-4, FR-5):** Run policy refresh and MPA integration regressions.
- **T-4:** Run Ruff, Pyright, bilingual consistency, whitespace, and default parallel Python regression.
- **T-5:** After separate authorization, deploy and retry one live MPA creation through all stages.

Affected files: `veadk/cli/frontend_deploy_policy.py`, `tests/cli/test_frontend_deploy_iam.py`, this bilingual PRD, the predecessor PRD, the bilingual component spec, and the active debug record.

## Verification and acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1`–`FR-4`, `FR-6` | `T-1`, `T-2` | `AC-1`: the default policy contains the complete explicit MPA set without new service wildcards | `uv run --extra dev pytest tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q` | `pass`, 22 tests, 2026-09-23 |
| `FR-5` | `T-3` | `AC-2`: default-role refresh and custom-role preservation pass | Same targeted command | `pass`, 2026-09-23 |
| `FR-1`–`FR-6` | `T-3`, `T-4` | `AC-3`: affected and default regression gates pass | Affected tests, Ruff, Pyright, bilingual/whitespace checks, and default parallel regression | affected/static `pass`; default regression `fail` on unrelated baseline/environment issues, 2026-09-23 |
| `FR-1`–`FR-5` | `T-5` | `AC-4`: deployed creation passes PG, network, gateway, worker, skills, Runtime, and readiness stages | Authorized deployment and live smoke | `not_run`; deployment not authorized |

Frontend tests/build are not applicable because no UI or HTTP schema changes. Static policy checks do not prove IAM propagation, service enablement, quotas, resource compatibility, or live network access.

## Risks and recovery

- Another service-side dependent permission may be enforced but not visible as a direct client call; live smoke remains required.
- IAM propagation may be delayed after update.
- Existing explicit denies, unavailable services, quota limits, or resource conflicts still take precedence.
- Rollback restores the known incomplete policy.

## Review and delivery record

Direct review on 2026-09-23 traced `provision()` through `RuntimeCloud`, `PGCloud`, `NetworkCloud`, `GatewayCloud`, `WorkerCloud`, and Skill Space/Runtime operations. It checked least privilege, service/action spelling, default-role refresh, customer-role ownership, security boundaries, compatibility, testability, and bilingual equivalence. The user approved the expanded all-stage scope.

The complete-policy test failed before the edit with exactly the ten audited missing actions. After the edit, 22 IAM/update tests and 418 affected MPA/CLI tests passed. `uv run --with ruff ruff check veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py`, the equivalent Pyright command, policy uniqueness, bilingual identifier, and `git diff --check` checks passed.

The required default regression ran as `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`: 5,216 passed, 11 skipped, 2 xfailed, 8 failed, and 2 collection errors. Six Harness failures and two Sandbox collection errors require undeclared optional `llama_index`/`anthropic` dependencies. Two optimized-Skill tests failed from parallel region-state interference and passed when rerun serially (2 passed). None touches the changed policy or test. Deployment and live MPA creation remain `not_run` pending authorization, so lifecycle status remains `approved`.
