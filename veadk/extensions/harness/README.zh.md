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
