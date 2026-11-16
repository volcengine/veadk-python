# CUA without VeADK

Minimal **Ark model → standard MCP client → AgentKit CUA sandbox** example.
No VeADK/AgentKit SDK imports, extra lifecycle implementation, or latency/token
statistics. [中文](README.zh.md)

```text
main.py             Model loop, MCP calls, screenshots and saved binding
requirements.txt    Independent dependencies
.env.example        Configuration reference
```

## Prepare and run

Create an authorized CUA-capable Tool in AgentKit. For desktop tasks, set
`ENABLE_COMPUTER=true` on the **sandbox template**. Grant its execution identity
`GetTool`, `ListSessions`, `GetSession`, `CreateSession` permissions; associate the
tool with Runtime when hosted. Model credentials and AgentKit credentials are separate.

Install `uv` (including `uvx`), then run in an independent Python 3.12 environment:

```bash
cd examples/cua_without_veadk
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt

export AGENTKIT_TOOL_ID='t-your-authorized-tool'
export ARK_MODEL='your-vision-model-or-endpoint'
export ARK_API_KEY='<model-key>'
export VOLCENGINE_ACCESS_KEY='<access-key>'
export VOLCENGINE_SECRET_KEY='<secret-key>'
export CUA_MCP_WHEEL_URL='https://browser-use-test.tos-cn-beijing.volces.com/agentkit-cua-mcp/1.0.0/agentkit_cua_mcp-1.0.0-py3-none-any.whl'

.venv/bin/python main.py \
  --session-id customer_task_001 \
  --state-file .state/customer_task_001.json \
  --prompt 'Take a desktop screenshot and describe what you see.'
```

This calls the model and may create a billable sandbox. The model must support
images and tools. Temporary AgentKit credentials also require
`VOLCENGINE_SESSION_TOKEN`; with both AK/SK absent, MCP uses the Runtime IAM file.
The program reads exported variables, **not `.env` automatically**; see
`.env.example` for optional TTL and creation-policy settings. No VeADK installation
or private repository access is needed. Verify a downloaded wheel with the adjacent
`.whl.sha256`; a verified local wheel path is also accepted.

For a browser task, change the prompt to: `Open the browser, visit
https://example.com, take a screenshot and tell me the page title.` The model
chooses tools; actions are not a hardcoded click sequence.

STG requires a matching ToolId/permissions and **both** settings below:

```bash
export AGENTKIT_TOOL_ENV=stg
export CUA_MCP_WHEEL_URL='https://browser-use-test.tos-cn-beijing.volces.com/agentkit-cua-mcp/1.0.0/revisions/dd3574c1f176/agentkit_cua_mcp-1.0.0-py3-none-any.whl'
```

Environment defaults to `prod`, region to `cn-beijing`. The original production
wheel does not support the STG switch; the client explicitly forwards it to MCP.

## Request flow

1. Start `uvx --from <wheel> agentkit-cua-mcp --transport stdio`.
2. Discover tools using `tools/list`, with the trusted application session in
   `_meta["veadk/cua"]`. This package namespace does **not** require VeADK.
3. Give schemas to the model; validate its arguments, then call one tool with the
   same metadata. MCP resolves/creates the sandbox lazily. `ensure_sandbox` is
   optional; do not call it during discovery or before every click.
4. Save returned physical binding metadata, including on action failure. Send
   tool text and **image content** to the model, without routing metadata.
5. Continue until the model answers; close MCP on exit. AgentKit owns instance
   expiry and cleanup, not the client process.

Reuse the same `--session-id` and state file for the same sandbox. This ID is the
application's logical `UserSessionId`, not the physical `SessionId`. Each run
starts a fresh model conversation: only the sandbox binding, not chat history,
is persisted. Use one active process per conversation and separate state files
for different accounts/identities/environments. After expiry/deletion, explicitly
start a new task with a new key and state file.

Discovery does not create instances. CUA-off templates expose only ensure;
explicit ensure can still create an instance while CUA is disabled. Multiple
model tool calls are all rejected before dispatch; one `cua_actions_batch` can
express a known supported sequence. Failed/partial/uncertain actions stop with a
nonzero exit code; do not retry mutations automatically. Terminal output contains
tool names/status and the final answer, not credentials or signed endpoints.

## Relation to AgentKit samples

Reference: [04-agentkit-tools](https://github.com/bytedance/agentkit-samples/tree/main/python/01-tutorials/04-agentkit-tools),
inspected commit `9fc58da287b9b2d5910047ca8519efea597189cb`.
Reuse its discovery/schema validation and saved-session patterns.
`sandbox_lifecycle_mcp` is a Streamable HTTP lifecycle gateway; this example uses
the separate CUA stdio package with different tools and request metadata.
Snapshot restore, pause and renewal are not implemented here.

When another entry creates the instance first, use the same authorized ToolId,
region/environment and UserSessionId so MCP can find it. The sample
`sandbox_lifecycle_http/03_invoke_session.py` uses physical `SessionId` with
`OperationType=RunCode` for code execution, not CUA actions. Do not guess missing
logical keys or attach arbitrary instances. This example registers neither
`run_code` nor `InvokeTool`.

## Verification scope

No HTTP server/Dockerfile is included; the functions can be embedded in
a customer's Agent service with trusted per-conversation routing.

On 2026-11-16 this example completed one authorized production-environment
smoke: real Ark model → public baseline wheel → one lazy-created sandbox → PNG
screenshot → model description. The persisted binding matched the platform
instance, and the test instance was deleted afterward. This was one screenshot
scenario, not STG, all-tool, browser-task or hosted Runtime certification.
