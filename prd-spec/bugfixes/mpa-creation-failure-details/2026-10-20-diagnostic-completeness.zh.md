# 补齐 MPA 异常诊断

[English](2026-10-20-diagnostic-completeness.md)

- 变更：mpa-diagnostic-completeness；日期：2026-10-20；状态：implemented。
- 前序：[失败展示](2026-10-20-failure-details.zh.md)。
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。

## 证据、范围和批准
BytePlus 实际重试在 IAM 和 Runtime 准备阶段停止，只记录 provider_error。IAM 替换原始异常并抑制异常链；Runtime 凭据及客户端准备可能遗漏操作诊断。失败详情标题和定义列表继承了比 13px 原因段落更大的字体。用户于 2026-10-20 明确要求补齐诊断并统一字号，已批准此范围，无需重复确认。

## 需求和场景
FR-1：SDK/HTTP 包装异常在上下文被丢弃前保留有界的异常类型、HTTP 状态、归一化响应类型以及已有错误码/Request ID。从有界 SDK JSON 参数及可用响应头提取结构化标识。未知异常类归一为 Exception；不持久化或展示任意消息、响应体、请求头、凭据、SQL 和堆栈。
FR-2：区分加载凭据、STS 身份校验、Runtime 客户端初始化与实际 Runtime 操作。保留原异常、IAM 错误键及类别、既有重试和控制流，不增加云调用或重试。外层重复上报保留原始诊断。
FR-3：以 SQLite 增量字段保存可选诊断，写入和读取均校验，通过既有任务 API 返回并加入展开及复制内容。兼容旧行和事件；尝试游标、属主校验、历史条数限制不变。
FR-4：详情标题、标签、值和复制反馈使用 13px、1.6 行高，与已有原因段落一致。复用既有失败组件及 Button，不覆盖全局或共享组件。成功、取消、通用智能体及操作按钮行为保持不变。不添加建议区。

## 设计和任务
T1：先补失败回归测试，覆盖 HTTP 包装异常、未知类及敏感值、STS 异常、诊断持久化重新读取、前端复制和展示边界。T2：扩展 managed 诊断、IAM 包装、Runtime 准备边界、任务持久化和类型、MPA 展示及翻译。T3：运行定向和 managed Python 回归、Ruff/Pyright、前端测试/构建/国际化/产物检查，并用隔离浏览器检查字号、键盘、复制、窄窗口。T4：同步双语契约及验证记录。
使用固定异常类型链（最多八项）、100–599 整数 HTTP 状态和归一化响应类型枚举。不重新开启原始 stderr 保存。既有影响重试的 failure_identifiers/classify_error 行为不变；诊断补充独立处理。新增字段均可选，不修改云端表结构或凭据。Exception 捕获不拦截取消。

## 审查、风险和验收
直接审查（review-spec 不可用）已核对安全、兼容、终态传播、取消、迁移、双语一致性，无阻塞。SPEC 引用的前端设计技能文件在本地不可用，采用已有组件及 SPEC/Foundation 字体规则，不引入新设计体系。
AC-1：模拟 SDK 包装 HTTP/JSON 异常能通过任务传到 UI，保留安全诊断且不含敏感文本。AC-2：STS 异常保持原异常对象并独立标识，调用次数不变。AC-3：旧 SQLite 行及重试兼容，不展示旧诊断。AC-4：真实浏览器确认字号一致、换行、展开/复制及成功时隐藏。历史丢失异常无法恢复，提供方也可能不返回 HTTP 信息。本次改善可诊断性，不直接修复云接口可靠性。

## 验证
见下方最终验证；不需要且未授权变更真实云资源。保留无关本地改动。未要求提交或推送。

## 最终验证及审查（2026-10-20）
范围：feat/from-upstream-main-20261020 工作区的诊断补齐改动；保留无关改动。
- pass：先失败回归复现丢失异常字段及 STS 来源。最终定向命令 `uv run --no-sync --extra dev pytest tests/integrations/mpa_managed/test_creation_failure_details.py tests/integrations/mpa_managed/test_iam_retry.py tests/integrations/mpa_managed/test_runtime_diagnostics.py -q`：73 项通过。
- pass：`uv run --no-sync --extra dev pytest -n 2 tests/integrations/mpa_managed -q`：1,176 项通过，两条上游 OpenTelemetry 弃用警告。原诊断精确预期补入新增字段，仍断言重试调用次数及间隔。
- pass：`npm --prefix frontend test`：1,389 项 Node 测试和 146 项 Vitest 测试通过。最后新增非法展示值用例后，`cd frontend && npx vitest run tests/mpaCreationFailure.test.tsx`：18 项通过。
- pass：修改文件的 Ruff 0.11.12 和使用 `.venv/bin/python` 的 Pyright 零错误/警告。`npm --prefix frontend run build`、`check:i18n`、`test:webui-assets` 通过，已重新生成 WebUI。构建仍有既有的大体积 chunk 警告。
- pass：隔离真实浏览器加载实际组件、翻译和 CSS：原因/标题/详情标签和值均为 13px、20.8px 行高；320px 容器无横向溢出；键盘展开、复制、成功/运行/取消时隐藏及返回失败状态通过。截图 `/tmp/mpa-diagnostic-font-preview.png` 仅含模拟数据。临时页面、服务和浏览器标签已清理。输入法不适用。
- pass：双语标识、相对链接及 `git diff --check`。
- fail（已核对为误报）：临时 Gitleaks v8.24.2 扫描变更源文件/测试/设计及生成 WebUI，在压缩 MarkdownPromptEditor 中命中一处 generic-api-key。只读比对确认 HEAD 已存在完全相同的不带引号的 JavaScript 表达式，不含字符串字面量或凭据。未绕过扫描规则，也未为了消除告警改写无关生成代码。
- not_run：真实云创建/重试（需用户重启 Studio 并重试原任务）；无关 Python 全仓测试及 all-files pre-commit（本次未要求提交）。未改变资源或重试策略。
直接审查确认安全证据穿过 IAM 异常替换及终态上报、SQLite 迁移保留旧行、准备阶段标识不改变异常及调用次数，原始异常文本/响应体/请求头和密钥不进入页面。范围内实现任务完成；历史根因仍无法还原。
