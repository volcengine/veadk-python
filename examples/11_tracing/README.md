# 11 · Tracing & observability

See exactly what the agent did — every LLM call and tool call — by attaching a
tracer. Each run gets a `trace_id` you can search in an observability platform.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer()
agent = Agent(tracers=[tracer], tools=[...])

answer = await runner.run(messages="...", session_id="demo-session")
runner.get_trace_id()    # the trace id to correlate in your backend
```

- **`tracers=[...]`** — attach one or more tracers to the agent.
- Each LLM call and tool call becomes a span with timing, inputs, and outputs.
- **`runner.get_trace_id()`** — the id that ties those spans together; search it
  in your observability platform's UI.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # then set MODEL_AGENT_API_KEY
python main.py
```

The script prints the answer and the trace id.

> ℹ️ The local `runner.save_tracing_file(...)` dump is intentionally omitted
> here: on the current VeADK + Google ADK 2.0 combination its session→trace
> filter can return an empty file. The platform exporters below are the reliable
> way to inspect traces.

## Exporting to a platform

To ship traces to **CozeLoop**, **APMPlus**, or **TLS** instead of (or in
addition to) the local dump, set the corresponding env vars — VeADK wires up the
exporters automatically:

```bash
ENABLE_COZELOOP=true
OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY=...
OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME=...   # space id
```

See `.env.example` for the APMPlus equivalents and the
[configuration docs](https://volcengine.github.io/veadk-python/) for the rest.
