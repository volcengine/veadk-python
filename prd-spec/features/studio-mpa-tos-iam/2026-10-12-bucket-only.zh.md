# Studio MPA TOS IAM 挂载

## Lifecycle 合入方案（2026-10-14）

用户确认从 `superops-team/veadk-python:feat/mpa-lifecycle-upstream-20261013`
（`2ffe6e14`）新建独立分支，创建替代 PR 后关闭 #25，保留共享源分支和官方
PR #1163 不变。解决请求模型、API 和表单冲突时，同时保留自动 OpenViking、
独立 PostgreSQL Workspace、`aidb` 名称预检/占用和最大实例数配置，TOS 则使用
仅选桶的 IAM Role 配置。README 保留双方说明，WebUI 生成文件按正常构建刷新。
不新增接口语义，不部署云端，不迁移已有资源。

手工设计评审确认：组合保留双方已批准行为、名称占用、请求身份以及 TOS 临时
配置；除现有 Role 设计外不改变组件语义。去掉移植 TOS 段落与目标分支冲突的
CON-17 标号，保留目标的 BytePlus CON-17 和其他 lifecycle 标识。

2026-10-14 验证结果（基线 `2ffe6e14`，本次合入工作区 diff）：

- 新增 4 个 lifecycle/TOS 组合用例（Python、Vitest 各 2 个）。创建请求模块
  18/18 通过，表单 67/67 通过。手动模式测试首次预期错误，已按既有省略字段
  契约修正；自动模式保留 `openvikingMode=auto`。未确认独立业务缺陷。
- 托管 MPA/Tool/资源列表 pytest 1,038/1,038 通过，覆盖率运行同样通过。
  相对目标分支的增量可执行行覆盖率 100%：Python 102/102、TypeScript 10/10，
  utree 解析 coverage.py XML / Clover XML，按用户要求的 95% 阈值检查
  （不冒充 CI 规则）。
- 全量前端 1,389 个 Node 测试、105 个 Vitest 用例通过；构建、打包资源、
  i18n、全文件 pre-commit 通过。Python 版本为 3.12.12。
- 全量 Python：7,150 通过、16 失败、2 收集错误、59 跳过、4 xfailed、
  6 个 subtest 通过（双 worker，469.04 秒）。目标分支干净源码同样复现
  16 失败/2 错误（其他 99 个用例通过），缺少可选 llama_index、openai_codex、
  anthropic 依赖。变更源码 Pyright 有 15 个 SDK 构造参数错误，目标分支
  `mpa_tool.py` 同样复现。这两项门禁仍失败/受阻；未声明 smoke 或 Python 3.10
  已验证。
- 隔离的本地浏览器验证：自动 OV/独立 PG/所选桶组合提交且没有 TOS 密钥，
  正常/空列表/加载/错误/重试状态、键盘选桶、任务取消/重试、步骤导航及
  390px 窄屏。新提示文案已可见验证。接口为模拟，不证明真实云端创建。
  临时验证文件已删除。

本次合入代码已实现、定向检查已验证，尚未部署；下文历史 V42 云端证据不验证
这次新合入版本。

用户于 2026-10-14 要求仅调整提示文案：未选桶时文件保存在沙箱本地目录。
同步中英文提示；内置配置默认不挂载 TOS、CLI/profile 兼容行为均不变。

[English](2026-10-12-bucket-only.md)

- 变更 ID：`studio-mpa-tos-iam`
- 日期：2026-10-12
- 状态：implemented；官方分支定向检查 verified；保留历史 V42 云端证据；官方迁移版未部署；基线全量门禁 blocked
- 基线：官方 `origin/main`，`812faadf`；初始实现及验证基线：`superops/main`，`035387d1`
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，会话输出存储。

## 背景与范围

Studio 目前要求同时提供 `tosAccessKey`、`tosSecretKey`、`tosBucket`。
`mpa_tool.build_tos_mount_config` 固定输出 AK/SK 鉴权；AgentKit SDK 支持
不带 Credentials 的 `TOS_CREDENTIAL_TYPE_IAM_ROLE`。已有 managed IAM
协调器保留额外绑定、拒绝冲突策略，但平台 TOS 策略没有业务桶写权限。

