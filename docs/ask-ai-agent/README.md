# VeADK docs "Ask AI" agent

A VeADK agent that answers questions about the documentation. It exposes one
tool, `search_docs`, which does keyword search over a prebuilt index of the docs
(`docs_index.json`) — no embeddings or vector DB required. The agent is served
over the **A2A** protocol, the same protocol it speaks once deployed to VeFaaS,
so the docs frontend talks to one protocol everywhere.

## Files

| File | Purpose |
| :-- | :-- |
| `agent.py` | The `Agent` + `search_docs` tool (`root_agent` for deploy). |
| `docs_search.py` | Dependency-free BM25-style keyword search (EN + CJK). |
| `build_index.py` | Builds `docs_index.json` from `../content/docs/**/*.mdx`. |
| `serve.py` | Serves the agent as an A2A app (local dev + VeFaaS) with CORS. |

## Run locally

```bash
cd docs/ask-ai-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # then fill MODEL_AGENT_API_KEY (Volcengine Ark)
python build_index.py       # regenerate the index from the docs
python serve.py             # A2A server on http://localhost:8000
```

Point the docs site at it with `NEXT_PUBLIC_AI_CHAT_URL=http://localhost:8000`
(see `docs/.env.local`), then run `pnpm dev`.

## Deploy to VeFaaS

```bash
python build_index.py
veadk deploy --vefaas-app-name veadk-docs-assistant --iam-role <role>
```

This is automated by `.github/workflows/deploy-ask-ai.yaml`, which rebuilds the
index and runs `veadk deploy` whenever `docs/ask-ai-agent/**` changes.
