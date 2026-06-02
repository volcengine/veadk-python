# 11 · 链路追踪与可观测性

通过挂载 tracer，清楚地看到智能体做了什么 —— 每一次大模型调用、每一次工具调用。
每次运行都会得到一个 `trace_id`（32 位十六进制），可在可观测平台中检索。

> English version: [README.md](./README.md)

## 核心思想

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer(exporters=[...])   # exporters 可选
agent = Agent(tracers=[tracer], tools=[...])

answer = await runner.run(messages="...", session_id="demo-session")
runner.get_trace_id()    # 用于在后端平台关联检索的 trace id
```

- **`tracers=[...]`** —— 为智能体挂载一个或多个 tracer。
- 每一次大模型调用与工具调用都会成为一个 span，包含耗时、输入与输出。
- **`runner.get_trace_id()`** —— 串联这些 span 的 32 位 id；在可观测平台 UI 中检索它。
- **不配 exporter** 时 span 仅在内存中收集（无需凭证），你依然能拿到 `trace_id`；
  加上 exporter 就能同时上报到平台。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 填入 MODEL_AGENT_API_KEY（要上报再填 AK/SK 和 ENABLE_*）
python main.py
```

脚本会打印启用了哪些 exporter、回答，以及 trace id。

## Exporter

本示例根据 `ENABLE_*` 环境变量来构建 exporter（具体配置从 `.env` 读取）：

- **APMPlus**（`ENABLE_APMPLUS=true`）—— 用 `VOLCENGINE_ACCESS_KEY` /
  `SECRET_KEY` 自动取 token，或填 `..._APMPLUS_API_KEY`；服务名用
  `..._APMPLUS_SERVICE_NAME`。
- **CozeLoop**（`ENABLE_COZELOOP=true`）—— `..._COZELOOP_API_KEY`；
  `..._COZELOOP_SERVICE_NAME` 是 space id。
- **火山 TLS**（`ENABLE_TLS=true`）—— 火山 AK/SK；`..._TLS_SERVICE_NAME` 是
  topic id，`..._TLS_REGION` 是地域。

（完整环境变量名为 `OBSERVABILITY_OPENTELEMETRY_<平台>_*`，见 `.env.example`。）
端点都有默认值，通常只需填 key / id。

```python
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

tracer = OpentelemetryTracer(exporters=[APMPlusExporter(), CozeloopExporter(), TLSExporter()])
```

可以同时开启多个 —— 同一批 span 会发往所有平台，并同时保留在内存中。

> ℹ️ 这里有意没有用本地的 `runner.save_tracing_file(...)` 导出：在当前
> VeADK + Google ADK 的组合下，其“会话→trace”过滤可能返回空文件。
> 上面的平台 exporter 才是查看 trace 的可靠方式。更多见
> [配置文档](https://volcengine.github.io/veadk-python/)。
