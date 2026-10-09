# 在 Studio 会话中保留 OIDC ID Token

- Change ID: `studio-oidc-id-token`
- 创建/修订：2026-09-23
- 状态：已被 [Studio MPA 登录预热](../studio-mpa-login/2026-09-23-studio-mpa-prewarm.zh.md) 取代
- English: [2026-09-23-retain-id-token.md](2026-09-23-retain-id-token.md)
- 组件：[Studio OAuth session](../../../specs/studio-oauth-session/README.zh.md)

## 背景与证据

本文件仅记录历史方案：本地长度检查中，1,519 字节的 access token 与同等长度的 ID token 使 Cookie 约为 4,490 字节。后续方案将 ID token 限制在本次请求内，不再保存到浏览器。

`OAuth2Handler.exchange_code_for_token()` 和 `_refresh_access_token_once()` 收到 token 响应后，目前构造 `OAuth2Session` 时没有传入 `id_token`。因此，Studio 的签名会话 Cookie 无法为后续经单独授权的 MPA 身份交接保留 OIDC ID token。本次将云上 Studio 与 MPA 的客户端 ID 相同作为假设，尚未验证。

## 目标与非目标

在现有 Studio 会话中保留授权码及刷新响应里的可选 `id_token`，包括 Cookie 往返，并继续读取旧 Cookie。不新增 token 共享 API，不向 MPA 发送 token，不修改 MPA 校验或 UserPool 配置。

## 场景与需求

- `FR-1`：授权码响应含 `id_token` 时，生成的 Studio 会话和签名 Cookie 保留它。
- `FR-2`：刷新响应含新 `id_token` 时替换旧值；提供方未返回时保留旧值。消费者使用前仍须验证过期时间。
- `FR-3`：没有 `id_token` 的旧会话仍有效，该字段为 `None`。

## 设计与契约影响

仅为 `OAuth2Session` 增加一个可选字段，并在两个现有构造点传入 token 响应值。现有 Cookie 编解码无需新存储格式即可处理该字段。不增加 HTTP 路由、配置、依赖、事件或前端类型。Cookie 经过签名但未加密，并且已携带 access/refresh token；加入 ID token 可能使长度超过浏览器限制。本改动不意味着可以向浏览器 JavaScript 暴露 ID token，也不证明两个 OAuth 客户端相同。未来交接给 MPA 前，必须验证 token 的有效期、用户、签发方、受众、授权和 Cookie 长度；若超限，应改为服务端存储。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| `FR-1` | `T-1`：先增加失败的登录/Cookie 测试，再保留字段 | `AC-1`：登录 ID token 经 Cookie 往返后仍在 | `tests/auth/test_oauth2_auth.py` |
| `FR-2` | `T-2`：增加刷新测试，再保留或替换字段 | `AC-2`：刷新响应有或没有 ID token 均符合约定 | `tests/auth/test_oauth2_auth.py` |
| `FR-3` | `T-3`：测试旧 Cookie 兼容性 | `AC-3`：旧 Cookie 能解码，且没有 ID token | `tests/auth/test_oauth2_auth.py` |

## 评审与交付记录

用户在 2026-09-23 要求保留 `id_token`，明确排除 MPA 校验改动，并将客户端一致作为假设，视为本范围的批准。评审：最小的模型与构造点改动保留现有会话/Cookie 边界；Cookie 长度与未加密风险已知，属于本次限定范围之外。验证与交付结果：待实施。
