# AgentKit A2A 中心注册与旧配置退役

状态：已接受设计；实现与验证另行记录。日期：2026-10-22。类型：功能与配置退役；风险 L3。用户已确认两种官方注册来源、只维护 MPA 与空间关联、删除旧历史配置。补充 2026-10-21 空间接入设计，替代其中“保留手动注册”的决策，其余派发合同继续有效。

## 背景、事实与场景

Studio 管理员应在协作 Agent 页面选择空间并注册已有服务。注册成功进入 AgentKit 中心，MPA 动态读取该空间，不维护逐 Agent 本地副本。其他账号/地域、停用或不兼容的服务不得因为注册成功而被当成可执行成功。

| ID | 类型 | 结论 | 证据 | 设计影响 | 验证方式 |
|---|---|---|---|---|---|
| FACT-1 | 已验证事实 | Runtime 已按空间动态发现 | agentkit-mpa-agent/app/services/a2a_space.py 的 A2ASpaceService | 保留关联与执行路径 | 原有空间测试 |
| FACT-2 | 已验证事实 | Studio 有受控签名 OpenAPI | veadk/cli/cli_frontend.py 的 _agentkit_openapi_post、_require_agent_management | 注册在 Studio 服务端执行 | 路由授权测试 |
| FACT-3 | 官方接口 | CreateA2aAgent 支持 Runtime、Standard；Standard 支持 json、url | https://docs.volcengine.com/docs/agentkit/CreateA2aAgent_-_Creates_an_A2A_agent?lang=zh | 按官方字段构造请求 | Payload 契约测试；真实云验证单列 |

## 目标、非目标和需求

| ID | 来源 | 优先级 | 触发范围 | 必须行为 | 可观察结果 |
|---|---|---|---|---|---|
| FR-1 | 用户原始请求 | 必须 | 管理员注册 | Runtime 来源提交 RuntimeId、NetworkType；Standard 来源支持 Card JSON 或 URL | 中心返回 Agent ID |
| FR-2 | 用户原始请求、FACT-1 | 必须 | MPA 选择空间 | 只保存一个空间关联，包含后续新增成员 | 无逐 Agent 本地写入 |
| FR-3 | 用户原始请求 | 必须 | 升级 Runtime | 删除当前 MPA 的旧本地注册数据，退役旧 CRUD，保留其他 MPA 和执行历史 | 幂等清理及 410 |
| NFR-1 | Studio AGENTS.md、FACT-2 | 必须 | 注册 API | 管理员及目标 Runtime 权限检查；输入有界；不回显 Card 凭证；失败不自动重试 | 授权、错误与重复点击测试 |

非目标：创建新的 Runtime、创建空间、编辑/删除中心已有 Agent、代理/VPC 配置向导、OAuth 适配、改变已有 dispatch_a2a_task 或 Harness 终态语义。Runtime 来源可输入任意有访问权的已部署 Runtime ID，不把 Studio 创建标签当作全部账号资源。现有 Runtime 列表可供选择，未列出的仍可输入。

## 设计与接口

DEC-1：Studio 的 POST /web/a2a-agents?region=... 接受 targetRuntimeId、spaceId 以及 source 区分的配置。使用现有 Studio 云凭据调用 CreateA2aAgent，返回仅 id；不将 Card/密钥放进响应、日志、浏览器持久化。Runtime 来源对待注册 Runtime 再做可见性校验；空间由官方 API 检查访问权。JSON Card 必须为对象且有非空 name、url、version；URL 只允许 HTTPS 无用户信息，抓取由 AgentKit 执行，Studio 不直接请求任意 URL。ProjectName 随所选空间传递，缺失时默认 default；SetDefaultVersion=true；网络为显式选择的 public/private。使用 SDK 已有签名链，不引入依赖。

DEC-2：UI 沿用当前空间选择和分页，新增“注册 Agent”内联表单。来源、导入方式及字段 progressive disclosure，保存期间防重入，可取消浏览器请求但提示云端结果可能已提交。网络/5xx 或取消后的结果不明，禁止盲目再次提交；先刷新中心确认，再由用户主动发起新的注册。成功后关闭表单、清空输入、刷新空间成员；刷新失败明确区分“注册已成功，列表刷新失败”。切换空间/Runtime 必须清空旧表单并取消旧响应。

