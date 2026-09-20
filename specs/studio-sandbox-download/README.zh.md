# Studio Sandbox 下载

[English](README.md)

组件：studio-sandbox-download；修订：2026-09-17；状态：active。
职责代码：frontend/src/ui/SandboxFileLink.tsx、Markdown.tsx、App.tsx、adk/client.ts。依赖现有 Studio Runtime 代理与 MPA 会话下载接口。关联 [PRD](../../prd-spec/features/studio-sandbox-download/2026-09-17-history-download.zh.md)。

## 契约
- CON-1：仅有 appName/sessionId 上下文的助手会话 Markdown 转换 `/data/output/`、`/data/workspace/` 下的绝对链接。URL 转义只解码一次；拒绝非法转义、路径穿越段、反斜杠、控制字符、空文件名及 query/hash 后缀。支持中文和空格。其他 Markdown 消费方和链接保持现有行为。
- CON-2：GET `/api/v1/sessions/{sessionId}/files/download?path={encodedPath}` 使用当前 app 解析出的端点及既有鉴权/身份传输。Runtime 凭据留在服务端；MPA 校验会话归属，Worker 执行文件系统边界校验。不查询 artifacts，不创建 Sandbox。
- CON-3：点击阻止导航，抑制重复请求，展示本地化加载状态，以路径文件名保存 blob 并释放对象 URL。失败显示局部 alert，再次点击重试。切换上下文或卸载取消请求并忽略过期响应。沿用现有传输超时。

## 数据、兼容与诊断
无持久化、配置或协议变更。历史及流式 Markdown 共用渲染。普通外链及视频保持既有行为。错误使用本地化通用提示，不显示服务器响应内容。Sandbox 过期或文件删除会使旧链接失效；浏览器缓冲完整文件。

## 验证与变更记录
测试：frontend/tests/sandboxDownload.test.tsx、sandboxDownloadClient.test.ts。覆盖 CON-1/2/3，包括非法路径、当前 Runtime/会话路由、取消与重试。执行 `npm --prefix frontend test`、专用 Vitest 覆盖率、构建与浏览器历史下载。PRD 记录结果和边界。已实现，验证结果见 PRD。

- CON-4：会话 Markdown 隐藏 `file-card`、`personal-drive-enable-card` 元素及其内容。下载入口使用主题 primary 色、16px 字体、最小 44px 高度、可见键盘焦点和文件名换行。每个下载入口独占一行，宽度随内容适配。保留周围消息正文。由 sandboxDownload.test.tsx 验证。
