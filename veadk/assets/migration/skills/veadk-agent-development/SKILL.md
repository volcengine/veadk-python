---
name: veadk-agent-development
description: Build, run, and ship AI agents with veadk-python (VeADK) — the Volcengine Agent Development Kit built on Google ADK. Covers the Agent/Runner API, tools, short/long-term memory, knowledge bases, serving on :8000, local iteration, and deploying to Volcengine AgentKit via the agentkit CLI. Use when writing or modifying a veADK agent, adding tools/memory/RAG, or preparing an agent for deployment. Does NOT handle non-VeADK agent frameworks (LangChain, CrewAI, etc.), general Python web development, AgentKit CLI operations (use agentkit-cli skill for that), or source-to-VeADK migration (use source-to-veadk skill for that).
---

# VeADK Agent Development

Practical, example-driven guidance for building agents with **veadk-python** (VeADK). VeADK
wraps Google ADK and Volcengine models/services so you can go from an idea to a
working agent quickly. Optimize for a tight loop: **scaffold → edit instruction/tools
→ run locally → publish with CLI → invoke**.

This skill includes a lightweight `agentkit` CLI publish path for smoke-testing a VeADK
agent. For cloud deployment, runtime binding, or delivery architecture, use the
`agentkit-cli` skill.

For a high-code Agent + App starting point, prefer the current CLI templates
listed by `agentkit init --list-templates` (for example `--template basic` or
`--template agent_server`). Repository template directories may exist as assets,
but they are not necessarily accepted by the installed CLI.

