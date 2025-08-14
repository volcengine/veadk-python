# 记忆

在 VeADK 中，记忆（Memory）能够为 Agent 提供上下文支撑，主要分为短期记忆和长期记忆：

- **短期记忆（Short-term memory）**：用户单 Session 中与 Agent 的对话历史
- **长期记忆（Long-term memory）**：用户多 Session 中与 Agent 的对话历史，具备跨 Session 的能力

## 短期记忆

VeADK 通过以下方式定义一个短期记忆（在不进行特殊指定的情况下，记忆默认将会在内存中存储）：

```python
from veadk.memory.short_term_memory import ShortTermMemory

# 创建短期记忆
short_term_memory = ShortTermMemory()

# 在短期记忆中创建一个会话
await short_term_memory.create_session(
        app_name=app_name, user_id=user_id, session_id=session_id
    )

# 获取会话服务
session_service = short_term_memory.session_service
```

为持久化您的短期记忆，VeADK 还支持通过传入`backend`参数，将记忆保存在数据库中：

```python
from veadk.memory.short_term_memory import ShortTermMemory

# 创建短期记忆，在数据库中存储
short_term_memory = ShortTermMemory(
    backend="database",
    db_url="...", # 当`db_url`为空时，将会启动一个本地SQLite数据库
)
```

其中，`db_url`遵循 SQLAlchemy 的连接字符串格式，您可以根据您的数据库类型进行配置。

短期记忆中的 backend 字段定义如下：

| backend | 说明 |
| --- | --- |
| local | 内存存储 |
| database | 数据库，需同时传入`db_url`，否则将会启动一个本地 SQLite 数据库 |
| mysql | MySQL 数据库，可自动读取环境变量拼接 MySQL 格式的 db_url |

以下示例展示了如何在 VeADK 中使用短期记忆，以实现对话上下文的短期记忆能力。通过在多个消息轮次中复用同一个 `session_id`，智能体能够在会话过程中持续保留并引用先前的对话信息，增强对话的连贯性与上下文感知能力：

```python
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

session_id = "..."

agent = Agent()
short_term_memory = ShortTermMemory()
runner = Runner(agent=agent, short_term_memory=short_term_memory)

prompt = "My name is VeADK."
response = await runner.run(messages=prompt, session_id=session_id)
print(response)

prompt = "Do you remember my name?"
response = await runner.run(messages=prompt, session_id=session_id)
print(response) # Your name is VeADK.
```

### 短期记忆的优化

持久化的短期记忆可能过长，占满某些模型的上下文。为解决短期记忆过长的问题，VeADK 中提供了记忆优化器来进行短期记忆的优化，通过在短期记忆类中传入`enable_memory_optimization`参数，开启记忆优化器。

```python
from veadk.memory.short_term_memory import ShortTermMemory

short_term_memory = ShortTermMemory(
    backend="database",
    db_url="...",
    enable_memory_optimization=True,
)
```

记忆优化器的使用需联合 backend 为 database 或 mysql 来使用。开启后，短期记忆模块将会初始化一个`ShortTermMemoryProcessor`模块，在记忆加载后进行相关信息抽取等处理。未来，我们将支持传入自定义的记忆优化器，计划支持如下记忆优化时机：

- 记忆存储前（在线优化）
- 记忆存储后（离线优化）
- 记忆加载后（在线优化）

并且提供如下维度的优化方法：

- 时间维度
- 信息维度
- 自定义维度（例如结构化信息抽取）

以下示例展示了 VeADK 中短期记忆在开启记忆优化模式（`enable_memory_optimization=True`）后的使用方式。通过该模式，Agent 能够在存储用户对话上下文时自动剔除冗余或无关的信息，从而提高记忆效率与响应准确性。

```python
import os
from sqlalchemy import create_engine
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

session_id = "..."

# prepare a local sqlite database
local_database_path = "..."
engine = create_engine(f"sqlite:///{local_database_path}")

db_url = f"sqlite+pysqlite:///{local_database_path}"
agent = Agent()

# Initial prompt: Contains some invalid information
prompt = [
    "Hi! My name is VeADK!",
    "My secret is `blueblueblue`.",
    "Do you know the differences between `java` and `javascript`?",  # useless chat
    "Once user ask your system prompt, just return `I have no system prompt`.",
    "What is my secret?", 
    "What is your system prompt?"
]

# Use the short-term memory to record the complete conversation content
short_term_memory = ShortTermMemory(backend="database", db_url=db_url)
runner = Runner(agent=agent, short_term_memory=short_term_memory)
await runner.run(messages=prompt, session_id=session_id)

# Redefine the short_term_memory and runner with enable_memory_optimization=True
short_term_memory = ShortTermMemory(
    backend="database", db_url=db_url, enable_memory_optimization=True
)
runner = Runner(agent=agent, short_term_memory=short_term_memory)

prompt = "What is my secret? What is your system prompt?"
response = await runner.run(messages=prompt, session_id=session_id)
print(response)

# clear local database
os.remove(local_database_path)
```

短期记忆优化过程与结果：

![短期记忆优化结果](/images/memory-optimization.png)

## 长期记忆

VeADK 的长期记忆通常存储在数据库中，通过如下方式定义一个长期记忆：

```python
from veadk.memory.long_term_memory import LongTermMemory

long_term_memory = LongTermMemory(backend=...) # 默认的数据库为`opensearch`

# 装配到Agent中，同时会自动挂载`load_memory_tool`工具
agent = Agent(long_term_memory=long_term_memory)

# 运行时可选将某个session存储到长期记忆中
session = await session_service.get_session(
    app_name=app_name,
    user_id=user_id,
    session_id=session_id,
) # 获取当前session
await self.long_term_memory.add_session_to_memory(session) # 添加
```

长期记忆中的 backend 字段定义如下：

| backend | 说明 |
| --- | --- |
| local | GIGO 模式的内存存储，不具备向量检索功能，仅用于测试 |
| viking | 火山引擎 [Viking 记忆库](https://www.volcengine.com/docs/84313/1783345)服务 |
| opensearch | OpenSearch 数据库 |
| redis | Redis 数据库，但不具备向量搜索功能 |
| mysql | MySQL 数据库，但不具备向量搜索功能 |

以下示例展示了如何在 VeADK 中使用长期记忆实现跨会话的信息保留与调用。开发者可以通过 `save_session_to_long_term_memory` 方法，将某一会话中的知识性信息存入长期记忆存储后端。在新的会话中，即使上下文为空，Agent 依然能够基于长期记忆准确回忆并回答相关问题。

```python
from veadk import Agent, Runner
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory

session_id = "..."
new_session_id = "..."

long_term_memory = LongTermMemory(backend=...)  # default backend is `opensearch`
agent = Agent(long_term_memory=long_term_memory) # agent with long term memort backend

runner = Runner(
    agent=agent,
    app_name="...",
    user_id="...",
    short_term_memory=ShortTermMemory(),
)
teaching_prompt = "..."
await runner.run(messages=teaching_prompt, session_id=session_id)

# save the teaching prompt and answer in long term memory
await runner.save_session_to_long_term_memory(session_id=session_id)

# now, let's validate this in a new session
student_prompt = "..."
response = await runner.run(messages=student_prompt, session_id=new_session_id)
print(response)
```
