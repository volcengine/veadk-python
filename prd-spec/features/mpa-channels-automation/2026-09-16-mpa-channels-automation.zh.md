# 自动化中的 MPA 消息渠道

[English](2026-09-16-mpa-channels-automation.md)

- 变更 ID：`mpa-channels-automation`
- 创建／修订日期：2026-09-16
- 状态：implemented
- 组件：[MPA 消息渠道](../../../specs/mpa-channels/README.zh.md)
- 基线：`1263a268`；分支：`feat/mpa-channels-automation`

## 背景与范围

`AgentWorkspace.tsx` 当前在 MPA 智能体详情内挂载 `RuntimeChannels`。自动化已将飞书机器人创建和网站集成归入消息渠道。`getRuntimes` 支持授权范围、`agentCategory=mpa`、地域和游标分页。`DeploymentSelect` 已支持搜索、键盘导航和分页。

将现有管理流程移至自动化，让用户在统一入口选择已有 MPA 智能体。保留飞书机器人创建与网站集成卡片。不创建或部署 Runtime，不修改渠道 API、不迁移绑定、不改变权限、不修改 MPA 后端行为。

## 需求与场景

- FR-1：消息渠道增加并列的 `MPA智能体消息渠道` 卡片（`mpa-channels`）。打开后展示返回操作、页面标题及可搜索的 MPA Runtime 选择器。移除智能体详情中的原栏目。
- FR-2：使用 `agentCategory: mpa`、授权 Runtime 范围及全部地域调用 `getRuntimes`。显式分页，不丢弃后续结果。拒绝明确非 MPA 的记录；只有请求已明确筛选 MPA 时才接受缺少分类的记录。以地域和 Runtime ID 共同标识选项，名称只显示一次，下方显示描述和创建者／创建时间；选中目标的信息仍保留地域和 ID。用户明确选择后才挂载渠道页面。
- FR-3：复用 `RuntimeChannels` 的飞书、企微、钉钉及极速／手动流程。以地域和 Runtime ID 为面板 key；切换后卸载旧面板，取消轮询／SDK 工作，清理临时凭据并忽略迟到结果。已有持久绑定保留。取消前端工作不撤销服务端已经接受的注册。
- FR-4：仅 Studio admin/super_admin 可进入管理；其他角色显示权限说明，不请求列表和渠道接口。后端原有鉴权仍为最终权限边界。请求失败、空结果、加载、搜索无匹配、Runtime 能力不支持分别展示；错误可重试。分页失败保留已有选项和当前绑定面板。
- FR-5：遵循当前自动化布局、语义颜色、自绘 SVG 图标及现有搜索／选择交互。覆盖键盘／输入法、长名称和窄窗口。完整支持两种语言。

## 设计与契约影响

在 `frontend/src/automations/` 新增独立定义和页面，接入类型联合、注册表、目录图标和 App 路由。App 传入角色及 Runtime 范围。复用 `DeploymentSelect`，Studio 已加载其全局样式。页面内加载列表，通过 AbortController 和请求身份防止过期写入。后续页按需加载，并提供显式加载更多／重试操作，包括搜索无匹配时。搜索已加载的名称、ID、地域，并说明可能仍有未加载的页。不自动选择或触发授权。

页面负责导航、列表、选择；`RuntimeChannels` 继续负责渠道状态，增加可选标题开关避免重复页标题。选择不写入浏览器存储。角色／范围变化通过子组件 key 重置页面。选择器不请求密钥。不影响 Python API、部署参数、数据库及事件契约。同步更新组件两种语言的导航与 CON-14。原详情选项为组件内状态，无公开深链接契约。

## 任务与验收

