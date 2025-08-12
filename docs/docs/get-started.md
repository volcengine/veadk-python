# 快速开始

## 安装 VeADK

参考[安装](./installation.md)文档进行配置，并将`config.yaml`配置文件放在项目根目录。

## 构建 Agent

当你安装 VeADK 并完成配置后，您可以构建一个查询天气的智能体，该智能体配置了内置的模拟查询天气的函数工具`get_city_weather`：

```python
from veadk import Agent
from veadk.tools.demo_tools import get_city_weather

agent = Agent(tools=[get_city_weather])
```

## 执行 Agent

由于某些操作是异步的，因此 Agent 的运行需要借助`asyncio`库在异步环境中进行。

Agent 的运行有两种方式，第一种是使用 Agent 自带的 `run` 方法运行：

```python
import asyncio

prompt = "How is the weather like in Beijing? Besides, tell me which tool you invoked."
response = asyncio.run(agent.run(prompt))
print(response)
```

第二种是使用 `Runner` 执行:

```python
from veadk import Runner
from veadk.memory.short_term_memory import ShortTermMemory
import asyncio

session_id = "..."
runner = Runner(agent=agent, short_term_memory=ShortTermMemory()) # 使用 Runner 执行智能体

prompt = "How is the weather like in Beijing? Besides, tell me which tool you invoked."
response = asyncio.run(runner.run(messages=prompt, session_id=session_id))
print(response) # The weather in Beijing is Sunny with a temperature of 25°C. The tool invoked is get_city_weather.
```

::: warning
我们在`Agent`类中提供的`run`方法仅为了本地测试和开发使用，由于该函数位于一个异步与同步函数共存的运行环境，可能会产生不可预知的异常。

因此不建议在生产环境中使用。
:::
