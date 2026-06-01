# 04 · 内置工具：联网搜索

使用 VeADK 提供的开箱即用工具。`web_search` 会调用火山引擎的搜索 API，
让智能体能基于最新的真实信息作答。

> English version: [README.md](./README.md)

## 核心思想

```python
from veadk.tools.builtin_tools.web_search import web_search

agent = Agent(tools=[web_search])
```

内置工具位于 `veadk.tools.builtin_tools`（联网搜索、图像生成、语音合成、代码沙箱等）。
它们的用法与自定义函数完全一样 —— 放进 `tools=[...]` 即可。

## 凭证

`web_search` 调用火山引擎搜索 API，因此除模型密钥外还需要一对火山引擎 **AK/SK**：

- `VOLCENGINE_ACCESS_KEY`
- `VOLCENGINE_SECRET_KEY`

可在[火山引擎 IAM 控制台](https://console.volcengine.com/iam/keymanage)创建。

## 运行步骤

```bash
pip install veadk-python
cp .env.example .env   # 填入 MODEL_AGENT_API_KEY 以及 VOLCENGINE_ACCESS_KEY/SECRET_KEY
python main.py
```

智能体会自行决定调用 `web_search`，并基于搜索结果作答。

## 下一步

- 浏览 `veadk/tools/builtin_tools/` 下的其他工具（如 `image_generate`、`tts`、`link_reader`）。
- 继续阅读 [05 · 知识库 RAG](../05_knowledgebase_rag/)，让回答基于你自己的文档。
