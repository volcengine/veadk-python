# harness-server · 部署 Harness 服务到火山方舟 AgentKit

把 VeADK 的 **Harness 服务**（`veadk.cloud.harness_app`）部署到
[火山引擎 AgentKit](https://www.volcengine.com/)，并用 `veadk harness` 命令行通过
HTTP 调用——无需编写应用代码，也无需本地 Docker。

> English version: [README.md](./README.md)

一个 *harness* 就是一份智能体规格——**模型 + 系统提示词 + 工具 + 技能**，外加创建时
绑定的知识库与长/短期记忆。规格写在分层的 `harness.yaml` 里；`deploy` 会把它展平成
runtime 的环境变量，服务端在启动时据此组装智能体，并通过 `POST /harness/invoke` 对外
服务。

流程为 **`create` → `add` → `deploy` → `invoke`**。完整命令参考见文档
（`docs/content/docs/cli/harness-cli`）。

## 1. 生成脚手架

```bash
veadk harness create harness-server
cd harness-server
```

该命令写入 `harness.yaml`（智能体配置）、`.env.example`（仅含火山引擎部署凭证）、
`Dockerfile` 和 `README.md`。

## 2. 配置智能体

用 `veadk harness add` 将参数写入 `harness.yaml`（也可直接编辑文件）：

```bash
veadk harness add \
  --name research-agent \
  --model-name doubao-seed-1-6-250615 \
  --system-prompt "You are a research assistant." \
  --tools web_search,web_fetch \
  --runtime adk
```

内置工具名来自 `veadk.tools.list_builtin_tools()`（如 `web_search`、`web_fetch`、
`vesearch`、`link_reader`、`run_code`、`coding`、`image_generate`、`image_edit`、
`video_generate`、`text_to_speech`）。在 AgentKit runtime 上 Ark 鉴权由 runtime 的
IAM 角色解析，因此模型只需名字、无需 API Key。用以下命令查看已配置内容：

```bash
veadk harness show
```

## 3. 部署

```bash
cp .env.example .env   # 然后设置 VOLCENGINE_ACCESS_KEY / VOLCENGINE_SECRET_KEY
veadk harness deploy
```

`deploy` 执行 AgentKit 的**云端**构建（无需本地 Docker），并创建以 `harness_name`
命名的 runtime。成功后端点与网关 API Key 会记录到 **`harness.json`**
（`{name: {url, key, runtime_id}}`），下一步无需手动复制 URL / Key。

> **提示（国内构建网络）：** 若 `pip`/`uv` 拉依赖慢，把构建指向国内镜像，例如
> `UV_INDEX_URL=https://mirrors.volces.com/pypi/simple/`。

## 4. 调用

```bash
veadk harness invoke --name research-agent \
  --message "总结一下强化学习的最新进展。"
```

`url`/`key` 默认按 `--name` 从 `harness.json` 读取；也可显式传 `--url` / `--key`
（或设 `HARNESS_URL` / `HARNESS_KEY`）指向某个服务。

### 一次性覆盖

提供 `--model-name` / `--tools` / `--skills` / `--system-prompt` / `--runtime`
中任意一个时，服务端会克隆已部署的智能体并叠加覆盖，**仅对本次调用生效**（工具/技能
为增量叠加；记忆与知识库永不可覆盖）：

```bash
veadk harness invoke --name research-agent \
  --tools get_city_weather \
  --message "北京今天天气怎么样？"
```

## API

服务端只暴露一个接口：

- `POST /harness/invoke` —— 请求体 `{prompt, harness_name, harness?, run_agent_request}`。
  运行已部署的智能体；非空的 `harness` 即本次调用的一次性覆盖（响应 `overwrite: true`）。
  `harness` 字段：`model_name`、`system_prompt`、`tools`、`skills`、`runtime`
  （`tools`/`skills` 为逗号分隔字符串）。`run_agent_request` 字段：`user_id`、`session_id`。

`curl` 等价写法（网关鉴权为 `Authorization: Bearer <API_KEY>`）：

```bash
curl -s -X POST "<ENDPOINT>/harness/invoke" \
  -H "Authorization: Bearer <API_KEY>" -H "Content-Type: application/json" \
  -d '{"prompt":"你好","harness_name":"research-agent","run_agent_request":{"user_id":"u1","session_id":"s1"}}'
```

## 关于扩缩容

短期记忆**按实例存在于内存中**。若 runtime 扩到多实例，某实例上的会话对另一个实例不可见。
要保证多轮会话一致，可把 runtime 固定为单实例（`MinInstance = MaxInstance = 1`），
或在 `harness.yaml` 中配置共享的 `short_term_memory` 后端（如 `mysql` / `postgresql`）。
