# Agent Identity 产品介绍

Agent Identity 是火山引擎提供的一站式身份及权限管理平台，负责用户身份验证、权限控制，确保 Agent 出、入操作的安全性与合规性。

## 核心功能

- **用户身份管理**：支持用户池管理、企业 IdP（SAML/OIDC）及第三方身份联合
- **工作负载身份管理**：为 Agent/工具分配唯一数字身份，维护属性标签
- **第三方凭据托管**：加密托管 API Key 和 OAuth 令牌，杜绝明文凭据泄露
- **权限管控**：基于属性和上下文的动态授权，实现细粒度权限控制

## 开通流程

### 1. 访问 Agent Identity 控制台

访问 **[Agent Identity](https://console.volcengine.com/identity)** 服务开通页，勾选 **同意服务条款**, 点击 **开通并授权**。

### 2. 创建出站凭据提供商

根据使用场景创建相应的出站凭据提供商：

| 认证方式 | 提供商类型 | 使用场景 |
|---------|----------|--------|
| API Key | API Key | 服务间通信 |
| OAuth2 M2M | OAuth Client | 后端服务间认证 |
| OAuth2 USER_FEDERATION | OAuth Client | 用户委托认证 |

### 3. 配置凭证信息

根据认证方式配置相应的凭证（如 API Key、Client ID、Client Secret、回调 URL 等）。

### 4. 快速使用

```python
from veadk.integrations.ve_identity import (
    VeIdentityFunctionTool,
    api_key_auth,
)

auth_config = api_key_auth(provider_name="my-provider")
tool = VeIdentityFunctionTool(
    func=my_function,
    auth_config=auth_config,
    into="api_key",
)
```

## 常见问题

**Q: 如何选择认证方式？**

A:

- **API Key**：简单、固定凭证，适合简单场景
- **OAuth2 M2M**：安全、支持令牌过期和刷新，适合生产环境
- **OAuth2 USER_FEDERATION**：用户授权，适合需要用户同意的场景

**Q: 凭证会被暴露吗？**

A: 不会。Agent Identity 会：

- 加密存储凭证
- 支持凭证自动轮换
- 不在代码中暴露凭证

**Q: 如何处理凭证过期？**

A: Agent Identity 会自动处理：

- 令牌缓存和刷新
- 凭证自动轮换
- 过期前自动更新

## 后续步骤

- [使用 API Key 进行出站认证](./api-key-outbound.md)
- [使用 OAuth2 M2M 进行出站认证](./oauth2-m2m-outbound.md)
- [使用 OAuth2 USER_FEDERATION 进行出站认证](./oauth2-user-federation-outbound.md)

## 相关资源

### Agent Identity 官方文档

- [Agent Identity API 参考](https://www.volcengine.com/docs/86848/1918752)

### 外部资源

- [OAuth2 规范](https://tools.ietf.org/html/rfc6749)
- [OpenID Connect](https://openid.net/connect/)

## 获取帮助

如有问题，请：

1. 查看相应文档的常见问题部分
2. 查看 [Agent Identity 官方文档](https://www.volcengine.com/docs/86848/2080920?lang=zh)
3. 联系火山引擎技术支持
