---
title: 短期记忆
---

本文档将介绍 VeADK 系统的**短期记忆（Short-term Memory）**机制及其应用。短期记忆的核心作用是保存「会话级」的上下文信息，从而提升多轮交互的一致性，让智能体的响应更连贯。

当用户与你的 Agent 开启对话时，ShortTermMemory 或 SessionService会自动创建一个 Session 对象。这个 Session 会全程跟踪并管理对话过程中的所有相关内容。


!!! note

    *   更多信息可参考[Google ADK Session](https://google.github.io/adk-docs/sessions/session)

## 使用ShortTermMemory

下面展示了创建和使用短期记忆：

```python
import asyncio
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

app_name = "app_short_term_1"
user_id = "user_short_term_1"
session_id = "session_short_term_1"

agent = Agent()
short_term_memory = ShortTermMemory(
    backend="local", # 指定 ShortTermMemory 的存储方式
    # 如果是 sqlite，指定数据库路径
    # local_database_path="/tmp/d_persistent_short_term_memory.db", 
)  
runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)

async def main():
    response1 = await runner.run(
        messages="我在 7 月 15 日购买了 20 个冰激凌", session_id=session_id
    )
    print(f"response of round 1: {response1}")
    
    response2 = await runner.run(
        messages="我什么时候买了冰激凌？", session_id=session_id
    )
    print(f"response of round 2: {response2}")
    
if __name__ == "__main__":
    asyncio.run(main())
```
**示例输出**

```
response of round 1: 听起来您记录了冰激凌的购买情况！请问您是否需要：

1. 计算相关费用（如果有单价信息）
2. 记录或分析消费习惯
3. 其他与这次购买相关的数据处理或记录需求？

response of round 2: 根据您提供的信息，您在 **7 月 15 日** 购买了 20 个冰激凌。
```
## 短期记忆的几种实现

VeADK 中，您可以使用如下短期记忆后端服务来初始化您的短期记忆：

| 类别 | 说明 |
| :- | :- |
| `local` | 内存短期记忆，程序结束后即清空。生产环境需要使用数据库进行持久化，以符合分布式架构要求。 |
| `mysql` | 使用 MySQL 数据库存储短期记忆，可实现持久化 |
| `sqlite` | 使用本地 SQLite 数据库存储短期记忆，可实现持久化 |
| `postgresql` | 使用 PostgreSQL 数据库存储短期记忆，可实现持久化 |

#### 数据库 backend 配置

=== "mysql"

    ``` yaml
    database:
        mysql:
            host: 
            user: 
            password: 
            charset: utf8
    ```

=== "postgresql"

    ``` yaml
    database:
        postgresql:
            host: # host or ip 
            user: 
            password:
    ```

 在火山引擎开通数据库
 
  - [如何开通火山引擎 MySQL 数据库](https://www.volcengine.com/product/rds-mysql)
  - [如何开通火山引擎 postgresql 数据库](https://www.volcengine.com/product/rds-pg)

## 会话管理

你通常无需直接创建或管理 `Session` 对象，而是通过 `SessionService` 来管理，负责对话会话的完整生命周期。

其核心职责包括：

1. **启动新会话**`create_session()`：当用户发起交互时，创建全新的 Session 对象。
2. **恢复已有会话**`get_session()`：通过 `session_id` 检索特定 Session ，使 Agent 能够接续之前的对话进度。
3. **保存对话进度**`append_event()`：将新的交互内容（Event 对象）追加到会话历史中。这也是会话状态的更新机制。
4. **列出会话列表**`list_sessions()`：查询特定用户及 application 下的活跃会话。
5. **清理会话数据**`delete_session()`：当会话结束或会话不再需要时，删除 Session 对象及其关联数据。

## 上下文压缩

随着 Agent 运行会话历史会不断增长，从而导致大模型处理数据的增长和响应时间变慢。上下文压缩功能使用滑动窗口方法来汇总会话历史数据，当会话历史超过预定义阈值时，系统会自动压缩旧事件。

### 配置上下文压缩

添加上下文压缩后，`Runner` 会在每次会话达到间隔时自动压缩会话历史。

```python
from google.adk.apps.app import App
from google.adk.apps.app import EventsCompactionConfig

app = App(
    name='my-agent',
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compaction_interval=3,  # 每 3 次新调用触发一次压缩。
        overlap_size=1          # 包含前一个窗口的最后一次事件重叠。
    ),
)
```

### 定义压缩器

你可以使用`LlmEventSummarizer`自定义使用特定的大模型和压缩结构`PromptTemplate`。

```python
from google.adk.apps.app import App
from google.adk.apps.app import EventsCompactionConfig
from google.adk.models.lite_llm import LiteLlm
from google.adk.apps.llm_event_summarizer import LlmEventSummarizer

# 自定义压缩器使用的AI模型
summarization_llm = LiteLlm(
                model="volcengine/doubao-seed-1-6-lite-251015",
                api_key=f"{model_api_key}",
                api_base=f"{model_api_base}",
            )

my_compactor = LlmEventSummarizer(llm=summarization_llm,  
# 自定义压缩结构
prompt_template="""
Please summarize the conversation. Compression Requirements:
1. Retain key entities, data points, and timelines
2. Highlight core problems and solutions discussed
3. Maintain logical coherence and contextual relevance
4. Eliminate duplicate expressions and redundant details
""")

app = App(
    name='my-agent',
    root_agent=root_agent,
    events_compaction_config=EventsCompactionConfig(
        compactor=my_compactor,
        compaction_interval=5, 
        overlap_size=1
    ),
)
```