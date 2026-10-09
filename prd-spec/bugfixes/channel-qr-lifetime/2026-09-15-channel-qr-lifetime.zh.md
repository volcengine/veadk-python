# 渠道配对二维码仅临时展示

[English](2026-09-15-channel-qr-lifetime.md)

日期：2026-09-15。状态：implemented。契约：[MPA channels](../../../specs/mpa-channels/README.zh.md)。用户批准移除等待/链接文案，导航或刷新后不恢复二维码。

## 证据、范围与需求
RuntimeChannels 在 sessionStorage 保存绑定 ID，并在挂载时恢复配对，导致回到渠道后恢复二维码。FR-1：移除 PENDING 等待文案和“打开授权页面”链接，保留二维码及有意义的错误/终态。FR-2：绑定界面和轮询仅存在于当前挂载的渠道面板。切换渠道/页面、浏览器刷新或面板“刷新”均清除配对展示；返回后需主动重新生成。忽略并清理旧版已保存绑定 ID。FR-3：保留持久化机器人配置，取消请求/定时器并忽略迟到响应；不调用 DELETE、不撤销平台授权、不修改后端。

## 设计与评审
绑定状态仅存 React，移除 sessionStorage 保存/恢复，挂载时清理旧键，面板刷新时重置临时配对状态。复用渠道 key 挂载和 AbortController。直接评审（review-spec 不可用）：API/凭据/服务端绑定生命周期不变，仅改变客户端恢复契约。用户明确批准此变化。隐藏二维码不代表服务端撤销。无未解决阻塞。

## 任务与验收
T-1/AC-1（FR-1）：回归验证二维码保留，等待文案/链接消失。
T-2/AC-2（FR-2/3）：测试切换/返回渠道、旧存储 ID、刷新及取消；在 RuntimeChannels.tsx 实施。
T-3/AC-3：前端 Vitest/回归/构建/资源及浏览器检查，更新文档。影响组件、组件测试、双语设计/契约、前端 README 和 webui 产物。不改 Python 或执行真实云操作。

## 验证
2026-09-15，当前未提交前端 diff：pass。测试先行：实施前 8 项失败，实施后 31 项渠道组件测试通过（`cd frontend && ./node_modules/.bin/vitest run tests/runtimeChannels.test.tsx --maxWorkers 1`）。前端回归：1206 项通过（`npm --prefix frontend test`）。生产构建：pass（`npm --prefix frontend run build`），仅既有大包体警告。资源校验：104 文件、248 引用通过（`npm --prefix frontend run test:webui-assets`）。

真实组件与模拟 API 的浏览器验证：配对区不显示等待/链接文案，键盘切换并返回不恢复配对，浏览器刷新不恢复，钉钉面板刷新移除配对且保留机器人摘要；检查了 480×850 布局。组件测试确认二维码图片初始保留、重置后消失；预览响应未提供真实图片字节。临时文件/服务/标签页已清理并恢复视口。双语文档、相对链接及定向空白检查通过。Python 检查：not_applicable（未改 Python）。真实平台操作：not_run（纯界面变更，未用真实账号）。