用户于 2026-10-12 确认 Studio 只选桶，并自动增量补齐桶授权。本次只修改
TOS 挂载鉴权，不改 Studio 登录、Runtime KeyAuth/JWT 或 Worker 协议。
最初实现范围不含发布。用户于 2026-10-12 随后明确授权提交推送、更新现有云端
Studio 并创建测试 MPA；创建桶、修改公开策略或迁移已有会话仍不在范围内。

## 需求与场景

### 已批准的桶前缀调整

2026-10-12 用户将 Studio 可选桶收窄为桶名以 `agentkit-platform-` 开头。
选择器在已有资源接口传入可选 `namePrefix`，按大小写敏感的精确前缀匹配，并在
搜索、计数和分页之前过滤。不传前缀的通用部署查询保持原行为。Studio 创建拒绝
其他桶及其恢复草稿，且在云调用前失败；独立 CLI/Worker 桶名校验保持不变。
本调整不修改角色已有策略、桶公开策略或会话路径。测试允许/排除/伪相似桶名、
空选择、旧草稿、参数传输及分页；人工设计复核确认这些边界。
此前版本已部署为 V41，环境变量未变，前端文件哈希匹配。用户提出本调整前，
尚未提交 MPA 或绑定桶策略；云端创建及全链路验证暂缓。

前缀调整验证：新增 8 个 Python 用例和 3 个 Vitest 用例。相关 Python 754/754，
创建窗口 46/46，完整前端 1,377 个 Node 测试及 73 个 Vitest 用例通过。构建、
前端产物（113 文件/350 引用）、i18n、Ruff、改动文件 Pyright 和 pre-commit 通过。
本轮四个目标文件相对 HEAD 的可执行增量行覆盖率为 100%（Python 22/22、前端
10/10），utree 使用 coverage.py XML 和 Istanbul Clover XML 统计。先确认缺少前缀
逻辑时测试失败，再同步相关 Studio fixture，没有放宽授权顺序或失败传播断言。
全量 Python 再跑：6,495 通过、6 失败、2 收集错误、19 跳过、2 xfailed、6 subtests
通过；失败的 Harness 用例和可选依赖缺失均为此前已复现的基线阻塞。
本地浏览器通过模拟响应确认仅展示匹配桶，临时验证页和 Vite 已清理。未报告存量
缺陷，这是已批准的范围变更。以上为发布前证据快照；后续已授权的发布和云端
Role 挂载验证仍待执行，将与本地验证结果分开记录。

- FR-1：只展示一个可选桶选择器，复用资源列表 hook 与 DeploymentSelect；
  保留加载、错误、空列表、搜索、分页、重试、禁用、键盘和取消行为。不展示 TOS AK/SK。
- FR-2：Studio 提供桶时使用实际 Worker Tool 角色的 IAM Role 鉴权；安全拒绝
  非法桶名和旧客户端非空凭据提交，清除浏览器恢复草稿中的旧凭据。未选桶保留
  服务端 profile（内置 profile 默认不挂载）。CLI/YAML AK/SK 模式保持兼容；显式 `tos-credential-type: iam_role`
  支持仅配置桶的 managed profile。
- FR-3：在工作负载身份、数据库、网络写操作前，核验桶属于部署账号且地域匹配，再协调稳定的
  桶专属自定义策略与 Worker 角色的 Global 绑定。验证账号、信任、策略内容和回读；
  保留额外策略及信任。冲突即失败；策略缺失、并发创建/绑定用有界超时恢复。
- FR-4：只在所选桶授予 `tos:HeadBucket`、`tos:ListBucket`；只对其
  `sandbox-session/*` 对象授予 `tos:GetObject`、`tos:PutObject`、
  `tos:AbortMultipartUpload`、`tos:DeleteObject`。不涉及其他桶、CreateBucket、
  桶策略/ACL、KMS 授权或全对象通配范围。
