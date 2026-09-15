# MPA Runtime 任务查看器

[English](README.md)

2026-09-15。Studio 面板负责只读展示并分页获取选中 Runtime 的 /api/v1/esa-cron-tasks 响应。MPA 负责存储、用户鉴权和调度，现有 Studio 代理负责 Runtime 访问和网关鉴权。选择包含 Runtime ID 和地域，未选择时不请求。请求使用 limit=20、offset 和 includeDisabled=true。可选 X-Jwt-Token 仅存在组件内存，切换目标或卸载时清除。列表仅展示令牌有权访问的任务。错误不能变成空成功，迟到响应不能跨目标显示。不增加修改或调度接口。参见[变更与验证](../../prd-spec/features/studio-mpa-cron-tasks/README.zh.md)。
