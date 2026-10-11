# Complete Studio AIDAP runtime permissions

[中文版](2026-09-23-complete-aidap-runtime-policy.zh.md)

- Change ID: `studio-mpa-aidap-permissions`
- Created/Revised: 2026-09-23
- Status: superseded
- Related component: [Studio MPA creation](../../../specs/studio-mpa-creation/README.md)
- Successor: [Complete MPA cloud runtime policy](2026-09-23-complete-mpa-cloud-runtime-policy.md)
- User approval: 2026-09-23, add every permission required by the automatic PostgreSQL Workspace flow.

## Background and evidence

Cloud Studio MPA creation now passes writable-state initialization but fails at the `admin_workspace` stage. Local deployments can succeed because they use operator AK/SK credentials, while a VeFaaS deployment normally uses STS credentials for `VeADKFrontendServiceRole`.

`PGCloud` invokes nine AIDAP operations: `DescribeWorkspaces`, `CreateWorkspace`, `DescribeWorkspaceDetail`, `DescribeBranches`, `DescribeComputes`, `DescribeWorkspaceEndpoint`, `DescribeDBAccounts`, `DescribeDatabases`, and `DescribeDBAccountConnection`. The default Studio policy currently grants only the five collection queries. It omits the create, detail, endpoint, and account-connection actions required by the same flow. This code-to-policy mismatch is confirmed; the exact provider error remains unavailable because this shell has no cloud credentials or log access.

Expected behavior is that a default cloud Studio deployment can run its supported automatic PostgreSQL preparation with its execution role. Actual behavior is that the role lacks four actions exercised at and after the failing stage.

## Goals and non-goals

Goals:

- Grant all nine AIDAP actions currently exercised by `PGCloud`.
- Refresh an existing `VeADKFrontendPolicy` during the normal `studio update` role-policy refresh.
- Add a regression test that ties the default policy to the automatic PG call surface.
- Preserve credential redaction, HTTP behavior, idempotency, and custom-role ownership.

Non-goals:

- Granting `aidap:*` or unrelated AIDAP administrative operations.
- Automatically rewriting customer-owned Studio roles.
- Changing AIDAP orchestration, retry behavior, Workspace lifecycle, or deploying the fix.

## Scenarios and requirements

- **FR-1:** Given the default Studio execution role, its custom policy contains all nine AIDAP actions required by `PGCloud`.
- **FR-2:** Given an existing default Studio role, `studio update` replaces the custom policy document and verifies the refreshed action set.
- **FR-3:** Given a customer-owned Studio role, the update flow does not replace its policy automatically; its operator must grant the same required actions.
- **FR-4:** The policy grants explicit actions only and does not add `aidap:*`.

## Design and contract impact

Add these missing actions to `FRONTEND_DEPLOY_POLICY`:

- `aidap:CreateWorkspace`
- `aidap:DescribeWorkspaceDetail`
- `aidap:DescribeWorkspaceEndpoint`
- `aidap:DescribeDBAccountConnection`

Together with the five existing actions, this exactly covers the methods called by `PGCloud`. `ensure_default_frontend_role_policy` already updates and verifies `VeADKFrontendPolicy`, so no IAM update algorithm change is required. Customer-owned roles remain untouched to preserve their ownership boundary.

The cloud credential source remains unchanged: local execution may use AK/SK, while VeFaaS reads role STS credentials. No credentials, provider responses, or connection strings are persisted or returned. The additional create permission authorizes the existing user-approved automatic Workspace operation; it does not introduce a new cloud side effect. API, configuration, state, concurrency, and compatibility contracts otherwise remain unchanged.

## Implementation tasks

- **T-1 (FR-1, FR-4):** Add a failing policy-completeness test for the exact nine-action set.
- **T-2 (FR-1):** Add the four missing actions to `veadk/cli/frontend_deploy_policy.py`.
- **T-3 (FR-2, FR-3):** Run existing default/custom-role refresh tests.
- **T-4:** Run affected MPA/CLI tests and changed-file static checks.
- **T-5:** After separate deployment authorization, update Studio and run a live cloud creation smoke test.

Affected files: `veadk/cli/frontend_deploy_policy.py`, `tests/cli/test_frontend_deploy_iam.py`, this bilingual PRD, and the bilingual Studio MPA creation component spec.

## Verification and acceptance

| Requirement | Task | Acceptance criterion | Verification | Result |
| --- | --- | --- | --- | --- |
| `FR-1`, `FR-4` | `T-1`, `T-2` | `AC-1`: the policy contains the exact required AIDAP subset and excludes `aidap:*` | `uv run --extra dev pytest tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q` | `pass`, 21 tests, 2026-09-23 |
| `FR-2`, `FR-3` | `T-3` | `AC-2`: default policy refresh and custom-role preservation tests pass | Same targeted test command | `pass`, 2026-09-23 |
| `FR-1` | `T-4` | `AC-3`: affected MPA and CLI regressions plus Ruff/Pyright pass | `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py tests/cli/test_studio_update_permissions.py -q`; `uv run --with ruff ruff check veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py`; `uv run --with pyright pyright veadk/cli/frontend_deploy_policy.py tests/cli/test_frontend_deploy_iam.py` | `pass`, 417 tests, Ruff and Pyright, 2026-09-23 |
| `FR-1`, `FR-2` | `T-5` | `AC-4`: deployed Studio passes `admin_workspace` and completes or reaches the next legitimate stage | Authorized `studio update` plus live creation | `not_run`; deployment not authorized |

Frontend tests/build are not applicable because no UI, browser behavior, or HTTP schema changes. A local policy test proves document completeness but not that IAM propagation or live AIDAP access succeeds.

## Risks and recovery

- IAM policy propagation may be delayed after update; retry only after the policy is visible.
- A service-side permission name mismatch or an unrelated account/project conflict may still fail the cloud smoke test; preserve sanitized diagnostics.
- Rollback removes the four actions and restores the known policy mismatch.

## Review and delivery record

Direct design review on 2026-09-23 checked policy scope, least privilege, existing-role refresh, customer-role ownership, credential handling, compatibility, testability, and bilingual equivalence. No blocking issue remains. The user explicitly approved adding all permissions used by this flow.

The regression test failed before the policy edit and named the four missing actions. After the edit, 21 focused permission tests and 417 affected MPA/CLI tests passed. Ruff, Pyright, bilingual identifier checks, and `git diff --check` passed. The repository-prescribed bare `uv run --extra dev ruff ...` command was `blocked` because Ruff is not declared in the current dev environment; the isolated `uv run --with ruff ...` equivalent passed. Deployment and live AIDAP verification remain `not_run` pending separate authorization, so lifecycle status remains `approved`.
