# sso_frontend_on_agentkit · 把带 SSO 的 VeADK 前端部署到 AgentKit

将 VeADK 的 Web 界面（A2UI）连同 **VeIdentity 单点登录** 一起部署到
[火山引擎 AgentKit](https://www.volcengine.com/) 运行时。未登录的浏览器看到登录页，
登录后以登录用户的身份使用界面与后端 Agent。

> English version: [README.md](./README.md)

## 目录结构

```text
sso_frontend_on_agentkit/
├── app.py                      # 部署入口：Web 界面 + Agent API + SSO
├── agents/
│   └── sso_demo_agent/         # 一个最简 Agent
├── requirements.txt            # veadk-python>=0.5.39
├── .env.example
└── .dockerignore
```

## 工作原理

界面、Agent API、VeIdentity OAuth2 中间件、内置 Web 界面都来自 PyPI 上的
`veadk-python`。SSO 全部通过运行时环境变量配置，无需改代码。

`app.py` 针对 AgentKit 网关做了两处适配。网关对每个请求都用运行时 key 鉴权，
key 放在 `Authorization: Bearer <key>` 请求头里，并把该头透传给容器：

- **剥离网关 key**：SSO 中间件会把 `Authorization` 头当成用户的访问令牌去解析 JWT，
  而网关 key 不是 JWT，会报 `Invalid JWT format`。`app.py` 在中间件之前移除这个非 JWT
  的头，使 SSO 回退到会话 cookie；合法的用户 JWT 保持不变。
- **静态资源透传 querystring**：若网关改为从查询串取 key，浏览器加载 `/assets/*`
  也需带上 key。返回的 `index.html` 会把页面的查询串拼到各静态资源 URL 上。

## 1. 前置准备

- 一个 VeIdentity 用户池及其下的一个 `WEB_APPLICATION` 客户端
  （控制台：<https://console.volcengine.com/veidentity>），记下两者的 **UID**。
- 一个火山引擎 Ark 模型 API Key，以及账号的 AK/SK。

```bash
cd examples/sso_frontend_on_agentkit
cp .env.example .env
# 编辑 .env：MODEL_AGENT_API_KEY、VOLCENGINE_ACCESS_KEY/SECRET_KEY、
#           OAUTH2_USER_POOL_ID、OAUTH2_USER_POOL_CLIENT_ID
set -a && source .env && set +a
```

## 2. 生成配置

交互式生成 `agentkit.yaml`（按提示填写区域、镜像仓库、运行时角色等账号相关字段）：

```bash
veadk agentkit config
```

随后在生成的 `agentkit.yaml` 的 `common.runtime_envs` 下补齐以下环境变量
（`OAUTH2_REDIRECT_URI` 先留空，部署拿到地址后再填）：

```yaml
    runtime_envs:
      MODEL_AGENT_PROVIDER: openai
      MODEL_AGENT_NAME: deepseek-v4-flash-260425
      MODEL_AGENT_API_BASE: https://ark.cn-beijing.volces.com/api/v3/
      MODEL_AGENT_API_KEY: <your-ark-api-key>
      OAUTH2_USER_POOL_ID: <your-user-pool-uid>
      OAUTH2_USER_POOL_CLIENT_ID: <your-user-pool-client-uid>
      VOLCENGINE_ACCESS_KEY: <your-ak>
      VOLCENGINE_SECRET_KEY: <your-sk>
      OTEL_SDK_DISABLED: 'true'
      VEADK_DISABLE_EXPIRE_AT: 'true'
```

## 3. 部署

```bash
# 构建镜像并创建运行时，输出 endpoint 与 API key
veadk agentkit launch
```

把上一步输出的 endpoint 写回回调地址，再更新一次运行时：

```bash
# 在 agentkit.yaml 的 runtime_envs 里加一行：
#   OAUTH2_REDIRECT_URI: https://<your-endpoint>/oauth2/callback
veadk agentkit deploy
```

回调地址会自动注册到用户池客户端，云端无需手动添加。

## 4. 访问

AgentKit 网关要求每个请求都带运行时 key。当前运行时 key 只支持放在请求头里
（`CreateRuntime` 的 `ApiKeyLocation` 仅接受 `header`），而浏览器的顶层导航无法自带请求头，
因此用浏览器扩展（如 ModHeader）对该域名**全局**添加请求头：

```text
Authorization: Bearer <your-runtime-key>
```

随后访问 endpoint 即可：界面加载 → 跳转 VeIdentity 登录 → 回调（扩展会带上请求头过网关）
→ 登录态走会话 cookie，界面与 Agent API 正常工作。

## 注意

- **模型**：`MODEL_AGENT_*` 用普通的火山引擎 Ark chat 模型即可。
- **AK/SK**：既供 `veadk agentkit` 构建部署使用，也注入运行时，供应用调用 VeIdentity API
  （解析用户池、注册回调）。
- **重新部署**：改动 `agentkit.yaml` 的 `runtime_envs` 后重跑 `veadk agentkit deploy`
  即可，镜像层会复用，速度很快。用 `veadk agentkit destroy` 拆除。
