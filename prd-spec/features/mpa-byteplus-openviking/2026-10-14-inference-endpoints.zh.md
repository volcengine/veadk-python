# BytePlus OV 推理凭据

[English](2026-10-14-inference-endpoints.md)

变更 ID：`mpa-byteplus-ov-inference-endpoints`。日期：2026-10-14。状态：implemented；真实联调待验证。
前置设计：[自动创建](2026-10-14-automatic-creation.zh.md)。
契约：[CON-18](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景与批准范围

用户提供的海外脚本支持普通推理凭据，每个模型传 `Source=volcengine`、`ApiKey` 和 `EndpointID`。初次本地接入只实现 Coding Plan。用户明确要求取消 Coding Plan，改用普通 API Key 加推理接入点，并要求先使用国内接入点标识作为海外默认值尝试。本次批准替代前置设计的凭据决策，个人版及 Runtime 单独适配范围不变。

## 目标、场景与要求

- FR-1：BytePlus 自动创建复用已有 MPA 创建流程解析的普通模型 Key，包括通过部署凭据发现。不读取 `OV_MODEL_API_KEY`，不新增浏览器密钥，不回退到 Coding Plan/AgentPlan。
- FR-2：创建个人版库，顶层及模型凭据均使用 `Source=volcengine`。保留海外模型名 `seed-2-0-lite` 和 `skylark-embedding-vision`，不传 ModelVersion。EndpointID 默认值为 `doubao-seed-2-0-lite-260428` 和 `doubao-embedding-vision-251215`；这是用户指定的试用值，尚未在海外验证。服务端 `OV_VLM_ENDPOINT_ID` 和 `OV_EMBEDDING_ENDPOINT_ID` 可覆盖。每项须为 1–128 位 ASCII 字母、数字、连字符、下划线或点，且以字母或数字开头。显式空值或非法值在云资源变更前失败，错误不回显输入值。
- FR-3：在现有 OV 意图中保存非密钥 Source/EndpointID。重试时接入点改变或已有 Coding Plan 意图，按配置冲突失败，不另建或修改库。此前仅缺少 Key、尚未记录 OV 意图的失败可以重试。创建结果未知、取消、保留资源、锁和回读校验保持不变。
- FR-4：国内模型参数、已提交手动任务、通用智能体及四个 OV Runtime 变量保持不变。不创建模型接入点，不修改 Runtime 记忆代码。
- FR-5：更新本地化界面和双语说明，解释复用推理凭据与可配置接入点，移除 Coding Plan 前置要求。布局和交互不变。

## 设计、影响文件与任务

T-1（FR-1/2）：managed/openviking.py 的专用 Key 解析替换为非密钥接入点解析；config.py 校验接入点，service.py 在变更资源前捕获并传入 ensure_openviking，使用已有流程取得的普通模型 Key。新增可选关键字参数兼容国内调用方。
T-2（FR-3/4）：保留意图比较和严格 Get 回读。不迁移已有 Coding Plan 库，其来源不能静默修改。仅捕获当前进程的接入点选择；重启后配置改变，与已记录意图不一致时安全失败。
T-3（FR-5）：更新语言包、managed README 双语、frontend README、CON-18 双语及生成的网页产物。
T-4：先测试，再运行 managed/startup 和前端回归、Ruff/Pyright、构建/国际化/产物检查、浏览器验证和密钥扫描。测试不产生真实云端副作用。

## 评审与验收

用户批准：2026-10-14 明确要求取消 Coding Plan 并沿用国内接入点默认值。直接设计评审（review-spec 不可用）：已审查范围、脚本参数、凭据区分、安全失败、重试兼容及双语一致性，无设计阻塞。不推测资源 ID、密钥或账号权限。

- AC-1：没有 OV_MODEL_API_KEY 时，默认 BytePlus auto 配置成功；创建请求包含解析后的普通 Key 及两个接入点。国内既有回归保持通过。
- AC-2：覆盖覆盖值、空/非法接入点、改变接入点后的重试、旧 Coding Plan 意图、远端接入点不符、取消及创建结果未知；错误及注册库不含模型 Key。
- AC-3：界面不再要求 Coding Plan；测试/构建及定向浏览器验证通过。无新增输入项，不改变 IME 或键盘行为。
- AC-4：双语文档、契约及生成产物一致；在下方记录实际检查及未验证的云端范围。

## 风险与验证记录

用户指定的默认接入点可能在海外账号不存在或该 Key 无权调用。服务端拒绝须明确报错；管理员可配置实际接入点，并仅在未创建冲突库时重试。本实现不证明 Runtime 支持个人用户和海外数据面。真实建库/记忆测试为 not_run：本次代码变更未授权云端创建，Runtime 适配是独立任务。提交/推送不在本次范围内。

2026-10-14：实现检查待执行；范围为当前分支未提交的 BytePlus OV 改动。保留无关的 contracts 迁移、OpenSpec 删除及 lockfile 修改。

## 验证结果（2026-10-14）

验证范围：基于 `2ffe6e14` 的当前未提交 BytePlus OV 修改；未提交、推送或部署云资源。

- pass：先写 OV 回归，实施前复现 14 项失败；实施后 OV 定向测试 52 项通过。
- pass：`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` — 1,004 项通过、4 项警告。按仓库建议使用两个 worker。新增 service 测试最初使用了错误的 Profile 构造方式和国内网络夹具；修正测试夹具后，完整受影响套件重跑通过。
- pass：`npm --prefix frontend test` — 1,389 项 Node 与 96 项 React 测试。
- pass：五个改动 Python 文件的 Ruff 0.11.12 检查/格式，以及使用 `.venv/bin/python` 的 Pyright — 0 错误/警告。
- pass：`npm --prefix frontend run build`、`run check:i18n`（2 个语言/21 个命名空间）、`run test:webui-assets`（113 个文件/350 个引用）、`git diff --check`。
- pass：真实 Chromium 加载实际弹窗，API 响应为模拟：普通 Key 文案、无 Coding Plan 要求、无手填密钥字段、接入点错误、同请求重试、旧手动恢复、国内文案、Escape 和 390px 视口。首次临时夹具漏导入组件主题；补齐夹具后重新执行浏览器检查。检查后移除临时页面及独立 Vite 服务。
- pass：双语需求标识/相对链接检查；已有无关 lockfile 哈希未变化。
- not_run：全仓库 Python 及 all-files pre-commit，因为范围是 MPA 集成及文案、没有提交请求；执行了受影响回归及完整前端门禁。Harness/Codex smoke 为 not_applicable：未改变 runtime/sidecar 契约。
- not_run：真实海外接入点调用、付费库创建及 Runtime 记忆联调。离线通过不能证明用户指定的默认 EndpointID 在海外有效。

- pass：`uv run --extra dev pre-commit run gitleaks --files <changed-existing-files>` — 覆盖源码、测试、文档及构建产物，未检测到密钥。
