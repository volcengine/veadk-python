# Studio MPA 名称创建流程

[English](2026-10-09-named-studio-creation.md)

- 变更 ID：`named-studio-creation`
- 创建/修订：2026-10-09
- 状态：approved；用户于 2026-10-09 确认，已实现；本地验证和部署状态见下文。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，重点涉及 CON-1、CON-3、CON-5、CON-6、CON-9 和 HTTP 请求体。

## 背景与范围

当前 Studio 弹窗生成并展示智能体 ID，提交可编辑的 Runtime/Worker 镜像字段。`frontend/server/mpa_creation.py` 要求提供 ID。托管 runner 把 ID 传给部署流程，`runtime.py` 用它作为新 Runtime 的 Name。内置 `studio_profile.py` 仍引用旧镜像。

本次按用户要求将这些技术输入替换为必填名称，由服务端生成稳定的智能体 ID，并使用镜像仓库 `agentkit-platform-2112682748-cn-beijing.cr.volces.com` 中已发布的 `mpa/mpa_agent:latest` 和 `mpa/mpa_codex_worker:latest` 创建新智能体。

现有智能体、数据库身份和 CLI 配置不在本次范围内。用户指定 Studio 的云端更新已获授权，作为独立交付步骤。复用弹窗布局、组件和其他资源步骤。实现本次变更不需要新增依赖、执行云端操作、变更账号权限或迁移数据。

## 需求与场景

- FR-1：基本信息显示可编辑的名称和描述，不显示智能体 ID 或镜像输入框。名称沿用 Studio Runtime 校验规则：4–64 个 ASCII 字母、数字、下划线或连字符，去除首尾空白。非法名称阻止向后导航和提交，服务端在部署前拒绝。
- FR-2：新浏览器请求包含 `name` 和 `requestId`，不包含 `agentId`、`runtimeImage`、`workerImage`。服务端根据可信 owner 和请求 UUID 派生 `mi-` 加 24 位十六进制字符的稳定 ID，随创建任务保存。不同 owner 或请求得到不同身份；响应丢失、重复提交、取消后重试均保持身份不变。
- FR-3：名称经过任务持久化和固定子进程协议，成为新 Runtime 的 `Name`。`MPA_AGENT_ID`、Worker 绑定、注册表键及其他资源身份仍使用生成的 ID。已注册 Runtime 保留原名称。
- FR-4：新的 Studio 请求使用服务端的两个 `latest` 镜像默认值。恢复未提交草稿时，不得暗中回传旧镜像覆盖项。已经提交的草稿/任务保留原请求和镜像选择，以安全重试。
- FR-5：为旧客户端和已提交草稿保留 API 的旧 `agentId` 及镜像字段。没有名称的旧请求保留原 Runtime 命名行为。CLI/YAML 镜像覆盖能力继续可用。不得放宽所有权检查或待完成请求的一致性检查。
- FR-6：保留取消、轮询、重试、提交后锁定、密钥排除、本地化和键盘/IME 行为。“新建智能体”产生新的名称草稿和请求 UUID。测试和产物不得含生产密钥。

有效新表单提交后，只创建一个任务，Runtime Name 为输入名称，生成的 ID 同时注入 Agent 和 Worker。POST 响应丢失后重试同一请求，不创建新身份。旧的已提交草稿恢复后重试，保持原操作。名称无效时不启动任何云写入。

## 设计与影响文件

1. 修改 `frontend/src/adk/mpaCreation.ts`、`frontend/src/ui/mpa-create/MpaCreateDialog.tsx` 和本地化文字。复用 `frontend/src/create/runtimeName.ts` 以及现有 ModalLayout、Button、Textarea。新请求显式移除隐藏字段；恢复已提交的旧草稿时保留原请求形状。
2. 在 `frontend/server/mpa_creation.py` 中增加名称校验，为新请求形状在服务端生成稳定 ID。省略未提供的旧可选字段，避免改变历史持久化请求的相等比较。
3. 通过 `managed/tasks.py`、`runner.py`、`service.py` 和 `runtime.py` 传递可选 Runtime 名称。名称参与持久化请求比较和待完成 Runtime 请求哈希。调和已有 Runtime 时保留其名称。
4. 仅将 `managed/studio_profile.py` 内置 Studio 镜像默认值改为已发布的 `/mpa/` 镜像，保留共享 CLI 镜像选择机制。
5. 同步双语组件契约、托管操作文档、前端文档和构建产物。HTTP 扩展保持向后兼容，无需更改数据库结构。

不采用“名称即智能体 ID”，因为用户名称不能成为所有权和数据库键。不采用每次重试重新随机生成 ID，因为这会破坏幂等性。owner/request 派生使用服务端可信身份，不采信浏览器传入的 owner。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1、FR-6 | T-1：先增加回归测试，再改 UI | AC-1：名称必填，旧输入框消失，加载/错误/IME/键盘状态可用 | 前端 MPA 弹窗测试及隔离模拟 API 的真实浏览器检查 |
| FR-2、FR-5 | T-2：扩展请求处理和恢复 | AC-2：owner/request 身份稳定，旧重试不变，输入改变产生冲突 | `tests/integrations/mpa_managed/` 的路由/任务测试 |
| FR-3 | T-3：传递 Runtime 名称 | AC-3：创建参数使用名称，身份绑定使用生成 ID，保留已有 Runtime 名称 | runner/service/runtime 测试 |
| FR-4 | T-4：更新内置默认值 | AC-4：两个镜像均为 `/mpa/<repository>:latest`，已提交任务保留选择 | profile/image/route 测试 |
| 全部 | T-5：同步文档和产物 | AC-5：双语契约一致，产物对应源码，无凭据 | test/build/i18n/assets、Ruff/Pyright、pre-commit、diff 审查 |