For exact API signatures and source, use **`references/veadk-python-index.md`** — a
retrieval map of the veadk-python repo (locate the file, then read it; don't guess).
For component selection, VeADK entrypoints, resource requirements, and default exposure
behavior, read **`references/components.md`**.

## When to Use This Skill

- Creating a new VeADK agent or editing an existing one
- Adding tools (built-in or your own functions), memory, or a knowledge base (RAG)
- Choosing how to wire VeADK components such as model, prompt management, session,
  memory, knowledge, tools, security, observability, skills, or frontend/extensions
- Serving an agent over HTTP (:8000) for local and deployment compatibility
- Running a simple `agentkit` CLI publish/invoke smoke check before cloud handoff
- Debugging "agent won't start / won't answer" issues

## Setup

```bash
pip install veadk-python            # core; add [extensions] only if you need
                                    # llama-index / redis / opensearch backends
```

Model credentials (local dev): VeADK defaults to a Volcengine Ark (doubao) model and
reads the key from the environment / a `.env`:

```bash
# .env
MODEL_AGENT_API_KEY=<your-ark-api-key>     # required locally to call the model
VOLCENGINE_ACCESS_KEY=<ak>                 # only for tools/memory/knowledge that hit Volcengine
VOLCENGINE_SECRET_KEY=<sk>
```

On a deployed AgentKit runtime the model's Ark credential is resolved from the runtime's
mounted IAM role / AK-SK — you do **not** set `MODEL_AGENT_API_KEY` there.

## Core: a minimal agent

`Agent` carries the model + instruction + tools; `Runner` drives it.

```python
from veadk import Agent, Runner

agent = Agent(
    name="assistant",                    # MUST be a valid identifier: [A-Za-z_][A-Za-z0-9_]* — no hyphens!
    description="A helpful assistant.",   # used in A2A scenarios
    instruction="You are concise and helpful. Use your tools when relevant.",
    # model_name defaults to VeADK's default doubao model; override to pin one:
    # model_name="doubao-seed-1-6-250615",
)

runner = Runner(agent=agent, app_name="assistant")

# run() is async and takes a list of messages + session identity:
import asyncio
output = asyncio.run(runner.run(messages=["Hello!"], user_id="u1", session_id="s1"))
print(output)
```

Key `Agent(...)` params: `name`, `description`, `instruction`, `model_name`,
`tools`, `runtime` (`"adk"` default | `"codex"`), `knowledgebase`,
`short_term_memory`, `long_term_memory`, `skills`.

## Tools

**Your own tool = a plain function with type hints + a docstring.** The docstring is what
the model reads to decide when/how to call it — write it well.

```python
def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English city name, e.g. "Beijing".
    Returns:
        A dict with a human-readable "result".
    """
    return {"result": f"Sunny in {city}"}

agent = Agent(name="assistant", instruction="...", tools=[get_city_weather])
```

**Built-in tools** — reference by name:

```python
from veadk.tools import get_builtin_tool, list_builtin_tools

list_builtin_tools()
# ['coding', 'get_city_weather', 'image_edit', 'image_generate', 'link_reader',
#  'parallel_web_search', 'run_code', 'text_to_speech', 'vesearch',
#  'video_generate', 'web_fetch', 'web_search', ...]

agent = Agent(name="assistant", instruction="...",
              tools=[get_builtin_tool("web_search"), get_builtin_tool("run_code")])
```

## Memory

```python
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.memory.long_term_memory import LongTermMemory

stm = ShortTermMemory(backend="local")          # session store: local | sqlite | mysql | postgresql
ltm = LongTermMemory(backend="viking", app_name="my-agent")   # cross-session: viking | opensearch | redis | mem0

agent = Agent(name="assistant", instruction="...",
              short_term_memory=stm, long_term_memory=ltm)
runner = Runner(agent=agent, short_term_memory=stm, app_name="assistant")
```

Reuse the same session id across `run()` calls to continue a conversation.

## Knowledge base (RAG)

```python
from veadk.knowledgebase import KnowledgeBase

kb = KnowledgeBase(backend="viking", app_name="my-agent")   # viking | opensearch | redis
agent = Agent(name="assistant", instruction="...", knowledgebase=kb)
```

Non-`viking` backends (llama-index / redis / opensearch) require `veadk-python[extensions]`.

## Serving and Deployment

A deployed agent must be an HTTP server listening on **`0.0.0.0:8000`** (the runtime's
readiness probe). Two options from `agentkit.apps`:

**A. `AgentkitSimpleApp`** — minimal `/ping` `/health` + one entrypoint. Good for a single
request/response agent.

```python
from veadk import Agent, Runner
from agentkit.apps import AgentkitSimpleApp

app = AgentkitSimpleApp()
agent = Agent(name="assistant", instruction="You are helpful.")
runner = Runner(agent=agent, app_name="assistant")

@app.ping
def ping() -> str:
    return "ok"

@app.entrypoint
async def invoke(messages):
    return await runner.run(messages=messages, session_id="default")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
```

**B. `AgentkitAgentServerApp`** — the **full ADK API server** (`/list-apps`, `/run`,
`/run_sse`, session/artifact management, + an `/invoke` compat route). Use this if the
Volcengine console, ADK clients, or `agentkit invoke` (which prefers `/run_sse`) will call it.

```python
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from agentkit.apps import AgentkitAgentServerApp

agent = Agent(name="assistant", instruction="You are helpful.")
server = AgentkitAgentServerApp(agent=agent, short_term_memory=ShortTermMemory(backend="local"))
app = server.app          # a FastAPI app
# run: uvicorn module:app --host 0.0.0.0 --port 8000   (or server.run("0.0.0.0", 8000))
```

## Deploy with the `agentkit` CLI

```bash
agentkit init my-agent --template basic --directory ./my-agent
cd ./my-agent
# ... edit the generated Python entrypoint: instruction, tools ...
agentkit release --name my-agent    # first run may write .agentkit/agentkit.yaml for review
agentkit release                    # cloud-builds the image + creates/updates the runtime → Ready + endpoint
agentkit invoke my-agent -m "hello"    # call it (auto-detects /run_sse vs /invoke)
agentkit runtime logs my-agent         # cloud instance logs when something's off
```

## Gotchas (learned the hard way)

- **Agent `name` must be a valid identifier** — `"my_agent"`/`"assistant"`, never `"my-agent"`
  (pydantic rejects hyphens). The *project*/runtime name may have hyphens; the agent name may not.
- **The container must listen on `0.0.0.0:8000`** — that's the only hard deploy requirement.
- **Model creds**: locally set `MODEL_AGENT_API_KEY`; on the runtime it comes from the IAM
  role (don't hardcode it). VeADK resolves the model key **eagerly at `Agent(...)` construction**,
  so a missing key fails at import/startup — build the agent lazily if you want the container to
  start before the model is configured.
- **Dockerfile for cloud builds**: no `# syntax=` directive and use a Volcengine-hosted base
  image (cloud builds can't reach Docker Hub). Install from **PyPI** (`veadk-python`); only pull
  `[extensions]` when a redis/opensearch/llama-index backend is actually used.
- **`runtime="codex"`** needs `openai-codex` installed; default `"adk"` needs nothing extra.
- **Defer heavy imports** (`get_builtin_tool`, backend classes) into functions if you want
  startup to be robust across veADK versions — a missing symbol then surfaces at call time,
  not as a container that never boots.

## Vibe-coding workflow

1. `agentkit init my-agent --template basic --directory ./my-agent` (or copy the minimal agent above).
2. Edit the `instruction` (persona) and `tools` (start with 1–2 built-ins).
3. Run locally: `python main.py` then `curl localhost:8000/ping`, or drive `runner.run(...)`.
4. `agentkit release --name my-agent` once to create release config if needed, then `agentkit release` → `agentkit invoke my-agent -m "..."`.
5. Iterate: tweak instruction/tools, redeploy. Read `agentkit runtime logs` when it misbehaves.
