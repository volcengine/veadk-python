# 保留探测到的 A2A 会话路由

[English](2026-09-22-a2a-session-routing.md)

## 元信息
- ID：`studio-a2a-session-routing`
- 日期：2026-09-22
- 状态：implemented
- 组件：[Studio Runtime Diagnostics，CON-9](../../../specs/studio-runtime-diagnostics/README.zh.md)

## 证据、目标与非目标
上一个无冲突的已提交前端包 `ea1c384d` 在注册 Runtime 连接时丢弃 MPA 类型和实例信息。当前源码重建后保留这些信息，即使探测结果为 `a2a-default`，也会选择原生 MPA 路由。相同连接输入的隔离回放复现了切换。受影响 Runtime 的 A2A Card 可用，原生 Profile 状态返回 `500 JWT_PUBLIC_KEY is not configured`。这不代表已确定用户历史浏览器加载的确切构建包。

目标：保留探测到的 A2A 会话协议和既有回答去重。非目标：云部署、JWT 配置、绕过鉴权、错误自动降级、修改 Profile 管理或跨协议迁移会话 ID。

## 需求与设计
- FR-1：Runtime 应用严格等于 `a2a-default` 时，即使带 MPA 类型或实例信息，创建/列表/读取/删除/运行仍使用现有 A2A 路径。
- FR-2：原生 MPA 保留 Profile 初始化、原生 CRUD/run/SSE 和执行配置前置查询。普通 ADK 应用不变。
- FR-3：聊天执行配置前置查询使用同一原生协议判断；A2A 发送不查原生执行配置。MPA 侧栏仍可使用产品信息。
- FR-4：错误、重试、取消、超时保持所选协议。401/403/500 后不降级。

向端点判断传入解析后的应用名，排除明确的 A2A 虚拟应用；聊天前置查询通过 `isMpaRuntimeApp` 复用该判断。不改变持久化结构、后端路由和凭据，不增加探测请求。每轮现有取消和结束处理保持权威。协议选择依据探测结果，而不是错误文本。

## 任务、文件与验收
- T-1 / AC-1（FR-1）：在 `frontend/tests/runSseAbort.test.mjs` 先增加失败测试，覆盖恢复的带 MPA 信息的 A2A 创建/列表/读取/删除/运行。
- T-2 / AC-2（FR-2、FR-3）：修改 `frontend/src/adk/client.ts` 和 `frontend/src/App.tsx`，验证原生前置查询保留、A2A 跳过。
- T-3 / AC-3（FR-4）：测试错误/重试/取消无协议降级；运行完整前端测试/构建、产物检查和浏览器验证。保留去重测试。
- T-4：同步双语契约、`frontend/README.md`、生成的 `veadk/webui` 产物和验证记录。

## 评审、风险与授权
2026-09-22：用户以“改下”批准局部协议修复。`review-spec` 不可用；直接评审覆盖鉴权保持、协议身份、恢复连接、原生兼容、取消和双语等价性，无阻塞项。既有 A2A 历史依赖 BFF 进程内索引，重启会清空索引；本地生效需考虑缓存的 HTML 和活动会话。本次不增加历史持久化。模拟测试不代表执行了云变更或真实模型运行。

## 验证
已实现并完成下述验证。真实浏览器传输检查区分隔离响应与真实 Runtime 访问。键盘/输入法及布局代码不变。未要求提交或推送。

### 2026-09-22 验证记录
范围：现有去重修改之上的当前未提交协议修复差异。
- pass：新增测试先复现 8 项失败、3 项通过；修复后 11 项全部通过。聊天前置查询测试执行从 App.tsx 提取的真实函数。
- pass：协议、运行/取消、会话配置定向测试共 38 项通过。
- pass：`npm --prefix frontend test`：1,272 项 Node 测试及 25 项 Vitest 测试通过。
- pass：`npm --prefix frontend run build`（含 TypeScript）；保留已有分包大小/导入警告。
- pass：`npm --prefix frontend run test:webui-assets`：104 个文件、248 个内部引用。
- pass：真实浏览器隔离页面导入实际客户端，验证 A2A 创建/空列表/读取/运行/删除、加载/取消、500 错误显示与显式重试、原生 MPA Profile/会话创建。响应为模拟，不代表真实模型验证。
- pass：定向运行现有 gitleaks pre-commit hook，包含生成的应用入口；`git diff --check`。首次因沙箱拒绝读取 uv 缓存，通过限定执行权限解决，未更改全局配置。
- not_applicable：新增 Python 检查、生成 Python、harness-sidecar 覆盖率、输入法/键盘/布局改动，本次均未涉及。此前 A2A 后端检查在其独立 PRD 中记录。
- not_run：提交前分支同步/all-files pre-commit，未要求提交。未执行真实模型生成。
- 本地生效：既有静态文件回退直接从磁盘提供 `/index.html`，无需重启即可加载新入口；`/` 在正常重启前仍保留启动时缓存的入口。未重启后端、修改云端、提交或推送。

- pass：已登录的实际 Studio 浏览器通过 `/index.html` 加载 `index-1z730Cp-.js` 和 MPA 选择器，使用既有本地服务及身份。
- pass：实际 Studio 首次连接在 Runtime 探测阶段失败。通过 UI 显式重试后成功：选中应用为 `a2a-default`，历史栏出现新会话，输入框可用，没有 JWT 创建错误。真实模型生成仍为 not_run；流式行为由隔离浏览器/客户端测试覆盖。
- 最终评审：新增生产修改仅限共享原生会话判断和聊天前置查询门控。保留 MPA 连接信息、鉴权和既有去重修改。代码审查未发现阻塞项，显式重试连接后实际创建会话通过，不宣称验证了真实模型回答。
