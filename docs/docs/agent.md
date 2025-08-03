# 智能体

## 属性

Agent中主要包括如下属性：

| 属性 | 类型 | 说明 |
| --- | --- | --- |
| name | str | Agent的名称，即标识符 |
| description | str | Agent的描述，后续会被构建为系统提示词的一部分；也被用来在A2A协议中进行Agent挑选 |
| instruction | str | Agent中内置模型的系统提示词 |
| tools | list | Function call中的工具列表，既可以是本地工具，也可以是MCP工具 |
| sub_agents | list | 子Agent列表，用于多Agent之间交互 |
| long_term_memory | Vector database | 长期记忆，后端通常为一个向量数据库（Vector database），能够检索 |
| knowledgebase | Vector database | 知识库，后端通常为一个向量数据库（Vector database），能够检索 |
| tracers | list | 追踪器列表，能够定义不同的追踪方式，并在Agent执行完毕后对整体Tracing信息保存至本地 |

## 运行

在生产环境中，我们推荐您使用`Runner`来进行多租户服务：

```python
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

# Define runner config
APP_NAME = ""
USER_ID = ""
SESSION_ID = ""

agent = Agent()
runner = Runner(agent=agent, short_term_memory=ShortTermMemory())
response = await runner.run(messages=prompt, session_id=session_id)
```
