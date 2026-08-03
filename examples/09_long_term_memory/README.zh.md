# 09 · 长期记忆

*跨对话*记住事实。短期记忆（[03](../03_short_term_memory/)）作用于单段会话内，
而长期记忆能跨越不同会话（乃至不同用户）持久保存，并在需要时被检索。

> English version: [README.md](./README.md)

## 核心思想

```python
long_term_memory = LongTermMemory(backend="local", app_name="ltm_demo")
agent = Agent(
    long_term_memory=long_term_memory,   # 添加 `load_memory` 工具
    auto_save_session=True,              # 自动把每段会话存入记忆
)
```

- `long_term_memory=...` 为智能体添加 **`load_memory`** 工具，用于检索过往会话。
- `auto_save_session=True` 会在每段会话结束后自动写入长期记忆。

本示例中，会话 #1 告诉智能体饮食限制；会话 #2 是一段*全新*对话，但智能体仍能
通过检索记忆（而非上下文窗口）回忆起来。

## 前置依赖

`local` 后端需要对记忆做 embedding，因此需要：

```bash
pip install "veadk-python[extensions]"
```

以及 embedding 模型配置（`MODEL_EMBEDDING_*`，可回退到 `MODEL_AGENT_API_KEY`）。

## 运行步骤

```bash
cp .env.example .env   # 填入 MODEL_AGENT_API_KEY（以及 embedding 配置）
python main.py
```

会话 #2 的推荐应当尊重会话 #1 中提到的花生过敏与素食偏好。

## 下一步

- 短期 vs 长期：会话内的记忆见 [03](../03_short_term_memory/)。
- 把 `backend="local"` 换成持久化存储（`openviking`、`viking`、`redis`、
  `opensearch`、`mem0`），让记忆在进程重启后依然存在。

### OpenViking 变体

使用 OpenViking 时，先配置服务连接和 owner/context ID：

```bash
export DATABASE_OPENVIKING_URL="http://127.0.0.1:1933"
export DATABASE_OPENVIKING_API_KEY="your-openviking-api-key"
export DATABASE_OPENVIKING_USER_ID="agent_context"
```

然后切换后端：

```python
long_term_memory = LongTermMemory(
    backend="openviking",
    app_name="ltm_demo",
    backend_config={
        # 可选；不配置时保持 VeADK 默认 OpenViking policy。
        "memory_policy": {
            "self": {"enabled": False},
            "peer": {"enabled": True},
            "memory_types": ["entities", "events", "preferences"],
        },
    },
)
```

`Runner.user_id` 仍表示最终用户，并会作为 OpenViking `peer_id` 传入。
`DATABASE_OPENVIKING_USER_ID` 表示 OpenViking 里的记忆 owner/context，未配置时默认
`default`。