DEC-3：Runtime 启动完成 schema 迁移后执行受控幂等清理，只 DELETE mpa_collaborating_agents WHERE mpa_id=当前配置值，不执行 DROP，不触及空间关联或工具账本。缺表为空操作；身份缺失时不清理。共享 collaborator_credential_key 保留，避免滚动升级中旧实例的在途写入被破坏；删除的是旧注册业务记录，不旋转或删除共享密钥。旧端点保留鉴权后返回 410 legacy_registration_retired；不能再写新旧记录。已发布 SQL 迁移原样保留。清理发生在启动阶段而非模型只读工具，避免绕过 Harness。

## 失败、安全、迁移及回滚

请求体校验失败 422，无权 401/403/404；云端拒绝或网络失败返回脱敏错误。成功表示中心接受注册，不表示远端执行已验证。并发点击仅发送一次注册；超时不会切换身份、自动重试或自动绑定不同空间。旧配置删除不可自动还原，升级前应由运维使用原有 DB 备份；回滚二进制不会恢复被删记录。保留表结构兼容旧迁移，降级后需重新配置；不得恢复旧 UI 来声称历史仍存在。共享凭据使用的 Studio 账号与 Runtime 云账号应一致；否则中心空间/权限校验失败，不能跨账号静默降级。

## 验收、计划与追踪

| ID | Given | When | Then | 验证方式 | 环境 |
|---|---|---|---|---|---|
| AC-1 | 可访问空间与 Runtime | Runtime 来源注册 | CreateA2aAgent 仅带对应字段 | backend tests | 本地模拟云 |
| AC-2 | Card JSON 或 HTTPS URL | Standard 注册 | 正确 ImportType，非法/过大数据拒绝 | backend tests | 本地 |
| AC-3 | 非管理员或 Runtime 无权 | 注册 | 无云端写请求 | backend tests | 本地 |
| AC-4 | 当前与其他 MPA 的旧记录、空间和账本 | 重复启动清理 | 仅当前旧配置删除；无全局凭据误删 | Runtime tests | SQLite；真实 PG 单列 |
| AC-5 | UI 表单或超时取消 | 提交/切换/重试 | 无旧响应污染、无自动重复注册、IME 不提交 | frontend tests + browser | 本地 |
| AC-6 | 已退役路径 | 旧客户端请求 | 鉴权后 410，无旧数据新增 | Runtime tests | 本地 |

| 需求 | 设计 | 验收 | 验证 | 文档覆盖 |
|---|---|---|---|---|
| FR-1 | DEC-1/2 | AC-1/2/5 | Python/React/browser | 已覆盖 |
| FR-2 | DEC-1 | 原空间回归 | test_a2a_registry_collaborators.py | 已覆盖 |
| FR-3 | DEC-3 | AC-4/6 | cleanup/API tests | 已覆盖 |
| NFR-1 | DEC-1/2/3 | AC-2/3/5/6 | 边界测试 | 已覆盖 |

执行顺序：先契约与清理/API 测试；再 Studio 注册路由和 UI；最后回归、构建、双轮评审及交付。风险：官方文档 AgentCard 字段描述存在歧义，按字符串化 JSON 与 GetA2aAgent 对齐；真实创建仍需独立云验收，不能用模拟结果声称已验证云端。UI 无真实云写入时使用确定性服务响应验证交互。当前请求不包含发布或新建云资源。

## 设计评审

结论可实施。已修正：全表删除改为当前 MPA 范围；旧迁移不改；清理不放只读路径；创建不自动重试；权限复用现有管理边界；UI 不清除空间关联。无待用户裁决的范围问题。真实云创建、PG 实例清理和发布状态必须单列，尚未执行。

## 备选、发布和风险

DEC-4：比较继续保留逐 Agent 本地注册、让 Runtime 承担中心创建、由 Studio 签名中心创建。选择第三项复用 Studio 已有控制面凭据和管理员边界，不给每个 Runtime 新增创建权限。目标 Runtime 的查询/派发权限保持原状。未来切换逐用户云身份时重新评估账号一致性。

