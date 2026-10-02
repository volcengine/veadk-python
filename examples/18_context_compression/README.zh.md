# 18 — 可恢复的上下文压缩

本例用两轮问答演示长工具结果压缩：430 条合成库存记录交给 Agent，先问记录 113，再问记录 227。完整记录保存在 SQLite，模型输入按需保留相关证据和来源引用。

## 运行

安装包含本 PR 的 SDK；在仓库根目录可执行 `pip install -e .`。进入本目录，将 `.env.example` 复制为 `.env`，填写你自己的业务模型、地址与认证，然后运行：

```bash
python main.py
```

预期事实：记录 113 的库存为 **2599 units**，记录 227 为 **5221 units**。真实回答质量需要实际模型验证，这两个数来自合成数据，并非评测分数。

示例将 `input_limit` 设为 16000，让小规模材料也能触发压缩。这是教学用输入预算；生产中建议先省略此覆盖，使用模型容量和默认触发比例。模型仍需有已知上下文容量；私有接入点请按真实限制设置 `context_window` 和 `output_reserve`。

## 默认接入只需创建 Agent

```python
from veadk import Agent

agent = Agent(name="assistant")  # 沿用运行环境配置的业务模型
```

- 不配置 embedding：使用中英文 BM25，不下载模型，也不调用默认重排模型。
- 显式配置 `MODEL_EMBEDDING_API_KEY`：自动启用索引准备和模型候选重排，不必再设置 `prepare_index=True`、`rerank=True`。可用模板中的其他 embedding 字段覆盖模型、维度和地址。
- 摘要和重排沿用 Agent 当前的模型、地址和认证，不固定为 Flash。方舟 Chat / Responses 的辅助请求关闭 thinking，业务主回答配置不变。
- 模型重排只返回合法片段 ID，SDK 取回对应原文；失败或超时保留原顺序。辅助调用受容量、次数和时间限制，会增加相应调用费与延迟。

独立关闭：

```python
agent = Agent(name="assistant", context_compression={"prepare_index": False})
agent = Agent(name="assistant", context_compression={"rerank": False})
agent = Agent(name="assistant", context_compression={"retrieval": "lexical"})
agent = Agent(name="assistant", context_compression=False)
```

上述依次关闭提前准备、模型重排、在线检索与默认重排、压缩变换。最后一种仍保留容量检查。

## 会话与原文

`.adk/compression-demo.db` 是持久 Session；`.adk/context-index.sqlite3` 是可再生索引。继续同一会话时保持数据库、应用、用户、Session 和 Agent 名称一致。重新演示时可改用新的 Session ID，避免把已有记录误当作首次处理。

只有后续业务缺少证据时才需调用 `veadk_read_context` 搜索或分页读取原文，开发者不用解析压缩结果或手动注册该工具，也不应强制每轮回查。SQLite 适合本地或单实例持久卷；不要将 Session 数据当缓存删除。

详见[开发者指南](../../docs/context-compression-developer-guide.zh.md)。
