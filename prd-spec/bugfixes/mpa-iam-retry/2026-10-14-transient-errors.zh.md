# IAM 临时失败恢复与诊断

[English](2026-10-14-transient-errors.md)

变更 ID：mpa-iam-retry。日期：2026-10-14。状态：implemented；未执行真实云端变更。
契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-10 和 CON-11。

## 证据、目标与范围

IAM SDK 错误转换为 IamError 时仅保留已知错误码。传输超时/连接错误丢失类别，角色准备立即失败。真实海外任务返回 iamVerificationFailed，而相同角色和凭据后续只读核对通过；原始错误未记录，历史原因不能确定。用户明确批准保留安全的接口/类别/Request ID、有限临时错误重试及区分界面提示。之后的 Worker CreateTool 失败是独立只读调查，不扩大本修复范围。

## 要求与场景

- FR-1：保留 IAM 白名单接口/类别/错误码及从结构化 SDK 响应/错误中取得、经校验的 Request ID。不保存异常文字、凭据、角色/策略文档或任意响应内容。
- FR-2：对超时、连接失败、限流和服务不可用执行最多四次临时错误尝试，等待 1/2/4 秒，受已有 120 秒角色期限及任务期限限制。权限、配置/冲突、参数及未知错误立即失败；缺权限不重试。
- FR-3：每次重试使用相同固定角色/策略名称，从先读后写的协调开始。创建/绑定响应丢失后，下一轮必须先回读，保留已有增量绑定及冲突处理。不并行重试操作，不回滚或扩大权限。取消保持终态；已发送的 SDK 请求可能完成，但取消后不再发送后续协调调用。
- FR-4：临时请求耗尽或截止期限时返回 iamTemporaryFailure，保留原永久错误 key。有限任务诊断（每任务 100 条）保存接口/类别/次数/结果及可选 Request ID。增量迁移 SQLite 表，兼容旧四字段诊断。
- FR-5：界面区分临时 IAM/网络失败与部署权限不足。通用智能体、角色权限集合、服务端点、OV 和 Worker 行为不变。

## 设计与任务

T-1：为 IamError 增加结构化元数据；IamCloud 使用已有分类，仅提取安全字段。有 HTTP 状态时保留类别，不从非结构化文字产生可见消息。
T-2：ensure_runtime_role 增加有限恢复计数，保留 get-or-create 和 Global 策略回读；重试/失败前记录安全诊断。
T-3：diagnostics 校验器/report 增加可选 requestId、IAM 接口白名单；tasks.py 增加默认空值的 request_id 列，仅持久化/输出经过校验的元数据。HTTP 任务结构仅增加错误枚举 key。
T-4：先写回归覆盖临时恢复/耗尽、永久/未知错误、取消/晚返回、创建响应丢失、Request ID 脱敏和 SQLite 迁移；更新双语界面/文档/产物，执行受影响 Python、Ruff/Pyright、前端/构建/浏览器及密钥检查。

## 评审、风险与验收

用户批准：2026-10-14 明确回复“改下”，接受这三项修改。直接设计评审（review-spec 不可用）：已审查安全字段、有限重试/期限、资源回读幂等、取消及旧诊断兼容；双语对应一致，无阻塞。

- AC-1：超时/连接/429/5xx 可恢复；四次失败以 iamTemporaryFailure 结束并记录接口/类别。缺少 IAM 权限仍立即返回 iamPermissionDenied，不重试。
- AC-2：创建响应丢失后先读后写，避免重复创建角色/策略；保留已有信任/策略文档及其他绑定；取消后不调用后续 SDK 接口。
- AC-3：结构化 Request ID 保留在诊断中，恶意/非 ID 文字忽略；旧记录迁移不丢失，原始密钥不进入错误/日志。
- AC-4：界面文案、测试/构建/产物及双语契约一致；下方记录实际检查。

无法追溯证明原真实失败原因。本实现未授权真实 IAM 写入或付费云创建；测试均使用隔离模拟。完整验证待执行。提交/推送不在范围内。保留已有用户修改。


## 验证（2026-10-14）

范围：基于 `2ffe6e14` 的未提交 IAM 改动，保留其他本地工作。新增回归首次运行复现 13 项失败。实施后 IAM/tasks/Worker 恢复定向检查 68 项通过。完整受影响套件 `uv run --extra dev pytest -n 2 -q tests/integrations/mpa_managed tests/cli/test_studio_startup_imports.py` 通过 1,017 项、4 项警告。之后 HTTP 状态提取及线程取消补强，全部 18 项 IAM 重试测试通过。覆盖传输异常及结构化 429/5xx/403 错误。

pass：iam.py、diagnostics.py、tasks.py 及两个修改的 IAM 测试的 Ruff 0.11.12 检查/格式与 Pyright（0 错误/警告）。pass：前端测试（1,389 项 Node + 97 项 React）、生产构建、国际化（2 个语言/21 个命名空间）、产物（113 文件/350 引用）、双语设计标识/链接及空白检查。真实 Chromium 加载实际弹窗，API 隔离模拟，检查明确 IAM 临时失败、同请求重试、个人版/default 界面、旧手动恢复、国内展示、Escape 和窄视口。验证后移除临时夹具及服务，未创建真实资源。用户 lockfile 哈希未变化。

not_run：全仓库 Python/all-files pre-commit，因为未要求提交，受影响 MPA 套件及前端门禁覆盖本范围。not_applicable：Harness/Codex smoke 和模型/OV 真实联调，因为契约未改变。not_run：真实 IAM 变更、Worker CreateTool 重试或云端创建。既有 Worker 失败仍为 provider_error，缺少原始错误码/Request ID；只读搜索确认没有同名模板，这不能确定被拒绝的具体原因。
