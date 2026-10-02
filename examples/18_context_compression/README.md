# 18 — Recoverable context compression

Ask two questions about a synthetic tool report containing 430 inventory records. The SDK reduces model input while preserving complete Session records in SQLite.

Install an SDK containing this PR (`pip install -e .` from the repository root), copy `.env.example` to `.env` in this directory, configure your model and credentials, then run:

```bash
python main.py
```

Record 113 has **2599 units**; record 227 has **5221 units**. These are synthetic source facts, not model-quality scores. The example sets `input_limit=16000` to demonstrate compression with a small report; omit this override in production to start with model-aware defaults. Private endpoints need verified `context_window` and `output_reserve` values.

## Default usage

```python
from veadk import Agent

agent = Agent(name="assistant")  # Uses your configured business model.
```

Without an embedding key, retrieval uses Chinese/English BM25 and downloads no model. Setting `MODEL_EMBEDDING_API_KEY` enables index preparation and model reranking automatically. Override the embedding name, dimensions and endpoint with the other template variables.

Summaries and reranking use the Agent's own model, endpoint and authentication. Ark Chat / Responses auxiliary requests disable thinking without changing main-answer settings. Reranking returns validated passage IDs only; failure or timeout preserves baseline ordering. Auxiliary work has capacity, call and time limits, and adds latency and cost.

```python
agent = Agent(name="assistant", context_compression={"prepare_index": False})
agent = Agent(name="assistant", context_compression={"rerank": False})
agent = Agent(name="assistant", context_compression={"retrieval": "lexical"})
agent = Agent(name="assistant", context_compression=False)
```

These disable preparation, reranking, online retrieval/default reranking, or compression transformations respectively. Capacity admission remains active even with compression disabled.

`.adk/compression-demo.db` stores persistent Sessions; `.adk/context-index.sqlite3` is a disposable index. Keep the same database, application, user, Session and Agent identities to continue. Use a fresh Session ID to repeat a first-run demonstration.

The model calls `veadk_read_context` only when later questions need missing source details. No manual parsing or tool registration is required. SQLite is suitable for local use or a single instance with persistent storage; do not delete Session data as cache.

See the [developer guide](../../docs/context-compression-developer-guide.zh.md).
