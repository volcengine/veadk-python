# deepseek_harness_runtime

An end-to-end acceptance example for `Agent(runtime="dsh")`.

It verifies the parts that should line up with the Codex-style runtime contract:

- streaming partial output
- ADK `SkillToolset` materialized into DSH native skills
- automatic long-term memory saving and direct retrieval
- SQLite short-term memory across turns
- OpenTelemetry observability through an ADK-shaped `call_llm` span

## Run

```bash
uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py
```

By default the example uses the `viking` long-term-memory backend because it can
use Volcengine AK/SK already present in the environment. You can override it:

```bash
uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py \
  --long-term-backend openviking
```

The runtime name is the canonical `dsh`.

The example defaults to the user-facing provider alias `volcengine` and the
`sdk-minimal` DSH profile:

```bash
VEADK_DEEPSEEK_HARNESS_PROVIDER=volcengine
VEADK_DEEPSEEK_HARNESS_PROFILE=sdk-minimal
MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
MODEL_AGENT_NAME=doubao-seed-2-1-pro-260628
```

Omitting the provider, `openai`, `volcengine`, `volcengine-ark`, `ark`,
`openai-compatible`, and `third-party` are all accepted VeADK entries for
third-party OpenAI-compatible endpoints. The current DSH wheel receives them
through its registered `deepseek-official` adapter while VeADK keeps passing the
explicit model, base URL, and API key.

## What Passes

The script prints one `PASS`/`FAIL` line per capability and includes evidence:
partial chunk count, skill output, SQLite session event count, direct memory
search result count after a session switch, trace id, and trace dump path.

No credentials are stored in this directory. All model, DSH, tracing exporter,
and memory backend credentials are read from environment variables.

Streaming and skill checks require a usable model endpoint because they inspect
DSH assistant stream chunks and the final skill sentinel.
