# 工具

工具 Tool 指的是赋予 Agent 扩展能力的模块化组件，每个工具都被设计用于执行一个明确的任务，使得 Agent 能够执行超出文本生成与推理范畴的具体操作。工具的引入，使得 Agent 不再仅仅是一个语言模型，而是具备实际行动力的智能体，能够感知、调用外部系统资源，完成更复杂的任务。

## 工具调用

您可以给Agent传入`tools`参数，指定想要调用的工具：

```python
from veadk import Agent

agent = Agent(
    tools=[...] # fill with tools
)
```

## 工具类型

在 VeADK 中，工具包括函数工具、内置工具、MCP 工具和系统工具等。

### 函数工具

VeADK 支持通过函数定义的方式快速创建自定义工具，使 Agent 能够调用本地业务逻辑代码完成特定任务。以下示例展示了 Agent 调用一个自定义的模拟天气查询的函数工具 `get_city_weather`：

```python
def get_city_weather(city: str) -> dict[str, str]:
    """Retrieves the weather information of a given city. the args must in English"""
    fixed_weather = {
        "beijing": {"condition": "Sunny", "temperature": 25},
        "shanghai": {"condition": "Cloudy", "temperature": 22},
        "guangzhou": {"condition": "Rainy", "temperature": 28}
    }

    city = city.lower().strip()
    if city in fixed_weather:
        info = fixed_weather[city]
        return {"result": f"{info['condition']}, {info['temperature']}°C"}
    else:
        return {"result": f"Weather information not found for {city}"}

session_id = "..."
prompt = "..."
agent = Agent(tools=[get_city_weather])
runner = Runner(agent=agent, short_term_memory=ShortTermMemory())
response = await runner.run(messages=prompt, session_id=session_id)
```

### 内置工具

VeADK 中集成了多个火山引擎提供的工具：

- [web_search](https://www.volcengine.com/docs/85508/1650263)（公域搜索）
- [vesearch](https://www.volcengine.com/docs/85508/1512748) （联网搜索，头条搜索等）
- [lark](https://open.larkoffice.com/app)（飞书通信和协同）代码见 [MCP server](https://github.com/larksuite/lark-openapi-mcp)
- [las](https://www.volcengine.com/product/las) （数据湖检索）
- [web_scraper](https://www.volcengine.com/docs/84296/1545470)（聚合搜索）邀测阶段，代码见 [MCP server](https://github.com/volcengine/mcp-server/tree/main/server)

此外，还提供多种沙箱工具：

- Computer sandbox (TBD)
- Browser sandbox (TBD)
- Code sandbox (TBD)

以下示例展示了如何在 VeADK 中集成并调用内置工具 vesearch，用于获取今天的三条热点新闻：

```python
from veadk import Agent
from veadk.tools.builtin_tools.vesearch import vesearch

agent = Agent(
    name="robot",
    description="A robot can help user.",
    instruction="Talk with user friendly. You can invoke your tools to finish user's task or question.",
    tools=[vesearch],
)

response = await agent.run(prompt="The top 3 news today.")
```
  
### MCP 工具

VeADK 支持定义 MCP (Model Context Protocol) 工具来进行功能扩展，例如飞书 Lark MCP 工具、LAS 数据湖 MCP 工具等。

以下示例展示了在 VeADK 中以 飞书 Lark MCP 工具为例定义 MCP 工具组件：

- STDIO 模式
- SSE 模式

```python
lark_tools = MCPToolset(
    connection_params=StdioServerParameters(
        command="npx",
        args=[..., "@larksuiteoapi/lark-mcp", ...],
        errlog=None,
    ),
)

lark_mcp_remote = MCPToolset(
    connection_params=SseConnectionParams(
        url="..."
    )
)
```

### 系统工具

- `load_knowledgebase`：检索知识库工具，在你给 Agent 传入`knowledgebase`参数后，将会自动挂载`load_knowledgebase_tool`工具，Agent 将在运行时自主决定何时查询知识库；
- `load_memory`：检索长期记忆工具，在你给 Agent 传入`long_term_memory`参数后，将会自动挂载`load_memory`工具，Agent 将在运行时自主决定何时查询长期记忆。