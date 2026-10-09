# 托管 MPA 创建复用 Studio 身份资源

[English](2026-09-23-deploy-identity-reuse.md)

- 变更 ID：`studio-mpa-identity-reuse`；创建/修订：2026-09-23；状态：approved。
- 用户在本任务确认以环境变量保存并复用的方案。
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 背景、目标与范围

`veadk studio deploy` 已将 Studio UserPool/客户端 UID 保存到 VeFaaS，并在得到公网地址后保存 OAuth 回调。旧 MPA 创建路径会解析资源名称，但新托管创建只从 YAML 读取 Identity 名称和回调。新的共享 PostgreSQL Workspace 要到创建 MPA 时才准备，因此无法存放 Studio 部署时的 Identity 信息。目标是让后续托管 MPA 自动复用 Studio 登录资源。不新增 PostgreSQL 表、浏览器输入或 UserPool/客户端创建流程，也不修改已有 Runtime。

## 场景与需求

- `FR-1`：Studio 部署确定 UserPool/客户端后，使用部署凭据解析名称，并在第二次发布中将名称、Identity 地域以及 `https://<studio-host>/oauth/callback` 作为非密钥 VeFaaS 环境变量保存。保留既有 UID 和 Studio 登录回调行为。
- `FR-2`：托管 MPA 创建在子进程执行云写入前合并这些服务端值。子进程重启后仍从继承环境读取相同值，并向新 Runtime 注入 `MPA_USER_POOL_NAME`、`MPA_USER_POOL_CLIENT_NAME`、`IDENTITY_CALLBACK_URL`、`IDENTITY_REGION`。
- `FR-3`：部署身份配置不完整，或 YAML 显式配置不同的 Identity 值时，在本地返回安全的配置错误。完整且一致的 YAML 可用；没有部署身份配置时保持独立 CLI/YAML 行为。身份值不进入浏览器请求或任务数据库。

## 设计与影响

使用四个 `VEADK_STUDIO_MPA_*` 环境变量，复用已有 `IdentityClient.get_user_pool_resource_names` 和托管配置/Runtime 环境链路。VeFaaS 第二次发布负责确定公网回调地址。配置加载器是 Studio 配置检查、任务接纳和固定子进程的共同边界，在云资源写入前校验完整性与冲突；只在 YAML 缺失时采用 Studio 环境值，显式冲突则拒绝，包括 `managed.runtime.env`。Identity 地域必须保存，因为它可能不同于部署地域。不改数据库结构、前端 API、任务载荷和依赖。UserPool 名称与回调不是密钥；AK/SK 和客户端密钥仍仅在服务端。

资源名称解析失败时，以脱敏的运维错误停止部署。回调注册沿用现有警告行为。已有云上 Studio 需要重新部署才能获得新环境值；已有 MPA Runtime 不变。本地测试不能证明真实 Identity/VeFaaS/Runtime 端到端链路。

## 任务、验收与评审

- `T-1`（`FR-1`、`AC-1`）：第二次 VeFaaS 发布保存四项；测试外部 UID 和非北京 Identity 地域。
- `T-2`（`FR-2`、`FR-3`、`AC-2`）：在 `load_profile` 合并并校验服务端环境，再在托管 Runtime 注入解析后的地域；测试缺失、一致、冲突、部分配置和独立模式。
- `T-3`（`AC-3`）：同步中英组件契约/操作文档，执行相关 Python 测试、pre-commit 和可行的扩大回归；在下文记录实际结果。

评审：Studio 部署时公共 PG 尚不存在，因此不新增表；不向浏览器传身份值或密钥；在云写入前校验。用户已确认环境变量方案。风险：回调注册仍可能只警告，真实服务商权限和 Runtime 启动尚未验证。

## 验证记录

2026-09-23 实现后，`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_studio_deploy_target.py tests/cli/test_cli_mpa.py -q` 通过（427 项）。隔离采集的改动可执行行覆盖率为 19/19（100%）：托管配置 13/13、Runtime 身份注入 2/2、Studio 部署 4/4。合并运行 pytest-cov 时，Pydantic/SDK 在插桩下出现收集行为异常；相同的受影响测试集在不插桩时通过。全量回归 5189 项通过、9 项失败、2 项收集错误：6 项 Harness 失败缺少可选 `llama_index`，2 项 Skill 版本失败为无关的来源地域不匹配，1 项 Workspace Editor 失败是 PATH 中缺少 `node`，2 个 Sandbox 测试模块缺少可选 `anthropic`。Pre-commit 通过。使用项目解释器的 Pyright 报告 36 个既有错误，新增行无错误。本次不修改前端源码/产物，前端构建不适用。真实云上 Identity/VeFaaS/Runtime 端到端未运行；部署权限与回调仍需运维验证。
