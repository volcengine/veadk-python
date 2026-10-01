# veADK 上下文压缩开发者入门

当前支持 `google-adk>=1.34.0,<2.3.0`，默认安装由依赖解析器选择兼容版本；CI 固定验证 1.34.0、2.1.0、2.2.0 的 Python 3.10 / 3.12 组合。**ADK 2.3 及以上（含 2.9.2）暂不支持**：它们要求 OpenTelemetry ≥1.39，而 AgentKit SDK 0.8.x 要求 ≤1.37。请勿使用 `--no-deps` 强行安装；开启、关闭上下文压缩均遵守此 SDK 依赖范围。


日期：2026-10-01。本文对应开发分支 `feat/default-context-compression`，包含默认 BM25 中英文检索和独立 JSON 模型容量配置。当前为开发版本，尚未正式发布；已安装的 PyPI 版本不一定具备本文行为。

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

### 4.1 显式开启 embedding，并准备完整索引

更重视长材料中的语义召回时，先在运行环境配置 `MODEL_EMBEDDING_API_KEY`、`MODEL_EMBEDDING_NAME`、`MODEL_EMBEDDING_DIM` 和 `MODEL_EMBEDDING_API_BASE`，再直接创建 Agent：

```python
from veadk import Agent

agent = Agent(
    name="assistant",
    context_compression={
        "prepare_index": True,
        "index_path": ".adk/context-index.sqlite3",
    },
)
```

不用解析 Session、手动注册回查工具或编写索引回调。输入触发压缩时，SDK 先准备本次可用材料的索引，再按当前问题挑选证据；后续调用可以复用 SQLite 中已完成的批次。原始记录仍由 Session 保存，索引不是 Session 的替代品。长材料沿用自适应父子切块：准备完成指当前检索层的索引完整，不代表全部子片段已提前计算。

- `prepare_index` 默认关闭；显式开启后仍需要配置 embedding。没有 embedding 时继续使用 BM25，不会下载模型。
- 准备阶段每次 Agent invocation 累计最多 **60 秒、512 条 embedding 请求**，与检索阶段原有的 **64 条请求、5 秒共享检索预算**分开计算。并发仍为 4；这些都是上限，不是固定消耗。参数分别为 `index_preparation_timeout_seconds`、`index_preparation_max_calls` 和 `embedding_max_calls`。
- 这是请求内的准备阶段，会增加首次处理长材料的延迟和 embedding 费用；不是后台任务。如果设置整轮 `request_timeout_seconds`，准备阶段最多使用当时剩余时间的一半，不延长总时限。
- 只处理实际输入中已授权的工具文本或可整理的旧文本历史，最多 8 个来源。工具材料优先，近期对话和未完成工具结果不纳入历史准备。不保证一次完成任意大小的材料；超时或失败回退，后续可续建。
- 部分索引不会冒充完整语义索引。索引保存材料片段，应放在受控持久目录；原文回查仍须通过 Session 身份和内容校验。
- 自定义 `use_context_retriever(...)` 的索引准备由调用者管理；该开关只作用于 SDK 默认检索器。

只关闭提前准备：`context_compression={"prepare_index": False}`。关闭所有在线 embedding：`context_compression={"retrieval": "lexical"}`。关闭压缩变换：`context_compression=False`。

该开关解决完整索引的接入问题，不能保证某个固定评测分数。短示例通常不会触发压缩；真实材料达到预算阈值才会执行。

## 5. 什么时候压缩，需要调参吗

建议先使用默认值，确认业务质量后再调整。

| 参数 | 默认值 | 含义 |
| --- | ---: | --- |
| trigger_ratio | 0.80 | 输入达到可用预算的 80% 时，开始整理长材料和工具结果 |
| target_ratio | 0.60 | 尽量把输入降到可用预算的 60% |
| summary_trigger_ratio | 0.95 | 输入达到可用预算的 95% 时，允许摘要整理旧对话 |

