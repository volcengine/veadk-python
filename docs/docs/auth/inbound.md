---
title: 入站认证
description: 通过入站认证访问 Agent
navigation:
  icon: i-lucide-lock
---

VeADK 支持 API Key 和 OAuth2 方式的入站认证。

## API Key 认证

API Key 认证是通过唯一字符串密钥验证请求方身份、授权访问 API 资源的常见认证方式。VeADK 约定将 API Key 通过 URL 的 `token` 参数传递。

!!! tip 
    API Key 仅适用于 A2A/MCP Server 部署模式，不建议在 VeADK Web 部署模式中使用，更推荐采用 OAuth2 认证。

### 使用方式

您可以通过脚手架创建 Agent 时指定 API Key 认证方式，或者部署已有项目时添加 `--auth-method=api-key` 参数启用该认证。

当用户访问应用时，API 网关将验证用户 `token` URL 参数中携带的 API Key。

## OAuth2 单点登录

OAuth2 是一种开放标准的授权框架，通过令牌而非直接暴露账号密码，安全实现第三方应用对资源的有限访问。

OAuth2 单点登录是基于 OAuth2 授权框架实现的身份认证方案，用户一次登录后可免重复验证访问多个关联应用。VeADK 提供两种 OAuth2 单点登录的接入方式：

| 方式 | 适用场景 | 说明 |
|------|----------|------|
| API 网关模式 | VeFaaS 云端部署 | 通过脚手架部署，由 API 网关处理认证 |
| Starlette/FastAPI 中间件 | 本地开发 / 自托管部署 | 在应用内集成 OAuth2 中间件 |

### 方式一：API 网关模式（VeFaaS 部署）

适用于通过 VeFaaS 部署的 VeADK Web 应用，由 API 网关处理 OAuth2 认证流程。

!!! tip 
    使用 API 网关模式需要版本为 4.0.0 及以上的 API 网关。

#### 使用方式

您可以通过脚手架创建 Agent 时指定 OAuth2 认证方式，或者部署已有项目时添加 `--auth-method=oauth2` 参数启用该认证，VeADK 将自动为您创建 Identity 用户池和客户端。如果您需要使用已有的用户池或客户端，您可以在部署时添加 `--user-pool-name` 和 `--client-name` 参数指定用户池和客户端。

在部署 VeADK Web 应用后，您可以在 Identity 中创建用户：

1. 登录火山引擎控制台，导航到 Agent Identity 服务
2. 在左侧导航树中，选择 身份认证 > 用户池管理，选择用户池
3. 在用户池的用户标签页中，点击 新建用户，填写用户信息并点击 确定

当用户访问 VeADK Web 应用时，API 网关将引导用户至登录页完成登录。您可以在 `Authorization` 请求头中获得用户的 JWT 令牌。

### 方式二：Starlette/FastAPI 中间件（本地/自托管）

适用于本地开发或自托管部署场景，通过 VeADK 提供的中间件在应用内处理 OAuth2 认证。支持所有基于 Starlette 的框架，包括 FastAPI。

#### 快速开始（FastAPI）

推荐使用 `OAuth2Config.from_veidentity()` 方法，自动配置 VeIdentity User Pool：

```python
from fastapi import FastAPI
from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

app = FastAPI()

setup_oauth2(
    app,
    OAuth2Config.from_veidentity(
        user_pool_name="my-app",
        client_name="my-app-web",
        redirect_uri="https://myapp.com/oauth2/callback",
    ),
)
```

#### 快速开始（Starlette）

```python
from starlette.applications import Starlette
from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

app = Starlette()

setup_oauth2(
    app,
    OAuth2Config.from_veidentity(
        user_pool_name="my-app",
        client_name="my-app-web",
        redirect_uri="https://myapp.com/oauth2/callback",
    ),
)
```

该方法会自动：

- 创建用户池（如不存在）
- 创建用户池客户端（如不存在）
- 注册回调 URL
- 配置 OAuth2 端点

#### 使用已有资源

如果您已有用户池和客户端，可以禁用自动创建：

```python
setup_oauth2(
    app,
    OAuth2Config.from_veidentity(
        user_pool_name="existing-pool",
        client_name="existing-client",
        redirect_uri="https://myapp.com/oauth2/callback",
        auto_create=False,            # 资源不存在时报错
        auto_register_callback=False, # 不修改回调 URL
    ),
)
```

#### 本地开发配置

本地开发时需要禁用 HTTPS cookie：

```python
setup_oauth2(
    app,
    OAuth2Config.from_veidentity(
        user_pool_name="my-app",
        client_name="my-app-web",
        redirect_uri="http://localhost:8000/oauth2/callback",
        cookie_secure=False,  # 本地 HTTP 开发
    ),
)
```

#### 自定义 OAuth2 Provider

如需接入非 VeIdentity 的 OAuth2 提供商，可直接配置 `OAuth2Config`：

```python
setup_oauth2(
    app,
    OAuth2Config(
        authorize_url="https://provider.com/oauth2/authorize",
        token_url="https://provider.com/oauth2/token",
        userinfo_url="https://provider.com/oauth2/userinfo",
        client_id="your-client-id",
        client_secret="your-client-secret",
        redirect_uri="https://myapp.com/oauth2/callback",
    ),
)
```

