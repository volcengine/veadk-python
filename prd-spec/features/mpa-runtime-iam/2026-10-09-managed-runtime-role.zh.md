# 自动准备 MPA 运行角色

[English](2026-10-09-managed-runtime-role.md)

变更 ID：`mpa-runtime-iam`；创建/修订：2026-10-09；状态：已实现，隔离验证通过，真实 smoke 未验证。
契约：[Studio 创建](../../../specs/studio-mpa-creation/README.zh.md)、[资源准备](../../../specs/mpa-runtime-provisioning/README.zh.md)。

## 背景、目标与边界

内置 Studio 配置为 Runtime 和 Worker 指定 `IDRoleForArkClawShareAgent`，但没有准备角色，新部署账号可能因此创建失败。历史角色的只读核对确认了 `vefaas`、`apig` 信任及 12 个系统策略；不复制历史测试/IDrive 策略。

在其他资源变更之前准备已批准角色。这不代表整个北京配置已支持任意账号：账号断言、镜像、Worker 参考模板仍须配置有效。通用智能体、旧 CLI 默认行为、自定义角色、已有信任文档和策略内容不属于自动改写范围。设计批准不授权真实 IAM 变更、提交、推送或部署。

## 场景与要求

- FR-1：内置 Studio 使用 `managed.iam.mode: auto`；显式 managed 配置默认 `existing`，跳过 IAM 准备。auto 只接受默认 Runtime/Worker 角色及全新模板来源；不兼容来源在 IAM 请求之前失败。
- FR-2：在 STS 核验的部署账号下查询或创建默认角色，无条件信任 `vefaas` 和 `apig` 的 `sts:AssumeRole`。已有信任必须包含两者且没有拒绝语句；不重写。校验返回角色名及账号 TRN。
- FR-3：补齐 12 个约定系统策略及版本化自定义策略 `VeADKMPARuntimeAccessV1` 的 Global 绑定，保留额外绑定。自定义策略包含 14 个已批准动作，资源为 `*`；已有内容冲突则失败，不覆盖。
- FR-4：仅明确对象不存在响应允许创建；创建竞态的 already-exists 响应后重新读取。有限轮询处理可见性延迟；超时/取消保留资源，同一智能体 ID 可重试。每次请求使用新核验凭据、独立 SDK 实例和传输超时。
- FR-5：输出阶段 `iam_role` 及权限、信任/策略冲突、属主、核验失败等白名单错误。禁止输出原始 SDK 文本、文档、凭据。失败后不准备 PG/网络/Runtime。
- FR-6：Studio 执行策略增加 `iam:CreatePolicy`，其他所需 IAM 动作已存在。部署凭据须能查询/创建角色和策略、查询绑定、绑定策略。配置检查不调用 IAM。

## 权限基线

系统策略：`AgentKitSkillsSandboxAccess`、`AgentKitToolAccess`、`LLMShieldProtectSdkAccess`、`Mem0ReadOnlyAccess`、`AgentKitRuntimeAccess`、`AgentKitTosAccess`、`CloudControlReadOnlyAccess`、`TorchlightApiFullAccess`、`IDReadOnlyAccess`、`VikingdbFullAccess`、`APMPlusServerDataExportRolePolicy`、`AgentKitReadOnlyAccess`。

自定义动作：`arkclaw:ListResources`、`arkclaw:GetMpaInstanceConf`、`apig:ListGateways`、`apig:GetGateway`、`apig:CreateGateway`、`apig:CreateIMChannelGateway`、`apig:GetIMChannelGatewayStatus`、`apig:CreateUpstream`、`apig:CreateRoute`、`agentkit:DeleteSession`、`agentkit:PauseSession`、`agentkit:ResumeSession`、`agentkit:SetSessionTtl`、`agentkit:CreateSessionSnapshot`。

这是用户批准的兼容基线，不宣称最小权限。ArkClaw 动作为兼容权限。IAM 资源为账号级，不随部署地域隔离。

## 设计、任务及影响文件

- T-1（FR-1–6）：实施前评审双语设计并更新两个组件契约。
- T-2（FR-1–4）：先添加隔离的失败测试；实现 `managed/iam.py` 及配置/profile 接入。采用增量补齐与回读，而非复制历史测试策略或覆盖用户信任。最多轮询 120 秒，每次 SDK 请求连接/读取超时各 5 秒。取消后停止新操作；进行中的同步 SDK 调用可能在传输时限内完成。
- T-3（FR-5–6）：在 `managed/service.py` 提前接入，通过 `runner.py`/`tasks.py` 传递安全错误，更新诊断、双语 UI 资源及 `frontend_deploy_policy.py`。
- T-4：更新双语使用说明、针对性 Python/前端测试；构建发布资源，用隔离模拟响应验证浏览器。

不增加持久表或公开请求字段，已有 IAM 状态即恢复记录。固定名称保证角色/策略创建幂等；同账号并发创建通过回读收敛。取消不回滚共享权限。不支持的信任格式保守失败。

## 验收与验证

AC-1：新建角色绑定全部 12 个系统策略及自定义策略，回读核验。AC-2：复用、缺少绑定、竞态及延迟可见均可收敛，不移除额外绑定。AC-3：权限错误、账号错误、不安全信任及策略冲突在其他资源变更前失败，返回安全错误。AC-4：existing 配置及通用智能体保持原行为。AC-5：双语 UI 显示角色阶段/错误，构建资源与源码一致。

