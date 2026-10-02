# 模型上下文容量覆盖说明

日期：2026-09-30。开发分支 `feat/default-context-compression`，尚未正式发布。

手工核实配置现有 **76 个型号、9 个服务商、21 个显式别名**。另有随 LiteLLM 安装的本地目录后备，因此这不是 SDK 能识别型号的总数。容量统一放在 `veadk/context/model_capacities.json`，运行时无需下载模型或请求网络。

## 覆盖了哪些场景

| 服务商配置名 | 条目数 | 主要模型与用途 |
| --- | ---: | --- |
| volcengine | 18 | 方舟 Seed 2.1/2.0、DeepSeek V4/V4.1、GLM、角色模型；通用 Agent、代码、长材料 |
| byteplus | 7 | Dola Seed 2.1 Turbo、Seed 2.0；国际版 Studio 与 Agent |
| openai | 27 | GPT-6、GPT-5.x、GPT-4.1/4o、o3/o4-mini；对话、推理、代码 |
| anthropic | 4 | 已核实的 Fable 5.1、Opus 5.5、Sonnet 5、Haiku 4.5 |
| gemini | 10 | Gemini 3.8/3.7/3.6/3.5、3 Flash Preview、2.5 系列 |
| deepseek | 2 | 厂商直连 DeepSeek Flash、V4 Pro |
| dashscope | 3 | 百炼 Qwen 3.8 Max/Flash、3.7 Plus |
| zai | 4 | 智谱 GLM 5、5.2、5.3、5.3 Flash |
| moonshot | 1 | Kimi K3 |

覆盖的是对话/推理/代码模型的 token 预算。图片、音频、视频输入仍需相应的媒体预算；绘图、视频生成、embedding 模型不混入此表。

普通开发者继续直接创建 Agent：

```python
from veadk import Agent

# 使用环境中配置的模型，默认开启压缩。
agent = Agent(name="assistant")

# 选择已有容量配置的方舟型号；凭证沿用应用环境配置。
agent = Agent(name="assistant", model_name="doubao-seed-2-1-pro-260915")

# 关闭压缩，保留发送前的容量检查。
agent = Agent(name="assistant", context_compression=False)
```

更换服务商时，也要配置该服务商的正式 API 地址和凭证，不能只改模型名。`openai_transport=true` 表示该条目允许 `openai/模型名` 这种兼容接口写法，不表示 OpenAI 托管了此模型。服务商前缀与模型版本均精确匹配；不去掉任意前缀、不按家族推断，不用别家的部署限制替代私有部署限制。

## 为什么不能只填一个窗口数字

实际可用输入为：

```text
min(用户输入上限, 模型最大输入, 总窗口 - 输出预留 - 安全余量)
```

- GPT-6 Astra 等型号的总窗口是 1,050,000，但官方最大输入为 922,000；本次修正了三条把二者混用的配置，并新增预算层回归。
- Qwen 同一型号在思考开/关时输入上限不同，本表取更小的 983,616。BytePlus 部分型号在不同能力表里分别标 224K/256K，也取较小值。
- Kimi K3 官方默认生成上限为 131,072，输入加这个值超过窗口会直接拒绝。因此未显式设置输出时，也预留这部分空间。其 API 最大输出参数为 1,048,576，本表按已公布的 1M 共享窗口保守限制到 1,000,000。
- 只公布总窗口的模型，输入配置以总窗口为上界，预算计算仍减输出；Gemini 只公布输入/输出上限时，以输入上限作为保守共享窗口，不能把两者相加。
- K/M 简写按十进制保守折算；官方给出的精确整数保留原值。输出预留是输入规划值，不能保证任意长度的思维链都能完成。

## 当前边界和维护方式

这里不能承诺“所有型号、所有地区、所有私有部署全覆盖”。本轮没有拿到新 Claude 页面正文，保留原先四条及其 9 月 28 日核实日期，没有补猜测数字；Kimi K2.6/2.7、其他聚合平台同名部署尚未补齐完整容量证据。BytePlus 表仅新增有独立 ID 的 Seed 型号，共用名称的跨平台条目需要单独核实接口与部署限制。

型号存在容量记录，不代表账号已开通或服务仍上架。Gemini 2.5 当前仅对历史使用者开放；旧 Seed 1.6/1.8、DeepSeek V3.2 等已进入官方下线名单。本轮将**新生成项目**的旧 Seed 1.6 默认值改为官方建议迁移目标 `doubao-seed-2-0-lite-260428`；前端占位值与实际生成的 `.env.example` 已同步；Studio 助手默认模型及已有项目配置保持原值。`deepseek-v4-pro-260425` 官方标为即将下线，建议新项目选已核实的新版本。