#### 路由说明

中间件会自动注册以下路由：

| 路由 | 说明 |
|------|------|
| `/oauth2/login` | 发起 OAuth2 登录流程 |
| `/oauth2/callback` | OAuth2 回调处理 |
| `/oauth2/logout` | 登出并清除会话 |
| `/oauth2/userinfo` | 获取当前用户信息 |

#### 免认证路径

可以配置跳过认证的路径：

```python
setup_oauth2(
    app,
    config,
    exempt_paths=["/health", "/metrics"],      # 精确匹配
    exempt_prefixes=["/public/", "/static/"],  # 前缀匹配
)
```

#### API 请求处理

中间件会根据请求类型自动选择响应方式：

- **浏览器请求**：重定向到登录页面
- **API 请求**：返回 `401 Unauthorized` JSON 响应

API 请求通过以下方式识别：

- `Accept: application/json` 请求头
- 路径前缀匹配（默认 `/api/`）
- `X-Requested-With: XMLHttpRequest` 请求头

可通过 `api_path_prefixes` 参数自定义：

```python
OAuth2Config.from_veidentity(
    # ...
    api_path_prefixes=["/api/", "/graphql"],
)
```

#### 配置参考

##### OAuth2Config.from_veidentity() 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `user_pool_name` | (必填) | VeIdentity 用户池名称 |
| `client_name` | (必填) | 用户池客户端名称 |
| `redirect_uri` | (必填) | OAuth2 回调 URL |
| `auto_create` | `True` | 资源不存在时自动创建 |
| `auto_register_callback` | `True` | 自动注册回调 URL |
| `client_type` | `WEB_APPLICATION` | 客户端类型 |
| `scope` | `"openid profile email"` | OAuth2 作用域 |
| `**extra_config` | - | 其他 OAuth2Config 参数 |

##### OAuth2Config 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `session_timeout_seconds` | `3600` | 会话超时时间（秒） |
| `cookie_secure` | `True` | 是否启用安全 cookie |
| `auto_refresh_token` | `True` | 自动刷新令牌 |
| `token_refresh_threshold_seconds` | `300` | 令牌刷新阈值（秒） |
| `api_path_prefixes` | `["/api/"]` | API 路径前缀 |

#### 分布式部署

默认的 `InMemoryStateStore` 仅适用于单进程部署。分布式场景需要使用 Redis 等外部存储：

```python
class RedisStateStore:
    def __init__(self, redis_client, ttl: int = 300):
        self._redis = redis_client
        self._ttl = ttl

    def create_state(self, redirect_after_auth: str = "/", code_verifier=None) -> str:
        import secrets, json
        state = secrets.token_urlsafe(32)
        self._redis.setex(
            f"oauth2:{state}",
            self._ttl,
            json.dumps({
                "redirect_after_auth": redirect_after_auth,
                "code_verifier": code_verifier,
            }),
        )
        return state

    def validate_and_consume_state(self, state: str):
        import json
        key = f"oauth2:{state}"
        data = self._redis.get(key)
        if not data:
            return None
        self._redis.delete(key)
        return json.loads(data)

# 使用
setup_oauth2(app, config, state_store=RedisStateStore(redis_client))
```

## OAuth2 JWT 认证

OAuth2 JWT 认证是将 OAuth2 授权框架与 JWT 结合，用 JWT 格式承载授权令牌的认证方式。A2A/MCP Server 支持 OAuth2 JWT 的认证方式。

### 使用方式

您可以通过脚手架创建 Agent 时指定 OAuth2 认证方式，或者部署已有项目时添加 `--auth-method=oauth2` 参数启用该认证，VeADK 将自动为您创建 Identity 用户池。如果您需要使用已有的用户池，您可以在部署时添加 `--user-pool-name` 参数指定用户池。

在部署 A2A/MCP Server 应用后，您可以在 Identity 中管理客户端：

1. 登录火山引擎控制台，导航到 Agent Identity 服务
2. 在左侧导航树中，选择 身份认证 > 用户池管理，选择用户池
3. 在客户端的用户标签中，点击 新建客户端，填写 客户端名称，选择 客户端类型 并点击确定

您可以创建 M2M 类型的客户端用于验证。您可以使用以下 curl 命令生成 JWT 令牌：

```bash
REGION="cn-beijing"
USER_POOL_ID="FILL_IN_YOUR_USER_POOL_ID"
CLIENT_ID="FILL_IN_YOUR_CLIENT_ID"
CLIENT_SECRET="FILL_IN_YOUR_SECRET"

curl --location "https://userpool-${USER_POOL_ID}.userpool.auth.id.${REGION}.volces.com/oauth/token" \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --header "Authorization: Basic $(echo -n "${CLIENT_ID}:${CLIENT_SECRET}" | base64)" \
  --data-urlencode "grant_type=client_credentials"
```

当用户访问 A2A/MCP Server 应用时，API 网关将验证用户携带的 JWT 令牌。您可以在 `Authorization` 请求头中获得用户的 JWT 令牌。
