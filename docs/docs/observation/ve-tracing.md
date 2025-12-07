---
title: 在火山引擎观测
---

## CozeLoop 平台
通过 VeADK 开发的火山智能体接入到扣子罗盘之后，可以通过扣子罗盘的评测功能进行 Agent 评测，或者通过 Trace 功能实现调用链路观测。火山智能体的 Trace 数据可以直接上报至扣子罗盘，实现调用链路观测；在扣子罗盘中注册的火山智能体，也可以通过观测功能进行 Agent 评测。
### 准备工作
在 VeADK 配置文件 config.yaml 的 observability 字段中填写 cozeloop 的属性。关于配置文件的详细说明及示例可参考配置文件。

- endpoint：固定设置为 https://api.coze.cn/v1/loop/opentelemetry/v1/traces。
- api_key：扣子罗盘访问密钥，支持个人访问令牌、OAuth 访问令牌和服务访问令牌。获取方式可参考[配置个人访问令牌](https://loop.coze.cn/open/docs/cozeloop/authentication-for-sdk#05d27a86)。
- service_name：扣子罗盘工作空间的 ID。你可以在登录扣子罗盘之后，左上角切换到想要存放火山智能体数据的工作空间，并在 URL 的 space 关键词之后获取工作空间 ID，例如 https://loop.coze.cn/console/enterprise/personal/space/739XXXXXXXX092/pe/prompts 中，**739XXXXXXXX092**为工作空间 ID。

![cozeloop空间](../assets/images/observation/coze-spaceid.png)

```yaml title="config.yaml"
model:
  agent:
    provider: openai
    name: doubao-seed-1-6-flash-250828
    api_base: https://ark.cn-beijing.volces.com/api/v3
    api_key: your api_key

volcengine:
  access_key: your ak
  secret_key: your sk

observability:
  opentelemetry:
    cozeloop:
      endpoint: https://api.coze.cn/v1/loop/opentelemetry/v1/traces
      api_key: your your api_key
      service_name: your cozeloop space id
```

### 部署运行
#### Cozeloop exporter接入代码
```python title="agent.py"
import asyncio

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporterConfig


cozeloop_exporter = CozeloopExporter()

exporters = [cozeloop_exporter]
tracer = OpentelemetryTracer(exporters=exporters)

agent = Agent(tools=[get_city_weather], tracers=[tracer])

session_id = "session_id_pj"

runner = Runner(agent=agent, short_term_memory=ShortTermMemory())

prompt = "How is the weather like in Beijing? Besides, tell me which tool you invoked."

asyncio.run(runner.run(messages=prompt, session_id=session_id))
```
#### 效果展示
```bash
python agent.py
```
![cozeloop空间](../assets/images/observation/coze-console.png)
![cozeloop空间](../assets/images/observation/coze-trace.png)

## APMPlus 平台
通过 VeADK 开发的火山智能体接入到 APMPlus 之后，可以通过 APMPlus 的评测功能进行 Agent 评测，或者通过 Trace 功能实现调用链路观测。火山智能体的 Trace 数据可以直接上报至 APMPlus，实现调用链路观测。
### 准备工作
- endpoint：指定APMPlus的接入点为 http://apmplus-cn-beijing.volces.com:4317。
- api_key：需填入有效应用程序密钥。
- service_name：指定服务名称，可根据实际需求修改。
初始化 APMPlusExporter：利用APMPlusExporterConfig配置端点、应用程序密钥和服务名称，创建APMPlusExporter实例，配置从环境变量获取。示例代码如下：

```yaml title="config.yaml"
model:
  agent:
    provider: openai
    name: doubao-seed-1-6-flash-250828
    api_base: https://ark.cn-beijing.volces.com/api/v3
    api_key: your api_key

volcengine:
  access_key: your ak
  secret_key: your sk

observability:
  opentelemetry:
    apmplus:
      endpoint: http://apmplus-cn-beijing.volces.com:4317
      api_key: your api_key
      service_name: apmplus_veadk_pj
```

```python title="agent.py"
import asyncio

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporterConfig
from os import getenv


apmplus_exporter = APMPlusExporter()

exporters = [apmplus_exporter]

tracer = OpentelemetryTracer(exporters=exporters)

agent = Agent(tools=[get_city_weather], tracers=[tracer])

session_id = "session_id_pj"

runner = Runner(agent=agent, short_term_memory=ShortTermMemory())

prompt = "How is the weather like in Beijing? Besides, tell me which tool you invoked."
asyncio.run(runner.run(messages=prompt, session_id=session_id))
```

### 部署运行
本地运行上述agent.py代码，触发APMPlus追踪器记录Agent运行的各个节点的调用，以及Metrics信息上传云端存储：
```bash
python agent.py
```
![apmplus空间](../assets/images/observation/apm-console.png)

#### 会话信息
![apmplus空间](../assets/images/observation/apm-session.png)

#### trace信息
![apmplus空间](../assets/images/observation/apm-trace.png)

#### 模型指标信息
![apmplus空间](../assets/images/observation/apm-metrics.png)

## TLS 平台
通过 VeADK 开发的火山智能体接入到 TLS 之后，可以通过 TLS 的评测功能进行 Agent 评测，或者通过 Trace 功能实现调用链路观测。火山智能体的 Trace 数据可以直接上报至 TLS，实现调用链路观测。
### 准备工作
#### veADK代码中创建tracing project和实例
```yaml title="config.yaml"
model:
  agent:
    provider: openai
    name: doubao-seed-1-6-flash-250828
    api_base: https://ark.cn-beijing.volces.com/api/v3
    api_key: your api_key

volcengine:
  access_key: your ak
  secret_key: your sk

observability:
  opentelemetry:
    tls:
      endpoint: https://tls-cn-beijing.volces.com:4318/v1/traces
      service_name: tp_pj
      region: cn-beijing
```

```python title="agent.py"
import asyncio

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporterConfig
from veadk.integrations.ve_tls.ve_tls import VeTLS
from os import getenv

# 初始化VeTLS客户端用于创建日志项目和追踪实例
ve_tls_client = VeTLS()

# 创建日志项目
project_name = "veadk_pj"
log_project_id = ve_tls_client.create_log_project(project_name)
print(f"Created log project with ID: {log_project_id}")

# 创建追踪实例
trace_instance_name = getenv("OBSERVABILITY_OPENTELEMETRY_TLS_SERVICE_NAME")
trace_instance = ve_tls_client.create_tracing_instance(log_project_id, trace_instance_name)
print(f"Created trace instance with ID: {trace_instance['TraceInstanceId']}")
```

#### TLS Exporter接入代码示例
```python title="agent.py"
import asyncio

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporterConfig
from veadk.integrations.ve_tls.ve_tls import VeTLS
from os import getenv

# 初始化TLSExporter用于上报 tracing 数据
tls_exporter = TLSExporter(
    config=TLSExporterConfig(
        topic_id=trace_instance.get('TraceTopicId', trace_instance_name),
    )
)

exporters = [tls_exporter]

tracer = OpentelemetryTracer(exporters=exporters)

agent = Agent(tools=[get_city_weather], tracers=[tracer])

session_id = "session_id_pj"

runner = Runner(agent=agent, short_term_memory=ShortTermMemory())

prompt = "How is the weather like in Beijing? Besides, tell me which tool you invoked."

asyncio.run(runner.run(messages=prompt, session_id=session_id))
```

### 部署运行
本地运行上述agent.py代码，触发TLS Project、Topic的创建，并且通过追踪器记录Agent运行的各个节点的调用：
```bash
python agent.py
```
![控制台打印](../assets/images/observation/tls-console.png)
![tls空间](../assets/images/observation/tls-trace.png)
