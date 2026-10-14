# 保留 MPA 重试时自有资源的名称预检

[English](2026-10-14-owned-resource-metadata.md)

变更 ID：mpa-name-retry。日期：2026-10-14。状态：implemented。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-20；前置：[名称预检](../../features/mpa-name-preflight/2026-10-13-runtime-name-and-workspace-labels.zh.md)，FR-3。

## 证据与范围

Runtime 部署后，同一请求重试被 runtimeNameTaken 拦截。已安装 GetRuntimeResponse 不含 Tags，ListRuntimes 则包含；名称检查只从 GetRuntime 要求创建者标签。沙箱创建写入 managed_by=mpa-deployment、mpa_agent_key=agent_suffix(account,region,agent_id)，并在 Envs 写 MPA_AGENT_ID；名称预检却要求创建过程未写入的 MPA_AGENT_ID 标签。现有测试错误模拟了此标签和 Runtime 详情标签。观测到的 Runtime Error／启动失败是另一问题，本次不修复。

目标：恢复已批准的自有资源重试保证，并继续拒绝外部／归属不明的同名资源。不改前端、请求身份、作用域哈希、云端载荷、资源变更、Runtime 启动、账号凭据或通用智能体。用户当前的重试缺陷报告以及此前批准的同请求恢复要求授权此次纠正；修改前已说明按真实元信息修复的具体方案。

## 需求与设计

- FR-1：组合对应 ListRuntimes 条目和 GetRuntime 详情的归属证据。详情 MPA_AGENT_ID 必须匹配；创建者与可选内部实例标签必须匹配。任一响应的创建者／内部实例证据冲突均安全拒绝。全部缺失创建者证据时新请求不允许复用；原意图须满足补充设计中的私有证明。不传 Studio owner 的已有 CLI 行为保持不变。
- FR-2：Worker 身份要求环境变量 MPA_AGENT_ID 和真实 managed_by/mpa_agent_key 标签匹配，使用与创建过程相同的账号／地域／agent suffix。仅有任意旧 MPA_AGENT_ID 标签不足以证明归属。真实标签缺失或外部归属仍拦截。
- FR-3：查询超时／取消、错误键、Workspace 检查、分页、本地名称保留、任务创建者／账号快照及不可变重试输入均不变。不因存在请求 ID 而直接跳过检查，新的同名请求仍失败。

T-1：修正错误 Worker 夹具，在 test_name_preflight.py 先写 SDK 形状的 Runtime／列表标签失败测试，以及外部／冲突／缺失标签场景。T-2：仅修复 names.py，复用已有 suffix／标签方法。T-3：运行目标名称／Worker／任务／路由测试、managed/startup 回归、Ruff/Pyright 及范围内仓库密钥／文档检查；能验证元信息时，对失败任务另行做只读真实预检。

## 契约评估、评审与验收

现有 CON-20 已要求验证自有资源后允许重试，本次修复实现及测试映射，不改变公开契约。仅补双语验证／变更链接。review-spec 不可用，直接评审确认归属要求不减弱、不输出密钥、写操作边界不变及双语等价。解释已有误报，不把误报当作允许接管未知资源的理由。无设计阻塞。

AC-1：真实 SDK 形状的详情缺少 Tags，但对应列表条目证明原请求归属时允许复用；冲突或缺失／外部创建者仍失败。
AC-2：创建过程真实 Worker 标签形状允许复用；外部／缺失标签和仅复制旧标签仍拒绝。国内与 BytePlus 使用相同不变量。
AC-3：必需检查通过；前端／构建为 not_applicable，不重放真实任务、不重启服务、不提交／推送。只读预检证据不证明 Runtime 启动已恢复。

## 验证与风险

2026-10-14，基于 2ffe6e14，保留无关本地工作。not_run：实现检查待执行。not_applicable：前端／浏览器／harness／Codex，UI 和协议不受影响。not_run：全部文件 pre-commit，未要求提交；须执行范围内检查。服务商列表元信息可能最终一致，归属不明仍安全拒绝。名称检查修复后，Runtime Error 仍可能导致就绪失败。

## 云端只读核对后的已批准设计补充

失败的 BytePlus Runtime 的原始 GetRuntime 和 ListRuntimes 均返回空 Tags，仅修正 SDK 形状无法允许恢复。FR-1 细化：仅在服务端认证的原创建意图中，标准化载荷与已存参数完全一致，私有 provider/account/region 快照匹配，且服务端派生的 MPA_AGENT_ID 环境变量匹配时，才允许缺失创建者标签。明确外部／冲突标签仍拒绝。CreationTasks.name_scope_for_request 按创建者／请求读取 SQLite 并拒绝改变指纹。POST 在标准化无密钥载荷后、云端名称检查前调用；公开请求／响应字段不变。名称预检将存储账号与 STS 核对。子进程已从验证的任务快照接收 expectedAccount，将此已有证明传入名称检查，保留全部账号及资源校验。无保存意图的新请求继续严格检查，绝不信任浏览器提供的重试标志。补充影响文件：tasks.py、service.py、frontend/server/mpa_creation.py 和对应任务／路由测试。无需扩展 runner 协议，不执行资源变更、不重建前端。这是此前批准的同请求恢复所必需的补齐，不授权复用外部或归属不明资源。直接评审确认更严格的指纹／账号保护，修正最初对缺失创建者标签的假设，仍须只读实测。

2026-10-14 验证，基于 2ffe6e14 的本地差异：pass，最初测试复现九项失败；补充私有证明连线前复现五项失败。pass，名称／路由目标 37 项；两个 worker 的 managed/startup 回归 1,091 项（四条依赖警告）。pass，实际 BytePlus 只读预检：原存储参数、派生 agent 身份／账号一致，真实 Worker 标签匹配，原名称允许恢复。未启动真实任务、未执行云端变更或服务重启，此预检不修复已观测到的 Runtime Error。最初夹具误用不支持的 Profile.provider 替换和有类型 SDK 构造参数，已改为 values.cloud_provider 和 model_validate。Ruff/Pyright 夹具导入／可空调用断言已在最终检查前修正。最终静态／密钥／文档结果见下方。前端／构建／浏览器／harness／Codex 为 not_applicable：UI 和协议未变，支持 API 有回归覆盖。全部文件 pre-commit／提交／推送为 not_run：未要求执行。保留无关本地工作。

最终检查：pass，六个受影响 Python 文件的 Ruff 检查／格式及 Pyright，零错误／警告；最终名称／路由回归 37 项；隔离范围按仓库配置的 Gitleaks；双语 ID／相对链接及 diff 空白。现有测试／构建密钥扫描排除规则未改变。最终评审确认不增加公开重试证明输入，私有匹配发生在云端检查及任务接受前。范围内无剩余阻塞。
