# Studio 保留源码更新

组件：`studio-source-preserving-updates`。状态：active。修订：2026-10-14。
[English](README.md)
[变更设计](../../prd-spec/bugfixes/2026-10-13-source-preserving-domain-updates.zh.md)

## 责任与入口

负责无法重新生成源码的应用的 Skill/MCP 编辑：
`veadk/cli/legacy_runtime_recovery.py`、`runtime_update_recovery.py`、相关
`cli_frontend.py` 路由、`veadk/integrations/agentkit/source_overlay.py` 和
`app.py` 自省，以及 CustomCreate、ProjectPreview、agentDraftStorage。
既有 `/web/runtime-update-capability` 与发布接口沿用认证授权规则。
`/web/agent-info/{app_name}` 提供校验后的元数据。领域工具工厂继续负责工具策略
与执行。本组件不管理模型、SQL 策略、MPA Profile 或 Runtime 弹性。

## 合同

| ID | 合同 |
| --- | --- |
| CON-1 | 保留源码编辑仅允许 Skill/MCP 变化。保留固定 digest 的基础镜像、应用入口、身份与导入路径；普通创建和重新生成沿用原有校验与生命周期。 |
| CON-2 | 可调用的 `_veadk_studio_mcp_overlay_handler` 校验应用 MCP，不用普通工具替换。处理器失败即终止。受支持的单根 HTTP 启动方式核对完整 `MCP_SERVERS_JSON`，责任或配置不匹配时拒绝。 |
| CON-3 | `managed.json`、`selected.json`、`final.json` 分别表达原有、打包和最终 Skill。最终选择为准；必需 Skill 缺失时报错，不能静默丢失。版本目录按内容摘要命名且非 root 可读。恢复遵守活动布局和 OCI whiteout，拒绝链接、错误清单和超限内容。 |
| CON-4 | `sourceOverlay` schema version 1 仅包含 `mcp: {agentName: [{name, transport, url, authTokenEnv}]}`。transport 为 `http`；URL 不得含用户凭证、查询或片段。上限为 128 Agent、256 MCP、1 MiB 文件、4096 字符 URL。非法元数据返回 `{schemaVersion: 1, status: "unavailable"}` 并阻止编辑；同时存在普通 draft 也不例外。 |
| CON-5 | MCP 凭证值不进入公开元数据、构建上下文或浏览器存储。既有已配置引用刷新后保留，明确删除或替换得到尊重。凭证只为准确授权端点解析，仅传入授权发布环境。 |
| CON-6 | 保留源码发布跳过 MPA Profile 生命周期。异步失败保留失败状态；构建成功不能代表 Runtime 发布或真实工具调用成功。 |

## 状态、配置与兼容

只有公开元数据和源镜像摘要完整，才能恢复为可编辑的保留源码状态；存在歧义时阻止
恢复。构建、Runtime 更新、发布与实际调用是不同阶段。重新编辑读取当前发布版本。
并发版本检查和取消行为继续由发布接口负责，本变更不增加云写入自动重试。

`VEADK_STUDIO_SKILL_OVERLAY` 和 `PYTHONPATH` 显式选择活动启动器。
MCP 凭证保存在 Runtime 环境变量，镜像文件仅包含引用。生成钩子将 ADK 导入延迟到
应用初始化。没有覆盖层的既有镜像沿用原恢复路径。启用覆盖后缺少新元数据，不能
静默允许源码重新生成。

## 验证与变更记录

CON-1/2：CLI 发布测试、生成钩子测试和真实领域工厂包装检查。
CON-3：Skill、启动、OCI 恢复回归。CON-4/5：自省、再次编辑、凭证存储测试。
CON-6：前端生命周期测试，包含普通创建和重新生成对照。强制工作流必须覆盖这些测试。

执行仓库 Python/前端门禁，并对明确授权目标完成真实 Studio 编辑、发布、再次打开
以及 Skill/MCP 实际调用。离线和真实结果分别记录在双语 PRD。实现、两次真实页面
发布、Skill/MCP 实际执行和再次编辑均已对齐；这不表示已发布正式 Studio 版本或
合入主线。

CON-1 的 Runtime 请求边界：省略 `Description` 与 `ApmplusEnable`，保留原资源描述与监控设置。普通更新不受此规则影响。

CON-1 环境边界：保留已有应用环境与元数据；不继承 Studio 主机配置，不创建 MPA
身份/标签，不重置环境选择，不自动解析替换模型凭证。已有严格禁用 Sidecar 的
过滤合同独立保持。

已授权编辑器不能拉取 Skill 文件时，源镜像当前覆盖层中已选中的运行时 Skill，
必须在下次构建时保留。以固定摘要的源镜像作为准备阶段，只合并上一版本仍被选中
的 Skill 与本次明确输入；新上传替换优先，已移除项不能重新出现。合并后仍执行
文件数/字节限制，拒绝链接、特殊文件和不完整清单，并保证原非 root 用户可读。
新版本目录绑定源镜像摘要和输入文件。不需要实例命令、镜像内凭证或仓库权限变更。
