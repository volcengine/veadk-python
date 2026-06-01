# 02 · Custom tools

Teach the agent to call your own Python functions. A tool is just a function
with **type hints** and a **docstring** — pass it in `tools=[...]` and the model
decides when to call it.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, e.g. "Beijing".
    """
    ...

agent = Agent(tools=[get_city_weather, recommend_clothing])
```

The docstring is the tool's "API spec" that the model reads. Describe each
argument clearly; the model uses it to decide *when* and *how* to call the tool.

This example chains two tools: the agent looks up the weather, reads the
temperature, then asks the clothing tool for advice — all in a single turn.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

## What to try next

- Add a `get_air_quality(city)` tool and update the instruction to use it.
- Move on to [03 · Short-term memory](../03_short_term_memory/) for multi-turn conversations.
