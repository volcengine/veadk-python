# MPA 创建最大实例数与错误高亮

[English](2026-10-13-max-instance-input.md)

- Change ID：`mpa-create-scaling`
- 创建/修订：2026-10-13
- 状态：implemented
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-21

## 证据与范围

基本信息步骤目前仅有名称/描述。受管 Runtime 已支持 `max_instance` 并映射为 AgentKit `MaxInstance`，内置配置当前为 1。请求/task/runner 尚无本次创建最大实例数。名称可用性错误以普通正文段落展示，缺少现有红色错误容器强调。

FR-1：用 Studio 确认弹窗同款 danger/soft Alert 高亮现有重名提示，保留原本地化文案及 alert 语义。仅使用组件公开属性，不增加独立 CSS/图标体系。
FR-2：基本信息增加可编辑数字字段“最大实例数”。新表单及新的可编辑草稿默认 20，接受正安全整数，步骤切换/配置加载期间保留编辑。下一步/提交前拒绝空、0、负数和小数。服务端拒绝无效整数类型，含布尔、数字字符串、小数，以及小于配置最小实例数的值。不改变最小实例数/单实例并发字段。最大值 20 是扩容上限，不代表启动 20 个实例。
FR-3：显式 `maxInstance` 贯穿浏览器草稿、POST、SQLite 请求身份及 runner stdin，在准备部署前应用到受管 Runtime 配置，复用现有 `MaxInstance` 映射及 Runtime 模板快照。已提交任务不能修改；新建另一请求重置为 20。重试改变数值须与原指纹冲突。省略/null 不加入旧指纹，保留旧配置行为；已提交旧草稿不升级，也不显示虚构的 20。

不修改已部署 Runtime、通用创建、最小实例数、单实例并发、镜像、资源清理或提供商适配。不授权真实云创建/扩容。

## 设计、文件与契约评估

复用创建弹窗现有数字字段排布及 StudioConfirmDialog 使用的 danger/soft Alert。数字输入保留文本编辑缓冲，允许空/输入过程，同时以数字保存规范草稿值。可选 API 字段 `maxInstance` 为严格正整数。新增小型 scaling 配置函数，由 BFF（受理前校验）及 runner（实际部署）共同使用；已有 YAML/CLI Runtime 默认值不变。任务持久化固定数值，仅存在时传入 stdin。保留取消/过期响应锁、原步骤导航及旧保存输入。

文件：MpaCreateDialog/API 类型/文案、授权创建请求、managed config/tasks/runner、定向前端/Python 回归、双语 PRD/spec/frontend 文档及 WebUI 发布资源。复用 service/runtime 映射，测试真正发出的 CreateRuntime/update 设置，不增加第二套映射。国内及 BytePlus MPA 共用该输入，通用智能体仍走原独立流程。无需数据库 schema 迁移。

## 任务、测试与验收

- T-1 / FR-1 / AC-1：先写 React 重名 danger/soft Alert 可见性失败测试；真实浏览器确认红色高亮及可访问文字。
- T-2 / FR-2 / AC-2：新建 20、可编辑整数、无效数值、步骤/配置响应、恢复草稿及旧已提交请求测试。
- T-3 / FR-3 / AC-3：BFF 校验、任务幂等/stdin、runner 及真实 Runtime Payload 断言；保留旧请求指纹和配置默认。
- T-4 / AC-4：先定向再 managed 部署回归、改动 Python Ruff/Pyright、前端全测/build/国际化/资源、浏览器正常/错误/重试/键盘/窄屏、脱敏密钥扫描及双语文档检查。

## 审查、风险与授权

`review-spec` 不可用，直接审查确认职责、可复用 UI 基准、可选字段兼容及通用流程隔离。用户于 2026-10-13 通过“按此方案实施（推荐）”批准具体方案。直接审查完成，无设计阻塞，可在该范围实现和编写回归测试。提供商额度/最大限制仍由 AgentKit 校验，不新增未文档化配额保证。任务快照防止重试静默更换扩容上限。实现前验证为 not_run；不授权提交、推送、重启、部署或云修改。

