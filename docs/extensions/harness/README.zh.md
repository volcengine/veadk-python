# VeADK Harness Extension 使用指南

[English](README.md)

VeADK Harness 是面向工具型 VeADK Agent 的轻量扩展。它在 Agent 调用链路外增加运行时治理能力，不要求你重写 Agent、模型或工具实现。

当你的 Agent 会处理大工具结果、多步长任务，或者最终回答必须基于工具证据时，可以使用 Harness。

## 安装

```bash
pip install "veadk-python[harness]"
```

Harness Extension 随 VeADK 内置。`harness` extra 会安装可选依赖，例如进程内 Headroom 压缩 provider。如果只使用默认 `builtin` provider，不需要额外服务。

## 快速接入

创建 `Runner` 时挂载 Harness plugins：

```python
from veadk import Agent, Runner
from veadk.extensions.harness.plugins import build_harness_plugins


agent = Agent(
    name="research_agent",
    instruction="Answer with evidence from tool results.",
)

runner = Runner(
    agent=agent,
    app_name="research_app",
    plugins=build_harness_plugins(
        components=[
            "invocation_context",
            "compactor",
            "response_verification",
        ],
    ),
)
```

如果你想先做最小验证，可以只启用压缩：

```python
plugins = build_harness_plugins(components=["compactor"])
```

## 组件

| Component | Plugin | 能力 |
| --- | --- | --- |
| `invocation_context` | `HarnessInvocationContextPlugin` | 模型调用前注入任务锚点、近期上下文和工具使用约束。 |
| `compactor` | `HarnessCompressPlugin` | 压缩过大的工具结果和旧 function response。 |
| `response_verification` | `HarnessResponseVerificationPlugin` | 记录 tool receipt，并检查最终回答是否有证据支撑。 |
| `long_run_control` | `HarnessLongRunControlPlugin` | 当运行接近模型调用预算时，注入面向收敛的引导。 |

## 核心概念

| 概念 | 含义 |
| --- | --- |
| Harness module | 可直接 import 和测试的独立原子能力。 |
| Harness plugin | 把原子能力接入 VeADK 生命周期回调的运行时包装。 |
| Invocation context block | 模型调用前注入的精简上下文块。 |
| Tool receipt | 工具调用的简短记录，包括状态和关键证据。 |
| Compaction report | 描述上下文或工具结果压缩效果的指标。 |
| Verification report | 描述最终回答是否有证据支撑的校验结果。 |

## 源码结构

| 路径 | 作用 |
| --- | --- |
| `veadk/extensions/harness/extension.py` | 从代码创建 Harness plugins 的 facade。 |
| `veadk/extensions/harness/env.py` | 从环境变量组装 plugins。 |
| `veadk/extensions/harness/schemas.py` | 公共 Pydantic 模型，例如 `ToolReceipt`、`CompactionReport`、`VerificationReport`。 |
| `veadk/extensions/harness/modules/invocation_context/` | 调用上下文构造原子模块。 |
| `veadk/extensions/harness/modules/tool_result_compactor/` | 工具结果压缩原子模块，以及 builtin / Headroom providers。 |
| `veadk/extensions/harness/modules/final_response_verifier/` | 最终回答校验原子模块。 |
| `veadk/extensions/harness/plugins/entrypoints.py` | 对外 plugin 入口。 |
| `veadk/extensions/harness/plugins/builder/` | 共享 store 的 plugin bundle 组装逻辑。 |
| `veadk/extensions/harness/plugins/invocation_context/` | 调用上下文回调 plugin。 |
| `veadk/extensions/harness/plugins/compactor/` | 工具结果和上下文压缩回调 plugin。 |
| `veadk/extensions/harness/plugins/response_verification/` | Receipt 记录和最终回答校验回调 plugin。 |
| `veadk/extensions/harness/plugins/long_run_control/` | 长任务收敛引导回调 plugin。 |
| `veadk/extensions/harness/plugins/_shared/` | 多个 plugin 共享的内部回调工具。 |
| `veadk/extensions/harness/stores/` | Store 协议，以及内存 / JSONL 实现。 |

## 运行链路

```text
用户消息
  -> invocation_context 构造并注入精简上下文块
  -> 模型调用
  -> 工具调用
  -> compactor 压缩过大的工具结果
  -> 模型基于压缩后的证据继续推理
  -> response_verification 校验最终回答证据
  -> 返回结果
```

这些 plugins 共享一个 store。上下文 plugin 记录消息，压缩 plugin 写入压缩事件，校验 plugin 读取 tool receipt，并根据配置写入 verification metadata 或阻断缺少证据的回答。

