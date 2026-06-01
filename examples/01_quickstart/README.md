# 01 · Quickstart

The smallest possible VeADK program. An `Agent` carries the model and
instruction; a `Runner` drives a conversation and returns the final answer.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
agent = Agent(name="quickstart_agent", instruction="You are a helpful assistant.")
runner = Runner(agent=agent, app_name="quickstart")
answer = await runner.run(messages="Hello!", session_id="demo-session")
```

- `Agent(...)` reads its model config from the environment (`MODEL_AGENT_*`).
- `runner.run(...)` is **async** and returns the final text reply as a string.

## Run it

1. Install VeADK:

   ```bash
   pip install veadk-python
   ```

2. Configure your key:

   ```bash
   cp .env.example .env
   # then edit .env and set MODEL_AGENT_API_KEY
   ```

3. Run:

   ```bash
   python main.py
   ```

You should see a one-sentence answer printed to the terminal.

## What to try next

- Change `instruction` to give the agent a different persona.
- Move on to [02 · Custom tools](../02_custom_tools/) to let the agent call
  your own Python functions.
