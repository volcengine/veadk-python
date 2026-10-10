# 使用 Worker 镜像默认值，移除重复 Tool 环境配置

[English](2026-10-09-worker-image-defaults.md)

- 变更 ID：`mpa-worker-image-defaults`
- 创建/修订：2026-10-09
- 状态：implemented
- 前序：[独立 Worker 创建](2026-10-09-independent-worker.zh.md)，仅修订其 FR-1/AC-1 的启动设置选择。
- 契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)；Runtime 部署继续引用该契约。

## 证据、目标与范围

固定 Worker 源码 `81f3496` 的 Dockerfile 定义 PORT=8000、MPA_CODEX_WORKER_PORT=8092、headless/minimal 模式及全部五个目录根路径。scripts/run.sh 同样提供这些默认值，并从 PORT 同步 PUBLIC_PORT。在 Tool Envs 中重复九项默认值没有必要，还会覆盖运维选择其他镜像时的默认设置。控制面的 Tool 环境列表不等于完整容器环境。

只移除内置 Worker env 中这九项。保留可选 managed.worker.env、模板引用/已有 Worker 支持、固定 CreateTool.Port=8000 及生成的 MPA_AGENT_ID。不修改已有 Tool、聊天、前端、镜像版本、权限或资源身份。自定义镜像必须支持已有 /opt/gem/run.sh 入口及对外端口 8000，或使用兼容的显式配置；去掉重复设置不代表任意镜像都兼容。

## 需求、场景与设计

- FR-1：内置 Studio Worker env 为空，reference ID 为空。新 CreateTool Envs 仅包含生成的 MPA_AGENT_ID；Port 仍为 8000。容器启动从镜像获得端口/模式/目录设置。
- FR-2：保留显式 Worker env 合并、校验、脱敏及排序哈希/ClientToken 行为。不更新已有绑定。已发送而未完成的请求如 env 改变，仍拒绝哈希不一致，不重复创建。
- AC-1：内置配置和模拟新账号创建测试证明不重复注入、不读取模板，保留镜像/角色/Port 并绑定 MPA_AGENT_ID。
- AC-2：已有配置/Worker 恢复回归通过，包括显式 env 及未完成载荷改变时的拒绝。

不改变状态/表结构/API/权限/依赖。Studio 契约和双语指南说明默认值归镜像所有；无需前端产物。

## 任务、审查与验证

- T-1（FR-1/AC-1）：先写失败的内置配置/请求回归，删除 studio_profile.py 的 env 块，更新 test_config.py/test_worker.py。
- T-2（FR-2/AC-2）：运行受影响部署回归及 Python 检查，同步 Studio 契约/指南及前序说明。

用户于 2026-10-09 以“没必要的就都去了”批准移除全部不必要默认配置。未提供 review-spec，编辑前直接审查通过双语一致性、入口/端口边界、显式覆盖及未完成意图保护。没有阻塞或未决实现选择。

验证范围：ef0ad519 加本次后续修改及此前未提交的 MPA 修复。必需：两项先失败的定向测试；托管/旧部署和 IAM 测试集；三个修改 Python 文件的 Ruff/Pyright；定向 pre-commit 与双语链接/标识/空白检查。真实云启动为 not_run（未授权为验证新增云写入）；前端/浏览器/生成产物及运行进程冒烟为 not_applicable（未修改这些路径）。完整提交检查等待授权提交。结果见下文。

## 结果（2026-10-09）

- 实现前 fail：两项定向测试因重复默认配置失败（97 deselected）。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py tests/cli/test_frontend_deploy_iam.py -q --tb=short` — 594 passed，五条已有弃用警告。AC-1/AC-2 及 T-1/T-2 已通过模拟请求完成。
- pass：对 managed 目录内 studio_profile.py、test_config.py、test_worker.py 执行 `uvx --from ruff==0.11.12 ruff check` 和 `uvx pyright --pythonpath .venv/bin/python`，零错误。
- pass：对三个 Python 文件及八个修改文档执行 `uv run --extra dev pre-commit run --files`，Ruff/格式/硬编码密钥检测通过。YAML 钩子为 not_applicable，未修改 YAML。
- pass：双语标识/相对链接及 `git diff --check`；直接实现审查确认镜像默认值、生成的智能体绑定和可选显式 env 共存，恢复保护不变。
- not_run：真实云创建/容器启动及无关全量 SDK 回归；受影响部署测试集通过。not_applicable：UI/构建/浏览器/生成产物及运行冒烟。未修改云资源或已有 Tool。完整提交检查等待授权提交。
