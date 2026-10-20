# 托管 MPA 使用 BytePlus 托管的默认镜像

[English](2026-10-14-byteplus-default-images.md)

- ID：`mpa-byteplus-default-images`
- 创建/修订日期：2026-10-14
- 状态：implemented
- 契约：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)

## 背景与证据

BytePlus 托管创建当前在未设置可信环境变量覆盖时，会继承火山引擎北京地域的 Runtime 和 Worker 镜像地址。真实 BytePlus 创建已推进到 `CreateTool`，随后以 `provider_error` 失败；持久化任务快照确认仍选择北京 `cr.volces.com` Worker 镜像。现已准备以下 BytePlus 公共仓库，并验证匿名读取 manifest 成功：

- `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/mpa_agent:latest`
- `agentkit-platform-3001037806-ap-southeast-1.cr.bytepluses.com/mpa/mpa_codex_worker:latest`

两份已验证 manifest 的 digest 分别为 `sha256:1db0caa3...` 和 `sha256:b9ea5f49...`。Worker 镜像基于 `agentkit-mpa-codex-worker` 的 `master@7aa11f0` 构建。

## 目标与非目标

使新的 BytePlus 内置 Studio 请求默认选择 BytePlus 托管的 Runtime 和 Worker 镜像。保留可信服务端覆盖及全部国内默认值。

不修改或重试已有任务，不改变镜像校验，不将默认值固定为 digest，不重新构建镜像，不修改云资源，不改变浏览器输入，也不改变 CLI/YAML 配置。

## 场景与需求

- FR-1：`load_studio_profile(provider="byteplus")` 默认使用上文两个 `ap-southeast-1.cr.bytepluses.com` latest Runtime/Worker 地址。
- FR-2：非空 `VEADK_MPA_BYTEPLUS_RUNTIME_IMAGE` 和 `VEADK_MPA_BYTEPLUS_WORKER_IMAGE` 继续作为优先级更高的可信覆盖。
- FR-3：火山引擎 `load_studio_profile()` 的北京 Runtime/Worker 默认值完全不变。
- FR-4：已提交任务保留其持久化镜像快照。Studio 重启后必须创建新请求才能取得新默认值。

## 设计与影响文件

在 `studio_profile_values` 的 BytePlus 分支中定义一次 BytePlus 仓库地址，并将其两个镜像地址作为现有环境变量覆盖项之后的默认值。配置/任务接口已返回并快照解析后的非敏感默认值，因此不需要前端或 HTTP 结构变更。

影响文件：

- `veadk/integrations/mpa/managed/studio_profile.py`
- `tests/integrations/mpa_managed/test_byteplus.py`
- 成对 Studio MPA 组件契约
- 本成对 bugfix 设计

## 任务、测试与验收

| 需求 | 任务 | 验收 |
| --- | --- | --- |
| FR-1/FR-3 | 先增加失败的平台隔离断言，再修改默认值 | BytePlus 选择海外地址，火山引擎保持不变 |
| FR-2 | 保留并运行覆盖项测试 | 两个可信覆盖项继续优先 |
| FR-4 | 更新成对契约并核验任务语义 | 文档明确只有新任务快照取得新默认值 |

验证：BytePlus 定向 pytest、改动文件 Ruff 和 Pyright、双语/链接复核及 `git diff --check`。没有前端或 HTTP 契约变化，因此前端构建和浏览器检查不适用。

## 风险与评审

按请求沿用 Studio 约定的可变 `latest` 标签；已验证 digest 只作为证据，不作为运行时固定值。公共 manifest 可读不能证明 AgentKit `CreateTool` 或 Runtime 应用就绪，因此仍需用新的隔离 BytePlus 创建做真实验收。已有失败任务不能接管新镜像，因为修改其快照会破坏重试身份。

直接设计评审（`review-spec` 不可用）：已检查范围、平台隔离、覆盖优先级、任务不可变性、安全性、兼容性、可测试性和双语等价性；无阻塞项。用户以“帮我改下”批准了前述方案。本批准不授权提交、推送或云端部署。

## 验证记录

2026-10-14 当前工作差异：

- pass：新增默认值断言在旧实现上失败，两个镜像仍解析为北京仓库。
- pass：`uv run --extra dev pytest tests/integrations/mpa_managed/test_byteplus.py tests/integrations/mpa_managed/test_tasks.py tests/integrations/mpa_managed/test_studio_shared_resources.py -q` — 47 项通过，另有两个上游弃用警告。
- pass：对改动 Python 文件执行 Ruff 0.11.12 检查/格式化和 Pyright；`git diff --check`；双语链接及语义已复核。
- pass：直接解析配置时选中两个 BytePlus 托管地址，并保留两个北京国内地址。
- pass：实现前已验证 BytePlus 公共镜像 manifest 可读。
- pass：Studio 重启后，真实任务 `209b63d5-04ec-490f-95d8-41b7931891f4` 已持久化两个 BytePlus 托管默认值，并完成 Worker 创建及就绪。任务随后在独立的 OpenViking 自动创建阶段以 `openvikingCreateUnknown` 失败，尚未进入 Runtime 创建。
- not_applicable：前端构建/浏览器检查；没有前端或 HTTP 契约变化。
