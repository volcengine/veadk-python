# Studio MPA 三步创建

[English](2026-09-23-studio-mpa-three-step-creation.md)

- Change ID: `studio-mpa-three-step-creation`
- 创建/修订日期：2026-09-23
- 状态：已在本地实施并验证；尚未提交
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

`MpaCreateDialog` 目前把生成的智能体 ID、镜像、资源计划和提交按钮放在同一页，ID 可以编辑。托管创建使用已有 PostgreSQL 实例，管理员和共享登记库凭据从服务端环境变量读取；它为智能体创建独立业务库，但不创建 PostgreSQL 云实例。托管 Studio 流程尚无单次创建的 OpenViking 输入，尽管 MPA Runtime 支持 `OPENVIKING_URL` 和 `OPENVIKING_RESOURCE_ID`。

## 目标与非目标

将 ID 设为只读，创建分为智能体基础信息、已有 PostgreSQL 实例设置、OpenViking 设置三步，并加入用户提供的火山引擎控制台链接。确保提交的非密钥配置进入 Runtime 和任务重试流程，保留服务端管理的凭据与授权。创建云 PG 实例、浏览器保存密码/API Key、修改无关 CLI 或已有智能体均不在范围内。

## 场景与需求

- **FR-1：** 新打开弹窗时保持原有的 `mi-[0-9a-f]{24}` ID 格式。用户可以选择和复制，但不能编辑；重新打开和重试保留同一 ID。短暂回归期间形成的未提交 12 位草稿会依据不变的请求 UUID 扩展为 24 位；已提交的 ID 保持原样以便重试。托管平铺创建除 CLI 原有的 12 位 ID 外，也接受这个 Studio ID。
- **FR-2：** 第一步展示地域、ID、描述、镜像和资源计划；下一步进入 PostgreSQL，上一步返回且不提交，再下一步进入 OpenViking；只有第三步能开始创建。处理键盘、输入法、窄屏、无效值和缺失的服务端配置。
- **FR-3：** PostgreSQL 步骤链接到指定 RDS 列表，并允许填写已有实例的主机与端口。默认值来自授权后的服务端配置。后端在云资源写入前拒绝与管理员连接目标不一致的主机/端口；数据库凭据保留在服务端。
- **FR-4：** OpenViking 步骤链接到指定的上下文管理页，允许填写可选的 HTTPS 服务地址与资源 ID。所选值应用到新 Runtime；API Key 继续来自服务端配置或参考 Runtime。浏览器缓存和任务响应均不保存密钥。
- **FR-5：** 任务随请求 ID 持久化非密钥选项；响应丢失、重试或重新打开继续使用同一组值。没有新字段的既有任务和客户端保持原行为。

## 设计与契约影响

`GET /web/mpa-creation/config` 增加非密钥的 PostgreSQL 主机/端口默认值。`POST /web/mpa-creation/tasks` 增加可选 `pgHost`、`pgPort`、`openvikingUrl`、`openvikingResourceId`。服务端校验 URL 语法、端口范围、ID 长度和 PostgreSQL 管理员连接目标。现有任务 payload 持久化把非密钥字段交给子进程；子进程在复制的 profile 上覆盖 Runtime 环境变量。`AgentDatabaseProvisioner` 继续校验管理员与 Runtime 主机一致。OpenViking 字段为空时保留继承的 Runtime 设置。修改未完成任务的选项仍然冲突。API 仍接受智能体 ID，以兼容 CLI 和旧客户端。

权限继续使用智能体管理权限，账号和地域继续由服务端验证。不需要新依赖、数据库迁移、密钥存储或云厂商 API 调用。控制台链接不授予权限，也不证明网络可达。用户提供的 OpenViking 链接是示例资源页面，而不是服务接口地址。

## 实施任务