| 任务 | 需求 | 验收／验证 |
| --- | --- | --- |
| T-1 | FR-1、FR-5 | AC-1：双语卡片、正确路由／返回、移除旧入口；目录／导航测试 |
| T-2 | FR-2、FR-4 | AC-2：限定范围的 MPA 分页／搜索、明确选择、加载／空／错误／重试／权限测试 |
| T-3 | FR-3 | AC-3：真实渠道组件重新挂载，旧请求不影响新 Runtime；现有渠道回归测试 |
| T-4 | FR-5 | AC-4：浏览器验证正常流程、取消、键盘／输入法及 390px 布局；国际化、构建、产物检查 |
| T-5 | 全部 | AC-5：双语契约和前端 README 同步；差异审查与密钥扫描 |

影响文件：自动化类型／注册表／新增定义／页面／样式／图标；`Applications.tsx`、`App.tsx`、`AgentWorkspace.tsx`、`RuntimeChannels.tsx`；两种自动化语言文件；定向测试；`frontend/README.md`；MPA 契约；生成的 `veadk/webui` 产物。

命令：定向 Vitest（`mpaChannelsAutomation.test.tsx`、`runtimeChannels.test.tsx`）、`npm --prefix frontend test`、`npm --prefix frontend run check:i18n`、`npm --prefix frontend run build`、`npm --prefix frontend run test:webui-assets`、`git diff --check`、仓库 pre-commit 密钥扫描。浏览器检查使用隔离的模拟 Runtime／渠道 API，不使用真实渠道凭据。

## 风险与评审

搜索覆盖已加载页；显式加载更多避免静默遗漏后续智能体。选中后由已有组件检测 Runtime 可达性／能力。切换会取消前端操作，但不会回滚已接受的后端操作。真实渠道连通性不属于本次导航变更，模拟检查不能证明真实连通性。

2026-09-16：用户认可上述迁移方案，要求独立分支，随后明确要求推送并开始开发。编辑前已推送分支，原分支保留。直接设计评审覆盖范围、双语一致性、兼容性、权限、分页、过期响应、密钥及可测性，无阻塞项。仓库／用户技能路径未找到引用的 frontend-design、ui-ux-pro-max 和 review-spec，直接依据 `frontend/SPEC.md` 和仓库评审标准审查。不引入新设计体系或依赖。

## 验证记录

执行日期：2026-09-16。验证范围：`feat/mpa-channels-automation` 相对 `1263a268` 的本地差异，包含新增文件及重建 WebUI 产物。T-1 至 T-5、AC-1 至 AC-5 均已完成。

| 检查 | 结果 | 证据 |
| --- | --- | --- |
| 先写选择器测试 | fail（预期） | 实施前新组件不存在，导入失败。 |
| `./frontend/node_modules/.bin/vitest run --root frontend tests/mpaChannelsAutomation.test.tsx tests/runtimeChannels.test.tsx --maxWorkers 1` | pass | 62 项；覆盖真实渠道组件重新挂载、角色／范围变化、轮询及迟到 SDK 凭据。 |
| `npm --prefix frontend test` | pass | 1207 项；两条旧详情渠道测试合并为一条迁移断言。另一条旧栏目联合类型断言初次失败，已按批准的导航更新。 |
| `node --test frontend/tests/agentWorkspace.test.mjs frontend/tests/applications.test.mjs` | pass | 最终格式化／清理后 38 项通过。 |
| `npm --prefix frontend run check:i18n` | pass | 2 种语言、21 个命名空间。 |
| `npm --prefix frontend run build` | pass | TypeScript 及应用／挂件两次构建通过；保留原有大分块提示。 |
| `npm --prefix frontend run test:webui-assets` | pass | 104 个产物、248 个引用。 |
| 隔离模拟 API 浏览器验证 | pass | 目录卡片、明确选择、中文搜索及键盘选择、返回消息渠道分类、切换目标清理二维码、手动绑定成功、分页、不支持镜像、加载／空／失败／重试／权限状态。在 390×844 下，body 宽 390，内容 client/scroll 宽均为 347。使用正式样式，未加载组件预览主题变量。 |
| 输入法组合输入 | pass | 单元事件测试验证组合输入期间 Enter 不会选择 Runtime；浏览器覆盖中文输入。 |
| `uv run --extra dev pre-commit run --all-files` | pass | Ruff 检查／格式及仓库 Gitleaks。另用明确 `--files` 扫描新增源码、测试、PRD 也通过（这些文件无 Python，Python 钩子正确跳过）。 |
| 额外默认 Gitleaks 扫描，包含变更产物／测试 | fail（已审查为误报） | 脱敏扫描 83 个修改／新增文件；唯一 generic-api-key 命中为 MarkdownPromptEditor 中 Lexical 选区的 anchor/focus key 表达式。完全相同表达式已存在于基线。未削弱规则；审查未发现凭据。 |
| `git diff --check -- ':!veadk/webui'` | pass | 源码／文档／测试空白检查通过。完整差异检查提示生成依赖模板字符串中的空白；基线和当前挂件均有 36 行，行尾上下文完全一致。保留生成代码语义。 |
| 双语标识及相对链接 | pass | FR/T/AC 标识一致，成对 PRD／契约链接全部存在。 |
| Python／Runtime／真实云／渠道测试 | not_applicable / not_run | 无 Python 或后端契约变更。模拟 API 浏览器检查不证明真实渠道投递；未执行真实云或渠道操作。 |

