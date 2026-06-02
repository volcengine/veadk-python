# 11 · Tracing & observability

See exactly what the agent did — every LLM call and tool call — by attaching a
tracer. Each run gets a `trace_id` (32 hex chars) you can search in an
observability platform.

> 中文版见 [README.zh.md](./README.zh.md)

## Core idea

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer(exporters=[...])   # exporters optional
agent = Agent(tracers=[tracer], tools=[...])

answer = await runner.run(messages="...", session_id="demo-session")
runner.get_trace_id()    # the trace id to correlate in your backend
```

- **`tracers=[...]`** — attach one or more tracers to the agent.
- Each LLM call and tool call becomes a span with timing, inputs, and outputs.
- **`runner.get_trace_id()`** — the 32-char id that ties those spans together;
  search it in your observability platform's UI.
- With **no exporter** the spans are kept in-memory (no creds needed); you still
  get a `trace_id`. Add exporters to also ship them to a platform.

## Run it

```bash
pip install veadk-python
cp .env.example .env   # set MODEL_AGENT_API_KEY (+ AK/SK and ENABLE_* to export)
python main.py
```

The script prints which exporters are active, the answer, and the trace id.

## Exporters

This example builds exporters based on `ENABLE_*` env flags (config comes from
`.env`):

- **APMPlus** (`ENABLE_APMPLUS=true`) — auth via `VOLCENGINE_ACCESS_KEY` /
  `SECRET_KEY` (auto token) or `..._APMPLUS_API_KEY`; service name via
  `..._APMPLUS_SERVICE_NAME`.
- **CozeLoop** (`ENABLE_COZELOOP=true`) — `..._COZELOOP_API_KEY`;
  `..._COZELOOP_SERVICE_NAME` is the space id.
- **Volcengine TLS** (`ENABLE_TLS=true`) — Volcengine AK/SK;
  `..._TLS_SERVICE_NAME` is the topic id, `..._TLS_REGION` the region.

(Full env var names are `OBSERVABILITY_OPENTELEMETRY_<PLATFORM>_*`; see
`.env.example`.) Endpoints have defaults, so you usually only set the key / id.

```python
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

tracer = OpentelemetryTracer(exporters=[APMPlusExporter(), CozeloopExporter(), TLSExporter()])
```

You can enable several at once — the same spans are sent to all of them, and
also kept in-memory.

> ℹ️ The local `runner.save_tracing_file(...)` dump is intentionally not used
> here: on the current VeADK + Google ADK combination its session→trace filter
> can return an empty file. The platform exporters above are the reliable way to
> inspect traces. See the
> [configuration docs](https://volcengine.github.io/veadk-python/) for more.
