# 08 · Model config: fallbacks & extra options

Configure the model directly on the `Agent` — pick the model per agent, add
fallbacks for resilience, and pass extra request options.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
agent = Agent(
    # primary + fallbacks, tried in order
    model_name=["doubao-seed-1-6-250615", "deepseek-v3-2-251201"],
    model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
)
```

- **`model_name` as a list** — the first model is primary; the rest are tried in
  order if a request fails. A single string also works for one fixed model.
- **`model_provider` / `model_api_base` / `model_api_key`** — override the model
  for *this* agent (e.g. a cheaper model for a sub-agent) without touching the
  global environment config.
- **`model_extra_config`** — merged into every request. The `thinking: disabled`
  body turns off the model's chain-of-thought output for faster, cheaper replies.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

Notice the reply comes back quickly — there's no long "thinking" stream because
we disabled it.

## What to try next

- Give different sub-agents in [06](../06_multi_agent/) different
  `model_name`s — a strong model to write, a cheap one to format.
