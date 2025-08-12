# 可观测

VeADK 提供可观测（Tracing）的能力，用于记录 Agent 执行过程中的关键路径与中间状态。支持将 Trace 数据输出至本地文件，或通过不同的 Exporter 上报至火山引擎平台，包括 CozeLoop、APMPlus、TLS，有助于开发者进行调试、性能分析、行为追踪等任务。

## 本地观测

通过如下方式开启本地观测，并且将运行时数据保存至本地：

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer()
agent = Agent(tracers=[tracer])

# ... run agent ...

# the data will be automatically saved to local
print(f"Tracing file path: {tracer._trace_file_path}")
```

## 火山云观测

通过设置不同的云端上报器`exporter`，可以将观测数据上传到对应平台：

- [CozeLoop 平台](https://www.coze.cn/loop)：`CozeLoopExporter`
- [APMPlus 平台](https://www.volcengine.com/product/apmplus)： `APMPlusExporter`
- [TLS 平台](https://www.volcengine.com/product/tls)：`TLSExporter`

示例：配置多个云端 `exporter`

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

# Configure multiple exporters
exporters = [CozeloopExporter(), APMPlusExporter(), TLSExporter()]
tracer = OpentelemetryTracer(exporters=exporters)
agent = Agent(tracers=[tracer])

# ... run agent ...

# the data will be automatically saved to local
print(f"Tracing file path: {tracer._trace_file_path}")
```

## 完整示例

以下示例演示如何在 Agent 执行期间启用多平台追踪（CozeLoop、APMPlus、TLS），并打印本地追踪文件路径：

```python
import json
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

session_id = "..."

# Initialize tracing exporters
exporters = [CozeloopExporter(), APMPlusExporter(), TLSExporter()]
tracer = OpentelemetryTracer(exporters=exporters)

# Create agent with tool and tracer
agent = Agent(
    name="chat_robot",
    description="A robot talk with user.",
    instruction="Talk with user friendly.",
    tools=[get_city_weather],
    tracers=[tracer],
)

# Create runner and execute
runner = Runner(
    agent=agent,
    short_term_memory=ShortTermMemory(),
)
await runner.run(messages="How is the weather like in Xi'an?", session_id=session_id)

print(f"Tracing file path: {tracer._trace_file_path}")
```

本地 Trace 文件内容示意：
![本地 tracing 文件](/images/tracing-file.png)

APMPlus 平台可视化界面：
![APMPlusExporter图](/images/tracing-apmplus.png)