命令：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py`；`npm --prefix frontend test`；`npm --prefix frontend run build`；`npm --prefix frontend run check:i18n`；`npm --prefix frontend run test:webui-assets`；修改文件的 Ruff/Pyright；`uv run --extra dev pre-commit run --all-files`。有意义的新增可执行行增量覆盖率须超过 95%。按仓库门禁扩大回归。本次代码修改请求未授权真实云端创建，须与模拟检查分开报告。

## 风险、评审与交付记录

- `latest` 可变。更新仓库标签影响后续拉取，不更新现有运行中的智能体。不同时间的新创建可能使用不同镜像；本次不增加现有资源自动更新。
- 未提交旧草稿迁移不能恢复隐藏镜像覆盖项。已提交草稿兼容性和同 owner/request 重复请求行为需要显式测试。
- 2026-10-09 源码审查：已确认前端 ID 生成、路由必填字段、持久化精确请求比较、固定子进程协议和 Runtime Name 覆盖行为。设计在实现前已获批准；当前验证结果见下文。
- `review-spec` 不可用，直接执行同等契约、安全、兼容、可测性和双语审查。仓库引用的 UI 技能路径缺失，采用可用 frontend-design 指南及 Studio 自身组件/交互规范约束这次表单变更。
- 用户已要求实现并沿用 fork/PR 流程；用户已确认实现、更新指定 Studio 部署，并与 PR #21 使用同一分支。


## 验证与发布证据（2026-10-09）

范围：基于 `origin/main` `ef0ad51` 的 `czh/fix-mpa-tos-copy` 分支名称创建变更，与既有 TOS 文案修改一并交付到 PR #21。未新增依赖或数据结构迁移。

- `pass`：定向 Python 回归 481 项（`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -o addopts='' --cov=veadk.integrations.mpa.managed --cov=frontend.server.mpa_creation`）。覆盖率运行需移除仓库 Pydantic 警告过滤器的预加载，否则 pytest-cov 收集阶段会产生重复 Pydantic 类；不采集覆盖率时，标准 MPA 测试已通过（最后两个用例加入前为 457 项）。没有为采集覆盖率排除测试。
- `pass`：`npm --prefix frontend test`，1,377 项 Node 测试和 52 项组件测试，其中创建弹窗 35 项。覆盖必填/非法/去空白名称、删除字段、草稿迁移、旧请求重试、迟到响应、取消和输入法组合事件。
- `pass`：新增可执行行覆盖率 75/75（100%），Python 27/27、弹窗 48/48。纯类型和非独立可执行的调用参数行不单独作为覆盖率语句；runner/子进程协议及 Runtime 身份断言独立验证名称传递。
- `pass`：`npm --prefix frontend run build`、`check:i18n`（2 种语言、21 个命名空间）、`test:webui-assets`（113 个文件、350 个内部引用）。
- `pass`：修改的 Python 生产文件与新回归测试的 Ruff/Pyright，以及 pre-commit Ruff/格式化和密钥扫描。额外检查既有修改测试时，`test_service.py` 保留两个原有 Pyright 错误，已对照修改前文件确认；本次未引入新错误。
- `pass`：使用隔离模拟 API 的本地真实浏览器检查：空/非法名称阻止继续，合法名称和描述显示正确且无 ID/镜像输入框，Tab/Enter 导航可用，三步均可展示，模拟 503 展示错误并锁定已提交字段。390×844 窄屏可用，无横向溢出。捕获的 POST 包含名称/requestId，不含智能体 ID 或镜像覆盖项。组合输入、重试/取消另由自动化测试覆盖；未执行操作系统输入法会话或真实云端创建。
- `fail`（基线/环境）：排除显式启用 Codex/Pi smoke 的默认全量 Python 回归，6,239 项通过、19 项跳过、2 项预期失败、7 项失败、2 项收集错误。全部七项失败和两项错误均在修改前 `ae39492` 复现：六项 Harness 用例缺少可选 `llama_index` 依赖，两项 Sandbox 模块缺少 `anthropic`，artifact writer 的 MIME 断言在本机得到 `application/octet-stream` 而非 `text/markdown`。未改动基线子集为 108 项通过及相同失败/错误。本次未修改无关依赖或 MIME 行为。
- `pass`：已按授权更新既有 Studio 代码，稳定版本由 36 升为 37。首页返回 HTTP 200 并引用 `/assets/app/index-BGwZgNyo.js`；该线上文件返回 HTTP 200，SHA256 与已验证本地构建完全一致。既有 44 项环境变量发布前后的整体哈希一致。代码包内修改的后端文件也与本地源码逐字节一致。VeADK wheel SHA256：`f1413695218969f8a34765cc1f7392ae44ffea9971ddba96c5c84ce03f12ada3`。本次发布未创建新的 MPA Runtime。凭据未进入仓库或代码包，部署验证后删除临时副本。
- `not_run`：真实云端 MPA 创建及消息投递。本地测试、构建和浏览器证据不代表云端已采用代码或 Agent/Worker 已实际执行。

直接设计/实现审查覆盖双语一致性、owner 隔离的稳定身份、旧请求精确比较、隐藏草稿覆盖项、名称传递和已有资源保留。修改行为未发现尚未解决的问题。`latest` 仍可变；重试保存标签引用，不锁定不可变 digest。
