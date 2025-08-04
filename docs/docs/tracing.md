# 可观测

VeADK中的可观测（Tracing）能力能够记录运行时关键节点的信息，并且支持无缝上报至火山引擎云平台（例如CozeLoop、APMPlus, TLS等）。

## 本地观测

你可以通过如下方式开启可观测，并且将运行时数据保存至本地：

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer(exporters=exporters)
agent = Agent(tracers=[tracer])

# ... run agent ...

# the data will be automatically saved to local
print(f"Tracing file path: {tracer._trace_file_path}")
```

## 火山云观测

通过设置不同的`exporter`上报器，可以将观测数据上传到对应平台：

- CozeLoop平台：`CozeLoopExporter`
- APMPlus平台： `APMPlusExporter`
- TLS平台：`TLSExporter`

使用方法如下：

```python
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

exporters = [CozeloopExporter(), APMPlusExporter(), TLSExporter()]
tracer = OpentelemetryTracer(exporters=exporters)
agent = Agent(tracers=[tracer])

# ... run agent ...

# the data will be automatically saved to local
print(f"Tracing file path: {tracer._trace_file_path}")
```
