# 托管 OpenViking 使用 BytePlus 模型标识

[English](2026-10-14-byteplus-model-identities.md)

- Change ID: `mpa-byteplus-model-identities`
- Created/Revised: 2026-10-14
- Status: implemented
- Related spec: [Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

BytePlus 托管 OpenViking 当前将 `OV_VLM_ENDPOINT_ID` 和
`OV_EMBEDDING_ENDPOINT_ID` 默认设为国内 `doubao-*` 标识。对账号
`3001037806`、地域 `ap-southeast-1` 的只读 Ark 查询表明这些标识返回
`NotFound.EndpointId`。真实 OpenViking 资源虽然接受了该配置，但语义入库
超时，Embedding 工作持续重新入队且未生成向量。

BytePlus Ark `CreateEndpoint` DryRun 拒绝国内模型名，并接受
`seed-2-0-lite` 版本 `260428` 和 `skylark-embedding-vision` 版本
`251215`。用户已批准保留当前 API Key 加模型标识绑定，不采用 Coding Plan，
也不创建账号专属 `ep-*` 资源。

## 目标与非目标

目标：

- BytePlus VLM 默认标识改为 `seed-2-0-lite-260428`。
- BytePlus Embedding 默认标识改为
  `skylark-embedding-vision-251215`。
- 保留 API Key 注入、环境变量覆盖、校验、脱敏、重试和非密钥意图持久化。

非目标：

- 不改变国内 OpenViking 默认值。
- 不创建、更新或删除 Ark Endpoint 或 OpenViking 资源。
- 不采用 Coding Plan，也不改变数据面 Base URL。
- 不迁移已有任务或 OpenViking 资源。

## 场景与需求

- `FR-1`：新的 BytePlus 自动 OpenViking 请求未设置覆盖时，VLM 和
  Embedding 凭据使用上述两个 BytePlus 模型标识。
- `FR-2`：`OV_VLM_ENDPOINT_ID` 和 `OV_EMBEDDING_ENDPOINT_ID` 继续覆盖
  默认值并沿用现有校验。
- `FR-3`：解析后的模型 API Key 仅附加到复制的线上请求，绝不持久化。
- `FR-4`：Volcengine 请求和已持久化请求保持不变。

## 设计与契约影响

仅修改 `byteplus_model_endpoints()` 返回的 fallback 值。现有请求构造器、
API Key 注入、注册表比对和云适配器保持不变。已有请求继续保留已持久化标识；
改变其输入仍会产生配置冲突。Studio 重启后创建的新任务取得新默认值。

安全、权限、并发、状态和公开 Python API 均不改变。维护中的 Studio MPA
创建契约需记录新默认值。

## 影响文件与任务

- `T-1` / `FR-1..4`：先更新 BytePlus 回归 fixture 和断言。
- `T-2` / `FR-1..2`：更新 `byteplus_model_endpoints()`。
- `T-3` / `FR-1..4`：同步 Studio MPA 创建双语组件契约。
- `T-4`：运行定向测试、Ruff、Pyright、双语检查和 diff 检查。

## 验证与验收

| 需求 | 验收条件 | 验证 | 结果 |
| --- | --- | --- | --- |
| `FR-1` | 默认请求使用两个 BytePlus 标识 | OpenViking 与 service pytest 测试集 | `pass`：240 项 |
| `FR-2` | 显式覆盖与非法值检查继续受覆盖 | 同一 pytest 命令 | `pass` |
| `FR-3` | API Key 仍仅在线上传递 | 同一 pytest 命令 | `pass` |
| `FR-4` | 国内代码路径不变 | diff 审查及现有 service 测试 | `pass` |
| 质量 | 变更 Python 通过静态检查 | Ruff `0.11.12`、Pyright 和 `git diff --check` | `pass`：0 个错误 |

验收标准：

- `AC-1`：新的 BytePlus 自动请求持久化已批准的模型标识。
- `AC-2`：线上请求包含 API Key，注册表状态不包含 API Key。
- `AC-3`：环境变量覆盖继续具有优先级。
- `AC-4`：实现验证不变更云资源。

## 风险与恢复

云端在建库时接受配置不代表推理一定成功；端到端语义验证需要创建新的隔离
真实资源。已有错误配置资源不做变更。需要回滚时，运维可同时设置两个环境变量
恢复旧行为。

## 评审与交付记录

直接评审确认除 BytePlus 默认值外，不改变 API、凭据、状态机或国内兼容性。
模型标识已通过 BytePlus Ark DryRun 验证。用户于 2026-10-14 批准精确值并
保留 API Key 绑定。实现于 2026-10-14 完成。验证结果：

- `uv run --extra dev pytest tests/integrations/mpa_managed/test_openviking.py tests/integrations/mpa_managed/test_openviking_byteplus.py tests/integrations/mpa_managed/test_openviking_diagnostics.py tests/integrations/mpa_managed/test_service.py -q`：`pass`，240 项。
- 对变更 Python 文件运行 Ruff `0.11.12` check/format 和 Pyright：`pass`。
- 对范围内文件运行 `git diff --check`：`pass`。
- 使用修正标识进行真实创建：`not_run`；需要 Studio 重启后显式创建新的付费 OpenViking 资源。
