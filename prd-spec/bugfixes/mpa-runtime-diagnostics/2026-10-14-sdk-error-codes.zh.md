# 保留 MPA Runtime SDK 失败错误码

[English](2026-10-14-sdk-error-codes.md)

变更 ID：mpa-runtime-diagnostics。日期：2026-10-14。状态：implemented；等待真实重试。
组件契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-10。

## 证据、范围与批准

一次 BytePlus 无 OV 请求初始化业务库和 Skill Space，保存 pending 创建意图后失败，没有 Runtime ID。SDK 错误被简化为 provision/provider_error。AgentKit ApiError 保留 error_code，但 Runtime 适配器未记录。用户明确批准先补日志，再重试同一任务。review-spec 不可用，已直接评审有界安全元信息、旧诊断兼容和不变副作用，无阻塞项。

## 需求、设计与任务

- FR-1 / T-1：RuntimeCloud.call 使用现有诊断通道记录 create_runtime/update_runtime 失败。这也是启用发布的请求，当前创建链路未调用单独 release API。保留分类、经过验证的 SDK errorCode，以及 SDK 暴露时的 requestId。最多遍历八个异常/cause，拒绝循环，复用现有验证器。不解析异常文本，不发送请求体、凭证、鉴权头、云端 Message 或 ClientToken。
- FR-2 / T-2：重新抛出原异常；成功、取消、请求序列化、提供商选择、超时、调用次数和 SDK 重试行为不变。不修改已保存输入或 pending 绑定/token。Skills/其他操作保留现有诊断行为。操作白名单仅增加两个名称，现有诊断持久化已支持这些字段。
- FR-3 / T-3：先编写隔离失败测试，覆盖两个提供商、创建/更新、直接/包装/不安全错误码、缺少 Request ID、传输/取消、载荷不变和成功结果。运行 MPA/启动测试、Ruff/Pyright、密钥扫描及双语检查，同步 CON-10 和模块 README。前端/通用智能体和云端契约不变。

## 验收与风险

AC-1：模拟 Runtime SDK 拒绝通过持久化诊断通道保留 operation/category/errorCode 和可选 Request ID，不含云端文本或密钥。
AC-2：保留原异常/载荷及单次调用，遍历有界且防循环，成功/取消不记录失败，不增加重试/清理副作用。
AC-3：受影响检查通过并记录真实证据。实现期间不提交/推送、不重放真实接口、不重启服务、不写云资源。

历史异常无法还原。当前 AgentKit SDK 的部分 ApiError 不暴露结构化 Request ID，不能伪造。用户需加载更新后的后端后重试。原 ClientToken 语义和绑定校验继续生效。补日志不代表已修复尚未确认的真实云端原因。

## 验证

2026-10-14，基于 2ffe6e14 的本地差异，保留无关工作。not_run：等待实现检查。前端/浏览器/Harness/Codex 检查 not_applicable，因为行为不变。真实 Runtime 创建/重试 not_run，实现后由用户复现。

2026-10-14 验证：pass，首次隔离回归在实现前复现 11 个失败。pass，Runtime/OV 诊断专项 32 项。pass，`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`（1,057 项，4 条依赖警告，两个 worker）。pass，两个修改模块及新测试通过 Ruff 0.11.12 检查/格式和指定 `--pythonpath .venv/bin/python` 的 Pyright（零错误/警告）。pass，10 个范围内文件的隔离副本通过仓库 Gitleaks hook，无密钥。pass，双语标识/链接及差异空白。全仓/全文件 pre-commit not_run，因为未要求提交，使用受影响回归/静态/密钥检查覆盖范围。真实云端创建/重放及服务重启 not_run，由用户重启后重试原任务。

后续：SDK 对非 200 响应抛出的 Exception(bytes) 没有结构化属性。最初仅读取属性的限制由[有界 JSON 解码](2026-10-14-sdk-json-and-restore-ov.zh.md)补齐；本文保留最初设计与验证历史。
