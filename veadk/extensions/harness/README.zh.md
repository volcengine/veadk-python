# VeADK Harness Extension

[English](README.md)

`veadk.extensions.harness` 提供两种互斥的接入模式。旧的进程内模式提供三个可复用能力：

- 为每轮 Agent 调用准备上下文
- 压缩大体积工具结果
- 验证最终回答，降低幻觉

旧 Extension 可以作为普通 Python 模块直接使用，也可以挂载到 VeADK Runner，
不需要单独启动运行时服务。

受管 Sidecar 模式采用另一条边界：全部 Harness 行为只在闭源 Sidecar Runtime 中执行。
`HarnessExtension.from_env()` 仅负责启动 Runtime、应用模型/MCP 绑定和管理生命周期；该模式下
`plugins()` 始终返回空列表，应用进程不会加载或挂载
`veadk.extensions.harness.plugins` 的实现。两种模式不得混用。

## 安装

```bash
pip install "veadk-python[harness]"
```

基础 Harness Extension 已随 VeADK 内置。`harness` extra 会安装可选的进程内
Headroom 压缩 provider。

在当前仓库内本地开发：

```bash
pip install .
```

本地开发并启用 Headroom：

```bash
pip install ".[harness]"
```

## 快速开始

```python
from veadk.extensions.harness.plugins import build_harness_plugins
from veadk import Agent, Runner

agent = Agent(name="research_agent")
runner = Runner(
    agent=agent,
    app_name="research",
    plugins=build_harness_plugins(
        components=["invocation_context", "compactor", "response_verification"],
        profile="research",
    ),
)
```

## 插件能力

| 插件 | 主要 Hook | 作用 |
| --- | --- | --- |
| `HarnessInvocationContextPlugin` | `on_user_message_callback`, `before_model_callback` | 准备任务锚点、近期上下文和工具使用约束。 |
| `HarnessCompressPlugin` | `before_model_callback`, `after_tool_callback` | 压缩过大的工具输出，同时保留关键事实。 |
| `HarnessResponseVerificationPlugin` | `after_tool_callback`, `after_model_callback`, `on_event_callback` | 记录工具执行 receipt，并标记缺少证据的最终回答。 |

## 运行时配置

```text
HARNESS_ENHANCE_ENABLED=true
HARNESS_ENHANCE_COMPONENTS=invocation_context,compactor,response_verification
HARNESS_PROFILE=research
HARNESS_COMPRESSION_PROVIDER=builtin
HARNESS_COMPACTION_STRATEGY=builtin
HARNESS_LONG_RUN_STRATEGY=counter
HARNESS_MODE_STRATEGY=keywords
```

```python
from veadk.extensions.harness.env import build_harness_plugins_from_env

plugins = build_harness_plugins_from_env()
```

在 VeADK HarnessApp 部署中，也可以写入 `harness.yaml`：

```yaml
harness_enhance:
  enabled: true
  components: [invocation_context, compactor, response_verification]
  profile: general
  compression_provider: builtin
```

## 判定模型策略

三个判定点可以选择改用已配置的判定模型，替代内置规则。所有策略默认关闭；没有配置判定模型时会各自保留原规则并打印告警。

| 策略 | 开关 | 被替代的规则 | 判定不可用时 |
| --- | --- | --- | --- |
| 压缩候选 | `HARNESS_COMPACTION_STRATEGY=decision` | 按角色和长度挑选压缩候选 | 内置规则 |
| 长任务引导 | `HARNESS_LONG_RUN_STRATEGY=decision` | 仅按模型调用次数计数 | 计数规则，并在 `unconditional_after_model_calls` 后强制生效 |
| 上下文模式块 | `HARNESS_MODE_STRATEGY=decision` | 精度/产物关键词匹配 | 关键词匹配 |
| 最终回答校验 | `HARNESS_VERIFIER_STRATEGY=decision` | 完成类关键词加「有无成功回执」 | 内置规则 |

判定返回的是「是」在 `[0, 1]` 上的概率，每个点各自持有阈值：同一个概率落在不同点上
代价不同，所以调高一个点的门槛不会抬高其它点。两个点返回的是评级而不是是否，阈值
比较的就是该评级。每个设置都接受 `HARNESS_ENHANCE_` 前缀的别名，越界的值会被夹紧，
不可用的值回落到 `0.5`。

| 阈值 | 开关 | 值调高意味着 |
| --- | --- | --- |
| 压缩候选 | `HARNESS_COMPACTION_KEEP_THRESHOLD=0.5` | 更多工具结果原样保留 |
| 长任务引导 | `HARNESS_LONG_RUN_READY_THRESHOLD=0.5` | 更早把运行推向收尾 |
| 上下文模式块 | `HARNESS_MODE_DECISION_THRESHOLD=0.5` | 更频繁注入模式块 |
| 最终回答校验 | `HARNESS_VERIFIER_SUPPORT_THRESHOLD=0.5` | 要求更充分的证据才放行回答 |

两个策略除了过阈值还会选动作，动作决定注入内容：

| 策略 | 可选动作 | 影响 |
| --- | --- | --- |
| 长任务引导 | `narrow_scope` / `nudge_to_finish` / `force_finish` | 用贴合当前轨迹的引导替换固定文案 |
| 最终回答校验 | `retry_tool_call` / `soften_claim` / `drop_claim` / `ask_user` | 组装交回主模型的修复指引 |

判定返回未知动作时保留默认文案，同一次判定里的评级仍然生效。

策略依赖已配置的判定模型，环境变量见 [decisions](../decisions/README.zh.md)。判定失败会回落到上表规则，不会让运行失败。

用代码装配插件时，同样的选择通过参数传入，而不是环境变量：
`compaction_config=ToolResultCompactorConfig(strategy="decision")`、
`context_config=HarnessInvocationContextConfig(mode_strategy="decision")`、
`HarnessExtension(long_run_strategy="decision", long_run_ready_threshold=0.5)`、
`verifier_config=FinalResponseVerifierConfig(strategy="decision", support_threshold=0.5)`。
一旦传入 `env` 映射，就以环境变量为唯一来源（`HarnessExtension.from_env()` 即这种形态）。

## 直接使用模块

```python
from veadk.extensions.harness import HarnessInvocationContextBuilder, HarnessInvocationRef

context = HarnessInvocationRef(session_id="session-1", invocation_id="run-1")
builder = HarnessInvocationContextBuilder()
bundle = builder.prepare_context(context, user_input="Summarize these tool results.")
```

## 更多文档

请阅读 [docs/extensions/harness/README.zh.md](../../../docs/extensions/harness/README.zh.md)。
里面包含精简的新手教程、核心概念、配置方式和接入建议。
