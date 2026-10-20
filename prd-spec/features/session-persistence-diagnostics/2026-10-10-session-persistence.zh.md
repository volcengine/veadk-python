# 会话持久化诊断

## 授权与依据
用户已授权按 AgentKit 诊断方案完成埋点，包括 Runtime 持久化阶段。ADK Runner 在执行中调用 SessionService.append_event；AgentkitAgentServerApp 保留调用方提供的 SessionService 实例。VeADK 在 SQLite、MySQL 和 PostgreSQL 工厂中创建 DatabaseSessionService。

## 设计与范围
三个内置工厂使用内部 DatabaseSessionService 子类，为真实 append_event 调用生成 veadk.session.append_event Span；参数、返回值、状态更新、异常和取消行为保持一致。partial 事件不计时，因为 ADK 不持久化它们。复用已有 OTel Provider，采集故障不阻断数据库调用。不记录数据库地址、凭证、事件正文、会话状态或异常正文。不修改自定义 SessionService 与 SDK 的实例身份约定，不新增导出通道、存储或表结构。

## 评审
已对照现有工厂和 SDK 实例身份测试评审。不修改对象方法，不改协议或配置。同步双语 tracing 规范说明范围。SQLite 验证真实持久化；替换基类方法的测试验证取消和采集故障。MySQL / PostgreSQL 工厂在不连接共享数据库的条件下检查。远端部署与 APMPlus 接收仍未验证。

## 任务与验收
- 增加内部数据库计时服务，接入三个内置工厂。
- 验证 SQLite 的事件与状态保存、partial 事件、父上下文、取消、异常脱敏和采集故障。
- 更新 tracing 规范，提交前记录实际测试结果。

## 验证
受影响测试：`uv run --extra dev --extra extensions --extra codex --extra sandbox pytest tests/memory/test_session_persistence_tracing.py tests/memory/test_postgres_schema.py tests/test_adk_compat.py tests/test_short_term_memory.py -q`：32 项通过。真实 ADK Runner 经本地 SQLite 保存事件／状态；父 Trace、关联标识、partial 事件不计时、异常脱敏、取消和采集故障不阻断均已验证。完整回归：6704 项通过、50 项跳过、4 项预期失败（484.07 秒）。跳过项不计作环境验证。

## 2026-10-20 范围纠正：直接指定数据库 URL

继续执行已授权埋点任务时发现另一条 SDK 自建路径：`ShortTermMemory(db_url=...)` 直接创建原始 `DatabaseSessionService`，绕过 CON-6。已有三个工厂的测试未覆盖此入口。当前 Playground 使用的内存后端不能证明数据库持久化路径已经执行。

此构造入口复用同一个内部计时子类，保留 `db_url` 的优先级和 `db_kwargs`。已有类型判断继续使用原基类。不包装调用方自定义服务，不改数据库配置，不记录 URL。将现有真实 SQLite 和 ADK Runner 用例扩展到工厂、直接 URL 两个入口，先复现失败，再验证事件／状态持久化、父 Trace 和脱敏。已有取消、partial 事件和采集故障语义保持不变。

已直接对照原设计与 CON-6 评审，没有 API、鉴权、导出器或存储结构变化。这是用户原有实现授权内的纠正，并已收到继续执行的指令。远端部署与 APMPlus 接收仍单独验收。基于已同步的上游 main `86c93529969e6dde86890b30f7e407bfc32ff5ea` 验证：直接 URL 回归先复现 2 项失败（缺少保存 Span）、1 项通过；修复后受影响用例 35 项通过。完整并行回归 7539 项通过、50 项跳过、4 项预期失败（502.56 秒），排除 `codex_smoke` 和 `piagent_smoke`。`uv run --no-sync --extra dev pre-commit run --all-files` 通过。测试使用既有本地环境、`--no-sync` 和 dev/extensions/codex/sandbox extras。独立的 SDK→VeADK 本地 ASGI 验证覆盖 `/run`、`/run_sse`、`/invoke`：使用全新 SQLite 数据库，每次请求均实际保存事件，并产生 4 个关联请求 Trace 与诊断 Run 的保存 Span；默认内存后端验证也通过。这些是确定性模型的本地验证，不是远端数据库、真实模型或 APMPlus 接收证据。Runtime V6 仍使用此前 VeADK 版本，本次纠正尚未部署。

### 回归环境补充（10/20）

上述 7539 项完整回归使用原有 Python 3.12.14／Google ADK 2.2.0／OpenTelemetry 1.37.0 环境（`--no-sync`）。同步后的上游源码要求 ADK >=2.7,<2.8；因此原结果仅证明旧依赖兼容，不证明新声明依赖组合。本次已从固定提交构建 wheel，并完成 Linux/Python 3.11 依赖解析（ADK 2.7.1、OpenTelemetry 1.42.1）；独立环境运行验证单独记录。

独立新依赖环境验证：基础镜像锁定依赖下 `uv pip check`、35 项受影响测试（13.54 秒）、三个 SDK 入口的 SQLite／内存关联均通过。安装 dev/extensions/codex/sandbox 后的完整回归为 7539 通过、50 跳过、4 预期失败、82 个警告（566.68 秒），排除真实 smoke。扩展回归环境使用 cachetools 6.2.6，基础镜像锁为 7.2.1；Google ADK 2.7.1、OTel 1.42.1、FastMCP 3.4.8 均相同。ADK 提示现有 Google GenAI 自动埋点包低于其建议版本；本次只确认 VeADK 自身模型、工具、保存 Span，不据此认定 ADK 其他自动埋点完整。