## 直接使用原子模块

你也可以不挂 plugin，直接使用原子模块。这适合单元测试、自定义运行时或局部集成验证。

```python
from veadk.extensions.harness import (
    HarnessInvocationContextBuilder,
    HarnessInvocationRef,
)


context = HarnessInvocationRef(session_id="session-1", invocation_id="run-1")
block = HarnessInvocationContextBuilder().prepare_context(
    context=context,
    user_input="Compare the tool results and explain the conclusion.",
)
print(block.header)
```

```python
from veadk.extensions.harness.modules.tool_result_compactor import ToolResultCompactor


tool_result = {
    "title": "Search results",
    "content": "important result\n" + ("raw text\n" * 2000),
}

compacted, report = ToolResultCompactor().compress_tool_result(tool_result)
print(compacted)
print(report.model_dump())
```

```python
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
)
from veadk.extensions.harness.schemas import ToolReceipt


receipts = [
    ToolReceipt(
        name="web_search",
        status="success",
        summary="The release date is 2026-05-01.",
    )
]

report = FinalResponseVerifier().verify_text(
    "The release date is 2026-05-01.",
    receipts=receipts,
)
print(report.model_dump())
```

## Runtime 配置

部署运行时可以使用环境变量：

```bash
export HARNESS_ENHANCE_ENABLED=true
export HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
export HARNESS_COMPRESSION_PROVIDER=builtin
export HARNESS_VERIFIER_MODE=observe
# 可选：把内置规则交给判定模型
# export HARNESS_COMPACTION_STRATEGY=decision
# export HARNESS_LONG_RUN_STRATEGY=decision
# export HARNESS_MODE_STRATEGY=decision
```

等价 YAML：

```yaml
harness_enhance:
  enabled: true
  components: [invocation_context, compactor, response_verification]
  compression_provider: builtin
  verifier_mode: observe
```

也可以在单次请求中通过 CLI 打开：

```bash
veadk agentkit invoke \
  --harness my-agent \
  --endpoint "$HARNESS_URL" \
  --apikey "$HARNESS_KEY" \
  --enable-harness-enhance \
  --harness-components "invocation_context,compactor,response_verification" \
  "Summarize the tool results with evidence."
```

## 配置速查

| 配置 | 默认值 | 说明 |
| --- | --- | --- |
| `HARNESS_ENHANCE_ENABLED` | `false` | 是否在运行时组装 Harness plugins。 |
| `HARNESS_ENHANCE_COMPONENTS` | `invocation_context,compactor,response_verification` | 启用哪些组件。 |
| `HARNESS_COMPRESSION_PROVIDER` | `builtin` | 压缩 provider，支持 `builtin` 或 `headroom`。 |
| `HARNESS_MAX_CONTEXT_CHARS` | `24000` | 上下文压缩阈值。 |
| `HARNESS_MAX_TOOL_RESULT_CHARS` | `4000` | 工具结果压缩阈值。 |
| `HARNESS_VERIFIER_MODE` | `observe` | 校验行为，支持 `observe` 或 `block`。 |
| `HARNESS_VERIFIER_STRATEGY` | `deterministic` | 最终回答校验策略：`deterministic` 或 `decision`。 |
| `HARNESS_VERIFIER_SUPPORT_THRESHOLD` | `0.5` | 最终回答支撑度阈值；判定低于该值即判为失败。 |
| `HARNESS_STORE_PATH` | 未设置 | 设置后使用 JSONL event store。 |
| `HARNESS_COMPACTION_STRATEGY` | `builtin` | 压缩候选策略：`builtin` 或 `decision`。 |
| `HARNESS_LONG_RUN_STRATEGY` | `counter` | 长任务引导策略：`counter` 或 `decision`。 |
| `HARNESS_MODE_STRATEGY` | `keywords` | 上下文模式块策略：`keywords` 或 `decision`。 |
| `HARNESS_COMPACTION_KEEP_THRESHOLD` | `0.5` | 压缩候选：概率高于该值即保留。 |
| `HARNESS_LONG_RUN_READY_THRESHOLD` | `0.5` | 长任务引导：概率高于该值即引导收尾。 |
| `HARNESS_MODE_DECISION_THRESHOLD` | `0.5` | 上下文模式块：概率高于该值即注入。 |

## 判定模型策略

四个 `*_STRATEGY=decision` 开关把一条规则换成判定模型的判定结果，需要 `DECISION_MODEL_ENABLED=true` 与 API Key；没有配置时各自保留原规则并打印告警。

