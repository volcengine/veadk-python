# MPA Runtime 定时任务管理

[English](README.md)

修订日期：2026-09-15。组件 ID：studio-mpa-cron-tasks。

Studio 展示所选 Runtime 内按用户隔离的定时任务。MPA 负责持久化、授权、调度和执行；Studio 服务端负责 Runtime 访问检查、可信用户身份及网关凭证。不获取 TOP/JWT，不回退到全用户读取。MPA 撤销提交 `91fd6a3` 后，本契约替代之前的全用户查看器。

## HTTP 和身份

所有路由要求 `region` 并沿用所选 Runtime 授权。`x-user-id` 来自认证的 Studio 用户，不能使用浏览器传入的身份请求头。上游端点/密钥由已有 Runtime 连接逻辑解析，仅转发网关 Authorization 和 x-user-id。JWT 开启的 Runtime 保留其正常鉴权失败。

| Studio 路由 | 方法 | MPA 路由 |
| --- | --- | --- |
| `/web/mpa-cron/{runtime_id}` | GET / POST | `/api/v1/esa-cron-tasks` |
| `/web/mpa-cron/{runtime_id}/{task_id}` | POST / DELETE | `/api/v1/esa-cron-tasks/{task_id}` |
| `/web/mpa-cron/{runtime_id}/{task_id}/run` | POST | `/api/v1/esa-cron-tasks/{task_id}/run` |
| `/web/mpa-cron/{runtime_id}/{task_id}/runs` | GET | `/api/v1/esa-cron-tasks/{task_id}/runs` |

任务 ID 只允许字母、数字、下划线和连字符。写入字段只允许现有 MPA schema 字段名，请求体上限 32 KiB，字段值由上游校验。请求超时 30 秒，不跟随重定向。HTTP 失败保留状态码，不回显上游响应体；格式错误、网络失败、重定向安全报错。列表使用 includeDisabled=true，每次服务端分页 20 条；执行历史保留分页。更新使用 expectedVersion，同一次创建/执行重试保留 clientToken。

## 页面和状态

参照 mono 的列表/日历、状态筛选、统计、任务详情/历史、创建/编辑/复制、删除确认、启停和立即执行交互。Studio 复用本地控件及样式，不引入 mono 的 workspace 依赖链。创建要求 Agent ID 和任务内容，支持 Web/飞书投递；编辑保留未改变的投递元数据。复制只打开表单，保存才写入。

完整读取任务分页后再展示日历或筛选列表，按 ID 去重，列表前端每页 10 条。统计使用上游实际的全历史范围，不标为不存在的近七日统计。lastRunAt 与 nextRunAt 含义不同。日历展开 Once/Interval/Daily/Weekly/Monthly 和固定时间 Cron，处理周期时区与夏令时；复杂 Cron 仅显示服务端 nextRunAt。单元格按任务合并多次执行。日历按设备时区显示，周期文案标注配置时区。

没有 Runtime 时不请求。切换目标取消读取并忽略过期结果，包括执行历史及写入完成响应。写入使用防重复提交保护；取消 HTTP 写请求不等于撤销服务端效果。写入失败保留表单，版本冲突要求刷新。加载、空数据、错误状态明确区分。既有 Studio/TOS 调度及 ADK 会话不受影响。

## 验证

见[实施和验收记录](../../prd-spec/features/studio-mpa-cron-tasks/2026-09-15-mono-task-management.zh.md)。覆盖代理边界、API schema、写入并发/幂等、分页、时区/夏令时、过期响应、IME、加载/错误/重试和键盘行为。增量覆盖率超过 95%。浏览器模拟数据验收与真实 Runtime 读取分开记录，不把模拟测试宣称为真实写入 E2E。

任务编辑器不展示执行 Agent 输入框。新任务自动使用所选 Runtime ID 作为 agentId；编辑和复制保留原值。

创建新任务不传 agentId，由 Runtime 使用配置中的 Agent 展示名称，缺失时回退运行时 Agent 名称。显式值及编辑/复制原值不变。此规则替代此前默认填写 Runtime ID 的处理。用户于 2026-09-15 明确批准；复核确认不改变鉴权和执行路由。
