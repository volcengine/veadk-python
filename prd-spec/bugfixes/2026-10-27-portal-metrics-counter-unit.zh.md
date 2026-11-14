# Bugfix PRD：chat_exception_counter 单位

## 背景 / 证据
`veadk/tracing/telemetry/portal_metrics.py` 中 `chat_exception_counter` 使用
`unit="time"` 创建，但其 description 为「聊天补全期间发生的异常数量」。计数离散事件的
counter 不应使用时长单位；同文件 `llm_invoke_counter` 为 `"count"`，
`skill_download_counter` / `skill_load_counter` 已为 `"1"`。

## 目标
- 将 `chat_exception_counter` 对齐为计数单位（`"1"`）。
- 新增仅依赖标准库的静态回归守卫，校验 counter 单位元数据。

## 非目标
- 不改动 span/事件契约、公共 API、依赖或指标名。
- 不改动运行时装配；不新增指标。

## 场景
- 运营方基于 `llm_completions_exceptions` 搭建看板时看到的是无量纲计数，而非时长单位。

## 影响文件
- `veadk/tracing/telemetry/portal_metrics.py`（一行：unit `"time"` -> `"1"`）
- `tests/test_portal_metrics_counter_unit.py`（新增，静态守卫）

## 测试
- 静态测试在隔离环境本地运行：base main `2301477` 上 exception counter 断言失败
  （RED），head 上通过（GREEN）；sibling counter 范围守卫在两个版本上均通过。
- 基于 recorder 的运行时测试（`test_portal_metrics.py`）依赖 google.adk，本地不运行，交给 CI。

## 风险
- 仅影响看板单位展示；无数据迁移。风险可忽略。

## 验收
- `chat_exception_counter` 单位为 `"1"`；静态回归通过；其他 counter 单位未改动。
