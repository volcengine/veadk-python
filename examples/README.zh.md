# VeADK 示例

一份动手实践的 VeADK 上手指南，从最小可运行的智能体，一路到多智能体工作流。
每个目录都自成一体：一个 `main.py`、一个 `.env.example`，以及中英双语 README。

> English version: [README.md](./README.md)

## 学习路径

| # | 示例 | 难度 | 你将学到 |
| --- | --- | --- | --- |
| 01 | [快速开始](./01_quickstart/) | 简单 | `Agent` + `Runner`，一问一答 |
| 02 | [自定义工具](./02_custom_tools/) | 简单 | 让智能体调用你的 Python 函数 |
| 03 | [短期记忆](./03_short_term_memory/) | 中等 | 带持久会话的多轮对话 |
| 04 | [联网搜索](./04_web_search/) | 中等 | 使用内置的火山引擎工具 |
| 05 | [知识库 RAG](./05_knowledgebase_rag/) | 中等 | 让回答基于你自己的文档 |
| 06 | [多智能体工作流](./06_multi_agent/) | 复杂 | 用 `SequentialAgent` 组合多个专家智能体 |
| 07 | [结构化输出](./07_structured_output/) | 中等 | 用 `output_schema` 获得经校验的 JSON |
| 08 | [模型配置](./08_model_config/) | 简单 | 模型回退 + 每个智能体的 `model_extra_config` |
| 09 | [长期记忆](./09_long_term_memory/) | 复杂 | 跨会话回忆事实（`auto_save_session`） |
| 10 | [智能体路由](./10_agent_routing/) | 复杂 | 协调者动态委派给专家智能体 |
| 11 | [链路追踪](./11_tracing/) | 复杂 | 观测大模型/工具调用；导出 span |

另外还有可通过 `veadk frontend --agents-dir examples` 运行的 frontend 示例：

- [`a2ui_agent/`](./a2ui_agent/) 展示由智能体驱动的 UI。
- [`multimodal_agent/`](./multimodal_agent/) 分析从聊天输入框上传的图片、
  TXT/Markdown、PDF 和视频。

如需一个可部署的**完整应用**（Web 前端 + Agent API 同处一个容器，通过
`veadk agentkit` 部署到火山引擎 AgentKit），参见 [`basic-app/`](./basic-app/)。

这些示例按概念分组：01–02 基础，03 与 09 记忆，04–05 工具与知识，
06 与 10 多智能体，07–08 模型行为，11 可观测性。

## 通用准备

1. 安装 VeADK（示例 05 需要 `extensions` 扩展）：

   ```bash
   pip install veadk-python
   # RAG 示例需要：
   pip install "veadk-python[extensions]"
   ```

2. 在每个示例目录下，复制环境变量模板并填入你的密钥：

   ```bash
   cd 01_quickstart
   cp .env.example .env
   ```

   VeADK 会自动从当前工作目录加载 `.env`。你也可以改用 `config.yaml`，
   详见[配置文档](https://volcengine.github.io/veadk-python/configuration/)。

3. 运行：

   ```bash
   python main.py
   ```

## 核心概念一览

- **`Agent`** —— 模型 + 指令 + 工具 + 记忆/知识。创建一次即可，自动从环境读取模型配置。
- **`Runner`** —— 驱动一次对话；`await runner.run(messages=..., session_id=...)` 返回最终回答文本。
- **工具（Tools）** —— 任意带类型注解和 docstring 的 Python 函数；内置工具位于
  `veadk.tools.builtin_tools`。
- **记忆（Memory）** —— 短期记忆（对话上下文，按 `session_id` 区分）与长期记忆（跨会话）。
- **知识库（KnowledgeBase）** —— 对你的文档做 RAG，自动添加检索工具。
- **工作流智能体** —— `SequentialAgent`、`ParallelAgent`、`LoopAgent`，用于编排多个智能体。

## 了解更多

- 文档：<https://volcengine.github.io/veadk-python/>
- 教程 Notebook：[`veadk_tutorial.ipynb`](../veadk_tutorial.ipynb)
