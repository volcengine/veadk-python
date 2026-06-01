# 03 · 短期记忆（多轮对话）

让智能体记住同一轮对话中之前说过的话。**短期记忆**即对话上下文，VeADK 通过 `session_id` 来区分。

> English version: [README.md](./README.md)

## 核心思想

```python
short_term_memory = ShortTermMemory(backend="sqlite", local_database_path="./short_term_memory.db")
agent = Agent(short_term_memory=short_term_memory)
runner = Runner(agent=agent, short_term_memory=short_term_memory, app_name="memory_demo")

await runner.run(messages="我叫小明。", session_id="user-42-chat")
await runner.run(messages="我叫什么名字？", session_id="user-42-chat")  # 能记住
```

- 相同的 `session_id` → 智能体能看到之前的对话轮次。
- `backend="sqlite"` 会把会话持久化到本地 `.db` 文件，进程重启后依然存在。
  若想要进程退出即消失的内存会话，使用 `backend="local"`。
- 其他后端：`mysql`、`postgresql`（通过环境变量 / `config.yaml` 配置）。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 然后填入 MODEL_AGENT_API_KEY
python main.py
```

第二轮应能正确回忆出第一轮提到的名字和颜色。再次运行，智能体仍然记得
（会话保存在 `short_term_memory.db` 文件中）。

## 下一步

- 修改 `SESSION_ID` 再运行一次 —— 这是一段全新的、没有记忆的对话。
- 短期记忆作用于*同一段*对话内。若需要*跨对话、跨用户*持久化的知识，
  请参阅 [VeADK 文档](https://volcengine.github.io/veadk-python/) 中的长期记忆（long-term memory）。
- 继续阅读 [04 · 联网搜索](../04_web_search/)，体验内置的火山引擎工具。
