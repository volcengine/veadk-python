# 代码包上传校验

[English](2026-10-19-code-package-upload-validation.md)

## 元数据

- Change ID：`code-package-upload-validation`
- 创建日期：2026-10-19
- 修订日期：2026-10-19
- 状态：implemented
- 相关组件规格：无变更。本 bugfix 保持现有 Studio 代码包部署契约不变，只把已知部署失败更早暴露在上传流程中。
- 用户批准：2026-10-19 已在对话中确认三项检查：无 Dockerfile 时要求 `app.py` 和 `requirements.txt`，缺少 `0.0.0.0:8000` 监听证据时提示警告，拒绝 Python 缓存/二进制文件。

## 背景和证据

Studio 代码包上传页目前会校验 ZIP 结构、安全路径、重复路径，以及 `agentkit.yaml common.entry_point` 声明的文件是否存在。一个在 `agentkit.yaml` 中指向 `main.py` 的代码包可以通过上传校验。

对没有自定义 Dockerfile 的普通上传代码包，Studio 后续会补充默认 Dockerfile。该 Dockerfile 执行 `CMD ["python", "-m", "app"]`，并安装 `requirements.txt`。因此只有 `main.py` 但没有根目录 `app.py`，或没有根目录 `requirements.txt` 的代码包，可能要到云构建或 Runtime 启动阶段才失败。这个反馈过晚，修复建议也不够明确。

上传 ZIP 读取器会按文本解码文件。`__pycache__/`、`*.pyc` 等 Python 缓存以及其他二进制文件不是可部署源码，可能破坏或污染浏览器提供的项目。

## 目标

- `G-1`：没有自定义 `Dockerfile` 时，拒绝不满足 Studio 默认 Dockerfile 假设的代码包。
- `G-2`：代码包没有明确显示监听 `0.0.0.0:8000` 时提示用户。
- `G-3`：部署前拒绝 Python 缓存和疑似二进制文件。
- `G-4`：提供简洁的中英文文案，说明问题和建议修复方式。

## 非目标

- 不改变云端部署、AgentKit SDK launch 行为或生成 Dockerfile 行为。
- 不做完整 Python、shell 或 Dockerfile 静态分析。
- 不新增 UI 组件或重新设计上传面板。
- 不更新组件规格，因为本变更不改变公开 API、路由、Runtime 契约或所有权边界。

## 场景和需求

- `FR-1`：给定一个没有根目录 `Dockerfile` 的上传包，当它缺少根目录 `app.py` 时，Studio 必须拒绝，并说明默认启动使用 `python -m app`，建议提供根目录 `app.py` 或自定义 Dockerfile。
- `FR-2`：给定一个没有根目录 `Dockerfile` 的上传包，当它缺少根目录 `requirements.txt` 时，Studio 必须拒绝，并说明默认构建会安装 `requirements.txt`，建议提供根目录 `requirements.txt` 或自定义 Dockerfile。
- `FR-3`：给定一个包含 `__pycache__/`、`*.pyc` 或疑似二进制条目的上传包，Studio 必须拒绝，并提示移除缓存和二进制构建产物。
- `FR-4`：给定一个通过其他校验的上传包，当 Studio 未发现监听 `0.0.0.0:8000` 的证据时，Studio 必须展示非阻断警告，说明 Runtime 可访问性风险，并给出 `uvicorn.run` 示例。
- `FR-5`：既有 ZIP 大小、文件数、路径、重复项和 `agentkit.yaml` 入口校验必须保持原有行为。

## 设计和契约影响

本变更在 `frontend/src/create/CodePackageCreate.tsx` 中增加浏览器侧校验，位置在 ZIP 条目归一化之后、项目被接受部署之前。校验复用部署 API 已经接收的根目录相对文件列表。

校验策略：

