# 04 · Built-in tool: web search

Use one of VeADK's ready-made tools. `web_search` queries Volcengine's search
API so the agent can answer with fresh, real-world information.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
from veadk.tools.builtin_tools.web_search import web_search

agent = Agent(tools=[web_search])
```

Built-in tools live under `veadk.tools.builtin_tools` (web search, image
generation, TTS, code sandbox, and more). They're added exactly like custom
functions — just put them in `tools=[...]`.

## Credentials

`web_search` calls the Volcengine search API, so besides the model key it needs
a Volcengine **AK/SK** pair:

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`

Create them in the [Volcengine IAM console](https://console.volcengine.com/iam/keymanage).

## Run it

```bash
pip install veadk-python
cp .env.example .env   # set MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY/SECRET_KEY
python main.py
```

The agent decides to call `web_search`, then answers using the results.

## What to try next

- Browse other tools in `veadk/tools/builtin_tools/` (e.g. `image_generate`,
  `tts`, `link_reader`).
- Move on to [05 · Knowledgebase RAG](../05_knowledgebase_rag/) to ground
  answers in your own documents.
