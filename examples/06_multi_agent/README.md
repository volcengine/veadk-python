# 06 · Multi-agent workflow

Split a job across specialist agents that run in a fixed order. A
`SequentialAgent` runs its sub-agents top to bottom, passing data through
shared session state.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```text
outliner  ->  writer  ->  editor
```

```python
outliner = Agent(name="outliner", instruction="...", output_key="outline")
writer = Agent(name="writer", instruction="...expand:\n{outline}", output_key="draft")
editor = Agent(name="editor", instruction="...polish:\n{draft}", output_key="final")

pipeline = SequentialAgent(
    name="content_pipeline", sub_agents=[outliner, writer, editor]
)
runner = Runner(agent=pipeline, app_name="multi_agent_demo")
```

Two mechanisms make this work:

- **`output_key`** — an agent stores its reply into session state under that key.
- **`{key}` templating** — the next agent's instruction pulls that value back in.

So `outliner` writes `outline`, `writer` reads `{outline}` and writes `draft`,
`editor` reads `{draft}` and produces the `final` text the runner returns.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

You'll get a polished paragraph that passed through all three stages.

## What to try next

- VeADK also ships `ParallelAgent` (run sub-agents concurrently) and `LoopAgent`
  (repeat until a condition). Same `sub_agents=[...]` pattern.
- For *dynamic* delegation (a coordinator that chooses which specialist to call),
  pass `sub_agents=[...]` to a regular `Agent` and let the LLM route.
