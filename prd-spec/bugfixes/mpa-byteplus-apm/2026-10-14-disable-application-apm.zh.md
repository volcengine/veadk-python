# 关闭 BytePlus Studio 配置中的应用 APM

[English](2026-10-14-disable-application-apm.md)

变更 ID：mpa-byteplus-application-apm。日期：2026-10-14。状态：superseded。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-17。
后续变更：[恢复应用 APM](2026-10-14-restore-application-apm.zh.md)。

## 背景、目标和范围

一个 BytePlus Runtime 在 APM GetAppKey 返回 InternalServiceTimeout 后，因 Agent 初始化失败而退出。内置海外配置从国内继承了 ENABLE_APMPLUS=true 和 FORCE_APMPLUS_EXPORTER_REGISTRATION=true。用户明确同意将这两个 BytePlus 默认值改为 false，测试应用启动。本文不保留生产日志、凭据或签名 URL。

目标：BytePlus 托管 Studio 创建默认不再请求初始化应用 APM。真实验证表明 `ApmplusEnable=true` 会将 Runtime 的 `ENABLE_APMPLUS` 重写为 `true`，因此 BytePlus 控制面设置也必须为 false。非目标：修改国内默认值、通用智能体、Worker 观测、agentkit-mpa-agent 代码、重试/网络恢复或已有云资源。

## 需求和场景

- FR-1：使用内置 BytePlus 配置时，解析后的 Runtime 环境和部署请求中 ENABLE_APMPLUS 与 FORCE_APMPLUS_EXPORTER_REGISTRATION 都为字符串 false。
- FR-2：使用内置火山配置时，两个应用开关及 ApmplusEnable 均保持 true。使用 BytePlus 时，两个应用开关及 ApmplusEnable 均为 false。每次调用返回独立配置，平台之间不能相互污染。
- FR-3：保留可信服务端显式配置覆盖、现有请求哈希、取消和部分失败处理。不修改 API、凭据、数据库结构或任务状态。不自动更新已有 Runtime，也不绕过未完成部署的配置冲突。

## 设计、影响和任务

T-1：在 tests/integrations/mpa_managed/test_byteplus.py 添加先失败的平台参数化回归，检查原始默认值、解析配置及 apply_runtime_settings 输出，不调用云接口（FR-1/FR-2）。
T-2：在 studio_profile_values 现有 BytePlus 分支覆盖两个应用键及 `apmplus-enable`（FR-1/FR-3）。维护 CON-17 和双语托管 README，说明平台差异。
T-3：执行目标测试、两进程托管/启动回归、变更文件 Ruff/Pyright、范围密钥扫描和双语/链接/空白检查。不修改前端产物；没有前端或 HTTP 接口变化，浏览器与构建检查不适用。

## 评审、风险和验收

用户批准：2026-10-14 明确要求关闭两个 BytePlus 开关，并在真实证据表明平台会覆盖后要求关闭 BytePlus `ApmplusEnable`。直接设计评审（review-spec 不可用）：已检查范围、配置优先级、平台隔离、安全、兼容性、测试和双语一致性，无阻塞项。不新增依赖或敏感值。BytePlus 应用及平台 APM 初始化均关闭，火山引擎保持不变。这不证明启动、OV 或聊天成功，也不解决其他已诊断故障。Runtime 设置变化可能与未完成部署哈希冲突；本次试验应使用新请求。

- AC-1：BytePlus 解析环境和请求包含两个 false 值。
- AC-2：国内环境与平台 ApmplusEnable 不变；BytePlus ApmplusEnable 为 false；多次加载平台配置保持隔离。
- AC-3：本地检查通过；真实验证单独报告，不执行云写入。

## 验证与交付

2026-10-14，基于 2ffe6e14 的本地差异：not_run，实施检查待执行。not_run，真实创建/重启/提交/推送及全文件 pre-commit，均未要求。not_applicable，前端/浏览器/构建和 harness smoke，未修改这些边界。保留无关本地改动。

2026-10-14 结果，基于 2ffe6e14 的本次局部变更：
- pass：修复前回归复现一项 BytePlus 失败，国内用例通过。
- pass：`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_config.py`，105 项测试。
- pass：`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`，1,093 项测试、四项依赖弃用警告；依据本地环境选用两个进程。
- pass：对 studio_profile.py 与 test_byteplus.py 执行 Ruff 0.11.12 check/format 和 Pyright `--pythonpath .venv/bin/python`，零错误/警告。
- pass：在隔离快照中按仓库配置执行本次源码/测试/文档的 Gitleaks hook；双语需求/任务/验收标识、相对链接与差异空白检查通过。
- not_run：真实云启动与聊天；用户将重启 Studio 并提交新请求。没有修改云资源、任务记录或服务。未要求提交/推送，因此同步和全文件 pre-commit 仍为 not_run。
最终评审：生产代码仅修改两个 BytePlus 应用开关。国内与平台 APM 保持原值；没有绕过重试，也不修改前端产物、依赖或通用智能体。本地证据满足 AC-1/AC-2/AC-3；真实部署仍未验证。