命令：`uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py`；变更文件 Ruff/Pyright；`npm --prefix frontend test`；`npm --prefix frontend run build`；`npm --prefix frontend run test:webui-assets`；`npm --prefix frontend run check:i18n`；回归 `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"`。真实新账号 IAM smoke 在单独授权之前为 not_run。浏览器验证不触碰真实 IAM/用户状态。

## 风险与评审记录

某些系统策略可能在账号中不可用或需要开通产品；明确失败，管理员修复后重试。不自动放宽已有信任限制。广泛权限基线属有意选择并已记录，不提交真实云端快照。共享角色变更会影响使用该角色的其他服务。SDK 单例隔离和取消需要回归覆盖。

直接设计评审（review-spec 不可用）：已检查范围、增量语义、有限重试、凭据刷新、不输出密钥、旧行为兼容、测试及双语等价，无未解决设计阻塞。用户已批准权限增加，并以“嗯，帮我改下，”授权实施，批准先于生产/测试修改。保留用户已有 `frontend/package-lock.json` 修改。

## 实施评审与验证结果

验证范围：`feat/test-main` 上未提交的 `mpa-runtime-iam` 功能，基线 `ef0ad519`，日期 2026-10-09。T-1–4、AC-1–5 已由隔离测试及浏览器检查覆盖，真实新账号就绪仍未验证。

实施评审修正了云端绑定格式 `PolicyScope[].PolicyScopeType: Global`，以及官方创建冲突码 `PolicyAlreadyExist`。`PolicyAttachConflict` 必须回读，不能视为已成功。来源：[官方 IAM 错误码](https://docs.volcengine.com/docs/IAM/ErrorCodeList?lang=en)、[官方 SDK 绑定结构](https://pkg.go.dev/github.com/volcengine/volcengine-go-sdk@v1.2.45/service/iam#AttachedPolicyMetadataForListAttachedRolePoliciesOutput)。新增测试先因未实现失败，随后因真实冲突码失败，修正实现后通过。权限错误不允许创建。已评审单例隔离、凭据刷新、超时/取消、信任/账号冲突、项目级绑定、重试和安全子进程错误。本功能范围内无剩余阻塞问题。

| 检查 | 结果 | 证据 / 限制 |
| --- | --- | --- |
| `uv run --extra dev pytest tests/integrations/mpa_managed tests/cli/test_frontend_deploy_iam.py -q` | pass | 最终修正后 474 项通过，不调用真实云端。 |
| `uvx --from ruff==0.11.12 ruff check <changed-python-files>` 及 format | pass | 版本与仓库钩子一致，使用临时工具环境。 |
| `uvx pyright --pythonpath .venv/bin/python <changed-production-python-files>` | pass | 0 错误 / 警告，使用仓库解释器。 |
| `npm --prefix frontend test` | pass | 1,377 项 Node 测试及 48 项 Vitest 测试。 |
| `npm --prefix frontend run build` | pass | TypeScript 及两个 bundle 构建成功，仅有已有体积/弃用警告。 |
| `npm --prefix frontend run test:webui-assets` | pass | 113 个文件，350 个引用。依赖 chunk 的哈希重命名属于生成资源。 |
| `npm --prefix frontend run check:i18n` | pass | 2 种语言、21 个命名空间一致。 |
| 隔离真实 Chrome 浏览器（`node /tmp/mpa-iam-browser.cjs`） | pass | 中英文三步流程、只读 ID、IAM 错误/阶段、Enter 键同 ID 重试、取消、375px 布局，全部服务响应为模拟。临时页面/服务已清理。测试页面首次加载触发 Vite 依赖优化重载；预热后的最终运行无页面错误。 |
| `uv run --extra dev pytest -n 2 -m "not codex_smoke and not piagent_smoke"` | fail | 较早实施版本：6,240 通过、7 失败、19 跳过、2 xfailed、2 收集错误。6 项 Harness 失败缺少 `llama_index`，2 项自托管沙箱收集错误缺少 `anthropic`。1 项上传重试测试收集到了其他后台线程的 sleep，单独重跑通过（1 项）。这些路径无本功能修改。最终 IAM 竞态修正通过 474 项相关测试验证，未重复受缺失依赖阻塞的无关测试。 |
| `uv run --extra dev pre-commit run --files <changed-python-files>` | pass | Ruff/check/format 和 gitleaks 钩子通过，YAML 钩子跳过（无 YAML 文件）。未请求提交，完整 `--all-files` 为 not_run。 |
| `git diff --check`；双语链接/标识符/权限基线 | pass | 设计/契约成对存在，链接有效，标识符一致。 |
| 真实 IAM / 新账号创建 | not_run | 须单独授权云端变更并准备隔离账号。 |
| Codex/PI smoke、sidecar coverage、IME/空态变更 | not_applicable | 未修改运行时/sidecar/输入/空态契约。 |

本地缺少 Ruff/Pyright，临时工具使用记录在这里，不修改机器全局配置。保留已有 package-lock 修改。未提交、推送或部署。已有云端 Studio 执行策略须增加 `iam:CreatePolicy` 后才能准备角色，本次不会部署该更新。内置配置仍断言配置账号并使用配置的镜像/参考资源，更换账号须独立调整这些设置。

