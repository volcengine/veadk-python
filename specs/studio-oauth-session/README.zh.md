# Studio OAuth 会话

- Component ID: `studio-oauth-session`
- 状态：拟议，待验证
- 修订：2026-09-23
- English: [README.md](README.md)
- 变更：[Studio MPA 登录预热](../../prd-spec/features/studio-mpa-login/2026-09-23-studio-mpa-prewarm.zh.md)

## 职责与入口

`veadk/auth/middleware/oauth2_auth.py` 负责 Studio 的 OAuth 授权码交换、token 刷新、`OAuth2Session` 和签名浏览器会话 Cookie。Identity 提供方负责签发 token；Studio MPA 预热使用本次请求中的 ID token。

## 拟议契约

- `CON-1`：`OAuth2Session.id_token` 是可选字段，默认 `None`，旧签名 Cookie 仍能解码。
- `CON-2`：授权码交换和刷新只在本次请求的会话中保留返回的 `id_token`；刷新未返回新 ID token 时不复用旧值。
- `CON-3`：新的会话 Cookie 排除 `id_token`；含有该可选字段的旧签名 Cookie 仍可读取。Cookie 有签名但未加密，且为 HttpOnly。中间件写回响应 Cookie 时，下游刷新的会话优先。
- `CON-4`：`validate_id_token()` 在预热调用方比对用户主体前，校验 JWKS 签名、签发方、有效期与所配客户端受众。

## 状态、数据、安全与兼容性

token 端点是事实来源；Cookie 是现有的可跨实例 access/refresh-token 会话存储。并发刷新合并不变。旧 Cookie 仍有效。即使 Runtime 交接随后失败，预热请求也会将轮换后的 refresh token 写回 Cookie。ID token 不进入新 Cookie 或浏览器 JavaScript。

## 验证与限制

`CON-1`–`CON-4` 对应 `tests/auth/test_oauth2_auth.py` 的登录、刷新、旧 Cookie、校验和中间件覆盖测试。真实 UserPool 行为、客户端一致性和生产 Cookie 长度仍需外部验证。
