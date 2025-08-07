# 快速开始

## 最简Agent

当你设置完环境变量后，你可以创建一个最简单的聊天智能体：

```python
from veadk import Agent

agent = Agent()
```

由于某些操作是异步的，因此Agent的运行需要在异步环境中进行：

::: warning
我们在`Agent`类中提供的`run`方法仅为了本地测试和开发使用，由于该函数位于一个异步与同步函数共存的运行环境，可能会产生不可预知的异常。

因此不建议在生产环境中使用。
:::

```python
import asyncio

prompt = "Hello!"
res = asyncio.run(agent.run(prompt))
```

## 工具调用

你可以给Agent传入`tools`参数，指定想要调用的工具：

```python
from veadk import Agent

agent = Agent(
    tools=[...] # fill with tools
)
```

### 内置工具

VeADK中集成了多个火山引擎提供的工具：

- web_search （公域搜索）
- vesearch （联网搜索，头条搜索等）
- lark （飞书通信和协同）
- las (数据湖检索）
- web_scraper 邀测，代码见MCP server （聚合搜索）

此外，还提供多种沙箱工具：

- Computer sandbox (TBD)
- Browser sandbox (TBD)
- Code sandbox (TBD)
  
### MCP工具

采用如下方式定义一个MCP工具, 例如LAS MCP工具：

```python
# 以飞书Lark MCP工具为例
lark_tools = MCPToolset(
    connection_params=StdioServerParameters(
        command="npx",
        args=[...],
        errlog=None,
    ),
)

remote_mcp_server = MCPToolset(connection_params=SseConnectionParams(url=url))

```

### 系统工具

- `load_knowledgebase`：检索知识库工具，在你给Agent传入`knowledgebase`参数后，将会自动挂载`load_knowledgebase_tool`工具，Agent将在运行时自主决定何时查询知识库；
- `load_memory`：检索长期记忆工具，在你给Agent传入`memory`参数后，将会自动挂载`load_memory_tool`工具，Agent将在运行时自主决定何时查询长期记忆。
