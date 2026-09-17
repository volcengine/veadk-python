# 会话历史 Sandbox 文件下载

[English](2026-09-17-history-download.md)

## 范围与批准
用户已确认历史 Markdown 路径调用 MPA 下载，并要求在 `czh/studio-cron-e2e` 实现。历史已包含 `[random.txt](/data/output/random.txt)`。无需修改 Worker、SSE 协议、artifacts 注册或持久化。

## 设计
遵循[组件契约](../../../specs/studio-sandbox-download/README.zh.md)。在助手消息块外提供会话上下文，共用 Markdown 渲染器在视频判断之前识别允许的链接。小型链接组件负责加载、错误、取消及 blob 下载。现有 ADK 客户端解析选定 Runtime，经 Studio 鉴权代理发送请求。保留链接文案，采用下文已批准的加大下载入口，不增加依赖或后端路由。

## 任务与验收
1. 先写失败回归测试，覆盖路径、中文空格、历史 Markdown、代理路由及生命周期。
2. 实现会话范围内链接与本地化加载/错误提示，再次点击可重试。
3. 执行前端测试、构建，增量覆盖率超过 95%；检查本地浏览器并提交生成的 web 资源。
4. fetch/rebase 目标上游，执行 pre-commit，然后 commit/push。

## 评审
直接评审（review-spec 不可用）：已核对职责、会话隔离、目录白名单、取消、凭据隔离、普通外链兼容及双语一致性，无阻塞。应用 frontend-design；本地未找到 ui-ux-pro-max，视觉行为遵循现有 frontend/SPEC.md。

## 风险与验证
下载受 Sandbox 生命周期限制。blob 下载会在浏览器内存缓冲文件。不会自动创建或恢复 Sandbox。实现后记录测试、浏览器证据及门禁结果。

## 已批准的展示调整
用户确认下载正常，要求隐藏旧文件卡片内容、增大并突出下载入口。复用 primary 色、最小 44px 高度、可见焦点与文件名换行；仅在会话上下文隐藏 file-card/personal-drive-enable-card 子树。回归测试保留周围 Markdown。

## 验证记录（2026-09-17）
- PASS：`npm --prefix frontend run test:sandbox-download-coverage`：26 项。新增组件行/语句/函数/分支覆盖率均 100%；已插桩增量代码行 46/46（100%）。将未插桩的 App provider 表达式保守计为未覆盖：46/47（97.87%）。既有 client/Markdown 整文件覆盖率不是增量覆盖率。
- PASS：`npm --prefix frontend test`：1102 项；`npm --prefix frontend run build`（TypeScript 与两个 bundle）；`npm --prefix frontend run check:i18n`。
- PASS：`git fetch polaris`、`git rebase --autostash polaris/czh/studio-cron-e2e`（已是最新，改动恢复）；`UV_PROJECT_ENVIRONMENT=/Users/bytedance/Applications/veadk-studio-mpa/.venv uv run --no-sync --extra dev pre-commit run --all-files`（复用现有环境，Ruff 与密钥扫描通过）。
- PASS：真实 Chrome localhost:8765，最后一个 MPA 智能体的随机文件历史：旧路径隐藏、下载按钮明显、回车触发加载与下载，Runtime 代理上游 HTTP 200。展示调整前用户也独立确认下载正常。错误/重试/取消及中文路径由隔离测试覆盖，未在真实 Sandbox 故意制造故障。窄视口未执行。
- 后端/Python 回归：不适用（无 Python 修改）。构建有既有包体积警告。生成的 vendor bundle 保留上游尾随空格；手写源码 diff 空白检查通过。
- 评审：鉴权沿用现有传输，会话上下文限制功能范围，排除路径穿越和非支持目录，已测试取消与对象 URL 释放。测试样例未添加凭据或生产 payload。
