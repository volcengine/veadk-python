# Studio MPA 预热

- Component ID: `studio-mpa-prewarm`
- 状态/修订：拟议，2026-09-23
- English: [README.md](README.md)
- 变更：[Studio MPA 登录预热](../../prd-spec/features/studio-mpa-login/2026-09-23-studio-mpa-prewarm.zh.md)

## 职责与契约

Studio 负责 `POST /web/mpa/identity-prewarm/{runtime_id}`，并在 MPA 网页聊天的 Runtime run 前调用。接口要求已鉴权的 Studio OAuth 浏览器会话、refresh 凭据、已授权的 MPA Runtime 和 Runtime key-auth。它刷新 Studio 令牌对，按配置的 UserPool JWKS/issuer/client 与 Studio 用户主体校验新 ID token，再将 `idToken` 和 `refreshToken` 从服务端发送到 Runtime 固定路径 `/identity/sessions/put`。响应只有成功或受限错误；令牌不进入浏览器 JavaScript 或日志。Runtime 地址和密钥只来自 Studio 可信的控制面解析器。

## 状态、失败、安全与兼容

刷新后的 Studio 会话替换 HttpOnly 签名 Cookie；即使 refresh token 轮换后 Runtime 交接失败也如此。ID token 只存在于本次请求，新的 Cookie 不编码该字段；带有可选字段的旧 Cookie 仍可读取。缺少 OAuth 会话、refresh token、MPA 标签、key-auth 凭据，或 token 主体不匹配、上游调用失败，均使接口明确报错，但前端仍继续 MPA 网页聊天 run，保留正常登录。用户取消仍会停止 run。前端将预热请求限制为十秒。仅网关会话及飞书聊天不调用此接口。不接受新的浏览器可见凭据或客户端指定 URL。多 Studio 实例和 MPA 独立 refresh token 轮换仍需线上验证。

## 验证

`tests/auth/test_oauth2_auth.py` 覆盖令牌/Cookie 状态；`tests/cli/test_frontend_runtime_proxy.py` 覆盖授权交接与失败。前端测试/构建覆盖调用顺序和非 MPA 行为。生产就绪仍需真实浏览器/UserPool/Runtime 验证。
