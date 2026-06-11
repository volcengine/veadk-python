# harness-server · 部署 Harness 服务到火山方舟 AgentKit

把 VeADK 的 **Harness 服务**（`veadk.cloud.harness_app`）部署到
[火山引擎 AgentKit](https://www.volcengine.com/)，并通过 HTTP 调用。

> English version: [README.md](./README.md)

一个 *harness* 就是一份带名字的 agent 配置 —— **模型 + system prompt + 工具**。
服务端支持运行时注册 harness（`/harness/add`）和调用（`/harness/invoke`），
调用时还可以临时传一个一次性 harness 覆盖已注册的那份。

服务代码已经在 `veadk` 包里，**不需要你写任何应用代码**，运行时直接跑模块即可：

```bash
python -m veadk.cloud.harness_app   # 在 0.0.0.0:8000 提供 API
```

## 本目录内容

```text
14_harness_server_on_agentkit/
├── README.md          # 英文说明
├── README.zh.md       # 本文件
├── .env.example       # 模型 + 火山凭证（占位符）
└── requirements.txt   # veadk-python（装进镜像）
```

> `veadk agentkit config` / `launch` 会在此目录生成 `agentkit.yaml`、`Dockerfile`
> 和 `.agentkit/`，这些是构建产物，已被 gitignore，不属于示例本身。

## API

- `POST /harness/add` —— 请求体 `{harness_name, harness}`，注册一个 harness；
  同名已存在返回 `code: 400`。
- `POST /harness/invoke` —— 请求体
  `{prompt, harness_name, harness?, run_agent_request}`，运行一个**已注册**的
  harness。请求里带非空 `harness` 则对本次调用临时覆盖（`overwrite: true`）。

`harness` 字段：`model_name`、`system_prompt`、`tools`、`skills`、`runtime`
（运行时，默认 `"adk"`，可传 `"codex"`）。`tools` 既接受数组
（`["web_search", "web_fetch"]`）也接受逗号分隔字符串（`"web_search,web_fetch"`）。
`run_agent_request` 字段：`user_id`、`session_id`。

内置工具名见 `veadk.tools.list_builtin_tools()`（如 `web_search`、`web_fetch`、
`vesearch`、`link_reader`、`run_code`、`coding`、`image_generate`、`image_edit`、
`video_generate`、`text_to_speech`）。

## 1. 配置

```bash
cd examples/14_harness_server_on_agentkit
cp .env.example .env
# 编辑 .env：填 MODEL_AGENT_API_KEY + VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
```

云函数没有 `.env`，所以模型凭证需要在 config 时作为运行时环境变量打进 runtime：

```bash
veadk agentkit config \
  --agent_name harness-server \
  --entry_point veadk.cloud.harness_app.py \
  --language Python --language_version 3.12 \
  --launch_type cloud --region cn-beijing \
  --dependencies_file requirements.txt \
  -e MODEL_AGENT_PROVIDER="$MODEL_AGENT_PROVIDER" \
  -e MODEL_AGENT_NAME="$MODEL_AGENT_NAME" \
  -e MODEL_AGENT_API_BASE="$MODEL_AGENT_API_BASE" \
  -e MODEL_AGENT_API_KEY="$MODEL_AGENT_API_KEY"
```

`entry_point` 是一个「点号模块路径」（结尾的 `.py` 会被去掉），所以 AgentKit
最终用 `python -m veadk.cloud.harness_app` 启动容器 —— 模块从镜像里安装好的
`veadk` 包解析，因此本目录**不需要任何 Python 文件**。

> **国内构建网络提示**：如果 `pip`/`uv` 拉依赖很慢，把构建指向国内镜像，例如设置
> 运行时/构建环境变量 `UV_INDEX_URL=https://mirrors.volces.com/pypi/simple/`。

## 2. 本地运行（可选）

```bash
python -m veadk.cloud.harness_app   # http://127.0.0.1:8000
```

## 3. 部署

```bash
veadk agentkit launch   # 构建镜像并部署，结束后打印访问 endpoint
```

## 4. 测试

把 `<ENDPOINT>` 换成 `launch` 打印的 URL，`<API_KEY>` 换成 runtime 的网关 key
（`veadk agentkit runtime get -r <runtime-id>` →
`AuthorizerConfiguration.KeyAuth.ApiKey`）。

用 VeADK CLI：

```bash
veadk agentkit harness add \
  --name research-agent \
  --model-name doubao-seed-1-6-250615 \
  --system-prompt "你是一个研究助手。" \
  --tools web_search,web_fetch \
  --url "<ENDPOINT>" --key "<API_KEY>"

veadk agentkit harness invoke \
  --harness research-agent \
  --url "<ENDPOINT>" --key "<API_KEY>" \
  "总结一下强化学习的最新进展。"
```

`--url` / `--key` 也可用环境变量 `HARNESS_URL` / `HARNESS_KEY` 代替。

或用 `curl`（网关鉴权为 `Authorization: Bearer <API_KEY>`）：

```bash
curl -s -X POST "<ENDPOINT>/harness/add" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"harness_name":"bot","harness":{"system_prompt":"回答简洁。"}}'

curl -s -X POST "<ENDPOINT>/harness/invoke" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"prompt":"你好","harness_name":"bot","run_agent_request":{"user_id":"u1","session_id":"s1"}}'
```

## 关于扩缩容

harness 注册表是**按实例存在内存里**的。如果 runtime 扩到多个实例，在实例 A 上
`add` 的 harness，对被路由到实例 B 的 `invoke` 是不可见的。对于「先注册再调用」的
用法，请把 runtime 固定为单实例（`MinInstance = MaxInstance = 1`），或者把注册表
外置（数据库 / 缓存）以在多实例间共享状态。