- FR-5：Tool 挂载使用 IAM Role 且不带 Credentials；保持 `/data/output`、
  规范的逐会话路径和 Runtime 非敏感挂载开关/桶名。复用核验同时检查鉴权模式
  与角色，不能只检查路径。不得隐式修改已有 Tool 和 Session。
- FR-6：权限、归属、配置和策略冲突在 IAM 阶段安全失败，返回本地化错误。
  取消保留 IAM 资源供重试；云调用使用新读取并核验账号的部署凭据。

## 设计与兼容

为 managed Worker 增加可选鉴权模式，CLI 历史默认仍为 AK/SK。Studio 请求仅
包含 `tosBucket`，固定 runner 应用 IAM Role。任务身份、锁定、取消契约保持不变。
复用已有 IAM SDK 边界、规范策略比较与错误白名单，增加独立命名的桶策略，
不改 `VeADKMPARuntimeAccessV1`。桶专属稳定策略名避免不同桶之间读改写竞争，
同一请求的并发操作可收敛。

ListBucket 暴露该桶元数据，但对象访问只允许会话输出前缀。共享角色的所有
使用者都会获得这个前缀权限，逐会话目录不是租户授权。SSE-KMS 桶需要另行
批准密钥权限。旧 Studio 客户端提交凭据字段会得到安全校验错误，需要刷新。
旧 CLI AK/SK 请求和普通智能体部署不变。

## 任务与验收

| 需求 | 任务 | 验收 | 证据 |
| --- | --- | --- | --- |
| FR-1、FR-2 | T-1：UI/API/config | AC-1：仅桶请求、清除旧密钥、选择器状态 | config/routes 和 43 个窗口用例通过；隔离浏览器通过 |
| FR-3、FR-4、FR-6 | T-2：IAM ensure 与编排接线 | AC-2：精确权限范围、重复/并发重试、失败/取消边界 | IAM/service 测试通过 |
| FR-5 | T-3：Tool 参数与复用核验 | AC-3：无 Credentials，严格核验模式/角色，旧模式不变 | Tool/worker 测试通过 |
| 全部 | T-4：文档/产物/门禁 | AC-4：定向/全量测试、构建/产物、浏览器状态、可执行增量覆盖率 >95% | 定向/构建/产物/浏览器/覆盖率通过；全量回归和 Pyright 存在已复现的基线阻塞 |

先执行相关 pytest，再执行
`uv run --extra dev pytest -n 2 -m 'not codex_smoke and not piagent_smoke'`、
`npm --prefix frontend test`、构建、产物核验、改动 Python 文件 Ruff/Pyright、
i18n、密钥扫描与 diff 空白检查。覆盖率统计可执行改动行，不以整文件替代。
浏览器检查使用隔离的模拟云响应；未单独授权的真实 IAM/挂载 E2E 标记 not_run。

## 评审与交付

review-spec 技能不可用，以人工设计评审替代，检查角色归属、增量策略范围、旧 CLI
兼容、重试/取消、本地化和双语一致性。ui-ux-pro-max 不可用，采用仓库 SPEC、
Foundation 和已有选择器行为。用户明确授权业务功能实现，单测技能的业务编辑
限制不覆盖此授权；测试仍严格断言正确行为。

## 验证与变更记录 — 2026-10-12

修改 Studio 请求/窗口、managed Worker 配置、IAM 协调、服务编排和 Tool 元数据
核验，同步双语组件契约与操作指南。无需修改 MPA Agent/Worker 源码，已有会话
挂载路径不变。复用资源选择器及其已有样式，没有新建 UI 系统。已删除临时浏览器
验证页源码并停止隔离的 Vite 服务，重新生成正式前端产物。

