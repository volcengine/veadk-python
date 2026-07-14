# 09 · Long-term memory

Remember facts *across* conversations. Where short-term memory ([03](../03_short_term_memory/))
lives inside one session, long-term memory persists across different sessions
(and users) and is searched on demand.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
long_term_memory = LongTermMemory(backend="local", app_name="ltm_demo")
agent = Agent(
    long_term_memory=long_term_memory,   # adds a `load_memory` tool
    auto_save_session=True,              # save each session to memory automatically
)
```

- `long_term_memory=...` gives the agent a **`load_memory`** tool to search past
  sessions.
- `auto_save_session=True` writes each finished session into long-term memory.

In this example, session #1 tells the agent about dietary restrictions;
session #2 is a *brand-new* conversation, yet the agent recalls them by
searching memory (not from its context window).

## Requirements

The `local` backend embeds memories, so it needs:

```bash
pip install "veadk-python[extensions]"
```

and an embedding model config (`MODEL_EMBEDDING_*`, falls back to
`MODEL_AGENT_API_KEY`).

## Run it

```bash
cp .env.example .env   # set MODEL_AGENT_API_KEY (+ embedding config)
python main.py
```

Session #2's recommendation should respect the peanut allergy and vegetarian
preference from session #1.

## What to try next

- Short-term vs long-term: see [03](../03_short_term_memory/) for the
  in-session kind.
- Swap `backend="local"` for a persistent store (`openviking`, `viking`,
  `redis`, `opensearch`, `mem0`) so memories survive process restarts.
