# 10 · Agent routing (dynamic delegation)

A coordinator agent that **decides at runtime** which specialist to hand each
request to. This is the counterpart to the fixed pipeline in
[06](../06_multi_agent/): there the order is hard-coded, here the LLM routes.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
coordinator = Agent(
    instruction="You are a router. Transfer to the right specialist.",
    sub_agents=[finance_agent, translator_agent],
)
```

Give a regular `Agent` a list of `sub_agents` and it can **transfer** the
conversation to whichever one fits. The coordinator chooses based on each
sub-agent's **`description`** — so those descriptions are effectively the routing
table. Write them for the router.

In this example:

- "100 USD to CNY?" → routed to `finance_agent` (which calls
  `get_exchange_rate`).
- "Translate ..." → routed to `translator_agent`.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

## SequentialAgent vs routing

| | Order | Decided by |
| --- | --- | --- |
| [06 SequentialAgent](../06_multi_agent/) | Fixed (A→B→C) | You |
| 10 Routing (this) | Dynamic | The LLM coordinator |

## What to try next

- Add a third specialist (e.g. a `weather_agent`) and watch the coordinator
  pick it.
- Combine: a routed specialist can itself be a `SequentialAgent`.
