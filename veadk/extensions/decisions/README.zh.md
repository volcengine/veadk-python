# VeADK 决策模型扩展

[English](README.md)

`veadk.extensions.decisions` 为 VeADK 增加一个可选的**决策模型**：它不生成文本，
而是返回类型化判断（选项、评分、或某个条件成立的概率）。它与 Agent 的对话模型相互独立、
provider 无关，并且默认关闭——不配置时 VeADK 其它行为完全不变。

适合把「小而重复的判断」从慢模型调用里拿出来：请求分流、候选排序、从封闭集合里取值、
校验某个断言是否成立。

## 安装

扩展随 VeADK 一起发布，无需额外依赖。

```bash
pip install veadk-python
```

## 配置

```text
DECISION_MODEL_ENABLED=true
DECISION_MODEL_PROVIDER=typesafe        # typesafe | openrouter | systemone
DECISION_MODEL_NAME=jev-latest
DECISION_MODEL_API_BASE=https://api.typesafe.ai
DECISION_MODEL_API_KEY=...
DECISION_MODEL_TIMEOUT=5                 # 单次判定的秒数（上限 5）
DECISION_MODEL_MAX_RETRIES=3
DECISION_MODEL_FAILURE_THRESHOLD=3       # 0 表示不熔断
DECISION_MODEL_COOLDOWN_SECONDS=30
```

`DECISION_MODEL_TIMEOUT` 是**一次判定**的总时间预算，重试与退避都算在里面。超过 5 秒
会被截断为 5 秒并打 warning：判定位于 Agent 主链路上，端点慢应该降级这次判定，
而不是拖住整轮运行。

三种 provider 走同一套 System One 协议，切换只改 base URL 与 API Key。provider
决定默认 `api_base`：

| provider | 默认 `api_base` | 说明 |
| --- | --- | --- |
| `typesafe` | `https://api.typesafe.ai` | 官方托管 Jev |
| `openrouter` | `https://openrouter.ai/api` | OpenRouter 转发同一模型；用 OpenRouter 的 Key，模型 ID 可写 `jev-1.13` / `jev-latest` / `typesafe/jev-1.13`；响应会多返回 `id`、`provider`、`usage.cost` |
| `systemone` | 无 | 自建 System One，必须显式指定 `api_base` |

显式设置的 `DECISION_MODEL_API_BASE` 始终优先；带不带 `/v1/systemone` 都可以。

同样的配置也可以写在 `config.yaml` 里——VeADK 会把配置压平成 `MODEL_DECISION_*`
环境变量。两种写法同时存在时，显式的 `DECISION_MODEL_*` 优先。

```yaml
model:
  agent: {}
  decision:
    enabled: true
    provider: typesafe
    name: jev-latest
    api_base: https://api.typesafe.ai
    api_key: ${YOUR_KEY}
```

## 快速开始

```python
from veadk.extensions.decisions import DecisionExtension

extension = DecisionExtension.from_env()

if extension.enabled:
    answer = await extension.achoose(
        "我的卡被扣了两次钱。",
        "Which team should handle this?",
        ["billing", "shipping", "returns"],
    )
    print(answer.choice, answer.confidence, answer.probabilities)
```

答案都是类型化对象：`ChoiceAnswer`、`ScoreAnswer`、`NoulAnswer`。`noul`（“是”的概率）
本身没有单独的置信度，请直接使用，并且阈值要在自己的数据上测过再定。

| 调用 | 返回 |
| --- | --- |
| `evaluate(state, questions)` / `aevaluate` | 一个 state 的全部答案，一次请求批量问完 |
| `choose(state, instructions, options)` / `achoose` | `ChoiceAnswer` |
| `score(state, instructions, levels)` / `ascore` | `ScoreAnswer` |
| `noul(state, instructions)` / `anoul` | `NoulAnswer` |

互相独立的问题请放进**同一次** `evaluate`：它们并行判定，代码可以忽略用不到的答案。

## 把工具交给 Agent

```python
from veadk import Agent
from veadk.extensions.decisions import decision_evaluate

agent = Agent(name="router", tools=[decision_evaluate])
```

