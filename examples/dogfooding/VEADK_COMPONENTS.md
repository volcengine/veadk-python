# VeADK Components Reference

Ground-truth reference for generating runnable VeADK agent projects. Everything
below is grounded in the real `veadk` API (`veadk/agent.py` and the examples
under `examples/`). Prefer the defaults; only enable a component when the
requirement actually needs it.

## 1. Minimal agent skeleton (the only hard requirements)

A VeADK project that the ADK API server / web UI can load is a Python package
(a directory with `__init__.py`) whose `agent.py` exposes a module-level
`root_agent`.

`agent.py`:

```python
from veadk import Agent

INSTRUCTION = "You are a helpful assistant. Answer concisely in the user's language."

agent = Agent(
    name="my_agent",                 # snake_case, no spaces
    description="一句话描述这个 agent。",  # used in A2A / multi-agent routing
    instruction=INSTRUCTION,
)

# Required by the Google ADK agent loader. MUST be named `root_agent`.
root_agent = agent
```

`__init__.py`:

```python
from . import agent

__all__ = ["agent"]
```

Notes:
- Do NOT pass `model=...`. VeADK fills the model from config/settings
  (`settings.model.*`). Never hardcode a foreign model id.
- `name` should be a valid identifier (snake_case). `description` may be Chinese.
- The instruction can reference session state with `{key}` placeholders (see
  multi-agent below).

## 2. Tools — plain Python functions

A tool is just a function with type hints and a docstring. The docstring is what
the model reads to decide when/how to call it, so write it for the model.
Tools should return a `dict` (e.g. `{"result": ...}`).

```python
from veadk import Agent

def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, e.g. "Beijing".

    Returns:
        A dict with a human-readable weather "result".
    """
    data = {"beijing": "Sunny, 25°C", "shanghai": "Cloudy, 22°C"}
    return {"result": data.get(city.lower().strip(), f"No data for {city}")}

agent = Agent(
    name="weather_agent",
    description="查询天气的助手。",
    instruction="Use `get_city_weather` to look up conditions, then answer.",
    tools=[get_city_weather],
)
root_agent = agent
```

### Built-in tools

VeADK ships ready-made tools under `veadk.tools.builtin_tools`. Add them the same
way (drop into `tools=[...]`). The most common one:

```python
from veadk.tools.builtin_tools.web_search import web_search  # Volcengine web search

agent = Agent(name="search_agent", description="联网搜索助手。",
              instruction="When a question needs fresh info, call `web_search` first.",
              tools=[web_search])
```

`web_search` needs Volcengine `VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`
in the environment. Only use built-in tools you are sure exist; otherwise define
plain function tools.

## 3. Multi-agent (sub_agents + workflow agents)

Two ways to compose agents:

(a) An `Agent` with `sub_agents=[...]` can transfer control to specialists
(LLM-driven routing). Each sub-agent needs a clear `description`.

```python
from veadk import Agent

billing = Agent(name="billing_agent", description="处理账单相关问题。",
                instruction="You handle billing questions.")
tech = Agent(name="tech_agent", description="处理技术支持问题。",
             instruction="You handle technical support.")

agent = Agent(
    name="router_agent",
    description="把用户问题路由到合适的子 agent。",
    instruction="Route the user's question to the right sub-agent.",
    sub_agents=[billing, tech],
)
root_agent = agent
```

(b) Fixed-order workflow with `SequentialAgent` (also `ParallelAgent`,
`LoopAgent`). Sub-agents share session state: each writes via `output_key`, the
next reads it with a `{key}` placeholder in its instruction.

```python
from veadk import Agent
from veadk.agents.sequential_agent import SequentialAgent

outliner = Agent(name="outliner",
                 instruction="Produce a tight 3-point outline.",
                 output_key="outline")
writer = Agent(name="writer",
               instruction="Expand this outline into a paragraph:\n\n{outline}",
               output_key="draft")

root_agent = SequentialAgent(
    name="content_pipeline",
    description="把主题变成一段成稿。",
    sub_agents=[outliner, writer],
)
```

Note: workflow agents (Sequential/Parallel/Loop) do not carry their own memory.

## 4. Short-term memory (conversation context across turns)

Session/conversation memory, keyed by `session_id`. Pass it to BOTH the `Agent`
and the `Runner` (the API server provides the Runner for you).

```python
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory

short_term_memory = ShortTermMemory(backend="local")  # or backend="sqlite",
                                                       # local_database_path="./stm.db"
agent = Agent(
    name="memory_agent",
    description="记得多轮对话内容的助手。",
    instruction="Remember what the user tells you.",
    short_term_memory=short_term_memory,
)
root_agent = agent
```

`backend="local"` is in-memory; `backend="sqlite"` persists to a local file.

## 5. Long-term memory (facts across sessions)

