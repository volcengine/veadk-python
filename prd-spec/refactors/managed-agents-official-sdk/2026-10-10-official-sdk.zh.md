# 官方 Anthropic SDK 适配验证

[English](2026-10-10-official-sdk.md)

变更 ID：`managed-agents-official-sdk`。创建/修订：2026-10-10。状态：implemented。

## 背景与范围

原示例 Dockerfile 安装相邻仓库的定制 Anthropic wheel，以提供
`anthropic.lib.environments._dispatcher`。迁移后的 Worker 已使用发行版
`anthropic==1.3.0` 与 VeADK dispatcher；锁定 wheel 哈希与
[PyPI](https://pypi.org/project/anthropic/1.3.0/) 一致。用户此次要求研究并实现官方
SDK 下的同等功能，可考虑 Python 扩展技术。用户随后批准镜像发布、指定 namespace 的本地 Kubernetes 部署与真实 SDK
验收；云 AgentKit 部署仍不在范围内。

## 需求与设计

- `FR-1`：安装未修改的官方 SDK；镜像将安装后的 Python 文件与发行物 RECORD 哈希
  比较，拒绝修改过的包内容。
- `FR-2`：环境级轮询使用生成的 `work.with_raw_response.poll`，保留 HTTP 204、
  严格 Work 校验、作用域认证、路由头、租约、取消与就绪语义。账号级
  `/v1/model-work/poll` 是 VeADK 网关扩展，用官方支持的 `client.get` 访问，不能
  宣称为 Claude 官方端点。
- `FR-3`：测试调用真实 VeADK scoped-client 适配器，不再导入 SDK 私有认证 helper。
  清除父客户端认证，传输层 Identity 注入保留 Runtime 网关与 Work 租约的双重认证。
- `FR-4`：构建指南说明原始依赖、官方安装方式、扩展边界和仍存在的版本敏感 helper。

采用组合。官方 EnvironmentWorker 没有任意 handler 回调，继承需要覆盖私有执行
方法与 SessionToolRunner 行为；全局 monkeypatch 会影响无关客户端。公开请求头、
HTTP client 和 raw-response 配置足以完成传输扩展，无需修改 SDK 源码。
`ToolError` 改用 tools 公开导出。发行版内部 `_download_and_extract` 仍需保留，
因为公开 download_session_skills 会跳过下载失败的固定 Skill；此依赖明确记录，
并用真实 SDK 归档测试验证。

## 任务与验收

| 任务 | 需求 | 文件与验证 |
| --- | --- | --- |
| `T-1` | `FR-1` | Docker SDK 完整性检查器、镜像安装门禁、修改文件反例测试 |
| `T-2` | `FR-2`、`FR-3` | dispatcher 与 Identity 协议测试：公开生成轮询、空/错误响应、全部请求头及凭据刷新 |
| `T-3` | `FR-4` | 双语构建指南、Runtime 契约与本设计；链接及空白检查 |

`AC-1`：未修改的安装包通过，SDK 文件被修改时完整性检查失败。
`AC-2`：锁定官方 SDK 的 Runtime/MPA 定向测试通过，包含 Python 3.10。
`AC-3`：pre-commit、Docker 构建及隔离导入通过；无私有 wheel 输入、版本变动、
SDK 源码覆盖或云端修改。云 E2E 为 not_run。

## 审查与风险

用户明确要求研究后实现，延续已批准的官方 SDK 迁移方案。直接审查确认公开
raw-response 支持与组合可行性；当前无 review-spec skill。同步更新 Runtime
双语契约以覆盖 FR-1/FR-2；其他资源与模型契约保持不变。SDK 内部 helper 名称仍有
版本敏感性，由锁定版本与集成测试控制风险。RECORD 校验检测已安装文件被修改，
锁文件中的官方发行物哈希在安装时验证来源；两者均不能证明服务端行为。
不记录真实凭据或端点。


独立审查还发现官方内部清理 helper 会输出原始异常。`T-2` 增加本地清理适配，调用 close/aclose 并保留额外 context-manager 退出，仅报告异常类型，传播取消；回归验证清理继续且不泄漏异常文本。

## 交付证据


- **pass（2026-10-10）**：Python 3.12 定向测试 213 项；Python 3.10 官方 SDK 适配
  子集 109 项，增加本地模型凭据 opt-in 后另跑 41 项凭据测试。全文件 pre-commit 通过。
- **pass**：发布固定 digest Worker 镜像；官方 SDK 1.3.0 的 1389 个 Python 文件
  均匹配 RECORD。K8s 内 Worker 的 dispatcher/worker/Identity/Session 源码哈希
  与本地一致，目标 namespace 内已 Ready。独立安装官方 SDK 1.5.0 验收客户端，
  保留 AKX 原有版本。
- **pass**：用户明确批准清理单个历史 Key；复核归档与零活跃状态后删除成功，
  专用环境 Key 创建成功。官方 SDK 1.5 完成两轮真实模型对话、六种原生工具、
  固定版本 Skill、跨 Worker 续接与模型 Work stopped 验证；自建 Session/Agent/Skill
  清理成功。另修复官方 SDK 工具 configs 的 type 判别，兼容 legacy name，
  真实 SDK 对象回归已计入 213 项测试。公网 APIG、云 Identity 与远程工具不在本次证明范围。


## 已授权的本地 Kubernetes 部署

用户随后授权部署 `ma-infra-stg-zn-ppe`，部署资产放在
`/home/mofanke/gitcode/akx`，最终用官方 Anthropic SDK 验收。`T-4` 新增限定到专用
Environment 的 Worker 与 VKE 模板；保存现有 Helm revision/镜像，保留后端、前端与
云 Runtime 默认配置。官方 SDK 创建独立资源，验证真实 Work 轮询、模型/工具事件、
两轮续接与固定版本 Skills。

当前 Worker 即使在本地 VKE 也要求 Session 模型 Identity。增加显式选择
`MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE=environment`，仅用于非 AgentKit 且无
provider 引用的 Session，只读取 `MODEL_AGENT_API_KEY`。默认 `session` 保持
Identity 行为；AgentKit 或任何显式 provider 引用始终使用 Session Identity，
不允许兜底。未知来源或缺少 Key 明确失败。模型 Key 由独立 Kubernetes Secret
提供，不进入仓库文件。本次验收证明配置的模型凭据，不证明云 Runtime Identity。
回滚删除新 Worker 并恢复明确改过的配置；清理测试 Agent/Session/Skill。
