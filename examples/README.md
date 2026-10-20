# VeADK Examples

A hands-on tour of VeADK, from the smallest possible agent to a multi-agent
workflow. Each folder is self-contained: a single `main.py`, an `.env.example`,
and a bilingual README (English + 中文).

> 中文版见 [README.zh.md](./README.zh.md)

## Learning path

| # | Example | Level | What you'll learn |
| --- | --- | --- | --- |
| 01 | [Quickstart](./01_quickstart/) | Simple | `Agent` + `Runner`, one question |
| 02 | [Custom tools](./02_custom_tools/) | Simple | Let the agent call your Python functions |
| 03 | [Short-term memory](./03_short_term_memory/) | Medium | Multi-turn conversation with a persistent session |
| 04 | [Web search](./04_web_search/) | Medium | Use a built-in Volcengine tool |
| 05 | [Knowledgebase RAG](./05_knowledgebase_rag/) | Medium | Ground answers in your own documents |
| 06 | [Multi-agent workflow](./06_multi_agent/) | Complex | Compose specialist agents with `SequentialAgent` |
| 07 | [Structured output](./07_structured_output/) | Medium | Get schema-validated JSON with `output_schema` |
| 08 | [Model config](./08_model_config/) | Simple | Model fallbacks + `model_extra_config` per agent |
| 09 | [Long-term memory](./09_long_term_memory/) | Complex | Recall facts across sessions (`auto_save_session`) |
| 10 | [Agent routing](./10_agent_routing/) | Complex | A coordinator that delegates to specialists dynamically |
| 11 | [Tracing](./11_tracing/) | Complex | Observe LLM/tool calls; dump or export spans |
| 13 | [OpenViking](./13_openviking/) | Complex | Use OpenViking for knowledge retrieval and long-term memory |

There are also frontend-focused demos that run with
`veadk frontend --agents-dir examples`:

- [`a2ui_agent/`](./a2ui_agent/) demonstrates agent-driven UI.
- [`multimodal_agent/`](./multimodal_agent/) analyzes images, TXT/Markdown,
  PDFs, and videos uploaded from the chat composer.

For a deployable **full app** (web UI + agent API in one container, shipped to
Volcengine AgentKit via `veadk agentkit`), see [`basic-app/`](./basic-app/).

The examples are grouped by concept: 01–02 basics, 03 & 09 memory, 04–05 tools &
knowledge, 06 & 10 multi-agent, 07–08 model behavior, 11 observability, and 13
OpenViking-backed knowledge and memory.

## Codex runtime

Four examples use `Agent(runtime="codex")`, which hands the inner loop to a
sandboxed coding agent that can write a file, run it, read the traceback and fix
it. Two of them show **what the runtime is for**; two show **how to wire it up**.

| Example | Kind | What you'll learn |
| --- | --- | --- |
| [Data analysis](./codex_data_analysis/) | What it's for | Codex writes an analysis script, hits a real error in dirty data, fixes it, re-runs, reports — the self-iteration loop |
| [Ops assistant](./codex_ops_assistant/) | What it's for | Correlate logs, metrics and deploys with throwaway scripts to find a root cause, inside a no-network sandbox |
| [Skill + MCP](./codex_with_skill_and_mcp/) | How to wire it | The paths a local skill and an MCP tool take under this runtime |
| [Deploy to AgentKit](./codex_runtime_on_agentkit/) | How to deploy | Ship a `runtime="codex"` agent to Volcengine AgentKit |

Reach for this runtime when the steps cannot be enumerated as tools ahead of
time — ad-hoc analysis, log triage, data wrangling. Keep `runtime="adk"` for a
fixed tool call and a formatted answer: it is faster, cheaper, and does not
reject `sub_agents` / `output_schema` / `planner` / `code_executor`. See
[when to use the codex runtime](../docs/content/docs/framework/agent/runtime.en.mdx#when-to-use-the-codex-runtime).

## Common setup

1. Install VeADK (example 05 with the local backend needs the `extensions` extra):

   ```bash
   pip install veadk-python
   # for example 05's local RAG backend:
   pip install "veadk-python[extensions]"
   ```

2. In each example folder, copy the env template and add your keys:

   ```bash
   cd 01_quickstart
   cp .env.example .env
   ```

   VeADK auto-loads `.env` from the current working directory. You can also
   use a `config.yaml` instead — see the
   [configuration docs](https://volcengine.github.io/veadk-python/configuration/).

3. Run:

   ```bash
   python main.py
   ```

## Key concepts in one place

- **`Agent`** — model + instruction + tools + memory/knowledge. Created once,
  reads model config from the environment.
- **`Runner`** — drives a conversation; `await runner.run(messages=..., session_id=...)`
  returns the final text answer.
- **Tools** — any Python function with type hints and a docstring; built-ins live
  under `veadk.tools.builtin_tools`.
- **Memory** — short-term (conversation context, keyed by `session_id`) and
  long-term (across sessions).
- **KnowledgeBase** — RAG over your documents; auto-adds a retrieval tool.
- **Workflow agents** — `SequentialAgent`, `ParallelAgent`, `LoopAgent` to
  orchestrate multiple agents.

## Learn more

- Docs: <https://volcengine.github.io/veadk-python/>
- Tutorial notebook: [`veadk_tutorial.ipynb`](../veadk_tutorial.ipynb)