- **pass：**Python 3.12.12，`tests/integrations/mpa_managed` 和
  `tests/integrations/test_mpa_tool.py` 共 719/719；相比基线 677 个净新增 42 个。
  契约测试在实现前确实失败。覆盖率插件环境下，Pydantic 延迟导入导致收集失败；
  在 `pytest.main([...])` 前显式导入 `pydantic.RootModel` 后，同样 719 个测试可以
  正常统计覆盖率，未修改业务代码或依赖。基线 service 收集也复现了该覆盖率
  导入错误。最终验证未采用 Python 3.13。
- **pass：**可执行增量行覆盖率 100%：Python 97/97，由 `utree coverage parse`
  对 diff hunks 和 coverage XML 统计；前端 9/9，由 Istanbul statement 起始行与
  改动行求交。排除未改动代码、纯类型、测试、文档及生成包；不是整文件或分支覆盖率。
- **pass：**`npm --prefix frontend test`：1,377 个 Node 测试及 70 个 Vitest 用例；
  `npm --prefix frontend run build`、`check:i18n`、`test:webui-assets`（113 文件、
  350 内部引用）、Ruff、pre-commit 全文件和 `git diff --check`。Vite 保留已有大包警告。
- **pass：**真实本地浏览器、模拟 API 响应：正常选择、无 TOS 密钥输入、加载、
  空列表、错误/重试、搜索、分页、键盘选择、中文搜索输入、关闭、390px 窄窗口。
  这不是云端 IAM/挂载验证，也不是操作系统真实 IME composition 测试。
- **fail，已复现基线：**全量并行回归：6,485 通过、6 失败、2 收集错误、19 跳过、
  2 xfailed、6 subtests 通过。使用相同解释器，在隔离的 `035387d1` 归档中复测
  对应六个 Harness 用例和两个 self-host Sandbox 收集错误，完全一致（60 通过）。
  原因是缺少可选 `llama_index`/`anthropic` 依赖，未修改无关业务或安装依赖来掩盖门禁。
- **fail，已复现基线：**Pyright 使用 `.venv/bin/python`，在 `mpa_tool.py` 未改动的
  历史 SDK 调用中报 15 个签名错误；临时复制的原始基线文件也报相同 15 个错误，
  已删除临时文件。其他改动的生产 Python 文件无 Pyright 诊断。
- **not_run：**真实 IAM 写入、云端 Role 挂载会话 E2E、部署、镜像发布、提交或推送。
  既有 Tool/Session 未变更。共享角色权限、已有 Deny、桶公开策略和 KMS 限制仍需
  操作方知悉；策略成功绑定不代表已证明云端文件读写成功。

实现评审检查稳定桶策略名、账号/地域/信任核验、精确对象前缀、增量幂等/并发、
安全失败、超时/取消及旧 CLI 兼容。未引入已有策略覆盖或全对象权限。全量/类型
门禁不能表述为通过，云端验收与本地实现仍然独立。

### 已授权的发布与云端验收

2026-10-12 对齐未变化的 `superops/main`，实现提交 `267705ef` 已推送到
`polaris/czh/studio-mpa-tos-iam-role`。同步后再次通过相关 Python 754 个用例、
Node 1,377 个及 Vitest 73 个用例；pre-commit、i18n 和前端产物检查通过。
前述全量基线阻塞仍然存在。

仅更新现有 Studio 代码包至 V42，环境变量哈希和品牌配置保持不变。wheel 中七个
生产源码文件及全部 WebUI 产物与工作区匹配，远程入口 JS/CSS/logo 哈希与本地
产物匹配。wheel SHA256：
`023bf085371cdc7c285b5e60bfcb2dd08e390c1935b7a995475c82c47b925a14`。
本次仅发布 Studio，未重新构建 Runtime/Worker 镜像。

远程 Studio 可选桶由未过滤的 18 个收窄为 4 个平台前缀桶，并拒绝旧草稿的
`agentkit-demo`。选 `agentkit-platform-2112682748` 创建测试 MPA
`role-tos-e2e-20261012-a`，未填写 TOS AK/SK。
Runtime `r-yex3bbopvkwqejues1lc` 达到 Ready，`/readiness` 返回 200。
Worker `t-yex3bb51xcwqejuen9oc` 达到 Ready，实际 Role 为
`IDRoleForArkClawShareAgent`，挂载模式为 `TOS_CREDENTIAL_TYPE_IAM_ROLE`，
没有 Credentials，读写目录为 `/data/output`，基础挂载路径符合预期。
IAM 回读确认精确桶/会话对象前缀的自定义策略已绑定。角色原本已有平台桶系统
策略，增量协调不会收窄既有权限。所选桶没有公开桶策略。

