# VeADK Studio E2E Workflow Scripts

These scripts exercise the backend APIs that the Studio frontend calls during
common UI workflows. They are intended for real Studio environments with
server-side cloud credentials configured. Release 1.1.0 also supports running
Studio in `provider=byteplus` mode.

## Custom A/B Debug -> Deploy -> Chat

Script:

```bash
python3 tests/e2e/studio/scripts/studio_custom_ab_deploy_chat_smoke.py \
  --config tests/e2e/studio/configs/custom_ab_deploy_chat.local.yaml
```

Create a local config first:

```bash
cp tests/e2e/studio/configs/custom_ab_deploy_chat.example.yaml \
  tests/e2e/studio/configs/custom_ab_deploy_chat.local.yaml
```

The workflow mirrors this UI path:

1. Open Studio and verify the backend has Volcengine AK/SK or STS credentials.
2. Go to Agents, add an agent, choose quick create, then custom mode.
3. Fill agent name and options.
4. Start debug mode.
5. Add one comparison group and change its model/prompt fields.
6. Start both temporary debug environments.
7. Send the same debug message to both environments.
8. Choose a winning configuration and generate the deployable project.
9. Fill deployment options and deploy to AgentKit Runtime / VeFaaS.
10. Connect to the deployed runtime and send a chat message.

The script does not click the browser UI. Instead, it calls the same backend
routes that the frontend calls, in the same product order, and verifies the
backend has produced real AgentKit/runtime effects.

## Credentials

Studio cloud credentials are checked through:

```text
GET /web/runtime-config
```

The response must report `credentials: true`. In Volcengine mode the Studio
server should have `VOLCENGINE_ACCESS_KEY`/`VOLCENGINE_SECRET_KEY` or an IAM
role/STS credential. In BytePlus mode it should have
`BYTEPLUS_ACCESS_KEY`/`BYTEPLUS_SECRET_KEY` or the equivalent IAM credential.
User authentication is still separate: use `studio.auth.cookie`,
`studio.auth.bearer_token`, or `studio.auth.local_user` for local no-SSO
development.

Do not commit local configs, cookies, bearer tokens, access keys, or generated
artifacts.

The execution conventions intentionally follow the existing
`agentkit-cli-autotest` practice where it applies to Studio: BytePlus uses its
own AK/SK instead of falling back to Volcengine credentials, cloud resources
created by a scenario should have an explicit cleanup path, and stdout/stderr
summaries are redacted before being printed.

## Manage -> Update -> Feedback Cases -> Delete Agents

Script:

```bash
python3 tests/e2e/studio/scripts/studio_manage_update_feedback_delete_smoke.py \
  --config tests/e2e/studio/configs/manage_update_feedback_delete.local.yaml
```

Create a local config first:

```bash
cp tests/e2e/studio/configs/manage_update_feedback_delete.example.yaml \
  tests/e2e/studio/configs/manage_update_feedback_delete.local.yaml
```

The workflow mirrors this UI path:

1. Open Agents and select an existing deployed agent.
2. Open details and check update capability.
3. Re-enter the custom options/update page and deploy the update into the same
   Runtime.
4. Verify the Runtime reports version `v2` or higher.
5. Chat with the updated agent.
6. Submit one thumbs-up and one thumbs-down response rating.
7. Open feedback cases, verify both cases exist, navigate each case back to the
   referenced chat session/event, delete one case, and verify it is gone.
8. Optionally delete explicitly configured runtimes, with name guards and
   AgentKit deletion verification.

Deletion is disabled by default. To test real deletion, list disposable runtime
IDs under `delete_agents.runtimes` and include `expected_name` or
`expected_name_contains` guards.

## Custom Knowledge Base -> Debug -> Deploy -> Chat

Script:

```bash
python3 tests/e2e/studio/scripts/studio_custom_kb_deploy_chat_smoke.py \
  --config tests/e2e/studio/configs/custom_kb_deploy_chat.local.yaml
```

Create a local config first:

```bash
cp tests/e2e/studio/configs/custom_kb_deploy_chat.example.yaml \
  tests/e2e/studio/configs/custom_kb_deploy_chat.local.yaml
```

The workflow mirrors this UI path:

1. Create a custom agent and enable 知识库.
2. For VikingDB, load the server-signed knowledgebase picker.
3. Start a temporary debug environment and send a test message.
4. Generate deployable project code and verify `KnowledgeBase` wiring exists.
5. Deploy to AgentKit Runtime.
6. Verify runtime `agent-info` reports a mounted knowledgebase and advertises
   `searchSources: ["knowledge"]`.