这些比例针对的是可用输入预算，不是模型标称总窗口，也不是固定的节省百分比。保留的近期对话、必要证据以及工具调用配对都会影响实际压缩量。

### 5.1 模型容量从哪里来

容量优先取 SDK 配置文件 `veadk/context/model_capacities.json`，其次使用随 LiteLLM 安装的本地精确条目；当前不会实时请求方舟容量接口。模型容量与协议参数均在 JSON 中维护，Python 只负责加载、校验和查询，当前手工表覆盖 76 个型号、9 个服务商、21 个别名，详见[覆盖范围与官方来源](context-compression-model-coverage.zh.md)及[模型上下文容量配置说明](context-compression-capacity-config.zh.md)。私有接入点或未覆盖的模型，需要按部署的实际限制配置 context_window，并通过 output_reserve 明确预留输出空间。不能只凭模型家族猜窗口，也不能用 input_limit 代替总窗口。

维护已有模型的窗口时，只修改 `veadk/context/model_capacities.json` 中相应版本的条目，保留来源与核实日期，不需要修改 Python 代码。配置随 SDK 包交付；修改后重新构建、安装并重启应用，当前不提供热更新。

容量未知时会返回 model_capacity_required 等明确错误。必要输入无法安全缩减、图片容量无法可靠估计等情况下，仍可能需要业务侧缩减输入或配置媒体预留，不能承诺消除所有超限错误。

需要查看能力状态时，可使用 agent.context_compression_status；它反映的是能力状态，不是每轮的实际压缩率。自定义模型适配器、外部执行器或实时音视频路径是否支持，需要单独确认。

## 6. 代码位置与验证状态

以下路径均相对于 SDK 仓库根目录：

| 文件或目录 | 用途 |
| --- | --- |
| veadk/context/config.py | 开关与预算参数 |
| veadk/context/defaults.py、veadk/context/index_preparation.py | 默认检索器、独立准备预算与来源校验 |
| veadk/context/lexical_retriever.py、veadk/context/_hybrid_index.py | 无模型 BM25 检索与分词 |
| veadk/context/manager.py、veadk/context/summary.py | 请求压缩与旧对话摘要 |
| veadk/context/model_capacities.json | 模型容量、别名、输出规划和协议配置 |
| veadk/context/model_capacity.py | 配置加载、校验与精确查询 |
| veadk/runner.py、veadk/memory/ | Session 与 SQLite 持久化 |
| tests/context/ | 压缩、预算、检索和原文回查回归 |

容量扩展新增了最大输入限制、默认生成型号及兼容接口别名的离线回归，已纳入强制门禁。此前已完成容量定向回归、前端全量与生产构建、Ruff、Pyright、pre-commit、打包及安装验证；当前候选的完整门禁结果见下文，详见[模型覆盖说明](context-compression-model-coverage.zh.md)。本文示例已对照公开 API 核对并完成语法静态检查；上述容量与打包验证不调用真实模型。

SQLite 超时恢复回归分别验证预算、真实取消、已完成批次持久化及恢复仅补缺失片段；两个 Python 版本下加入 500ms 异步停顿均通过。生产超时参数未变。

这些属于工程验证，不能替代业务自身的质量评测，也不代表新默认已达到旧 embedding 方案的公开问答分数。Python 3.10 / 3.12 的发布与依赖回归各 10 项通过；基础安装和 eval 扩展均排除已知不兼容的 ADK 版本。远端检查以 [PR #1152](https://github.com/volcengine/veadk-python/pull/1152) 的当前提交为准，完整 Studio 发行与线上业务验收另行执行。

本次索引准备新增 14 项机制回归；Python 3.10 / ADK 1.34.0 与 Python 3.12 / ADK 2.2.0 的完整门禁各 1,320 项通过、5 项跳过，定向 67 项全部通过。三个核心回归已在修复前复现失败。

完整回归入口：`python tests/run_context_compression_gate.py -q`。

模型容量的配置格式与维护说明见[容量配置参考](context-compression-capacity-config.zh.md)。