从远程 Studio 提交两段会话，均实际调用沙箱执行命令。GetSession 回读确认分别
挂载到 `/sandbox-session/tool-{tool_id}/session-{user_session_id}/`。
两段会话各写入同名 `role-tos-e2e.txt`，内容为不同 A/B 标记；第二段起初没有该
文件。账号侧独立 TOS 读取（没有账号侧写入）确认两个对象均持久化，B 写入后
A 内容未变。A 的沙箱结果、TOS 对象和浏览器下载文件 SHA256 均为
`e762fa20c53dd7394b3f89af8e084e42d486a8e241fa37d68acbd695a17b82a7`；
B 的沙箱结果和 TOS 对象 SHA256 均为
`0d797e5173d581880100a21f25a7e00f4990d82b440c4f01f01d78e8776b1e6e`。
浏览器下载事件等待在 45 秒后超时，但下载随后完成，已核验本地字节；不是接口
失败。该镜像的 `/ready?scope=execution` 返回 404，执行证明来自实际命令和对象
读取，不来自这个就绪接口。

测试 MPA 和两个输出对象保留供查看，既有 Tool/Session 未修改，仓库中没有残留
探索文件。此次验收不覆盖收窄角色既有权限、KMS 加密桶、显式 Deny、独立身份
或真实业务渠道消息交付。

### 官方上游 PR 准备

用户随后要求向 `volcengine/veadk-python:main` 提 PR。原 fork 分支的共同祖先会让
PR 夹带无关历史，因此将两个功能/证据提交迁移到官方 `main` 的 `812faadf`，使用
独立分支 `czh/studio-mpa-tos-iam-role-upstream`。唯一业务源码冲突是导入语句：
同时保留官方 `resolve_model_key` 和 TOS IAM ensure。前端生成物冲突通过官方
基线源码重新构建解决，没有选择任一旧产物，也没有迁入无关 fork 提交。

两个 TOS 授权顺序用例最初失败，是因为模拟云没有提供官方新增的 Ark Key 发现
依赖。仅在这两个用例中隔离该依赖，并断言它以正确 profile/cloud 被 await；
保留授权先于 identity、错误传播等全部断言，随后 2/2 通过。未为测试修改生产逻辑。

官方基线验证使用 Python 3.12.12：相关 Python 872 个用例通过，Node 1,377 个及
Vitest 75 个用例通过；前端构建、i18n、产物、仓库固定版本 Ruff 0.11.12 和
pre-commit 通过。相对官方 main 的可执行增量行覆盖率为 100%（Python 102/102、
TS 10/10），使用 coverage.py XML 和 Istanbul Clover XML 解析。聚焦单测修复
遵循 bits-unit-test-gen Step1–7；TOS 编排覆盖新增可执行行 5/5，utree flush 已执行。

官方全量回归已完成：6,950 通过、16 失败、2 收集错误、59 跳过、4 xfailed、
6 subtests 通过。使用相同解释器，在隔离的官方 main 归档复现六个 Harness
失败和两个 self-host 收集错误（64 通过），原因是缺少可选 `llama_index`/
`anthropic`。十个 Codex runtime 失败也在该归档复现，缺少可选 `openai_codex`。
15 个历史 SDK 签名 Pyright 错误在官方 main 原始 `mpa_tool.py` 上同样复现。
这些门禁不能表述为全绿。

上文 V42 云端证据属于原 fork 实现。本次官方基线迁移没有重新部署或运行浏览器/
云端 E2E；保留官方模型 Key 行为，不据此推断该行为已在 V42 执行。
原 fork PR 和云资源均保持不变。
