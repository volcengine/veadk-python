# 重新构建损坏的 Studio WebUI 静态资源

[English](2026-09-23-rebuild-corrupted-assets.md)

- 变更 ID：`studio-webui-build-integrity`
- 创建/修订日期：2026-09-23
- 状态：implemented
- 组件规格：无变更；HTTP、UI 和部署契约均保持不变。

## 背景与证据

云上 Studio 根路径返回 HTTP 200，但页面空白。引用的 `assets/app/index-Ceg2hYta.js` 以 `<<<<<<<< HEAD` 开头，`node --check` 报 `Unexpected token '<<'`。仓库扫描发现 114 个打包 JS 文件含冲突标记。原有静态资源检查仅验证引用，不检查冲突标记。源码构建还遇到企业微信回调参数隐式 `any` 的 TypeScript 错误，以及本地缺少已声明的 SDK 依赖；后者属于安装问题，不是应用变更。

## 目标、非目标、场景与需求

- 目标：提供可解析、内部引用一致的 WebUI 资源，使 Studio 登录页正常渲染。
- 非目标：改变登录、UserPool、Runtime、MPA、调度器或企业微信授权行为。
- `FR-1`：给定干净的源码构建，打包后 HTML/CSS/JS 文件不包含行首 Git 冲突标记。
- `FR-2`：未登录浏览器访问云上 Studio 的 `/` 时，显示 Identity 登录界面而不是空白页。
- 边界：未登录访问 `/web/runtime-config` 会跳转登录；这不能证明登录后的工作台。

## 设计与契约影响

使用现有 `frontend/scripts/build.mjs` 重建 `veadk/webui/`，不手工编辑压缩文件。在 `frontend/scripts/verifyBuiltAssets.mjs` 增加冲突标记断言。为现有企业微信 SDK 回调结果补充窄类型以通过 TypeScript 构建；运行逻辑不变。不新增依赖、API、状态、持久化、权限、凭据处理或兼容性契约，因此无需修改组件规格或用户文档。逐个手改 114 个文件不可重复，故不采用。生成的 JavaScript 包含模板字符串空白，即使语法和打包检查通过，`git diff --check` 仍可能报告生成行。

## 任务与验收

| 需求 | 任务 | 验收 | 证据（2026-09-23，`15ac109`） |
| --- | --- | --- | --- |
| `FR-1` | `T-1` 重建打包资源；`T-2` 增加冲突标记检查 | `AC-1` 所有打包 JS 可解析且资源引用有效 | `npm run build`：pass；`npm run test:webui-assets`：pass，101 个文件/236 处引用；对所有打包 JS 执行 `node --check`：pass |
| `FR-2` | `T-3` 重新部署现有 Studio 应用 | `AC-2` 浏览器显示 Identity 登录标题与按钮 | 现有 VeFaaS 应用更新：pass；真实浏览器 DOM 和截图：pass |

`npm test`：pass（1,253 个 Node 测试、25 个 Vitest 测试）。针对暂存文件的 pre-commit：pass。全文件 pre-commit：fail，因为 Ruff 格式化了三个无关的既有 Python 测试文件；这些附带修改已撤销。`git diff --check`：fail，原因是生成的 `website-integration.js` 模板字符串中的空白。登录后的工作台及 MPA 创建：not_run，不属于本次空白页修复。云凭据与原始日志未写入文档。

## 风险、评审与交付

生成资源的哈希和多处文件名须整体更新；只发布 `index.html` 会破坏引用。此次复用了原应用和 Identity 配置，调度器部署也已完成。源码、静态资源及浏览器检查已覆盖报告的问题。没有可用的 `review-spec` skill；直接评审确认无契约变更或安全权限扩展。本次操作性修复沿用正在进行的云上部署请求；实施前未单独记录设计审批。
