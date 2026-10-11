# Studio 使用 STS 核验的部署账号

[English](2026-10-09-sts-account.md)

变更 ID：mpa-studio-account。创建/修订日期：2026-10-09。状态：implemented。

## 证据与范围

内置 Studio 配置固定的预期账号。新账号凭据通过 STS 后，在 `managed/service.py` 的 `checking` 阶段失败，尚未准备 IAM 或其他资源。用户在 2026-10-09 明确要求去掉该内置账号限制。本文件不包含真实凭据或任务载荷。

## 需求与场景

- FR-1：Studio 不预设账号；非空 STS 身份决定 IAM、PG、网络、APIG 和 Runtime 归属的部署账号。
- FR-2：新建 Runtime 的 `CLAW_SPACE_ID` 和 `RUNTIME_IAM_ROLE_TRN` 由核验账号和所选角色生成。内置默认值不以旧账号环境变量覆盖它们。
- FR-3：保留显式 YAML 账号限制、调用方环境变量覆盖、引用/模板 Runtime 行为以及创建期间凭据切换账号的现有检查。
- FR-4：镜像仓库地址和 Worker 参考 ID 是源资源，不是部署身份。保留默认值，不假定新账号存在这些源资源，不宣称已验证跨账号访问。

当 STS 返回另一个有效账号，内置创建应进入 IAM 准备，并在 Runtime 环境变量中使用该账号。当显式 YAML 预期账号不匹配时，仍在资源变更前停止。STS 身份为空或创建中账号变化时，继续按原规则拒绝执行。

## 设计与受影响契约

移除内置 `account-id` 和固定账号派生的环境字段。镜像仓库保留为名称明确的源仓库。新建模板使用所选 Runtime 角色和核验账号生成角色名/TRN；现有 `apply_runtime_settings` 的显式覆盖保持优先。`build_runtime_env` 已根据 STS 账号派生 `CLAW_SPACE_ID`，直接复用。

契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)、[Runtime 部署](../../../specs/mpa-runtime-provisioning/README.zh.md)。不改变 API、数据库结构、前端、任务状态或权限。不包含云资源变更、部署、进程重启、提交或推送。取消及资源清理行为保持不变。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1、FR-2 | T-1：回归测试及配置/模板修复 | AC-1：模拟内置创建无需覆盖账号，IAM 和 Runtime 使用模拟 STS 账号 | managed 配置/共享资源测试 |
| FR-3 | T-2：边界回归 | AC-2：显式账号不匹配在 IAM 前失败；所选角色派生正确 TRN | service 测试 |
| FR-4 | T-3：双语契约及使用说明 | AC-3：保留镜像/参考默认值并记录访问限制 | 文档及差异检查 |

涉及 `managed/studio_profile.py`、`managed/service.py`、managed 测试、两组组件契约和 managed README。运行 `uv run --extra dev pytest tests/integrations/mpa_managed`、变更文件 Ruff/Pyright 和密钥扫描。本次修复不修改 UI 或 web 产物，前端/浏览器/构建检查不适用。未获得隔离真实测试授权时，云端创建为 not_run。

## 审查、批准与风险

直接设计审查（review-spec 技能不可用）：需求与双语契约一致；保留显式 CLI 安全检查、凭据账号变化保护和覆盖规则；不输出密钥，不隐式复制源资源。无阻塞项。用户要求移除内置限制，批准本次限定修复。新账号仍可能在后续遇到源镜像/参考模板访问失败，本次修复不证明完整新账号部署链路。验证记录见下。

## 验证记录

2026-10-09，基于 `ef0ad519` 工作区的账号修复；保留此前 IAM 工作及无关 lockfile 改动。

- pass：修复前配置/共享资源回归出现 5 个预期失败，复现固定账号拦截；实现后相同流程使用模拟 STS 身份，通过 IAM 准备和 Runtime 账号元数据检查。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed tests/integrations/test_mpa_provision_env.py tests/integrations/test_mpa_runtime.py -q`：496 项通过。新增角色测试最初使用了无效 MPA ID 夹具，改为支持的格式后完整目标通过。
- pass：五个变更 Python 文件的 `uvx --from ruff==0.11.12 ruff check` 和仓库 pre-commit Ruff 格式/检查；生产代码 Pyright 首轮通过。测试 Pyright 发现两处既有夹具类型问题及一处新增 AsyncMock 缺失断言，均做最小修复，最终结果见下。
- pass：包含 Python、双语契约、managed README 和本设计的变更文件 `uv run --extra dev pre-commit run --files`：Ruff 和硬编码密钥扫描通过；YAML 扫描 not_applicable（未修改 YAML）。
- not_applicable：前端测试/构建/浏览器、通用智能体聊天及 sidecar 门禁；本修复不改动前端/聊天/sidecar 契约或生成产物。
- not_run：全仓回归和 all-files pre-commit；没有提交请求，限定部署回归覆盖本修复。真实新账号创建、镜像/参考资源访问及服务重启为 not_run；未执行云资源变更。

审查：显式配置仍保留 CLI 账号断言；内置配置不提供断言输入。核验账号继续决定注册表范围及凭据账号变化保护。额外夹具断言/monkeypatch 仅修复受影响测试的类型问题。双语文档及相对链接已同步。

- pass：最终对两个生产文件及三个受影响测试文件执行 `uvx pyright --pythonpath .venv/bin/python`：0 错误、0 警告。夹具修正后执行 `uv run --extra dev pytest tests/integrations/mpa_managed/test_service.py tests/integrations/mpa_managed/test_studio_shared_resources.py -q`：70 项通过。最终变更文件 pre-commit 通过。
