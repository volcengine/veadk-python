# 恢复前端 esbuild 锁文件条目

[English](2026-10-09-restore-esbuild-lock-entries.md)

## 元数据

- 变更 ID：`frontend-lockfile-sync`
- 创建日期：2026-10-09
- 修订日期：2026-10-10
- 状态：implemented
- 相关组件规格：无；本变更仅恢复生成的依赖元数据，不改变组件契约

## 背景与证据

PR #23 在 Harness Sidecar Release Gate 的 `npm ci --ignore-scripts` 阶段失败。CI 日志报告 `frontend/package-lock.json` 缺少 `esbuild@0.28.2` 及其平台包。

`frontend/package.json` 与 `origin/main` 完全一致。提交 `3f134207` 在未修改依赖声明的情况下删除了 512 行锁文件内容，其中包括 Vitest 嵌套的 esbuild 包和平台专属可选包。已确认的根因是生成的锁文件不完整。

## 目标与非目标

### 目标

- 恢复对受支持 CI 平台完整的锁文件。
- 使 `npm ci --ignore-scripts` 和受影响的前端发布 gate 通过。
- 保持所有声明的依赖版本和产品行为不变。

### 非目标

- 修改前端依赖或版本范围。
- 修改 Studio UI、运行时行为或 harness-sidecar 契约。
- 修改 PR #23 中无关的实现文件。

## 场景与需求

### 场景

给定未变化的 `frontend/package.json`，当 CI 在 Linux 上运行 `npm ci --ignore-scripts` 时，npm 必须能够解析精确的锁文件依赖图，并且不报告缺少 esbuild 包。

- `FR-1`：`frontend/package-lock.json` 必须包含当前 `frontend/package.json` 对应的完整依赖图。
- `FR-2`：修复不得改变 `frontend/package.json` 或组件行为。
- `FR-3`：受影响的前端 gate、常规前端测试和生产构建必须在本地通过。

## 设计与契约影响

将 `frontend/package-lock.json` 恢复为完整的 `origin/main` 版本，因为 `frontend/package.json` 未变化，且分支独有的锁文件差异仅包含意外删除。

- 接口与状态：不适用；没有源码契约变更。
- 并发与权限：不适用。
- 安全：不新增凭据或外部输入。
- 兼容性：恢复 Linux CI 兼容性，同时保持依赖声明不变。
- 组件规格：无影响；本变更只修正生成的包元数据。
- 用户文档：无影响。

已拒绝的替代方案：执行广泛的依赖升级。该方案会产生无关的版本变动，且不能精确解决已确认的意外删除。

## 实施任务

- `T-1`（`FR-1`、`FR-2`）：从 `origin/main` 恢复 `frontend/package-lock.json`。
- `T-2`（`FR-3`）：运行受影响的安装、覆盖率、测试和构建命令。
- `T-3`：检查最终差异是否存在无关变更，并记录验证证据。

## 验证与验收

| 需求 | 任务 | 验收标准 | 验证命令 | 结果 |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1` | `AC-1`：npm 接受锁文件 | `npm --prefix frontend ci --ignore-scripts` | pass：安装 695 个包 |
| `FR-2` | `T-1`、`T-3` | `AC-2`：依赖声明和组件契约未变化 | `git diff origin/main -- frontend/package.json` 和差异审查 | pass：无依赖声明或契约差异 |
| `FR-3` | `T-2` | `AC-3`：受影响的覆盖率 gate 通过 | `npm --prefix frontend run test:harness-sidecar-coverage` | pass：22 项测试 |
| `FR-3` | `T-2` | `AC-4`：前端测试通过 | `npm --prefix frontend test` | pass：1,377 项 Node 测试和 65 项 Vitest 测试 |
| `FR-3` | `T-2` | `AC-5`：生产构建通过 | `npm --prefix frontend run build` | pass |

## 风险与待决问题

- `npm run build` 可能重新生成已跟踪的 Web 资产。必须审查所有生成差异，只保留当前源码确实需要的内容。
- 没有待决设计问题。

## 审查与交付记录

- 2026-10-09：根据 PR #23 CI 日志和分支差异确认根因。
- 2026-10-09：设计审查未发现契约、安全、兼容性或可测试性阻塞项。
- 2026-10-09：用户批准恢复完整锁文件并运行前端 gate。
- 2026-10-09：从 `origin/main` 恢复被删除的 512 行锁文件内容；在 `d3370fd1` 加本工作区修复的差异范围内，依赖安装、受影响的覆盖率、完整前端测试和生产构建均通过。
- 2026-10-09：`npm ci` 报告既有依赖审计问题（6 个 low、3 个 moderate、6 个 high、1 个 critical）；依赖修复不属于本次锁文件恢复范围。
- 2026-10-10：提交 `5644e146` 再次引入相同的 512 行删除。从当前 `upstream/main` 恢复锁文件；`npm ci --ignore-scripts`、1,377 项 Node 测试、67 项 Vitest 测试、22 项 Sidecar coverage 测试和两项生产构建均通过。
- 提交、推送和更新 PR 仍需单独授权。
