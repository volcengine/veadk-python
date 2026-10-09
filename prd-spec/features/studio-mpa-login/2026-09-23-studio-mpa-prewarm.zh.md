# Studio MPA 登录预热

- Change ID: `studio-mpa-login`
- 日期/状态：2026-09-23，用户要求继续开发免二次登录，方案已获同意
- English: [2026-09-23-studio-mpa-prewarm.md](2026-09-23-studio-mpa-prewarm.md)
- 组件：[Studio OAuth 会话](../../../specs/studio-oauth-session/README.zh.md)、[Studio MPA 预热](../../../specs/studio-mpa-prewarm/README.zh.md)

## 背景、目标与范围

Studio 浏览器会话已有 UserPool refresh token，但 MPA 网页聊天目前只有 Runtime key-auth，可能要求同一用户再次登录。MPA 已提供服务端鉴权的 `POST /identity/sessions/put`；Runtime key-auth 代理已注入可信的 Studio 用户 ID。完整 ID token 若写入签名 Cookie，可能超过 4 KB。本改动让 Studio 网页聊天以新鲜的 UserPool ID/refresh token 预热 MPA，不将令牌或 Runtime 密钥交给浏览器 JavaScript。飞书登录及 MPA 现有令牌校验不在范围内。Studio/MPA 使用同一个 UserPool 客户端是运行前提，源码测试不能证明线上配置一致。

## 需求与设计

- `FR-1`：发起 MPA Runtime 网页聊天前，Studio 尝试刷新 OAuth 会话并获得新鲜 ID token。预热失败不阻止 run；MPA 随后可按原流程要求用户登录。
- `FR-2`：Studio 对选定 MPA Runtime 做鉴权和授权，校验新 ID token 的签名、发行方、有效期、受众和用户主体，再用服务端持有的 Runtime key 将 ID/refresh token 发送至固定路径 `/identity/sessions/put`。不接受浏览器指定的上游 URL。
- `FR-3`：轮换后的 refresh 凭据通过现有 HttpOnly 签名 Studio Cookie 返回；ID token 只在请求内使用，不写入 Cookie，以避开浏览器大小限制。旧 Cookie 继续可读。
- `FR-4`：只有 MPA Runtime 网页聊天执行预热。飞书和非 MPA 传输不变。预热失败只作诊断；用户取消仍会停止 run。

新接口 `POST /web/mpa/identity-prewarm/{runtime_id}` 只接收 Runtime ID 和地域。它使用已鉴权的 Studio Cookie、现有控制面 Runtime 授权与凭据解析，并限制上游请求时长。前端在 MPA run 请求前以十秒上限和聊天取消信号调用预热。只记录不含令牌的状态；失败后仍继续正常 run，允许 MPA 手动登录。不向响应返回令牌。即便 Runtime 传递失败，已轮换的会话也必须覆盖中间件原先准备写回的 Cookie。

## 任务、验证与风险

| 需求 | 任务 | 验收 | 测试 |
| --- | --- | --- | --- |
| `FR-1`、`FR-3` | `T-1`：ID token 仅在请求内使用并保留轮换 | `AC-1`：刷新结果可用，但 Cookie 不含 ID token | `tests/auth/test_oauth2_auth.py` |
| `FR-2` | `T-2`：新增授权预热接口 | `AC-2`：可信用户主体、固定目的地、不泄露令牌；非法输入失败 | `tests/cli/test_frontend_runtime_proxy.py` |
| `FR-4` | `T-3`：MPA run 前调用预热 | `AC-3`：交接失败仍启动 MPA run；取消会阻止它；其他传输不变 | 前端测试/构建 |

不新增依赖或 Runtime 生成配置。风险：多实例 Studio 之间的 UserPool refresh token 轮换、MPA 后续轮换同一 refresh token，以及 UserPool 客户端不一致。浏览器预热十秒上限可能先于异常缓慢的提供方刷新结束，此情况需要线上验证。在真实浏览器与云上 Runtime 验证前，不宣称端到端成功。评审结论：复用已有服务端凭据解析和 OAuth 校验；禁止客户端传入 token、URL 或 sender ID。

2026-09-23 验证：`tests/auth/test_oauth2_auth.py` 通过（59）；与 `tests/cli/test_frontend_runtime_proxy.py` 合并运行通过（144）；`npm --prefix frontend test` 通过（1305 个 Node 测试、25 个 Vitest 测试）；预热专项 Vitest 测试通过（4）；前端构建与 pre-commit 通过。新增/修改的 Python 可执行行覆盖 48/48，前端 client 语句覆盖 11/11。使用项目解释器运行 Pyright 仍报告 40 个变更行以外的错误。并行全量回归：5069 通过、11 跳过、2 预期失败、8 失败、2 个收集错误。其中 6 个云端测试失败可由缺少可选 `llama_index` 扩展复现，2 个自托管 Sandbox 收集错误可由缺少可选 `anthropic` 包复现；另 2 个 Skill 版本测试单独重跑未复现失败。真实浏览器/UserPool/Runtime 端到端验证：未运行。
