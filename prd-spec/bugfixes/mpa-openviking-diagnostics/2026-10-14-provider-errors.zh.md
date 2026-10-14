# 保留 OpenViking 云端错误诊断

[English](2026-10-14-provider-errors.md)

变更 ID：mpa-openviking-diagnostics。日期：2026-10-14。状态：implemented；未进行真实复现。
组件契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-10 和 CON-18。

## 证据与范围

一次 BytePlus 创建在 CreateOpenVikingCollection 返回 provider_error。任务未保留结构化云端错误码或 Request ID，随后不确定建库保护显示 openvikingCreateUnknown。只读账号/地域列表返回零个库，但无法据此恢复原始拒绝原因。用户在此诊断后要求补错误日志。本次为两个 OV 适配器保留安全错误元信息，不改变建库参数、模型接入点、错误分类、重试条件、资源绑定或不确定建库恢复。历史错误无法还原。

## 需求与场景

- FR-1：结构化 OV 响应错误在现有诊断事件中保留接口操作、安全云端 errorCode 和 Request ID。结构化 HTTP/SDK 异常响应体采用相同提取方式；格式错误的响应体及传输异常仅发送现有分类，不发送原始文本。
- FR-2：仅允许非敏感、有界错误码（1–128 字符，以大写字母开头的 ASCII 标识符，可用点或下划线分隔）和现有十六进制/UUID Request ID。拒绝任意文本、凭证形式的值、URL、多行和超长输入。绝不记录云端 Message、请求/响应体、模型凭证、鉴权头或异常文本。
- FR-3：诊断事件增加可选 errorCode，SQLite 追加 error_code 列。兼容旧四字段及 requestId 事件，保留旧记录，每个任务仍最多保留 100 条诊断；父进程结合任务/阶段记录已验证元信息。公开任务响应不变。
- FR-4：保持国内和 BytePlus 建库行为、读取重试上限、单次建库提交、取消与防重复建库保护。OV 面向用户的错误仍为枚举文案。

## 设计与影响文件

T-1（FR-1/FR-4）：在 managed/openviking.py 中仅从结构化 JSON 响应体提取安全元信息；成功响应缺少 Result 或 Result 格式不正确时，若存在 Request ID 则保留。云端传输与建库载荷不变。
T-2（FR-2/FR-3）：扩展 managed/diagnostics.py 的验证/报告及 managed/tasks.py 的持久化/日志；在子进程/父进程边界验证数据。现有 IAM、Worker 诊断继续兼容。
T-3（全部需求）：新增 tests/integrations/mpa_managed/test_openviking_diagnostics.py，使用模拟响应覆盖两个提供商的错误、异常/传输故障、恶意元信息、不确定建库防重复、诊断持久化及旧表迁移。先运行失败回归，再运行受影响 MPA 测试和静态/密钥检查。
T-4：同步双语设计及 CON-10/CON-18。任务 HTTP 字段和 UI 行为不变，因此无需前端产物或 Runtime 改造。

## 评审、风险与验收

批准记录：用户在 2026-10-14 要求补 OV 创建错误日志，接受此前提出的诊断记录方案。review-spec 不可用，已直接评审：仅结构化提取、密钥排除、追加表结构、旧版本兼容、诊断上限及不变的云端副作用；双语文档语义一致，无阻塞项。

- AC-1：模拟 BytePlus 或国内云端拒绝时输出可用于定位的 operation/category/errorCode/requestId，云端文本和凭证不会进入日志、事件或错误文案。
- AC-2：无效元信息被忽略，旧事件被接受，新字段在隔离任务库重开后仍存在，迁移保留旧记录。
- AC-3：传输故障、读取重试及不确定建库防重复行为不变。
- AC-4：受影响 Python 测试、Ruff/Pyright、空白、双语契约及密钥检查通过。真实云端写入、服务重启、重置失败任务、提交和推送均不在本次范围内。

真实复现需加载修改后再次提交新的请求；现有不确定任务不会自动重复建库。代码验证不能证明海外模型接入点可用。

## 验证

2026-10-14，基于 2ffe6e14 的本地差异，保留无关改动。pass：首次回归复现 10 个失败；实现后受影响 MPA/启动套件通过 1,040 项测试，含 4 条依赖警告（`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`，两个 worker）。随后补充两项结构化 SDK 响应体场景，日志专项套件共通过 20 项（`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_openviking_diagnostics.py`）。pass：全部四个修改的 Python 文件通过 Ruff 0.11.12 检查/格式及 `uvx pyright --pythonpath .venv/bin/python`（零错误/警告）。首次 Pyright 未指定仓库解释器而无法解析依赖，显式指定后解决，未改变机器全局配置。pass：11 个范围内文件在隔离暂存副本中通过仓库 Gitleaks hook，无密钥。pass：双语文档标识/链接及差异空白检查。not_run：全仓/全文件 pre-commit，因为未要求提交，本次使用受影响 Python/静态/密钥检查覆盖范围。not_applicable：前端/浏览器/Codex/Harness 检查，因为未改 UI、产物或执行契约。not_run：云端建库及真实错误复现，未获额外写入授权。
