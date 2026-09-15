# MPA Runtime 任务查看器

[English](README.md)

2026-09-15。Studio 面板负责只读展示并分页获取选中 Runtime 的 /api/v1/esa-cron-tasks 响应。MPA 负责存储、用户鉴权和调度，现有 Studio 代理负责 Runtime 访问和网关鉴权。选择包含 Runtime ID 和地域，未选择时不请求。请求使用 limit=20、offset 和 includeDisabled=true。可选 X-Jwt-Token 仅存在组件内存，切换目标或卸载时清除。列表仅展示令牌有权访问的任务。错误不能变成空成功，迟到响应不能跨目标显示。不增加修改或调度接口。参见[变更与验证](../../prd-spec/features/studio-mpa-cron-tasks/README.zh.md)。

## 自动凭证修订 — 2026-09-15
当前用户授权将手动 JWT 输入替换为服务端调用 TOP GetMpaInstanceToken（2026-03-01）。从已授权的所选 Runtime 读取 MPA_AGENT_ID、MPA_SPACE_ID/CLAW_SPACE_ID、MPA_IS_DEBUG_RUNTIME 和 ARKCLAW_TOP_SERVICE。使用可信企业身份 user_pool_user_uid；本地管理员在服务端配置 VEADK_STUDIO_MPA_USER_UID。禁止使用浏览器传入的身份申请凭证。JWT 由 TOP 签发。转发 Authorization 和 X-Jwt-Token 前校验其 HTTPS 地址与所选 Runtime 相同。每次列表请求获取新凭证，不缓存、持久化或向浏览器返回凭证。保持只读范围，参照 mono SharedAgent/Cron 增加任务提示词详情、执行次数与成功率。配置缺失和 TOP 失败需明确展示。测试覆盖身份、地址不匹配、上游错误、凭证隔离和取消，增量覆盖率超过 95%。本修订替代旧手动 JWT 契约；此前验证结果仅针对旧版本。

## 直接访问 Runtime 修订（2026-09-15）
用户已关闭 Runtime 的 JWT 校验，并授权移除 TOP 凭证申请。替代此前的凭证契约：保留所选 Runtime 的权限检查及网关鉴权，使用当前 Studio 身份的 owner_id 作为 x-user-id；从 Runtime 配置读取 x-space-id 和 x-mpa-id，缺失时沿用 MPA 的本地默认值；不再申请或转发 X-Jwt-Token。移除企业 UID 配置及凭证相关页面提示。任务仍按用户筛选。本次不修改 Runtime 配置或业务逻辑。验证请求头、不调用 TOP、分页、上游异常与取消；增量覆盖率须超过 95%。

## 最终全量读取契约 — 2026-09-15
用户明确授权在 Runtime 关闭 JWT 时开放全量用户读取，MPA 提交 833c6bc 已实现此行为。Studio 只携带网关鉴权，不发送 JWT、x-user-id、x-space-id 或 x-mpa-id，也不再要求业务用户身份。本节替代之前按用户筛选的直接访问修订。保留 Runtime 权限检查、只读范围、分页与现有错误处理。
