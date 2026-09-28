# Studio MPA 创建使用可写临时状态

[English](2026-09-23-use-temporary-state.md)

- 变更 ID：`studio-mpa-writable-state`
- 创建/修订日期：2026-09-23
- 状态：implemented
- 相关组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)
- 用户批准：2026-09-23，暂不实现 TOS 持久化，先用 `/tmp` 修复云端问题。

## 背景与证据

已部署 Studio 的代码目录只读。首个 MPA 创建请求在启动子进程前失败，因为 `CreationTasks` 尝试创建 `.adk/mpa-creation.sqlite3`；后续自动准备 PostgreSQL 时也会因 `.adk/mpa-pg-bootstrap.sqlite3` 遇到同类问题。本地只读目录复现及运行时插桩已确认首个失败点。两个存储仅包含非密钥控制状态，但都要求可写文件系统。

预期行为是有权限的云端 Studio 请求能够开始创建；实际行为是在提交任务前返回 HTTP 500。

## 目标与非目标

目标：

- 将内置云端 Studio 的任务数据库和 PostgreSQL bootstrap 数据库放到 `/tmp/veadk-studio/`。
- 保留显式 `VEADK_MPA_TASK_DB` 覆盖及独立 CLI/YAML 默认值。
- 保持密钥处理、API 结构、任务限制及云编排行为不变。

非目标：

- 函数实例替换或多个 Studio 实例间的持久状态。
- TOS CAS、NAS、数据库协调、已有 `.adk` 文件迁移或部署。

## 场景与需求

- **FR-1：**未设置任务数据库覆盖时，Studio 延迟创建任务服务应使用 `/tmp/veadk-studio/mpa-creation.sqlite3`。
- **FR-2：**设置 `VEADK_MPA_TASK_DB` 时，Studio 创建任务服务应优先使用显式路径。
- **FR-3：**使用内置 Studio 配置时，自动 PG bootstrap 应使用 `/tmp/veadk-studio/mpa-pg-bootstrap.sqlite3`。
- **FR-4：**独立 YAML 未设置 `bootstrap-path` 时，继续使用现有 `.adk/mpa-pg-bootstrap.sqlite3` 默认值。
- **FR-5：**任何凭据或 OpenViking API Key 均不得写入两个 SQLite 存储。

## 设计与契约影响

HTTP 路由拥有 Studio 任务存储默认值，本次仅修改该默认值。代码内置 Studio 配置拥有 PG bootstrap 路径，本次仅修改该配置值。`CreationTasks` 与 `BootstrapStore` 保持现有 SQLite 实现、表结构、锁和文件权限。

目标 VeFaaS 运行时的 `/tmp` 可写，但属于临时且实例本地的存储。重启或实例替换可能丢失任务历史及 bootstrap 身份。因此，本修复只作为已明确接受的单实例临时恢复方案。若云资源创建结果不确定时任务记录丢失，运维必须先检查云资源再重试。持久共享实现仍是后续工作。

安全及权限不变：父目录权限为 `0700`，数据库文件权限为 `0600`，不持久化密钥。HTTP 请求/响应及独立 CLI/YAML 调用保持兼容。不涉及前端契约。

本次临时修复未采用的方案：

- TOS CAS：可持久共享，但需要任务租约、重启协调及 bootstrap 并发语义。
- NAS：可通过少量代码改动提供持久化，但要求配置部署存储。
- 删除状态：不安全，因为幂等和不确定结果恢复依赖这些状态。

## 实现任务

- **T-1（FR-1、FR-2）：**增加路由测试并修改 Studio 任务数据库默认值。
- **T-2（FR-3、FR-4）：**增加配置测试并修改内置 bootstrap 路径。
- **T-3（FR-5）：**运行现有路由、任务和配置安全回归测试。
- **T-4：**收集修复后证据后移除临时运行时插桩。

涉及文件：`frontend/server/mpa_creation.py`、`veadk/integrations/mpa/managed/studio_profile.py`、`tests/integrations/mpa_managed/test_routes.py`、`tests/integrations/mpa_managed/test_config.py` 及双语组件规范。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1`、`FR-2` | `T-1` | `AC-1`：默认值及覆盖值解析到预期任务路径 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_routes.py` | `pass`，2026-09-23 |
| `FR-3`、`FR-4` | `T-2` | `AC-2`：内置配置及 YAML 配置路径保持正确隔离 | `uv run --extra dev pytest tests/integrations/mpa_managed/test_config.py` | `pass`，2026-09-23 |
| `FR-5` | `T-3` | `AC-3`：现有任务及路由脱敏测试通过 | `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -q` | `pass`，396 项测试，2026-09-23 |
| `FR-1`、`FR-3` | `T-4` | `AC-4`：只读代码目录复现可在 `/tmp` 初始化两个存储 | 本地只读工作目录复现；云端冒烟需要单独部署授权 | 本地 `pass`；云端 `not_run`，2026-09-23 |

按 `frontend/SPEC.md` 执行改动 Python 文件的 Ruff 和 Pyright。因为不修改 UI 或 HTTP 结构，前端测试/构建不适用。

## 风险与恢复

- 实例重启会丢失 `/tmp` 状态；云资源可能比本地意图记录存活更久。
- 多个函数实例不共享锁或并发计数。使用此临时方案期间，当前部署必须保持单实例。
- 回滚会恢复 `.adk` 默认值，同时恢复云端只读目录故障。

## 审查与交付记录

2026-09-23 设计审查确认不修改 API、密钥处理或独立 CLI 兼容性。已明确记录持久性及多实例限制，并由用户作为临时修复接受。英文/中文的需求 ID、路径、限制、任务及验收标准已检查语义一致。

2026-09-23 实现验证通过 396 项 MPA/CLI 测试、改动文件 Ruff、改动文件 Pyright、`git diff --check`，并在只读工作目录下成功初始化两个 `/tmp` 存储。云端部署和真实创建为 `not_run`，因为部署需要单独授权。
