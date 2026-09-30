# veADK 上下文压缩开发者入门

当前支持 `google-adk>=1.34.0,<2.3.0`，默认安装由依赖解析器选择兼容版本；CI 固定验证 1.34.0、2.1.0、2.2.0 的 Python 3.10 / 3.12 组合。**ADK 2.3 及以上（含 2.9.2）暂不支持**：它们要求 OpenTelemetry ≥1.39，而 AgentKit SDK 0.8.x 要求 ≤1.37。请勿使用 `--no-deps` 强行安装；开启、关闭上下文压缩均遵守此 SDK 依赖范围。


日期：2026-09-30。本文对应开发分支 `feat/default-context-compression`，包含默认 BM25 中英文检索和独立 JSON 模型容量配置。当前为开发版本，尚未正式发布；已安装的 PyPI 版本不一定具备本文行为。

## 1. 它解决什么问题

长对话、大段工具结果和长文档会持续占用模型输入窗口。veADK 在每次发送请求前检查容量，按需把旧材料缩减为相关证据、摘要和来源引用，尽量保留回答当前问题所需的信息，降低输入超限的风险。

两个边界需要特别注意：

- 压缩对象是发给模型的输入，Session 中的原始记录始终完整保存。旧材料在模型输入里变成证据、摘要和来源引用；业务需要细节时，模型可以调用 veadk_read_context 搜索或分页读取原文，不必每轮强制回查。但可以回查不等于回答质量完全无损。
- 默认检索是轻量 BM25，无需 embedding 模型，也不需要下载任何模型。BM25 只负责挑选原文证据；历史摘要和 Agent 回答仍然由 LLM 完成。

## 2. 三分钟接入

先按项目现有方式配置 Agent 的业务模型、服务地址与认证。模型凭证由运行环境提供，不写进示例代码；默认检索也不需要任何 embedding 配置。

```python
from veadk import Agent

# 默认开启上下文压缩；无 embedding 配置时使用 BM25。
agent = Agent(name="assistant")
```

创建时不需要手动挂载压缩回调、注册原文恢复工具或设置语言。已有的业务工具照常用 tools 参数传给 Agent 即可。

三种创建方式：

| 需求 | 创建方式 |
| --- | --- |
| 默认开启压缩，自动选择检索方式 | Agent(name="assistant") |
| 开启压缩，固定使用无模型检索 | Agent(name="assistant", context_compression={"retrieval": "lexical"}) |
| 关闭压缩变换 | Agent(name="assistant", context_compression=False) |

检索方式的选择规则：

- auto（默认）：仅在显式配置环境变量 MODEL_EMBEDDING_API_KEY 时启用在线混合检索，否则使用 BM25；不会复用 Agent 自身的模型密钥。
- lexical：SDK 自带检索器始终不使用 embedding。
- 如果项目已通过 use_context_retriever(...) 主动绑定自定义检索器，自定义检索器优先生效。

关闭压缩后，SDK 仍会检查模型容量；超限或容量未知时，可以在发送前直接报错。它不是绕过模型上下文限制的开关。

## 3. 完整示例：多轮对话与 SQLite 持久化

把下面的代码保存为项目中的 app.py，在已安装候选 SDK、已配置业务模型的环境中运行 python app.py：

```python
import asyncio
from pathlib import Path

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory


async def main():
    # 相对 app.py 固定存储位置，切换工作目录后仍使用同一数据库。
    database = Path(__file__).resolve().parent / "data" / "sessions.db"
    memory = ShortTermMemory(
        backend="sqlite",
        local_database_path=str(database),
    )

    agent = Agent(
        name="assistant",
        # 明确选择无模型检索；其余压缩参数使用默认值。
        context_compression={"retrieval": "lexical"},
    )
    runner = Runner(
        agent=agent,
        short_term_memory=memory,
        app_name="context_demo",
        user_id="demo_user",
    )
    session_id = "demo_session"

    print(await runner.run(
        messages="Remember: invoice INV-418 totals 187.25 USD.",
        session_id=session_id,
    ))
    print(await runner.run(
        messages="What is the total for invoice INV-418?",
        session_id=session_id,
    ))


if __name__ == "__main__":
    asyncio.run(main())
```

### 3.1 这个示例演示了什么

两轮对话内容很短，通常不会触发压缩，目的只是展示接入方式和会话复用。接入真实的长材料或工具结果后，SDK 按预算自动决定是否压缩，业务代码不需要每轮主动调用。

### 3.2 重启后如何继续同一会话

保持同一个数据库、app_name、user_id、session_id 和 Agent 身份，即可继续原会话。线上服务应按登录用户和会话分别设置 ID。如果重启后只是想继续提问，直接执行后续的 runner.run(...) 即可，不需要重新写入第一轮材料。

### 3.3 默认存储与部署注意事项

不显式传入短期记忆或 Session 服务时，当前候选的 Runner 默认保存到工作目录下的 .adk/session.db；显式传入的后端优先。ShortTermMemory(backend="local") 是内存后端，无法保证重启后恢复。

