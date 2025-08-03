# 记忆

在VeADK中，记忆（Memory）能够为Agent提供上下文支撑，主要分为短期记忆和长期记忆：

- **短期记忆（Short-term memory）**：单个会话内的对话记录
- **长期记忆（Long-term memory）**：多个会话内的对话记录，具备跨session的能力

## 短期记忆

通过以下方式定义一个短期记忆（在不进行特殊指定的情况下，记忆默认将会在内存中存储）：

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

为持久化您的短期记忆，VeADK还支持通过传入`backend`参数，将记忆保存在数据库中：

```python
from veadk.memory.short_term_memory import ShortTermMemory

# 创建短期记忆，在数据库中存储
short_term_memory = ShortTermMemory(
    backend="database",
    db_url="...", # 当`db_url`为空时，将会启动一个本地SQLite数据库
)
```

其中，`db_url`遵循SQLAlchemy的[连接字符串格式]()，您可以根据您的数据库类型进行配置。

短期记忆中的backend字段定义如下：

| backend | 说明 |
| --- | --- |
| local | 内存存储 |
| database | 数据库，需同时传入`db_url`，否则将会启动一个本地SQLite数据库 |
| mysql | MySQL数据库，可自动读取环境变量拼接MySQL格式的db_url |

## 短期记忆的优化

持久化的短期记忆可能过长，占满某些模型的上下文。为解决短期记忆过长的问题，VeADK中提供了记忆优化器来进行短期记忆的优化，通过在短期记忆类中传入`enable_memory_optimization`参数，开启记忆优化器。

```python
from veadk.memory.short_term_memory import ShortTermMemory

short_term_memory = ShortTermMemory(
    backend="database",
    db_url="...",
    enable_memory_optimization=True,
)
```

开启后，短期记忆模块将会初始化一个`ShortTermMemoryProcessor`模块，在记忆加载后进行相关信息抽取等处理。未来，我们将支持传入自定义的记忆优化器，并计划支持如下记忆优化时机：

- 记忆存储前（在线优化）
- 记忆存储后（离线优化）
- 记忆加载后（在线优化）

并且提供如下维度的优化方法：

- 时间维度
- 信息维度
- 自定义维度（例如结构化信息抽取）

## 长期记忆

长期记忆通常存储在数据库中，通过如下方式定义一个长期记忆：

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

长期记忆中的backend字段定义如下：

| backend | 说明 |
| --- | --- |
| local | GIGO模式的内存存储，不具备向量检索功能，仅用于测试 |
| viking | 火山引擎Viking Memory服务 |
| opensearch | OpenSearch数据库 |
| redis | Redis数据库，但不具备向量搜索功能 |
| mysql | MySQL数据库，但不具备向量搜索功能 |

