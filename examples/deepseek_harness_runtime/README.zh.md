# deepseek_harness_runtime

这是 `Agent(runtime="dsh")` 的端到端验收示例。

它验证和 Codex 风格 runtime 契约对齐的几项关键能力：

- 流式 partial 输出
- ADK `SkillToolset` 物化到 DSH 原生 skill
- 长期记忆自动保存与直接检索
- SQLite 短期记忆跨轮上下文
- 通过 ADK 形状的 `call_llm` span 接入 OpenTelemetry 观测

## 运行

```bash
uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py
```

默认长期记忆后端是 `viking`，因为它可以直接使用环境变量里的 Volcengine AK/SK。
也可以切换：

```bash
uv run --extra dev --extra dsh python examples/deepseek_harness_runtime/main.py \
  --long-term-backend openviking
```

runtime 的规范名称是 `dsh`。

示例默认使用面向用户的 provider 别名 `volcengine` 和 DSH `sdk-minimal` profile：

```bash
VEADK_DEEPSEEK_HARNESS_PROVIDER=volcengine
VEADK_DEEPSEEK_HARNESS_PROFILE=sdk-minimal
MODEL_AGENT_API_BASE=https://ark.cn-beijing.volces.com/api/v3
MODEL_AGENT_NAME=doubao-seed-2-1-pro-260628
```

不填 provider、`openai`、`volcengine`、`volcengine-ark`、`ark`、`openai-compatible`
和 `third-party` 都是 VeADK 面向第三方 OpenAI-compatible endpoint 接受的入口。当前 DSH
wheel 会通过其已注册的 `deepseek-official` adapter 接收这些配置，同时 VeADK 继续传入显式
model、base URL 和 API key。

## 输出含义

脚本会对每项能力打印一行 `PASS` / `FAIL`，并带上证据：partial chunk 数、skill
输出、SQLite session event 数、切换 session 后的直接记忆检索条数、trace id
和 trace dump 路径。

本目录不会保存任何凭据。模型、DSH、观测 exporter 和记忆后端配置都从环境变量读取。

streaming 和 skill 检查需要可用的模型 endpoint，因为它们会检查 DSH assistant stream chunks 和最终 skill sentinel。
