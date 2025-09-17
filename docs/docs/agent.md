# 智能体

智能体 Agent 是一个具备完整功能的执行单元，依托内置的大模型推理能力，其不仅可以独立完成各类任务、与用户进行智能交互、调用外部工具资源，还能实现与其他 Agent 之间的协同配合。

## 属性

Agent 中主要包括如下属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| name | str | Agent 的名称，即标识符 |
| description | str | Agent 的描述，后续会被构建为系统提示词的一部分，也被用来在A2A协议中进行 Agent 挑选 |
| instruction | str | Agent 中内置模型的系统提示词 |
| model_name | str | Agent 中内置模型的名称，默认从环境变量中获取 |
| model_provider | str | Agent 中内置模型的提供商，默认从环境变量中获取 |
| model_api_base | str | Agent 中内置模型的 API Base，默认从环境变量中获取 |
| model_api_key | str | Agent 中内置模型的 API Key，默认从环境变量中获取 |
| model_extra_config | dict | Agent 进行模型请求时的额外参数，Key 值为属性名，Value 值为属性值 |
| tools | list | Function call 中的工具列表，既可以是本地工具，也可以是 MCP 工具 |
| sub_agents | list | 子 Agent 列表，用于多 Agent 之间交互 |
| knowledgebase | KnowledgeBase | 知识库，后端支持本地内存（local）和数据库（opensearch、viking、redis、mysql），通常设置为一个能够检索的向量数据库 |
| long_term_memory | LongTermMemory | 长期记忆，后端支持本地内存（local）和数据库（opensearch、viking、redis、mysql），通常设置为一个能够检索的向量数据库 |
| tracers | list | 追踪器列表，能够定义不同的追踪方式，并在 Agent 执行完毕后将整体 Tracing 信息保存至本地 |

您可以在[火山引擎方舟平台](https://www.volcengine.com/product/ark)选择适合您的大模型。

## 运行

在生产环境中，我们推荐您使用 VeADK 的`Runner`执行器来进行多租户服务与 Agent 运行，在多租场景下，`Runner`通过三个属性来确定资源空间：

- `app_name`：应用名称
- `user_id`：用户ID
- `session_id`：某个用户某次会话的ID

```python
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

# Define Runner config
APP_NAME = "..."
USER_ID = "..."
SESSION_ID = "..."

agent = Agent()

runner = Runner(
    agent=agent,
    short_term_memory=ShortTermMemory(),
    app_name=APP_NAME,
    user_id=USER_ID
)

response = await runner.run(messages="...", session_id=SESSION_ID)
```

## A2A 智能体

当智能体部署到云上后，可以在本地被初始化为一个 Remote Agent，也就是能够通过 A2A 协议来访问的智能体，初始化方法如下：

```python
remote_agent = RemoteVeAgent(
    name="a2a_agent",
    url="..." # <--- url from cloud platform
)

short_term_memory = ShortTermMemory()
runner = Runner(
    agent=remote_agent,
    short_term_memory=short_term_memory
)

res = await runner.run(
    messages="...",
    session_id="sample_session"
)
```

## 多智能体

使用 VeADK 可以构建多 Agent 协作， 主 Agent 通过 `sub_agents` 机制协调多个子 Agent 完成复杂任务。以下代码示例分别定义了三个 Agent：

- weather_reporter：负责获取指定城市的天气信息（调用了 `get_city_weather` 工具）。
- suggester：根据天气情况给出穿衣建议。
- planner_agent：作为“调度员”，先调用 `weather_reporter` 获取天气，再调用 `suggester` 获取建议，最后将结果整合返回给用户。

该多智能体协作能更好的满足用户的需求。

```python
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.demo_tools import get_city_weather

session_id = "..."
prompt = "..."

# 定义三个智能体，分别为天气预报智能体、穿衣建议智能体以及一个Planner智能体
weather_reporter = Agent(
    name="weather_reporter",
    description="A weather reporter agent to report the weather.",
    tools=[get_city_weather],
)
suggester = Agent(
    name="suggester",
    description="A suggester agent that can give some clothing suggestions according to a city's weather.",
)

planner_agent = Agent(
    name="planner",
    description="A planner that can generate a suggestion according to a city's weather.",
    instruction="Invoke weather reporter agent first to get the weather, then invoke suggester agent to get the suggestion. Return the final response to user.",
    sub_agents=[weather_reporter, suggester],
)

runner = Runner(agent=planner_agent, short_term_memory=ShortTermMemory())
response = await runner.run(messages=prompt, session_id=session_id)
```

## 从 Agent 配置文件构建

你可以通过一个 Agent 配置文件来构建 Agent 运行时实例，例如：

```yaml
root_agent:
  type: Agent # Agent | SequencialAgent | LoopAgent | ParallelAgent
  name: test
  description: A test agent
  instruction: A test instruction
  long_term_memory:
    backend: local
  knowledgebase:
    backend: opensearch
  tools:
    - module: demo_tool   # tool 所在的模块
      func: greeting      # tool 的函数名称
    - module: tools.tool
      func: count
  sub_agents:
    - ${sub_agent_1}

sub_agent_1:
  type: Agent
  name: agent1
```

其中，每个`agent`的`type`负责指定 Agent 的类名。

可以通过如下代码来实例化这个 Agent:

```python
from veadk.agent_builder import AgentBuilder

agent = AgentBuilder().build(path="./agent.yaml")
```

函数`build`接收 2 个参数：

- `path`：配置文件路径
- `root_agent_identifier`：配置文件中主 Agent 的名称，默认为`root_agent`
