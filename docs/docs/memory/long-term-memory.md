---
title: 长期记忆
---

本文档介绍 VeADK 系统中的**长期记忆（Long-term Memory）**概念及应用。长期记忆用于跨会话、跨时间保存重要信息，以增强智能体在连续交互中的一致性和智能性。

**定义**：长期记忆是智能体用于存储超出单次会话范围的重要信息的机制，可以包含用户偏好、任务历史、知识要点或长期状态。

**为什么重要**：

- 支持跨会话的连续对话体验；
- 允许智能体在多次交互中保留学习成果和用户特定信息；
- 减少重复询问，提升用户满意度和效率；
- 支持长期策略优化，例如个性化推荐或任务追踪。

智能体用户需要长期记忆来实现更智能、个性化和可持续的交互体验，尤其在多次会话或复杂任务场景中显著提高系统实用性。

## 支持后端类型

| 类别         | 说明                                                       |
| :----------- | :--------------------------------------------------------- |
| `local`      | 内存跨 Session 记忆，程序结束后即清空                      |
| `opensearch` | 使用 OpenSearch 作为长期记忆存储，可实现持久化和检索       |
| `redis`      | 使用 Redis 作为长期记忆存储，Redis 需要支持 Rediseach 功能 |
| `viking`     | 使用 VikingDB 记忆库产品作为长期记忆存储                   |
| `viking_mem` | 已废弃，设置后将会自动转为 `viking`                        |

### Viking 后端

## 初始化方法

在使用长期记忆之前，需要实例化 LongTermMemory 对象并指定后端类型。以下代码展示了如何初始化基于 VikingDB 的长期记忆模块，并将其绑定到 Agent：

```python
os.environ["DATABASE_VIKING_PROJECT"] = "default"
os.environ["DATABASE_VIKING_REGION"] = "cn-beijing"

# 初始化长期记忆
# backend="viking" 指定使用 VikingDB
# app_name 和 user_id 用于数据隔离
long_term_memory = LongTermMemory(
    backend="viking",
    app_name="local_memory_demo",
    user_id="demo_user"
)

# 将长期记忆绑定到 Agent
root_agent = Agent(
    name='minimal_agent',
    instruction="Acknowledge user input and maintain simple conversation.",
    short_term_memory=short_term_memory, # 短期记忆实例
)

# 初始化 Runner 时传入 shared memory 对象
runner = Runner(
    agent=root_agent,
    long_term_memory=long_term_memory, # 长期记忆实例
)
```

### ...

## 记忆管理

### 添加会话到长期记忆

在会话（Session）结束或达到特定节点时，需要显式调用 add_session_to_memory 将会话数据持久化。对于 Viking 后端，这一步会触发数据的向量化处理。

```python
# 假设 runner1 已经完成了一次对话
completed_session = await runner1.session_service.get_session(
    app_name=APP_NAME,
    user_id=USER_ID,
    session_id=session_id
)

# 将完整会话归档到长期记忆
root_agent.long_term_memory.add_session_to_memory(completed_session)
```

### 检索长期记忆

除了 Agent 在运行时自动检索外，开发者也可以调用 search_memory 接口直接进行语义搜索，用于调试或构建自定义的 RAG（检索增强生成）应用。

```python
query = "favorite project"
res = await root_agent.long_term_memory.search_memory(
    app_name=APP_NAME,
    user_id=USER_ID,
    query=query
)

# 打印检索结果
print(res)
```

## 使用长期记忆进行会话管理

在单租户场景中，长期记忆可用于管理同一用户的多次会话，确保智能体能够：

- 在新会话中记忆上一次交互内容；
- 根据历史信息做出个性化响应；
- 在多轮任务中累积进度信息或中间结果。

### 准备工作

- 为每个用户分配唯一标识（user_id 或 session_owner_id）；
- 设计长期记忆数据结构以支持多会话信息保存；
- 配合短期记忆使用，实现会话内上下文快速访问。

```
# 占位: 单租户多会话长期记忆结构示例
```

### 示例

以下示例演示了一个完整的流程：Runner1 告诉 Agent 一个信息（"My favorite project is Project Alpha"），将会话存入记忆，然后创建一个全新的 Runner2，验证其能否回答相关问题。

```python
# --- 阶段 1: 写入记忆 ---
# Runner1 告诉 Agent 信息
runner1_question = "My favorite project is Project Alpha."
user_input = types.Content(role="user", parts=[types.Part(text=runner1_question)])

async for event in runner1.run_async(user_id=USER_ID, session_id=session_id, new_message=user_input):
    pass # 处理 Runner1 的响应

# 关键步骤：将会话归档到 VikingDB
completed_session = await runner1.session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=session_id)
root_agent.long_term_memory.add_session_to_memory(completed_session)

# --- 阶段 2: 跨会话读取 ---
# 初始化 Runner2 (模拟新的会话或后续交互)
runner2 = Runner(
    agent=root_agent,
    app_name=APP_NAME,
    user_id=USER_ID,
    short_term_memory=short_term_memory
)

# Runner2 提问，依赖长期记忆回答
qa_question = "favorite project"
qa_content = types.Content(role="user", parts=[types.Part(text=qa_question)])

final_text = None
async for event in runner2.run_async(user_id=USER_ID, session_id=session_id, new_message=qa_content):
    if event.is_final_response():
         final_text = event.content.parts[0].text.strip()
```

### 说明 / 结果展示

- 智能体能够识别并关联同一用户的历史交互；
- 提供连续性强、个性化的多会话交互体验；
- 为长期任务、学习型应用或持续监控场景提供基础能力。

```
[Log Output]
Runner1 Question: My favorite project is Project Alpha.
Runner1 Answer: (Acknowledged)
...
[Step 4] Archiving session to Long-Term Memory via memory_service
Session archived to Long-Term Memory
...
Runner2 Question: favorite project
Runner2 Answer: Your favorite project is Project Alpha.
```
