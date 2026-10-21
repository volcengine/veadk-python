# Studio latest 镜像内容快照

[English](2026-10-20-latest-image-snapshots.md)

- 变更 ID：`studio-latest-image-refresh`
- 创建：2026-10-20；修订：2026-10-21
- 状态：approved；2026-10-21 用户确认 digest 快照方案，并授权修改、部署 Studio 和创建验证 MPA。
- 组件：[Studio MPA 创建](../../../specs/studio-mpa-creation/README.zh.md)。
- 基线：`86c93529969e6dde86890b30f7e407bfc32ff5ea`，与已部署 Studio 的源码归档一致。

## 证据与原因

仓库当前 Worker `latest` manifest 与最近发布版本一致。本地拉取和三个源码文件哈希确认代码是新版。AgentKit CreateTool 收到正确 latest 地址；CloudTrail 证明下游 CreateFunction 请求也携带该地址，未携带旧 image ID。然而生成的 veFaaS revision 及新 Session 仍使用旧内部 image ID。预热成功不会更新已经发布的绑定。刷新函数 source 并发布新 revision 能修好个别测试函数，但不能修好后续 CreateTool。

已经证明的故障边界是 veFaaS 创建时的 source 同步／解析；服务内部缓存键、TTL 和选择算法尚未确认。Studio 当前仅接受平台 Ready，没有确认镜像内容新旧。目前 API 拒绝 digest 格式的预热地址，也拒绝将预热后的内部镜像地址作为新 source，因此这两种地址都不能视为已建立的受支持部署机制。

另一个 Studio 任务失败后，其 Runtime 后来达到 Ready V1。确切异常尚未确认。不能宣称镜像修复同时解决了部署收尾失败；必须单独调查，再决定是否修改重试行为。

## 目标与非目标

保留用户配置 `latest`、持续向 latest 推送的工作方式。每个全新 Studio MPA 必须绑定本次创建选定的内容，同一次创建重试必须保留原选择。通过 Studio 创建全新 MPA 并检查实际 Worker 内容。不修改旧 MPA Session、日历授权、Agent／Worker 业务代码和云缓存配置，不删除失败资源。保持独立 CLI 部署兼容。

## 场景与需求

- **FR-1：** Studio 输入 latest，新部署身份准备时，读取受支持 CR 镜像的当前 manifest，在同仓库生成确定性的内容快照 tag，保留原 latest。
- **FR-2：** 已记录镜像选择时，同一次创建重试即使 latest 移动也复用原选择；拒绝更换原输入；不静默改写升级前未完成 Worker／Runtime 的请求哈希。
- **FR-3：** 仓库拒绝访问、manifest 缺失、digest 非法、快照 tag 冲突或 latest 仓库不受支持时，在创建 Worker／Runtime 前用有界、脱敏诊断明确失败，不回退到未核验的 latest 部署。
- **FR-4：** 新 MPA 完成要求正常部署收尾和应用 readiness；E2E 还必须检查新 Worker Session 的实际版本标记／源码哈希，不能仅依据平台 Ready。
- **FR-5：** 部分部署失败时保留资源和原创建意图；诊断不得转发子进程 stderr、密钥或任意异常文本。

## 设计与契约

仅对 Studio 所有的新部署，在 managed 部署逻辑旁新增一个职责明确的内部镜像解析模块。复用已有、区分 provider 的 AgentKit CR 认证及 HTTP 依赖。可信仓库主机限制为当前 provider 支持的 CR 域名；校验仓库、tag、digest 格式；HTTPS 请求禁止重定向并设置有界超时；不能根据认证挑战向任意主机发送凭据。

显式接受受支持的 OCI／Docker media type，读取 latest manifest，计算 SHA-256 并核对声明的 digest。通过 registry distribution API，将原始字节发布为同仓库的 `mpa-sha256-<64 位小写十六进制>` tag。若快照已存在，应核验 digest，不覆盖内容冲突的 tag；使用前重新读取确认。不会删除、覆盖或移动原 latest。快照 tag 是持久发布引用，自动清理不在本次范围。

在现有原生逐 Agent 注册记录中，持部署锁、于 CreateTool／CreateRuntime 前持久化原输入、选中 digest、部署引用；无需表结构迁移。Runtime 和 Worker 都使用各自快照引用。重试验证原输入并复用记录的部署引用。对升级前含糊的 pending 状态明确失败，不隐式修复旧创建。注册记录是镜像选择的权威来源；Studio 任务／浏览器输入继续显示 latest。快照选择的是创建时的 latest，不会持续改变已运行 MPA。

这里有明确语义区别：用户输入继续是 latest，底层 Tool／Runtime 的镜像地址会是内容快照 tag。如果要求底层平台地址本身必须始终以 `:latest` 结尾，则本方案不满足；那需要平台提供已验证的缓存失效／强制拉新契约，目前尚未建立。

云写操作限制在选定镜像仓库和新部署身份。需要仓库拉取和推送权限，不自动修改 IAM。不新增依赖和公开 HTTP 请求字段，不计划修改前端行为。保留取消处理、既有请求 token、网络／数据库归属验证和未知结果恢复。API／传输错误明确暴露，仅允许安全的操作名、类别、错误码和 request ID 进入 Studio。