- **T-1：** 先加入三步、只读 ID、链接、校验及后端覆盖/安全的失败测试（`FR-1`–`FR-5`）。
- **T-2：** 加入本地化的三步 UI 和少量响应式样式（`FR-1`–`FR-4`）。
- **T-3：** 扩展类型化 API、后端校验、任务 payload 和 runner 的 profile 覆盖（`FR-3`–`FR-5`）。
- **T-4：** 更新双语组件契约和操作文档；运行相关测试、类型/样式检查、构建和浏览器检查（`FR-1`–`FR-5`）。

## 验收与验证

- **AC-1：** 表单中的 ID 不能修改；上一步/下一步保留输入且不发送 POST。
- **AC-2：** 两个控制台链接打开指定地址。完成校验后仅第三步可提交。
- **AC-3：** PG 目标不一致及无效 OpenViking 值在部署前失败；有效值进入 Runtime 环境且不修改密钥。
- **AC-4：** 相同身份与选项的重复请求复用任务；不同选项冲突。旧 payload 继续可用。
- **AC-5：** 前端测试/构建、定向 Python 测试、改动文件的 Ruff/Pyright、双语检查及真实浏览器检查通过。模拟测试不等于真实云部署。

## 风险、审查与交付记录

现有 profile 仍须指向所选 PG 实例，并提供可用的登录及管理员连接。向导不能建立私网连通性或创建 PG 实例。直接设计审查确认：把凭据放入当前任务 SQLite payload 将违反现有安全契约，因此继续由服务端管理凭据。OpenViking API Key 仍在服务端配置；仅填写地址/资源 ID 不会创建资源或授予权限。

2026-09-23 的直接设计与实现审查确认：POST 在创建任务前拒绝 PG 目标不一致及无效 OpenViking 设置。明确的 HTTP 400/422 拒绝会解锁表单供修改；无法确定服务端结果的网络失败则保留已提交的请求身份与选项，以便幂等重试。旧客户端不传新字段时沿用原创建路径。已核对双语文档与组件契约的字段、长度限制、链接和行为一致。用户审查发现 Studio 生成的 ID 被意外缩短；修正后恢复原有的 24 位后缀，并让平铺创建路径兼容该格式；CLI 自动生成的 ID 仍为 12 位。

当前未提交改动的验证结果：`npm --prefix frontend test` **pass**（1,305 项 Node 测试及 30 项 Vitest 测试）；`.venv/bin/pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` **pass**（284 项）；改动 Python 文件的 Ruff 检查/格式化 **pass**；使用 `.venv/bin/python` 的 Pyright **pass**（0 错误）；TypeScript `tsc --noEmit` **pass**；`npm --prefix frontend run build` **pass**；`npm --prefix frontend run test:webui-assets` **pass**（104 个文件、248 条内部引用）；`git diff --check` 与双语标识/成对文件检查 **pass**；基于 diff 的 Gitleaks 扫描 **pass**。本地浏览器预览对三步、两个控制台链接、只读 ID、窄屏和无效 OpenViking 输入的检查 **pass**；预览使用模拟配置，没有发起云端创建。真实云部署为 **not_run**，因为它会创建服务商资源。沙箱无法写全局 uv 缓存，`uv run --extra dev` 因此为 **blocked**；相应测试及检查改用仓库现有虚拟环境和缓存工具。由于没有提交请求，pre-commit 的 `--all-files` 为 **not_run**。

恢复 Studio 原有 ID 长度后，创建弹窗定向测试 **pass**（15 项，涵盖未提交草稿安全迁移和已提交 ID 保留），`.venv/bin/pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/cli/test_cli_mpa.py -q` **pass**（298 项），改动 Python 文件的 Ruff 检查/格式化 **pass**，TypeScript 检查 **pass**，重新构建 **pass**，打包资源 **pass**（104 个文件、248 条内部引用），双语 ID 契约检查 **pass**，`git diff --check` **pass**。前述完整前端测试在此次 ID 修正前运行；定向弹窗测试已覆盖该修正。真实部署仍为 **not_run**。