该工具向已配置的决策模型要一个判断，返回 `{"kind", "answer", "confidence", ...}`；
当决策模型未配置或请求失败时返回 `{"error": ...}`，不会因为可选能力而中断整轮运行。

## 失败与降级

决策模型是可选的，所以调用方只需要处理一种错误类型：`DecisionModelError`。
无论哪种异常，都是这次判定降级为调用方自己的规则，而不是中断整轮运行。

| 异常情况 | 结果 |
| --- | --- |
| 未配置 / 没有 API Key | 首次调用抛 `DecisionModelDisabledError`，其它行为完全不变 |
| 超时、连接失败、`429`、`5xx` | 在 `timeout` 预算内指数退避重试（尊重 `retry-after`），仍失败则抛 `DecisionModelRequestError` |
| 其它 `4xx` | 不重试，抛 `DecisionModelRequestError`，带状态码与响应片段 |
| `200` 但答案不可用 | 抛 `DecisionModelResponseError`；字段缺失、类型未知都一样对待，不会漏出 `pydantic` 或 `httpx` 的原始异常 |
| `DECISION_MODEL_TIMEOUT` 超过上限 | 截断为 5 秒并打 warning |
| 启动时配置不可用 | 自动关闭该扩展并打 warning，不影响启动 |
| 连续失败达到 `DECISION_MODEL_FAILURE_THRESHOLD`（默认 3） | 端点被标记为不可用，冷却 `DECISION_MODEL_COOLDOWN_SECONDS`（默认 30 秒）内直接抛 `DecisionModelUnavailableError` 且不发 HTTP 请求；冷却后放一个探测请求决定是否恢复 |

日志克制且不含用户数据：

| 级别 | 内容 |
| --- | --- |
| `DEBUG` | 每次成功判定一行：模型、耗时、token、成本 |
| `INFO` | 冷却结束发出探测请求；判定恢复 |
| `WARNING` | 一次重试；判定失败导致端点被标记不可用；配置被截断或不可用 |

被判定的 state 原文与 API Key 都不进日志。

## 判定阈值

每个判定点各自持有阈值，比较的都是「是」的概率在 `[0, 1]` 上的取值：

| 判定点 | 阈值 | 默认 |
| --- | --- | --- |
| 压缩候选 | `HARNESS_COMPACTION_KEEP_THRESHOLD` | 0.5 |
| 长任务引导 | `HARNESS_LONG_RUN_READY_THRESHOLD` | 0.5 |
| 上下文模式块 | `HARNESS_MODE_DECISION_THRESHOLD` | 0.5 |
| 记忆落库 | `MEMORY_SAVE_WORTH_THRESHOLD` | 0.5 |

解析统一走 `probability_threshold()`：越界的值**夹紧**而不是回落（`1.5 → 1.0`、
`-1 → 0.0`，保留「永不生效 / 总是生效」的原意，回落会把行为整个翻转）；`NaN`
或非数字没有原意可保留，回落到默认值并打 warning。阈值之间相互独立——同一个概率
落在不同判定点上代价不同，调高一处不会连带影响其它判定点。

## 目录结构

| 路径 | 作用 |
| --- | --- |
| `config.py` | 配置与环境变量解析、端点规范化 |
| `client.py` | System One HTTP 客户端（同步/异步），带退避重试 |
| `questions.py` | 三种问题类型的构造器 |
| `types.py` | 类型化答案与响应解析 |
| `extension.py` | 统一入口：`DecisionExtension` 与进程级默认实例 |
| `tools.py` | 面向 Agent 的 `decision_evaluate` 工具 |

## 暂未包含

- 使用决策模型的运行时插件（工具过滤、上下文压缩、回答核验）。共享的
  `DecisionExtension` 实例就是它们预留的接入点。
- 把 `decision_evaluate` 注册进核心内置工具表（`veadk/tools/__init__.py`）：前端
  studio 的工具目录有一份必须与核心注册表完全一致的静态声明表，注册时需要同步补上
  声明与 schema。
- 响应缓存与连接复用；目前每次调用都会新建 HTTP 客户端。
- 非英文问题文本：即使被判定的 state 是中文，`instructions` 也建议用英文写，
  判定质量更稳。
