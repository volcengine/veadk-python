# 05 · 知识库 RAG

通过检索增强生成（RAG），让智能体基于*你自己的*文档作答。`KnowledgeBase` 会把文档
向量化并存入向量库；当它被挂载到 `Agent` 上时，VeADK 会自动为其添加检索工具。

> English version: [README.md](./README.md)

## 核心思想

```python
knowledgebase = KnowledgeBase(backend="local", index="company_faq")
knowledgebase.add_from_directory("./docs")

agent = Agent(knowledgebase=knowledgebase)   # 自动添加检索工具
```

提问时，智能体会从你的文档中检索最相关的片段并据此作答 —— 因此它能正确回答
基座模型从未见过的问题（本例中是 `docs/` 里 Acme 公司的内部年假 / 远程办公政策）。

## 前置依赖

`local` 后端需要对文档做 embedding，因此需要：

1. 安装可选扩展依赖：

   ```bash
   pip install "veadk-python[extensions]"
   ```

2. 配置 **embedding 模型**（`MODEL_EMBEDDING_*`）。若不单独配置 embedding 密钥，
   VeADK 会复用 `MODEL_AGENT_API_KEY`。

## 运行步骤

```bash
cp .env.example .env   # 填入 MODEL_AGENT_API_KEY（以及 embedding 配置）
python main.py
```

关于年假 / 远程办公的回答直接来自 `docs/company_faq.md`，而非模型的固有知识。

## 下一步

- 把你自己的 `.md` / `.txt` / `.pdf` 文件放进 `docs/` 并就其内容提问。
- 将 `backend="local"` 替换为持久化存储（如 `openviking`、`milvus`、`viking`、
  `opensearch`、`redis`，在 `.env` 或 `config.yaml` 中配置），用于生产环境。
- 继续阅读 [06 · 多智能体工作流](../06_multi_agent/)，组合多个智能体。
