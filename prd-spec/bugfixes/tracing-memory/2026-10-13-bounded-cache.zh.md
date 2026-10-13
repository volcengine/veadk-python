# 限制本地追踪缓存

[English](2026-10-13-bounded-cache.md)

## 元数据

- 变更 ID：`tracing-memory`
- 创建及修订日期：2026-10-13
- 状态：implemented
- 组件：[追踪缓存](../../../specs/tracing-cache/README.zh.md)

## 背景、目标与范围

已发布的 1.0.9 和 1.1.14 会将每个被采样的 span 追加到进程生命周期内的列表中，每个追踪器还会向全局 provider 注册另一个收集器。会话索引独立增长，`clear()` 不会清理它。反复轮询请求携带的大响应会放大内存占用。源码检查已确认缺陷，尚未测量它在具体生产进程 RSS 中的占比

本次修复限制本地保留量，保留云端 exporter、span 字段补充、采样及埋点抑制行为，继续支持近期会话导出和最新 trace ID。不修改 AgentKit SDK 请求内容、前端行为、生产配置、包版本或部署

## 场景与需求

- FR-1：持续导出时，默认最多保留 1,024 个 span 和 16,777,216 估算字节，淘汰最旧 span 直到同时满足两个限制。单个 span 超限时仅跳过本地缓存，不丢弃之前的有效记录，也不改变云端上报
- FR-2：关闭本地缓存时，不保留 span 或会话索引，仍保留字段补充处理器、最新 trace ID 和云端链路
- FR-3：淘汰、清空或关闭后，不保留过期会话映射。查询返回保留数据的一致快照，并发导出、清理及读取安全
- FR-4：同一 provider 的多个追踪器只在处理流水线首部注册一个共享收集器。不同 provider 拥有各自的缓存，首次创建收集器时确定配置
- FR-5：提供经过校验的配置，明确本地导出只包含仍被保留的历史，云端保留策略由云端 exporter 或服务负责

## 设计与契约影响

使用加锁的 FIFO 双端队列和对应的逐 span 大小记录。通过 Python 对象大小估算已知 span 字段、属性值、资源、事件、链接和埋点元数据，不序列化或复制大块内容。该估算是缓存预算，并非进程 RSS 精确限制；数量限制同时约束元数据开销。超大记录仅跳过本地保存。读取时从仍被保留的 `call_llm` span 生成会话到 trace 的索引，避免独立索引持续增长。若包含会话信息的 span 已被淘汰，对应 trace 可能不再出现在本地会话导出中

在 `OpenTelemetryConfig` 中提供 `inmemory_enabled`、`inmemory_max_spans`、`inmemory_max_bytes`，对应 `OBSERVABILITY_OPENTELEMETRY_INMEMORY_*` 环境变量。默认值为 true、1024、16777216；限制值必须非负，任一限制为零即关闭保存。沿用已有启动 settings/config.yaml 处理方式，修改后需新建 provider 或重启进程

provider 拥有共享 exporter，通过注册锁初始化。即使关闭保存，仍保留现有字段补充处理器。导出、读取、清空和关闭共用缓存锁，关闭为终态。`force_flush()` 不清理历史。不引入后台线程、定时任务、新依赖、额外网络调用或权限变更

未选择的方案：定时清空的峰值仍由流量决定且会整批丢失历史；只限制数量不足以控制大响应；删除处理器会破坏字段补充与埋点抑制。公开 tracer/exporter 构造签名兼容。按设计将本地历史从无限保留改为有限保留，缓存不会截断或过滤任何云端 span

## 任务与验收

| 需求 | 任务 | 验收 | 验证 |
| --- | --- | --- | --- |
| FR-1、FR-3 | T-1：先增加失败回归，再在 `inmemory_exporter.py` 实现有界缓存 | AC-1：数量及字节淘汰、超大内容、会话清理、关闭和并发操作通过 | `uv run --no-sync --extra dev pytest tests/test_inmemory_exporter.py -q` |
| FR-2、FR-4 | T-2：在 `opentelemetry_tracer.py` 共享收集器 | AC-2：多追踪器共用一个收集器，关闭或限制缓存仍保留云端 span、字段和 trace ID | `uv run --no-sync --extra dev pytest tests/test_tracing.py -q` |
| FR-5 | T-3：增加配置校验和双语用户文档及规范 | AC-3：验证默认值、覆盖、零值和非法值 | `uv run --no-sync --extra dev pytest tests/config/test_tracing_config.py -q` |
| 全部 | T-4：检查差异，运行针对性追踪回归及 Ruff，同步双语记录 | AC-4：检查通过，限制被如实记录 | 见交付记录 |

## 风险与审查

有限本地历史可能导致长会话导出不完整。共享缓存覆盖整个 provider，各追踪器竞争同一预算并观察同一近期历史。Python 对象估算不包含分配器碎片和其他组件拥有的内存，不承诺 RSS 上限。不能用本地测试声称生产内存已稳定或云端行为已验证

已直接审查归属、错误、并发、兼容性、配置、双语一致性及验证覆盖，无待解决阻塞项。用户于 2026-10-13 在提出有界缓存方向后要求修复已确认的泄漏。复杂测试及云端操作需后续确认，本次范围内的回归修复不依赖二者

## 交付记录

- 基线：`b8038fb16`；验证日期：2026-10-13
- 范围：有界 exporter、provider 注册、配置、回归测试和双语缓存文档；T-1 至 T-4、AC-1 至 AC-4 已完成
- 实现前回归：按预期 fail，缓存及配置测试 20 项失败、3 项通过，包含旧 span 引用保留和会话状态残留
- 核心检查：pass，`uv run --no-sync --extra dev pytest tests/test_inmemory_exporter.py tests/config/test_tracing_config.py tests/test_tracing.py -q` 共 46 项通过
- 针对性兼容检查：pass，连同核心检查共 75 项通过，覆盖内容采集、LLM 属性提取、运行时 tracing 和 Studio 观测；出现一条原有非法转义警告
- 原有 exporter fixture 在退出时尝试向 `localhost:8000` 发送指标并记录 `UNAVAILABLE`，测试进程退出码为 0；新增缓存及云端导出集成测试使用本地内存替身，不访问云服务
- Ruff 格式及检查、`git diff --check`：pass，覆盖修改的 Python 文件和差异
- 文档：pass，两份 tracing MDX 均通过 `@mdx-js/mdx` 编译，已审查双语契约及配置一致性和相对文档链接
- 提交前检查：pass，同步 `origin/main` 后再次运行 75 项针对性测试，并通过 `uv run --no-sync --extra dev pre-commit run --all-files`，包含 Ruff 和两项密钥扫描
- 全量回归、文档站构建及类型检查：not_run，按当前流程仅执行针对性检查，未修改前端应用
- 生产及云端验证：not_run，未要求访问或修改生产环境
- UI 验证：not_applicable，无前端行为变更
- 提交及 PR：已获授权；软件包发布及生产部署：not_run，不在本次范围内
