# veADK Harness Extension

[English](README.md)

`veadk.extensions.harness` 是一个轻量级 Harness Extension，它提供三个可复用能力：

- 为每轮 Agent 调用准备上下文
- 压缩大体积工具结果
- 验证最终回答，降低幻觉

Extension 可以作为普通 Python 模块直接使用，也可以挂载到 veADK Runner。
它不需要单独启动运行时服务。

## 安装

```bash
pip install "veadk-python[harness]"
```

基础 Harness Extension 已随 veADK 内置。`harness` extra 会安装可选的进程内
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
from veadk.extensions.harness.adk import build_harness_plugins
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

在 veADK HarnessApp 部署中，也可以写入 `harness.yaml`：

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

请阅读 [docs/README.zh.md](docs/README.zh.md)。里面包含精简的新手教程、核心概念、
配置方式和评测命令。
