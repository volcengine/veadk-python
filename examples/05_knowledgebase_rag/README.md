# 05 · Knowledgebase RAG

Ground the agent's answers in *your own* documents using Retrieval-Augmented
Generation (RAG). A `KnowledgeBase` embeds your docs into a vector store; when
attached to an `Agent`, VeADK gives it a retrieval tool automatically.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
knowledgebase = KnowledgeBase(backend="local", index="company_faq")
knowledgebase.add_from_directory("./docs")

agent = Agent(knowledgebase=knowledgebase)   # retrieval tool added automatically
```

At query time the agent retrieves the most relevant passages from your docs and
answers based on them — so it can correctly answer questions the base model has
never seen (here: Acme Inc.'s internal leave / remote-work policy in `docs/`).

## Requirements

The `local` backend embeds documents, so it needs:

1. The optional extensions dependency:

   ```bash
   pip install "veadk-python[extensions]"
   ```

2. An **embedding model** config (`MODEL_EMBEDDING_*`). If you omit the embedding
   key, VeADK reuses `MODEL_AGENT_API_KEY`.

## Run it

```bash
cp .env.example .env   # set MODEL_AGENT_API_KEY (and embedding config)
python main.py
```

The answer about annual leave / remote work comes straight from
`docs/company_faq.md`, not the model's prior knowledge.

## What to try next

- Drop your own `.md` / `.txt` / `.pdf` files into `docs/` and ask about them.
- Swap `backend="local"` for a persistent store like `openviking`, `milvus`,
  `viking`, `opensearch`, or `redis` (configured in `.env` or `config.yaml`) for
  production use.
- Move on to [06 · Multi-agent workflow](../06_multi_agent/) to compose several
  agents.
