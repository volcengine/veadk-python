# A2A 成员操作、空间删除与明确注册错误

[English](2026-10-22-member-actions.md)

日期：2026-10-22。ID：mpa-a2a-member-actions。状态：implemented。用户批准 Studio 详情弹窗和注销，新增空间删除，并报告同一 Runtime 在 Default 注册后出现 RuntimeId already exists。关联：[组件合同](../../../specs/mpa-collaborating-agents/README.zh.md)、[空间管理](2026-10-22-space-management.zh.md)。

## 证据与需求

FR-1：每个成员提供查看、注销。查看使用现有 ModalButton/ModalLayout 弹窗，以 Id、SpaceId 调用 GetA2aAgent。仅展示有长度限制的名称/状态/来源/默认版本/项目，以及 Runtime ID/网络/导入类型。不返回原始 Card、含凭据 URL、提供商 Reason 或原始响应。展示或删除前校验返回的 Agent 和空间 ID。

FR-2：注销前显示带名称的确认，说明会移除共享空间内注册、影响发现/调用，同时保留来源 Runtime。校验 Studio 管理权限和目标 Runtime，核对 GetA2aAgent 身份，再以 Id 调用 DeleteA2aAgent。成功刷新成员，不删除 Runtime，不改绑定。结果不明不自动重试。

FR-3：空间选择旁增加删除空间。确认指明所选空间和不可恢复影响。调用 DeleteA2aSpace 前，授权目标，读取目标 Runtime 当前绑定，拒绝已绑定空间（409 space_bound）；核对 GetA2aSpace 的身份，并查询 ListA2aAgents 第 1 页、大小 1。拒绝非空空间（409 space_not_empty）。不级联注销、不自动解绑。并发及其他调用者由云 API 管理；用户需确认其他调用方已停止依赖该空间。成功刷新空间，不保留已删除的本地选项。当前 MPA 绑定检查不证明其他 MPA 未使用此共享空间。

FR-4：区分云端明确拒绝与写入不明。现有创建处理将所有异常归为 502。用户报告的 RuntimeId already exists 是明确拒绝，并非超时证据。为现有签名 helper 增加可选结构化错误模式，仅供 A2A 中心使用。将已知提供商状态/代码/消息特征映射为安全原因枚举（runtime_already_registered、forbidden、invalid_parameter、not_found、conflict、rate_limited）。不返回原始提供商消息。网络/5xx/成功响应损坏仍为不明，须刷新核对。不自动重试或绕过注册。公开文档未定义普遍跨账号/地域唯一规则；诊断针对本次 Runtime 来源拒绝。

## 接口、并发与边界

GET/DELETE /web/a2a-agents/{agentId}?targetRuntimeId=...&spaceId=...&region=... 返回脱敏详情或 {deleted:true}。DELETE /web/a2a-spaces/{spaceId}?targetRuntimeId=...&region=... 返回 {deleted:true}。云操作前执行已有管理员、地域、ID 与目标授权。前置读取失败不删除。返回 ID 必须匹配所请求目标；无效响应快速失败。详情显式展示加载/错误/重试；写操作确认展示明确拒绝或结果不明。提交期间关闭会中止浏览器请求，不声称云端回滚，并锁定后续写操作直至刷新。切换 Runtime/空间卸载弹窗并中止旧响应。共享 busy 防止创建/绑定/注销/删除并发；详情查询仅只读。成功后刷新失败仍为写入成功，并显示列表错误。复用已有组件变量/间距，不新增依赖或图标。

非目标：删除来源 Runtime、验证期间真实注册/删除、自动跨空间迁移、编辑原始 Card、显示凭据、提供商全局策略改变、Runtime/Harness 变化。签名 helper 的结构化模式默认关闭，原有调用者错误行为保持不变。不改 Runtime 列表默认分页。

## 任务、测试与验收

T-1 / AC-1（FR-1）：先补详情身份/脱敏/授权失败测试，以及 UI 弹窗/加载/重试测试，再实现受限投影。
T-2 / AC-2（FR-2）：测试一次明确注销写入、错误空间拒绝、取消、权限失败与成功后刷新；实现确认与客户端。
T-3 / AC-3（FR-3）：测试绑定/非空/无效响应检查、拒绝时零写入、精确 DeleteA2aSpace Payload 及旧弹窗清理；实现删除。
T-4 / AC-4（FR-4）：测试用户报告的重复特征、400/403 与网络/无效响应区分、非 A2A helper 行为保留、不自动重试；实现错误脱敏。
T-5 / AC-5：对齐双语文档、frontend README 与产物；执行定向 Python API/代理测试、npm test/build/check:i18n/test:webui-assets、变更文件 Ruff/Pyright 与 tsc、真实浏览器模拟正常/失败/取消/窄屏，以及范围内密钥扫描和差异检查。在下方记录实际结果，不以模拟测试声称真实云写入通过。

## 评审与批准