查不到配置且 LiteLLM 本地目录也没有精确条目时，发送前报 `model_capacity_required`。私有接入点需由开发者提供核实后的 `context_window`、`input_limit` 和 `output_reserve`，不默认猜 32K/128K。型号、来源、核实日期与传输别名随 SDK 版本维护；更新配置后须构建新包并重启进程。此表是容量防护，不是模型服务可用性探测。

方舟本轮通过其公开文档页面使用的 `getDocDetail` 接口核实资料。这是文档正文接口，**不是实时查询某个模型/接入点容量的正式模型 API**；SDK 请求链路不调用它。

## 验证

修改前，5 条离线回归稳定失败：三个 OpenAI 最大输入配置和两种云服务商的生成默认覆盖。新增测试位于 `tests/context/test_model_capacity_coverage.py`，已由 `tests/run_context_compression_gate.py` 的目录入口纳入强制门禁。实际生成环境及前端默认型号也有离线回归，分别纳入 Python 强制入口和前端 `contextCompression` 门禁。新增依赖 0；本轮真实模型调用 0。

本轮在 5663 测试账号的 Devbox 隔离目录验证：Python 3.10 / ADK 1.34.0 与 Python 3.12 / ADK 2.2.0 的完整门禁各 **1,312 项通过、5 项跳过**；容量定向回归各 118 项通过。前端全量 **1,246 项通过**，生产构建、Ruff、Pyright、pre-commit 通过。wheel/sdist 打包、安装后读取全部配置及创建开启/关闭压缩 Agent 均通过；安装后验证禁用网络。