- 根目录 `Dockerfile` 存在时，不强制默认的 `app.py` 和 `requirements.txt`，因为代码包自行负责构建和启动命令。
- 没有根目录 `Dockerfile` 时，必须存在根目录 `app.py` 和根目录 `requirements.txt`。
- `__pycache__/`、`*.pyc`，以及 UTF-8 解码后含替换字符或 NUL 字符的条目会作为缓存或疑似二进制文件被拒绝。
- `0.0.0.0:8000` 监听证据只作为 warning，不作为阻断。静态检测会查找项目文本中的 `0.0.0.0` 以及 `8000` 或 `PORT`，并在 Dockerfile 文本中查找端口/监听线索。因为该提示是建议性质，可以接受误报。

安全和隐私：该检查减少意外上传二进制/缓存文件，不访问外部系统，也不传输新数据。文案不得回显大段文件内容。

兼容性：已包含 `app.py` 和 `requirements.txt` 且能部署成功的包不受影响。依赖自定义 Dockerfile 的包仍然允许。过去能通过上传但会在 Studio 默认构建下失败的包，现在会更早失败并给出修复建议。

## 实现任务

- `T-1`：在 `frontend/src/create/CodePackageCreate.tsx` 中增加包校验 helper 和 warning 状态。覆盖 `FR-1` 至 `FR-4`。
- `T-2`：在 `frontend/src/i18n/resources/en-US/create.json` 和 `frontend/src/i18n/resources/zh-CN/create.json` 中增加同步文案。覆盖 `FR-1` 至 `FR-4`。
- `T-3`：扩展 `frontend/tests/codePackageDeploy.test.mjs` 的聚焦前端测试。覆盖 `FR-1` 至 `FR-5`。
- `T-4`：运行目标前端测试并记录结果。覆盖所有验收标准。

## 验证和验收

- `AC-1`：上传校验拒绝没有 Dockerfile 且缺少 `app.py` 的包，并展示包含问题和建议的文案。
- `AC-2`：上传校验拒绝没有 Dockerfile 且缺少 `requirements.txt` 的包，并展示包含问题和建议的文案。
- `AC-3`：上传校验拒绝 Python 缓存和疑似二进制条目。
- `AC-4`：对缺少监听证据但其他校验通过的包，上传校验可以展示非阻断 `0.0.0.0:8000` 警告。
- `AC-5`：既有代码包上传校验仍有测试覆盖。

| Requirement | Task | Acceptance criterion | Test or verification command | Result/evidence |
| --- | --- | --- | --- | --- |
| `FR-1` | `T-1`, `T-2`, `T-3` | `AC-1` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass，2026-10-19，12 个测试通过 |
| `FR-2` | `T-1`, `T-2`, `T-3` | `AC-2` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass，2026-10-19，12 个测试通过 |
| `FR-3` | `T-1`, `T-2`, `T-3` | `AC-3` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass，2026-10-19，12 个测试通过 |
| `FR-4` | `T-1`, `T-2`, `T-3` | `AC-4` | `node --test frontend/tests/codePackageDeploy.test.mjs` | pass，2026-10-19，12 个测试通过 |
| `FR-5` | `T-3`, `T-4` | `AC-5` | `npm --prefix frontend test`; `npm --prefix frontend run check:i18n`; `npm --prefix frontend run build` | pass，2026-10-19。前端测试：1389 个 node 测试和 118 个 Vitest 测试通过。i18n：2 个 locale、21 个 namespace 一致。Build 完成，保留既有 Vite chunk/dynamic-import warning。 |

未运行浏览器检查，因为本变更只增加上传阶段校验文案，没有引入超出现有上传面板的新交互界面。未运行仓库 pre-commit，因为用户未请求提交。

## 风险和开放问题

- 静态监听检测可能产生误报。该风险已接受，因为警告不阻断，并会说明部署风险。
- 自定义 Dockerfile 仍可能存在上传页无法完整检测的问题。本变更只增加轻量预检提示。

## 评审和交付记录

- 设计评审：本会话没有可用的 `review-spec` skill，因此直接执行评审。该修复范围可行，安全影响为正，兼容性影响仅限于更早拒绝不满足既有默认构建假设的包，中英文需求保持一致。
- 实现状态：implemented。
- 验证状态：目标代码包测试、完整前端测试、i18n 一致性检查和前端 build 均通过。`npm --prefix frontend run build` 已按预期刷新生成的 `veadk/webui` 资产。
