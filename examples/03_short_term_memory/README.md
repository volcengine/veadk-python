# 03 · Short-term memory (multi-turn)

Make the agent remember earlier turns within a conversation. **Short-term
memory** is the conversation context; VeADK keys it by `session_id`.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
short_term_memory = ShortTermMemory(backend="sqlite", local_database_path="./short_term_memory.db")
agent = Agent(short_term_memory=short_term_memory)
runner = Runner(agent=agent, short_term_memory=short_term_memory, app_name="memory_demo")

await runner.run(messages="My name is Xiao Ming.", session_id="user-42-chat")
await runner.run(messages="What is my name?", session_id="user-42-chat")  # remembers
```

- Same `session_id` → the agent sees the previous turns.
- `backend="sqlite"` persists the session to a local `.db` file, so it survives
  restarts. Use `backend="local"` for an ephemeral in-memory session.
- Other backends: `mysql`, `postgresql` (configured via env / `config.yaml`).

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

Turn 2 should correctly recall the name and color from turn 1. Run it again and
the agent still remembers (the session is on disk in `short_term_memory.db`).

## What to try next

- Change `SESSION_ID` and run again — it's a fresh conversation with no memory.
- Short-term memory is *within* a conversation. For knowledge that persists
  *across* conversations and users, see long-term memory in the
  [VeADK docs](https://volcengine.github.io/veadk-python/).
- Move on to [04 · Web search](../04_web_search/) for built-in Volcengine tools.
