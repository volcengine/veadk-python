# Studio 启动资产完整性 Hotfix

[English](2026-09-22-studio-startup-assets.md)

## 元数据

- Change ID：`studio-startup-assets`
- 创建日期：2026-09-22
- 修订日期：2026-09-22
- 状态：`implemented`
- 用户批准：在推荐的“恢复并防复发”方案于 2026-09-22 会话中展示后，用户已批准
- 相关组件规范：不变更组件契约；参见[组件契约影响](#组件契约影响)
- 所属规范：[AgentKit Studio AI 开发规范](../../../frontend/SPEC.md)

## 背景与证据

### 预期行为

通过仓库本地 CLI 运行打包版 Studio 时，必须提供可执行的 WebUI：

```bash
.venv/bin/veadk studio --dev --host 127.0.0.1 --port 8000
```

浏览器必须执行入口模块并渲染 Studio 登录页或工作区，而不是留下空的根节点。使用 `npm ci` 也必须能够复现干净的前端依赖安装。

### 实际行为

当前 `origin/main` 修订 `3bbd260a` 对 `/` 及入口 JavaScript 都返回 HTTP 200，但浏览器显示白屏。打包入口文件以 Git 冲突标记开头：

```text
<<<<<<<< HEAD:veadk/webui/assets/app/index-CKbnL9AU.js
```

仓库检查发现 `veadk/webui` 下有 114 个跟踪文件包含冲突标记。冲突标记最早出现在 feature 提交 `dae75ce8`，并存在于合并提交的第二父提交 `9ff62d54` 中；第一父提交 `fd9bec69` 中数量为 0。`frontend/src` 下的源文件不包含这些标记。

已提交的 `frontend/package.json` 与 `frontend/package-lock.json` 也不一致。在干净的 hotfix worktree 中，`npm ci --dry-run --ignore-scripts --no-audit --no-fund` 失败，因为锁文件没有包含已锁定 Vitest/Vite 依赖图所需的 `esbuild@0.28.2` peer resolution。因此仓库当前无法复现干净的前端构建。

现有 `frontend/scripts/verifyBuiltAssets.mjs` 会检查目录结构、内部引用以及可选的 HTTP 逐字节一致性，但不会显式拒绝未解决的冲突标记。在当前工作树中，它会因引用的资产缺失而失败，却没有报告更直接的损坏原因。

### 已确认根因

来自两个不兼容构建的 WebUI 生成产物带着未解决的文本合并冲突标记被提交。静态服务不会解析 JavaScript，因此服务端仍返回 200，只有浏览器解析入口模块时才暴露损坏。不可复现的锁文件又阻断了可靠的干净重建恢复路径。

## 目标

- 恢复可复现的前端依赖图，使干净检出中的 `npm ci` 成功。
- 从当前 `frontend` 源码重新生成 `veadk/webui`，确保每个打包资产都来自同一次一致构建且不含冲突标记。
- 扩展现有打包资产校验器，使用直接诊断拒绝未解决的 Git 冲突标记。
- 证明普通打包模式启动可以在干净 Chrome Profile 中渲染，无需 `--vite` 或 `--frontend-dir` 临时方案。
- 将 hotfix 与无关应用、API、Runtime 和 UI 行为隔离。

## 非目标

- 不改变 Studio CLI 选项、host/port 默认值、HTTP 路由、鉴权、Session 行为、Runtime 行为、MPA 行为或 UI 交互设计。
- 不新增前端或 Python 依赖。锁文件对齐可以更新 `package.json` 已要求的传递依赖解析。
- 不进行大范围 CI workflow 重构。Hotfix 会加强现有 `test:webui-assets` 命令；除非当前仓库证据证明有必要，否则不在所有 workflow 中新增构建任务。
- 未经用户另行授权，不 commit、push、创建 PR、发布或部署。
- 不修改用户主 checkout 或其中的本地清理提交。

## 场景

### 场景 S-1：拒绝损坏的生成资产

假设 `veadk/webui` 下某文件包含以 `<<<<<<<`、`|||||||`、`=======` 或 `>>>>>>>` 开头的标准未解决合并行，当运行 `npm --prefix frontend run test:webui-assets` 时，校验必须失败、指出受影响文件，并明确说明存在未解决的冲突标记。

### 场景 S-2：可复现干净构建

假设处于干净 checkout 并使用受支持的本地 Node/npm 工具链，当运行 `npm --prefix frontend ci` 和 `npm --prefix frontend run build` 时，依赖安装和两次前端构建必须成功完成，无需手工修改锁文件。

### 场景 S-3：打包版 Studio 正常渲染

假设 `veadk/webui` 已重新生成，当不带 `--vite` 或 `--frontend-dir` 启动 `.venv/bin/veadk studio --dev` 时，`/` 和 `/web/ui-config` 必须返回 200，干净 Chrome Profile 必须渲染非空 Studio UI，且无页面级 JavaScript 错误。

### 场景 S-4：源码与运行时契约保持不变

假设评审 hotfix diff，当检查源码、API、配置和用户文档时，不应存在 Studio 运行时契约或用户流程变更；变更仅限依赖锁对齐、资产校验、生成 WebUI 以及本 PRD 双语文档。

## 需求

| ID | 需求 |
| --- | --- |
| `FR-1` | `frontend/package-lock.json` 必须与 `frontend/package.json` 同步，并且从干净依赖目录执行 `npm --prefix frontend ci` 必须成功。 |
| `FR-2` | `frontend/scripts/verifyBuiltAssets.mjs` 必须检查打包文本资产，并在引用校验掩盖直接原因之前对未解决的 Git 冲突标记失败。 |
| `FR-3` | 冲突标记检查必须覆盖 `veadk/webui` 下的 `.html`、`.css` 和 `.js` 文件，包括 diff3 的 `|||||||` base 标记，并报告相对文件名；只有标准 Git 标记出现在行边界时才判定失败，不得把普通压缩运算符或源码文本误判为冲突标记。 |
| `FR-4` | `npm --prefix frontend run build` 必须从当前源码重新生成一致的 `veadk/webui` 树；不得残留旧资产或未解决标记。 |
| `FR-5` | `npm --prefix frontend run test:webui-assets` 必须对重新生成的资产通过，并保留所有现有目录、引用和可选 HTTP 字节一致性检查。 |
| `FR-6` | 普通打包模式 `veadk studio --dev` 必须在干净 Chrome Profile 中渲染可见 Studio 内容。仅 HTTP 200 不能作为充分证据。 |
| `FR-7` | 变更不得修改公共 Python import、CLI 参数、服务端路由、前端 API 类型、配置优先级、鉴权、持久化或 Runtime 语义。 |

## 方案

### 选定方案

复用现有构建和校验架构：

1. 在 `verifyBuiltAssets.mjs` 中增加窄范围内容完整性检查。对于校验器已读取的每个 `.html`、`.css` 和 `.js` 打包文件，使用多行表达式检测标准未解决 Git 标记行，并抛出包含相对路径的断言。此检查先于内部引用提取执行。
2. 以当前 `frontend/package.json` 为依赖意图，使用仓库 npm 工具链仅重新生成 `package-lock.json`。不得改变直接依赖声明及其范围。必须确认普通的干净 `npm ci --no-audit --no-fund` 成功，不能只接受一次 install-only 或仅 `--ignore-scripts` 的结果。
3. 执行现有 `npm --prefix frontend run build`。其 Vite 配置会在生成前清空 `veadk/webui`，避免冲突构建的旧文件继续残留。
4. 执行加强后的校验器、前端测试和真实打包启动浏览器检查。

### 备选方案

- **仅重建：** 可以修复当前文件，但仍允许未解决冲突标记回归。现有校验器是自然且低成本的预防边界，因此不采用。
- **只替换入口 JavaScript：** 只掩盖一个症状，仍留下另外 113 个损坏资产和破损锁文件。不完整且不可复现，因此不采用。
- **为所有 CI workflow 新增完整构建任务：** 执行范围更广，但会显著扩大 hotfix 范围和 CI 成本。本次使用可复用资产校验器已足够，故暂缓。

### 错误行为

校验必须围绕不变量尽早失败，例如：

```text
assets/app/index-*.js contains an unresolved Git conflict marker
```

校验器不得输出资产内容，因为即使生成 bundle 不应嵌入密钥，其中仍可能包含类似配置的字符串。

### 兼容与回滚

- Runtime 兼容性：不变。生成 UI 仍来自相同的当前源码和 API。
- 依赖兼容性：直接依赖范围不变；锁文件对齐到这些范围。
- 回滚：revert hotfix 提交。回滚会恢复已知白屏缺陷，因此首选操作恢复方式是使用上一个干净的生成 WebUI，同时修复 main。

### 安全、状态与并发

- 安全：不改变凭据、鉴权、URL 获取或信任边界。校验只读取仓库本地生成文本并仅报告文件名。
- 状态/数据：不改变应用数据或持久化。
- 并发/取消：不适用；变更后的校验器是单进程构建期命令。
- 外部副作用：依赖安装只下载仓库已声明的软件包；未授权任何云端或 provider 操作。

## 组件契约影响

不创建或更新组件规范。本 hotfix 保持所有外部可观察的 Studio、CLI、HTTP、Runtime、鉴权、状态和配置契约不变，只修复生成交付资产及其构建期完整性检查。因此未触发 `specs/README.md` 中的组件规范更新条件。如果实现需要变更 CLI 选项、路由、配置默认值、Runtime 行为或前端 API 契约，必须重新评估此 no-impact 结论。

## 涉及文件

预期手工维护文件：

- `.gitattributes`
- `frontend/package-lock.json`
- `frontend/scripts/verifyBuiltAssets.mjs`
- `prd-spec/bugfixes/studio-startup-assets/2026-09-22-studio-startup-assets.md`
- `prd-spec/bugfixes/studio-startup-assets/2026-09-22-studio-startup-assets.zh.md`

预期生成文件：

- 由 `npm --prefix frontend run build` 生成的 `veadk/webui/**`

不应修改 `frontend/src` 下的源码、Python 模块、组件规范或用户文档。

## 实现任务

| ID | 任务 | 需求 |
| --- | --- | --- |
| `T-1` | 在现有资产校验器中增加冲突标记门禁，然后在生成资产仍损坏且尚未重建的工作树上运行加强后的校验器，作为负例证明；在任何生成资产变更前保留失败输出。 | `FR-2`, `FR-3` |
| `T-2` | 对齐 `package-lock.json`，移除 hotfix worktree 的依赖目录，并证明干净 `npm ci`。 | `FR-1` |
| `T-3` | 使用现有构建命令重新生成 `veadk/webui`，确认不存在旧资产或冲突资产。 | `FR-4`, `FR-5` |
| `T-4` | 执行前端测试、资产校验、diff hygiene 和最终 diff 所需的密钥扫描/pre-commit 门禁。 | `FR-5`, `FR-7` |
| `T-5` | 不带临时方案启动打包版 Studio，使用干净 Chrome Profile 验证可见渲染、DOM 内容、console/page error 和核心 HTTP endpoint。 | `FR-6` |
| `T-6` | 执行两轮实现评审，并用实际证据同步中英文交付记录。 | 全部 |

## 验证与验收

执行日期为 2026-09-22。最终测试范围为 rebase 到 `origin/main` 修订 `821f0f36` 的 `fix/studio-startup-assets` 及其 hotfix worktree diff。前端依赖检查使用 Node `v22.23.0` 和 npm `10.9.8`。修订 `3bbd260a` 仍是上文记录的缺陷复现基线。

| 需求 | 任务 | 验收标准 | 测试或验证命令 | 结果/证据 |
| --- | --- | --- | --- | --- |
| `FR-2`, `FR-3` | `T-1` | `AC-1`：增加门禁后且重建前，当前损坏工作树必须针对未解决冲突标记失败并指出文件名，以证明新检查对原始缺陷敏感。 | 重建前运行 `npm --prefix frontend run test:webui-assets` | `pass`：退出码 1，提示 `assets/app/index-Ceg2hYta.js contains an unresolved Git conflict marker`；输出被限制为 536 字节。 |
| `FR-1` | `T-2` | `AC-2`：包括 package lifecycle script 在内的普通干净依赖安装使用已提交锁文件成功，且不修改 `package.json`。 | `npm --prefix frontend ci --no-audit --no-fund`；`git diff --exit-code -- frontend/package.json` | `pass`：安装 697 个 package；`package.json` SHA-256 保持 `81b2946cc95da4014fef3924b4e6a3a096e69d0b5635bfa00e97148571d19ac8`。 |
| `FR-4`, `FR-5` | `T-3` | `AC-3`：构建成功，生成树的冲突标记文件数量为 0，且所有资产引用可解析。 | `npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`；扫描 `veadk/webui` 中的标记；重复构建 SHA-256 对比 | `pass`：两次 Vite 构建完成；104 个打包文件和 248 个引用通过；标记数量为 0；连续两次构建的全部 104 个文件 SHA-256 完全一致。 |
| `FR-5`, `FR-7` | `T-4` | `AC-4`：前端回归测试和构建期检查通过，且未弱化断言。 | `npm --prefix frontend test`；`npm --prefix frontend run check:i18n`；`git diff --check` | `pass`：rebase 后 1305 个 Node 测试和 25 个 Vitest 测试通过；2 个 locale、21 个 namespace 一致；diff check 通过。 |
| `FR-6` | `T-5` | `AC-5`：打包版 Studio 的 `/` 与 `/web/ui-config` 返回 200；新 Chrome Profile 产生非空渲染 DOM 和截图，且没有页面级 JavaScript 错误。 | `.venv/bin/veadk studio --dev --host 127.0.0.1 --port 18081` 加隔离 Chrome/CDP 验证 | `pass`：两个 endpoint 均返回 200；`rootChildren=1`；渲染登录文本包含 `AgentKit Studio`；捕获的 page/console/network error 列表为空；截图确认 UI 可见。 |
| 全部 | `T-6` | `AC-6`：仓库要求的最终门禁全部完成，或诚实记录原因；双语文档与交付 diff 一致。 | `uv run --extra dev pre-commit run --all-files` 和适用的最终评审 | `pass`：Ruff check、Ruff format 和 gitleaks 通过。两轮实现评审解决了有界诊断、diff3/CRLF 标记覆盖和生成 bundle 空白处理。 |
| 仓库回归 | `T-6` | 执行要求的默认 Python 回归，并在不扩大本前端 hotfix 范围的前提下记录无关基线失败。 | `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | `fail`：5013 passed、12 skipped、2 xfailed、11 failed、2 collection errors。失败位于未修改的环境、Skill、MPA managed-service 与 Harness 测试；collection error 提示缺少可选 `anthropic`。本 hotfix 未修改 Python 源码。 |

## 风险与待确认问题

- 现有依赖范围较宽，锁文件重新生成可能产生较大的传递依赖 diff。评审必须区分必要同步与无关升级，并在 npm 允许的范围内减少 churn。
- 依赖命令使用仓库本地 `frontend/package.json`、`frontend/package-lock.json` 和当前可用的 Node 22/npm 10 工具链。最终干净安装证据必须记录实际版本。
- 生成 WebUI diff 天然较大。校验必须关注可复现性、无冲突标记、内部引用、前端测试和真实浏览器行为，不能只依赖人工阅读压缩文本。
- `website-integration.js` 包含带有语义尾随空白的第三方模板字符串。现有 `.gitattributes` 策略已对 `veadk/webui/assets` 下的生成 JavaScript 禁用空白诊断；本 hotfix 将同一策略精确扩展到根目录的生成 integration bundle，而不是改写有语义的 bundle 内容。
- 当前仓库似乎没有在每个通用 PR workflow 中运行 `test:webui-assets`。本 hotfix 会增强可复用命令，但不声称已经实现全局 CI 强制。若需要，可另行提出 CI 治理变更。
- 阻塞性待确认问题：无。用户已于 2026-09-22 批准范围受控的“恢复并防复发”方案。

## 评审与交付记录

- 2026-09-22：已向用户展示范围、备选方案、根因证据和推荐方案。用户回复“继续”，批准按推荐方案推进。
- 2026-09-22 Spec 评审：发现并解决两个 P1 缺口。负例现在明确要求在重建前运行加强后的校验器；干净安装现在要求执行普通 lifecycle script，不能依赖 `--ignore-scripts`。已检查双语标识、命令、涉及文件、兼容性、组件 no-impact、安全、回滚和验收追踪，无剩余阻塞项。
- 2026-09-22 实现评审：第二轮边界检查增加了标准 diff3 `|||||||` base 标记覆盖；同时将仓库已有的生成 JavaScript 空白属性扩展到 `veadk/webui/website-integration.js`，因为其中第三方模板字符串的尾随空白具有语义。
- Spec 评审结论：批准进入实现。
- 2026-09-22 最终同步：已 rebase 到 `origin/main` 修订 `821f0f36`。上游在加入后续前端修复时已独立替换损坏 WebUI；从该最新源码重新构建后，`veadk/webui` diff 为 0。因此 hotfix 最终只保留可复现 lockfile 修复、冲突标记防复发门禁和本双语设计记录。
- 2026-09-22 交付：任务 `T-1` 至 `T-6` 与验收标准 `AC-1` 至 `AC-6` 全部通过。未修改 Python 源码、前端应用源码、公共契约、组件规范或用户文档。
- 默认 Python 全量回归因上述最新 main 无关失败仍为红灯。前端专项交付门禁和仓库 pre-commit 均通过；本 hotfix 未压制或修改这些无关 Python 失败。
- 剩余范围：PR、发布和部署不属于本次交付；用户已另行授权 commit 与 push。
