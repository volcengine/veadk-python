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
DECISION_MODEL_PROVIDER=typesafe        # typesafe | systemone
DECISION_MODEL_NAME=jev-latest
DECISION_MODEL_API_BASE=https://api.typesafe.ai
DECISION_MODEL_API_KEY=...
DECISION_MODEL_TIMEOUT=30
DECISION_MODEL_MAX_RETRIES=3
```

`typesafe` 是托管服务，`systemone` 是自建 System One 服务，二者请求协议相同，
只是 `api_base` 不同；`api_base` 带不带 `/v1/systemone` 都可以。

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
