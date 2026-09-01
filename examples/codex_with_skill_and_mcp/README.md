# codex_with_skill_and_mcp

A `runtime="codex"` agent that uses **both a local skill and an MCP tool** on a
chat backend (Volcengine Ark).

```
codex_with_skill_and_mcp/
├── main.py                     # the agent + a sample run
├── mcp_server.py               # a tiny stdio MCP server (get_weather)
└── skills/
    └── weather-style/
        └── SKILL.md            # a local skill (how to phrase weather answers)
```

## What it shows

The agent has two tools wired the ordinary VeADK way:

- a **skill** — `SkillToolset(skills=[load_skill_from_dir(...)])`
- an **MCP tool** — `MCPToolset(...)` (stdio here; swap for streamable-HTTP)

Ask *"What's the weather in Beijing?"* and the agent should reply with the
skill's format using the tool's data, e.g.:

```
Beijing: sunny, 28°C. Have a nice day!
```

## How the codex runtime handles it

Codex runs the turn instead of ADK's LLM flow, and it only speaks the Responses
API — so the two tools take different paths:

- **Skill** → materialized into Codex's on-disk skill directory
  (`$CODEX_HOME/skills/<name>/SKILL.md`) and discovered by Codex's native skill
  system. Backend-independent.
- **MCP tool** → Codex can't be handed MCP tools directly (it presents them to
  the model as a `namespace` tool the chat backend rejects), so the runtime's
  Responses shim advertises them to the backend as plain `function` tools and
  executes them itself, invisibly to Codex.

Both are handled by the runtime — the agent code is just normal tool wiring.

## Run

```bash
pip install "veadk-python[codex]"   # openai-codex + the bundled Codex CLI binary
# Ark (or another OpenAI-compatible chat) credentials:
export MODEL_AGENT_API_KEY=...
export MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
export MODEL_AGENT_NAME=deepseek-v4-flash-260425

python examples/codex_with_skill_and_mcp/main.py
```

## Notes

- Tools are dispatched by the runtime shim, while calls, results, state
  changes, confirmations, and authentication surface as standard ADK events
  for Session/Trace/UI.
- Static authentication (headers / bearer tokens / ve-identity workload
  tokens) and ADK interactive authentication requested during tool execution
  are supported. Authentication required before an MCP toolset can list tools
  still depends on the corresponding ADK/MCP client capability.
- `runtime="codex"` is a *sandboxed-execution* runtime, not a drop-in
  replacement for the ADK flow. Part of the `Agent` surface is rejected outright
  under it (`sub_agents`, `output_schema`, `planner`, `code_executor`,
  `generate_content_config` beyond `system_instruction`, `include_contents="none"`,
  `enable_supervisor`, and an explicit `model=`), and more is dropped with a
  warning (`knowledgebase`, `example_store`, `skills_mode`, ...). See the
  [support matrix](../../docs/content/docs/framework/agent/runtime.en.mdx#support-matrix).
- Note the distinction this example relies on: ADK's `SkillToolset` is bridged
  into Codex's native skill system, but VeADK's own `Agent(skills_mode=...)` is
  **not** — that one warns and has no effect.
