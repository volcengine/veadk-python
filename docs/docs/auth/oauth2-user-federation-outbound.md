# 使用 OAuth2 USER_FEDERATION 进行出站认证

OAuth2 USER_FEDERATION 认证用于用户委托场景，应用代表用户访问第三方服务。

## 创建 OAuth2 USER_FEDERATION 凭据

### 基础步骤

1. 登录火山引擎控制台，导航到 **Agent Identity** 服务
2. 在左侧导航树中，选择 **身份认证 > 出站凭据托管 > OAuth Client**
3. 点击 **新建 > 新建 OAuth Client**
4. 在 **OAuth2 流程** 中选择 **用户委托（USER_FEDERATION）**

### 方式一：使用内置 Vendor（推荐）

选择提供商类型：**Lark**、**Coze**、**Google**、**GitHub** ，填写：

- Client ID
- Client Secret
- 回调 URL（选择[回调地址](./4.oauth2-user-federation-outbound.md#回调地址)对应区域的地址）

### 方式二：使用 OIDC 配置

选择提供商类型为 **自定义**，填写：

- 发行者 URL：OIDC 提供商的 Discovery URL（如 `https://accounts.google.com/.well-known/openid-configuration`）
- Client ID
- Client Secret
- 权限范围：至少包含 `openid`
- 回调 URL（选择[回调地址](./4.oauth2-user-federation-outbound.md#回调地址)对应区域的地址）

### 方式三：使用自定义 OAuth2 配置

选择提供商类型为 **自定义**，填写：

- Client ID
- Client Secret
- 权限范围
- Issuer
- 授权端点
- 令牌端点
- 回调 URL（选择[回调地址](./4.oauth2-user-federation-outbound.md#回调地址)对应区域的地址）

## 回调地址

在第三方 OAuth2 提供商中配置回调地址时，使用以下 Agent Identity 回调地址（根据所在区域选择）：

- **北京**：`https://auth.id.cn-beijing.volces.com/api/v1/oauth2callback`
- **上海**：`https://auth.id.cn-shanghai.volces.com/api/v1/oauth2callback`
- **广州**：`https://auth.id.cn-guangzhou.volces.com/api/v1/oauth2callback`

用户授权后，提供商会将授权码（code）和状态（state）重定向到该地址，Agent Identity 负责处理后续的令牌交换。

## 使用方式

### VeIdentityFunctionTool

```python
from veadk.integrations.ve_identity import VeIdentityFunctionTool, oauth2_auth
import aiohttp

async def access_github(access_token: str, repo_owner: str, repo_name: str):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github.v3+json",
    }
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

auth_config = oauth2_auth(
    provider_name="github-oauth2-provider",
    scopes=["repo", "user"],
    auth_flow="USER_FEDERATION",
    callback_url="https://your-app.com/oauth/callback",
)
tool = VeIdentityFunctionTool(
    func=access_github,
    auth_config=auth_config,
)
```

### VeIdentityMcpToolset

```python
from veadk.integrations.ve_identity import VeIdentityMcpToolset, oauth2_auth
from google.adk.agents.mcp import StdioServerParameters

auth_config = oauth2_auth(
    provider_name="github-oauth2-provider",
    scopes=["repo", "user"],
    auth_flow="USER_FEDERATION",
    callback_url="https://your-app.com/oauth/callback",
)
toolset = VeIdentityMcpToolset(
    auth_config=auth_config,
    connection_params=StdioServerParameters(
        command="npx",
        args=["@modelcontextprotocol/server-github"],
    ),
)
```

## 示例

```python
import asyncio
from veadk import Agent
from veadk.integrations.ve_identity import (
    VeIdentityMcpToolset,
    oauth2_auth,
)
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StreamableHTTPConnectionParams,
)

from veadk.integrations.ve_identity.auth_processor import AuthRequestProcessor

# ECS 工具集
ecs_tools = VeIdentityMcpToolset(
    auth_config=oauth2_auth(
        provider_name="volc-ecs-oauth2-provider",
        scopes=["read"],
        auth_flow="USER_FEDERATION",
    ),
    connection_params=StreamableHTTPConnectionParams(
        url="https://ecs.mcp.volcbiz.com/ecs/mcp",
    ),
)

# 云助手 工具集
cloud_assistant_tools = VeIdentityMcpToolset(
    auth_config=oauth2_auth(
        provider_name="volc-ecs-oauth2-provider",
        scopes=["read"],
        auth_flow="USER_FEDERATION",
    ),
    connection_params=StreamableHTTPConnectionParams(
        url="https://ecs.mcp.volcbiz.com/cloud_assistant/mcp",
    ),
)

agent = Agent(
    tools=[ecs_tools, cloud_assistant_tools],
    system_prompt="你是火山引擎ECS助手，可以查询ECS实例信息并执行服务器命令。",
    run_processor=AuthRequestProcessor(),
)

asyncio.run(
    agent.run(
        prompt="先查询我的ECS实例列表，然后选择一个运行中的实例，在上面执行 'uname -a && df -h && free -m' 命令来检查系统信息、磁盘空间和内存使用情况"
    )
)
```

## 常见问题

**Q: 用户首次使用时需要做什么？**

A: 用户需要在第三方服务中授权应用。Agent Identity 会自动处理授权流程。

**Q: 如何处理用户撤销授权？**

A: 如果用户撤销授权，Agent Identity 会返回错误。应用应该提示用户重新授权。

**Q: 令牌过期了怎么办？**

A: Agent Identity 会自动刷新令牌。如果刷新失败，会返回错误，应用应该提示用户重新授权。

**Q: 需要自定义回调地址怎么办？**

A: 如需自定义回调地址，需要将授权码（code）、状态（state）和重定向 URL 传递到对应区域的 Agent Identity 回调地址进行处理。Agent Identity 会负责令牌交换和凭证管理。

## 相关资源

- [Agent Identity 产品介绍](./1.agent-identity-intro.md)
- [API Key 认证](./2.api-key-outbound.md)
- [OAuth2 M2M 认证](./3.oauth2-m2m-outbound.md)
- [Agent Identity API 参考](https://www.volcengine.com/docs/86848/1918752)
