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
