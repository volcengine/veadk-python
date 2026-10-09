# 对齐 Studio 的 OpenViking wheel

[English](2026-10-07-align-sdk-wheel.md)

- 变更 ID：`studio-openviking-wheel`
- 创建/修订日期：2026-10-07
- 状态：implemented
- 范围：Studio 依赖打包；本次未请求云端部署或提交。

## 证据和目标

`pyproject.toml` 要求 `openviking-sdk>=0.1.9`，`uv.lock` 解析为
0.1.9，但 `veadk/cli/studio_dependencies.py` 仍准备 0.1.4。
`build_local_studio_requirements(offline_runtime=False)` 将此 wheel 和本地
VeADK wheel 写入同一份 requirements，产生依赖冲突。BytePlus 的依赖准备
也使用该清单。完整离线构建已经通过 `uv.lock` 解析，使用 0.1.9。

恢复打包兼容性，不改变 SDK API、最低依赖、锁文件、MPA 镜像和运行中的部署。
不重新设计依赖解析，也不升级无关的固定依赖。

## 需求和场景

- FR-1：`volcengine` 和 `byteplus` 携带的 OpenViking wheel 均须满足项目声明
  的 SDK 依赖要求。
- FR-2：版本、文件名、下载 URL 和 SHA256 须与锁定的 PyPI wheel 一致。
  保持既有依赖准备和校验失败行为。
- FR-3：固定版本低于最低要求或与锁定产物不一致时，回归检查必须失败。
  测试不得访问云服务或包服务器。

当前固定为 0.1.4 时，一致性测试失败；对齐至锁定的 0.1.9 后，两种云厂商路径
均通过。仅包含旧 wheel 的预备缓存需要刷新；缺少当前 wheel 时仍明确失败。

## 设计和契约评估

将已提交锁文件中的 0.1.9 文件名、URL 和 SHA256 复制到现有静态 wheel 记录。
更新部署测试夹具。使用 `packaging` 和已有 TOML 解析支持增加跨文件测试，不
增加依赖。降低 SDK 最低要求会与已经更新的 options API 冲突，因此不采用。

无需修改组件规格：本次恢复已有 SDK 依赖兼容性和锁定产物完整性，不定义新的
API、配置、状态、权限或失败契约。并发、取消、会话处理和 UI 行为不受影响。
保留已有校验机制，不涉及凭据或外部资源修改。

## 任务和验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1 | T-1：修复前增加回归测试 | AC-1：两种云厂商的固定版本均满足项目依赖要求 |
| FR-2 | T-2：更新 wheel 记录和部署夹具 | AC-2：版本、文件名、URL 和哈希与 `uv.lock` 一致 |
| FR-3 | T-3：运行相关测试、静态检查和文档检查 | AC-3：记录修复前失败与修复后通过的结果 |

涉及实现和测试：`veadk/cli/studio_dependencies.py`、
`tests/cli/test_studio_dependencies.py`、`tests/cli/test_studio_deploy_target.py`。
通过 `uv run --extra dev pytest` 运行新增测试、Studio 发布/部署/离线打包测试
和已有 OpenViking 后端测试；对修改的 Python 文件运行 Ruff、Pyright，并运行
`git diff --check`。

## 审查、风险和交付

- 用户以“帮改下”批准此前提出的 0.1.9 固定版本、URL/哈希和测试改动方案。
- 直接完成设计审查（`review-spec` 不可用）：已核对范围、现有调用方、依赖兼容性、
  错误行为、安全和双语一致性，无阻塞项。
- 源码更新不会修改已有部署，需要另行构建和部署。旧的依赖预备缓存需重新生成。
- 浏览器/前端构建：not_applicable；未修改 UI、前端源码或网页产物。
  云端部署与完整 Linux 打包：not_run；本次在本地验证固定依赖与打包契约，
  不部署资源。
- 实现审查：差异仅调整 OpenViking 产物和测试夹具，增加跨文件回归检查，
  保持依赖准备行为。已核对双语文档及相对链接。

### 验证（2026-10-07，`056e8acd` 上的工作区差异）

| 检查 | 结果 |
| --- | --- |
| 修复前 `uv run --extra dev pytest tests/cli/test_studio_dependencies.py -q` | fail（预期）：4 项失败，复现 0.1.4 与 SDK 要求和锁文件不一致 |
| 下方回归命令，2 个 worker | pass：192 项测试，包含全部 4 项新增用例 |
| `uv run --with ruff==0.11.12 ruff check veadk/cli/studio_dependencies.py tests/cli/test_studio_dependencies.py tests/cli/test_studio_deploy_target.py` | pass：使用仓库固定的 Ruff 版本 |
| `uv tool run pyright --pythonpath .venv/bin/python veadk/cli/studio_dependencies.py tests/cli/test_studio_dependencies.py` | pass：0 errors |
| 相同 Pyright 命令加上 `tests/cli/test_studio_deploy_target.py` | fail：1169、1366、1713、2424 行共 10 项历史错误；临时目录中的未修改 HEAD 文件复现完全相同的诊断 |
| `uv run --extra dev pre-commit run --files <全部五个改动文件>` | pass：Ruff 检查/格式和密钥扫描通过；YAML 钩子 not_applicable（无 YAML 文件） |
| `git diff --check`、双语内容/标识符/链接审查 | pass |

```bash
uv run --extra dev pytest tests/cli/test_studio_dependencies.py tests/cli/test_studio_release.py tests/cli/test_studio_deploy_target.py tests/cli/test_studio_sidecar_prerequisites.py tests/cli/test_studio_offline_runtime.py tests/test_openviking_knowledgebase.py tests/test_openviking_long_term_memory.py -n 2 -q
```

首次使用未固定版本的 Ruff 报告 8 项问题；使用仓库要求的 0.11.12 后检查通过，
无需无关修改。原有部署测试类型错误保留并如实报告，不宣称该检查通过。
T-1 至 T-3、AC-1 至 AC-3 已完成；实际部署仍在本次变更范围之外。
