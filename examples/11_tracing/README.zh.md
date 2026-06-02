# 11 · 链路追踪与可观测性

通过挂载 tracer，清楚地看到智能体做了什么 —— 每一次大模型调用、每一次工具调用。
每次运行都会得到一个 `trace_id`，可在可观测平台中检索。

> English version: [README.md](./README.md)

## 核心思想

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer()
agent = Agent(tracers=[tracer], tools=[...])

answer = await runner.run(messages="...", session_id="demo-session")
runner.get_trace_id()    # 用于在后端平台关联检索的 trace id
```

- **`tracers=[...]`** —— 为智能体挂载一个或多个 tracer。
- 每一次大模型调用与工具调用都会成为一个 span，包含耗时、输入与输出。
- **`runner.get_trace_id()`** —— 串联这些 span 的 id；在可观测平台 UI 中检索它。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

脚本会打印回答与 trace id。

> ℹ️ 这里有意没有演示本地的 `runner.save_tracing_file(...)` 导出：在当前
> VeADK + Google ADK 2.0 的组合下，其“会话→trace”过滤可能返回空文件。
> 下方的平台 exporter 才是查看 trace 的可靠方式。

## 导出到平台

若想把 trace 上报到 **CozeLoop**、**APMPlus** 或 **TLS**（替代或叠加本地导出），
只需设置对应的环境变量，VeADK 会自动接好 exporter：

```bash
ENABLE_COZELOOP=true
OBSERVABILITY_OPENTELEMETRY_COZELOOP_API_KEY=...
OBSERVABILITY_OPENTELEMETRY_COZELOOP_SERVICE_NAME=...   # space id
```

APMPlus 的等价配置见 `.env.example`，其余配置见
[配置文档](https://volcengine.github.io/veadk-python/)。
