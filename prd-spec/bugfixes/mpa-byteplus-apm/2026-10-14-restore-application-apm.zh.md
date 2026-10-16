# 恢复 BytePlus Studio 配置中的应用 APM

[English](2026-10-14-restore-application-apm.md)

变更 ID：mpa-byteplus-application-apm-restore。日期：2026-10-14。状态：implemented。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-17。
前序变更：[关闭应用 APM](2026-10-14-disable-application-apm.zh.md)。

## 背景、目标和范围

此前为绕过海外 `GetAppKey` 超时，临时关闭了 BytePlus 应用 APM。真实创建随后到达
Runtime 就绪，但平台从实际环境中移除了 `ENABLE_APMPLUS=false`，创建验证器因要求
配置完全一致而持续等待。用户现已要求恢复全部 APM 绕过设置。

目标：恢复 BytePlus 继承的 Runtime 默认值：`ApmplusEnable=true`、
`ENABLE_APMPLUS=true` 和 `FORCE_APMPLUS_EXPORTER_REGISTRATION=true`。
非目标：修复上游 APMPlus 超时、修改就绪协调、变更已有 Runtime 资源或修改火山引擎
默认值。

## 需求和场景

- FR-1：新的 BytePlus 配置继承三个已启用的 APM 默认值。
- FR-2：火山引擎默认值继续启用，各平台配置调用保持隔离。
- FR-3：已有 Runtime 资源和已提交任务快照不变；须重启 Studio 并创建新请求后才使用
  恢复后的默认值。

## 设计、影响和任务

- T-1：将平台回归测试改为要求两个平台均启用 APM，并确认实现前失败（FR-1/FR-2）。
- T-2：仅从 `studio_profile_values` 删除 BytePlus APM 覆盖项；保留镜像、模型、OV 和
  平台设置（FR-1/FR-3）。
- T-3：同步本文、前序 PRD 和双语组件契约；运行定向测试、Ruff、Pyright、双语/链接和
  空白检查。

不修改 API、数据库结构、凭据、前端或生成产物契约。已知的 BytePlus APMPlus 服务超时
可能再次导致 Runtime 启动失败；这是有意回滚，不代表上游 APMPlus 已恢复。

## 评审、风险和验收

用户批准：2026-10-14 用户明确要求恢复 `ENABLE_APMPLUS` 及相关 APM 绕过设置。
直接设计评审：已检查范围、平台隔离、兼容性、安全和可测试性，无阻塞项。主要风险是
已观察到的 `GetAppKey InternalServiceTimeout` 再次出现。

- AC-1：两个平台解析和部署的三个 APM 设置均为启用。
- AC-2：定向测试和静态检查通过。
- AC-3：文档双语一致，并记录不修改已有 Runtime。

## 验证与交付

2026-10-14，基于当前工作区差异：

- pass：修改后的回归测试在实施前对 BytePlus 失败，删除三个覆盖项后通过。
- pass：`uv run --extra dev pytest -q
  tests/integrations/mpa_managed/test_byteplus.py
  tests/integrations/mpa_managed/test_config.py`，105 项测试。
- pass：`uv run --extra dev pytest -n 2 -q
  tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py`，
  1,093 项测试，四项依赖弃用警告。
- pass：对变更 Python 文件执行 Ruff 0.11.12 check/format 和 Pyright。
- pass：双语文档存在、相对链接和局部差异空白检查。
- not_run：未要求真实云创建、提交、推送和全文件 pre-commit。
- not_applicable：前端构建/浏览器检查；没有前端行为变化。
