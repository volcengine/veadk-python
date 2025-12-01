# 使用 API Key 进行出站认证

API Key 认证是最简单的出站认证方式，适用于服务间通信和固定凭证场景。

## 创建 API Key 凭据

1. 登录火山引擎控制台，导航到 **Agent Identity** 服务
2. 在左侧导航树中，选择 **身份认证 > 出站凭据托管**
3. 点击 **新建 > 新建 API Key**，填写 API Key 名称
4. 输入第三方服务提供的 API Key
5. 配置 API Key 传递方式（Header 或 Query）并点击 **确定**

## 使用方式

### VeIdentityFunctionTool

```python
from veadk.integrations.ve_identity import VeIdentityFunctionTool, api_key_auth
import aiohttp

async def call_api(api_key: str, endpoint: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(endpoint, headers=headers) as resp:
            return await resp.json()

auth_config = api_key_auth(provider_name="my-api-provider")
tool = VeIdentityFunctionTool(
    func=call_api,
    auth_config=auth_config,
    into="api_key",
)
```

### VeIdentityMcpToolset

```python
from veadk.integrations.ve_identity import VeIdentityMcpToolset, api_key_auth
from google.adk.agents.mcp import StdioServerParameters

auth_config = api_key_auth(provider_name="my-api-provider")
toolset = VeIdentityMcpToolset(
    auth_config=auth_config,
    connection_params=StdioServerParameters(
        command="python",
        args=["-m", "my_api_mcp_server"],
    ),
)
```

## 示例

```python
import asyncio
from veadk import Agent, Runner
from veadk.integrations.ve_identity import VeIdentityFunctionTool, api_key_auth
import aiohttp

async def query_api(api_key: str, user_id: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"https://api.example.com/users/{user_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            return await resp.json()

tool = VeIdentityFunctionTool(
    func=query_api,
    auth_config=api_key_auth(provider_name="user-api"),
    into="api_key",
)

agent = Agent(tools=[tool])
runner = Runner(agent=agent)
asyncio.run(runner.run(messages="查询用户 123"))
```

## 常见问题

**Q: 如何更新 API Key？**

A: 在 Agent Identity 控制台中编辑凭证即可。

**Q: 如何处理 API 调用失败？**

A: 实现错误处理和重试逻辑。

## 相关资源

- [Agent Identity 产品介绍](./1.agent-identity-intro.md)
- [OAuth2 M2M 认证](./3.oauth2-m2m-outbound.md)
- [OAuth2 USER_FEDERATION 认证](./4.oauth2-user-federation-outbound.md)
- [Agent Identity API 参考](https://www.volcengine.com/docs/86848/1918752)
