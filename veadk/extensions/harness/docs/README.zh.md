# veADK Harness Extension 使用指南

[English](README.md)

这份文档帮助开发者从零开始使用 SDK。

## 安装

```bash
pip install "veadk-python[harness]"
```

Harness Extension 已随 veADK 内置。`harness` extra 会安装可选的进程内
Headroom provider，用于 `HARNESS_COMPRESSION_PROVIDER=headroom`。

## 它解决什么问题

veADK Harness Extension 给 veADK Agent 增加一层轻量控制能力：

1. 在模型调用前准备精简上下文。
2. 在大工具结果进入后续对话前进行压缩。
3. 记录工具执行 receipt，并检查最终回答是否有证据支撑。

当你的 Agent 会调用工具、处理长输出，或者需要更强的回答可靠性时，可以使用它。

## 核心概念

| 概念 | 含义 |
| --- | --- |
| Harness module | 可直接 import 和测试的独立原子能力。 |
| Harness plugin | 面向 veADK Runner 的运行时增强能力。 |
| Invocation context block | 模型调用前注入的精简上下文块。 |
| Tool receipt | 工具执行结果的简短记录，包括工具名称、状态和摘要。 |
| Compaction report | 记录上下文或工具输出压缩效果的指标。 |
| Verification report | 判断最终回答是否有证据支撑的结果。 |

## 用 Plugin 接入

```python
from veadk.extensions.harness.adk import build_harness_plugins
from veadk import Agent, Runner

agent = Agent(name="demo_agent")
runner = Runner(
    agent=agent,
    app_name="demo",
    plugins=build_harness_plugins(
        components=["invocation_context", "compactor", "response_verification"],
    ),
)
```

## 直接使用原子模块

```python
from veadk.extensions.harness import HarnessInvocationContextBuilder, HarnessInvocationRef

context = HarnessInvocationRef(session_id="s1", invocation_id="r1")
bundle = HarnessInvocationContextBuilder().prepare_context(
    context,
    user_input="Find the best model from the tool result.",
)
print(bundle.header)
```

```python
from veadk.extensions.harness.modules.tool_result_compactor import ToolResultCompactor

compactor = ToolResultCompactor()
compressed, report = compactor.compress_tool_result({"rows": "x" * 8000})
print(compressed)
print(report.model_dump())
```

## 配置

最小运行时配置：

```text
HARNESS_ENHANCE_ENABLED=true
HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
HARNESS_PROFILE=default
HARNESS_COMPRESSION_PROVIDER=builtin
```

压缩 provider：

| Provider | 行为 |
| --- | --- |
| `builtin` | 默认 provider。使用本地结构化压缩和安全摘要 fallback。 |
| `headroom` | 进程内调用已安装的本地 `headroom` Python 包；不会启动服务，也不会在运行时安装依赖；不可用时自动回退到 `builtin`。 |

验证默认是 observe 行为。高级运行时可以配置 block 行为，用于阻断缺少证据支撑的最终回答。

## 评测

运行确定性测试：

```bash
PYTHONPATH=. pytest -q tests/extensions/harness
```

运行本地 HarnessApp 延迟和上下文 benchmark：

```bash
PYTHONPATH=. python \
  veadk/extensions/harness/examples/harness_app_runtime/stable_latency_token_case.py \
  --repeats 3
```

benchmark 会对比普通调用和 Harness 增强调用，并输出延迟、prompt 上下文长度、
压缩比例和答案一致性。