| ID | 触发 | 概率/影响 | 缓解 | 监测 | 恢复 |
|---|---|---|---|---|---|
| RISK-1 | 云端创建超时但实际已提交 | 中/重复注册 | 不自动重试，结果不明先刷新 | UI uncertain | 管理员核对中心 ID |
| RISK-2 | 升级清理历史配置后回滚 | 中/配置不可自动恢复 | 上线前使用既有备份；仅当前 MPA | deleted_count | 运维恢复备份或重新注册 |
| RISK-3 | 官方 API 与文档字段不一致 | 中/注册拒绝 | Payload 契约测试与独立云验收 | 脱敏错误类型 | 保留控制台注册入口 |

发布顺序：运维先备份旧配置，升级 Runtime 验证 scoped cleanup，再发布 Studio 构建。单 Runtime 灰度验证三种输入、中心 ID 回读和原有派发；没有证据不扩大灰度。失败回滚对应二进制，数据仅由备份恢复，不自动创建替代资源。日志仅记录 action 所属错误类型、地域/空间 ID 和删除数量；不打印请求体或异常正文。无新增强制性能阈值。

## 实现与本地验证（2026-10-22）

已实现两种来源、互斥字段校验、所选空间刷新、凭据遮罩、结果不明处理及旧表单退役。Runtime 清理实现在 agentkit-mpa-agent，线上数据在升级启动之前不会删除。转发所选空间的 ProjectName，缺元数据时默认 default。用户原有 package-lock.json 改动未覆盖。

| 检查 | 结果 | 范围与限制 |
|---|---|---|
| 注册与权限测试 | 23 passed | 模拟云端，未真实调用 CreateA2aAgent |
| Runtime API/清理/空间测试 | 40 passed | SQLite；未执行真实 PG 锁路径 |
| Runtime 受影响模块行覆盖 | 83/86（96.51%） | 行/分支综合显示 94%；不是整个 app 覆盖率 |
| 代理单文件回归 | 129 passed | 混合运行有两项 provider/地域失败，单列记录 |
| npm test | Node suite 和 156 Vitest cases passed | 成功、失败、空、取消、IME、键盘、焦点及刷新失败 |
| 构建/产物 | pass；114 files、351 references | veadk/webui 已更新，未部署 |
| i18n | 2 locales、22 namespaces consistent | 两种语言 |
| TypeScript | pass | tsc --noEmit |
| 新后端模块/测试 Pyright | 0 errors | Studio 现有环境 |
| CLI 整文件 Pyright | 37 errors | 删除新增挂载的对照同样有 37 项，诊断消息完全一致 |
| Ruff | pass | 修改的 Python 文件 |
| 浏览器 | 模拟 API 验证通过 | 注册成功后刷新、JSON 错误/遮罩、拒绝/结果不明、菜单 Escape/焦点；390px 无横向溢出 |
| 密钥扫描 | 仓库规则通过；默认规则 1 项旧第三方误报 | 含产物 21.73 MB；Lexical anchor/focus.key 表达式，HEAD 旧产物同样命中；未绕过规则 |

两轮自审修正共享密钥退役竞争、Select Escape 冒泡与 React 初始化顺序。JSON review ledger 校验通过，未使用独立评审 Agent。Runtime 冻结源码全量验证记录在对应 Runtime 仓库报告中；发布准出与这些本地检查分开。未创建云资源、未清理线上 PG、未发布镜像或部署。真实验收前需要同时更新 Studio 与 Runtime。

### Runtime 和混合回归最终证据

Runtime 固定源码 make test：10366 passed、304 skipped、1 项 scheduled Worker 基线失败；前后指纹一致。475 个生产/脚本 Python 文件与交付树一致；3 项补充管理路由测试单独通过，未改生产代码。Studio 混合回归：150 passed、两个 provider/地域断言失败；只移除新增 CLI 注册挂载的相同组合也复现这两项失败。当前与对照的代理单文件均为 129 passed。CLI 整文件 Pyright 在有/无挂载时也有完全相同的 37 项诊断。这些属于明确保留的验证限制，不能宣称全量门禁通过。未发布或清理线上数据。
