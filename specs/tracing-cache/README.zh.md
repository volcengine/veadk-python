# 本地追踪缓存

[English](README.md)

组件 ID：`tracing-cache` · 状态：active · 修订日期：2026-10-13

## 职责与接口

负责 `veadk/tracing/telemetry/exporters/inmemory_exporter.py` 中有界的诊断 span 保存，由 `OpentelemetryTracer` 接入。云端传输、SDK 请求埋点和 Studio 存储属于其他组件。使用方为 `OpentelemetryTracer.dump()` 和 `trace_id`，构造签名保持兼容

## 契约

- CON-1：每个 provider 只有一个缓存，由所有 VeADK 追踪器共用。默认上限为 1024 个 span 和 16777216 估算字节，优先淘汰最旧记录，超过字节预算的单条记录不缓存。其他 exporter 接收未经本缓存修改的 span
- CON-2：`OpenTelemetryConfig.inmemory_enabled` 默认 true。`inmemory_max_spans` 和 `inmemory_max_bytes` 为非负整数，任一为零即关闭保存。环境变量为 `OBSERVABILITY_OPENTELEMETRY_INMEMORY_ENABLED`、`OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_SPANS`、`OBSERVABILITY_OPENTELEMETRY_INMEMORY_MAX_BYTES`。使用现有启动 settings 及 config.yaml 到环境变量的处理方式，非法值导致配置校验失败。首次创建收集器时确定配置，修改后需新建 provider 或重启进程
- CON-3：关闭保存时，保留字段补充处理器、埋点抑制、最新 trace ID 和现有云端导出及 flush 行为，不保留 span 或会话索引。没有对应历史时，`dump()` 写出空数组
- CON-4：会话索引从仍被保留的 `call_llm` span 生成。会话导出按导出顺序返回 trace ID 匹配的保留 span，包括自身没有会话属性的关联 span。会话关联节点被淘汰后，部分 trace 可能无法再通过会话查询。`clear()` 重置 span、大小记录、索引和最新 trace ID。`shutdown()` 清空数据并永久停止保存，flush 不清空数据
- CON-5：导出、读取、清空、关闭通过缓存锁串行处理，provider 注册使用独立锁。读取返回快照，无定时器或新增后台任务。缓存仅存在当前进程内，不持久化。预算覆盖已知 span 数据的估算量，不代表精确 RSS，不包含分配器碎片或其他组件内存

例如：启动前设置 `OBSERVABILITY_OPENTELEMETRY_INMEMORY_ENABLED=false`，保留云端观测并关闭本地历史。有界缓存用于保存近期诊断，完整历史应使用云端存储

## 安全、失败与兼容性

缓存不引入凭据、权限、外部写入或网络操作，现有内容采集及脱敏设置仍由埋点层负责。淘汰仅影响诊断历史，不影响用户会话或云端观测。超大记录只在本地跳过，不打印其内容。有限历史及 provider 内共享替代此前每个追踪器无限保存的行为。不增加依赖或不兼容的 Python 语法

## 验证与变更记录

CON-1/4/5 对应 `tests/test_inmemory_exporter.py`；CON-2 对应 `tests/config/test_tracing_config.py`；CON-1/3/5 集成对应 `tests/test_tracing.py`。使用 `uv run --no-sync --extra dev pytest <paths> -q` 运行，再进行针对性追踪兼容检查及 Ruff。生产 RSS 需要另行提供负载证据

设计与验证：[tracing-memory](../../prd-spec/bugfixes/tracing-memory/2026-10-13-bounded-cache.zh.md)。上述契约已实现，并通过所链接设计记录中的针对性回归检查；尚未发布软件包
