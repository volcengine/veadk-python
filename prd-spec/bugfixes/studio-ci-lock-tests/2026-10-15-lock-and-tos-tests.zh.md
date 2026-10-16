# 修复 PR 1167 CI，保持产品行为不变

[English](2026-10-15-lock-and-tos-tests.md)

日期：2026-10-15。基线：`8ae26a6d`。状态：已批准实施。

## 背景与范围

PR 1167 的前端 CI 和发布验证在 npm ci 阶段失败：锁文件缺少嵌套 Vite 依赖所需的 esbuild 0.28.2 及其平台包。Python 3.12 的 test_creation_images.py 有三个失败：旧断言禁止持久化 tosBucket，与已批准的[本地任务恢复设计](../mpa-creation-local-state/2026-10-15-local-task-recovery.zh.md)冲突。桶名是非密钥请求身份，TOS 凭据仍须排除。

## 需求与设计

- R1：仅修复锁文件缺失的解析条目。保持 package.json、已有包版本及产品源码不变。在干净目录使用与 CI 兼容的 Node/npm 生成，验证干净环境 npm ci。
- R2：更新三个旧测试用例，要求任务响应/持久载荷保存所选桶，同时保留密钥排除检查。结构化读取持久 JSON，不再搜索 SQLite 原始字节。保留已有请求变更拒绝和子进程 TOS 传递测试。
- R3：先复现定向失败，再运行 managed Python 回归、npm test、构建、sidecar 覆盖率及改动文件 lint/密钥检查。不降低 CI 门槛或删除测试。

涉及文件：frontend/package-lock.json；tests/integrations/mpa_managed/test_creation_images.py；本双语设计。组件契约影响：无；恢复现有任务恢复契约的验证并补全开发依赖元数据。不修改生产运行时、公共 API、云资源或安全策略。不包含部署、发布、提交或推送。

## 任务与验收

1. 在隔离环境复现现有测试失败和锁文件安装失败。
2. 修复锁元数据并同步断言；保留修改桶名冲突和密钥拒绝行为。
3. 验证已有锁定包版本不变、干净安装成功、受影响测试和构建通过，再审查最终差异。

风险：npm 可能改写无关元数据，需比较全部已有锁条目；构建可能生成资源，因此在隔离工作目录运行，避免无关产物变化。发布后仍需重新运行 Linux CI，macOS 验证不等于 Linux 实测。本次仅改元数据/测试，不适用 UI/浏览器检查。

## 评审与批准

用户回复“帮我修一下，不要影响功能”，批准前述方案。直接设计评审（review-spec 不可用）检查了契约一致性、安全、最小范围、依赖兼容性、测试与双语等价性，无阻断项。现有失败证据作为先行回归基线，生产行为不变。

## 验证

已完成，详细证据如下。


## 验证记录

2026-10-15，基线 `8ae26a6d`，仅锁文件/测试/文档差异：

- pass：在干净临时目录用 Node 22.17.0/npm 10.9.2 复现完全一致的 npm ci 缺少 esbuild 错误，并复现三个 pytest 失败（其余 15 项通过）。
- pass：该目录执行 `npm install --package-lock-only --ignore-scripts --no-audit --no-fund`，恰好增加 27 个锁条目。结构化比较确认已有条目及版本均未改变，package.json 和全部生产源码保持不变。
- pass：macOS 上使用 Node 22.17.0/npm 10.9.2 干净执行 `npm ci --ignore-scripts --no-audit --no-fund`，安装 697 个包。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed -n 2 -q --tb=short` — Python 3.10 上 1151 项通过；使用两个 worker 限制本机资源占用。
- pass：隔离 Python 3.12 环境执行 `uv run --python 3.12 --extra dev pytest tests/integrations/mpa_managed/test_creation_images.py tests/integrations/mpa_managed/test_routes.py tests/integrations/mpa_managed/test_tasks.py -n 2 -q --tb=short` — 55 项通过，覆盖修改桶名拒绝和持久化。没有替换仓库 Python 环境。
- pass：隔离前端工作区执行 `npm test` — 1389 个 Node 测试及 118 个 Vitest 测试通过。首次隔离执行缺少仓库配套文件，四个测试模块因 ENOENT 失败；复制所需已跟踪配套文件后解决测试环境问题，没有改代码。
- pass：`npm run test:harness-sidecar-coverage` — 22 项测试；语句覆盖率 98.55%、分支 94.44%、函数/行 100%。
- pass：隔离工作区执行 `npm run build` — TypeScript 和两个 Vite 构建成功，保留既有体积/弃用警告。本次不包含仓库生成资源变更。
- pass：改动文件 pre-commit 的 Ruff 检查/格式化和密钥扫描；依赖/YAML hook 为 not_applicable；`git diff --check` 及双语标识符/链接审查。
- fail（既有问题）：改动文件 Pyright 报告两个诊断，同命令检查 HEAD 文件得到完全相同的规则/消息，没有新增诊断，未清理无关类型问题。
- not_run：全仓库 Python 套件及 GitHub 重跑（未要求提交或推送）；已完成上述受影响回归。
- not_applicable：真实浏览器/云端 smoke，没有产品 UI/运行行为变化。

Linux 容器验证：pass。在 Linux ARM64 上使用全新 `node:22.17.0-bookworm-slim`（Node 22.17.0/npm 10.9.2），`npm ci --ignore-scripts --no-audit --no-fund`、`npm run test:harness-sidecar-coverage`、`npm test` 均成功退出：22 个覆盖率测试、1389 个 Node 测试和 118 个 Vitest 测试。GitHub Linux x64 重跑仍是独立验证。未执行提交、推送、部署或云资源修改。