最终审查未发现目标身份、分类过滤、权限、分页、取消、凭据生命周期和导航的阻塞缺陷。现有渠道绑定行为继续由 RuntimeChannels 负责。共享 DeploymentSelect 显式导入现有 ProjectPreview 样式。临时浏览器测试文件、预览服务及标签页已清理。已按要求推送分支基线；开发修改保留为未提交状态，供审阅。


### 选项详情调整（2026-09-16）

用户要求将选项内重复的名称替换为描述、创建者和创建时间。属于 FR-2／FR-5 的已批准调整：标题仅保留一次，第二行显示描述，第三行显示创建者／时间。缺失或非法值使用本地化占位，有效时间按当前语言格式化。选中目标仍显示地域／ID。DeploymentSelectOption 增加可选 `metadata` 字符串，既有调用不变；提示包含全部选项信息。不改变 API、绑定、权限或存储。直接评审无契约／安全阻塞。新增内容及缺省值回归，随后重跑前端测试、国际化、构建／产物及隔离浏览器布局检查。编辑前本次检查：not_run。

本次调整验证（2026-09-16）：先写测试时 2 失败／13 通过，实现后渠道／自动化 64 项通过；前端全量 1207 项通过；国际化、应用／挂件构建和 104 文件／248 引用产物检查通过。浏览器验证三层信息、本地化日期、缺省占位、长描述和创建者换行。在 390×844 下，body 宽 390，选项 client/scroll 宽均为 292；完整信息可在提示中查看。未提供 metadata 的现有选项保留原布局。未操作真实 Runtime／渠道。临时文件／预览服务／标签页已清理。

### 简洁创建信息与 Runtime 信息（2026-09-16）

用户进一步指定选项页脚为“创建者姓名（缺失显示未知创建者） | 相对创建时间”，不显示字段前缀，并要求恢复各选项中的地域和 Runtime ID。保留名称和描述行，其后依次显示简洁创建信息与地域／Runtime ID。复用 `formatRelativeTimeLabel`，缺失或非法时间显示破折号。此决定替代前文绝对时间方案。现有 metadata 字符串增加换行，共享样式保留该换行；未提供 metadata 的调用方不变。同步 FR-2／FR-5 与 CON-14。用户请求授权此展示细化；评审确认不影响 API、权限、状态或凭据。验证待完成。

简洁页脚验证（2026-09-16）：先写回归时 2 失败／13 通过；最终渠道／自动化 64 项、前端全量 1207 项通过，国际化／构建／产物通过。浏览器确认“未知创建者 | 14 小时前”及单独一行的地域／Runtime ID。390×844 下 body 宽 390，两个选项 client/scroll 宽均为 292。缺失时间显示破折号，相对时间复用已有公共方法。临时预览文件、服务和标签页已清理。修改仍未提交。
