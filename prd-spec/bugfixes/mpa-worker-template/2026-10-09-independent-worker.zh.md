# 不依赖旧账号模板的 Worker 创建

[English](2026-10-09-independent-worker.md)

- 变更 ID：`mpa-worker-template`
- 创建/修订：2026-10-09
- 状态：implemented
- 契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。

## 背景与证据

Studio 内置 Worker 配置引用旧账号中的 Tool。新部署账号无法读取该 Tool：创建在 `get_reference_worker` 失败，尚未调用 `CreateTool`。Worker 镜像已显式配置。`worker.py` 只从引用模板复制环境设置；命令、资源、角色与网络由编排器生成。固定 Worker 源码版本 `81f3496` 的 `scripts/run.sh` 提供启动默认值，无需引用 Tool。

## 目标、非目标与场景

让新账号使用镜像和显式启动配置创建 Worker，同时兼容可选模板引用和已有 Worker。不修改镜像、IAM/网络、Runtime 聊天、前端，也不自动修改已有 Tool。镜像仓库访问仍是独立前置条件。

- 新 Studio 创建不读取旧模板，直接到达 `CreateTool`。
- CLI 配置可以显式继承有权限访问的 Tool 环境，显式设置优先。
- 显式引用不存在仍失败；结果不确定的创建重试保留原请求和 token。

## 需求与设计

- **FR-1：** 删除内置 `reference-id`。将不含密钥的 `PORT`、Worker 端口、headless/minimal 模式、workspace/data/runtime/sidecar 根目录及技能空间基础目录显式固定为该镜像的默认值。
- **FR-2：** 新增可选 `managed.worker.env: dict[str, str]`，默认空。服务端解析完整 `${ENV_NAME}` 引用。拒绝非法大写环境变量名、智能体/Runtime/Tool/技能空间绑定、继承的渠道/Runtime 凭据以及控制库连接地址。`existing-id` 携带非空 env 时失败，避免静默忽略。
- **FR-3：** 按已过滤模板环境、显式 env、生成的 `MPA_AGENT_ID` 顺序合并。不修改配置对象和模板响应。显式引用失败不回退为空环境。
- **FR-4：** 保留排序请求哈希、ClientToken、归属校验、取消和有界重试。未完成请求的显式 env 改变时报告配置冲突。环境值不写入部署记录，也不出现在配置摘要、repr 或错误响应中。

已有镜像契约支持按会话传入模型凭据；Studio 不复制旧模型密钥。额外运维配置通过 Worker env 和服务端密钥引用提供。不新增依赖、云 API、权限、任务表结构或前端产物。新配置契约由 Studio 组件维护，Runtime 部署引用该契约。非托管旧创建逻辑不变。

## 任务与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1 | T-1：修改内置配置并补回归 | AC-1：新账号使用镜像创建时跳过模板读取，提交显式启动配置 |
| FR-2 | T-2：配置结构/解析及安全校验测试 | AC-2：密钥引用可解析；非法/保留字段及已有 Worker env 失败且不暴露值 |
| FR-3 | T-3：请求合并与兼容测试 | AC-3：显式值优先，智能体绑定由编排器生成，缺失显式模板仍失败 |
| FR-4 | T-4：重试/不可变测试及审查 | AC-4：相同请求重试 token 不变；修改 env 失败；注册记录/摘要/repr 不含环境值 |

## 风险与恢复

默认值覆盖固定镜像；自定义镜像可能需要显式 env。不自动执行云创建冒烟。已有 Tool ID 仍是绑定依据，不重命名/更新。尚未写入 Worker 创建意图就失败的任务，可重启 Studio 后以同一智能体 ID 重试。已发出创建且哈希改变的任务必须保留原配置；禁止重置意图绕过防重复保护。

## 审查与验证记录

未提供 review-spec，直接审查通过了配置优先级、密钥处理、账号边界、部分失败、兼容性及双语一致性。2026-10-09 用户以“帮我改”批准移除固定旧模板并显式配置，在实现前记录。

验证范围：`ef0ad519` 加本次 Worker 修改及此前未提交的账号/IAM/网络/APIG 修复。必需命令：配置/Worker 定向测试、托管部署回归、修改文件 Ruff/Pyright、定向 pre-commit、双语/链接/空白检查。真实云创建：`not_run`；代码和模拟请求不能证明镜像拉取权限或平台就绪。浏览器/前端检查：`not_applicable`，无 UI/API 改动。执行后补充结果。

### 已执行检查（2026-10-09）

- 实现前 `fail`：配置/Worker 回归复现固定旧模板和缺少 env 支持（5 failed、94 passed）。
- `pass`：`uv run --extra dev pytest tests/integrations/mpa_managed/test_config.py tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker_metadata.py -q --tb=short` — 152 passed。
- `pass`：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 594 passed、5 条已有弃用警告；覆盖最终模板过滤及未完成 env 恢复。
- `pass`：对 managed 源码/测试目录的 `config.py`、`worker.py`、`studio_profile.py`、`test_config.py`、`test_worker.py` 执行 `uvx --from ruff==0.11.12 ruff check` 和 `uvx pyright --pythonpath .venv/bin/python` — 零错误。
- `pass`：对上述五个 Python 文件及八个修改文档执行 `uv run --extra dev pre-commit run --files` — Ruff 和硬编码密钥检测通过。YAML 钩子 `not_applicable`（未修改 YAML）。
- `pass`：双语标识/相对链接及 `git diff --check`。直接实现审查无阻塞项：模拟新账号请求不读取模板、显式覆盖/不可变性、绑定/控制库地址过滤、安全密钥引用及未完成 token 保护。AC-1 至 AC-4 通过模拟请求验收。
- `not_run`：真实镜像拉取/容器启动及全量无关 SDK 回归。隔离托管测试集覆盖受影响契约；验证没有创建云资源。`not_applicable`：前端构建/浏览器、生成产物及运行进程冒烟（未修改聊天/前端/镜像代码）。完整 all-files 提交检查等待另行授权提交。

T-1 至 T-4 完成，无已约定实现范围延期；真实平台就绪仍属于运维验证限制。重启本地 Studio，以同一智能体 ID 重试尚未生成 Worker 创建意图的任务。

启动默认值后续修订：[2026-10-09-worker-image-defaults](2026-10-09-worker-image-defaults.zh.md) 替代 FR-1/AC-1 中内置 env 显式注入的选择。上述初次验证为历史证据，其余契约保留。