远端 CI 以 [PR #1152 当前提交](https://github.com/volcengine/veadk-python/pull/1152) 的检查为准，以上离线结果不替代远端检查或业务质量评测。

## 逐型号配置与官方来源

下面的输入/输出数字是 SDK 配置上限，含上述保守取值；来源文档的独立限制、服务状态与推理参数仍需一起看。

| 服务商 | 型号 | 总窗口 | 输入上限 | 输出上限 | 核实日期 | 官方来源 |
| --- | --- | ---: | ---: | ---: | --- | --- |
| volcengine | `doubao-seed-2-1-pro-260628` | 256,000 | 256,000 | 256,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-1-pro-260915` | 1,024,000 | 1,024,000 | 256,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-1-lite-260915` | 1,024,000 | 1,024,000 | 256,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-1-turbo-260628` | 256,000 | 256,000 | 256,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-lite-260428` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-mini-260428` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-pro-260215` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-lite-260215` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-mini-260215` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-2-0-code-preview-260215` | 256,000 | 224,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `deepseek-v4-1-flash-260910` | 1,024,000 | 1,024,000 | 384,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `deepseek-v4-pro-ga-260813` | 1,024,000 | 1,024,000 | 384,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `deepseek-v4-flash-ga-260731` | 1,024,000 | 1,024,000 | 384,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `glm-5-3-flash-260828` | 1,024,000 | 1,024,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `glm-5-2-260617` | 1,024,000 | 1,024,000 | 128,000 | 2026-09-28 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| openai | `gpt-6-astra` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-6-astra) |
| openai | `gpt-5.6-terra` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.6-terra) |
| openai | `gpt-5.6-luna` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.6-luna) |
| openai | `gpt-4.1-2025-04-14` | 1,047,576 | 1,047,576 | 32,768 | 2026-09-28 | [文档](https://developers.openai.com/api/docs/models/gpt-4.1) |
| openai | `gpt-4o-2024-08-06` | 128,000 | 128,000 | 16,384 | 2026-09-28 | [文档](https://developers.openai.com/api/docs/models/gpt-4o) |
| anthropic | `claude-fable-5-1` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-28 | [文档](https://platform.claude.com/docs/en/about-claude/models/overview) |
| anthropic | `claude-opus-5-5` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-28 | [文档](https://platform.claude.com/docs/en/about-claude/models/overview) |
| anthropic | `claude-sonnet-5` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-28 | [文档](https://platform.claude.com/docs/en/about-claude/models/overview) |
| anthropic | `claude-haiku-4-5-20251001` | 200,000 | 200,000 | 64,000 | 2026-09-28 | [文档](https://platform.claude.com/docs/en/about-claude/models/overview) |
| gemini | `gemini-3.8-flash` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) |
| openai | `gpt-6-sol` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-6-sol) |
| openai | `gpt-6-luna` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| openai | `gpt-5.6-sol` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.6-sol) |
| openai | `gpt-5.5` | 1,050,000 | 1,050,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.5) |
| openai | `gpt-5.5-pro` | 1,050,000 | 1,050,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.5-pro) |
| openai | `gpt-5.4` | 1,050,000 | 1,050,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.4) |
| openai | `gpt-5.4-pro` | 1,050,000 | 1,050,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.4-pro) |
| openai | `gpt-5.4-mini` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.4-mini) |
| openai | `gpt-5.4-nano` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.4-nano) |
| openai | `gpt-5.3-codex` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.3-codex) |
| openai | `gpt-5.2` | 400,000 | 400,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.2) |
| openai | `gpt-5.2-pro` | 400,000 | 400,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.2-pro) |
| openai | `gpt-5.1` | 400,000 | 400,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5.1) |
| openai | `gpt-5` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5) |
| openai | `gpt-5-mini` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5-mini) |
| openai | `gpt-5-nano` | 400,000 | 272,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-5-nano) |
| openai | `gpt-4.1-mini` | 1,047,576 | 1,047,576 | 32,768 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-4.1-mini) |
| openai | `gpt-4.1-nano` | 1,047,576 | 1,047,576 | 32,768 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-4.1-nano) |
| openai | `gpt-4o-mini` | 128,000 | 128,000 | 16,384 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-4o-mini) |
| openai | `o3` | 200,000 | 200,000 | 100,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/o3) |
| openai | `o4-mini` | 200,000 | 200,000 | 100,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/o4-mini) |
| deepseek | `deepseek-flash` | 1,000,000 | 1,000,000 | 384,000 | 2026-09-30 | [文档](https://api-docs.deepseek.com/quick_start/pricing/) |
| deepseek | `deepseek-v4-pro` | 1,000,000 | 1,000,000 | 384,000 | 2026-09-30 | [文档](https://api-docs.deepseek.com/quick_start/pricing/) |
| zai | `glm-5` | 200,000 | 200,000 | 128,000 | 2026-09-30 | [文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5) |
| zai | `glm-5.2` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-30 | [文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.2) |
| zai | `glm-5.3` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-30 | [文档](https://docs.bigmodel.cn/cn/guide/models/text/glm-5.3) |
| zai | `glm-5.3-flash` | 1,000,000 | 1,000,000 | 128,000 | 2026-09-30 | [文档](https://docs.bigmodel.cn/cn/guide/models/vlm/glm-5.3-flash) |
| byteplus | `dola-seed-2-1-turbo-260628` | 256,000 | 256,000 | 256,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-lite-260428` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-mini-260428` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-pro-260328` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-lite-260228` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-mini-260215` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| byteplus | `seed-2-0-code-preview-260328` | 256,000 | 224,000 | 128,000 | 2026-09-30 | [文档](https://docs.byteplus.com/en/docs/ModelArk/model-list) |
| dashscope | `qwen3.8-max` | 1,000,000 | 983,616 | 131,072 | 2026-09-30 | [文档](https://help.aliyun.com/zh/model-studio/qwen3-8-max) |
| dashscope | `qwen3.7-plus` | 1,000,000 | 983,616 | 131,072 | 2026-09-30 | [文档](https://help.aliyun.com/zh/model-studio/qwen3-7-plus) |
| dashscope | `qwen3.8-flash` | 1,000,000 | 983,616 | 131,072 | 2026-09-30 | [文档](https://help.aliyun.com/zh/model-studio/qwen3-8-flash) |
| moonshot | `kimi-k3` | 1,000,000 | 1,000,000 | 1,000,000 | 2026-09-30 | [文档](https://platform.kimi.com/docs/api/chat) |
| openai | `gpt-6.1-sol` | 1,050,000 | 922,000 | 128,000 | 2026-09-30 | [文档](https://developers.openai.com/api/docs/models/gpt-6.1-sol) |
| gemini | `gemini-3.7-flash` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.7-flash) |
| gemini | `gemini-3.6-flash` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.6-flash) |
| gemini | `gemini-3.5-flash` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash) |
| gemini | `gemini-3.5-flash-lite` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) |
| gemini | `gemini-3.1-pro-preview` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview) |
| gemini | `gemini-3-flash-preview` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-3-flash-preview) |
| gemini | `gemini-2.5-flash` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash) |
| gemini | `gemini-2.5-flash-lite` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite) |
| gemini | `gemini-2.5-pro` | 1,048,576 | 1,048,576 | 65,536 | 2026-09-30 | [文档](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-pro) |
| volcengine | `doubao-seed-evolving` | 1,024,000 | 1,024,000 | 256,000 | 2026-09-30 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `deepseek-v4-pro-260425` | 1,024,000 | 1,024,000 | 384,000 | 2026-09-30 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |
| volcengine | `doubao-seed-character-251128` | 128,000 | 96,000 | 32,000 | 2026-09-30 | [文档](https://www.volcengine.com/docs/ark/model-list?lang=zh) |

协议补充依据：[BytePlus Chat API](https://docs.byteplus.com/en/docs/modelark/chat-api)、[Kimi Chat API](https://platform.kimi.com/docs/api/chat)、[Kimi 型号列表](https://platform.kimi.com/docs/models)、[方舟下线模型迁移说明](https://www.volcengine.com/docs/ark/model-deprecation-migration-guide)。

配置格式见[容量配置说明](context-compression-capacity-config.zh.md)，完整使用示例见[开发者指南](context-compression-developer-guide.zh.md)。
