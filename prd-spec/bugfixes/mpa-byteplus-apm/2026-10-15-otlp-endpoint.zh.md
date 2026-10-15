# BytePlus Studio MPA OTLP 上报地址

[English](2026-10-15-otlp-endpoint.md)

## 元数据与证据
变更 ID：mpa-byteplus-otlp-endpoint。日期：2026-10-15。状态：implemented。
SDK 的默认地址即便在海外地域也使用国内 volces.com 后缀。用户提供了 BytePlus 新加坡采集地址。仅获取 AppKey 不会选择该采集地址。

## 范围与需求
FR-1：新的 BytePlus Studio 配置向 Runtime Envs 注入 `OBSERVABILITY_OPENTELEMETRY_APMPLUS_ENDPOINT=http://apmplus-ap-southeast-1.bytepluses.com:4317`。
FR-2：火山配置、通用智能体、全局 SDK 默认值、AppKey 获取及 APM 启用状态不变。不迁移已有 Runtime 资源及已提交任务快照。
FR-3：保留现有可信 Runtime 环境变量覆盖优先级。
新建 BytePlus 请求生成的 Runtime 请求体携带上报地址；国内请求不增加海外上报地址。

## 设计与任务
T-1：扩展供应商隔离回归，先验证缺失地址时失败，覆盖原始默认值、加载后的配置、Runtime 请求体及显式覆盖。
T-2：仅在 `veadk/integrations/mpa/managed/studio_profile.py` 的 BytePlus 分支加入地址常量值。
T-3：同步中英文 Studio 创建 CON-17 及托管模块 README；运行目标测试、Ruff、Pyright、空白和链接检查。
相关契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-17。受影响测试：`tests/integrations/mpa_managed/test_byteplus.py`。
不新增 API、数据库结构、凭据、网络调用、超时、取消或并发行为。复用既有环境变量到请求体的处理，仅修改默认采集地址配置。

## 评审与验收
用户批准：2026-10-15 明确要求 BytePlus 创建注入所给地址且不影响国内行为。因 review-spec 不可用，直接完成设计评审：已检查供应商边界、覆盖优先级、重试快照、安全、兼容及双语一致性，无阻塞项。
AC-1：BytePlus 默认值及最终请求体包含地址。AC-2：国内默认值及请求体不包含此项，显式覆盖仍生效。AC-3：范围内检查通过，单独说明云端验证情况。
风险：采集地址实际连通性及 Trace 接收需要云端验证。已有部署需另行授权更新；新请求需重启 Studio。本变更不证明 APM 已成功上报。

## 验证
2026-10-15，基于 4997196d 的本地修改，仅涉及 Studio 配置、供应商回归及双语文档：
- pass：实现前回归重现 BytePlus KeyError，国内用例通过。
- pass：`uv run --extra dev pytest -q tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_apm_key.py tests/integrations/mpa_managed/test_service.py` — 219 项通过，两个依赖弃用警告。
- pass：对两个修改的 Python 文件运行 `uv tool run --from ruff==0.11.12 ruff check` 和 `ruff format --check`；运行 `uv tool run pyright --pythonpath .venv/bin/python` — 零错误、零警告。本地无 Ruff/Pyright 可执行文件，使用临时工具，遵循用户此前仅记录验证结果的偏好。
- pass：`git diff --check`，已检查双语需求 ID 和相对链接。
- not_applicable：前端构建/浏览器及 harness smoke；未修改 UI、API 或 harness 代码。
- not_run：真实云端部署/上报验证及全文件 pre-commit；用户未要求部署或提交。范围内 hook 另行记录于下方。
评审：国内分支在新增环境变量前返回；未修改共享 SDK 或加入密钥。保留原有无关前端锁文件修改。生成请求体测试覆盖 AC-1/AC-2；真实 Trace 投递仍未验证。


- pass：`uv run --extra dev pre-commit run --files <八个本次修改文件>` — Ruff 检查/格式化及硬编码密钥扫描通过；依赖/YAML hook 因无对应文件改动而跳过。
