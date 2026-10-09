# 等待新建 AIDAP Workspace 元数据就绪

[English](2026-09-23-aidap-workspace-readiness.md)

日期：2026-09-23。状态：已在工作区实施。归属：[Studio MPA 创建](../../specs/studio-mpa-creation/README.zh.md)。修正[自动 PostgreSQL 功能设计](../features/mpa-space-scoped-resources/2026-09-23-auto-pg-workspaces.zh.md)。

## 背景和证据

新建 MPA 在每个 Workspace 分配后立即失败：第一次停在 `admin_workspace`，下一次推进到 `business_workspace` 后失败。现在两个已记录的 Workspace ID 均能在已核验的账号中查到，状态为运行中、引擎为 PostgreSQL 17，归属标签和连接参数正确。两个库的只读 SQL 连接均成功，返回的账号具备 `CREATEDB` 权限。任务运行器脱敏了当时的原始异常，因此“元数据稍后才可见”是推断，不是已证实的历史响应。代码中存在明确的易错路径：`CreateWorkspace` 后立即校验详情字段和标签，且校验不在 `PGNotReady` 等待循环内。

## 目标、范围和场景

- 新建或已记录且由 VeADK 拥有的 Workspace 若暂时缺少详情字段/标签，或服务商返回 `ResourceNotFound`，应在现有创建超时范围内等待可见，然后继续使用已记录 ID。
- 已出现但错误的账号、地域、项目、名称、引擎或归属标签仍立即失败。显式接管保持严格校验。本修正不再次调用 `CreateWorkspace`，不删除 Workspace，不迁移或写入数据库。
- 用户以相同智能体 ID 重试时须复用已记录的两个 Workspace。其他 MPA 创建阶段及通用 Studio 智能体不在范围内。

## 设计和涉及文件

在 `veadk/integrations/mpa/managed/pg_bootstrap.py` 中，仅对引导状态标记为自行创建的 Workspace，把缺少身份字段或预期标签判为 `PGNotReady`。将详情校验放入已有就绪等待循环；此类已记录自有资源的服务商 not-found 视为暂时不可见。非空但错误的值仍立即失败。在 `tests/integrations/mpa_managed/test_auto_pg.py` 中增加离线延迟元数据和错误归属测试。更新本契约和双语文档；不改变前端 API 或界面。

## 任务、测试和验收

1. 修正前用模拟 AIDAP 服务复现立即校验标签/详情失败。
2. 仅等待暂时缺失，保留严格冲突校验和原 Workspace ID。
3. 运行托管创建测试、受影响 CLI 测试、可用时的 Python 静态/类型检查及 `git diff --check`。确认没有进行中创建任务后才重启本机 Studio。

验收：延迟出现的服务商元数据可成功且不重复创建；错误归属仍失败；两个真实已记录 Workspace 保持原状；本机 Studio 加载修正。验证离线行为不需要真实新建资源。

## 风险、审查和验证

审查：修正只改变自有 Workspace 的校验时机。永久缺失会等到现有引导超时，但不会重复分配。真实冲突值仍立即失败。后续 SQL、IAM 或 Runtime 错误不在本修正范围。

验证记录（2026-09-23，分支 `feat/from-main-20260922`，未提交改动）：延迟元数据测试在实施前失败、实施后通过；错误归属仍失败。两个已记录资源的只读 AIDAP/SQL 检查通过。`UV_CACHE_DIR=/tmp/veadk-uv-cache uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py -q`：346 通过。允许本地模拟服务绑定后，CLI 回归 41 通过。Python 编译及 `git diff --check` 通过。本机无 Ruff/Pyright 可执行文件且离线缓存无 Ruff，相关检查受阻。确认创建中任务为零后已重启本机 Studio；配置接口返回自动模式且可创建。验证期间未执行线上重试或分配新云资源。