| 策略 | 被替代的规则 | 判定不可用时 |
| --- | --- | --- |
| `HARNESS_COMPACTION_STRATEGY` | 按角色和长度挑选压缩候选 | 内置规则 |
| `HARNESS_LONG_RUN_STRATEGY` | 仅按模型调用次数计数 | 计数规则，超过强制次数后必定生效 |
| `HARNESS_MODE_STRATEGY` | 精度/产物关键词匹配 | 关键词匹配 |
| `HARNESS_VERIFIER_STRATEGY` | 完成类关键词加「有无成功回执」 | 内置规则 |

### 判定阈值

每个判定点各自持有阈值，比较的都是「是」在 `[0, 1]` 上的概率：同一个概率在不同判定点上代价不同，所以调高一个点不会连带抬高其它点。设置同时接受 `HARNESS_ENHANCE_` 前缀的别名，越界的值会被夹紧，不可用的值回落到 `0.5`。

| 阈值 | 默认值 | 值调高意味着 |
| --- | --- | --- |
| `HARNESS_COMPACTION_KEEP_THRESHOLD` | `0.5` | 更多工具结果原样保留 |
| `HARNESS_LONG_RUN_READY_THRESHOLD` | `0.5` | 更早把运行推向收尾 |
| `HARNESS_MODE_DECISION_THRESHOLD` | `0.5` | 更频繁注入模式块 |
| `HARNESS_VERIFIER_SUPPORT_THRESHOLD` | `0.5` | 要求更充分的证据才放行回答 |

判定还会选动作：长任务引导可选 `narrow_scope` / `nudge_to_finish` / `force_finish` 决定注入的引导文案，最终回答校验可选 `retry_tool_call` / `soften_claim` / `drop_claim` / `ask_user` 决定修复指引；动作不可用时保留默认文案，评级仍然生效。

## 压缩 Provider

默认 `builtin` provider 是通用、无额外依赖的实现。它不依赖任务 prompt、工具名称或业务特定返回 schema。对于 JSON-like 结果，它会有界遍历 mapping 和 sequence，保留代表性事实，把超长标量替换为形状信息，记录省略项数量，并在写回摘要前做基础脱敏。

压缩后的工具响应会包含类似标记：

```json
{
  "harness_compressed": true,
  "provider": "builtin",
  "summary": "...",
  "original_chars": 8033
}
```

当配置 `HARNESS_COMPRESSION_PROVIDER=headroom` 且安装了可选依赖时，Harness 会通过 Python import 懒加载 Headroom，并在当前进程内调用它。它不会启动服务。如果 Headroom 不可用或返回不合法结果，Harness 会回退到 builtin provider。

## 推荐默认值

| 配置 | 建议值 | 原因 |
| --- | --- | --- |
| `components` | `invocation_context,compactor,response_verification` | 适合工具型 Agent 的均衡默认组合。 |
| `compression_provider` | `builtin` | 稳定、无额外依赖。 |
| `max_tool_result_chars` | `4000` | 只压缩明显过大的结果，小结果保持原样。 |
| `max_context_chars` | `24000` | 给多步任务保留足够上下文，同时限制 prompt 增长。 |
| `verifier_mode` | `observe` | 先观察校验报告，再决定是否阻断回答。 |

## 如何验证效果

建议从这些信号开始：

| 信号 | 好的表现 |
| --- | --- |
| 工具结果压缩 | 大工具响应包含 `harness_compressed: true`，且 `compressed_chars < original_chars`。 |
| Prompt 大小下降 | 后续模型调用携带的原始工具上下文更少。 |
| 回答证据支撑 | 缺少证据的完成类声明能在 verification metadata 中被发现。 |
| 任务质量 | 最终回答仍正确，同时长输出任务的延迟或 token 使用下降。 |

## 常见问题

### 需要一次开启所有组件吗？

不需要。`compactor` 最容易先通过上下文大小和 token 指标验证。需要更强的上下文控制和回答可靠性时，再加入 `invocation_context` 与 `response_verification`。

### 压缩会不会丢掉关键信息？

压缩目标是保留结构化事实、标题、链接、数值、错误信息和短摘要。对于强依赖原文的任务，可以调高压缩阈值，或只在特定场景启用压缩。

### 校验会不会直接阻断回答？

默认模式是 `observe`，只记录 verification metadata，不阻断。只有确认规则适合你的应用后，再使用 `block`。

### Agent 主代码需要大改吗？

通常不需要。创建 `Runner` 时增加 `plugins=build_harness_plugins(...)` 即可；工具、模型配置和 Agent 指令可以保持原有结构。
