# 从智能体 ID 派生 MPA 沙箱模板名称

- Change ID：`mpa-worker-naming`；创建/修订：2026-09-28；状态：implemented。
- [English](2026-09-28-agent-derived-worker-name.md)
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-3。

## 证据、目标与范围

`managed/worker.py` 当前使用 `mpa_worker_` 加作用域哈希命名工具。已核对的 ArkClaw 实现则去掉智能体 ID 两端空白，将连字符换成下划线，作为正式工具名称。目标是让用户按智能体 ID 识别模板。仅修改托管 MPA 工具创建；不重命名已有云工具，不改变 Runtime 名称/ID、镜像、网络、标签、数据库名称或通用智能体，不创建调试工具。

## 需求与场景

- FR-1 / AC-1：新 `mi-example` 智能体创建/发现模板 `mi_example`；去掉两端空白，将所有 `-` 替换为 `_`。
- FR-2 / AC-2：已登记 worker ID 和显式指定的已有 ID 保留绑定，不进行发现、创建或重命名。
- FR-3 / AC-3：变更前未完成的创建意图，重试时保留哈希名称、完整请求哈希和 ClientToken，无论云端是否已经创建工具。若请求内容改变，仍在发现/创建前失败。
- FR-4 / AC-4：同名不构成接管授权。保留所有权校验、作用域标签、超时、取消和终态处理。

## 设计与兼容

新请求使用智能体派生的 Name。已有 worker_hash 不匹配时，使用原哈希 Name 重新计算请求哈希。仅完全匹配才继续使用旧请求，否则保留配置变更错误。无数据库结构/API 扩展、迁移、新依赖、新权限或密钥持久化。已有绑定 ID 仍直接跳过请求名称构造。现有账号锁继续负责串行化。名称规范化可能产生碰撞，因此必须保留同名冲突拒绝和所有权检查。新意图尚未完成时回退旧代码，需使用新代码完成该意图；已有绑定 ID 仍可使用。

## 任务与影响文件

- T-1（FR-1–FR-4）：在 `tests/integrations/mpa_managed/test_worker.py` 增加隔离回归测试；实现前证明新命名测试失败。
- T-2（FR-1、FR-3）：最小修改 `veadk/integrations/mpa/managed/worker.py`。
- T-3：同步双语设计、Studio 创建 CON-3 和托管集成 README 双语文档；运行 worker/managed 回归、Ruff、Pyright 和空白检查。

## 评审与批准

2026-09-28：用户回复“改为旧规则”，批准已提出的按智能体命名并兼容已有资源/重试方案。`review-spec` 不可用；直接评审已核对边界、失败语义、所有权、安全、回退、可测性及双语等价性，无阻塞项。生产代码修改在本评审之后。

## 验证

范围：当前分支工作区的 worker 命名改动；保留无关的共享网络修改。T-1–T-3 结果见下文。真实云创建：`not_run`（仅名称/请求变更无需执行；本次不进行云修改）。浏览器/构建：`not_applicable`（无前端或浏览器 API 变更）。提交门禁：`not_run`（用户未要求提交）。

### 2026-09-28 验证记录

T-1–T-3 / AC-1–AC-4 已完成，范围为当前工作区的命名改动。实现前命名测试 `fail`（2 failed、14 passed），符合预期；实现后：

- `uv run --extra dev pytest tests/integrations/mpa_managed/test_worker.py tests/integrations/mpa_managed/test_worker_recovery.py tests/integrations/mpa_managed/test_worker_metadata.py -q --tb=short`：`pass`，67 passed。
- `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py tests/cli/test_frontend_deploy_iam.py -q --tb=short`：`pass`，422 passed，5 条已有依赖弃用警告。
- `uv run --with ruff --with pyright ruff check veadk/integrations/mpa/managed/worker.py tests/integrations/mpa_managed/test_worker.py`：`pass`；首次 import 排序失败已修正。
- `uv run --with ruff --with pyright pyright veadk/integrations/mpa/managed/worker.py tests/integrations/mpa_managed/test_worker.py`：`pass`，0 errors。
- `git diff --check`：`pass`。

最终代码评审：完整旧 payload 哈希匹配才保留旧名称；不改变幂等凭据或所有权标识；已有 ID 不进入创建分支。双语需求/契约已同步。uv 缓存首次受沙箱限制，批准访问后检查完成；按用户已有偏好仅记录本次验证，不修改环境说明。无提交、推送或云端修改。

附加检查：仓库固定 Ruff 检查及格式检查、PRD 相对链接、双语对应和修改文件的 `gitleaks dir --redact` 扫描均为 `pass`。前端说明已更新，无生成产物变化。

## Rebase 验证 — 2026-10-07

为 PR #17 与 main `e0448a4d` 协调。保留原功能补丁及上游发现/鉴权和 Worker 恢复改动。参见[组合协调及验证记录](../mpa-shared-network-bootstrap/2026-09-28-registry-owned-network.zh.md#pr-17-rebase-协调--2026-10-07)。
