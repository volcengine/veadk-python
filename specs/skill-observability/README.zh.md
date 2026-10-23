# 技能可观测

[English](README.md)

组件：`skill-observability`；状态：implemented（本地验证；全量回归限制见 PRD）；修订：2026-10-22。
关联变更：[skill-observability](../../prd-spec/features/skill-observability/2026-10-16-skill-observability.zh.md)。

## 责任与接口

VeADK 在 `veadk/skills/` 与 `veadk/tracing/telemetry/telemetry.py` 负责 Runtime 技能包获取及 ADK 指令加载埋点。`actb-mono/sandboxes/agentkit-skill` 负责 Python/Go Sandbox 安装、工具适配及 exporter 生命周期。共享下述上报结构；Sandbox 独立发布，不导入尚未发布的 SDK 记录模块。既有工具/签名/结果保持兼容。技能指标采用下述新名称和单位，查询方须同步切换；不重复发送旧名称。技能发现、资源/脚本执行、主动问题汇报和业务成功不属于本组件。

## 契约

- CON-1：`gen_ai_skill_download_count` 是 OTEL counter，单位 `1`；维度严格为 `skill_source`、`skill_id`、`skill_name`、`skill_version`、`skill_space_id`。每次获取结束加一，包含缓存恢复和失败。单纯发现或本地软链接创建不产生事件；结果仅记录在 Span。
- CON-2：`gen_ai_skill_load_count` 是 OTEL counter，单位 `1`；维度严格为上述五个身份字段。每次成功返回指令加一，ADK invocation 缓存命中仍计数。失败、取消、转发、资源/脚本访问不计数。
- CON-3：下载 Span `download_skill {skill_name}` 包含 `skill.source`、`skill.id`、`skill.name`、`skill.version`、`skill.space_id`、`skill.consumer`、`skill.download.outcome`、`skill.download.cache_hit`。结果为 `success` 或 `error`（含取消）；失败增加 `error.type` 和安全的静态 `error.description`，状态为 ERROR。成功加载将既有工具 Span 命名为 `load_skill {skill_name}`，并添加五个点分身份字段和 `skill.consumer`，不新增重复 Span。`skill.consumer` 为 `runtime` 或 `skill_sandbox`。Span 耗时覆盖实际操作。consumer/cache/结果/错误文本不放入 metric 标签。
- CON-4：身份遵循下表。缺失版本/空间用空字符串，不使用生成的缓存 hash。缺少可信 ID 的远端技能和无法分类的本地技能不采集。遥测身份以 Registry 元数据为准，覆盖技能包同名 metadata。SkillHub 安装时随实际安装包记录 slug，不能仅依赖当前期望配置。

`skill_name` 使用当前来源已解析的技能名称：Runtime/技能空间用元数据，本地技能用已加载名称，SkillHub 安装用已解析的安装名称。显式 TOS 获取优先传递版本接口的 `Name`；缺失时在成功获取或缓存恢复后读取已验证包的名称。获取失败且尚无名称时使用空字符串，不用 ID、slug 或路径冒充名称。名称读取仅用于观测，失败不得影响获取结果。

| skill_source | skill_id | skill_name | skill_version | skill_space_id |
| --- | --- | --- | --- | --- |
| builtin_skill | name | name | 空 | 空 |
| skillhub_skill | slug | 已解析名称或空字符串 | 空 | 空 |
| skillhub_skill_space | s-* | 已解析名称或空字符串 | 接口提供时为 sv-* | sp-* |
| agentkit_skill | s-* | 已解析名称或空字符串 | vN | 空 |
| agentkit_skill_space | s-* | 已解析名称或空字符串 | 接口提供或旧包路径中存在的 vN | ss-* |

Python 支持以上五类来源。Sandbox 固定 Go SDK 仍拒绝 `sp-*`，用户已批准保留这一限制。本地 SkillHub 来源记录供 Python/Go 共同读取。

- CON-5：通过全局 OTEL provider 记录，不依赖 Span 采样。Runtime 加载采集随既有 VeADK tracing hook 启用。SDK 记录模块不安装 exporter。Sandbox 周期 OTLP metric 遵循 `OTEL_SDK_DISABLED`、`OTEL_METRICS_EXPORTER=none`、标准 metric/base endpoint 配置，并复用已有 provider。关闭 trace 不关闭 metric。默认本地 collector 使用 4318 端口的 OTLP/HTTP；退出有时间上限，导出失败不阻断业务。Metrics 使用 `OTEL_EXPORTER_OTLP_METRICS_PROTOCOL`（或基础 protocol），支持 HTTP/protobuf 和 grpc；默认间隔为 60000 ms。短生命周期 SkillHub 安装器使用 200 ms exporter 超时，退出前尽力 flush；空配置和仅禁用内置技能跳过初始化。启动开销记录在 PRD。
- CON-6：每次获取独立持有观测状态直到结束，并发 invocation 不共享可变观测状态。Python `to_thread` 等待取消不会停止已经运行的获取：实际获取结果可能稍后产生，但取消的等待者不计指令加载成功。除已安装 SkillHub 的来源记录外，不新增持久化状态。既有锁、缓存验证、保留和清理规则仍然有效。
- CON-7：新增遥测不含原始异常、URL、token、文件路径、指令和用户内容。记录/导出失败不得改变工具结果或吞掉业务异常。不要求新凭据或配置。没有 provider 时采用 OTEL 正常空操作行为。

## 验证与演进

CON-1/4/6 对应 materializer/cache 和 Sandbox package 测试。CON-2/3 对应真实 ADK 工具与 Sandbox wrapper 测试，包含重复加载、参数错误、异常和取消。CON-5/7 对应内存 OTEL 和本地 collector 测试，覆盖 metric、Span、脱敏、开关、provider 复用及故障。具体命令和实际证据在关联 PRD 中维护。增加维度或改变计数语义须重新评审设计并同步双语。implemented 状态不表示已部署或全仓验收通过。
