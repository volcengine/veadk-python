# 向 BytePlus Studio Runtime 注入部署账号的 APM AppKey

[English](2026-10-14-server-app-key.md)

变更 ID：mpa-byteplus-server-app-key。日期：2026-10-14。状态：implemented。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-17。
前置设计：[APM 恢复](2026-10-14-restore-application-apm.zh.md)。

## 证据、目标和非目标

Runtime 内置 VeADK 的 GetAppKey 超时时，Agent 初始化失败。使用部署账号对 apmplus-server.ap-southeast-1.byteplusapi.com 的只读探测成功。内置 VeADK 1.1.5 支持 OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY，有值时跳过自动获取；已对安装源码执行隔离验证。本文不记录真实 Key 或生产日志。

目标：Studio 在准备资源前获取 BytePlus AppKey，注入 Runtime Envs。按此前用户要求恢复继承的启用 APM 默认值，替代临时绕过。非目标：修改镜像、全局 VeADK Host 选择、国内/通用智能体/CLI 行为、OTLP 上报地址、沙箱凭据兼容、已有云资源或网络重试恢复。

## 需求和场景

- FR-1：核验部署账号并解析模型 Key 后，Studio BytePlus 创建调用 GetAppKey，service 为 apmplus_server、version 为 2024-07-30、签名地域为 ap-southeast-1、host 为 apmplus-server.ap-southeast-1.byteplusapi.com。每次尝试刷新并核验凭据，传递 STS Token 与 X-Apmplus-Region。在 IAM/PG/网络/资源写入前解析。国内与非 Studio 调用者不调用此辅助函数。
- FR-2：仅接受可用的 data.app_key 字符串；将 OBSERVABILITY_OPENTELEMETRY_APMPLUS_API_KEY 注入 Runtime 创建/更新 Envs。不修改调用者配置，不把原始 Key 持久化到任务/启动/部署记录、浏览器响应、诊断或报告。保留可信配置中的有效显式 Runtime Key；空值走发现，格式错误或遮罩 Key 安全失败。
- FR-3：临时错误最多三次读取，每次 HTTP 连接/读取限制 10/30 秒，异步期限 45 秒；重试间隔 0.2/0.5 秒。取消后不再尝试或写资源。权限、协议和永久服务错误停止，不回退。诊断仅保留白名单 operation/category/attempt/outcome/errorCode/requestId，包含 HTTP 错误元信息。准备资源前抛出安全异常。
- FR-4：恢复 BytePlus ApmplusEnable=true、ENABLE_APMPLUS=true 与 FORCE_APMPLUS_EXPORTER_REGISTRATION=true；国内值、显式配置和平台隔离不变。不升级已提交快照，不更新已有 Runtime。重试重新读取账号 Key；保留未完成请求哈希检查，Key/配置变化时失败，不静默重部署。

## 设计和任务

T-1：先添加失败的隔离辅助函数与服务回归：签名 Host/账号/STS、原始 Key 传递、显式 Key、国内/CLI 排除、错误响应、错误/重试/取消和写资源前失败。更新启用默认值回归（FR-1 至 FR-4）。
T-2：增加小型 managed apm_key 模块，复用签名传输及现有诊断元信息校验，白名单新增 get_apm_key，接入 service.provision。取得的 Key 仅保存在局部变量中，直到构造 Runtime 环境。现有请求/哈希与秘密存储规则不变。
T-3：更新双语 CON-17、托管 README 和 frontend README，记录评审与检查。执行目标测试及两进程托管/启动回归、变更 Python 文件 Ruff/Pyright、仓库配置的范围 Gitleaks、双语标识/链接与空白检查。

## 评审、安全、风险和验收

用户批准：2026-10-14 明确要求实现上述服务端获取/注入 Key；此前已要求撤销 APM 绕过。直接评审（review-spec 不可用）：已检查平台范围、凭据刷新、安全失败诊断、秘密持久化、取消期限、兼容和双语一致性，无阻塞项。Runtime 环境访问仍需特权。部署凭据额外需要 apmplus_server:GetAppKey；不扩展 Runtime 角色策略，不注入长期部署 AK/SK。平台重写禁用 APM 的环境变量，是恢复启用默认值的原因。

AC-1：仅 Studio BytePlus 在写资源前获取 Key，实际 Runtime 请求含该 Key。AC-2：安全失败/取消及秘密排除回归通过。AC-3：国内/通用智能体/CLI 路径与未完成输入保护不变，检查和文档已同步。真实 APM 上报及 Runtime 启动/聊天另行验证。本次不修复已知 BytePlus 沙箱 IAM 缺陷。旧未完成部署的原请求不含此变量，可能需要新请求。

## 验证

2026-10-14，基于 2ffe6e14 的本地差异：not_run，实施检查待执行。not_run，真实创建/更新/重启/提交/推送及全文件 pre-commit，本次实施未授权这些操作。not_applicable，前端/浏览器/构建与 harness smoke，未影响 UI/API/事件边界或产物。保留无关本地改动。

2026-10-14 最终验证（基于 2ffe6e14 的本地差异）：
- pass：实施前回归因模块不存在而收集失败；第一轮实施运行还暴露诊断操作白名单/服务接线缺失，最终测试前已补齐。
- pass：`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_apm_key.py tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_service.py`，213 项测试。随后新增四项隔离/无效显式 Key 用例，最终辅助函数套件 23 项全部通过。
- pass：`uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`，1,112 项测试、两项依赖弃用警告；依据本地资源选用两个进程。此后仅增加测试/文档，执行了目标重跑。
- pass：apm_key.py、service.py、diagnostics.py、test_apm_key.py 和 test_service.py 的 Ruff 0.11.12 check/format 与 Pyright `--pythonpath .venv/bin/python`，零错误/警告。初始替身未声明 account_id 的赋值已改用 monkeypatch，test_service 格式已修正。
- pass：`uv build --wheel --out-dir /tmp/mpa-app-key-wheel`；归档含新辅助模块和接线服务，不含 .env。不新增前端构建或依赖变化。
- blocked：Studio 已不再监听 8000，无法取得进程凭据，新辅助函数真实只读探测未能启动。此前专用 Host 的 GetAppKey 探测成功，但不是本次新辅助函数。没有更新 Runtime/资源。真实注入、启动、观测和聊天仍为 not_run。
- pass：最终按仓库配置执行范围 Gitleaks、双语标识/链接与差异空白检查（执行后记录见下）。
最终评审：现有完整模拟创建流程已验证 Runtime 传递，结果/注册库不含原始 AppKey。全局 SDK GetAppKey Host 选择与 Runtime/沙箱 IAM 客户端不变。本次任务和本地验收检查完成，已有云部署保持原样。没有提交/推送/服务重启。

最终文档检查：pass，本次范围相对链接和双语标识通过。frontend README 中一个无关的历史可选本地技能示例链接不存在，未改动。初始 Gitleaks 扫描标记了一处文档表述，调整文字后，沿用仓库原配置的扫描通过；未新增排除规则。
