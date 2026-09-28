# Debug Session: mpa-admin-workspace-failure
- **Status**: [OPEN]
- **Issue**: Cloud Studio MPA creation passes local state initialization but fails while preparing the management PostgreSQL Workspace.
- **Debug Server**: pending
- **Log File**: `.dbg/trae-debug-log-mpa-admin-workspace-failure.ndjson`

## Reproduction Steps
1. Open the deployed Studio MPA creation dialog.
2. Complete the three steps and submit.
3. Observe `创建失败` at `准备管理 PG Workspace`.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | The deployed revision still uses the read-only `.adk` path | Medium | Low | Deployed revision or server log references `.adk/mpa-pg-bootstrap.sqlite3` |
| B | AIDAP Workspace APIs reject the deployment identity due to IAM permissions | High | Low | Provider error category/code indicates access denied |
| C | Built-in account, region, project, or Workspace identity conflicts with the active credential/resource | Medium | Medium | Verified account or Workspace metadata differs from expected values |
| D | Workspace creation succeeded but metadata/tags are not yet visible, or an earlier uncertain create conflicts | Medium | Medium | Create returns an ID followed by repeated incomplete/not-found metadata, or discovery finds conflicting resources |

## Log Evidence
- The UI reached stage `admin_workspace`. In `prepare_postgres`, that stage is emitted only after `BootstrapStore` initialization and lock acquisition, so the previous read-only `.adk` failure is no longer the active failure.
- `PGCloud.find()` next calls AIDAP `DescribeWorkspaces`; when no matching Workspace exists, `PGCloud.create()` calls `CreateWorkspace`.
- The deployed Studio role policy in `veadk/cli/frontend_deploy_policy.py` grants `aidap:DescribeWorkspaces`, `aidap:DescribeBranches`, `aidap:DescribeComputes`, `aidap:DescribeDBAccounts`, and `aidap:DescribeDatabases`, but does not grant `aidap:CreateWorkspace`, `aidap:DescribeWorkspaceDetail`, `aidap:DescribeWorkspaceEndpoint`, or `aidap:DescribeDBAccountConnection`.
- Direct cloud log/API inspection is currently unavailable in this shell because no local Volcengine credential profile or environment credential is available.
- On 2026-09-23 the user accepted the policy mismatch as sufficient evidence and requested all permissions used by the flow. A regression test failed before the fix with the four missing actions, then passed after the default policy was expanded to the exact nine-action `PGCloud` set. The affected 417 MPA/CLI tests also passed.
- The user then expanded the audit to every MPA creation stage. Static tracing found ten additional missing actions: `sts:GetCallerIdentity`; `ecs:DescribeZones`; `vpc:DescribeSubnetAttributes`, `vpc:CreateVpc`, `vpc:CreateSubnet`; and `apig:ListGateways`, `apig:CreateGateway`, `apig:GetGateway`, `apig:CreateIMChannelGateway`, `apig:GetIMChannelGatewayStatus`. Runtime, Worker, and Skill Space operations remain covered by `agentkit:*`. The expanded regression failed with exactly those ten actions before the fix and passed afterward.
- Debug event delivery now requires both `DEBUG_SERVER_URL` and `DEBUG_SESSION_ID`; normal cloud deployments make no localhost debug request.

## Verification Conclusion
| ID | Status | Evidence |
|----|--------|----------|
| A | Rejected | Reaching `admin_workspace` proves both local SQLite stores initialized before the reported failure. |
| B | Fix implemented locally; cloud confirmation pending | The default deployment policy now covers the complete directly invoked STS, ECS/VPC, APIG, AIDAP, and AgentKit operation set; deployment and live retry remain unauthorized. |
| C | Inconclusive | Requires a sanitized AIDAP response or cloud log. |
| D | Inconclusive | Requires a sanitized AIDAP response or cloud log. |

The most likely root cause is incomplete AIDAP permissions on the Studio execution role. The user explicitly accepted the policy mismatch as sufficient evidence, and the local policy fix is complete. Keep this session open until an authorized deployment and live retry confirm or reject hypothesis B.
