# 可信 MCP 会话

[English](README.md)

- 组件 ID：`trusted-mcp-sessions`
- 状态：`active`；范围内路由契约已通过隔离组件测试验证。
- 修订日期：2026-10-26
- 相关 PRD：[普通 MCP 死锁](../../prd-spec/bugfixes/trusted-mcp-session-routing/2026-10-26-standard-mcp-deadlock.zh.md)
- 所属代码：`veadk/tools/mcp_tool/trusted_mcp_session_manager.py`。
- 调用方：`veadk/tools/mcp_tool/trusted_mcp_toolset.py`。
- 测试：`tests/tools/mcp_tool/test_trusted_mcp_components.py`；`tests/tools/mcp_tool/test_trusted_mcp_session_routing.py`。

## 职责与入口

`TrustedMcpSessionManager` 继承 Google ADK 的 `MCPSessionManager`，负责可信传输选择、可信会话创建和会话池；普通会话委托 Google ADK。`TrustedMcpToolset` 安装此管理器，用于工具发现和执行。

会话入口为 `async create_session(headers: Optional[Dict[str, str]] = None) -> ClientSession`。依赖包括 Google ADK 连接参数和父类生命周期方法、MCP `ClientSession`，以及 `bytedance.jeddak_trusted_mcp.trusted_mcp_client`。继承的 `close()` 负责普通会话池清理；可信条目的既有兼容局限见下文。工具集参数转发、可信证明内部实现、云端部署和通用依赖策略不属于本组件范围。

## 契约

- `CON-1`：选择可信路径必须同时满足 `StreamableHTTPConnectionParams` 和合并后 `x-trusted-mcp == "true"`。其他连接类型及标记值使用普通传输。
- `CON-2`：普通 `create_session` 在获取子类会话锁或访问会话池之前委托父类。普通会话的同步、初始化、复用、替换、错误和清理由父类负责。`_create_client` 重写方法在普通路径接收并转发父类位置／关键字参数。
- `CON-3`：继承父类请求头合并优先级，调用请求头覆盖连接请求头。路由检查不得修改输入字典。所选传输须能获得鉴权请求头。可信标记只在生成可信会话键后从内部合并副本移除。
- `CON-4`：可信创建使用 `trusted_mcp_client`，缓存已初始化会话及其 `AsyncExitStack`。同一键复用健康会话；断开的会话在会话锁内移除并替换。清理失败沿用现有日志报告。
- `CON-5`：普通错误及取消按父类语义传播。等待锁时取消，不得使子类继续持锁。不新增超时、重试策略或成功回退。

输入示例：streamable HTTP 连接使用 `headers={"Authorization": "Bearer test-placeholder"}` 时选择普通 MCP。增加 `x-trusted-mcp: "true"` 后选择可信 MCP；调用请求头用 `"false"` 覆盖时选择普通 MCP。

## 状态、数据与并发

会话状态仅保存在进程内继承的 `_sessions`：当前父类为普通会话保存键 → `(session, exit_stack, loop)`；未改动的可信分支保存键 → `(session, exit_stack)`。没有持久化结构或新增环境变量。会话键及连接超时沿用父类实现。

相关转换为：不存在 → 已初始化／缓存 → 复用；断开 → 清理／移除 → 替换；以及通过继承的 `close()` 从缓存 → 关闭／移除。普通转换由父类管理。可信转换只获取一次子类锁。创建失败不能缓存为成功会话。等待锁时取消会释放已经通过上下文管理器获取的锁。

本次不调整事件循环锁分配、跨循环会话处理、迟到的传输事件，以及可信资源进入后的取消清理；这些仍受上游或现有实现限制。

在已验证的 Google ADK 2.7.1 基线上，继承的 `close()` 要求三元素会话池条目，与未改动的可信双元素条目不兼容。本次修复保留可信创建／复用；测试显式关闭可信栈，不声称继承的最终关闭已兼容。解决这个既有可信生命周期问题，需要另行批准变更。

## 安全、失败与兼容

可信选择依据明确的连接类型和标记，不能仅凭 Bearer 请求头启用。诊断、规格和测试数据不得新增真实凭据。验证替换真实传输，不读取本地 AICC 配置，不调用可信证明或云端服务。

公共导入路径／签名及鉴权配置保持兼容。依赖支持遵循[运行时依赖兼容](../runtime-dependency-compatibility/README.zh.md)，当前为 Google ADK `>=2.7.0,<2.8.0` 和仓库 MCP `1.26.0`。报告中的 Google ADK 2.1.0 组合只是问题背景，不代表当前已验证支持。

诊断继续使用现有会话创建／清理日志。普通路径已移除原先阻止连接开始的子类持锁；传输失败仍表现为父类异常。本次不保证连接不可用服务器成功，也不修复无关的上游取消清理问题。

## 验证与变更记录

| 契约 | 验证 | 证据 |
| --- | --- | --- |
| `CON-1`、`CON-3`、`CON-4` | 路由、请求头、可信创建／复用测试及现有组件测试 | `pass`，包含在 24 条定向测试中；见相关 PRD |
| `CON-2` | 使用真实父类加锁，验证修复前有界失败、修复后成功；普通传输／生命周期测试 | `pass`，修复前两条超时，修复后成功；见相关 PRD |
| `CON-5` | 普通失败重试及等待锁时取消 | `pass`，包含在 24 条定向测试中；见相关 PRD |

命令：`uv run --extra dev pytest tests/tools/mcp_tool`。扩大检查及最终结果记录在 PRD。真实可信证明对本次隔离锁回归为 `not_applicable`。

2026-10-26：用户批准范围明确的 PRD；已实现普通会话委托和父类工厂参数转发，保留可信路由。验证环境为 Python 3.11.14、Google ADK 2.7.1、MCP 1.26.0，检查范围为基线 `c662cc8d` 加工作区路由差异。定向测试通过；扩大验证及局限记录在 PRD。