Persists facts across different sessions/users. Attaching it gives the agent a
`load_memory` tool automatically. `auto_save_session=True` writes each finished
session into long-term memory. Needs `pip install "veadk-python[extensions]"`.

```python
from veadk import Agent
from veadk.memory.long_term_memory import LongTermMemory

long_term_memory = LongTermMemory(backend="local", app_name="my_app")
agent = Agent(
    name="ltm_agent",
    description="跨会话记住用户偏好的助手。",
    instruction="When the user asks about something they told you before, "
                "use the `load_memory` tool to recall it.",
    long_term_memory=long_term_memory,
    auto_save_session=True,
)
root_agent = agent
```

## 6. Knowledgebase / RAG

A `KnowledgeBase` embeds documents into a vector backend. Attaching it adds a
retrieval tool automatically, so the agent grounds answers in your content.
`backend="local"` needs `pip install "veadk-python[extensions]"`.

```python
from veadk import Agent
from veadk.knowledgebase import KnowledgeBase

knowledgebase = KnowledgeBase(backend="local", index="company_faq")
# knowledgebase.add_from_directory("./docs")  # ingest local docs (embedded on add)

agent = Agent(
    name="rag_agent",
    description="基于知识库回答问题。",
    instruction="Always consult the knowledge base first and answer from what "
                "you retrieve. If it's not there, say so.",
    knowledgebase=knowledgebase,
)
root_agent = agent
```

## 7. Structured output

Force the reply to match a Pydantic model with `output_schema`. The reply is then
JSON matching that schema. Note: with `output_schema` set, the agent cannot call
tools or transfer to sub-agents.

```python
from pydantic import BaseModel, Field
from veadk import Agent

class Ticket(BaseModel):
    summary: str = Field(description="One-line summary.")
    priority: str = Field(description="One of: low, medium, high.")

agent = Agent(
    name="ticket_extractor",
    description="把自由文本变成结构化工单。",
    instruction="Extract a support ticket from the user's message.",
    output_schema=Ticket,
)
root_agent = agent
```

## 8. Tracing / observability

Attach a tracer via `tracers=[...]`. Every LLM/tool call becomes a span. By
default spans are collected in-memory (no credentials needed). Cloud exporters
(APMPlus / CozeLoop / TLS) are enabled via env vars `ENABLE_APMPLUS` /
`ENABLE_COZELOOP` / `ENABLE_TLS` = `true` plus their creds.

```python
from veadk import Agent
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

agent = Agent(
    name="traced_agent",
    description="带链路追踪的助手。",
    instruction="You are a helpful assistant.",
    tracers=[OpentelemetryTracer()],
)
root_agent = agent
```

## 9. A2UI (agent-driven rich UI)

Set `enable_a2ui=True` to let the agent reply with declarative UI cards rendered
by a client. It appends a `send_a2ui_json_to_client` tool. Needs
`pip install "veadk-python[a2ui]"`.

```python
from veadk import Agent

agent = Agent(
    name="a2ui_agent",
    description="能返回富 UI 卡片的助手。",
    instruction="When the answer is naturally visual (a status card, a list, a "
                "small form), reply by calling `send_a2ui_json_to_client` with "
                "A2UI JSON built from the catalog components (Card, Column, Row, "
                "Text, Icon, Button...). Otherwise answer in plain text.",
    enable_a2ui=True,
)
root_agent = agent
```

## 10. Authorization

`enable_authz=True` adds an authorization check (a `before_agent_callback`)
gating the agent. Only set it when the requirement asks for access control.

```python
agent = Agent(name="secure_agent", description="需要鉴权的助手。",
              instruction="...", enable_authz=True)
```

## Field cheat-sheet (Agent)

| Field | Type | Purpose |
|---|---|---|
| `name` | `str` | snake_case identifier |
| `description` | `str` | used in routing / A2A |
| `instruction` | `str` | system prompt; supports `{state_key}` placeholders |
| `tools` | `list` | plain functions or built-in tools |
| `sub_agents` | `list[BaseAgent]` | child agents for routing |
| `output_key` | `str` | write reply into session state under this key |
| `output_schema` | `BaseModel` | force structured JSON output |
| `short_term_memory` | `ShortTermMemory` | per-session memory |
| `long_term_memory` | `LongTermMemory` | cross-session memory (adds `load_memory`) |
| `auto_save_session` | `bool` | persist each session to long-term memory |
| `knowledgebase` | `KnowledgeBase` | RAG; adds retrieval tool |
| `tracers` | `list[BaseTracer]` | observability spans |
| `enable_a2ui` | `bool` | agent-driven rich UI |
| `enable_authz` | `bool` | authorization gate |

Do NOT pass `model=`; VeADK reads it from config. Always end `agent.py` with
`root_agent = <your top-level agent>`.