7. Query `/web/search?source=knowledge` through the runtime proxy.
8. Send a deployed chat message.

## Additional Workflow Scripts

All scripts live under `tests/e2e/studio/scripts` and take:

```bash
python3 tests/e2e/studio/scripts/<script>.py \
  --config tests/e2e/studio/configs/<config>.local.yaml
```

Use `--dry-run` to validate config shape and print the planned workflow without
calling Studio.

| Workflow | Script | Example Config | Main Backend Coverage |
| --- | --- | --- | --- |
| Short-term / long-term memory | `studio_memory_workflows_smoke.py` | `memory_workflows.example.yaml` | generated test run, generated project, deploy, `agent-info` memory components, optional `source=memory` search |
| Built-in/custom/MCP tools | `studio_tools_workflow_smoke.py` | `tools_workflow.example.yaml` | generated tool wiring, deploy, `agent-info` tools/toolsets, chat |
| Multi-agent workflow | `studio_multi_agent_workflow_smoke.py` | `multi_agent_workflow.example.yaml` | sequential/parallel/loop draft generation, deploy, runtime graph/sub-agent metadata, chat |
| Code package upload | `studio_code_package_upload_smoke.py` | `code_package_upload.example.yaml` | uploaded files -> `/web/deploy-agentkit`, runtime connect, chat |
| Existing runtime connect | `studio_existing_runtime_connect_smoke.py` | `existing_runtime_connect.example.yaml` | `/web/runtimes`, `/web/runtime-detail`, runtime proxy `list-apps`, `agent-info`, chat |
| Deploy/runtime options | `studio_runtime_options_smoke.py` | `runtime_options.example.yaml` | session storage, min/max instances, network mode, Feishu flag/env, runtime detail verification |
| Cancel deployment | `studio_cancel_deploy_smoke.py` | `cancel_deploy.example.yaml` | in-flight deploy SSE plus `/web/cancel-deploy-agentkit` cleanup request |
| Error surfacing | `studio_error_surface_smoke.py` | `error_surface.example.yaml` | invalid draft validation and invalid deploy option errors |
| Skill Space + A2A catalog | `studio_catalog_skill_a2a_smoke.py` | `catalog_skill_a2a.example.yaml` | `/web/skill-spaces*`, `/web/a2a-spaces`, optional catalog-backed agent generation/deploy |
| RBAC | `studio_rbac_smoke.py` | `rbac.example.yaml` | `/web/access`, create-agent enforcement, manage-agent enforcement |
| BytePlus basic | `studio_byteplus_basic_smoke.py` | `byteplus_basic.example.yaml` | `provider=byteplus` UI config, BytePlus credentials, `ap-southeast-1` runtimes, Skill/A2A/Viking probes, BytePlus codegen defaults, optional debug/deploy/chat |

## Master Suite

Copy and edit the suite config:

```bash
cp tests/e2e/studio/configs/run_all.example.yaml \
  tests/e2e/studio/configs/run_all.local.yaml
```

Then run:

```bash
python3 tests/e2e/studio/scripts/studio_run_all_smokes.py \
  --config tests/e2e/studio/configs/run_all.local.yaml
```

The suite config is just a list of script/config pairs. Keep expensive or
destructive workflows such as code-package upload, cancel deploy, RBAC, and
agent deletion disabled until their local configs point at disposable resources.

## Workflow Coverage Map

The current folder covers these Studio user paths:

1. Create custom agent, A/B debug, deploy selected config, chat.
2. Manage existing agent, update to v2, chat, submit thumbs up/down, inspect
   feedback cases, delete selected disposable agents.
3. Create agent with knowledgebase, deploy, verify knowledge search.
4. Create agent with short-term and/or long-term memory, deploy, verify memory.
5. Create agent with tools, deploy, verify runtime tools/toolsets.
6. Create multi-agent workflow, deploy, verify runtime graph.
7. Upload an existing code package and deploy it.
8. Open an existing runtime and chat through Studio's backend proxy.
9. Deploy with runtime options: network, session storage, scaling, Feishu.
10. Cancel an in-flight deployment.
11. Verify backend error responses are surfaced for invalid operations.
12. Browse Skill Space and A2A catalogs, optionally deploy a catalog-backed agent.
13. Verify Studio RBAC for create/manage operations.
14. Run basic BytePlus provider coverage: credentials, runtime list, catalog
    probes, code generation defaults, optional debug/deploy/chat.