SQLite 适合本地开发或单实例加持久卷的场景。部署时要把数据库所在目录持久化，不能当作缓存清理；多实例服务应配置共享数据库的 Session 后端。BM25 默认路径不创建向量索引，原文恢复依赖 Session 数据。

## 4. 中英文材料如何检索

| 材料 | 默认检索方式 |
| --- | --- |
| 英文 | 按单词匹配，忽略大小写，支持数字和包含下划线的词项 |
| 中文 | 按相邻两个字符匹配，单字单独保留，无需分词模型或词典 |
| 中英混合 | 同时提取两种词项，统一参与 BM25 排序，无需设置语言 |

BM25 按匹配词的区分度、出现次数和片段长度排序，适合日志、订单编号、业务术语和关键词检索。当前不做英文词干还原、同义词扩展或自动翻译：run 与 running 不保证互相召回；仅用英文同义表达查询纯中文材料也不保证有效。

## 5. 什么时候压缩，需要调参吗

建议先使用默认值，确认业务质量后再调整。

| 参数 | 默认值 | 含义 |
| --- | ---: | --- |
| trigger_ratio | 0.80 | 输入达到可用预算的 80% 时，开始整理长材料和工具结果 |
| target_ratio | 0.60 | 尽量把输入降到可用预算的 60% |
| summary_trigger_ratio | 0.95 | 输入达到可用预算的 95% 时，允许摘要整理旧对话 |

这些比例针对的是可用输入预算，不是模型标称总窗口，也不是固定的节省百分比。保留的近期对话、必要证据以及工具调用配对都会影响实际压缩量。

### 5.1 模型容量从哪里来

容量优先取 SDK 配置文件 `veadk/context/model_capacities.json`，其次使用随 LiteLLM 安装的本地精确条目；当前不会实时请求方舟容量接口。模型容量与协议参数均在 JSON 中维护，Python 只负责加载、校验和查询，详见[模型上下文容量配置说明](context-compression-capacity-config.zh.md)。私有接入点或未覆盖的模型，需要按部署的实际限制配置 context_window，并通过 output_reserve 明确预留输出空间。不能只凭模型家族猜窗口，也不能用 input_limit 代替总窗口。

维护已有模型的窗口时，只修改 `veadk/context/model_capacities.json` 中相应版本的条目，保留来源与核实日期，不需要修改 Python 代码。配置随 SDK 包交付；修改后重新构建、安装并重启应用，当前不提供热更新。

容量未知时会返回 model_capacity_required 等明确错误。必要输入无法安全缩减、图片容量无法可靠估计等情况下，仍可能需要业务侧缩减输入或配置媒体预留，不能承诺消除所有超限错误。

需要查看能力状态时，可使用 agent.context_compression_status；它反映的是能力状态，不是每轮的实际压缩率。自定义模型适配器、外部执行器或实时音视频路径是否支持，需要单独确认。

## 6. 代码位置与验证状态

以下路径均相对于 SDK 仓库根目录：

| 文件或目录 | 用途 |
| --- | --- |
| veadk/context/config.py | 开关与预算参数 |
| veadk/context/defaults.py | 默认检索器选择 |
| veadk/context/lexical_retriever.py、veadk/context/_hybrid_index.py | 无模型 BM25 检索与分词 |
| veadk/context/manager.py、veadk/context/summary.py | 请求压缩与旧对话摘要 |
| veadk/context/model_capacities.json | 模型容量、别名、输出规划和协议配置 |
| veadk/context/model_capacity.py | 配置加载、校验与精确查询 |
| veadk/runner.py、veadk/memory/ | Session 与 SQLite 持久化 |
| tests/context/ | 压缩、预算、检索和原文回查回归 |

当前候选已在隔离 Devbox 完成完整门禁：两组各 1,295 项通过、5 项跳过（Python 3.10 / google-adk 1.34.0；Python 3.12 / google-adk 2.2.0），包含无模型检索与新增的容量配置回归；实际安装包的 JSON 配置读取验证通过。本文示例已对照公开 API 核对并完成语法静态检查，本轮未调用真实模型。

SQLite 超时恢复回归分别验证预算、真实取消、已完成批次持久化及恢复仅补缺失片段；两个 Python 版本下加入 500ms 异步停顿均通过。生产超时参数未变。

这些属于工程验证，不能替代业务自身的质量评测，也不代表新默认已达到旧 embedding 方案的公开问答分数。Python 3.10 / 3.12 的发布与依赖回归各 10 项通过；基础安装和 eval 扩展均排除已知不兼容的 ADK 版本。远端检查以 [PR #1152](https://github.com/volcengine/veadk-python/pull/1152) 的当前提交为准，完整 Studio 发行与线上业务验收另行执行。

完整回归入口：`python tests/run_context_compression_gate.py -q`。

模型容量的配置格式与维护说明见[容量配置参考](context-compression-capacity-config.zh.md)。
