# Studio TEA 前端埋点

Studio 的产品行为数据统一上报到 TEA App `1050062`。火山引擎和 BytePlus
部署共用该应用。实现位于 `frontend/src/telemetry/`；业务组件只能调用该模块导出的
语义化方法，不应直接调用 TEA SDK 或拼接事件名。

## 事件

| 事件 | 含义 |
| --- | --- |
| `studio_entry_viewed` | 用户打开 Studio 前端页面后的一次匿名入口访问；不要求登录。 |
| `studio_session_started` | 用户身份确认且页面可用后开始的一次 Studio 访问；不是 Agent 对话会话。 |
| `studio_agent_deploy` | 部署或更新 Agent。 |
| `studio_sandbox_create` | 创建 Sandbox。 |
| `studio_agent_debug` | 创建 Agent 调试运行。 |
| `studio_agent_connect` | 连接 Agent Runtime、本地 Agent 或 Sandbox。 |
| `studio_agent_message` | 向 Agent 或 Sandbox 发送消息。 |
| `studio_agent_source_download` | 下载 Agent 源码包。 |

除访问事件外，操作事件均上报 `started` 和一个终态 `succeeded` 或 `failed`。
同一次操作复用 `operation_id`，每条物理事件使用不同的 `event_id`，终态自动包含
`duration_ms`。

## 指标口径

- Studio 匿名入口访问次数：`studio_entry_viewed` 去重 `page_instance_id`。
- Studio 使用人数：`studio_session_started` 去重 `user_unique_id`。
- Studio 登录访问次数：`studio_session_started` 去重 `page_instance_id`。
- 活跃用户池数：过滤空值后去重 `user_pool_id`。
- 每池活跃人数：按 `user_pool_id` 分组后去重 `user_unique_id`。
- 操作尝试数：过滤 `status = started` 后去重 `operation_id`。
- 操作成功数：过滤 `status = succeeded` 后去重 `operation_id`。
- 操作成功率：成功操作数除以尝试操作数。
- 操作人数：按所需状态过滤后去重 `user_unique_id`。
- 有效 Agent 对话人数：`studio_agent_message` 去重 `user_unique_id`。
- 有效 Agent 对话数：`studio_agent_message` 去重 `session_id`；只包含至少发送过一条
  消息的对话。

前端事件只能计算时间范围内的活跃用户池和池内活跃用户，不能计算从未访问 Studio
的用户池、池内全部成员或当前 Agent/Sandbox 存量。这些资源存量必须来自后端管理接口
或定期快照。

`account_id` 表示部署当前 Studio 的云账号 ID。它在 `veadk studio deploy/update`
时解析并保存到 Studio 运行时环境中，前端通过匿名可访问的 `/web/ui-config` 获取该值，
用于 `studio_entry_viewed` 和后续登录会话埋点，不应作为登录用户身份使用。

## 数据边界

只允许上报已登记的扁平 string/number 字段。禁止上报 Prompt、消息正文、模型响应、
源码、文件路径、错误堆栈、Cookie、Token、AK/SK 或其他密钥。错误默认保留稳定的
`error_kind`、可选 `error_code` 和适用事件的 `failed_phase`。
`studio_agent_deploy` 失败事件额外允许上报经过前端脱敏与长度限制的 `error_message`，
用于定位部署、构建和 Runtime 初始化失败原因。构建阶段失败时，`error_message` 优先来自
前端已收到的 CodePipeline 构建日志文本；没有可用构建日志时再回退到部署接口返回的
错误摘要。构建日志较长时保留末尾内容，避免截掉通常位于日志尾部的真实失败行。
后端在构建失败的最终同步中会有限重试拉取 CodePipeline 日志，直到保留的日志尾部包含
构建错误 marker，降低日志服务延迟导致埋点只拿到镜像下载/解压进度的概率。
部署主阶段按 `prepare -> upload -> build -> deploy -> publish -> update -> evaluation`
单调推进；CodePipeline 日志事件只更新构建日志，不应把已经进入部署阶段的任务回退为
构建阶段。

`user_unique_id` 通过 TEA `config` 设置，不作为自定义事件属性重复发送。所有资源 ID
在模块边界转换为字符串；布尔属性使用 `0/1`。

## APMPlus 边界

本迁移仅删除 Studio 产品行为埋点使用的前端 APMPlus Web SDK 和配置传递链路。
`veadk/tracing/telemetry/`、APMPlus OpenTelemetry exporter、Runtime trace 和问题反馈中的
APMPlus 查询能力不在迁移范围内并继续保留。

## 开发排障记录

- 检查 Studio 后端使用的 AgentKit SDK 时，应优先使用仓库虚拟环境
  `.venv/bin/python`。当前全局 `python` 命令可能不存在，且全局 `python3` 环境可能未安装
  `agentkit` 包，直接执行 `python3 -c 'import agentkit'` 会得到
  `ModuleNotFoundError: No module named 'agentkit'`。
