# Studio MPA 创建使用公开仓库默认镜像

[English](2026-10-09-public-registry-images.md)

- 变更 ID：`mpa-latest-images`
- 创建/修订：2026-10-09
- 状态：approved
- 合同：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)，CON-9

## 背景与证据

Studio 当前从 `studio_profile.py` 预填固定历史标签。用户指定的公开仓库为 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/agentkit_mpa_agent_studio` 和 `agentkit-platform-2112682748-cn-beijing.cr.volces.com/agentkit/agentkit_mpa_codex_worker_studio`。2026-10-09 匿名 OCI 读取成功；其他部署账号无法用自身 CR 管理接口查询源仓库。MPA 使用包含证明条目的 OCI index，Worker 使用单 Docker manifest。公开元数据提供构建时间，没有推送时间。目前每个仓库只有一个历史标签；自动查询无法产生尚未发布的新版本。

## 目标与非目标

新 Studio 请求自动选择最新 Linux/amd64 构建，保留手动输入及稳定重试镜像。不创建云资源、不修改凭据、不升级已有 Runtime、不提供通用仓库浏览器，也不为 CLI YAML 自动发现镜像。源账号与经核验的部署账号独立。CLI 配置继续显式指定。

## 场景与需求

- FR-1：新建弹窗从两个公开仓库获得具体默认镜像。按镜像 config 的 UTC `created` 排序，以标签名确定相同时间的顺序。忽略非 Linux/amd64 平台及证明条目；兼容镜像缺少时间或时间非法时明确报错。
- FR-2：保留镜像输入框编辑。显式输入跳过该镜像的自动查询。留空在首次提交时解析。自动选择使用经核验的 SHA256 manifest digest，避免可变标签漂移。
- FR-3：通过已有任务 `images` 快照保存首次实际选择。同一 owner/request 的重试及重复提交不再访问仓库，复用快照。修改原请求输入仍冲突。旧快照保持原样，包括空快照。
- FR-4：查询为服务端匿名 GET，有边界且支持取消。不需要部署账号 CR 权限或仓库密钥。网络、鉴权、元数据、数量限制和没有兼容镜像的错误转换成安全 ConfigurationError，绝不静默回退历史标签。

## 设计与边界

新增内部异步 HTTPX OCI 解析器，复用已有依赖。固定仓库常量由 Studio profile 管理。读取标签、manifest/index、Linux/amd64 manifest 和镜像 config。核验 manifest/config digest 完整性。鉴权 challenge 必须指向同一 HTTPS 仓库 origin，scope 必须对应当前仓库。分页限制在同一 tags 接口。仅 blob 可重定向至 HTTPS 火山引擎对象存储域名，跨 origin 不转发 bearer token。JSON 上限 1 MiB、每仓库 100 标签、10 标签分页、5 次 blob 重定向、4 个并发标签读取、每请求 15 秒、一次发现 60 秒。客户端生命周期覆盖一次解析，超时或取消关闭请求。

配置 GET 通过原合同返回 `runtimeImage`/`workerImage` digest 引用。POST 先读取已有 owner/request 快照，再仅解析缺失的默认镜像。SQLite `start` 仍负责事务内首次选择和冲突校验。不变更持久化 schema，不缓存；新的配置检查可看到新构建。CLI 保留固定、不自动查询的默认镜像，但改用指定仓库名。已有请求保留已保存的镜像。通用智能体对话、资源编排、IAM 和部署账号核验不受影响。

## 任务与受影响文件

- T-1 / FR-1、FR-4：在 `tests/integrations/mpa_managed/test_studio_images.py` 和 `frontend/server/mpa_creation_images.py` 增加回归测试及解析器。
- T-2 / FR-2、FR-3：在 `frontend/server/mpa_creation.py`、`managed/tasks.py` 接入路由和 owner 范围快照查询；补充路由/任务测试。
- T-3 / FR-1、FR-2：在 `managed/studio_profile.py` 定义仓库常量；更新双语 CON-9 和使用指南。原表单/类型已支持 digest，不改变布局或交互。
- T-4：运行相关 Python 测试、Ruff/Pyright、前端测试/构建及只读浏览器检查；检查双语等价、脱敏和空白。

## 验证与验收

| 需求 | 任务 | 验收 | 验证 | 结果 |
| --- | --- | --- | --- | --- |
| FR-1、FR-4 | T-1 | AC-1：选择正确兼容构建，安全且有界失败 | MockTransport 测试及公开匿名读取 | not_run |
| FR-2、FR-3 | T-2 | AC-2：留空/手动/重试/归属行为正确 | 创建镜像/任务回归 | not_run |
| FR-1、FR-2 | T-3、T-4 | AC-3：默认值进入原输入框，不破坏 UI 合同 | 前端测试/构建，只读弹窗检查 | not_run |

命令：`uv run --extra dev pytest tests/integrations/mpa_managed`、限定范围 Ruff/Pyright、`npm --prefix frontend test`、`npm --prefix frontend run build`、`git diff --check`。测试使用模拟 transport/tasks；真实验证只执行 GET，未授权真实部署。验证范围为 `feat/test-main` 当前工作差异，保留其他已有修改。

## 风险与恢复

查询增加延迟，依赖公开仓库可用性。构建时间可能不同于推送顺序，这是明确约定。超过 100 标签时须显式调整限制，不能静默截取。未通过新建云部署证明平台接受 digest，但已有镜像校验支持。手动镜像保持原标签语义。回滚发现仅影响新任务，不改变已有任务快照。

## 设计评审与批准

没有可用 `review-spec`；2026-10-09 已直接评审归属、错误、安全、重试竞争、兼容、可测试性及双语等价，无阻塞项。用户以“帮我改”批准公开仓库/手动输入/固定重试的方案。不授权提交、推送、部署或云写入。下面将同步实际实现与验证记录。

配置 GET 接受可选 UUID `requestId`；owner 范围已有快照在重开失败任务时也跳过发现。原 UI 传递请求身份，仅接通 API，不重新设计视觉/交互。直接评审确认这是补齐 FR-3，没有扩大范围。

客户端配置/创建请求允许 75 秒，使 60 秒解析器有时间返回明确错误。构建时间保留纳秒顺序（RFC3339，最多 9 位小数）。