## 任务与验收

| 需求 | 任务 | 验收 | 验证 | 当前结果 |
| --- | --- | --- | --- | --- |
| FR-1/FR-3 | T-1：可信 CR manifest 快照模块 | AC-1：字节／digest 一致、latest 未变；访问／格式／冲突负例明确失败 | 先写失败回归；模拟 CR／HTTP 模块测试 | pass；本地证据见下文 |
| FR-2 | T-2：接入 Studio 部署与原生记录 | AC-2：latest 移动后同身份重试保留原快照；独立 MPA 解析新快照；保留旧 pending 状态 | managed service／Worker／Runtime 集成回归 | pass；本地证据见下文 |
| FR-4/FR-5 | T-3：定位实际 Studio 收尾异常，只修已证实原因 | AC-3：失败回归重现根因；正常最终更新及 readiness 完成 | 定向创建／部署测试和安全在线诊断 | not_run；根因尚未建立 |
| 全部 | T-4：验证并发布 Studio | AC-4：增量覆盖率高于 95%；如实报告门禁；保留 Studio 原认证／环境 | pytest coverage、Ruff、改动文件 Pyright、全文件 pre-commit、按影响扩大回归；支持的 Studio update | not_run |
| FR-4 | T-5：复用已授权 Chrome 会话创建全新 MPA | AC-5：Studio 任务成功、Runtime readiness 成功、选中 manifest 对应实际新 Worker 代码、安全功能执行终态 | 浏览器证据及官方云 API／源码探针；不发送真人 IM 消息 | not_run |

## 风险与恢复

生成快照需要仓库写权限并增加 tag 元数据。多架构 media type 必须完整保留，不改写 manifest，不静默切换架构。开放该能力前，先用有界新资源实验确认 AgentKit 接受快照 tag。不假定 registry tag 不可变：已有内容冲突必须检测，重试进一步写部署资源前重新校验。保留失败资源；验收失败时通过支持的发布机制回滚 Studio。不宣称修改了平台内部缓存实现。

## 审查与交付记录

没有可用 review-spec 技能，已直接审查 provider 边界、凭据保护、manifest 完整性、取消／超时、重试身份、旧 pending 兼容、latest 输入语义及双语一致性。已解除阻塞：用户明确同意 latest 作为输入、内容快照作为底层部署地址。独立的部署收尾异常仍是待定位任务，不预设修法。2026-10-21 用户已批准方案、代码修改、部署及新建验证；见下方交付记录。

## 2026-10-21 批准与实施范围

用户指令：“修改一下studio 部署一下试试”。已实测唯一 tag 与按 latest digest 自动生成的 `mpa-sha256-<digest>` 都可让新 Worker 采用已发布源码；因此接受此设计作为实现基线。源码基线同步至 `5e5deb6a`。实施范围为镜像快照解析、原生部署记录中的持久版本选择、受影响双语契约和测试、BP Studio 更新与新建验证。既有部署收尾失败的根因仍未知，不预设或扩大修复；若新建仍失败，保留资源并如实报告。安全及双语一致性已直接复核；review-spec 技能不可用。

## 2026-10-21 本地实现与验证

实现 `managed/image_snapshot.py`，由 `service.provision` 的既有部署锁调用；原生 JSON 保存请求/解析结果，首次准备固定两个镜像，重试仅验证原快照。非 Studio CLI 和固定 tag 不变。CR 实例名从带地域的仓库域名解析，认证携带 STS；原始 manifest 字节、digest、media type 均核验。测试覆盖仓库协议、跨平台/重定向拒绝、认证、冲突/损坏状态、失败/取消、重试及 Worker/Runtime payload 接入。

验证环境：Python 3.12.12，`uv sync --frozen --extra dev --python 3.12`；未修改依赖/锁文件。

- pass：`pytest tests/integrations/mpa_managed tests/cli/test_cli_mpa.py -n 2 -q`，1220 passed。
- pass：47 个快照/接入用例；模块行/分支覆盖率 100%；增量生产代码行覆盖 130/130（100%）。覆盖执行在启动 pytest 前预加载 `pydantic_settings` 与 SDK Runtime 类型，规避依赖导入身份问题；相同问题在未修改主分支和带 coverage 的并行执行中均可重现，未通过改业务代码掩盖。
- pass：`npm --prefix frontend test`，8 文件、118 用例；`npm --prefix frontend run build`。
- pass：改动 Python 的 Ruff/Pyright；`pre-commit run --all-files`（含密钥扫描）；`git diff --check`。
- pass：已授权 BP 真实账号上调用同一实现，解析并回读 Agent/Worker digest 快照，latest 保持不变。
- not_run：Studio 更新及浏览器新建 MPA、应用就绪/A2A；部署后补记录。独立 Codex/Pi/Harness、国内真实部署、日历/真人 IM 不属于本次验证。

直接复核：无新增依赖/公开字段；HTTP 凭据主机边界、原生锁/持久选择、取消后固定 tag 副作用、旧 pending 拒绝、CLI 兼容及双语一致性均已检查。快照 tag 保留，不自动清理。