review-spec 不可用，直接评审。用户批准：“可以，按这个给我实现”和“增加删除空间的功能”。2026-10-22 读取官方文档：[GetA2aAgent](https://docs.volcengine.com/docs/86681/2249666)、[DeleteA2aAgent](https://docs.volcengine.com/docs/86681/2249664)、[DeleteA2aSpace](https://docs.volcengine.com/docs/86681/2249661)、[删除空间前提](https://docs.volcengine.com/docs/86681/2248661)。DeleteA2aAgent 示例错误地使用 as- 前缀；实现使用实际选中的 a- 成员身份，并用 GetA2aAgent 核对。此设计评审前不修改生产代码。范围、身份、权限、边界、双语一致性、状态恢复和可测试性均无阻塞项。

风险：共享空间删除/注销影响其他调用方，必须确认，本次不做真实写入。云端前置查询不能锁定成员，因此提供商拒绝仍是最终依据。结果不明不静默成功、不自动重试。回滚代码不会恢复云注册/空间；恢复应由操作者明确重新创建，不属于自动路径。初始验证：not_run；实现与实际证据随后记录。未请求提交、推送或部署。

## 实现、评审与验证（2026-10-22）

状态：已本地实现，未执行云端写入。已在原有未提交中心变更之上完成 T-1 至 T-5、AC-1 至 AC-5。测试先行证据：实现前 19 项 Python 用例及 4 项前端用例失败。最终评审修正弹窗退出期间重复提交，区分读取前置检查失败（尚未写入）与写入后结果不明，并在提供商错误使用 5xx 状态时仍保留明确的 Runtime 重复业务错误。仅识别已知重复特征；其他 5xx/网络错误保持结果不明。API 投影不暴露原始 Card、原始配置 URL 或提供商错误体。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| uv run --extra dev pytest tests/cli/test_a2a_center_actions.py tests/cli/test_a2a_center_registration.py tests/test_mpa_collaborator_proxy_policy.py -q | pass | 70 passed；本地模拟云，身份/授权/脱敏/空空间/错误分类 |
| uv run --extra dev pytest tests/cli/test_frontend_runtime_proxy.py -q | pass | 129 passed；签名 helper 默认兼容性及原代理回归 |
| npm --prefix frontend test | pass | 1389 项 Node 测试；11 文件 175 项 Vitest 用例，其中协作页面 28 项 |
| npm --prefix frontend run build | pass | 更新发布产物；既有大分块警告 |
| npm --prefix frontend run check:i18n | pass | 2 种语言 / 22 个命名空间 |
| npm --prefix frontend run test:webui-assets | pass | 114 个发布文件 / 351 个引用 |
| frontend/node_modules/.bin/tsc --noEmit -p frontend/tsconfig.json | pass | 无诊断 |
| 变更 Python 的 pre-commit ruff-check / ruff-format | pass | frontend/server/a2a_center.py、tests/cli/test_a2a_center_actions.py、veadk/cli/cli_frontend.py |
| 新增服务端模块及测试 Pyright，.venv/bin/python | pass | 0 错误/警告；复用现有 Pyright 可执行文件和仓库解释器 |
| CLI 整文件 Pyright | fail（基线） | 37 项诊断；与恢复旧签名 helper/挂载的对照在严重性/消息/规则多重集上完全一致，无新增诊断 |
| 浏览器 | pass | 真实浏览器、模拟 API：详情弹窗、390px 视图、Escape/焦点恢复、明确注销及刷新、空空间删除与旧选择移除；React 测试另覆盖前置检查失败/结果不明/迟到响应 |
| 源码密钥扫描 / 差异空白 | pass | 使用仓库配置执行 gitleaks；保留既有排除项，未绕过策略 |
| 全量 Python 回归 / 真实云写入 | not_run | 共享 helper 默认行为保留，受影响代理/API 测试通过；验证期间未授权修改真实注册/空间 |

提供商报告的 Runtime 重复错误解释了本次问题；只读列表不能证明全局唯一性或最终写入结果。未自动迁移、注销、删除、重试、提交、推送或云部署。本机服务生效与产物检查在下方另记。验证后删除临时夹具及诊断对照文件。

评审补充：公开文档未定义默认标记空间的独立本地删除禁令。因此 UI/服务端仅校验官方的空间为空前提及当前 MPA 已解绑要求，实际云端删除策略交给 AgentKit 判断。未尝试删除真实默认空间。

本机生效已验证：沿用原 `veadk studio` 命令重启，确认当前构建入口与 JS 产物（HTTP 200），实时 OpenAPI 包含成员 GET/DELETE 和空间 DELETE 路由；无效目标返回 HTTP 422，未触发云请求。临时浏览器夹具、Python 对照文件和验证 Vite 进程已删除。默认空间策略评审修正后，已对齐最终构建、定向测试、i18n、类型检查、密钥扫描及产物检查。未提交代码或执行云端写入。
