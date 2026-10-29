# Agent 所属原生 MCP 工具集的准备计时

[English](2026-10-27-mcp-preparation-native-extension.md)

变更 ID：`mcp-preparation-native-extension`；日期：2026-10-27；状态：在现有一期实现授权范围内批准，尚未发布。前序：[Trusted 准备计时](2026-10-27-mcp-preparation-timing.zh.md)。契约：[MCP 会话分派](../../../specs/mcp-session-dispatch/README.zh.md)。

## 依据与目标

V25 已在 APMPlus 验收 Trusted 准备／获取 Span。内置 mcp_router、lark、las、vod、supabase 使用原生 ADK McpToolset；VeIdentity 使用另一工具集及原生管理器。原有封装尚未覆盖这些 Agent 所属路径。

## 需求、设计与边界

- `FR-1`：VeADK Agent 组装已知原生及 VeIdentity 工具集时接入计时。Trusted 保留现有计时，不重复创建 Span。未知工具及 VeADK 未持有的原生 ADK 类保持不变。
- `FR-2`：专用适配器向已有工具集／管理器实例绑定封装。保留构造、回调、凭据、锁、缓存、生命周期、过滤、重试及取消语义；不替换管理器，不全局修改第三方类。
- `FR-3`：get_tools 与 create_session 复用固定元数据 preparation_span。保留参数、返回值与异常对象、调用方上下文，每次仅委托原逻辑一次。新增遥测不记录鉴权、请求头、URL、正文或异常消息。
- `FR-4`：重复安装不重复封装。复制后的绑定方法必须操作复制后的对象：捕获未绑定函数，不捕获原对象的绑定方法。多个 Agent 共用实例不得重复计时；未知非标准方法保持不变。
- `FR-5`：Agent 只增加小型接入调用，逻辑放新模块。工具执行传播、动态身份凭据、provider／exporter、云资源及依赖不在本扩展范围。离线身份样例不能证明真实提供方授权。

## 任务与验收

`T-1`／`AC-1`：先编写失败的原生／身份准备测试；覆盖实例不变、独立管理器、参数、异常／取消对象、并发、幂等、deepcopy 绑定、Trusted 不重复、未知工具及实际 Agent 组装。

`T-2`／`AC-2`：实现适配器与 Agent 接入，保留重试、缓存及鉴权回调；执行相关 MCP、身份、Agent 回归及要求的全量回归／pre-commit，更新双语契约和用户 MDX。

`T-3`／`AC-3`：在现有仅镜像更新授权下，使用隔离样例验证实际原生 HTTP 工具集及 APMPlus 回查，依赖和 29 项配置不变。真实身份凭据验收需已授权且配置完成的提供方，单独记录；不推导新增地址、角色或凭据权限。

## 评审与授权

review-spec 不可用，已直接评审。用户已要求完成所有可推进的一期实现与验证并持续自主探索，现有授权覆盖这一采集缺口；不宣称新增人工评审或部署授权。已评审风险：替换管理器会丢失回调，全局修改影响其他消费者，捕获绑定对象破坏 deepcopy，重复封装造成重复计数；实例适配方案对应规避这些风险。生产代码／测试编辑前已核对需求及双语一致性。

## 验证记录

- `pass`：实现前，无操作适配器复现六项缺少计时失败及三项原行为通过。
- `pass`：130 项相关 MCP／身份／Agent／生成客户端回归通过，原生与 Trusted 缓存／重试均通过；另一次十项适配器测试覆盖请求头提供方、sampling／elicitation 回调对象保留及原场景。
- `pass`：本地真实 HTTP 样例及归档检查共 12 项通过，覆盖 Trusted 与原生准备、三次获取、两次调用、父上下文恢复与关闭。这不能证明原生云端部署及 APMPlus 入库。
- `pass`：格式化后全文件 pre-commit、文档站生产构建。
- `fail`：独立文档 types:check 生成空 `.source/server.ts` 并报 TS2306。将两份 MDX 暂时恢复为未修改 HEAD 后，同一命令复现相同错误；finally 已恢复工作改动。前序 Trusted 记录中的类型通过不能证明全新检查可稳定通过。
- `pass`：全量 Python 回归 7,958 passed、50 skipped、4 xfailed、88 warnings，耗时 512.83 秒；核对 Python 差异摘要未改变。完整 Agent 自动接入的云端部署与真实 VeIdentity 授权不属于该合成样例的验证证据。
- `pass`：现有隔离 Runtime V26 原生 HTTP 样例及 APMPlus 回查通过：一次准备、三次获取、两次成功内部工具调用，Trace／父子祖先匹配，会话关闭，29 项配置不变且依赖版本与 V25 一致。云端样例直接调用同一实例适配器；Agent 自动组装接入已离线验证，不等于完整 Agent 云端部署。真实 VeIdentity 提供方授权及请求 meta 传播仍是单独范围。

## Agent 自动接入的云端验证扩展

在现有隔离镜像更新授权内，已于样例／测试编辑前评审。1e3c150 旧 Agent 源码与 ba030adb 候选仅相差六行自动接入逻辑，不可变 V26 中的 Agent 身份现已通过构建前写入校验。归档扩为五份，包含 veadk/agent.py；写入任何源码前，要求不可变 V26 基线的 Agent SHA 匹配 8c171a0d8ff5b0db58d7f97427925783beeb1445078808dd7a0507f9b78f6f99。不匹配时构建失败，不影响正在运行的部署。

无参数 loopback 样例使用合成模型配置构造真实 Agent，并通过 Agent.tools 调用；不调用模型，该模式不手动安装适配器。复用启动时的 tracer，保留 provider／exporter 对象及数量，遇到非预期 CozeLoop／TLS 自动导出地址时拒绝执行；不改变环境变量、依赖、SDK、凭据及 29 项 Runtime 配置。实现前补真实 HTTP 和错误基线摘要测试；核对新镜像五个模块、协议中的 Agent 初始化标记及 APM 阶段／父子链。这些检查通过前不宣称完整 Agent 云端通过。

验证结果：`pass`——20 项样例／归档／tracer 检查通过，旧 Agent SHA 门禁和 13 个活动代码文件摘要已核对。隔离 Runtime V27 构造真实 Agent，通过其原生 MCP 工具执行，不手动安装适配器，返回初始化标记；APMPlus 精确查到一次准备、三次获取、两次成功内部调用，Trace／父子祖先一致。SDK／正文开关、依赖版本、既有 provider／exporter 对象及 29 项 Runtime 配置不变。本次未调用模型；真实 VeIdentity 提供方授权及逐次请求 meta 修复仍单独推进。