## 实现与验证 — 2026-10-13

范围：基于 `0dd3907d` 的工作区差异，仅含 FR-1–FR-3、对应测试/文档和 WebUI 产物。T-1–T-4 与 AC-1–AC-4 已完成。直接实现审查确认数值传到实际 CreateRuntime/update Payload、配置副本独立、任务身份不可变、服务端严格校验，且通用创建路由未改变。无遗留阻塞。

先回归后实现的证据：修改生产代码前，定向 Python 为 13 failed / 6 passed；React 创建测试为 7 failed / 47 passed。失败覆盖当时缺失的 UI/API/实例数行为。最终结果：

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| 定向 Python | pass | 20 项；严格类型、配置最小值、省略/null 兼容、子进程 stdin、幂等重试、runner 与实际 Runtime Payload。 |
| Managed/部署集成回归 | pass | 两个 worker 共 998 项；外部服务使用模拟，排除 smoke 标记。 |
| 前端测试 | pass | 1,389 项 Node、95 项 React，其中 MPA 创建 57 项；已有类型区分、删除、取消覆盖仍通过。 |
| Build / 国际化 / 资源引用 | pass | 应用与集成 widget 均重建；2 个语言 / 21 个 namespace 一致；113 个发布文件 / 350 个引用核验。现有分包大小/依赖警告不阻塞。 |
| 改动 Python Ruff / 格式 / Pyright | pass | 五个文件；Ruff 使用本仓库 pre-commit 的 0.11.12 版本。Pyright 使用本仓库 Python，0 错误 / 0 警告。因本地未安装检查工具，使用临时 `uvx`，未改全局配置。 |
| 真实 Chromium UI | pass | 隔离临时页面中的真实 React 弹窗，API 全为模拟。检查桌面/390×844 窄屏、默认 20、数字校验、键盘增量、步骤保留、数字提交、失败请求只读、新请求重置、BytePlus 手动 OV、旧字段省略，以及预检查/任务阶段重名高亮。完整中文错误可换行，无横向溢出。 |
| 密钥扫描 / 文档 / 空白 | pass | 按本仓库 Gitleaks 规则扫描变更文件并脱敏输出；审查双语标识符/数值限制/命令/相对链接；`git diff --check`。 |
| 真实云 / Codex smoke / sidecar coverage | not_applicable | 未改变云操作或 harness/sidecar 行为，未授权真实创建。未实测提供商额度/扩容。 |
| 提交 / pre-commit / 推送 / 重启 | not_run | 未请求或授权。未来提交前须同步目标基线并执行要求的 pre-commit/单元测试。 |

探索性未固定版本的 `uvx ruff check` 使用了 Ruff 0.17.0，在其扩展规则下 fail（17 项）。这不是仓库配置的检查版本；固定 0.11.12 的 check/format 均通过。未修改无关规则或生产代码来隐藏结果。

已执行命令：

```bash
uv run --extra dev pytest tests/integrations/mpa_managed/test_creation_scaling.py -q --no-cov
uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke" tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/integrations/test_mpa_tool.py tests/integrations/test_mpa_skill_space.py tests/integrations/test_ve_faas_deploy_image_key_auth.py -q --no-cov
uvx --from ruff==0.11.12 ruff check frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
uvx --from ruff==0.11.12 ruff format --check frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
uvx pyright --pythonpath .venv/bin/python frontend/server/mpa_creation.py veadk/integrations/mpa/managed/config.py veadk/integrations/mpa/managed/runner.py veadk/integrations/mpa/managed/tasks.py tests/integrations/mpa_managed/test_creation_scaling.py
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run check:i18n
npm --prefix frontend run test:webui-assets
git diff --check
```
